"""Tes formatter blok kode DOCX (``tools/format_code.py``)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from lxml import etree

import format_code as api

DOCUMENT_PART = "word/document.xml"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}


# ---------------------------------------------------------------------------
# Fixture


def _ensure_style(document: Document, name: str, style_type):
    for style in document.styles:
        if style.name == name:
            return style
    return document.styles.add_style(name, style_type)


def build_docx(path: Path, blocks, code_style_name: str = "Source Code") -> Path:
    """Bangun DOCX kecil sesuai daftar blok.

    Blok yang didukung:

    - ``("code", ["baris 1", "baris 2"])``: paragraf berstyle kode. Teks boleh
      memuat ``\\n`` untuk line break di dalam satu paragraf.
    - ``("body", "teks")``: paragraf biasa.
    - ``("inline", "awal ", "kode", " akhir")``: paragraf biasa dengan satu run
      berstyle karakter ``Verbatim Char`` di tengahnya.
    """

    document = Document()
    code_style = _ensure_style(
        document, code_style_name, WD_STYLE_TYPE.PARAGRAPH
    )
    char_style = _ensure_style(document, "Verbatim Char", WD_STYLE_TYPE.CHARACTER)

    for block in blocks:
        kind = block[0]
        if kind == "code":
            for text in block[1]:
                paragraph = document.add_paragraph(style=code_style)
                paragraph.add_run(text)
        elif kind == "body":
            document.add_paragraph(block[1])
        elif kind == "inline":
            paragraph = document.add_paragraph(block[1])
            paragraph.add_run(block[2]).style = char_style
            paragraph.add_run(block[3])
        else:  # pragma: no cover - kesalahan fixture
            raise ValueError(f"blok tidak dikenal: {kind!r}")

    document.save(path)
    return path


def run_tool(source: Path, output: Path) -> Path:
    assert api.main(["--docx", str(source), "--out", str(output)]) == 0
    return output


def document_xml(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(DOCUMENT_PART)


def document_root(path: Path):
    return etree.fromstring(document_xml(path))


def first_table(path: Path):
    root = document_root(path)
    tables = root.findall(f".//{qn('w:tbl')}")
    assert len(tables) == 1
    return tables[0]


def cell_texts(table) -> list[str]:
    cell = table.find(f"{qn('w:tr')}/{qn('w:tc')}")
    assert cell is not None
    return [
        "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
        for paragraph in cell.findall(qn("w:p"))
    ]


@pytest.fixture()
def source_docx(tmp_path):
    return build_docx(
        tmp_path / "input.docx",
        [
            (
                "code",
                [
                    "def main():",
                    "    nilai = 42",
                    "    return nilai",
                ],
            )
        ],
    )


# ---------------------------------------------------------------------------
# 1. Tiga paragraf Source Code berurutan menjadi satu tabel 1x1


def test_tiga_paragraf_source_code_menjadi_satu_tabel(source_docx, tmp_path):
    output = run_tool(source_docx, tmp_path / "out.docx")

    document = Document(output)
    assert len(document.tables) == 1

    table = document.tables[0]
    assert len(table.rows) == 1
    assert len(table.columns) == 1

    paragraphs = table.cell(0, 0).paragraphs
    assert [paragraph.text for paragraph in paragraphs] == [
        "def main():",
        "    nilai = 42",
        "    return nilai",
    ]


# ---------------------------------------------------------------------------
# 2. Gaya ilmiah: tanpa vertikal, atas/bawah 1 pt, padding 108 twip


def test_border_dan_properti_tabel(source_docx, tmp_path):
    output = run_tool(source_docx, tmp_path / "out.docx")
    table = first_table(output)
    table_properties = table.find(qn("w:tblPr"))
    assert table_properties is not None

    width = table_properties.find(qn("w:tblW"))
    assert width is not None
    assert width.get(qn("w:w")) == "5000"
    assert width.get(qn("w:type")) == "pct"

    expected_borders = {
        "top": ("single", "8"),
        "bottom": ("single", "8"),
        "left": ("nil", None),
        "right": ("nil", None),
        "insideH": ("nil", None),
        "insideV": ("nil", None),
    }
    borders = table_properties.find(qn("w:tblBorders"))
    assert borders is not None
    assert len(borders) == len(expected_borders)
    for side, (value, size) in expected_borders.items():
        border = borders.find(qn(f"w:{side}"))
        assert border is not None, f"border {side} tidak ada"
        assert border.get(qn("w:val")) == value
        assert border.get(qn("w:sz")) == size
        assert border.get(qn("w:color")) == "000000"

    assert table.findall(f".//{qn('w:shd')}") == []
    assert table.findall(f".//{qn('w:tcBorders')}") == []

    cell_margins = table_properties.find(qn("w:tblCellMar"))
    assert cell_margins is not None
    for side in ("top", "left", "bottom", "right"):
        margin = cell_margins.find(qn(f"w:{side}"))
        assert margin is not None, f"cell margin {side} tidak ada"
        assert margin.get(qn("w:w")) == "108"
        assert margin.get(qn("w:type")) == "dxa"

    cell = table.find(f"{qn('w:tr')}/{qn('w:tc')}")
    cell_margins = cell.find(f"{qn('w:tcPr')}/{qn('w:tcMar')}")
    assert cell_margins is not None
    for side in ("top", "left", "bottom", "right"):
        margin = cell_margins.find(qn(f"w:{side}"))
        assert margin is not None
        assert margin.get(qn("w:w")) == "108"
        assert margin.get(qn("w:type")) == "dxa"

    assert table.findall(f".//{qn('w:numPr')}") == []


# ---------------------------------------------------------------------------
# 3. Font Courier New 10 pt hitam, tidak bold/italic, line spacing 1,0


def test_font_dan_spasi_paragraf_kode(source_docx, tmp_path):
    output = run_tool(source_docx, tmp_path / "out.docx")
    document = Document(output)
    paragraphs = document.tables[0].cell(0, 0).paragraphs

    for paragraph in paragraphs:
        assert paragraph.paragraph_format.line_spacing == 1.0
        assert paragraph.paragraph_format.space_before == Pt(0)
        assert paragraph.paragraph_format.space_after == Pt(0)

        for run in paragraph.runs:
            assert run.font.name == "Courier New"
            assert run.font.size == Pt(10)
            assert run.font.color.rgb == RGBColor(0, 0, 0)
            assert run.bold is False
            assert run.italic is False


# ---------------------------------------------------------------------------
# 4. Indentasi spasi dipertahankan


def test_indentasi_spasi_dipertahankan(tmp_path):
    source = build_docx(
        tmp_path / "spasi.docx",
        [
            (
                "code",
                [
                    "    if nilai:",
                    "        return nilai",
                ],
            )
        ],
    )
    output = run_tool(source, tmp_path / "out.docx")

    paragraphs = Document(output).tables[0].cell(0, 0).paragraphs
    assert [paragraph.text for paragraph in paragraphs] == [
        "    if nilai:",
        "        return nilai",
    ]

    # Setiap w:t harus membawa xml:space="preserve" agar spasi tidak dibuang.
    for paragraph in paragraphs:
        text_nodes = paragraph._p.findall(f".//{qn('w:t')}")
        assert text_nodes
        for node in text_nodes:
            assert node.get(XML_SPACE) == "preserve"


# ---------------------------------------------------------------------------
# 5. Dua blok kode terpisah menjadi dua tabel


def test_dua_blok_kode_terpisah_menjadi_dua_tabel(tmp_path):
    source = build_docx(
        tmp_path / "dua_blok.docx",
        [
            ("code", ["baris pertama"]),
            ("body", "Paragraf penjelas di antara dua blok kode."),
            ("code", ["baris kedua"]),
        ],
    )
    output = run_tool(source, tmp_path / "out.docx")

    document = Document(output)
    assert len(document.tables) == 2
    assert document.tables[0].cell(0, 0).text == "baris pertama"
    assert document.tables[1].cell(0, 0).text == "baris kedua"

    body_texts = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text
    ]
    assert "Paragraf penjelas di antara dua blok kode." in body_texts


# ---------------------------------------------------------------------------
# 6. Idempoten


def test_idempoten(source_docx, tmp_path):
    first = run_tool(source_docx, tmp_path / "first.docx")
    second = run_tool(first, tmp_path / "second.docx")

    assert len(Document(first).tables) == 1
    assert len(Document(second).tables) == 1
    assert document_xml(first) == document_xml(second)

    # --out boleh menunjuk file input yang sama.
    in_place = run_tool(first, first)
    assert len(Document(in_place).tables) == 1
    assert document_xml(in_place) == document_xml(first)


def test_tabel_kode_lama_dinormalisasi(tmp_path):
    """Tabel kode dari build lama (kotak penuh) ikut diubah ke gaya ilmiah."""

    document = Document()
    code_style = _ensure_style(document, "Source Code", WD_STYLE_TYPE.PARAGRAPH)
    table = document.add_table(rows=1, cols=1)
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.style = code_style
    paragraph.add_run("nilai = 1")

    table_properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:color"), "000000")
        borders.append(border)
    table_properties.append(borders)

    cell_margins = OxmlElement("w:tblCellMar")
    for side in ("top", "left", "bottom", "right"):
        margin = OxmlElement(f"w:{side}")
        margin.set(qn("w:w"), "28")
        margin.set(qn("w:type"), "dxa")
        cell_margins.append(margin)
    table_properties.append(cell_margins)

    source = tmp_path / "lama.docx"
    document.save(source)
    output = run_tool(source, tmp_path / "out.docx")

    table = first_table(output)
    table_properties = table.find(qn("w:tblPr"))
    borders = table_properties.find(qn("w:tblBorders"))
    assert borders is not None
    for side in ("top", "bottom"):
        assert borders.find(qn(f"w:{side}")).get(qn("w:sz")) == "8"
    for side in ("left", "right", "insideH", "insideV"):
        assert borders.find(qn(f"w:{side}")).get(qn("w:val")) == "nil"

    cell_margins = table_properties.find(qn("w:tblCellMar"))
    assert cell_margins is not None
    for side in ("top", "left", "bottom", "right"):
        assert cell_margins.find(qn(f"w:{side}")).get(qn("w:w")) == "108"


# ---------------------------------------------------------------------------
# 7. ZIP hasil tetap valid


def test_zip_hasil_valid(source_docx, tmp_path):
    output = run_tool(source_docx, tmp_path / "out.docx")

    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert DOCUMENT_PART in names
        assert "[Content_Types].xml" in names
        for name in names:
            assert archive.read(name) is not None


# ---------------------------------------------------------------------------
# Perilaku tambahan yang wajib dijaga


def test_kode_inline_tidak_diubah(tmp_path):
    source = build_docx(
        tmp_path / "inline.docx",
        [
            ("inline", "Gunakan ", "inline_code()", " di tengah paragraf biasa."),
        ],
    )
    output = run_tool(source, tmp_path / "out.docx")

    document = Document(output)
    assert document.tables == []
    paragraph = document.paragraphs[0]
    assert paragraph.text == "Gunakan inline_code() di tengah paragraf biasa."
    assert paragraph.runs[1].style.style_id == "VerbatimChar"


@pytest.mark.parametrize(
    "style_name",
    ["Verbatim Char", "HTML Code", "HTML Preformatted"],
)
def test_style_kode_alternatif_dikenali(tmp_path, style_name):
    source = build_docx(
        tmp_path / "alternatif.docx",
        [("code", ["nilai = 1"])],
        code_style_name=style_name,
    )
    output = run_tool(source, tmp_path / "out.docx")

    document = Document(output)
    assert len(document.tables) == 1
    assert document.tables[0].cell(0, 0).text == "nilai = 1"


def test_line_break_dalam_satu_paragraf_dipecah(tmp_path):
    source = build_docx(
        tmp_path / "linebreak.docx",
        [
            ("code", ["baris 1\n  baris 2\nbaris 3"]),
        ],
    )
    output = run_tool(source, tmp_path / "out.docx")

    paragraphs = Document(output).tables[0].cell(0, 0).paragraphs
    assert [paragraph.text for paragraph in paragraphs] == [
        "baris 1",
        "  baris 2",
        "baris 3",
    ]


def test_bookmark_di_dalam_blok_kode_dipertahankan(tmp_path):
    document = Document()
    code_style = _ensure_style(document, "Source Code", WD_STYLE_TYPE.PARAGRAPH)
    paragraph = document.add_paragraph(style=code_style)

    bookmark_start = OxmlElement("w:bookmarkStart")
    bookmark_start.set(qn("w:id"), "42")
    bookmark_start.set(qn("w:name"), "blok-kode-1")
    paragraph._p.append(bookmark_start)

    paragraph.add_run("x = 1")

    bookmark_end = OxmlElement("w:bookmarkEnd")
    bookmark_end.set(qn("w:id"), "42")
    paragraph._p.append(bookmark_end)

    source = tmp_path / "bookmark.docx"
    document.save(source)
    output = run_tool(source, tmp_path / "out.docx")

    root = document_root(output)
    starts = root.xpath(
        ".//w:bookmarkStart[@w:name='blok-kode-1']", namespaces=NSMAP
    )
    ends = root.xpath(".//w:bookmarkEnd[@w:id='42']", namespaces=NSMAP)
    assert len(starts) == 1
    assert len(ends) == 1
    assert starts[0].xpath("ancestor::w:tc", namespaces=NSMAP)
    assert ends[0].xpath("ancestor::w:tc", namespaces=NSMAP)


def test_paragraf_kode_dengan_field_dilewati(tmp_path):
    document = Document()
    code_style = _ensure_style(document, "Source Code", WD_STYLE_TYPE.PARAGRAPH)
    paragraph = document.add_paragraph(style=code_style)

    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "1"
    run.append(text)
    field.append(run)
    paragraph._p.append(field)

    source = tmp_path / "field.docx"
    document.save(source)
    output = run_tool(source, tmp_path / "out.docx")

    document = Document(output)
    assert document.tables == []
    assert document.paragraphs[0]._p.find(qn("w:fldSimple")) is not None
