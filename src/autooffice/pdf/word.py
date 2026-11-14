"""Adapter Microsoft Word COM untuk finalisasi field DOCX dan ekspor PDF.

API publik:

``export_pdf(docx, pdf, ...)``
    Salin DOCX ke snapshot sementara, buka snapshot di Word, perbarui field
    dan TOC, lalu ekspor PDF. DOCX sumber tidak pernah dibuka atau disimpan
    ulang.

``update_fields(docx, ...)``
    Salin DOCX ke snapshot, perbarui field dan TOC, verifikasi hasil, lalu
    ganti DOCX sumber secara atomik. Bila salah satu langkah gagal, DOCX
    sumber tidak berubah.

Kedua fungsi memakai watchdog, lock COM global dengan timeout turunan, dan
cleanup PID Word yang diidentifikasi dari window handle aplikasi. pywin32
diimpor lazy oleh :mod:`autooffice.pdf.com`.
"""

import contextlib
import gc
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .com import (
    WATCHDOG_CLEANUP_TIMEOUT_S,
    Deadline,
    PdfUnavailableError,
    SystemProcessControl,
    WordCleanupError,
    WordComError,
    WordProcessTracker,
    application_window_handle,
    com_apartment,
    com_lock,
    limit_process_control,
    load_com_modules,
    run_with_watchdog,
    validate_timeout,
)

_WD_DO_NOT_SAVE_CHANGES = 0
_WD_EXPORT_FORMAT_PDF = 17
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_WORK_PREFIX = "autooffice-word-"


def export_pdf(
    docx: Path,
    pdf: Path,
    *,
    timeout_s: float = 120.0,
    visible: bool = False,
) -> Path:
    """Ekspor DOCX ke PDF lewat Word tanpa mengubah DOCX sumber.

    ``timeout_s`` membatasi lock, operasi COM, dan cleanup. ``visible`` hanya
    untuk debugging dan default menyembunyikan Word. Path PDF dikembalikan
    dalam bentuk absolut setelah ditulis atomik.
    """

    validate_timeout(timeout_s)
    docx_path = _resolve_docx(docx)
    pdf_path = _resolve_pdf(pdf)
    deadline = Deadline.start(timeout_s)
    work_dir = Path(tempfile.mkdtemp(prefix=_WORK_PREFIX))
    cleanup_safe = True
    snapshot = work_dir / "source.docx"
    temp_pdf = pdf_path.with_name(f".{pdf_path.stem}-{uuid.uuid4().hex}.pdf")
    try:
        shutil.copyfile(docx_path, snapshot)
        with com_lock(timeout_s=deadline.remaining_or_raise("menunggu lock COM")):
            _run_word(
                open_path=snapshot,
                visible=visible,
                deadline=deadline,
                export_path=temp_pdf,
            )
        _check_file(temp_pdf, magic=_PDF_MAGIC, label="PDF")
        try:
            os.replace(temp_pdf, pdf_path)
        except OSError as exc:
            raise WordComError(
                f"Gagal menulis PDF tujuan: {pdf_path}. "
                "Pastikan berkas tidak sedang dibuka aplikasi lain. "
                f"Detail: {exc}"
            ) from exc
    except WordCleanupError:
        # Worker masih dapat menulis ke snapshot/temp; jangan hapus di bawahnya.
        cleanup_safe = False
        raise
    finally:
        if cleanup_safe:
            with contextlib.suppress(OSError):
                temp_pdf.unlink(missing_ok=True)
            shutil.rmtree(work_dir, ignore_errors=True)
    return pdf_path


def update_fields(
    docx: Path,
    *,
    timeout_s: float = 120.0,
    visible: bool = False,
) -> Path:
    """Perbarui field dan TOC DOCX, lalu ganti sumber secara atomik.

    Word membuka snapshot, bukan path sumber. Hasil snapshot diverifikasi dan
    baru kemudian dipindahkan ke path DOCX dengan ``os.replace``. Path DOCX
    dikembalikan dalam bentuk absolut.
    """

    validate_timeout(timeout_s)
    docx_path = _resolve_docx(docx)
    deadline = Deadline.start(timeout_s)
    work_dir = Path(tempfile.mkdtemp(prefix=_WORK_PREFIX))
    cleanup_safe = True
    snapshot = work_dir / "source.docx"
    temp_docx = docx_path.with_name(f".{docx_path.stem}-{uuid.uuid4().hex}.docx")
    try:
        shutil.copyfile(docx_path, snapshot)
        with com_lock(timeout_s=deadline.remaining_or_raise("menunggu lock COM")):
            _run_word(
                open_path=snapshot,
                visible=visible,
                deadline=deadline,
                export_path=None,
            )
        _check_file(snapshot, magic=_ZIP_MAGIC, label="DOCX")
        try:
            shutil.copyfile(snapshot, temp_docx)
        except OSError as exc:
            raise WordComError(
                f"Gagal menulis DOCX sementara di direktori tujuan: {temp_docx}. Detail: {exc}"
            ) from exc
        _check_file(temp_docx, magic=_ZIP_MAGIC, label="DOCX")
        try:
            os.replace(temp_docx, docx_path)
        except OSError as exc:
            raise WordComError(
                f"Gagal mengganti DOCX dengan hasil finalisasi field: {docx_path}. "
                "Pastikan berkas tidak sedang dibuka aplikasi lain. "
                f"Detail: {exc}"
            ) from exc
    except WordCleanupError:
        cleanup_safe = False
        raise
    finally:
        if cleanup_safe:
            with contextlib.suppress(OSError):
                temp_docx.unlink(missing_ok=True)
            shutil.rmtree(work_dir, ignore_errors=True)
    return docx_path


def _resolve_docx(docx: Path) -> Path:
    try:
        path = Path(docx).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Path DOCX tidak valid: {docx}") from exc
    if not path.exists():
        raise FileNotFoundError(f"Berkas DOCX tidak ditemukan: {path}")
    if not path.is_file():
        raise ValueError(f"Path bukan berkas DOCX: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Path bukan berkas .docx: {path}")
    return path


def _resolve_pdf(pdf: Path) -> Path:
    try:
        path = Path(pdf).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Path PDF tidak valid: {pdf}") from exc
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Path tujuan bukan berkas .pdf: {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WordComError(f"Direktori PDF tidak dapat dibuat: {path.parent}") from exc
    return path


def _terminate_tracker(tracker: WordProcessTracker, deadline: Deadline) -> None:
    """Cleanup PID dengan sisa waktu yang masih dimiliki deadline."""

    wait_s = max(0.0, min(2.0, deadline.remaining()))
    with contextlib.suppress(Exception):
        limit_process_control(tracker.control, deadline.remaining())
    with contextlib.suppress(Exception):
        tracker.terminate_owned(wait_s=wait_s)


def _run_word(
    *,
    open_path: Path,
    visible: bool,
    deadline: Deadline,
    export_path: Path | None,
) -> None:
    client, pythoncom = load_com_modules()
    control = SystemProcessControl()
    limit_process_control(control, deadline.remaining())
    tracker = WordProcessTracker.begin(control)
    deadline.check("mengambil snapshot proses Word")

    def operation() -> None:
        _execute_word_operation(
            client=client,
            pythoncom=pythoncom,
            tracker=tracker,
            open_path=open_path,
            visible=visible,
            export_path=export_path,
        )

    description = "Ekspor PDF Word" if export_path is not None else "Finalisasi field DOCX"
    remaining = deadline.remaining_or_raise("menjalankan Word")
    try:
        run_with_watchdog(
            operation,
            timeout_s=remaining,
            cleanup_timeout_s=min(WATCHDOG_CLEANUP_TIMEOUT_S, max(0.25, remaining)),
            on_timeout=lambda: _terminate_tracker(tracker, deadline),
            description=description,
        )
    finally:
        _terminate_tracker(tracker, deadline)


def _execute_word_operation(
    *,
    client: Any,
    pythoncom: Any,
    tracker: WordProcessTracker,
    open_path: Path,
    visible: bool,
    export_path: Path | None,
) -> None:
    word: Any | None = None
    doc: Any | None = None
    stage = "menyiapkan COM"
    with com_apartment(pythoncom):
        try:
            stage = "membuat aplikasi Word"
            try:
                word = client.DispatchEx("Word.Application")
            except Exception as exc:
                raise PdfUnavailableError(
                    "Microsoft Word tidak terpasang atau COM Word tidak "
                    "tersedia. Pasang Microsoft Word desktop di Windows, "
                    f"lalu ulangi. Detail: {exc}"
                ) from exc
            tracker.claim(hwnd=application_window_handle(word))
            stage = "mengatur opsi Word"
            _configure_word(word, visible)
            stage = "membuka dokumen"
            doc = word.Documents.Open(str(open_path), False, False, False)
            if bool(doc.ReadOnly):
                raise WordComError(
                    f"Dokumen terbuka dalam mode read-only: {open_path}. "
                    "Periksa atribut atau izin berkas, lalu coba lagi."
                )
            stage = "memperbarui field dan daftar isi"
            _refresh_fields(doc)
            stage = "mengekspor PDF" if export_path is not None else "menyimpan DOCX"
            _save_or_export(doc, export_path)
            stage = "menutup dokumen"
        except PdfUnavailableError, WordComError:
            raise
        except Exception as exc:
            raise WordComError(
                f"Word gagal pada tahap '{stage}' untuk '{open_path}': {exc}"
            ) from exc
        finally:
            _close_quietly(doc)
            _quit_quietly(word)
            doc = None
            word = None
            gc.collect()


def _configure_word(word: Any, visible: bool) -> None:
    with contextlib.suppress(Exception):
        word.AutomationSecurity = 3
    with contextlib.suppress(Exception):
        word.Options.UpdateLinksAtOpen = False
    with contextlib.suppress(Exception):
        word.Options.ConfirmConversions = False
    word.Visible = bool(visible)
    word.DisplayAlerts = 0
    with contextlib.suppress(Exception):
        word.ScreenUpdating = False


def _refresh_fields(doc: Any) -> None:
    doc.Repaginate()
    doc.Fields.Update()
    toc_count = int(doc.TablesOfContents.Count)
    for index in range(1, toc_count + 1):
        toc = doc.TablesOfContents.Item(index)
        try:
            toc.Update()
        finally:
            del toc
    doc.Repaginate()


def _save_or_export(doc: Any, export_path: Path | None) -> None:
    if export_path is not None:
        doc.ExportAsFixedFormat(str(export_path), _WD_EXPORT_FORMAT_PDF)
    else:
        doc.Save()


def _close_quietly(doc: Any | None) -> None:
    if doc is None:
        return
    with contextlib.suppress(Exception):
        doc.Close(_WD_DO_NOT_SAVE_CHANGES)


def _quit_quietly(word: Any | None) -> None:
    if word is None:
        return
    with contextlib.suppress(Exception):
        word.Quit()


def _check_file(path: Path, *, magic: bytes | None, label: str) -> None:
    try:
        with path.open("rb") as handle:
            header = handle.read(len(magic)) if magic is not None else b""
        size = path.stat().st_size
    except OSError as exc:
        raise WordComError(
            f"Word selesai tanpa error tetapi {label} tidak dapat dibaca: {path}. Detail: {exc}"
        ) from exc
    if size == 0 or (magic is not None and header != magic):
        raise WordComError(
            f"Word selesai tanpa error tetapi {label} tidak valid atau kosong: {path}"
        )
