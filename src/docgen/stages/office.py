"""Stage ``office``: finalisasi field DOCX dan ekspor PDF lewat Microsoft Word.

Modul ini adalah satu-satunya adapter Word untuk pipeline. Word desktop
dijalankan lewat ``resources/word.ps1``; tidak ada mesin konversi lain.
Stage ``office`` memperbarui seluruh field (termasuk TOC/PAGEREF), melakukan
repaginasi, lalu menyimpan DOCX. Ekspor PDF memakai dokumen yang sama dan
memeriksa hasil Word sebelum dianggap berhasil.

API publik:

``update_fields(docx_path, ...)``
    Perbarui field DOCX di tempat memakai Word.

``export_pdf(docx_path, pdf_path, ...)``
    Ekspor DOCX final ke PDF memakai Word, dengan output atomic.
"""

import contextlib
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..errors import ExternalToolError, PdfError, ToolMissingError, WordError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

DEFAULT_TIMEOUT = 300
"""Batas waktu Word dalam detik. Nilai 0 berarti tanpa batas."""

_ZIP_MAGIC = b"PK\x03\x04"
_PDF_MAGIC = b"%PDF-"
_WORD_SCRIPT_ENV = "DOCGEN_WORD_SCRIPT"
_WORD_EXE_ENV = "DOCGEN_WINWORD"
_POWERSHELL_ENV = "DOCGEN_POWERSHELL"

CommandRunner = Callable[[Sequence[str], int], "WordProcessResult | int"]


@dataclass(frozen=True)
class WordProcessResult:
    """Hasil satu pemanggilan PowerShell/Word."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


# ---------------------------------------------------------------------------
# Deteksi perkakas
# ---------------------------------------------------------------------------


def is_windows() -> bool:
    """True bila Word desktop dapat dipanggil (platform Windows)."""

    return sys.platform == "win32"


def find_powershell() -> str | None:
    """Cari PowerShell 5.1 atau PowerShell Core."""

    override = os.environ.get(_POWERSHELL_ENV)
    if override:
        return override
    for name in ("powershell", "pwsh"):
        executable = shutil.which(name)
        if executable:
            return executable
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        fallback = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if fallback.is_file():
            return str(fallback)
    return None


def _find_word_in_registry() -> str | None:
    if not is_windows():
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - hanya Windows
        return None

    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        if value and Path(value).is_file():
            return str(value)
    return None


def _find_word_in_program_files() -> str | None:
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        root = Path(base) / "Microsoft Office" / "root"
        if not root.is_dir():
            continue
        matches = sorted(root.glob("Office*/WINWORD.EXE"))
        if matches:
            return str(matches[-1])
    return None


def find_word_executable() -> str | None:
    """Cari ``WINWORD.EXE`` tanpa membuka COM."""

    override = os.environ.get(_WORD_EXE_ENV)
    if override:
        return override
    executable = shutil.which("WINWORD.EXE")
    if executable:
        return executable
    return _find_word_in_registry() or _find_word_in_program_files()


def word_script_path() -> Path | None:
    """Lokasi ``resources/word.ps1`` di repo maupun paket."""

    override = os.environ.get(_WORD_SCRIPT_ENV)
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None

    module_path = Path(__file__).resolve()
    candidates = (
        module_path.parents[3] / "resources" / "word.ps1",
        module_path.parents[1] / "resources" / "word.ps1",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def word_available() -> bool:
    """True bila platform, PowerShell, dan Word desktop tersedia."""

    return is_windows() and find_powershell() is not None and find_word_executable() is not None


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------


def build_word_command(
    powershell: str,
    script: Path,
    docx_path: Path,
    pdf_path: Path | None = None,
    *,
    visible: bool = False,
) -> list[str]:
    """Bangun command PowerShell untuk satu aksi Word.

    Tanpa ``pdf_path``, skrip memperbarui field lalu menyimpan DOCX. Dengan
    ``pdf_path``, skrip mengekspor PDF dari snapshot DOCX.
    """

    command = [
        powershell,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-DocxPath",
        str(docx_path),
    ]
    if pdf_path is not None:
        command.extend(["-PdfPath", str(pdf_path)])
    if visible:
        command.append("-Visible")
    return command


def build_update_fields_command(
    powershell: str,
    script: Path,
    docx_path: Path,
    *,
    visible: bool = False,
) -> list[str]:
    return build_word_command(
        powershell,
        script,
        docx_path,
        visible=visible,
    )


def build_export_pdf_command(
    powershell: str,
    script: Path,
    docx_path: Path,
    pdf_path: Path,
    *,
    visible: bool = False,
) -> list[str]:
    return build_word_command(
        powershell,
        script,
        docx_path,
        pdf_path,
        visible=visible,
    )


# ---------------------------------------------------------------------------
# Proses
# ---------------------------------------------------------------------------


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Hentikan PowerShell beserta proses Word yang menjadi anaknya."""

    if os.name == "nt":
        with contextlib.suppress(OSError):  # pragma: no cover - taskkill praktis selalu ada
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    else:
        process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):  # pragma: no cover - jalur darurat
        process.wait(timeout=10)


def _run_process(command: Sequence[str], timeout: int) -> WordProcessResult:
    """Jalankan PowerShell dan kembalikan stdout/stderr/returncode."""

    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout if timeout > 0 else None)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        raise
    return WordProcessResult(
        returncode=process.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
    )


def _result_detail(result: WordProcessResult) -> str:
    text = "\n".join(
        part.strip() for part in (result.stderr, result.stdout) if part and part.strip()
    )
    if not text:
        return ""
    return f" Output: {text[-2000:]}"


def _check_docx(path: Path, error_type: type[ExternalToolError]) -> None:
    try:
        with path.open("rb") as handle:
            header = handle.read(len(_ZIP_MAGIC))
    except OSError as exc:
        raise error_type(
            f"DOCX hasil Word tidak dapat dibaca: {exc}",
            code="WORD-OUTPUT",
            path=path,
        ) from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise error_type(
            "Word selesai tanpa error tetapi DOCX tidak terbentuk.",
            code="WORD-OUTPUT",
            path=path,
        )
    if header != _ZIP_MAGIC:
        raise error_type(
            "Word selesai tanpa error tetapi hasilnya bukan DOCX valid.",
            code="WORD-OUTPUT",
            path=path,
        )


def _check_pdf(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            header = handle.read(len(_PDF_MAGIC))
    except OSError as exc:
        raise PdfError(
            f"PDF hasil Word tidak dapat dibaca: {exc}",
            code="PDF-OUTPUT",
            path=path,
        ) from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise PdfError(
            "Word selesai tanpa error tetapi PDF tidak terbentuk.",
            code="PDF-OUTPUT",
            path=path,
        )
    if header != _PDF_MAGIC:
        raise PdfError(
            "Word selesai tanpa error tetapi hasilnya bukan PDF valid.",
            code="PDF-OUTPUT",
            path=path,
        )


# ---------------------------------------------------------------------------
# Adapter Word
# ---------------------------------------------------------------------------


class WordAdapter:
    """Adapter tipis untuk satu resource ``word.ps1``.

    ``runner`` dapat diganti pada tes. Signature runner adalah
    ``(command, timeout) -> WordProcessResult | int``; tidak ada pemanggilan
    Word nyata di tes.
    """

    def __init__(
        self,
        *,
        powershell: str | None = None,
        script: Path | None = None,
        word_executable: str | None = None,
        runner: CommandRunner | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        visible: bool = False,
    ) -> None:
        self._powershell = powershell
        self._script = Path(script) if script is not None else None
        self._word_executable = word_executable
        self._runner = runner
        self._timeout = timeout
        self._visible = visible

    # -- deteksi --------------------------------------------------------

    def _powershell_exe(self) -> str | None:
        return self._powershell or find_powershell()

    def _word_exe(self) -> str | None:
        return self._word_executable or find_word_executable()

    def _script_path(self) -> Path | None:
        return self._script or word_script_path()

    def available(self) -> bool:
        return is_windows() and self._powershell_exe() is not None and self._word_exe() is not None

    def _resolve(
        self,
        error_type: type[ExternalToolError],
        *,
        path: Path,
    ) -> tuple[str, Path]:
        if not is_windows():
            raise ToolMissingError(
                "Microsoft Word",
                "Microsoft Word hanya tersedia di Windows; gunakan --target docx di platform ini.",
                path=path,
            )
        powershell = self._powershell_exe()
        if powershell is None:
            raise ToolMissingError(
                "Microsoft Word",
                "PowerShell tidak ditemukan; Word tidak dapat dijalankan.",
                path=path,
            )
        if self._word_exe() is None:
            raise ToolMissingError(
                "Microsoft Word",
                "Microsoft Word desktop tidak ditemukan; pasang Word atau gunakan --target docx.",
                path=path,
            )
        script = self._script_path()
        if script is None or not script.is_file():
            raise error_type(
                "Resource word.ps1 tidak ditemukan; instalasi docgen tidak lengkap.",
                code="WORD-RESOURCE",
                path=path,
            )
        return powershell, script

    # -- eksekusi -------------------------------------------------------

    def _execute(
        self,
        command: Sequence[str],
        *,
        timeout: int | None,
        error_type: type[ExternalToolError],
        path: Path,
        action: str,
    ) -> WordProcessResult:
        effective_timeout = self._timeout if timeout is None else timeout
        runner = self._runner or _run_process
        try:
            raw = runner(command, effective_timeout)
        except subprocess.TimeoutExpired as exc:
            raise error_type(
                f"Word tidak selesai {action} dalam {effective_timeout} detik.",
                code="WORD-TIMEOUT",
                path=path,
            ) from exc
        except OSError as exc:
            raise error_type(
                f"gagal menjalankan PowerShell/Word: {exc}",
                code="WORD-START",
                path=path,
            ) from exc

        result = raw if isinstance(raw, WordProcessResult) else WordProcessResult(raw)
        if result.returncode != 0:
            raise error_type(
                f"Microsoft Word gagal {action} (kode {result.returncode})."
                f"{_result_detail(result)}",
                code="WORD-FAILED",
                path=path,
            )
        return result

    # -- API ------------------------------------------------------------

    def update_fields(
        self,
        docx_path: str | Path,
        timeout: int | None = None,
    ) -> Path:
        path = _resolve_docx_input(docx_path, WordError)
        powershell, script = self._resolve(WordError, path=path)
        command = build_update_fields_command(
            powershell,
            script,
            path,
            visible=self._visible,
        )
        self._execute(
            command,
            timeout=timeout,
            error_type=WordError,
            path=path,
            action="memperbarui field DOCX",
        )
        _check_docx(path, WordError)
        return path

    def export_pdf(
        self,
        docx_path: str | Path,
        pdf_path: str | Path,
        timeout: int | None = None,
    ) -> Path:
        docx = _resolve_docx_input(docx_path, PdfError)
        pdf = _resolve_pdf_output(pdf_path, docx)
        powershell, script = self._resolve(PdfError, path=docx)
        try:
            pdf.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PdfError(
                f"direktori tujuan PDF tidak dapat dibuat: {exc}",
                code="PDF-OUTPUT",
                path=pdf,
            ) from exc

        temporary = pdf.parent / f".{pdf.stem}.{uuid.uuid4().hex}.pdf"
        try:
            command = build_export_pdf_command(
                powershell,
                script,
                docx,
                temporary,
                visible=self._visible,
            )
            self._execute(
                command,
                timeout=timeout,
                error_type=PdfError,
                path=pdf,
                action="mengekspor PDF",
            )
            _check_pdf(temporary)
            try:
                os.replace(temporary, pdf)
            except OSError as exc:
                raise PdfError(
                    f"gagal memindahkan PDF hasil Word ke tujuan: {exc}",
                    code="PDF-OUTPUT",
                    path=pdf,
                ) from exc
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:  # pragma: no cover - pembersihan best-effort
                pass
        return pdf


# ---------------------------------------------------------------------------
# Validasi path
# ---------------------------------------------------------------------------


def _resolve_docx_input(
    docx_path: str | Path,
    error_type: type[ExternalToolError],
) -> Path:
    path = Path(docx_path).expanduser()
    with contextlib.suppress(OSError):
        path = path.resolve()
    if not path.is_file():
        raise error_type(
            "berkas DOCX tidak ditemukan.",
            code="WORD-INPUT",
            path=path,
        )
    if path.suffix.lower() != ".docx":
        raise error_type(
            "berkas sumber harus berekstensi .docx.",
            code="WORD-INPUT",
            path=path,
        )
    return path


def _resolve_pdf_output(pdf_path: str | Path, docx: Path) -> Path:
    path = Path(pdf_path).expanduser()
    with contextlib.suppress(OSError):
        path = path.resolve()
    if path.suffix.lower() != ".pdf":
        raise PdfError(
            "path tujuan harus berekstensi .pdf.",
            code="PDF-INPUT",
            path=path,
        )
    if path == docx:
        raise PdfError(
            "path DOCX dan PDF tidak boleh sama.",
            code="PDF-INPUT",
            path=path,
        )
    return path


# ---------------------------------------------------------------------------
# API modul
# ---------------------------------------------------------------------------


def update_fields(
    docx_path: str | Path,
    timeout: int = DEFAULT_TIMEOUT,
    *,
    adapter: WordAdapter | None = None,
) -> Path:
    """Perbarui field DOCX memakai Word; error bila Word gagal."""

    word = adapter or WordAdapter()
    return word.update_fields(docx_path, timeout=timeout)


def export_pdf(
    docx_path: str | Path,
    pdf_path: str | Path,
    timeout: int = DEFAULT_TIMEOUT,
    *,
    adapter: WordAdapter | None = None,
) -> Path:
    """Ekspor DOCX final ke PDF memakai Word; error bila Word gagal."""

    word = adapter or WordAdapter()
    return word.export_pdf(docx_path, pdf_path, timeout=timeout)


# ---------------------------------------------------------------------------
# Helper stage
# ---------------------------------------------------------------------------


class WordAdapterProtocol(Protocol):
    """Kontrak adapter Word yang dapat disuntikkan lewat ``ctx.word``."""

    def available(self) -> bool: ...

    def update_fields(
        self,
        docx_path: str | Path,
        *,
        timeout: int | None = None,
    ) -> Path: ...

    def export_pdf(
        self,
        docx_path: str | Path,
        pdf_path: str | Path,
        *,
        timeout: int | None = None,
    ) -> Path: ...


def _word_adapter(ctx: object, *, action: str) -> WordAdapterProtocol:
    """Pakai ``ctx.word`` bila disuntikkan pipeline, selain itu adapter baru."""

    candidate = getattr(ctx, "word", None)
    if (
        candidate is not None
        and callable(getattr(candidate, "available", None))
        and callable(getattr(candidate, action, None))
    ):
        return candidate
    return WordAdapter()


def _document_report_name(ctx: object) -> str:
    metadata = getattr(getattr(ctx, "document", None), "metadata", None)
    if metadata is None:
        raise WordError(
            "metadata dokumen tidak tersedia; stage office/pdf membutuhkan report_name.",
            code="WORD-INPUT",
        )
    return str(metadata.report_name)


def _docx_path(ctx: object) -> Path:
    artifacts = getattr(ctx, "artifacts", None)
    if artifacts is not None and "docx" in artifacts.keys():  # noqa: SIM118 - Artifacts bukan Mapping
        path = artifacts.require("docx")
        if path.is_file():
            return path
        raise WordError(
            "artifact DOCX tidak ditemukan di disk.",
            code="WORD-INPUT",
            path=path,
        )

    report_name = _document_report_name(ctx)
    candidates = [
        getattr(ctx, "output_dir", Path.cwd()) / f"{report_name}.docx",
    ]
    workspace = getattr(ctx, "workspace", None)
    if workspace is not None and callable(getattr(workspace, "path", None)):
        candidates.append(workspace.path(f"{report_name}.docx"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise WordError(
        f"DOCX final tidak ditemukan untuk stage office/pdf: {report_name}.docx",
        code="WORD-INPUT",
        path=candidates[0],
    )


def _pdf_path(ctx: object) -> Path:
    report_name = _document_report_name(ctx)
    output_dir = getattr(ctx, "output_dir", Path.cwd())
    return output_dir / f"{report_name}.pdf"


def _skipped(
    *,
    stage: StageName,
    started: float,
    warning: str,
) -> StageResult:
    return StageResult(
        stage=stage.value,
        status="skipped",
        changed=False,
        duration_ms=int((time.monotonic() - started) * 1000),
        warnings=(warning,),
    )


def _missing_word_warning(target: str) -> str:
    if target == "docx":
        return (
            "Microsoft Word tidak tersedia; field DOCX tidak diperbarui dan "
            "TOC memakai cache terakhir. DOCX tetap dihasilkan."
        )
    return (
        "Microsoft Word tidak tersedia; PDF dilewati dan DOCX tetap "
        "dihasilkan (--allow-missing-word)."
    )


class OfficeStage(BaseStage):
    """Finalisasi field/TOC DOCX memakai Microsoft Word."""

    name = StageName.OFFICE
    order = 160
    requires = canonical_prefix(StageName.OFFICE)
    mutates = frozenset({"package"})
    idempotent = False

    def enabled(self, ctx: object) -> bool:
        return not getattr(ctx, "dry_run", False)

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        adapter = _word_adapter(ctx, action="update_fields")

        if not adapter.available():
            target = getattr(getattr(ctx, "options", None), "target", "both")
            allow = bool(getattr(getattr(ctx, "options", None), "allow_missing_word", False))
            if target == "docx" or (target == "both" and allow):
                return _skipped(
                    stage=self.name,
                    started=started,
                    warning=_missing_word_warning(target),
                )
            try:
                docx = _docx_path(ctx)
            except WordError:
                docx = None
            raise ToolMissingError(
                "Microsoft Word",
                "Microsoft Word tidak tersedia; target PDF tidak dapat "
                "dihasilkan. Pasang Word desktop atau gunakan --target docx.",
                path=docx,
            )

        docx = _docx_path(ctx)
        try:
            result = adapter.update_fields(docx)
        except WordError, ToolMissingError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise WordError(
                f"stage office gagal: {exc}",
                code="WORD-STAGE",
                path=docx,
            ) from exc

        _check_docx(result, WordError)
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=True,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={"docx_bytes": result.stat().st_size},
            artifacts=(result,),
        )
