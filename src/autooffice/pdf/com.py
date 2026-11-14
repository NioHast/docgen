"""Guard COM Windows, lifecycle apartment, timeout, dan cleanup proses Office.

Modul ini adalah lapisan bawah adapter :mod:`autooffice.pdf.word` dan
:mod:`autooffice.pdf.powerpoint`. Import pywin32 dilakukan lazy agar paket
``autooffice.pdf`` tetap dapat diimpor di Linux atau mesin tanpa Office.
Pemanggilan Word/PowerPoint nyata hanya terjadi di Windows dengan Microsoft
Office desktop.

Tidak ada PowerShell dan tidak ada subprocess ke ``scripts/word.ps1``.
Serialisasi memakai lock file. Cleanup proses hanya menyentuh PID yang
diidentifikasi secara eksplisit sebagai proses automation melalui window handle
aplikasi COM, lalu diverifikasi ulang nama image dan creation time sebelum
``taskkill``.
"""

import contextlib
import csv
import importlib
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from types import ModuleType
from typing import Any, BinaryIO, Protocol, cast

from autooffice.errors import AutoOfficeError

WORD_IMAGE = "WINWORD.EXE"
"""Nama image proses Microsoft Word."""

POWERPOINT_IMAGE = "POWERPNT.EXE"
"""Nama image proses Microsoft PowerPoint."""

COM_LOCK_FILE = "docgen-word.lock"
"""Nama lock file global untuk seluruh operasi COM Word/PowerPoint."""

DEFAULT_LOCK_TIMEOUT_S = 30.0
"""Batas tunggu lock COM dalam detik."""

WATCHDOG_CLEANUP_TIMEOUT_S = 5.0
"""Batas tunggu worker setelah watchdog timeout sebelum cleanup dianggap ambigu."""

_LOCK_POLL_S = 0.05
_TASKLIST_TIMEOUT_S = 15
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _clamp_task_timeout(timeout_s: float) -> float:
    """Batasi timeout tasklist/taskkill tanpa melebihi budget pemanggil."""

    if math.isnan(timeout_s):
        return 0.0
    return max(0.0, min(_TASKLIST_TIMEOUT_S, timeout_s))


class PdfUnavailableError(AutoOfficeError):
    """Microsoft Word/PowerPoint COM atau pywin32 tidak tersedia di mesin ini."""


class WordComError(AutoOfficeError):
    """Pemanggilan Microsoft Word/PowerPoint lewat COM gagal."""


class WordTimeoutError(WordComError):
    """Operasi Word/PowerPoint melewati batas waktu yang diminta."""


class WordCleanupError(WordTimeoutError):
    """Worker COM tidak berhenti setelah timeout sehingga cleanup tidak pasti.

    Error ini sengaja dibedakan dari :class:`WordTimeoutError` biasa karena
    worker yang masih hidup dapat menulis ke snapshot/temp setelah pemanggil
    menerima error. Pemanggil tidak boleh menghapus direktori kerja pada kasus
    ini; pesan error menyebutkan bahwa cleanup ambigu.
    """

    cleanup_ambiguous: bool = True


class WordBusyError(WordComError):
    """Lock COM tidak diperoleh karena proses lain masih memakainya."""


class ProcessSnapshotError(WordComError):
    """Snapshot proses Office gagal sehingga cleanup PID tidak dapat dijamin."""


def _platform() -> str:
    """Platform Python saat ini; seam untuk test guard non-Windows."""

    return sys.platform


def _is_windows() -> bool:
    """True bila lock COM dan proses Windows relevan."""

    return os.name == "nt" and _platform() == "win32"


def _import_module(name: str) -> ModuleType:
    """Seam import lazy agar test tidak memuat pywin32."""

    return importlib.import_module(name)


def _is_32bit_process() -> bool:
    """True bila interpreter Python berjalan sebagai proses 32-bit."""

    return struct.calcsize("P") == 4


def _windows_system_directory() -> Path | None:
    """Path absolut ``System32`` dari ``GetSystemDirectoryW``, atau ``None``."""

    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except AttributeError, ImportError:
        return None
    try:
        kernel32: Any = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
        kernel32.GetSystemDirectoryW.restype = wintypes.UINT
        buffer = ctypes.create_unicode_buffer(260)
        length = kernel32.GetSystemDirectoryW(buffer, len(buffer))
        if not length:
            return None
        path = Path(buffer.value)
        return path if path.is_absolute() else None
    except AttributeError, OSError, ValueError:
        return None


def _system32_tool(name: str) -> str:
    r"""Path absolut tool Windows di ``%SystemRoot%\System32``.

    Proses Python 32-bit di Windows 64-bit melihat ``System32`` yang
    di-redirect ke ``SysWOW64``. ``Sysnative`` dipakai lebih dulu agar tool
    yang dijalankan tetap versi native dan tidak bisa dibajak executable di
    direktori kerja atau ``PATH``. ``SYSTEMROOT``/``WINDIR`` yang relatif
    diabaikan; path absolut dicari lewat ``GetSystemDirectoryW`` dan bila
    gagal operasi ditolak.
    """

    if os.name != "nt":
        return name
    system32: Path | None = None
    for env_name in ("SYSTEMROOT", "WINDIR"):
        system_root = os.environ.get(env_name)
        if not system_root:
            continue
        root = Path(system_root)
        if root.is_absolute():
            system32 = root / "System32"
            break
    if system32 is None:
        system32 = _windows_system_directory()
    if system32 is None:
        raise OSError(
            "SystemRoot tidak tersedia sebagai path absolut; tool proses Windows "
            "tidak dapat dilokasi."
        )
    if _is_32bit_process():
        sysnative = system32.parent / "Sysnative"
        if sysnative.is_dir():
            system32 = sysnative
    return str(system32 / name)


def _process_creation_time(pid: int) -> int | None:
    """Creation time proses Windows dalam 100 ns ticks, atau ``None``.

    Nilai ini dibandingkan persis dengan nilai yang dicatat saat PID diklaim.
    PID yang sudah dipakai ulang akan punya creation time berbeda sehingga
    tidak boleh dihentikan.
    """

    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except AttributeError, ImportError:
        return None
    try:
        kernel32: Any = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None
            return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        finally:
            kernel32.CloseHandle(handle)
    except AttributeError, OSError, ValueError:
        return None


def _window_process_id(hwnd: int) -> int | None:
    """PID pemilik window handle melalui ``GetWindowThreadProcessId``."""

    if os.name != "nt" or hwnd <= 0:
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except AttributeError, ImportError:
        return None
    try:
        user32: Any = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        process_id = wintypes.DWORD()
        thread_id = user32.GetWindowThreadProcessId(
            wintypes.HWND(int(hwnd)),
            ctypes.byref(process_id),
        )
        if not thread_id or not process_id.value:
            return None
        return int(process_id.value)
    except AttributeError, OSError, ValueError:
        return None


def application_window_handle(application: Any) -> int | None:
    """Ambil ``Application.Hwnd`` Office tanpa melempar error ke pemanggil."""

    try:
        hwnd = int(application.Hwnd)
    except Exception:  # noqa: BLE001 - identifikasi PID bersifat best-effort
        return None
    return hwnd if hwnd > 0 else None


def limit_process_control(control: ProcessControl, timeout_s: float) -> None:
    """Batasi tasklist/taskkill pada control yang mendukung budget waktu."""

    setter = getattr(control, "set_timeout", None)
    if callable(setter):
        setter(max(0.0, timeout_s))


def validate_timeout(timeout_s: float) -> float:
    """Validasi batas waktu positif dan terbatas.

    ``timeout_s`` dipakai untuk watchdog, sehingga nilai nol, negatif, atau
    tak hingga tidak punya arti yang aman.
    """

    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s harus angka positif yang terbatas.")
    return timeout_s


def load_com_modules() -> tuple[Any, Any]:
    """Impor ``win32com.client`` dan ``pythoncom`` secara lazy.

    Di platform non-Windows atau tanpa pywin32, fungsi ini melempar
    :class:`PdfUnavailableError` dengan tindakan yang dapat dilakukan
    pengguna. Modul ``autooffice.pdf`` sendiri tidak mengimpor pywin32 saat
    import time.
    """

    if _platform() != "win32":
        raise PdfUnavailableError(
            "PDF Office hanya tersedia di Windows dengan Microsoft Word atau "
            "PowerPoint desktop. Jalankan build PDF di Windows atau gunakan "
            "`--target docx`."
        )
    try:
        client: Any = _import_module("win32com.client")
        pythoncom: Any = _import_module("pythoncom")
    except ImportError as exc:
        raise PdfUnavailableError(
            "pywin32 tidak terpasang sehingga COM Office tidak dapat dipakai. "
            "Di Windows, jalankan `uv sync --extra windows` atau "
            "`pip install pywin32`, lalu ulangi build PDF."
        ) from exc
    return client, pythoncom


@contextlib.contextmanager
def com_apartment(pythoncom: Any) -> Iterator[None]:
    """Masuk apartment COM pada thread pemanggil dan selalu uninitialize."""

    try:
        pythoncom.CoInitialize()
    except Exception as exc:
        raise PdfUnavailableError(
            "COM Windows tidak dapat diinisialisasi. Pastikan Microsoft Word "
            "desktop terpasang dan sesi pengguna interaktif. "
            f"Detail: {exc}"
        ) from exc
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            pythoncom.CoUninitialize()


@dataclass(frozen=True, slots=True)
class Deadline:
    """Batas waktu berbasis jam monotonic dengan clock yang dapat diganti."""

    timeout_s: float
    started_at: float
    clock: Callable[[], float]

    @classmethod
    def start(cls, timeout_s: float, *, clock: Callable[[], float] = time.monotonic) -> Deadline:
        """Mulai hitungan pada ``clock()`` saat ini."""

        validate_timeout(timeout_s)
        return cls(timeout_s=timeout_s, started_at=clock(), clock=clock)

    def remaining(self) -> float:
        """Sisa waktu dalam detik; negatif berarti sudah lewat batas."""

        return self.timeout_s - (self.clock() - self.started_at)

    def check(self, step: str) -> None:
        """Lempar :class:`WordTimeoutError` bila langkah sudah lewat batas."""

        if self.remaining() <= 0:
            raise WordTimeoutError(
                f"Word tidak menyelesaikan langkah '{step}' dalam {self.timeout_s:g} detik."
            )

    def remaining_or_raise(self, step: str) -> float:
        """Kembalikan sisa waktu positif atau lempar timeout untuk ``step``.

        Waktu dibaca satu kali agar balapan antara pemeriksaan dan pemakaian
        tidak dapat mengembalikan nilai negatif ke pemanggil.
        """

        remaining = self.remaining()
        if remaining <= 0:
            raise WordTimeoutError(
                f"Word tidak menyelesaikan langkah '{step}' dalam {self.timeout_s:g} detik."
            )
        return remaining


def _ensure_lock_byte(handle: BinaryIO) -> None:
    """Pastikan lock file punya satu byte untuk dikunci."""

    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)


@contextlib.contextmanager
def com_lock(
    *,
    timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
    lock_path: Path | None = None,
) -> Iterator[None]:
    """Serialisasi operasi COM Word/PowerPoint lintas proses.

    Di non-Windows fungsi ini no-op. Di Windows lock memakai
    ``msvcrt.locking`` pada ``%TEMP%/docgen-word.lock`` agar satu mesin hanya
    menjalankan satu operasi COM pada satu waktu.
    """

    if not _is_windows():
        yield
        return

    msvcrt: Any = _import_module("msvcrt")
    path = lock_path or Path(tempfile.gettempdir()) / COM_LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        _ensure_lock_byte(handle)
        deadline = Deadline.start(timeout_s)
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if deadline.remaining() <= 0:
                    raise WordBusyError(
                        f"COM Word sedang dipakai proses lain; lock '{path}' "
                        f"tidak diperoleh dalam {timeout_s:g} detik."
                    ) from exc
                time.sleep(_LOCK_POLL_S)
        try:
            yield
        finally:
            handle.seek(0)
            with contextlib.suppress(OSError):
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class ProcessControl(Protocol):
    """Operasi proses minimum yang dibutuhkan tracker PID Office."""

    def list_word_pids(self) -> set[int] | None:
        """PID semua proses ``WINWORD.EXE``, atau ``None`` bila snapshot gagal."""

        ...

    def list_powerpoint_pids(self) -> set[int] | None:
        """PID semua proses ``POWERPNT.EXE``, atau ``None`` bila snapshot gagal."""

        ...

    def image_name(self, pid: int) -> str | None:
        """Nama image untuk ``pid``, atau ``None`` bila proses tidak ada."""

        ...

    def creation_time(self, pid: int) -> int | None:
        """Creation time proses dalam 100 ns ticks, atau ``None``."""

        ...

    def pid_for_window(self, hwnd: int) -> int | None:
        """PID pemilik window handle, atau ``None`` bila tidak dapat dipastikan."""

        ...

    def terminate(self, pid: int) -> bool:
        """Hentikan satu PID beserta pohon prosesnya."""

        ...


def _tasklist_rows(
    *filters: str,
    timeout_s: float = _TASKLIST_TIMEOUT_S,
) -> list[list[str]] | None:
    """Jalankan tasklist dan kembalikan baris CSV, atau ``None`` bila gagal."""

    budget = _clamp_task_timeout(timeout_s)
    if budget <= 0:
        return None
    try:
        executable = _system32_tool("tasklist.exe")
    except OSError:
        return None
    command = [executable, *filters, "/FO", "CSV", "/NH"]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=budget,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    rows: list[list[str]] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith('"'):
            continue
        rows.append(next(csv.reader([stripped]), []))
    return rows


def _image_pids(image: str, *, timeout_s: float = _TASKLIST_TIMEOUT_S) -> set[int] | None:
    """PID semua proses yang cocok dengan nama image tertentu."""

    rows = _tasklist_rows("/FI", f"IMAGENAME eq {image}", timeout_s=timeout_s)
    if rows is None:
        return None
    pids: set[int] = set()
    for row in rows:
        if len(row) < 2 or row[0].strip().upper() != image:
            continue
        with contextlib.suppress(ValueError):
            pids.add(int(row[1].strip()))
    return pids


class SystemProcessControl:
    """Kontrol proses Windows lewat tasklist/taskkill, tanpa PowerShell."""

    def __init__(self, *, timeout_s: float = _TASKLIST_TIMEOUT_S) -> None:
        self._timeout_s = _clamp_task_timeout(timeout_s)

    def set_timeout(self, timeout_s: float) -> None:
        """Batasi tasklist/taskkill berikutnya dengan sisa budget operasi."""

        self._timeout_s = _clamp_task_timeout(timeout_s)

    def list_word_pids(self) -> set[int] | None:
        """PID proses Word yang sedang berjalan."""

        return _image_pids(WORD_IMAGE, timeout_s=self._timeout_s)

    def list_powerpoint_pids(self) -> set[int] | None:
        """PID proses PowerPoint yang sedang berjalan."""

        return _image_pids(POWERPOINT_IMAGE, timeout_s=self._timeout_s)

    def image_name(self, pid: int) -> str | None:
        """Nama image untuk PID tertentu."""

        for row in _tasklist_rows("/FI", f"PID eq {pid}", timeout_s=self._timeout_s) or []:
            if len(row) >= 2 and row[1].strip() == str(pid):
                return row[0].strip() or None
        return None

    def creation_time(self, pid: int) -> int | None:
        """Creation time PID tertentu, atau ``None`` bila tidak dapat dibaca."""

        return _process_creation_time(pid)

    def pid_for_window(self, hwnd: int) -> int | None:
        """PID pemilik window handle melalui Win32."""

        return _window_process_id(hwnd)

    def terminate(self, pid: int) -> bool:
        """Hentikan PID yang sudah dipastikan milik automation."""

        if self._timeout_s <= 0:
            return False
        try:
            executable = _system32_tool("taskkill.exe")
            completed = subprocess.run(
                [executable, "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self._timeout_s,
            )
        except OSError, subprocess.TimeoutExpired:
            return False
        return completed.returncode == 0


@dataclass
class _ProcessTracker:
    """Lacak PID Office automation dan bersihkan hanya PID yang pasti miliknya.

    ``before`` diambil sebelum COM membuat aplikasi dan tidak boleh berupa
    ``None``. PID automation diidentifikasi dari ``Application.Hwnd`` lewat
    ``GetWindowThreadProcessId``; snapshot PID baru hanya dipakai sebagai
    pemeriksaan silang. Bila PID tidak dapat dipastikan secara unik, tracker
    tidak mengklaim apa pun dan cleanup tidak menghentikan proses apa pun.
    """

    control: ProcessControl
    image: str
    before: set[int]
    list_pids: Callable[[], set[int] | None] = field(repr=False, compare=False)
    _pid: int | None = field(default=None, init=False)
    _creation_time: int | None = field(default=None, init=False)
    _ready: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _terminated: bool = field(default=False, init=False)

    def claim(self, *, hwnd: int | None = None) -> int | None:
        """Catat PID automation dari window handle, atau ``None`` bila ambigu.

        PID dari ``Hwnd`` harus lolos semua pemeriksaan: bukan PID yang sudah
        ada di snapshot awal, terlihat oleh snapshot baru, image-nya cocok, dan
        creation time-nya dapat dibaca. Tidak ada fallback ke "PID baru
        terendah" karena PID baru bisa saja milik pengguna yang membuka Office
        setelah ``begin``.
        """

        claimed: tuple[int, int] | None = None
        try:
            resolver = getattr(self.control, "pid_for_window", None)
            pid = resolver(hwnd) if hwnd is not None and callable(resolver) else None
            if pid is not None and pid > 0 and pid not in self.before:
                after = self.list_pids()
                if after is not None and pid in after:
                    creation_reader = getattr(self.control, "creation_time", None)
                    image = self.control.image_name(pid)
                    creation_time = creation_reader(pid) if callable(creation_reader) else None
                    if (
                        image is not None
                        and image.strip().upper() == self.image
                        and creation_time is not None
                    ):
                        claimed = (pid, creation_time)
        except Exception:  # noqa: BLE001 - PID ambigu berarti tanpa cleanup
            claimed = None
        with self._lock:
            if claimed is None:
                self._pid = None
                self._creation_time = None
            else:
                self._pid, self._creation_time = claimed
            pid = self._pid
        self._ready.set()
        return pid

    @property
    def pid(self) -> int | None:
        """PID yang sudah dicatat, bila ada."""

        with self._lock:
            return self._pid

    def terminate_owned(self, *, wait_s: float = 0.0) -> bool:
        """Hentikan PID Office milik automation bila masih hidup.

        ``wait_s`` dipakai watchdog untuk menunggu ``claim`` selesai sebelum
        memutuskan apakah ada PID yang perlu dihentikan. Sebelum ``taskkill``,
        nama image dan creation time dibaca ulang; PID yang sudah dipakai ulang
        proses lain tidak pernah dihentikan.
        """

        if wait_s > 0:
            self._ready.wait(wait_s)
        with self._lock:
            if self._terminated:
                return False
            pid = self._pid
            creation_time = self._creation_time
        if pid is None or creation_time is None:
            return False
        image = self.control.image_name(pid)
        creation_reader = getattr(self.control, "creation_time", None)
        current_creation_time = creation_reader(pid) if callable(creation_reader) else None
        if (
            image is None
            or image.strip().upper() != self.image
            or current_creation_time is None
            or current_creation_time != creation_time
        ):
            return False
        terminated = self.control.terminate(pid)
        if terminated:
            with self._lock:
                self._terminated = True
        return terminated


def _begin_tracker(
    *,
    list_pids: Callable[[], set[int] | None],
) -> tuple[set[int], Callable[[], set[int] | None]]:
    """Ambil baseline snapshot; batalkan sebelum COM bila snapshot gagal."""

    before = list_pids()
    if before is None:
        raise ProcessSnapshotError(
            "Snapshot proses Office gagal dibaca, sehingga PID automation "
            "tidak dapat dibedakan dari proses pengguna. Operasi dibatalkan "
            "sebelum aplikasi COM dibuat agar Word/PowerPoint pengguna tidak "
            "ikut dihentikan."
        )
    return set(before), list_pids


@dataclass
class WordProcessTracker(_ProcessTracker):
    """Lacak PID Word baru dan bersihkan hanya PID milik automation."""

    @classmethod
    def begin(cls, control: ProcessControl) -> WordProcessTracker:
        """Ambil snapshot proses sebelum Word dibuat.

        Raises:
            ProcessSnapshotError: Snapshot gagal; Word belum boleh dibuat.

        """

        before, list_pids = _begin_tracker(list_pids=control.list_word_pids)
        return cls(control=control, image=WORD_IMAGE, before=before, list_pids=list_pids)


@dataclass
class PowerPointProcessTracker(_ProcessTracker):
    """Lacak PID PowerPoint baru dan bersihkan hanya PID milik automation."""

    @classmethod
    def begin(cls, control: ProcessControl) -> PowerPointProcessTracker:
        """Ambil snapshot proses sebelum PowerPoint dibuat.

        Raises:
            ProcessSnapshotError: Snapshot gagal; PowerPoint belum boleh dibuat.

        """

        before, list_pids = _begin_tracker(list_pids=control.list_powerpoint_pids)
        return cls(control=control, image=POWERPOINT_IMAGE, before=before, list_pids=list_pids)


def run_with_watchdog[T](
    operation: Callable[[], T],
    *,
    timeout_s: float,
    on_timeout: Callable[[], object],
    description: str,
    cleanup_timeout_s: float | None = None,
) -> T:
    """Jalankan operasi COM di thread daemon dengan timeout wall-clock.

    Saat timeout, ``on_timeout`` dipanggil untuk menghentikan PID automation,
    lalu worker ditunggu sampai selesai sebelum direktori kerja dibersihkan.
    Bila worker masih hidup setelah ``cleanup_timeout_s``, fungsi melempar
    :class:`WordCleanupError` yang menyatakan cleanup ambigu; pemanggil tidak
    boleh menghapus temp selama worker dapat menulis ke sana.
    """

    validate_timeout(timeout_s)
    outcome: Queue[tuple[bool, object]] = Queue(maxsize=1)

    def worker() -> None:
        try:
            outcome.put((True, operation()))
        except Exception as exc:  # noqa: BLE001 - semua kegagalan worker diteruskan
            outcome.put((False, exc))

    thread = threading.Thread(target=worker, name="autooffice-com", daemon=True)
    thread.start()
    try:
        ok, value = outcome.get(timeout=timeout_s)
    except Empty:
        cleanup_error: Exception | None = None
        try:
            on_timeout()
        except Exception as exc:  # noqa: BLE001 - cleanup tidak boleh menimpa timeout
            cleanup_error = exc
        wait_s = (
            WATCHDOG_CLEANUP_TIMEOUT_S if cleanup_timeout_s is None else max(0.0, cleanup_timeout_s)
        )
        thread.join(wait_s)
        if thread.is_alive():
            raise WordCleanupError(
                f"{description} melewati {timeout_s:g} detik dan worker COM "
                f"masih berjalan setelah {wait_s:g} detik cleanup. Cleanup "
                "ambigu (ambiguous cleanup): proses/temp tidak boleh disentuh "
                "karena worker dapat masih menulis. Periksa proses Office secara "
                "manual."
            ) from cleanup_error
        raise WordTimeoutError(
            f"{description} tidak selesai dalam {timeout_s:g} detik; "
            "upaya cleanup proses Office milik automation sudah dijalankan."
        ) from cleanup_error
    thread.join()
    if not ok:
        raise cast(BaseException, value)
    return cast(T, value)
