"""Tes cabang edge XML: part rusak, ZIP rusak, dan normalisasi workbook."""

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from autooffice.deck.render.pptx.shapes import PptxRenderError
from autooffice.deck.render.pptx.xml import (
    forbidden_node_paths,
    normalize_embedded_workbooks,
    validate_package,
)

_CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_CORE_TIMESTAMP = "2000-01-01T00:00:00Z"


def _write_pptx(path: Path, workbook: bytes | None = None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        if workbook is not None:
            archive.writestr("ppt/embeddings/book1.xlsx", workbook)


def _workbook(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_forbidden_node_paths_wraps_invalid_xml_part(tmp_path: Path) -> None:
    path = tmp_path / "broken-part.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", b"<p:sld")

    with pytest.raises(PptxRenderError, match="Part XML tidak valid"):
        forbidden_node_paths(path)


def test_validate_package_wraps_bad_zip(tmp_path: Path) -> None:
    path = tmp_path / "bukan-zip.pptx"
    path.write_bytes(b"bukan arsip")

    with pytest.raises(PptxRenderError, match="bukan PPTX ZIP yang valid"):
        validate_package(path)


def test_validate_package_rejects_corrupt_zip_entry(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", b"A" * 128)
        archive.writestr("ppt/presentation.xml", b"B" * 128)
    data = bytearray(buffer.getvalue())
    offset = data.find(b"A" * 32)
    data[offset] = ord("Z")
    path = tmp_path / "korup.pptx"
    path.write_bytes(bytes(data))

    with pytest.raises(PptxRenderError, match="Arsip PPTX rusak"):
        validate_package(path)


def test_normalize_embedded_workbooks_wraps_bad_zip(tmp_path: Path) -> None:
    path = tmp_path / "bukan-zip.pptx"
    path.write_bytes(b"bukan arsip")

    with pytest.raises(PptxRenderError, match="bukan PPTX ZIP yang valid"):
        normalize_embedded_workbooks(path)


def test_normalize_embedded_workbooks_rejects_invalid_workbook(tmp_path: Path) -> None:
    path = tmp_path / "workbook-rusak.pptx"
    _write_pptx(path, b"bukan xlsx")

    with pytest.raises(PptxRenderError, match="Workbook tertanam bukan XLSX valid"):
        normalize_embedded_workbooks(path)


def test_normalize_embedded_workbooks_rejects_invalid_core_xml(tmp_path: Path) -> None:
    path = tmp_path / "core-rusak.pptx"
    _write_pptx(path, _workbook({"docProps/core.xml": b"<bukan xml"}))

    with pytest.raises(PptxRenderError, match=r"core.xml workbook tertanam tidak valid"):
        normalize_embedded_workbooks(path)


def test_normalize_embedded_workbooks_fixes_existing_timestamps_and_skips_missing(
    tmp_path: Path,
) -> None:
    core = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<cp:coreProperties xmlns:cp="{_CORE_NS}" xmlns:dcterms="{_DCTERMS_NS}">'
        "<dcterms:created>2020-01-01T00:00:00Z</dcterms:created>"
        "</cp:coreProperties>"
    )
    path = tmp_path / "core-normalisasi.pptx"
    _write_pptx(
        path,
        _workbook(
            {
                "docProps/core.xml": core.encode(),
                "xl/workbook.xml": b"<workbook/>",
            }
        ),
    )

    assert normalize_embedded_workbooks(path) == ("ppt/embeddings/book1.xlsx",)
    first = path.read_bytes()
    assert normalize_embedded_workbooks(path) == ("ppt/embeddings/book1.xlsx",)
    assert path.read_bytes() == first

    with zipfile.ZipFile(path) as package:
        workbook = package.read("ppt/embeddings/book1.xlsx")
    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        root = etree.fromstring(archive.read("docProps/core.xml"))

    created = root.find(f"{{{_DCTERMS_NS}}}created")
    assert created is not None
    assert created.text == _CORE_TIMESTAMP
    assert root.find(f"{{{_DCTERMS_NS}}}modified") is None
