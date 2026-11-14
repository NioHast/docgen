"""Adapter Microsoft PowerPoint COM untuk ekspor PDF dan embedding font PPTX.

API publik:

``export_pdf(pptx, pdf, ...)``
    Salin PPTX ke snapshot sementara, buka snapshot secara read-only di
    PowerPoint, ekspor PDF dengan format ``ppSaveAsPDF``, lalu tutup
    presentasi tanpa menyimpan. PPTX sumber tidak pernah dibuka atau disimpan
    ulang.

``embed_fonts(pptx, ...)``
    Salin PPTX ke snapshot, buka snapshot di PowerPoint, simpan salinan dengan
    ``ppSaveAsOpenXMLPresentation`` dan ``EmbedTrueTypeFonts=msoTrue``, lalu
    verifikasi paket final dan ganti PPTX sumber secara atomik. Bila salah satu
    langkah gagal, PPTX sumber tidak berubah.

Kedua fungsi memakai watchdog, lock COM global dengan timeout turunan, dan
cleanup PID PowerPoint yang diidentifikasi dari window handle aplikasi.
pywin32 diimpor lazy oleh :mod:`autooffice.pdf.com`.
"""

import contextlib
import gc
import os
import posixpath
import shutil
import tempfile
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .com import (
    WATCHDOG_CLEANUP_TIMEOUT_S,
    Deadline,
    PdfUnavailableError,
    PowerPointProcessTracker,
    SystemProcessControl,
    WordCleanupError,
    WordComError,
    application_window_handle,
    com_apartment,
    com_lock,
    limit_process_control,
    load_com_modules,
    run_with_watchdog,
    validate_timeout,
)

_PP_SAVE_AS_PDF = 32
_PP_SAVE_AS_OPEN_XML_PRESENTATION = 24
_PP_ALERTS_NONE = 1
_MSO_TRUE = -1
_PDF_MAGIC = b"%PDF-"
_WORK_PREFIX = "autooffice-powerpoint-"
_FONT_WORK_PREFIX = "autooffice-powerpoint-fonts-"
_PRESENTATIONML_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_REQUIRED_FONT_FAMILY = "Plus Jakarta Sans"
_FONTDATA_CONTENT_TYPES = frozenset(
    {
        "application/x-fontdata",
        "application/vnd.openxmlformats-officedocument.obfuscatedfont",
    }
)


@dataclass(frozen=True, slots=True)
class _PackageSignature:
    """Metadata yang harus tetap ada setelah PowerPoint menyimpan ulang paket."""

    markers: frozenset[str]
    alt_texts: frozenset[str]


def export_pdf(
    pptx: Path,
    pdf: Path,
    *,
    timeout_s: float = 120.0,
    visible: bool = False,
) -> Path:
    """Ekspor PPTX ke PDF lewat PowerPoint tanpa mengubah PPTX sumber.

    ``timeout_s`` membatasi lock, operasi COM, dan cleanup. ``visible`` hanya
    untuk debugging dan default menyembunyikan PowerPoint. Path PDF
    dikembalikan dalam bentuk absolut setelah ditulis atomik.
    """

    validate_timeout(timeout_s)
    pptx_path = _resolve_pptx(pptx)
    pdf_path = _resolve_pdf(pdf)
    deadline = Deadline.start(timeout_s)
    work_dir = Path(tempfile.mkdtemp(prefix=_WORK_PREFIX))
    cleanup_safe = True
    snapshot = work_dir / "source.pptx"
    temp_pdf = pdf_path.with_name(f".{pdf_path.stem}-{uuid.uuid4().hex}.pdf")
    try:
        shutil.copyfile(pptx_path, snapshot)
        with com_lock(timeout_s=deadline.remaining_or_raise("menunggu lock COM")):
            _run_powerpoint(
                open_path=snapshot,
                visible=visible,
                deadline=deadline,
                read_only=True,
                description="Ekspor PDF PowerPoint",
                action_stage="mengekspor PDF",
                action=lambda presentation: presentation.SaveAs(str(temp_pdf), _PP_SAVE_AS_PDF),
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
        cleanup_safe = False
        raise
    finally:
        if cleanup_safe:
            with contextlib.suppress(OSError):
                temp_pdf.unlink(missing_ok=True)
            shutil.rmtree(work_dir, ignore_errors=True)
    return pdf_path


def embed_fonts(pptx: Path, *, timeout_s: float = 120.0) -> Path:
    """Tanam font TrueType ke PPTX lewat PowerPoint COM.

    PPTX dibuka dari snapshot sementara. PowerPoint menulis salinan berfont ke
    berkas sementara di direktori sumber dengan
    ``SaveCopyAs(ppSaveAsOpenXMLPresentation=24, EmbedTrueTypeFonts=msoTrue)``.
    Hasil diverifikasi sebelum PPTX sumber diganti secara atomik:

    - ada font ``Plus Jakarta Sans`` pada ``p:embeddedFontLst``;
    - ``p:regular`` dan ``p:bold`` menunjuk part ``ppt/fonts/*.fntdata`` yang
      ada dan tidak kosong;
    - tidak ada ``p:timing`` atau ``p:transition``;
    - marker key dan alt text dari sumber masih ada;
    - paket dapat dibuka python-pptx.

    Bila COM atau verifikasi gagal, PPTX sumber tidak berubah dan tidak ada
    berkas sementara yang ditinggalkan (kecuali cleanup ambigu).
    """

    validate_timeout(timeout_s)
    pptx_path = _resolve_pptx(pptx)
    deadline = Deadline.start(timeout_s)
    work_dir = Path(tempfile.mkdtemp(prefix=_FONT_WORK_PREFIX))
    cleanup_safe = True
    snapshot = work_dir / "source.pptx"
    temp_pptx = pptx_path.with_name(f".{pptx_path.stem}-{uuid.uuid4().hex}.pptx")
    try:
        shutil.copyfile(pptx_path, snapshot)
        expected = _package_signature(snapshot)
        with com_lock(timeout_s=deadline.remaining_or_raise("menunggu lock COM")):
            _run_powerpoint(
                open_path=snapshot,
                visible=False,
                deadline=deadline,
                read_only=False,
                description="Embedding font PowerPoint",
                action_stage="menanam font",
                action=lambda presentation: presentation.SaveCopyAs(
                    str(temp_pptx),
                    _PP_SAVE_AS_OPEN_XML_PRESENTATION,
                    _MSO_TRUE,
                ),
            )
        _verify_embedded_fonts(temp_pptx, expected=expected)
        try:
            os.replace(temp_pptx, pptx_path)
        except OSError as exc:
            raise WordComError(
                f"Gagal mengganti PPTX dengan hasil embedding font: {pptx_path}. "
                "Pastikan berkas tidak sedang dibuka aplikasi lain. "
                f"Detail: {exc}"
            ) from exc
    except WordCleanupError:
        cleanup_safe = False
        raise
    finally:
        if cleanup_safe:
            with contextlib.suppress(OSError):
                temp_pptx.unlink(missing_ok=True)
            shutil.rmtree(work_dir, ignore_errors=True)
    return pptx_path


def _resolve_pptx(pptx: Path) -> Path:
    try:
        path = Path(pptx).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Path PPTX tidak valid: {pptx}") from exc
    if not path.exists():
        raise FileNotFoundError(f"Berkas PPTX tidak ditemukan: {path}")
    if not path.is_file():
        raise ValueError(f"Path bukan berkas PPTX: {path}")
    if path.suffix.lower() != ".pptx":
        raise ValueError(f"Path bukan berkas .pptx: {path}")
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


def _terminate_tracker(tracker: PowerPointProcessTracker, deadline: Deadline) -> None:
    """Cleanup PID dengan sisa waktu yang masih dimiliki deadline."""

    wait_s = max(0.0, min(2.0, deadline.remaining()))
    with contextlib.suppress(Exception):
        limit_process_control(tracker.control, deadline.remaining())
    with contextlib.suppress(Exception):
        tracker.terminate_owned(wait_s=wait_s)


def _run_powerpoint(
    *,
    open_path: Path,
    visible: bool,
    deadline: Deadline,
    read_only: bool,
    description: str,
    action_stage: str,
    action: Callable[[Any], None],
) -> None:
    client, pythoncom = load_com_modules()
    control = SystemProcessControl()
    limit_process_control(control, deadline.remaining())
    tracker = PowerPointProcessTracker.begin(control)
    deadline.check("mengambil snapshot proses PowerPoint")

    def operation() -> None:
        _execute_powerpoint_operation(
            client=client,
            pythoncom=pythoncom,
            tracker=tracker,
            open_path=open_path,
            visible=visible,
            read_only=read_only,
            action_stage=action_stage,
            action=action,
        )

    remaining = deadline.remaining_or_raise("menjalankan PowerPoint")
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


def _execute_powerpoint_operation(
    *,
    client: Any,
    pythoncom: Any,
    tracker: PowerPointProcessTracker,
    open_path: Path,
    visible: bool,
    read_only: bool,
    action_stage: str,
    action: Callable[[Any], None],
) -> None:
    powerpoint: Any | None = None
    presentation: Any | None = None
    stage = "menyiapkan COM"
    with com_apartment(pythoncom):
        try:
            stage = "membuat aplikasi PowerPoint"
            try:
                powerpoint = client.DispatchEx("PowerPoint.Application")
            except Exception as exc:
                raise PdfUnavailableError(
                    "Microsoft PowerPoint tidak terpasang atau COM PowerPoint "
                    "tidak tersedia. Pasang Microsoft PowerPoint desktop di "
                    f"Windows, lalu ulangi. Detail: {exc}"
                ) from exc
            tracker.claim(hwnd=application_window_handle(powerpoint))
            stage = "mengatur opsi PowerPoint"
            _configure_powerpoint(powerpoint, visible)
            stage = "membuka presentasi"
            presentation = powerpoint.Presentations.Open(
                str(open_path),
                read_only,
                False,
                False,
            )
            stage = action_stage
            action(presentation)
            stage = "menutup presentasi"
        except PdfUnavailableError, WordComError:
            raise
        except Exception as exc:
            raise WordComError(
                f"PowerPoint gagal pada tahap '{stage}' untuk '{open_path}': {exc}"
            ) from exc
        finally:
            _close_quietly(presentation)
            _quit_quietly(powerpoint)
            presentation = None
            powerpoint = None
            gc.collect()


def _package_signature(path: Path) -> _PackageSignature:
    """Baca marker key dan alt text dari PPTX sumber sebelum COM."""

    label = f"PPTX sumber '{path.name}'"
    try:
        with zipfile.ZipFile(path) as archive:
            return _signature_from_archive(archive)
    except zipfile.BadZipFile as exc:
        raise WordComError(
            f"{label} bukan arsip PPTX valid sehingga metadata tidak dapat diverifikasi. "
            f"Detail: {exc}"
        ) from exc
    except OSError as exc:
        raise WordComError(f"{label} tidak dapat dibaca: {path}. Detail: {exc}") from exc


def _signature_from_archive(
    archive: zipfile.ZipFile,
    *,
    label: str | None = None,
) -> _PackageSignature:
    markers: set[str] = set()
    alt_texts: set[str] = set()
    for name in archive.namelist():
        if not (name.startswith("ppt/slides/") and name.endswith(".xml")):
            continue
        try:
            root = ElementTree.fromstring(archive.read(name))
        except ElementTree.ParseError as exc:
            if label is None:
                raise
            raise WordComError(
                f"PowerPoint selesai tanpa error tetapi {label} memiliki XML "
                f"tidak valid pada {name}. Detail: {exc}"
            ) from exc
        for node in root.iter():
            if _local_name(node.tag) != "cNvPr":
                continue
            shape_name = node.get("name")
            if shape_name and shape_name.startswith("autooffice:"):
                markers.add(shape_name)
            description = node.get("descr")
            if description:
                alt_texts.add(description)
    return _PackageSignature(
        markers=frozenset(markers),
        alt_texts=frozenset(alt_texts),
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_member(archive: zipfile.ZipFile, name: str, label: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak memiliki {name}."
        ) from exc


def _parse_member(data: bytes, name: str, label: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} memiliki {name} "
            f"yang tidak valid. Detail: {exc}"
        ) from exc


def _read_relationships(
    archive: zipfile.ZipFile,
    label: str = "PPTX hasil embedding font",
) -> dict[str, tuple[str, str]]:
    data = _read_member(archive, "ppt/_rels/presentation.xml.rels", label)
    root = _parse_member(data, "ppt/_rels/presentation.xml.rels", label)
    relationships: dict[str, tuple[str, str]] = {}
    for relationship in root.findall(f"{{{_PACKAGE_RELATIONSHIP_NS}}}Relationship"):
        if relationship.get("TargetMode") == "External":
            continue
        relationship_id = relationship.get("Id")
        target = relationship.get("Target")
        relationship_type = relationship.get("Type")
        if relationship_id and target and relationship_type:
            relationships[relationship_id] = (relationship_type, target)
    return relationships


def _resolve_relationship_target(target: str) -> str:
    normalized = target.replace("\\", "/")
    if normalized.startswith("/"):
        return posixpath.normpath(normalized.lstrip("/"))
    return posixpath.normpath(posixpath.join("ppt", normalized))


def _font_content_types_cover(
    archive: zipfile.ZipFile,
    font_parts: dict[str, int],
    label: str,
) -> bool:
    root = _parse_member(
        _read_member(archive, "[Content_Types].xml", label),
        "[Content_Types].xml",
        label,
    )
    default_valid = False
    overrides: dict[str, str] = {}
    for node in root:
        node_name = _local_name(node.tag)
        content_type = (node.get("ContentType") or "").strip().casefold()
        if node_name == "Default":
            extension = (node.get("Extension") or "").strip().casefold()
            if extension == "fntdata" and content_type in _FONTDATA_CONTENT_TYPES:
                default_valid = True
        elif node_name == "Override":
            part_name = (node.get("PartName") or "").lstrip("/").casefold()
            if part_name:
                overrides[part_name] = content_type
    for part_name in font_parts:
        override = overrides.get(part_name.casefold())
        if override is not None:
            if override not in _FONTDATA_CONTENT_TYPES:
                return False
        elif not default_valid:
            return False
    return True


def _verify_embedded_fonts(path: Path, *, expected: _PackageSignature) -> None:
    """Pastikan PPTX hasil PowerPoint membawa font yang benar dan utuh."""

    label = f"PPTX hasil embedding font '{path.name}'"
    try:
        with zipfile.ZipFile(path) as archive:
            font_parts = {
                name: archive.getinfo(name).file_size
                for name in archive.namelist()
                if name.startswith("ppt/fonts/") and name.lower().endswith(".fntdata")
            }
            if not font_parts:
                raise WordComError(
                    f"PowerPoint selesai tanpa error tetapi {label} tidak memuat "
                    "part font ppt/fonts/*.fntdata."
                )
            empty_parts = [name for name, size in font_parts.items() if size == 0]
            if empty_parts:
                raise WordComError(
                    f"PowerPoint selesai tanpa error tetapi {label} memuat part font "
                    f"kosong: {', '.join(empty_parts)}."
                )
            presentation_xml = _read_member(archive, "ppt/presentation.xml", label)
            presentation_root = _parse_member(
                presentation_xml,
                "ppt/presentation.xml",
                label,
            )
            relationships = _read_relationships(archive, label)
            if not _font_content_types_cover(archive, font_parts, label):
                raise WordComError(
                    f"PowerPoint selesai tanpa error tetapi {label} memiliki "
                    "[Content_Types].xml tanpa content type fntdata yang valid "
                    "(application/x-fontdata)."
                )
            _check_no_animation(archive, label)
            actual = _signature_from_archive(archive, label=label)
    except zipfile.BadZipFile as exc:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} bukan arsip PPTX valid. Detail: {exc}"
        ) from exc
    except OSError as exc:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak dapat dibaca: {path}. "
            f"Detail: {exc}"
        ) from exc

    embedded_list = presentation_root.find(f".//{{{_PRESENTATIONML_NS}}}embeddedFontLst")
    if embedded_list is None:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak memiliki "
            "p:embeddedFontLst yang berisi p:embeddedFont."
        )
    embedded_font = _embedded_font_for_family(embedded_list)
    if embedded_font is None:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak memiliki "
            f'p:font typeface="{_REQUIRED_FONT_FAMILY}" pada p:embeddedFontLst.'
        )
    _verify_regular_and_bold(
        embedded_font=embedded_font,
        font_parts=font_parts,
        relationships=relationships,
        label=label,
    )
    _verify_signature(expected, actual, label)
    _verify_open_with_python_pptx(path, label)


def _embedded_font_for_family(embedded_list: ElementTree.Element) -> ElementTree.Element | None:
    for embedded_font in embedded_list.findall(f"{{{_PRESENTATIONML_NS}}}embeddedFont"):
        font = embedded_font.find(f"{{{_PRESENTATIONML_NS}}}font")
        if font is not None and font.get("typeface") == _REQUIRED_FONT_FAMILY:
            return embedded_font
    return None


def _verify_regular_and_bold(
    *,
    embedded_font: ElementTree.Element,
    font_parts: dict[str, int],
    relationships: dict[str, tuple[str, str]],
    label: str,
) -> None:
    roles: list[tuple[str, str]] = []
    for role_name in ("regular", "bold"):
        role = embedded_font.find(f"{{{_PRESENTATIONML_NS}}}{role_name}")
        if role is None:
            raise WordComError(
                f"PowerPoint selesai tanpa error tetapi {label} tidak memiliki "
                f"p:{role_name} untuk font {_REQUIRED_FONT_FAMILY}."
            )
        relationship_id = role.get(f"{{{_RELATIONSHIP_NS}}}id")
        if not relationship_id:
            raise WordComError(
                f"PowerPoint selesai tanpa error tetapi {label} memiliki p:{role_name} tanpa r:id."
            )
        roles.append((role_name, relationship_id))

    resolved_parts: list[str] = []
    for role_name, relationship_id in roles:
        relationship = relationships.get(relationship_id)
        if relationship is None:
            raise WordComError(
                f"PowerPoint selesai tanpa error tetapi {label} memiliki p:{role_name} "
                f"yang merujuk relationship tidak ada: {relationship_id}."
            )
        relationship_type, target = relationship
        if not relationship_type.rstrip("/").casefold().endswith("/font"):
            raise WordComError(
                f"PowerPoint selesai tanpa error tetapi {label} memiliki relasi "
                f"{relationship_id} untuk p:{role_name} dengan tipe bukan font: "
                f"{relationship_type}."
            )
        part_name = _resolve_relationship_target(target)
        if part_name not in font_parts:
            raise WordComError(
                f"PowerPoint selesai tanpa error tetapi {label} memiliki p:{role_name} "
                f"yang merujuk part font tidak ada: {part_name}."
            )
        if font_parts[part_name] <= 0:
            raise WordComError(
                f"PowerPoint selesai tanpa error tetapi {label} memiliki p:{role_name} "
                f"yang merujuk part font kosong: {part_name}."
            )
        resolved_parts.append(part_name)

    if len(set(resolved_parts)) < 2:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak memiliki part "
            "fntdata terpisah untuk regular dan bold."
        )


def _check_no_animation(archive: zipfile.ZipFile, label: str) -> None:
    for name in archive.namelist():
        if not name.lower().endswith(".xml"):
            continue
        root = ElementTree.fromstring(archive.read(name))
        for node in root.iter():
            element_name = _local_name(node.tag)
            if element_name in {"timing", "transition"}:
                raise WordComError(
                    f"PowerPoint selesai tanpa error tetapi {label} memuat "
                    f"p:{element_name} pada {name}; animasi/transisi tidak boleh "
                    "ditambahkan saat embedding font."
                )


def _verify_signature(
    expected: _PackageSignature,
    actual: _PackageSignature,
    label: str,
) -> None:
    missing_markers = sorted(expected.markers - actual.markers)
    if missing_markers:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} kehilangan metadata key: "
            f"{', '.join(missing_markers)}."
        )
    missing_alt = sorted(expected.alt_texts - actual.alt_texts)
    if missing_alt:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} kehilangan alt text: "
            f"{', '.join(missing_alt)}."
        )


def _verify_open_with_python_pptx(path: Path, label: str) -> None:
    """Buka hasil dengan python-pptx agar paket yang rusak tidak lolos."""

    try:
        from pptx import Presentation

        Presentation(str(path))
    except Exception as exc:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak dapat dibuka "
            f"python-pptx. Detail: {exc}"
        ) from exc


def _configure_powerpoint(powerpoint: Any, visible: bool) -> None:
    powerpoint.DisplayAlerts = _PP_ALERTS_NONE
    if visible:
        # PowerPoint menolak ``Visible = False``; jendela presentasi sudah
        # disembunyikan oleh ``WithWindow=False`` saat Open.
        powerpoint.Visible = True


def _close_quietly(presentation: Any | None) -> None:
    if presentation is None:
        return
    with contextlib.suppress(Exception):
        presentation.Close()


def _quit_quietly(powerpoint: Any | None) -> None:
    if powerpoint is None:
        return
    with contextlib.suppress(Exception):
        powerpoint.Quit()


def _check_file(path: Path, *, magic: bytes, label: str) -> None:
    try:
        with path.open("rb") as handle:
            header = handle.read(len(magic))
        size = path.stat().st_size
    except OSError as exc:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak dapat dibaca: "
            f"{path}. Detail: {exc}"
        ) from exc
    if size == 0 or header != magic:
        raise WordComError(
            f"PowerPoint selesai tanpa error tetapi {label} tidak valid atau kosong: {path}"
        )
