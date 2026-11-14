"""Stage ``office``: finalisasi field DOCX dan ekspor PDF lewat Microsoft Word.

Modul ini memakai adapter Word COM Python :mod:`autooffice.pdf.word`; tidak ada
mesin konversi lain. Stage ``office`` memperbarui seluruh field (termasuk
TOC/PAGEREF), melakukan repaginasi, lalu menyimpan DOCX. Ekspor PDF memakai
snapshot DOCX sehingga dokumen sumber tidak berubah. Timeout, serialisasi, dan
cleanup proses Word ditangani :mod:`autooffice.pdf.com`.

API publik:

``update_fields(docx_path, ...)``
    Perbarui field DOCX di tempat memakai Word.

``export_pdf(docx_path, pdf_path, ...)``
    Ekspor DOCX final ke PDF memakai Word, dengan output atomic.

Referensi: https://learn.microsoft.com/en-us/office/vba/api/overview/word
"""

import contextlib
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from autooffice.pdf import com as pdf_com
from autooffice.pdf import word as pdf_word

from ..errors import DocgenError, ExternalToolError, PdfError, ToolMissingError, WordError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

DEFAULT_TIMEOUT = 300
"""Batas waktu Word dalam detik."""

_WORD_EXE_ENV = "DOCGEN_WINWORD"
_ZIP_MAGIC = b"PK\x03\x04"
_PDF_MAGIC = b"%PDF-"
_TRANSIENT_COM_HRESULTS = frozenset({0x80010001, -2147418111, 0x800706BE, -2147023170})
_TRANSIENT_COM_MARKERS = (
    "rpc_e_call_rejected",
    "call was rejected by callee",
    "0x80010001",
    "0x800706be",
)


# ---------------------------------------------------------------------------
# Deteksi perkakas
# ---------------------------------------------------------------------------


def is_windows() -> bool:
    """True bila Word desktop dapat dipanggil (platform Windows)."""

    return sys.platform == "win32"


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


def _com_available() -> bool:
    """True bila pywin32/COM dapat diimpor pada platform ini."""

    if not is_windows():
        return False
    try:
        pdf_com.load_com_modules()
    except Exception:  # noqa: BLE001 - probe ketersediaan tidak boleh melempar
        return False
    return True


def word_available() -> bool:
    """True bila Windows, Word desktop, dan pywin32/COM tersedia.

    Keberadaan ``WINWORD.EXE`` saja tidak cukup: Word dipanggil lewat COM,
    sehingga pywin32 yang hilang harus diperlakukan sama seperti Word yang
    tidak terpasang.
    """

    return is_windows() and find_word_executable() is not None and _com_available()


# ---------------------------------------------------------------------------
# Validasi output
# ---------------------------------------------------------------------------


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


def _is_transient_com_error(exc: BaseException) -> bool:
    """True untuk penolakan COM sementara yang aman dicoba ulang sekali."""

    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "hresult", None) in _TRANSIENT_COM_HRESULTS:
            return True
        text = f"{current} {current.args}".casefold()
        if any(marker in text for marker in _TRANSIENT_COM_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


def _call_with_com_retry[T](operation: Callable[[], T]) -> T:
    """Panggil operasi COM dan ulangi sekali bila ditolak sementara."""

    try:
        return operation()
    except Exception as exc:
        if not _is_transient_com_error(exc):
            raise
        return operation()


class WordAdapter:
    """Adapter tipis untuk :mod:`autooffice.pdf.word`.

    ``timeout`` adalah batas default bila pemanggil tidak memberi timeout.
    ``visible`` hanya dipakai untuk debugging. Adapter ini tidak menjalankan
    proses eksternal; seluruh lifecycle Word berada di
    :mod:`autooffice.pdf.com`.
    """

    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT, visible: bool = False) -> None:
        self._timeout = timeout
        self._visible = visible

    def available(self) -> bool:
        return word_available()

    def _timeout_value(self, timeout: int | None) -> float:
        return float(self._timeout if timeout is None else timeout)

    def update_fields(
        self,
        docx_path: str | Path,
        timeout: int | None = None,
    ) -> Path:
        path = _resolve_docx_input(docx_path, WordError)
        timeout_s = self._timeout_value(timeout)
        try:
            result = _call_with_com_retry(
                lambda: pdf_word.update_fields(
                    path,
                    timeout_s=timeout_s,
                    visible=self._visible,
                )
            )
        except Exception as exc:
            raise _translate_error(
                exc,
                error_type=WordError,
                path=path,
                action="memperbarui field DOCX",
                timeout_s=timeout_s,
                cleanup_code="WORD-CLEANUP",
            ) from exc
        _check_docx(result, WordError)
        return result

    def export_pdf(
        self,
        docx_path: str | Path,
        pdf_path: str | Path,
        timeout: int | None = None,
    ) -> Path:
        """Ekspor DOCX ke PDF lewat Word dan kembalikan path PDF final.

        Adapter Word menyalin DOCX ke snapshot sementara dan menulis PDF
        secara atomic, sehingga DOCX sumber tidak berubah.
        """

        docx = _resolve_docx_input(docx_path, PdfError)
        pdf = _resolve_pdf_output(pdf_path, docx, PdfError)
        try:
            pdf.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PdfError(
                f"direktori tujuan PDF tidak dapat dibuat: {exc}",
                code="PDF-OUTPUT",
                path=pdf,
            ) from exc

        timeout_s = self._timeout_value(timeout)
        try:
            result = _call_with_com_retry(
                lambda: pdf_word.export_pdf(
                    docx,
                    pdf,
                    timeout_s=timeout_s,
                    visible=self._visible,
                )
            )
        except Exception as exc:
            raise _translate_error(
                exc,
                error_type=PdfError,
                path=pdf,
                action="mengekspor PDF",
                timeout_s=timeout_s,
                cleanup_code="PDF-CLEANUP",
            ) from exc
        _check_pdf(result)
        return result


def _translate_error(
    exc: BaseException,
    *,
    error_type: type[ExternalToolError],
    path: Path,
    action: str,
    timeout_s: float,
    cleanup_code: str,
) -> DocgenError:
    """Petakan error adapter COM ke kontrak error stage yang stabil."""

    if isinstance(exc, pdf_com.PdfUnavailableError):
        return ToolMissingError("Microsoft Word", str(exc), path=path)
    if isinstance(exc, pdf_com.WordCleanupError):
        return error_type(
            f"Cleanup Word ambigu setelah {action}; proses/temp tidak boleh disentuh. {exc}",
            code=cleanup_code,
            path=path,
            cleanup_ambiguous=True,
        )
    if isinstance(exc, pdf_com.WordTimeoutError):
        return error_type(
            f"Word tidak selesai {action} dalam {timeout_s:g} detik. {exc}",
            code="WORD-TIMEOUT",
            path=path,
        )
    if isinstance(exc, pdf_com.WordBusyError):
        return error_type(
            f"Microsoft Word sedang dipakai proses lain; {exc}",
            code="WORD-BUSY",
            path=path,
        )
    if isinstance(exc, pdf_com.WordComError):
        return error_type(str(exc), code="WORD-FAILED", path=path)
    if isinstance(exc, (FileNotFoundError, ValueError)):
        return error_type(str(exc), code="WORD-INPUT", path=path)
    if isinstance(exc, OSError):
        return error_type(
            f"gagal menjalankan Word: {exc}",
            code="WORD-START",
            path=path,
        )
    return error_type(
        f"Word gagal {action}: {exc}",
        code="WORD-FAILED",
        path=path,
    )


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


def _resolve_pdf_output(
    pdf_path: str | Path,
    docx: Path,
    error_type: type[ExternalToolError],
) -> Path:
    path = Path(pdf_path).expanduser()
    with contextlib.suppress(OSError):
        path = path.resolve()
    if path.suffix.lower() != ".pdf":
        raise error_type(
            "path tujuan harus berekstensi .pdf.",
            code="PDF-INPUT",
            path=path,
        )
    if path == docx:
        raise error_type(
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
    """Pakai ``ctx.word`` bila disuntikkan pipeline, selain itu adapter baru.

    ``ctx.word`` yang diisi tetapi tidak memenuhi protokol adalah error
    konteks, bukan alasan membuat adapter Word nyata. Fallback diam-diam ke
    adapter nyata akan membuat tes/CI tanpa Word mencoba COM.
    """

    candidate = getattr(ctx, "word", None)
    if candidate is None:
        return WordAdapter()
    missing = [
        name for name in ("available", action) if not callable(getattr(candidate, name, None))
    ]
    if missing:
        names = ", ".join(repr(name) for name in missing)
        raise TypeError(
            f"ctx.word tidak memenuhi WordAdapterProtocol: method {names} tidak tersedia "
            f"pada {type(candidate).__name__}"
        )
    return cast("WordAdapterProtocol", candidate)


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
        path: Path = artifacts.require("docx")
        if path.is_file():
            return path
        raise WordError(
            "artifact DOCX tidak ditemukan di disk.",
            code="WORD-INPUT",
            path=path,
        )

    report_name = _document_report_name(ctx)
    output_dir = getattr(ctx, "output_dir", None)
    if not output_dir:
        raise WordError(
            "ctx.output_dir tidak tersedia; path DOCX tidak dapat ditentukan.",
            code="WORD-INPUT",
        )
    candidate = Path(output_dir) / f"{report_name}.docx"
    if candidate.is_file():
        return candidate
    raise WordError(
        f"DOCX final tidak ditemukan untuk stage office/pdf: {report_name}.docx",
        code="WORD-INPUT",
        path=candidate,
    )


def _pdf_path(ctx: object) -> Path:
    output_dir = getattr(ctx, "output_dir", None)
    if not output_dir:
        raise PdfError(
            "ctx.output_dir tidak tersedia; path PDF tidak dapat ditentukan.",
            code="PDF-INPUT",
        )
    report_name = _document_report_name(ctx)
    return Path(output_dir) / f"{report_name}.pdf"


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


def _can_skip_missing_word(ctx: object) -> bool:
    """True bila target masih menghasilkan DOCX saat Word tidak tersedia."""

    target = getattr(getattr(ctx, "options", None), "target", "both")
    allow = bool(getattr(getattr(ctx, "options", None), "allow_missing_word", False))
    return target == "docx" or (target == "both" and allow)


def _skip_missing_word(
    ctx: object,
    *,
    stage: StageName,
    started: float,
) -> StageResult:
    target = getattr(getattr(ctx, "options", None), "target", "both")
    return _skipped(
        stage=stage,
        started=started,
        warning=_missing_word_warning(target),
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
        """Perbarui field DOCX memakai Microsoft Word.

        Mengembalikan ``skipped`` untuk target DOCX tanpa Word bila diizinkan;
        selain itu ``ToolMissingError`` dilempar. ``WordError`` diteruskan bila
        Word gagal atau hasilnya bukan DOCX valid.
        """

        started = time.monotonic()
        adapter = _word_adapter(ctx, action="update_fields")

        if not adapter.available():
            if _can_skip_missing_word(ctx):
                return _skip_missing_word(ctx, stage=self.name, started=started)
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
        except ToolMissingError:
            if _can_skip_missing_word(ctx):
                return _skip_missing_word(ctx, stage=self.name, started=started)
            raise
        except pdf_com.PdfUnavailableError as exc:
            if _can_skip_missing_word(ctx):
                return _skip_missing_word(ctx, stage=self.name, started=started)
            raise ToolMissingError("Microsoft Word", str(exc), path=docx) from exc
        except pdf_com.WordCleanupError as exc:
            raise _translate_error(
                exc,
                error_type=WordError,
                path=docx,
                action="memperbarui field DOCX",
                timeout_s=DEFAULT_TIMEOUT,
                cleanup_code="WORD-CLEANUP",
            ) from exc
        except WordError:
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
