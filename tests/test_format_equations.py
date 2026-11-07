"""Tes penomoran persamaan display DOCX (OMML)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Twips
from lxml import etree

import format_equations as api
import normalize_layout as layout_api

DOCUMENT_PART = "word/document.xml"
W_R = qn("w:r")
W_T = qn("w:t")
W_TABS = qn("w:tabs")
W_SPACING = qn("w:spacing")
W_IND = qn("w:ind")
W_JC = qn("w:jc")
M_T = qn("m:t")


# ---------------------------------------------------------------------------
# Fixture DOCX


def _ensure_style(document: Document, name: str):
    for style in document.styles:
        if style.name == name or style.style_id == name:
            return style
    return document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def _configure_section(document: Document) -> None:
    """Lebar konten tepat 9072 twip agar nilai tab stop mudah diperiksa."""

    section = document.sections[0]
    section.page_width = Twips(12240)
    section.page_height = Twips(15840)
    section.left_margin = Twips(1440)
    section.right_margin = Twips(1728)
    section.gutter = Twips(0)


def _add_equation(paragraph, text: str) -> None:
    math_para = OxmlElement("m:oMathPara")
    math = OxmlElement("m:oMath")
    run = OxmlElement("m:r")
    math_text = OxmlElement("m:t")
    math_text.text = text
    run.append(math_text)
    math.append(run)
    math_para.append(math)
    paragraph._p.append(math_para)


def _add_equation_paragraph(
    document: Document, text: str, first_line_indent: bool = False
):
    paragraph = document.add_paragraph()
    if first_line_indent:
        # Meniru Normal style laporan yang memakai first-line 1,25 cm.
        paragraph.paragraph_format.first_line_indent = Cm(1.25)
    _add_equation(paragraph, text)
    return paragraph


def _add_complex_field(paragraph, instruction: str, result: str) -> None:
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin_run._r.append(begin)

    instruction_run = paragraph.add_run()
    instruction_text = OxmlElement("w:instrText")
    instruction_text.set(qn("xml:space"), "preserve")
    instruction_text.text = instruction
    instruction_run._r.append(instruction_text)

    separate_run = paragraph.add_run()
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    separate_run._r.append(separate)

    paragraph.add_run(result)

    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run._r.append(end)


def build_main_fixture(path: Path) -> Path:
    """Dua bab, tiga persamaan display."""

    document = Document()
    _configure_section(document)
    heading1 = _ensure_style(document, "Heading 1")

    document.add_paragraph("BAB I PENDAHULUAN", style=heading1)
    _add_equation_paragraph(document, "x = y", first_line_indent=True)
    _add_equation_paragraph(document, "a + b = c")

    document.add_paragraph("BAB II TINJAUAN PUSTAKA", style=heading1)
    _add_equation_paragraph(document, "p = q")

    document.add_paragraph("Penjelasan variabel.")
    document.save(path)
    return path


def build_a4_fixture(path: Path) -> Path:
    """A4 dengan margin 4/3 cm: lebar konten 7937 twip."""

    document = Document()
    section = document.sections[0]
    section.page_width = Twips(11906)
    section.page_height = Twips(16838)
    section.left_margin = Twips(2268)
    section.right_margin = Twips(1701)
    section.gutter = Twips(0)
    heading1 = _ensure_style(document, "Heading 1")

    document.add_paragraph("BAB I PENDAHULUAN", style=heading1)
    _add_equation_paragraph(document, "x = y")

    document.save(path)
    return path


def build_no_heading_fixture(path: Path) -> Path:
    document = Document()
    _configure_section(document)
    heading2 = _ensure_style(document, "Heading 2")

    document.add_paragraph("Subbab tanpa nomor bab", style=heading2)
    _add_equation_paragraph(document, "x = y")

    document.save(path)
    return path


def build_safety_fixture(path: Path) -> Path:
    document = Document()
    _configure_section(document)
    # Section break di awal: memastikan w:sectPr di pPr dan body tidak rusak.
    document.add_section(WD_SECTION.NEW_PAGE)
    heading1 = _ensure_style(document, "Heading 1")

    document.add_paragraph("BAB I PENDAHULUAN", style=heading1)

    # Persamaan dengan bookmark mengapit OMML.
    paragraph = document.add_paragraph()
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), "7")
    start.set(qn("w:name"), "_TocPersamaan1")
    paragraph._p.append(start)
    _add_equation(paragraph, "x = y")
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), "7")
    paragraph._p.append(end)

    # Persamaan yang memuat field: harus dilewati, counter tetap maju.
    paragraph = document.add_paragraph()
    _add_equation(paragraph, "a = b")
    _add_complex_field(paragraph, " PAGE ", "1")

    # Persamaan biasa setelah persamaan ber-field: nomor (1.3).
    _add_equation_paragraph(document, "c = d")

    field_paragraph = document.add_paragraph("Halaman: ")
    _add_complex_field(field_paragraph, " PAGE ", "1")

    document.save(path)
    return path


@pytest.fixture(scope="session")
def docs(tmp_path_factory):
    root = tmp_path_factory.mktemp("format_equations")
    return SimpleNamespace(
        main=build_main_fixture(root / "main.docx"),
        a4=build_a4_fixture(root / "a4.docx"),
        no_heading=build_no_heading_fixture(root / "tanpa_heading.docx"),
        safety=build_safety_fixture(root / "safety.docx"),
    )


# ---------------------------------------------------------------------------
# Utilitas tes


def run_tool(source: Path, tmp_path: Path, stem: str = "out") -> Path:
    output = tmp_path / f"{stem}.docx"
    assert api.main(["--docx", str(source), "--out", str(output)]) == 0
    return output


def document_xml(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(DOCUMENT_PART)


def document_root(path: Path) -> etree._Element:
    return etree.fromstring(document_xml(path))


def equation_paragraphs(root: etree._Element) -> list[etree._Element]:
    return [
        paragraph
        for paragraph in root.iter(api.W_P)
        if paragraph.find(api.M_O_MATH_PARA) is not None
    ]


def direct_run_text(paragraph: etree._Element) -> str:
    parts: list[str] = []
    for run in paragraph.findall(W_R):
        for text_node in run.findall(W_T):
            parts.append(text_node.text or "")
    return "".join(parts)


def number_runs(paragraph: etree._Element) -> list[etree._Element]:
    return [
        run
        for run in paragraph.findall(W_R)
        if api._run_number_text(run) is not None
    ]


def canonical(element: etree._Element) -> bytes:
    return etree.tostring(element, method="c14n")


# ---------------------------------------------------------------------------
# 1. Nomor per bab dan reset counter


def test_nomor_per_bab_reset(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)
    paragraphs = equation_paragraphs(document_root(output))

    assert len(paragraphs) == 3
    assert [direct_run_text(paragraph) for paragraph in paragraphs] == [
        "(1.1)",
        "(1.2)",
        "(2.1)",
    ]


# ---------------------------------------------------------------------------
# 2. Nomor berada di run terpisah, bukan di dalam OMML


def test_nomor_di_run_terpisah_di_luar_omml(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)
    paragraph = equation_paragraphs(document_root(output))[0]
    equation = paragraph.find(api.M_O_MATH_PARA)
    assert equation is not None

    before = equation_paragraphs(document_root(docs.main))[0].find(api.M_O_MATH_PARA)
    assert before is not None
    assert canonical(equation) == canonical(before)

    math_text = "".join(node.text or "" for node in equation.iter(M_T))
    assert math_text == "x = y"
    assert "(1.1)" not in math_text

    runs = number_runs(paragraph)
    assert len(runs) == 1
    run = runs[0]
    assert run.getparent() is paragraph
    assert run[0].tag == api.W_TAB
    assert "".join(node.text or "" for node in run.findall(W_T)) == "(1.1)"
    assert paragraph.index(equation) < paragraph.index(run)


# ---------------------------------------------------------------------------
# 3. Idempoten


def test_idempoten(docs, tmp_path):
    first = run_tool(docs.main, tmp_path, "first")
    second = run_tool(first, tmp_path, "second")

    assert document_xml(first) == document_xml(second)

    paragraphs = equation_paragraphs(document_root(second))
    assert [direct_run_text(paragraph) for paragraph in paragraphs] == [
        "(1.1)",
        "(1.2)",
        "(2.1)",
    ]
    for paragraph in paragraphs:
        assert len(number_runs(paragraph)) == 1


# ---------------------------------------------------------------------------
# 4. Tanpa Heading1: tidak menomori dan tidak crash


def test_tanpa_heading1_tidak_menomori(docs, tmp_path):
    output = tmp_path / "tanpa_heading_out.docx"
    assert api.main(["--docx", str(docs.no_heading), "--out", str(output)]) == 0

    root = document_root(output)
    paragraphs = equation_paragraphs(root)
    assert len(paragraphs) == 1
    assert direct_run_text(paragraphs[0]) == ""
    assert paragraphs[0].find(f"{api.W_PPR}/{W_TABS}") is None
    assert paragraphs[0].find(f"{api.W_PPR}/{W_IND}") is None
    assert paragraphs[0].find(f"{api.W_PPR}/{W_SPACING}") is None

    # OMML tetap ada dan dokumen tetap dapat dibuka.
    assert paragraphs[0].find(api.M_O_MATH_PARA) is not None
    assert Document(output).paragraphs


# ---------------------------------------------------------------------------
# 5. Spacing dan indentasi


def test_spacing_dan_indent(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)
    root = document_root(output)
    paragraph = equation_paragraphs(root)[0]
    ppr = paragraph.find(api.W_PPR)
    assert ppr is not None

    indent = ppr.find(W_IND)
    assert indent is not None
    assert indent.get(api.W_LEFT) == "1440"
    assert indent.get(api.W_FIRST_LINE) == "0"

    spacing = ppr.find(W_SPACING)
    assert spacing is not None
    assert spacing.get(api.W_BEFORE) == "360"
    assert spacing.get(api.W_AFTER) == "360"

    justification = ppr.find(W_JC)
    assert justification is not None
    assert justification.get(api.W_VAL) == "left"

    tabs = ppr.find(W_TABS)
    assert tabs is not None
    tab = tabs.find(api.W_TAB)
    assert tab is not None
    assert tab.get(api.W_VAL) == "right"
    assert tab.get(api.W_POS) == "9072"

    body = root.find(api.W_BODY)
    assert body is not None
    assert api._content_width(body) == 9072

    # Urutan schema: w:tabs -> w:spacing -> w:ind.
    assert ppr.index(tabs) < ppr.index(spacing) < ppr.index(indent)


def test_urutan_normalize_lalu_equations(docs, tmp_path):
    """Normalisasi lebih dulu, lalu equations: jc=left dan spacing 360 bertahan."""

    normalized = tmp_path / "normalized.docx"
    assert layout_api.main(
        ["--docx", str(docs.main), "--out", str(normalized)]
    ) == 0

    normalized_root = document_root(normalized)
    normalized_ppr = equation_paragraphs(normalized_root)[0].find(api.W_PPR)
    normalized_spacing = normalized_ppr.find(W_SPACING)
    normalized_jc = normalized_ppr.find(W_JC)
    assert normalized_spacing.get(api.W_BEFORE) == "0"
    assert normalized_spacing.get(api.W_AFTER) == "0"
    assert normalized_jc.get(api.W_VAL) == "both"

    output = tmp_path / "after_equations.docx"
    assert api.main(["--docx", str(normalized), "--out", str(output)]) == 0

    paragraphs = equation_paragraphs(document_root(output))
    assert [direct_run_text(paragraph) for paragraph in paragraphs] == [
        "(1.1)",
        "(1.2)",
        "(2.1)",
    ]
    for paragraph in paragraphs:
        ppr = paragraph.find(api.W_PPR)
        spacing = ppr.find(W_SPACING)
        justification = ppr.find(W_JC)
        assert spacing.get(api.W_BEFORE) == "360"
        assert spacing.get(api.W_AFTER) == "360"
        assert justification.get(api.W_VAL) == "left"


def test_tab_kanan_mengikuti_lebar_konten(docs, tmp_path):
    """A4 margin 4/3 cm memakai lebar konten 7937 twip, bukan fallback 9072."""

    output = run_tool(docs.a4, tmp_path, "a4")
    root = document_root(output)
    body = root.find(api.W_BODY)
    assert body is not None
    assert api._content_width(body) == 7937

    paragraph = equation_paragraphs(root)[0]
    tabs = paragraph.find(f"{api.W_PPR}/{W_TABS}")
    assert tabs is not None
    tab = tabs.find(api.W_TAB)
    assert tab is not None
    assert tab.get(api.W_VAL) == "right"
    assert tab.get(api.W_POS) == "7937"


def test_content_width_fallback_9072():
    body = OxmlElement("w:body")
    assert api._content_width(body) == 9072


# ---------------------------------------------------------------------------
# 6. ZIP valid dan part lain tidak berubah


def test_zip_valid_dan_part_lain_identik(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)

    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        with zipfile.ZipFile(docs.main) as source:
            assert set(archive.namelist()) == set(source.namelist())
            for name in archive.namelist():
                if name != DOCUMENT_PART:
                    assert archive.read(name) == source.read(name)

    document = Document(output)
    assert document.paragraphs
    assert etree.fromstring(document_xml(output)) is not None


# ---------------------------------------------------------------------------
# Field, bookmark, dan section tetap aman


def test_field_bookmark_dan_section_tetap_aman(docs, tmp_path):
    before_root = document_root(docs.safety)
    before_sections = list(before_root.iter(api.W_SECT_PR))
    before_field_paragraph = next(
        paragraph
        for paragraph in before_root.iter(api.W_P)
        if direct_run_text(paragraph).startswith("Halaman:")
    )

    output = run_tool(docs.safety, tmp_path, "safety")
    after_root = document_root(output)
    paragraphs = equation_paragraphs(after_root)
    assert len(paragraphs) == 3

    # Persamaan dengan bookmark tetap bernomor; bookmark tidak hilang.
    first = paragraphs[0]
    assert direct_run_text(first) == "(1.1)"
    starts = first.findall(qn("w:bookmarkStart"))
    ends = first.findall(qn("w:bookmarkEnd"))
    assert [node.get(qn("w:id")) for node in starts] == ["7"]
    assert [node.get(qn("w:id")) for node in ends] == ["7"]
    assert starts[0].get(qn("w:name")) == "_TocPersamaan1"

    # Persamaan ber-field dilewati dan pPr-nya tidak disentuh.
    field_equation = paragraphs[1]
    assert field_equation.find(f"{api.W_PPR}/{W_TABS}") is None
    assert field_equation.find(f"{api.W_PPR}/{W_IND}") is None
    assert field_equation.find(f"{api.W_PPR}/{W_SPACING}") is None

    # Counter tetap maju: persamaan ber-field tetap menempati urutan, sehingga
    # persamaan sesudahnya mendapat (1.3), bukan (1.2).
    assert direct_run_text(paragraphs[2]) == "(1.3)"

    # Field di paragraf biasa tidak berubah.
    after_field_paragraph = next(
        paragraph
        for paragraph in after_root.iter(api.W_P)
        if direct_run_text(paragraph).startswith("Halaman:")
    )
    assert canonical(after_field_paragraph) == canonical(before_field_paragraph)

    # Section properties tidak berubah, termasuk sectPr di pPr dan body.
    after_sections = list(after_root.iter(api.W_SECT_PR))
    assert len(before_sections) >= 2
    assert len(after_sections) == len(before_sections)
    for before_section, after_section in zip(before_sections, after_sections):
        assert canonical(after_section) == canonical(before_section)
