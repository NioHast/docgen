"""Tes post-process caption, gambar, dan tabel DOCX."""

from __future__ import annotations

import importlib.util
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from lxml import etree

import format_figures as api

FIXTURES = Path(__file__).parent / "fixtures" / "format_figures"
BUILDER_PATH = FIXTURES / "make_fixture.py"
DOCUMENT_PART = "word/document.xml"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "format_figures_make_fixture", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_builder = _load_builder()


@pytest.fixture(scope="session")
def docs(tmp_path_factory):
    root = tmp_path_factory.mktemp("format_figures")
    return SimpleNamespace(
        main=_builder.build_main_fixture(root / "contoh.docx"),
        oversized=_builder.build_oversized_fixture(root / "gambar_besar.docx"),
        no_heading=_builder.build_no_heading_fixture(root / "tanpa_heading.docx"),
        generic=_builder.build_generic_caption_fixture(root / "caption_generic.docx"),
        field=_builder.build_field_caption_fixture(root / "caption_field.docx"),
    )


def run_tool(source: Path, tmp_path: Path, stem: str = "out") -> Path:
    output = tmp_path / f"{stem}.docx"
    assert api.main(["--docx", str(source), "--out", str(output)]) == 0
    return output


def caption_texts(path: Path, style_id: str) -> list[str]:
    document = Document(path)
    return [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.style.style_id == style_id
    ]


def document_xml(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(DOCUMENT_PART)


def xml_text(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph._p.iter(qn("w:t")))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BAB I PENDAHULUAN", 1),
        ("BAB II TINJAUAN PUSTAKA", 2),
        ("BAB IV HASIL", 4),
        ("BAB IX", 9),
        ("BAB II.", 2),
        ("BAB 12", 12),
        ("DAFTAR GAMBAR", None),
        ("BAB IVAN", None),
    ],
)
def test_nomor_bab_romawi_dan_arab(text, expected):
    assert api._chapter_number(text) == expected


# ---------------------------------------------------------------------------
# 1. Nomor caption per bab


def test_nomor_caption_per_bab_reset(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)

    assert caption_texts(output, "ImageCaption") == [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 2.1 Arsitektur sistem",
    ]
    assert caption_texts(output, "TableCaption") == [
        "Tabel 1.1 Data responden",
        "Tabel 2.1 Hasil pengujian",
    ]


# ---------------------------------------------------------------------------
# 2. Prefix lama dihapus dan idempoten


def test_prefix_lama_dihapus_dan_idempoten(docs, tmp_path):
    assert "Gambar 1. Diagram alur" in caption_texts(docs.main, "ImageCaption")
    assert "Gambar 1.2 Foto hasil" in caption_texts(docs.main, "ImageCaption")

    first = run_tool(docs.main, tmp_path, "first")
    second = run_tool(first, tmp_path, "second")

    expected_images = [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 2.1 Arsitektur sistem",
    ]
    expected_tables = [
        "Tabel 1.1 Data responden",
        "Tabel 2.1 Hasil pengujian",
    ]

    assert caption_texts(first, "ImageCaption") == expected_images
    assert caption_texts(second, "ImageCaption") == expected_images
    assert caption_texts(first, "TableCaption") == expected_tables
    assert caption_texts(second, "TableCaption") == expected_tables

    for paragraph_text in expected_images + expected_tables:
        assert not re.match(
            r"^(Gambar|Tabel)\s+\d+(?:\.\d+)?\.?\s+(Gambar|Tabel)\b",
            paragraph_text,
        )

    # Prefix tidak dobel dan seluruh XML identik pada run kedua.
    assert document_xml(first) == document_xml(second)

    document = Document(first)
    italic_caption = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text == "Gambar 1.2 Foto hasil"
    )
    assert italic_caption.runs[-1].italic is True


# ---------------------------------------------------------------------------
# 3. Gambar 20 cm di-clamp ke 14 cm, tinggi proporsional


def test_gambar_besar_di_clamp_proporsional(docs, tmp_path):
    output = run_tool(docs.oversized, tmp_path)
    document = Document(output)

    assert len(document.inline_shapes) == 2
    big, small = document.inline_shapes

    assert big.width == api.MAX_IMAGE_WIDTH_EMU
    assert big.height == 2_520_000
    assert small.width == 3_600_000
    assert small.height == 1_800_000

    transform_extents = [
        extent
        for extent in document.element.body.iter(qn("a:ext"))
        if extent.get("cx") and extent.get("cy")
    ]
    assert (int(transform_extents[0].get("cx")), int(transform_extents[0].get("cy"))) == (
        api.MAX_IMAGE_WIDTH_EMU,
        2_520_000,
    )

    image_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph._p.findall(".//" + qn("w:drawing"))
    ]
    assert len(image_paragraphs) == 2
    for paragraph in image_paragraphs:
        assert paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
        assert paragraph.paragraph_format.space_before == 0
        assert paragraph.paragraph_format.space_after == 0


# ---------------------------------------------------------------------------
# 4. Tabel: border 0,5 pt, tanpa shading, margin sel, isi/lebar tetap


def test_tabel_border_dan_tanpa_shading(docs, tmp_path):
    source = Document(docs.main)
    output = run_tool(docs.main, tmp_path)
    result = Document(output)

    assert len(source.tables) == len(result.tables) == 2

    for before, after in zip(source.tables, result.tables):
        before_pr = before._tbl.tblPr
        after_pr = after._tbl.tblPr

        # Fixture memang diberi shading di level tabel/baris/sel.
        assert before_pr.find(qn("w:shd")) is not None
        assert before_pr.find(qn("w:tblBorders")) is not None
        assert before.rows[0]._tr.trPr.find(qn("w:shd")) is not None
        assert before.cell(0, 0)._tc.tcPr.find(qn("w:shd")) is not None

        assert after_pr.find(qn("w:shd")) is None

        borders = after_pr.find(qn("w:tblBorders"))
        assert borders is not None
        assert len(borders) == 6
        for tag in (
            "w:top",
            "w:left",
            "w:bottom",
            "w:right",
            "w:insideH",
            "w:insideV",
        ):
            border = borders.find(qn(tag))
            assert border is not None
            assert border.get(qn("w:val")) == "single"
            assert border.get(qn("w:sz")) == "4"
            assert border.get(qn("w:color")) == "000000"

        cell_margins = after_pr.find(qn("w:tblCellMar"))
        assert cell_margins is not None
        expected_margins = {
            "w:top": "108",
            "w:bottom": "108",
            "w:left": "0",
            "w:right": "0",
        }
        for tag, value in expected_margins.items():
            margin = cell_margins.find(qn(tag))
            assert margin is not None
            assert margin.get(qn("w:w")) == value
            assert margin.get(qn("w:type")) == "dxa"

        for row in after._tbl.findall(qn("w:tr")):
            row_properties = row.find(qn("w:trPr"))
            if row_properties is not None:
                assert row_properties.find(qn("w:shd")) is None
            for cell in row.findall(qn("w:tc")):
                cell_properties = cell.find(qn("w:tcPr"))
                if cell_properties is None:
                    continue
                assert cell_properties.find(qn("w:shd")) is None
                assert cell_properties.find(qn("w:tcBorders")) is None
                assert cell_properties.find(qn("w:tcMar")) is None

        assert [[cell.text for cell in row.cells] for row in before.rows] == [
            [cell.text for cell in row.cells] for row in after.rows
        ]
        assert [column.width for column in before.columns] == [
            column.width for column in after.columns
        ]
        assert before.alignment == after.alignment
        assert [
            paragraph.alignment
            for row in before.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        ] == [
            paragraph.alignment
            for row in after.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        ]


# ---------------------------------------------------------------------------
# 5. Tanpa Heading1: tidak menomori, tidak crash


def test_tanpa_heading_tidak_menomori(docs, tmp_path, capsys):
    output = tmp_path / "tanpa_heading.docx"
    assert api.main(["--docx", str(docs.no_heading), "--out", str(output)]) == 0
    captured = capsys.readouterr()
    assert "Heading1" in captured.err

    assert caption_texts(output, "ImageCaption") == [
        "Gambar 4.2 Diagram tanpa bab"
    ]
    assert caption_texts(output, "TableCaption") == ["Tabel 4.1 Data tanpa bab"]
    assert caption_texts(output, "Caption") == ["Gambar 9.9 Caption generik"]

    # Gambar dan tabel tetap diproses walau penomoran dilewati.
    document = Document(output)
    assert document.tables[0]._tbl.tblPr.find(qn("w:tblBorders")) is not None


# ---------------------------------------------------------------------------
# 6. ZIP valid dan bisa dibuka python-docx


def test_zip_valid_dan_bisa_dibuka_python_docx(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)

    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert DOCUMENT_PART in names
        assert "[Content_Types].xml" in names

    root = etree.fromstring(document_xml(output))
    assert root.find(qn("w:body")) is not None

    document = Document(output)
    assert document.paragraphs


# ---------------------------------------------------------------------------
# Tambahan: keamanan dan varian caption


def test_part_selain_document_tidak_berubah(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)

    with zipfile.ZipFile(docs.main) as source, zipfile.ZipFile(output) as result:
        for name in source.namelist():
            if name == DOCUMENT_PART:
                continue
            assert result.read(name) == source.read(name)

    document = Document(output)
    assert document.sections[0].header.paragraphs[0].text == "Header fixture"
    assert document.sections[0].footer.paragraphs[0].text == "Footer fixture"


def test_bookmark_dan_field_tidak_rusak(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)
    document = Document(output)
    body = document.element.body

    bookmark_names = [
        bookmark.get(qn("w:name"))
        for bookmark in body.iter(qn("w:bookmarkStart"))
    ]
    assert "_TocGambar1" in bookmark_names

    instructions = [node.text or "" for node in body.iter(qn("w:instrText"))]
    assert any("PAGE" in instruction for instruction in instructions)

    field_types = [
        node.get(qn("w:fldCharType"))
        for node in body.iter(qn("w:fldChar"))
    ]
    assert field_types.count("begin") == field_types.count("end")


def test_caption_generic_style(docs, tmp_path):
    output = run_tool(docs.generic, tmp_path)

    assert caption_texts(output, "Caption") == [
        "Gambar 4.1 Diagram generik",
        "Tabel 4.1 Data generik",
        "Paragraf biasa, bukan caption.",
    ]

    document = Document(output)
    first_caption = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id == "Caption"
    )
    # Prefix lama dipecah ke dua run; run judul tetap italic.
    assert first_caption.runs[0].text == "Gambar 4.1 "
    assert first_caption.runs[-1].text == "Diagram generik"
    assert first_caption.runs[-1].italic is True


def test_caption_dengan_prefix_field_dilewati(docs, tmp_path, capsys):
    output = tmp_path / "caption_field.docx"
    assert api.main(["--docx", str(docs.field), "--out", str(output)]) == 0
    captured = capsys.readouterr()
    assert "prefix nomornya" in captured.err

    document = Document(output)
    captions = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id == "ImageCaption"
    ]
    assert len(captions) == 2

    # Caption pertama punya SEQ field di prefix: teks dan field dibiarkan.
    assert xml_text(captions[0]) == "Gambar 1.1 Diagram field"
    assert captions[0]._p.find(".//" + qn("w:fldSimple")) is not None

    # Caption berikutnya tetap mendapat nomor urut berikutnya.
    assert xml_text(captions[1]) == "Gambar 5.2 Diagram literal"
