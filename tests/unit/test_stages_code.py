"""Tes unit stage ``code``: blok kode, tabel 1x1, dan idempotensi."""

import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from lxml import etree

from docgen.docx.package import DOCUMENT_PART, DocumentPackage
from docgen.docx.tables import (
    CODE_TABLE_BORDERS,
    TableSpec,
    is_code_table,
    iter_tables,
)
from docgen.docx.xml import sha256_c14n
from docgen.stages.captions import apply_captions
from docgen.stages.code import CodeStage, apply_code

# ---------------------------------------------------------------------------
# Fixture DOCX
# ---------------------------------------------------------------------------


def ensure_style(document: Document, name: str, style_type):
    for style in document.styles:
        if style.name == name or style.style_id == name:
            return style
    return document.styles.add_style(name, style_type)


def build_docx(
    path: Path,
    blocks,
    *,
    code_style_name: str = "Source Code",
) -> Path:
    """Bangun DOCX kecil dari daftar blok ``code``/``body``/``inline``."""

    document = Document()
    code_style = ensure_style(document, code_style_name, WD_STYLE_TYPE.PARAGRAPH)
    char_style = ensure_style(document, "Verbatim Char", WD_STYLE_TYPE.CHARACTER)

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


def first_table(root) -> etree._Element:
    tables = root.findall(f".//{qn('w:tbl')}")
    assert len(tables) == 1
    return tables[0]


def cell_texts(table: etree._Element) -> list[str]:
    cell = table.find(f"{qn('w:tr')}/{qn('w:tc')}")
    assert cell is not None
    return [
        "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
        for paragraph in cell.findall(qn("w:p"))
    ]


def border_values(table: etree._Element) -> dict[str, tuple[str | None, str | None]]:
    table_properties = table.find(qn("w:tblPr"))
    assert table_properties is not None
    borders = table_properties.find(qn("w:tblBorders"))
    assert borders is not None
    return {
        border.tag.rsplit("}", 1)[-1]: (
            border.get(qn("w:val")),
            border.get(qn("w:sz")),
        )
        for border in borders
    }


def cell_margins(table: etree._Element) -> dict[str, str | None]:
    table_properties = table.find(qn("w:tblPr"))
    assert table_properties is not None
    margins = table_properties.find(qn("w:tblCellMar"))
    assert margins is not None
    return {margin.tag.rsplit("}", 1)[-1]: margin.get(qn("w:w")) for margin in margins}


@pytest.fixture()
def source_docx(tmp_path: Path) -> Path:
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
# 1. Blok kode menjadi tabel 1x1
# ---------------------------------------------------------------------------


def test_tiga_paragraf_source_code_menjadi_satu_tabel(source_docx, tmp_path):
    package = DocumentPackage.load(source_docx)
    report = apply_code(package)
    output = tmp_path / "out.docx"
    package.save(output)

    document = Document(output)
    assert len(document.tables) == 1

    table = document.tables[0]
    assert len(table.rows) == 1
    assert len(table.columns) == 1
    assert [paragraph.text for paragraph in table.cell(0, 0).paragraphs] == [
        "def main():",
        "    nilai = 42",
        "    return nilai",
    ]
    assert report.tables == 1
    assert report.paragraphs == 3
    assert report.lines == 3
    assert report.normalized_tables == 0
    assert report.changed is True


def test_border_dan_margin_tabel_kode(source_docx, tmp_path):
    package = DocumentPackage.load(source_docx)
    apply_code(package)
    output = tmp_path / "out.docx"
    package.save(output)

    table = first_table(package.xml(DOCUMENT_PART))
    table_properties = table.find(qn("w:tblPr"))
    assert table_properties is not None

    width = table_properties.find(qn("w:tblW"))
    assert width is not None
    assert width.get(qn("w:w")) == "5000"
    assert width.get(qn("w:type")) == "pct"

    expected = {
        "top": ("single", "8"),
        "left": ("single", "8"),
        "bottom": ("single", "8"),
        "right": ("single", "8"),
        "insideH": ("nil", None),
        "insideV": ("nil", None),
    }
    assert border_values(table) == expected
    assert code_table_border_constant_matches() is True

    assert cell_margins(table) == {
        "top": "108",
        "left": "108",
        "bottom": "108",
        "right": "108",
    }

    cell = table.find(f"{qn('w:tr')}/{qn('w:tc')}")
    assert cell is not None
    cell_margins_element = cell.find(f"{qn('w:tcPr')}/{qn('w:tcMar')}")
    assert cell_margins_element is not None
    assert {
        margin.tag.rsplit("}", 1)[-1]: margin.get(qn("w:w")) for margin in cell_margins_element
    } == {"top": "108", "left": "108", "bottom": "108", "right": "108"}

    assert table.findall(f".//{qn('w:shd')}") == []
    assert table.findall(f".//{qn('w:tcBorders')}") == []
    assert table.findall(f".//{qn('w:numPr')}") == []


def code_table_border_constant_matches() -> bool:
    return tuple(CODE_TABLE_BORDERS) == (
        ("w:top", "single", 8),
        ("w:left", "single", 8),
        ("w:bottom", "single", 8),
        ("w:right", "single", 8),
        ("w:insideH", "nil", None),
        ("w:insideV", "nil", None),
    )


def test_font_dan_spasi_paragraf_kode(source_docx, tmp_path):
    package = DocumentPackage.load(source_docx)
    apply_code(package)
    output = tmp_path / "out.docx"
    package.save(output)

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


def test_indentasi_spasi_dipertahankan(tmp_path):
    source = build_docx(
        tmp_path / "spasi.docx",
        [("code", ["    if nilai:", "        return nilai"])],
    )
    package = DocumentPackage.load(source)
    apply_code(package)

    paragraphs = first_table(package.xml(DOCUMENT_PART)).findall(
        f"{qn('w:tr')}/{qn('w:tc')}/{qn('w:p')}"
    )
    assert [
        "".join(node.text or "" for node in paragraph.iter(qn("w:t"))) for paragraph in paragraphs
    ] == ["    if nilai:", "        return nilai"]

    for paragraph in paragraphs:
        text_nodes = paragraph.findall(f".//{qn('w:t')}")
        assert text_nodes
        for node in text_nodes:
            assert node.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve"


def test_dua_blok_kode_terpisah_menjadi_dua_tabel(tmp_path):
    source = build_docx(
        tmp_path / "dua_blok.docx",
        [
            ("code", ["baris pertama"]),
            ("body", "Paragraf penjelas di antara dua blok kode."),
            ("code", ["baris kedua"]),
        ],
    )
    package = DocumentPackage.load(source)
    report = apply_code(package)

    assert report.tables == 2
    output = tmp_path / "out.docx"
    package.save(output)
    document = Document(output)
    assert len(document.tables) == 2
    assert document.tables[0].cell(0, 0).text == "baris pertama"
    assert document.tables[1].cell(0, 0).text == "baris kedua"


# ---------------------------------------------------------------------------
# 2. Idempotensi dan normalized_tables
# ---------------------------------------------------------------------------


def test_idempoten_dan_normalized_tables_nol(source_docx, tmp_path):
    package = DocumentPackage.load(source_docx)
    first = apply_code(package)
    first_path = tmp_path / "first.docx"
    package.save(first_path)

    assert first.tables == 1
    assert first.normalized_tables == 0

    second_package = DocumentPackage.load(first_path)
    second = apply_code(second_package)
    second_path = tmp_path / "second.docx"
    second_package.save(second_path)

    assert second.tables == 0
    assert second.normalized_tables == 0
    assert second.changed is False
    assert sha256_c14n(DocumentPackage.load(first_path).part(DOCUMENT_PART)) == sha256_c14n(
        DocumentPackage.load(second_path).part(DOCUMENT_PART)
    )


def test_tabel_kode_lama_dinormalisasi(tmp_path):
    document = Document()
    code_style = ensure_style(document, "Source Code", WD_STYLE_TYPE.PARAGRAPH)
    table = document.add_table(rows=1, cols=1)
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.style = code_style
    paragraph.add_run("nilai = 1")

    table_properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "nil" if side in ("left", "right") else "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:color"), "000000")
        borders.append(border)
    table_properties.append(borders)

    margins = OxmlElement("w:tblCellMar")
    for side in ("top", "left", "bottom", "right"):
        margin = OxmlElement(f"w:{side}")
        margin.set(qn("w:w"), "28")
        margin.set(qn("w:type"), "dxa")
        margins.append(margin)
    table_properties.append(margins)

    source = tmp_path / "lama.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    report = apply_code(package)

    assert report.tables == 0
    assert report.normalized_tables == 1

    table = first_table(package.xml(DOCUMENT_PART))
    assert border_values(table)["top"] == ("single", "8")
    assert border_values(table)["left"] == ("single", "8")
    assert cell_margins(table) == {
        "top": "108",
        "left": "108",
        "bottom": "108",
        "right": "108",
    }

    # Simpan hasil normalisasi agar run kedua membaca tabel yang sama.
    normalized_path = tmp_path / "normalized.docx"
    package.save(normalized_path)
    second = apply_code(DocumentPackage.load(normalized_path))
    assert second.normalized_tables == 0


# ---------------------------------------------------------------------------
# 3. Deteksi style dan keamanan
# ---------------------------------------------------------------------------


def test_kode_inline_tidak_diubah(tmp_path):
    source = build_docx(
        tmp_path / "inline.docx",
        [("inline", "Gunakan ", "inline_code()", " di tengah paragraf biasa.")],
    )
    package = DocumentPackage.load(source)
    report = apply_code(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.tables == 0
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
    package = DocumentPackage.load(source)
    apply_code(package)
    output = tmp_path / "out.docx"
    package.save(output)

    document = Document(output)
    assert len(document.tables) == 1
    assert document.tables[0].cell(0, 0).text == "nilai = 1"


def test_line_break_dalam_satu_paragraf_dipecah(tmp_path):
    source = build_docx(
        tmp_path / "linebreak.docx",
        [("code", ["baris 1\n  baris 2\nbaris 3"])],
    )
    package = DocumentPackage.load(source)
    apply_code(package)
    output = tmp_path / "out.docx"
    package.save(output)

    paragraphs = Document(output).tables[0].cell(0, 0).paragraphs
    assert [paragraph.text for paragraph in paragraphs] == [
        "baris 1",
        "  baris 2",
        "baris 3",
    ]


def test_bookmark_di_dalam_blok_kode_dipertahankan(tmp_path):
    document = Document()
    code_style = ensure_style(document, "Source Code", WD_STYLE_TYPE.PARAGRAPH)
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
    package = DocumentPackage.load(source)
    apply_code(package)
    root = package.xml(DOCUMENT_PART)

    starts = root.xpath(
        ".//w:bookmarkStart[@w:name='blok-kode-1']",
        namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
    )
    ends = root.xpath(
        ".//w:bookmarkEnd[@w:id='42']",
        namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
    )
    assert len(starts) == 1
    assert len(ends) == 1
    assert starts[0].xpath(
        "ancestor::w:tc",
        namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
    )


def test_paragraf_kode_dengan_field_dilewati(tmp_path):
    document = Document()
    code_style = ensure_style(document, "Source Code", WD_STYLE_TYPE.PARAGRAPH)
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
    package = DocumentPackage.load(source)
    report = apply_code(package)

    assert report.tables == 0
    assert report.skipped == 1
    root = package.xml(DOCUMENT_PART)
    assert root.find(f".//{qn('w:tbl')}") is None
    assert root.find(f".//{qn('w:fldSimple')}") is not None


# ---------------------------------------------------------------------------
# 4. Tabel kode bukan tabel data
# ---------------------------------------------------------------------------


def test_code_table_tidak_diberi_caption_tabel(tmp_path):
    source = build_docx(
        tmp_path / "code.docx",
        [("code", ["nilai = 1"])],
    )
    package = DocumentPackage.load(source)
    code_report = apply_code(package)
    caption_report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert code_report.tables == 1
    assert caption_report.table_captions == 0
    assert caption_report.created_table_captions == 0
    assert caption_report.missing_captions == []

    document = Document(output)
    assert len(document.tables) == 1
    table = document.tables[0]
    assert len(table.rows) == 1
    assert len(table.columns) == 1
    assert not [
        paragraph for paragraph in document.paragraphs if paragraph.style.style_id == "TableCaption"
    ]

    table_info = iter_tables(package)[0]
    assert table_info.is_code is True
    assert table_info.has_caption is False
    assert is_code_table(table._tbl) is True

    xml_table = first_table(package.xml(DOCUMENT_PART))
    assert border_values(xml_table)["top"] == ("single", "8")
    assert border_values(xml_table)["left"] == ("single", "8")


def test_tabel_data_tidak_dianggap_tabel_kode(tmp_path):
    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "2"
    source = tmp_path / "data.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    info = iter_tables(package)[0]
    assert info.is_code is False


# ---------------------------------------------------------------------------
# 5. Part non-target byte-identik dan metadata stage
# ---------------------------------------------------------------------------


def test_part_non_target_byte_identik(source_docx, tmp_path):
    package = DocumentPackage.load(source_docx)
    original = {name: package.part(name) for name in package.part_names() if name != DOCUMENT_PART}

    apply_code(package)
    output = tmp_path / "out.docx"
    package.save(output)

    with zipfile.ZipFile(source_docx) as _source, zipfile.ZipFile(output) as result:
        for name, payload in original.items():
            assert result.read(name) == payload


def test_code_stage_metadata():
    stage = CodeStage()
    assert stage.name.value == "code"
    assert stage.order == 60
    assert stage.mutates == frozenset({"word/document.xml"})
    assert stage.idempotent is True


def test_table_spec_default_tidak_mengubah_tabel_data(tmp_path):
    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "2"
    source = tmp_path / "data.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    info = iter_tables(package)[0]
    from docgen.docx.tables import normalize_table, set_borders, set_table_width

    normalize_table(package, info.element, TableSpec())
    set_borders(info.element, TableSpec().borders)
    set_table_width(info.element, 100)
    assert is_code_table(info.element) is False
