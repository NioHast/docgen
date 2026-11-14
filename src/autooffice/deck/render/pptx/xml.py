"""Utilitas XML, verifikasi larangan animasi, dan hash paket PPTX."""

import hashlib
import io
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import cast

from lxml import etree
from pptx.oxml.ns import qn
from pptx.presentation import Presentation

from autooffice.common.zip import (
    MAX_ZIP_CENTRAL_DIRECTORY_BYTES,
    MAX_ZIP_COMPRESSION_RATIO,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES,
    MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
    ZipEntryError,
    ZipFormatError,
    ZipLimitError,
    ZipLimits,
    ZipReader,
    check_declared_limits,
    open_zip,
)

from .shapes import PptxRenderError

_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)
_UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_REQUIRED_PARTS = ("[Content_Types].xml", "ppt/presentation.xml")
_EMBEDDED_WORKBOOK_PATTERN = re.compile(r"^ppt/embeddings/[^/]+\.xlsx$", re.IGNORECASE)
_CORE_PROPERTIES_PART = "docProps/core.xml"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_CORE_TIMESTAMP = "2000-01-01T00:00:00Z"
_ZIP_TIMESTAMP = (2000, 1, 1, 0, 0, 0)
_ZIP_COMPRESS_LEVEL = 6

# Batas keamanan untuk paket PPTX dan workbook XLSX tertanam dibagikan dengan
# package DOCX lewat ``autooffice.common.zip`` (lihat docs/dev/security.md).
ZIP_LIMIT_CODE = "PPTX-ZIP-LIMIT"
XML_UNSAFE_CODE = "PPTX-XML-UNSAFE"


def _make_parser() -> etree.XMLParser:
    """Parser XML yang tidak me-resolve entity, DTD, atau jaringan."""

    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        remove_blank_text=False,
        remove_comments=False,
        remove_pis=False,
        recover=False,
        huge_tree=False,
    )


def _parse_xml(
    data: bytes,
    *,
    part_name: str,
    invalid_label: str = "Part XML",
) -> etree._Element:
    """Parse part XML dan tolak DOCTYPE maupun entity sebelum traversal."""

    try:
        root = etree.fromstring(data, parser=_make_parser())
    except (etree.LxmlError, ValueError, TypeError) as error:
        raise PptxRenderError(f"{invalid_label} tidak valid: {part_name}.") from error
    if root is None:
        raise PptxRenderError(f"{invalid_label} tidak menghasilkan elemen root: {part_name}.")

    tree = root.getroottree()
    if tree.docinfo.doctype or tree.docinfo.internalDTD is not None:
        raise PptxRenderError(
            f"{invalid_label} memuat DOCTYPE/entity yang tidak didukung: "
            f"{part_name} ({XML_UNSAFE_CODE})."
        )
    for node in root.iter():
        if isinstance(node, etree._Entity):
            raise PptxRenderError(
                f"{invalid_label} memuat entity XML yang tidak didukung: "
                f"{part_name} ({XML_UNSAFE_CODE})."
            )
    return root


def _zip_limits() -> ZipLimits:
    """Susun batas dari konstanta modul agar test dapat menurunkannya."""

    return ZipLimits(
        max_entries=MAX_ZIP_ENTRIES,
        max_entry_bytes=MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES,
        max_total_bytes=MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
        max_ratio=MAX_ZIP_COMPRESSION_RATIO,
        max_central_directory_bytes=MAX_ZIP_CENTRAL_DIRECTORY_BYTES,
    )


def _zip_limit_error(error: ZipLimitError) -> PptxRenderError:
    return PptxRenderError(f"{error} ({ZIP_LIMIT_CODE}).")


def _check_zip_limits(archive: zipfile.ZipFile, *, source: str) -> None:
    """Tolak metadata ZIP PPTX/XLSX yang jelas melewati batas.

    Ukuran sebenarnya tetap dihitung oleh :class:`ZipReader`; metadata
    ``file_size``/``compress_size`` tidak dipercaya sebagai bukti keamanan.
    """

    try:
        check_declared_limits(archive, source=source, limits=_zip_limits())
    except ZipLimitError as error:
        raise _zip_limit_error(error) from error


def remove_animation_nodes(presentation: Presentation) -> tuple[str, ...]:
    """Hapus node ``p:timing`` dan ``p:transition`` dari slide yang dibuat."""
    removed: list[str] = []
    for index, slide in enumerate(presentation.slides, start=1):
        element = slide._element
        for tag, label in ((qn("p:timing"), "timing"), (qn("p:transition"), "transition")):
            for child in list(element):
                if child.tag == tag:
                    element.remove(child)
                    removed.append(f"slide{index}:{label}")
    return tuple(removed)


def forbidden_node_paths(pptx_path: Path) -> tuple[str, ...]:
    """Kembalikan part dan nama node terlarang yang ditemukan di ZIP."""
    findings: list[str] = []
    try:
        with open_zip(pptx_path, limits=_zip_limits()) as archive:
            _check_zip_limits(archive, source=pptx_path.name)
            reader = ZipReader(archive, source=pptx_path.name, limits=_zip_limits())
            for info in sorted(archive.infolist(), key=lambda entry: entry.filename):
                if not info.filename.endswith(".xml"):
                    continue
                root = _parse_xml(reader.read(info), part_name=info.filename)
                for tag, label in (
                    (qn("p:timing"), "p:timing"),
                    (qn("p:transition"), "p:transition"),
                ):
                    if next(root.iter(tag), None) is not None:
                        findings.append(f"{info.filename}:{label}")
    except ZipLimitError as error:
        raise _zip_limit_error(error) from error
    except (ZipFormatError, zipfile.BadZipFile) as error:
        raise PptxRenderError(f"File bukan PPTX ZIP yang valid: {pptx_path.name}.") from error
    return tuple(findings)


def assert_no_forbidden_nodes(pptx_path: Path) -> None:
    """Gagalkan render bila ada timing atau transition di paket final."""
    findings = forbidden_node_paths(pptx_path)
    if findings:
        raise PptxRenderError(
            "PPTX memuat node animasi/transisi terlarang: " + ", ".join(findings) + "."
        )


def validate_package(pptx_path: Path) -> None:
    """Pastikan ZIP PPTX dapat dibuka dan memuat part wajib."""
    try:
        with open_zip(pptx_path, limits=_zip_limits()) as archive:
            _check_zip_limits(archive, source=pptx_path.name)
            reader = ZipReader(archive, source=pptx_path.name, limits=_zip_limits())
            names: set[str] = set()
            for info in archive.infolist():
                names.add(info.filename)
                reader.drain(info)
    except ZipLimitError as error:
        raise _zip_limit_error(error) from error
    except ZipEntryError as error:
        raise PptxRenderError(f"Arsip PPTX rusak: {pptx_path.name}.") from error
    except (ZipFormatError, zipfile.BadZipFile) as error:
        raise PptxRenderError(f"File bukan PPTX ZIP yang valid: {pptx_path.name}.") from error
    missing = [name for name in _REQUIRED_PARTS if name not in names]
    if missing:
        raise PptxRenderError(f"PPTX kehilangan part wajib: {', '.join(missing)}.")


def normalize_embedded_workbooks(pptx_path: Path) -> tuple[str, ...]:
    """Set timestamps workbook tertanam ke nilai tetap dan normalkan metadata ZIP-nya.

    Chart native menyimpan XLSX di ``ppt/embeddings``. XlsxWriter menulis waktu
    pembuatan ke ``docProps/core.xml`` dan ZIP entry dapat membawa timestamp
    sendiri; keduanya membuat byte workbook berubah antar-render sehingga
    ``content_hash`` tidak deterministik. Fungsi ini idempoten: pemanggilan kedua
    tidak mengubah byte workbook lagi.
    """
    try:
        with open_zip(pptx_path, limits=_zip_limits()) as package:
            _check_zip_limits(package, source=pptx_path.name)
            workbooks = [
                info.filename
                for info in package.infolist()
                if _EMBEDDED_WORKBOOK_PATTERN.match(info.filename)
            ]
            if not workbooks:
                return ()
            reader = ZipReader(package, source=pptx_path.name, limits=_zip_limits())
            entries = [(info, reader.read(info)) for info in package.infolist()]
    except ZipLimitError as error:
        raise _zip_limit_error(error) from error
    except (ZipFormatError, zipfile.BadZipFile) as error:
        raise PptxRenderError(f"File bukan PPTX ZIP yang valid: {pptx_path.name}.") from error

    replaced: list[tuple[zipfile.ZipInfo, bytes]] = []
    changed = False
    for info, data in entries:
        if info.filename in workbooks:
            normalized = _normalize_workbook(data, part_name=info.filename)
            changed = changed or normalized != data
            data = normalized
        replaced.append((info, data))
    if changed:
        _rewrite_package(pptx_path, replaced)
    return tuple(workbooks)


def _normalize_workbook(data: bytes, *, part_name: str) -> bytes:
    """Tulis ulang workbook dengan core properties dan timestamp ZIP tetap."""
    source = f"workbook tertanam {part_name}"
    try:
        with open_zip(io.BytesIO(data), limits=_zip_limits()) as workbook:
            _check_zip_limits(workbook, source=source)
            reader = ZipReader(workbook, source=source, limits=_zip_limits())
            entries = [(info, reader.read(info)) for info in workbook.infolist()]
    except ZipLimitError as error:
        raise _zip_limit_error(error) from error
    except (ZipFormatError, zipfile.BadZipFile) as error:
        raise PptxRenderError(f"Workbook tertanam bukan XLSX valid: {part_name}.") from error

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for info, part in entries:
            if info.filename == _CORE_PROPERTIES_PART:
                part = _with_fixed_core_timestamps(part, part_name=part_name)
            clone = zipfile.ZipInfo(info.filename, date_time=_ZIP_TIMESTAMP)
            clone.compress_type = info.compress_type
            clone.external_attr = info.external_attr
            clone.internal_attr = info.internal_attr
            clone.create_system = info.create_system
            archive.writestr(
                clone,
                part,
                compress_type=info.compress_type,
                compresslevel=(
                    _ZIP_COMPRESS_LEVEL if info.compress_type == zipfile.ZIP_DEFLATED else None
                ),
            )
    return stream.getvalue()


def _with_fixed_core_timestamps(data: bytes, *, part_name: str) -> bytes:
    root = _parse_xml(
        data,
        part_name=part_name,
        invalid_label="docProps/core.xml workbook tertanam",
    )
    for local_name in ("created", "modified"):
        element = root.find(f"{{{_DCTERMS_NS}}}{local_name}")
        if element is not None:
            element.text = _CORE_TIMESTAMP
    serialized = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return cast(bytes, serialized)


def _rewrite_package(
    pptx_path: Path,
    entries: list[tuple[zipfile.ZipInfo, bytes]],
) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{pptx_path.stem}-",
        suffix=".pptx",
        dir=pptx_path.parent,
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for info, data in entries:
                archive.writestr(
                    info,
                    data,
                    compress_type=info.compress_type,
                    compresslevel=(
                        _ZIP_COMPRESS_LEVEL if info.compress_type == zipfile.ZIP_DEFLATED else None
                    ),
                )
        os.replace(temporary, pptx_path)
    finally:
        temporary.unlink(missing_ok=True)


def content_hash(pptx_path: Path) -> str:
    """Hash konten deterministik dari part ZIP yang sudah dinormalisasi."""
    digest = hashlib.sha256()
    try:
        with open_zip(pptx_path, limits=_zip_limits()) as archive:
            _check_zip_limits(archive, source=pptx_path.name)
            reader = ZipReader(archive, source=pptx_path.name, limits=_zip_limits())
            for info in sorted(archive.infolist(), key=lambda entry: entry.filename):
                name = info.filename
                digest.update(name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(_normalize_part(name, reader.read(info)))
                digest.update(b"\0")
    except ZipLimitError as error:
        raise _zip_limit_error(error) from error
    except (ZipFormatError, zipfile.BadZipFile) as error:
        raise PptxRenderError(f"File bukan PPTX ZIP yang valid: {pptx_path.name}.") from error
    return digest.hexdigest()


def _normalize_part(name: str, data: bytes) -> bytes:
    if not name.endswith((".xml", ".rels")):
        return data
    text = data.decode("utf-8", errors="replace")
    text = _TIMESTAMP_PATTERN.sub("<timestamp>", text)
    text = _UUID_PATTERN.sub("<uuid>", text)
    return text.encode("utf-8")
