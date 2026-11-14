r"""Guard COM Windows, lifecycle apartment, timeout, dan cleanup proses Office.

Modul ini adalah lapisan bawah adapter :mod:`autooffice.pdf.word` dan
:mod:`autooffice.pdf.powerpoint`. Import pywin32 dilakukan lazy agar paket
``autooffice.pdf`` tetap dapat diimpor di Linux atau mesin tanpa Office.
Pemanggilan Word/PowerPoint nyata hanya terjadi di Windows dengan Microsoft
Office desktop.

Tidak ada PowerShell dan tidak ada subprocess ke adapter PowerShell lama.
Serialisasi memakai lock file. Cleanup proses hanya menyentuh PID yang
dibuktikan sebagai proses automation: Word memakai snapshot PID ``WINWORD.EXE``
baru plus window ``OpusApp`` milik PID itu dan verifikasi ulang
``ActiveWindow.Hwnd``; PowerPoint menolak instance yang sudah berjalan lalu
membuktikan tepat satu PID ``POWERPNT.EXE`` baru. Nama image dan creation time
diverifikasi ulang sebelum ``taskkill``; ``Quit`` hanya dipanggil untuk
instance yang PID-nya sudah diklaim.

Penemuan dan penghentian proses memakai ``tasklist.exe``/``taskkill.exe``
lewat ``subprocess``, bukan ``win32process``. Alasannya: ``win32process``
memang dapat mengenumerasi dan membuka proses, tetapi menghentikan pohon
proses membutuhkan Job Object (``win32job``) beserta manajemen handle yang
rawan bocor dan sulit diuji. ``taskkill /T /F`` lebih sederhana dan sudah
menangani proses anak. Kedua tool selalu dipanggil lewat path absolut
``%SystemRoot%\System32`` (atau ``Sysnative`` untuk Python 32-bit di Windows
64-bit) tanpa shell, sehingga executable di ``PATH`` atau direktori kerja tidak
dapat dibajak.

Risiko yang diterima dan mitigasinya:

- Output CSV ``tasklist`` bergantung pada locale dan versi Windows. Parser
  bersikap defensif: baris yang tidak dikenali dilewati, dan hanya image/PID
  yang cocok serta numerik yang dipakai. Kegagalan parsing berujung pada tidak
  ada PID yang diklaim (cleanup dibatalkan), bukan menebak PID.
- Format CSV dapat berubah pada rilis Windows mendatang; kegagalan menjalankan
  atau membaca tasklist dikembalikan sebagai ``None`` sehingga tracker
  membatalkan operasi alih-alih memakai snapshot kosong.
- Setiap snapshot dan terminasi memakai subprocess sehingga ada overhead
  pembuatan proses.
- Ada race antara snapshot dan klaim PID. Word mengklaim hanya PID baru yang
  juga memiliki window ``OpusApp``, PowerPoint hanya saat tepat satu PID baru
  muncul; image dan creation time diverifikasi ulang tepat sebelum ``taskkill``.
- Bila worker COM tetap hidup setelah batas cleanup, :class:`WordCleanupError`
  dilempar sebagai fail-safe; pemanggil tidak boleh menghapus temp karena
  worker dapat masih menulis.
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

COM_LOCK_FILE = "autooffice-word.lock"
"""Nama lock file global untuk seluruh operasi COM Word/PowerPoint."""

DEFAULT_LOCK_TIMEOUT_S = 30.0
"""Batas tunggu lock COM dalam detik."""

CLEANUP_TIMEOUT_S = 5.0
"""Anggaran tetap cleanup PID/worker setelah timeout, dalam detik.

Nilainya tidak boleh berasal dari sisa deadline operasi: saat watchdog
timeout, sisa deadline sudah nol atau negatif sehingga cleanup akan menjadi
no-op.
"""

QUIT_VERIFY_TIMEOUT_S = 1.0
"""Batas tunggu singkat setelah ``Quit`` sebelum status PID diverifikasi."""

WATCHDOG_CLEANUP_TIMEOUT_S = CLEANUP_TIMEOUT_S
"""Alias historis :data:`CLEANUP_TIMEOUT_S` untuk pemanggil lama."""

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


class WordOwnershipError(WordComError):
    """PID instance Office tidak dapat dibuktikan milik automation.

    Error ini mencegah ``Quit``/``taskkill`` menyentuh instance Office
    pengguna ketika proses bersama tidak dapat dibedakan dengan aman.
    """


class WordTimeoutError(WordComError):
    """Operasi Word/PowerPoint melewati batas waktu yang diminta."""


class WordCleanupError(WordComError):
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
    """Ambil ``Application.Hwnd`` Office tanpa melempar error ke pemanggil.

    Untuk Word, ``Application.Hwnd`` tidak tersedia; gunakan
    :func:`find_word_window_handle` sebelum dokumen dibuka dan
    ``Application.ActiveWindow.Hwnd`` setelah dokumen terbuka.
    """

    try:
        hwnd = int(application.Hwnd)
    except Exception:  # noqa: BLE001 - identifikasi PID bersifat best-effort
        return None
    return hwnd if hwnd > 0 else None


WORD_WINDOW_CLASS = "OpusApp"
"""Class name window utama Microsoft Word."""


def find_word_window_handle(pid: int) -> int | None:
    """Cari HWND top-level Word yang PID-nya persis ``pid``.

    ``Application.Hwnd`` tidak tersedia sebelum dokumen dibuka, dan caption
    ``"Word"`` juga dapat dimiliki instance pengguna. Karena itu semua window
    top-level class ``OpusApp`` dienumerasi dan hanya HWND dengan PID automation
    baru yang dipilih. ``None`` berarti tidak ada window yang cocok.
    """

    if os.name != "nt":
        return None
    try:
        win32gui: Any = _import_module("win32gui")
    except ImportError:
        return None

    matches: list[int] = []

    def collect(hwnd: Any, _extra: Any) -> bool:
        try:
            numeric = int(hwnd)
            if (
                win32gui.GetClassName(numeric) == WORD_WINDOW_CLASS
                and _window_process_id(numeric) == pid
            ):
                matches.append(numeric)
        except Exception:  # noqa: BLE001 - lanjutkan enumerasi window lain
            return True
        return True

    try:
        win32gui.EnumWindows(collect, None)
    except Exception:  # noqa: BLE001 - enumerasi gagal berarti tidak ada klaim
        return None
    return matches[0] if matches else None


def query_process_running(control: object, pid: int) -> bool | None:
    """Tanyakan status PID ke control: hidup, hilang, atau tidak pasti."""

    checker = getattr(control, "is_running", None)
    if not callable(checker):
        return None
    try:
        status = checker(pid)
    except Exception:  # noqa: BLE001 - status tak terbaca berarti tidak pasti
        return None
    return status if isinstance(status, bool) else None


def quit_owned_application(application: Any, tracker: Any) -> None:
    """``Quit`` hanya instance yang PID-nya sudah diklaim tracker.

    ``Quit`` dipanggil paling banyak sekali. Keberhasilan ``Quit`` bukan bukti
    proses sudah keluar: status PID diverifikasi ulang secara singkat, dan
    ``terminate_owned`` dipanggil dengan anggaran cleanup tetap bila proses
    masih hidup atau statusnya tidak dapat dipastikan.
    """

    pid = tracker.pid
    if pid is None:
        return
    with contextlib.suppress(Exception):
        application.Quit()
    status = query_process_running(tracker.control, pid)
    deadline = time.monotonic() + QUIT_VERIFY_TIMEOUT_S
    while status is True and time.monotonic() < deadline:
        time.sleep(_LOCK_POLL_S)
        status = query_process_running(tracker.control, pid)
    if status is not False:
        with contextlib.suppress(Exception):
            tracker.terminate_owned(wait_s=CLEANUP_TIMEOUT_S)


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
    ``msvcrt.locking`` pada ``%TEMP%/autooffice-word.lock`` agar satu mesin
    hanya menjalankan satu operasi COM pada satu waktu.
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

    def is_running(self, pid: int) -> bool | None:
        """Status PID: ``True`` hidup, ``False`` sudah hilang, ``None`` tak pasti."""

        ...


# ---------------------------------------------------------------------------
# Penemuan dan penghentian proses: tasklist/taskkill, bukan win32process
# ---------------------------------------------------------------------------
# pywin32 ``win32process`` dapat mengenumerasi dan membuka proses, tetapi
# menghentikan satu pohon proses memerlukan Job Object (``win32job``) plus
# manajemen handle. ``taskkill /PID <pid> /T /F`` lebih sederhana, sudah
# menangani proses anak, dan tidak memerlukan shell. Agar tidak bisa dibajak
# executable di CWD/PATH, tool selalu dipanggil lewat path absolut
# ``%SystemRoot%\System32`` (atau ``Sysnative`` untuk Python 32-bit) tanpa
# ``shell=True``.
#
# Risiko: output CSV ``tasklist`` bergantung pada locale/versi Windows,
# formatnya bisa berubah, dan setiap panggilan menambah overhead subprocess.
# Parser di bawah bersikap defensif; baris yang tidak dikenali dilewati
# sehingga PID yang tidak lolos verifikasi tidak pernah diklaim, dan kegagalan
# menjalankan/membaca tasklist dikembalikan sebagai ``None`` supaya tracker
# membatalkan operasi (fail-safe), bukan menebak PID. PID yang diklaim tetap
# diverifikasi ulang lewat image dan creation time sebelum taskkill untuk
# menutup race PID reuse antara snapshot dan klaim.
# ---------------------------------------------------------------------------


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
    """Kontrol proses Windows lewat tasklist/taskkill, tanpa PowerShell.

    ``tasklist`` hanya untuk snapshot dan verifikasi; terminasi memakai
    ``taskkill /PID <pid> /T /F`` dengan path absolut System32/Sysnative.
    Keduanya dipanggil tanpa shell dan dengan timeout terbatas.
    """

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
        """Hentikan PID yang sudah dipastikan milik automation.

        Memakai ``taskkill /PID <pid> /T /F`` agar proses anak ikut berhenti;
        path executable absolut dan tidak lewat shell. ``taskkill`` dapat
        mengembalikan exit code nonzero ketika pohon proses sudah mati; karena
        itu hasil nonzero diverifikasi ulang lewat :meth:`is_running`. Cleanup
        dianggap berhasil bila PID target sudah tidak ada, dan hanya gagal bila
        PID masih hidup atau statusnya tidak dapat diverifikasi.
        """

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
        if completed.returncode == 0:
            return True
        return self.is_running(pid) is False

    def is_running(self, pid: int) -> bool | None:
        """Status PID lewat tasklist: hidup, hilang, atau tidak dapat dipastikan.

        ``False`` hanya dikembalikan bila tasklist berhasil dijalankan dan PID
        tidak ada di hasilnya. ``None`` berarti snapshot gagal sehingga
        pemanggil tidak boleh menyimpulkan proses sudah hilang.
        """

        rows = _tasklist_rows("/FI", f"PID eq {pid}", timeout_s=self._timeout_s)
        if rows is None:
            return None
        return any(len(row) >= 2 and row[1].strip() == str(pid) for row in rows)


@dataclass
class _ProcessTracker:
    """Lacak PID Office automation dan bersihkan hanya PID yang pasti miliknya.

    ``before`` diambil sebelum COM membuat aplikasi dan tidak boleh berupa
    ``None``. PID automation dibuktikan dari window handle yang PID-nya cocok
    (Word: window ``OpusApp`` milik PID baru) atau dari tepat satu PID image
    baru setelah ``DispatchEx`` (PowerPoint); snapshot PID baru hanya dipakai
    sebagai pemeriksaan silang. Bila PID tidak dapat dipastikan secara unik,
    tracker tidak mengklaim apa pun dan cleanup tidak menghentikan proses apa
    pun.
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

    def claim_pid(self, pid: int) -> int | None:
        """Klaim PID yang sudah diverifikasi sebagai proses baru.

        Dipakai Word setelah :meth:`verify_new_process` dan pencocokan window.
        Tidak mengambil snapshot baru; image dan creation time tetap
        diverifikasi langsung agar PID yang hilang/daur ulang tidak diklaim.
        """

        claimed: tuple[int, int] | None = None
        try:
            if pid > 0 and pid not in self.before:
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
            claimed_pid = self._pid
        self._ready.set()
        return claimed_pid

    def verify_new_process(self) -> int:
        """Verifikasi tepat satu PID image baru dan kembalikan PID-nya.

        Tidak menyimpan klaim apa pun; pemanggil dapat mencocokkan window milik
        PID tersebut lebih dulu sebelum memanggil :meth:`claim`.
        """

        pid, _creation_time = self._verified_new_process()
        return pid

    def claim_new_process(self) -> int:
        """Klaim satu-satunya PID image baru setelah ``DispatchEx``.

        Dipakai PowerPoint yang tidak menyediakan window handle stabil dan
        dapat menempel ke instance pengguna. Snapshot baru harus berisi tepat
        satu PID baru dibanding ``before``; image dan creation time juga harus
        cocok. PID nol atau lebih dari satu selalu dianggap ambigu sehingga
        pemanggil tidak boleh ``Quit``/``taskkill`` instance mana pun.
        """

        try:
            pid, creation_time = self._verified_new_process()
            with self._lock:
                self._pid = pid
                self._creation_time = creation_time
            return pid
        finally:
            self._ready.set()

    def _verified_new_process(self) -> tuple[int, int]:
        after = self.list_pids()
        if after is None:
            raise ProcessSnapshotError(
                "Snapshot proses setelah DispatchEx gagal; PID automation "
                "tidak dapat dibuktikan sehingga instance tidak akan ditutup."
            )
        new_pids = set(after) - self.before
        if len(new_pids) != 1:
            raise WordOwnershipError(
                f"Diharapkan tepat satu proses {self.image} baru setelah "
                f"DispatchEx, ditemukan {len(new_pids)}. Instance Office "
                "bersama tidak aman untuk di-Quit."
            )
        pid = next(iter(new_pids))
        creation_reader = getattr(self.control, "creation_time", None)
        image = self.control.image_name(pid)
        creation_time = creation_reader(pid) if callable(creation_reader) else None
        if image is None or image.strip().upper() != self.image or creation_time is None:
            raise WordOwnershipError(
                f"PID baru {pid} tidak lolos verifikasi image/creation time "
                f"untuk {self.image}; instance tidak akan ditutup."
            )
        return pid, creation_time

    def terminate_owned(self, *, wait_s: float = 0.0) -> bool:
        """Hentikan PID Office milik automation bila masih hidup.

        ``wait_s`` dipakai watchdog untuk menunggu ``claim`` selesai sebelum
        memutuskan apakah ada PID yang perlu dihentikan. Sebelum ``taskkill``,
        nama image dan creation time dibaca ulang; PID yang sudah dipakai ulang
        proses lain tidak pernah dihentikan. Bila ``terminate`` mengembalikan
        ``False`` (misalnya ``taskkill`` nonzero padahal pohon proses sudah
        mati), status PID diverifikasi ulang dan cleanup dianggap berhasil bila
        PID terbukti sudah hilang.
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
        if not terminated and self._confirmed_gone(pid):
            terminated = True
        if terminated:
            with self._lock:
                self._terminated = True
        return terminated

    def _confirmed_gone(self, pid: int) -> bool:
        """True hanya bila control memastikan PID sudah tidak ada."""

        return query_process_running(self.control, pid) is False


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
    Bila ``on_timeout`` mengembalikan ``True``, cleanup dianggap terverifikasi
    selesai (PID target sudah hilang). Bila worker masih hidup setelah
    ``cleanup_timeout_s`` dan PID tidak terverifikasi hilang, fungsi melempar
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
        cleanup_verified = False
        try:
            cleanup_verified = on_timeout() is True
        except Exception as exc:  # noqa: BLE001 - cleanup tidak boleh menimpa timeout
            cleanup_error = exc
        wait_s = CLEANUP_TIMEOUT_S if cleanup_timeout_s is None else max(0.0, cleanup_timeout_s)
        thread.join(wait_s)
        if thread.is_alive():
            if cleanup_verified:
                raise WordTimeoutError(
                    f"{description} melewati {timeout_s:g} detik dan worker COM "
                    f"masih berjalan setelah {wait_s:g} detik cleanup, tetapi "
                    "PID target sudah terverifikasi hilang sehingga cleanup "
                    "dianggap selesai. Periksa thread/temp secara manual bila "
                    "diperlukan."
                ) from cleanup_error
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
