"""Tes unit stage/layout WS5: normalize, field bold, tab stop, blank lines."""

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips

from docgen.docx import DOCUMENT_PART, DocumentPackage
from docgen.docx.layout import (
    content_width,
    has_bold_field,
    is_chapter_heading,
    is_exempt,
    iter_body_units,
    normalize_layout,
)
from docgen.docx.numbering import chapter_number
from docgen.docx.paragraphs import heading_level, paragraph_text
from docgen.pipeline import BuildOptions, StageName
from docgen.stages import blank_lines, equations, normalize, numbering

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
W_R = qn("w:r")
W_RPR = qn("w:rPr")
W_B = qn("w:b")
W_BCS = qn("w:bCs")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_TABS = qn("w:tabs")
W_POS = qn("w:pos")
W_FLDCHAR = qn("w:fldChar")
W_FLDCHARTYPE = qn("w:fldCharType")
W_FLDSIMPLE = qn("w:fldSimple")
W_INSTR = qn("w:instr")
W_INSTRTEXT = qn("w:instrText")
W_INS = qn("w:ins")
W_DEL = qn("w:del")
W_TBL = qn("w:tbl")
M_O_MATH_PARA = qn("m:oMathPara")
M_O_MATH = qn("m:oMath")

BODY_BOLD = "Body tebal"
PAGE_BODY_BOLD = "Body PAGE"
PAGE_RESULT = "7"
TOC_TEXT = "Daftar isi"
RIGHT_TEXT = "Agustus 2026"
HEADING_BOLD = "BAB I PENDAHULUAN"
COVER_TITLE = "Judul Sampul"
COVER_NAME = "Nama Mahasiswa"
CODE_TEXT = "print('halo')"
H4_TEXT = "1.1.1.1 Subbagian"
EQUATION_TEXT = "x = y"
TABLE_CAPTION = "Tabel 1.1 Data"
AFTER_TABLE = "Isi setelah tabel."


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


def _add_bold_run(paragraph, text: str):
    run = paragraph.add_run(text)
    run.font.bold = True
    rpr = run._r.get_or_add_rPr()
    rpr.append(OxmlElement("w:bCs"))
    return run


def _add_complex_field(
    paragraph,
    instruction: str,
    result: str,
    *,
    bold_result: bool = False,
) -> None:
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

    result_run = paragraph.add_run(result)
    if bold_result:
        result_run.bold = True

    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(W_FLDCHARTYPE, "end")
    end_run._r.append(end)


def _add_simple_field(paragraph, instruction: str, result: str) -> None:
    field = OxmlElement("w:fldSimple")
    field.set(W_INSTR, instruction)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = result
    run.append(text)
    field.append(run)
    paragraph._p.append(field)


def _add_equation(paragraph, text: str = EQUATION_TEXT) -> None:
    math_para = OxmlElement("m:oMathPara")
    math = OxmlElement("m:oMath")
    run = OxmlElement("m:r")
    math_text = OxmlElement("m:t")
    math_text.text = text
    run.append(math_text)
    math.append(run)
    math_para.append(math)
    paragraph._p.append(math_para)


def _add_custom_tab(paragraph, position: int = 1234) -> None:
    paragraph.paragraph_format.tab_stops.add_tab_stop(Twips(position))


def _conflict(paragraph, *, before: int = 12, after: int = 12, right: bool = False) -> None:
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.alignment = (
        WD_ALIGN_PARAGRAPH.RIGHT if right else WD_ALIGN_PARAGRAPH.LEFT
    )


def build_layout_fixture(path: Path) -> Path:
    document = Document()

    paragraph = document.add_paragraph()
    _set_style(paragraph, "Normal")
    _add_bold_run(paragraph, BODY_BOLD)
    _conflict(paragraph)
    _add_custom_tab(paragraph)

    paragraph = document.add_paragraph(RIGHT_TEXT)
    _set_style(paragraph, "Normal")
    _conflict(paragraph, before=12, after=6, right=True)

    paragraph = document.add_paragraph()
    _set_style(paragraph, "Heading1")
    _add_bold_run(paragraph, HEADING_BOLD)
    _conflict(paragraph, before=12, after=0)

    paragraph = document.add_paragraph()
    _set_style(paragraph, "CoverTitle")
    _add_bold_run(paragraph, COVER_TITLE)
    _conflict(paragraph)

    paragraph = document.add_paragraph()
    _set_style(paragraph, "CoverName")
    _add_bold_run(paragraph, COVER_NAME)
    _conflict(paragraph)

    paragraph = document.add_paragraph()
    _set_style(paragraph, "SourceCode")
    _add_bold_run(paragraph, CODE_TEXT)
    _conflict(paragraph)

    paragraph = document.add_paragraph()
    _set_style(paragraph, "Normal")
    _add_bold_run(paragraph, TOC_TEXT)
    _conflict(paragraph)
    _add_complex_field(paragraph, ' TOC \\o "1-3" \\h \\z \\u ', "1", bold_result=True)

    paragraph = document.add_paragraph()
    _set_style(paragraph, "Normal")
    _add_bold_run(paragraph, PAGE_BODY_BOLD)
    _conflict(paragraph)
    _add_complex_field(paragraph, " PAGE ", PAGE_RESULT, bold_result=True)

    paragraph = document.add_paragraph("Halaman sederhana: ")
    _set_style(paragraph, "Normal")
    _conflict(paragraph)
    _add_simple_field(paragraph, " PAGEREF _Toc1 \\h ", "3")

    paragraph = document.add_paragraph()
    _set_style(paragraph, "Heading4")
    _add_bold_run(paragraph, H4_TEXT)
    _conflict(paragraph)

    document.save(path)
    return path


def build_tracked_fixture(path: Path) -> Path:
    document = Document()

    heading = document.add_paragraph("BAB I PENDAHULUAN")
    _set_style(heading, "Heading1")
    inserted = OxmlElement("w:ins")
    inserted.set(qn("w:id"), "1")
    inserted.set(qn("w:author"), "tester")
    heading._p.addprevious(inserted)
    inserted.append(heading._p)

    content = document.add_paragraph("Isi paragraf.")
    _set_style(content, "Normal")
    inserted.append(content._p)

    deleted = document.add_paragraph("Paragraf dihapus.")
    _set_style(deleted, "Normal")
    deletion = OxmlElement("w:del")
    deletion.set(qn("w:id"), "2")
    deletion.set(qn("w:author"), "tester")
    deleted._p.addprevious(deletion)
    deletion.append(deleted._p)

    heading2 = document.add_paragraph("1.1 Latar Belakang")
    _set_style(heading2, "Heading2")

    h4 = document.add_paragraph(H4_TEXT)
    _set_style(h4, "Heading4")
    document.add_paragraph("Isi setelah H4.")

    caption = document.add_paragraph(TABLE_CAPTION)
    _set_style(caption, "TableCaption")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Sel tabel."
    document.add_paragraph(AFTER_TABLE)

    equation = document.add_paragraph()
    _add_equation(equation)
    document.add_paragraph("Isi setelah persamaan.")

    document.save(path)
    return path


@pytest.fixture()
def layout_docx(tmp_path: Path) -> Path:
    return build_layout_fixture(tmp_path / "layout.docx")


@pytest.fixture()
def tracked_docx(tmp_path: Path) -> Path:
    return build_tracked_fixture(tmp_path / "tracked.docx")


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------


def _paragraphs(package: DocumentPackage):
    body = package.xml(DOCUMENT_PART).find(W_BODY)
    assert body is not None
    return list(body.iter(W_P))


def _paragraph_by_text(package: DocumentPackage, marker: str):
    matches = [
        paragraph for paragraph in _paragraphs(package) if marker in paragraph_text(paragraph)
    ]
    assert len(matches) == 1, f"paragraf {marker!r} tidak tunggal"
    return matches[0]


def _run_by_text(paragraph, marker: str):
    matches = [run for run in paragraph.iter(W_R) if marker in "".join(run.itertext())]
    assert len(matches) == 1, f"run {marker!r} tidak tunggal"
    return matches[0]


def _run_exact(paragraph, text: str):
    matches = [run for run in paragraph.iter(W_R) if "".join(run.itertext()) == text]
    assert len(matches) == 1, f"run {text!r} tidak tunggal"
    return matches[0]


def _has_bold(run) -> bool:
    rpr = run.find(W_RPR)
    if rpr is None:
        return False
    return rpr.find(W_B) is not None or rpr.find(W_BCS) is not None


def _part_hashes(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _save(package: DocumentPackage, path: Path) -> Path:
    package.save(path)
    return path


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def test_normalize_spacing_bold_tab_dan_pengecualian(layout_docx: Path, tmp_path: Path) -> None:
    package = DocumentPackage.load(layout_docx)
    report = normalize_layout(package)
    assert report.checked > 0
    assert report.normalized > 0
    assert report.fields_preserved >= 1

    output = _save(package, tmp_path / "out.docx")
    result = DocumentPackage.load(output)

    body = _paragraph_by_text(result, BODY_BOLD)
    ppr = body.find(W_PPR)
    assert ppr is not None
    spacing = ppr.find(W_SPACING)
    assert spacing is not None
    assert spacing.get(W_BEFORE) == "0"
    assert spacing.get(W_AFTER) == "0"
    assert spacing.get(W_LINE) == "360"
    assert spacing.get(W_LINE_RULE) == "auto"
    assert ppr.find(W_JC).get(W_VAL) == "both"
    assert not _has_bold(_run_by_text(body, BODY_BOLD))

    # Tab stop kustom dipertahankan.
    tabs = ppr.find(W_TABS)
    assert tabs is not None
    assert [(tab.get(W_VAL), tab.get(W_POS)) for tab in tabs.findall(W_TAB)] == [("left", "1234")]

    # Perataan kanan dipertahankan.
    right = _paragraph_by_text(result, RIGHT_TEXT)
    assert right.find(f"{W_PPR}/{W_JC}").get(W_VAL) == "right"

    # Heading dan CoverTitle tidak berubah, bold tetap.
    for marker in (HEADING_BOLD, COVER_TITLE):
        paragraph = _paragraph_by_text(result, marker)
        assert _has_bold(_run_by_text(paragraph, marker))
        assert paragraph.find(f"{W_PPR}/{W_SPACING}") is not None
        assert paragraph.find(f"{W_PPR}/{W_JC}") is not None

    # Cover selain CoverTitle kehilangan bold, layout tidak dinormalisasi.
    cover_name = _paragraph_by_text(result, COVER_NAME)
    assert not _has_bold(_run_by_text(cover_name, COVER_NAME))
    # Layout cover tidak dinormalisasi; spacing konflik dari fixture tetap.
    assert cover_name.find(f"{W_PPR}/{W_SPACING}") is not None

    # Blok kode tidak disentuh.
    code = _paragraph_by_text(result, CODE_TEXT)
    assert _has_bold(_run_by_text(code, CODE_TEXT))
    assert code.find(f"{W_PPR}/{W_SPACING}") is not None

    # Field TOC dikecualikan sebelum bold dihapus; bold hasil field tetap.
    toc = _paragraph_by_text(result, TOC_TEXT)
    assert _has_bold(_run_exact(toc, "1"))
    assert toc.find(f"{W_PPR}/{W_SPACING}") is not None

    # Field PAGE tidak membuat paragraf dikecualikan, tetapi run field tetap
    # bold. Bold body dihapus.
    page = _paragraph_by_text(result, PAGE_BODY_BOLD)
    assert not _has_bold(_run_by_text(page, PAGE_BODY_BOLD))
    assert _has_bold(_run_exact(page, PAGE_RESULT))
    assert page.find(f"{W_PPR}/{W_SPACING}").get(W_LINE) == "360"


def test_normalize_idempoten_dan_part_non_target_identik(layout_docx: Path, tmp_path: Path) -> None:
    before = _part_hashes(layout_docx)
    package = DocumentPackage.load(layout_docx)
    normalize_layout(package)
    first = _save(package, tmp_path / "first.docx")
    after = _part_hashes(first)

    assert before.keys() == after.keys()
    for name in before:
        if name != DOCUMENT_PART:
            assert before[name] == after[name], name

    second_package = DocumentPackage.load(first)
    report = normalize_layout(second_package)
    assert report.normalized == 0
    assert report.bold_runs_removed == 0
    second = _save(second_package, tmp_path / "second.docx")

    first_part = DocumentPackage.load(first).part(DOCUMENT_PART)
    second_part = DocumentPackage.load(second).part(DOCUMENT_PART)
    assert first_part == second_part


def test_stage_normalize_metadata_dan_run(layout_docx: Path) -> None:
    assert normalize.NormalizeStage.order == 80
    assert normalize.NormalizeStage.name is StageName.NORMALIZE
    package = DocumentPackage.load(layout_docx)
    ctx = SimpleNamespace(package=package, options=BuildOptions(), format=None)
    result = normalize.NormalizeStage().run(ctx)
    assert result.stage == "normalize"
    assert result.status == "ok"
    assert result.changed is True
    assert result.metrics["checked"] > 0

    # Run kedua pada package yang sama: tidak ada perubahan semantik.
    second = normalize.NormalizeStage().run(ctx)
    assert second.changed is False


# ---------------------------------------------------------------------------
# Helper layout
# ---------------------------------------------------------------------------


def test_helper_layout_field_bold_dan_bab() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    run = paragraph.add_run("hasil")
    run.bold = True

    field = OxmlElement("w:fldSimple")
    field.set(W_INSTR, " PAGE ")
    field_run = OxmlElement("w:r")
    field_rpr = OxmlElement("w:rPr")
    field_rpr.append(OxmlElement("w:b"))
    field_run.append(field_rpr)
    field_text = OxmlElement("w:t")
    field_text.text = "3"
    field_run.append(field_text)
    field.append(field_run)
    paragraph._p.append(field)

    assert has_bold_field(paragraph._p)
    assert is_exempt(paragraph._p) is False

    assert chapter_number("BAB IV TINJAUAN") == 4
    assert chapter_number("BAB 2 Pendahuluan") == 2
    assert chapter_number("BAB IX") == 9
    assert chapter_number("DAFTAR PUSTAKA") is None
    assert is_chapter_heading("ChapterTitle") is True
    assert is_chapter_heading("Heading1") is True
    assert is_chapter_heading("Heading2") is False


def test_heading_level_paragraph_dan_is_chapter_heading() -> None:
    document = Document()
    paragraph = document.add_paragraph("BAB I")
    _set_style(paragraph, "ChapterTitle")

    assert heading_level(paragraph._p) is None
    assert is_chapter_heading(paragraph._p) is True

    _set_style(paragraph, "Heading 2")

    assert heading_level(paragraph._p) == 2
    assert is_chapter_heading(paragraph._p) is False


def test_content_width_dari_sectpr() -> None:
    document = Document()
    section = document.sections[0]
    section.page_width = Twips(12240)
    section.page_height = Twips(15840)
    section.left_margin = Twips(1440)
    section.right_margin = Twips(1728)
    section.gutter = Twips(0)
    body = document.element.body
    assert content_width(body) == 9072


# ---------------------------------------------------------------------------
# Blank lines
# ---------------------------------------------------------------------------


def _body_children(package: DocumentPackage):
    body = package.xml(DOCUMENT_PART).find(W_BODY)
    assert body is not None
    return body, [unit.element for unit in iter_body_units(body)]


def _child_index(children, marker: str) -> int:
    matches = [
        index
        for index, child in enumerate(children)
        if child.tag == W_P and marker in paragraph_text(child)
    ]
    assert len(matches) == 1, f"penanda {marker!r} tidak tunggal"
    return matches[0]


def _is_blank(child) -> bool:
    return child.tag == W_P and not paragraph_text(child).strip()


def test_blank_lines_tracked_changes_dan_heading4(tracked_docx: Path) -> None:
    package = DocumentPackage.load(tracked_docx)
    report = blank_lines.insert_blank_lines(package)
    assert report.inserted > 0

    body, children = _body_children(package)
    h1 = _child_index(children, "BAB I PENDAHULUAN")
    # Heading1 dibungkus w:ins; paragraf kosong tetap disisipkan setelahnya
    # di dalam pembungkus yang sama.
    assert children[h1].getparent().tag == W_INS
    assert _is_blank(children[h1 + 1])
    assert children[h1 + 1].getparent().tag == W_INS

    # w:del tidak dihitung sebagai isi dan tidak menjadi tempat sisipan.
    deletion = body.find(W_DEL)
    assert deletion is not None
    assert len([child for child in deletion if child.tag == W_P]) == 1

    h2 = _child_index(children, "1.1 Latar Belakang")
    assert _is_blank(children[h2 - 1])

    # Heading4-H9 tidak diklasifikasi sebagai heading struktural dan tidak
    # mendapat aturan gap heading baru.
    h4 = _child_index(children, H4_TEXT)
    assert blank_lines.classify(children[h4]) == blank_lines.CONTENT
    assert not _is_blank(children[h4 - 1])
    assert not _is_blank(children[h4 + 1])

    # Tabel ber-caption: kosong sebelum caption dan setelah tabel.
    caption = _child_index(children, TABLE_CAPTION)
    assert _is_blank(children[caption - 1])
    table_index = next(index for index, child in enumerate(children) if child.tag == W_TBL)
    assert _is_blank(children[table_index + 1])

    # Persamaan display: kosong sebelum dan sesudah (ada isi setelahnya).
    equation_index = next(
        index
        for index, child in enumerate(children)
        if child.tag == W_P and child.find(M_O_MATH_PARA) is not None
    )
    assert _is_blank(children[equation_index - 1])
    assert _is_blank(children[equation_index + 1])

    assert report.before_heading >= 1
    assert report.before_object >= 2
    assert report.after_object >= 2


def test_blank_lines_idempoten_dan_part_identik(tracked_docx: Path, tmp_path: Path) -> None:
    before = _part_hashes(tracked_docx)
    package = DocumentPackage.load(tracked_docx)
    blank_lines.insert_blank_lines(package)
    first = _save(package, tmp_path / "first.docx")
    after = _part_hashes(first)
    for name in before:
        if name != DOCUMENT_PART:
            assert before[name] == after[name], name

    second_package = DocumentPackage.load(first)
    report = blank_lines.insert_blank_lines(second_package)
    assert report.inserted == 0
    second = _save(second_package, tmp_path / "second.docx")
    assert DocumentPackage.load(first).part(DOCUMENT_PART) == DocumentPackage.load(second).part(
        DOCUMENT_PART
    )


def test_urutan_stage_normalize_equations_numbering_blank_lines() -> None:
    assert (
        normalize.NormalizeStage.order
        < equations.EquationsStage.order
        < numbering.NumberingStage.order
        < blank_lines.BlankLinesStage.order
    )
    assert StageName.NORMALIZE in equations.EquationsStage.requires
    assert StageName.EQUATIONS in numbering.NumberingStage.requires
    assert StageName.NUMBERING in blank_lines.BlankLinesStage.requires


def test_stage_blank_lines_metadata(tracked_docx: Path) -> None:
    assert blank_lines.BlankLinesStage.order == 110
    assert blank_lines.BlankLinesStage.name is StageName.BLANK_LINES
    package = DocumentPackage.load(tracked_docx)
    ctx = SimpleNamespace(package=package, options=BuildOptions(), format=None)
    result = blank_lines.BlankLinesStage().run(ctx)
    assert result.status == "ok"
    assert result.changed is True
    second = blank_lines.BlankLinesStage().run(ctx)
    assert second.changed is False
