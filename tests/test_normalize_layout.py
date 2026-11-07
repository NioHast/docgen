"""Tes normalisasi layout paragraf DOCX."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from lxml import etree

import normalize_layout as api

DOCUMENT_PART = "word/document.xml"
W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_SPACING = qn("w:spacing")
W_JC = qn("w:jc")
W_VAL = qn("w:val")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_LINE = qn("w:line")
W_LINE_RULE = qn("w:lineRule")
W_BEFORE_LINES = qn("w:beforeLines")
W_AFTER_LINES = qn("w:afterLines")
W_BEFORE_AUTO = qn("w:beforeAutospacing")
W_AFTER_AUTO = qn("w:afterAutospacing")
W_R = qn("w:r")
W_T = qn("w:t")
W_SECTPR = qn("w:sectPr")
W_BOOKMARK_START = qn("w:bookmarkStart")
W_BOOKMARK_END = qn("w:bookmarkEnd")
W_FLDCHAR = qn("w:fldChar")
W_INSTRTEXT = qn("w:instrText")
W_FLDSIMPLE = qn("w:fldSimple")
W_INSTR = qn("w:instr")
W_FLDCHARTYPE = qn("w:fldCharType")

NORMAL_MARKER = "Paragraf normal dengan spasi satu."
TABLE_MARKER = "Paragraf dalam sel tabel."


# ---------------------------------------------------------------------------
# Fixture DOCX


def set_style(paragraph, style_id: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(W_PSTYLE)
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(W_VAL, style_id)


def set_conflicting_layout(
    paragraph,
    *,
    before: int = 12,
    after: int = 12,
    line: float = 1.0,
    alignment=WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    paragraph_format = paragraph.paragraph_format
    paragraph_format.space_before = Pt(before)
    paragraph_format.space_after = Pt(after)
    paragraph_format.line_spacing = line
    paragraph_format.alignment = alignment


def add_spacing_overrides(paragraph) -> None:
    spacing = paragraph._p.get_or_add_pPr().find(W_SPACING)
    assert spacing is not None
    spacing.set(W_BEFORE_LINES, "100")
    spacing.set(W_AFTER_LINES, "100")
    spacing.set(W_BEFORE_AUTO, "1")
    spacing.set(W_AFTER_AUTO, "1")


def add_complex_field(
    paragraph, instruction: str, result: str = "1", chunks: list[str] | None = None
) -> None:
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(W_FLDCHARTYPE, "begin")
    begin_run._r.append(begin)

    for chunk in chunks or [instruction]:
        instruction_run = paragraph.add_run()
        instr_text = OxmlElement("w:instrText")
        instr_text.set(qn("xml:space"), "preserve")
        instr_text.text = chunk
        instruction_run._r.append(instr_text)

    separate_run = paragraph.add_run()
    separate = OxmlElement("w:fldChar")
    separate.set(W_FLDCHARTYPE, "separate")
    separate_run._r.append(separate)

    paragraph.add_run(result)

    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(W_FLDCHARTYPE, "end")
    end_run._r.append(end)


def add_simple_field(paragraph, instruction: str, result: str = "3") -> None:
    field = OxmlElement("w:fldSimple")
    field.set(W_INSTR, instruction)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = result
    run.append(text)
    field.append(run)
    paragraph._p.append(field)


def build_fixture(path: Path) -> Path:
    document = Document()

    paragraph = document.add_paragraph(NORMAL_MARKER)
    set_style(paragraph, "Normal")
    set_conflicting_layout(paragraph)
    add_spacing_overrides(paragraph)

    for marker, style_id in (
        ("print('halo')", "SourceCode"),
        ("<b>halo</b>", "HTML Code"),
        ("verbatim", "Verbatim Char"),
        ("preformatted", "HTML Preformatted"),
    ):
        paragraph = document.add_paragraph(marker)
        set_style(paragraph, style_id)
        set_conflicting_layout(paragraph, before=6, after=6)

    for marker, style_id in (
        ("Gambar 1.1 Diagram", "ImageCaption"),
        ("Tabel 1.1 Data", "TableCaption"),
        ("Gambar figure", "Figure"),
        ("Gambar captioned", "CaptionedFigure"),
        ("Caption figure", "FigureCaption"),
    ):
        paragraph = document.add_paragraph(marker)
        set_style(paragraph, style_id)
        set_conflicting_layout(paragraph, before=6, after=6)

    for style_id in ("TOC1", "TOC9", "TOCHeading", "CoverTitle", "Cover", "Title"):
        paragraph = document.add_paragraph(f"Isi {style_id}.")
        set_style(paragraph, style_id)
        set_conflicting_layout(paragraph)

    for marker, style_id, alignment, before in (
        ("BAB I PENDAHULUAN", "Heading1", WD_ALIGN_PARAGRAPH.CENTER, 0),
        ("Latar Belakang Penelitian", "Heading2", WD_ALIGN_PARAGRAPH.JUSTIFY, 12),
        ("Judul Bab Kustom", "ChapterTitle", WD_ALIGN_PARAGRAPH.CENTER, 12),
    ):
        paragraph = document.add_paragraph(marker)
        set_style(paragraph, style_id)
        set_conflicting_layout(
            paragraph, before=before, after=0, line=1.5, alignment=alignment
        )

    paragraph = document.add_paragraph("Daftar isi: ")
    set_style(paragraph, "Normal")
    set_conflicting_layout(paragraph)
    add_complex_field(paragraph, ' TOC \\o "1-3" \\h \\z \\u ')

    paragraph = document.add_paragraph("Halaman: ")
    set_style(paragraph, "Normal")
    set_conflicting_layout(paragraph)
    add_simple_field(paragraph, " PAGEREF _Toc123 \\h ")

    paragraph = document.add_paragraph("Halaman pecah: ")
    set_style(paragraph, "Normal")
    set_conflicting_layout(paragraph)
    add_complex_field(
        paragraph,
        "",
        chunks=[" PAGEREF _Toc4", "56 \\h "],
    )

    paragraph = document.add_paragraph("Nomor: ")
    set_style(paragraph, "Normal")
    set_conflicting_layout(paragraph)
    add_complex_field(paragraph, " SEQ Gambar \\* ARABIC ")

    paragraph = document.add_paragraph("Halaman biasa: ")
    set_style(paragraph, "Normal")
    set_conflicting_layout(paragraph)
    add_complex_field(paragraph, " PAGE \\* MERGEFORMAT ")

    table = document.add_table(rows=1, cols=1)
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    cell_paragraph.text = TABLE_MARKER
    set_style(cell_paragraph, "Normal")
    set_conflicting_layout(cell_paragraph)

    document.save(path)
    return path


@pytest.fixture()
def source_docx(tmp_path: Path) -> Path:
    return build_fixture(tmp_path / "input.docx")


# ---------------------------------------------------------------------------
# Utilitas tes


def run_tool(source: Path, tmp_path: Path, stem: str = "out") -> Path:
    output = tmp_path / f"{stem}.docx"
    assert api.main(["--docx", str(source), "--out", str(output)]) == 0
    return output


def document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read(DOCUMENT_PART))


def canonical(element: etree._Element) -> bytes:
    return etree.tostring(element, method="c14n")


def paragraph_text(paragraph: etree._Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(W_T))


def find_paragraph(path: Path, marker: str) -> etree._Element:
    root = document_root(path)
    body = root.find(W_BODY)
    assert body is not None
    matches = [
        paragraph for paragraph in body.iter(W_P) if marker in paragraph_text(paragraph)
    ]
    assert len(matches) == 1, f"paragraf dengan penanda {marker!r} tidak tunggal"
    return matches[0]


def paragraph_by_marker(path: Path, marker: str) -> etree._Element:
    return find_paragraph(path, marker)


def spacing_of(paragraph: etree._Element) -> etree._Element:
    spacing = paragraph.find(f"{W_PPR}/{W_SPACING}")
    assert spacing is not None
    return spacing


def justification_of(paragraph: etree._Element) -> str | None:
    justification = paragraph.find(f"{W_PPR}/{W_JC}")
    assert justification is not None
    return justification.get(W_VAL)


def style_of(paragraph: etree._Element) -> str | None:
    style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
    assert style is not None
    return style.get(W_VAL)


def zip_hashes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
        }


# ---------------------------------------------------------------------------
# Tes wajib


def test_paragraf_normal_dinormalisasi(source_docx: Path, tmp_path: Path) -> None:
    output = run_tool(source_docx, tmp_path)

    paragraph = paragraph_by_marker(output, NORMAL_MARKER)
    spacing = spacing_of(paragraph)

    assert spacing.get(W_BEFORE) == "0"
    assert spacing.get(W_AFTER) == "0"
    assert spacing.get(W_LINE) == "360"
    assert spacing.get(W_LINE_RULE) == "auto"
    for attribute in (W_BEFORE_LINES, W_AFTER_LINES, W_BEFORE_AUTO, W_AFTER_AUTO):
        assert spacing.get(attribute) is None

    assert justification_of(paragraph) == "both"
    assert style_of(paragraph) == "Normal"
    assert paragraph_text(paragraph) == NORMAL_MARKER


@pytest.mark.parametrize(
    ("marker", "style_id"),
    (
        ("print('halo')", "SourceCode"),
        ("<b>halo</b>", "HTML Code"),
        ("verbatim", "Verbatim Char"),
        ("preformatted", "HTML Preformatted"),
    ),
)
def test_paragraf_blok_kode_tidak_berubah(
    source_docx: Path, tmp_path: Path, marker: str, style_id: str
) -> None:
    before = canonical(paragraph_by_marker(source_docx, marker))
    output = run_tool(source_docx, tmp_path)
    after = canonical(paragraph_by_marker(output, marker))

    assert after == before
    assert style_of(paragraph_by_marker(output, marker)) == style_id


@pytest.mark.parametrize(
    ("marker", "style_id"),
    (
        ("Gambar 1.1 Diagram", "ImageCaption"),
        ("Tabel 1.1 Data", "TableCaption"),
    ),
)
def test_caption_tidak_berubah(
    source_docx: Path, tmp_path: Path, marker: str, style_id: str
) -> None:
    before = canonical(paragraph_by_marker(source_docx, marker))
    output = run_tool(source_docx, tmp_path)
    after = canonical(paragraph_by_marker(output, marker))

    assert after == before
    assert style_of(paragraph_by_marker(output, marker)) == style_id


@pytest.mark.parametrize(
    ("marker", "style_id"),
    (
        ("Gambar figure", "Figure"),
        ("Gambar captioned", "CaptionedFigure"),
        ("Caption figure", "FigureCaption"),
    ),
)
def test_paragraf_gambar_tidak_berubah(
    source_docx: Path, tmp_path: Path, marker: str, style_id: str
) -> None:
    before = canonical(paragraph_by_marker(source_docx, marker))
    output = run_tool(source_docx, tmp_path)
    after = canonical(paragraph_by_marker(output, marker))

    assert after == before
    assert style_of(paragraph_by_marker(output, marker)) == style_id


def test_paragraf_dalam_sel_tabel_dinormalisasi(
    source_docx: Path, tmp_path: Path
) -> None:
    output = run_tool(source_docx, tmp_path)

    paragraph = paragraph_by_marker(output, TABLE_MARKER)
    spacing = spacing_of(paragraph)

    assert spacing.get(W_BEFORE) == "0"
    assert spacing.get(W_AFTER) == "0"
    assert spacing.get(W_LINE) == "360"
    assert spacing.get(W_LINE_RULE) == "auto"
    assert justification_of(paragraph) == "both"


@pytest.mark.parametrize(
    "marker",
    (
        "Daftar isi: ",
        "Halaman: ",
        "Halaman pecah: ",
        "Nomor: ",
    ),
)
def test_paragraf_berisi_field_tidak_berubah(
    source_docx: Path, tmp_path: Path, marker: str
) -> None:
    before = canonical(paragraph_by_marker(source_docx, marker))
    output = run_tool(source_docx, tmp_path)
    after = canonical(paragraph_by_marker(output, marker))

    assert after == before


def test_field_biasa_tetap_dinormalisasi(source_docx: Path, tmp_path: Path) -> None:
    output = run_tool(source_docx, tmp_path)

    paragraph = paragraph_by_marker(output, "Halaman biasa: ")
    spacing = spacing_of(paragraph)

    assert spacing.get(W_BEFORE) == "0"
    assert spacing.get(W_AFTER) == "0"
    assert spacing.get(W_LINE) == "360"
    assert spacing.get(W_LINE_RULE) == "auto"
    assert justification_of(paragraph) == "both"


def test_idempoten(source_docx: Path, tmp_path: Path) -> None:
    first = run_tool(source_docx, tmp_path, stem="first")
    second = run_tool(first, tmp_path, stem="second")

    with zipfile.ZipFile(first) as archive:
        first_xml = archive.read(DOCUMENT_PART)
    with zipfile.ZipFile(second) as archive:
        second_xml = archive.read(DOCUMENT_PART)

    assert first_xml == second_xml
    assert canonical(document_root(second)) == canonical(document_root(first))


def test_zip_valid_dan_dapat_dibuka_python_docx(
    source_docx: Path, tmp_path: Path
) -> None:
    output = run_tool(source_docx, tmp_path)

    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert DOCUMENT_PART in archive.namelist()
        assert "[Content_Types].xml" in archive.namelist()

    document = Document(output)
    assert document.paragraphs[0].text == NORMAL_MARKER


# ---------------------------------------------------------------------------
# Tes tambahan


@pytest.mark.parametrize(
    "style_id",
    ("TOC1", "TOC9", "TOCHeading", "CoverTitle", "Cover", "Title"),
)
def test_style_daftar_isi_cover_dan_title_tidak_berubah(
    source_docx: Path, tmp_path: Path, style_id: str
) -> None:
    marker = f"Isi {style_id}."
    before = canonical(paragraph_by_marker(source_docx, marker))
    output = run_tool(source_docx, tmp_path)
    after = canonical(paragraph_by_marker(output, marker))

    assert after == before
    assert style_of(paragraph_by_marker(output, marker)) == style_id


@pytest.mark.parametrize(
    ("marker", "style_id", "alignment", "before_twips", "after_twips"),
    (
        ("BAB I PENDAHULUAN", "Heading1", "center", 0, 0),
        ("Latar Belakang Penelitian", "Heading2", "both", 240, 0),
        ("Judul Bab Kustom", "ChapterTitle", "center", 240, 0),
    ),
)
def test_heading_tidak_berubah(
    source_docx: Path,
    tmp_path: Path,
    marker: str,
    style_id: str,
    alignment: str,
    before_twips: int,
    after_twips: int,
) -> None:
    before = canonical(paragraph_by_marker(source_docx, marker))
    output = run_tool(source_docx, tmp_path)
    paragraph = paragraph_by_marker(output, marker)
    spacing = spacing_of(paragraph)

    assert canonical(paragraph) == before
    assert style_of(paragraph) == style_id
    assert justification_of(paragraph) == alignment
    assert spacing.get(W_BEFORE) == str(before_twips)
    assert spacing.get(W_AFTER) == str(after_twips)


def test_teks_run_style_section_field_dan_bookmark_tidak_berubah(
    source_docx: Path, tmp_path: Path
) -> None:
    output = run_tool(source_docx, tmp_path)

    def snapshot(path: Path) -> dict[str, list[bytes] | list[str]]:
        root = document_root(path)
        body = root.find(W_BODY)
        assert body is not None
        return {
            "text": [node.text or "" for node in body.iter(W_T)],
            "runs": [canonical(run) for run in body.iter(W_R)],
            "styles": [canonical(style) for style in body.iter(W_PSTYLE)],
            "sections": [canonical(sectpr) for sectpr in body.iter(W_SECTPR)],
            "bookmarks": [
                canonical(node)
                for tag in (W_BOOKMARK_START, W_BOOKMARK_END)
                for node in body.iter(tag)
            ],
            "fields": [
                canonical(node)
                for tag in (W_FLDCHAR, W_INSTRTEXT, W_FLDSIMPLE)
                for node in body.iter(tag)
            ],
        }

    assert snapshot(output) == snapshot(source_docx)


def test_part_selain_document_xml_tidak_berubah(
    source_docx: Path, tmp_path: Path
) -> None:
    output = run_tool(source_docx, tmp_path)
    before = zip_hashes(source_docx)
    after = zip_hashes(output)

    assert before.keys() == after.keys()
    for name in before:
        if name != DOCUMENT_PART:
            assert before[name] == after[name], name


def test_output_boleh_menimpa_input(source_docx: Path, tmp_path: Path) -> None:
    assert api.main(["--docx", str(source_docx), "--out", str(source_docx)]) == 0

    paragraph = paragraph_by_marker(source_docx, NORMAL_MARKER)
    assert spacing_of(paragraph).get(W_LINE) == "360"
    assert justification_of(paragraph) == "both"
