"""Tes unit stage ``equations``: nomor per bab, ChapterTitle, OMML aman."""

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Twips
from lxml import etree

from docgen.docx import DOCUMENT_PART, DocumentPackage
from docgen.docx.page import PageError
from docgen.pipeline import BuildOptions, StageName
from docgen.stages import equations

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_R = qn("w:r")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_TABS = qn("w:tabs")
W_IND = qn("w:ind")
W_SPACING = qn("w:spacing")
W_JC = qn("w:jc")
W_VAL = qn("w:val")
W_LEFT = qn("w:left")
W_POS = qn("w:pos")
W_FLDCHAR = qn("w:fldChar")
W_FLDCHARTYPE = qn("w:fldCharType")
W_INSTRTEXT = qn("w:instrText")
W_BOOKMARK_START = qn("w:bookmarkStart")
W_BOOKMARK_END = qn("w:bookmarkEnd")
M_T = qn("m:t")
M_O_MATH_PARA = qn("m:oMathPara")
M_O_MATH = qn("m:oMath")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _set_style(paragraph, style_id: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(W_PSTYLE)
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(W_VAL, style_id)


def _configure_a4(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Twips(11906)
    section.page_height = Twips(16838)
    section.left_margin = Twips(2268)
    section.right_margin = Twips(1701)
    section.gutter = Twips(0)


def _add_equation(paragraph, text: str, *, display_para: bool = True) -> None:
    container = OxmlElement("m:oMathPara") if display_para else paragraph._p
    math = OxmlElement("m:oMath")
    run = OxmlElement("m:r")
    math_text = OxmlElement("m:t")
    math_text.text = text
    run.append(math_text)
    math.append(run)
    if display_para:
        container.append(math)
        paragraph._p.append(container)
    else:
        container.append(math)


def _add_complex_field(paragraph, instruction: str, result: str) -> None:
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(W_FLDCHARTYPE, "begin")
    begin_run._r.append(begin)

    instruction_run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    instruction_run._r.append(instr)

    separate_run = paragraph.add_run()
    separate = OxmlElement("w:fldChar")
    separate.set(W_FLDCHARTYPE, "separate")
    separate_run._r.append(separate)

    paragraph.add_run(result)

    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(W_FLDCHARTYPE, "end")
    end_run._r.append(end)


def build_equations_fixture(path: Path) -> Path:
    document = Document()
    _configure_a4(document)

    heading = document.add_paragraph("BAB 2 PENDAHULUAN")
    _set_style(heading, "Heading1")

    first = document.add_paragraph()
    _add_equation(first, "a = b")

    field_equation = document.add_paragraph()
    _add_equation(field_equation, "c = d")
    _add_complex_field(field_equation, " PAGE ", "1")

    third = document.add_paragraph()
    _add_equation(third, "e = f")

    heading = document.add_paragraph("DAFTAR PUSTAKA")
    _set_style(heading, "Heading1")

    after_back_matter = document.add_paragraph()
    _add_equation(after_back_matter, "g = h")

    chapter_four = document.add_paragraph("BAB IV TINJAUAN PUSTAKA")
    _set_style(chapter_four, "ChapterTitle")
    fourth = document.add_paragraph()
    _add_equation(fourth, "i = j")

    chapter_nine = document.add_paragraph("BAB IX METODE")
    _set_style(chapter_nine, "ChapterTitle")
    fifth = document.add_paragraph()
    _add_equation(fifth, "k = l")

    document.save(path)
    return path


def build_no_chapter_fixture(path: Path) -> Path:
    document = Document()
    _configure_a4(document)
    heading = document.add_paragraph("Subbab tanpa bab")
    _set_style(heading, "Heading2")
    equation = document.add_paragraph()
    _add_equation(equation, "x = y")
    document.save(path)
    return path


@pytest.fixture()
def equations_docx(tmp_path: Path) -> Path:
    return build_equations_fixture(tmp_path / "equations.docx")


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------


def _paragraphs(package: DocumentPackage):
    body = package.xml(DOCUMENT_PART).find(W_BODY)
    assert body is not None
    return list(body.iter(W_P))


def _equation_paragraphs(package: DocumentPackage):
    return [
        paragraph
        for paragraph in _paragraphs(package)
        if paragraph.find(M_O_MATH_PARA) is not None or paragraph.find(M_O_MATH) is not None
    ]


def _direct_run_text(paragraph) -> str:
    return "".join((text.text or "") for run in paragraph.findall(W_R) for text in run.findall(W_T))


def _number_runs(paragraph):
    return [run for run in paragraph.findall(W_R) if equations.run_number_text(run) is not None]


def _canonical(element) -> bytes:
    return etree.tostring(element, method="c14n")


def _save(package: DocumentPackage, path: Path) -> Path:
    package.save(path)
    return path


# ---------------------------------------------------------------------------
# Tes
# ---------------------------------------------------------------------------


def test_nomor_per_bab_chapter_title_dan_romawi(equations_docx: Path, tmp_path: Path) -> None:
    package = DocumentPackage.load(equations_docx)
    report = equations.format_equations(package)
    output = _save(package, tmp_path / "out.docx")
    result = DocumentPackage.load(output)
    paragraphs = _equation_paragraphs(result)

    # Empat persamaan bernomor; satu persamaan ber-field dilewati tetapi
    # counter tetap maju. DAFTAR PUSTAKA tidak mereset bab.
    assert [(_direct_run_text(paragraph)) for paragraph in paragraphs] == [
        "(2.1)",
        "1",
        "(2.3)",
        "(2.4)",
        "(4.1)",
        "(9.1)",
    ]
    assert report.equation_paragraphs == 6
    assert report.numbered == 5
    assert report.skipped_field == 1
    assert report.bab_headings == 3


def test_heading_arab_bertitik_dikenali_sebagai_bab(tmp_path: Path) -> None:
    source = tmp_path / "arabic.docx"
    document = Document()
    _configure_a4(document)
    heading = document.add_paragraph("4. Metode")
    _set_style(heading, "Heading1")
    equation = document.add_paragraph()
    _add_equation(equation, "x = y")
    document.save(source)

    package = DocumentPackage.load(source)
    report = equations.format_equations(package)
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))

    assert report.bab_headings == 1
    assert report.numbered == 1
    assert [_direct_run_text(paragraph) for paragraph in _equation_paragraphs(result)] == ["(4.1)"]


def test_nomor_di_run_luar_omml(equations_docx: Path, tmp_path: Path) -> None:
    before = DocumentPackage.load(equations_docx)
    before_equation = _equation_paragraphs(before)[0].find(M_O_MATH_PARA)

    package = DocumentPackage.load(equations_docx)
    equations.format_equations(package)
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))
    paragraph = _equation_paragraphs(result)[0]
    after_equation = paragraph.find(M_O_MATH_PARA)
    assert after_equation is not None
    assert _canonical(after_equation) == _canonical(before_equation)

    math_text = "".join(node.text or "" for node in after_equation.iter(M_T))
    assert math_text == "a = b"
    assert "(2.1)" not in math_text

    runs = _number_runs(paragraph)
    assert len(runs) == 1
    assert runs[0].getparent() is paragraph
    assert runs[0][0].tag == W_TAB
    assert paragraph.index(after_equation) < paragraph.index(runs[0])


def test_tab_stop_dan_indentasi(equations_docx: Path, tmp_path: Path) -> None:
    package = DocumentPackage.load(equations_docx)
    equations.format_equations(package)
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))
    paragraph = _equation_paragraphs(result)[0]
    ppr = paragraph.find(W_PPR)
    assert ppr is not None

    tabs = ppr.find(W_TABS)
    assert tabs is not None
    tab = tabs.find(W_TAB)
    assert tab is not None
    assert tab.get(W_VAL) == "right"
    # A4 dengan margin kiri 2268 dan kanan 1701: 11906 - 2268 - 1701 = 7937.
    assert tab.get(W_POS) == "7937"

    indent = ppr.find(W_IND)
    assert indent is not None
    assert indent.get(W_LEFT) == "1440"
    assert indent.get(qn("w:firstLine")) == "0"

    spacing = ppr.find(W_SPACING)
    assert spacing is not None
    assert spacing.get(qn("w:before")) == "0"
    assert spacing.get(qn("w:after")) == "0"
    assert ppr.find(W_JC).get(W_VAL) == "left"

    assert ppr.index(tabs) < ppr.index(spacing) < ppr.index(indent)


def test_persamaan_tanpa_sectpr_menimbulkan_page_error(tmp_path: Path) -> None:
    document = Document()
    _configure_a4(document)
    heading = document.add_paragraph("BAB I PENDAHULUAN")
    _set_style(heading, "Heading1")
    equation = document.add_paragraph()
    _add_equation(equation, "x = y")
    source = tmp_path / "no-section.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    body = package.xml(DOCUMENT_PART).find(W_BODY)
    assert body is not None
    for section in body.findall(qn("w:sectPr")):
        body.remove(section)

    with pytest.raises(PageError) as excinfo:
        equations.format_equations(package)
    assert excinfo.value.code == "PAGE-WIDTH"


def test_tanpa_persamaan_tanpa_sectpr_tidak_gagal(tmp_path: Path) -> None:
    document = Document()
    _configure_a4(document)
    heading = document.add_paragraph("BAB I PENDAHULUAN")
    _set_style(heading, "Heading1")
    source = tmp_path / "no-equation-no-section.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    body = package.xml(DOCUMENT_PART).find(W_BODY)
    assert body is not None
    for section in body.findall(qn("w:sectPr")):
        body.remove(section)

    report = equations.format_equations(package)

    assert report.equation_paragraphs == 0
    assert report.numbered == 0


def test_field_dan_bookmark_tetap_aman(equations_docx: Path, tmp_path: Path) -> None:
    package = DocumentPackage.load(equations_docx)
    field_paragraph = _equation_paragraphs(package)[1]
    assert field_paragraph.find(f"{W_PPR}/{W_TABS}") is None
    before_field = _canonical(field_paragraph)

    # Tambahkan bookmark mengapit persamaan pertama.
    first_equation = _equation_paragraphs(package)[0]
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), "7")
    start.set(qn("w:name"), "_TocPersamaan")
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), "7")
    first_equation.insert(0, start)
    first_equation.append(end)

    equations.format_equations(package)
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))
    paragraphs = _equation_paragraphs(result)
    assert _canonical(paragraphs[1]) == before_field
    assert paragraphs[1].find(f"{W_PPR}/{W_TABS}") is None

    first = paragraphs[0]
    assert first.find(f"{W_BOOKMARK_START}") is not None
    assert first.find(f"{W_BOOKMARK_END}") is not None
    assert first.find(W_BOOKMARK_START).get(qn("w:id")) == "7"
    assert first.find(W_BOOKMARK_END).get(qn("w:id")) == "7"


def test_tanpa_bab_tidak_menomori_dan_tidak_mengubah_ppr(
    tmp_path: Path,
) -> None:
    source = build_no_chapter_fixture(tmp_path / "no-chapter.docx")
    package = DocumentPackage.load(source)
    report = equations.format_equations(package)
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))
    paragraph = _equation_paragraphs(result)[0]

    assert report.skipped_no_chapter == 1
    assert _direct_run_text(paragraph) == ""
    assert paragraph.find(f"{W_PPR}/{W_TABS}") is None
    assert paragraph.find(f"{W_PPR}/{W_IND}") is None
    assert paragraph.find(f"{W_PPR}/{W_SPACING}") is None


def test_direct_omath_dengan_nomor_lama_tetap_diformat(
    tmp_path: Path,
) -> None:
    document = Document()
    _configure_a4(document)
    heading = document.add_paragraph("BAB II TINJAUAN")
    _set_style(heading, "Heading1")
    paragraph = document.add_paragraph()
    _add_equation(paragraph, "p = q", display_para=False)
    run = paragraph.add_run()
    run.add_tab()
    run.add_text("(2.1)")
    source = tmp_path / "word-normalized.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    equations.format_equations(package)
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))
    candidate = _equation_paragraphs(result)[0]
    assert _direct_run_text(candidate) == "(2.1)"
    assert candidate.find(f"{W_PPR}/{W_IND}").get(W_LEFT) == "1440"


def test_idempoten_part_identik_dan_stage(equations_docx: Path, tmp_path: Path) -> None:
    before = {}
    with zipfile.ZipFile(equations_docx) as archive:
        before = {name: archive.read(name) for name in archive.namelist()}

    package = DocumentPackage.load(equations_docx)
    equations.format_equations(package)
    first = _save(package, tmp_path / "first.docx")
    with zipfile.ZipFile(first) as archive:
        after = {name: archive.read(name) for name in archive.namelist()}
    assert before.keys() == after.keys()
    for name in before:
        if name != DOCUMENT_PART:
            assert before[name] == after[name], name

    second_package = DocumentPackage.load(first)
    equations.format_equations(second_package)
    second = _save(second_package, tmp_path / "second.docx")
    assert DocumentPackage.load(first).part(DOCUMENT_PART) == DocumentPackage.load(second).part(
        DOCUMENT_PART
    )

    assert equations.EquationsStage.order == 90
    assert equations.EquationsStage.name is StageName.EQUATIONS
    ctx = SimpleNamespace(package=DocumentPackage.load(second), options=BuildOptions(), format=None)
    assert equations.EquationsStage().run(ctx).changed is False
