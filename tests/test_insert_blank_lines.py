"""Tes penyisipan paragraf kosong fisik pada DOCX."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

import insert_blank_lines as api

DOCUMENT_PART = "word/document.xml"
W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_RPR = qn("w:rPr")
W_SPACING = qn("w:spacing")
W_RFONTS = qn("w:rFonts")
W_SZ = qn("w:sz")
W_SZCS = qn("w:szCs")
W_DRAWING = qn("w:drawing")
W_TBL = qn("w:tbl")
W_VAL = qn("w:val")
W_INSTR = qn("w:instr")
W_FLDCHAR = qn("w:fldChar")
W_FLDCHARTYPE = qn("w:fldCharType")
W_INSTRTEXT = qn("w:instrText")


# ---------------------------------------------------------------------------
# Fixture DOCX


def set_style(paragraph, style_id: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(W_PSTYLE)
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(W_VAL, style_id)


def add_complex_field(paragraph, instruction: str, result: str = "1") -> None:
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(W_FLDCHARTYPE, "begin")
    begin_run._r.append(begin)

    instruction_run = paragraph.add_run()
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = instruction
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


def add_dummy_image(paragraph) -> None:
    drawing = OxmlElement("w:drawing")
    paragraph._p.append(drawing)


def build_fixture(path: Path) -> Path:
    document = Document()
    section = document.sections[0]
    section.header.paragraphs[0].text = "Header uji"
    section.footer.paragraphs[0].text = "Footer uji"

    paragraph = document.add_paragraph("DAFTAR ISI")
    set_style(paragraph, "TOCHeading")
    paragraph = document.add_paragraph("BAB I PENDAHULUAN\t1")
    set_style(paragraph, "TOC1")
    add_complex_field(paragraph, ' TOC \\o "1-3" \\h \\z \\u ', result="1")

    paragraph = document.add_paragraph("BAB I PENDAHULUAN")
    set_style(paragraph, "Heading1")
    paragraph = document.add_paragraph("1.1 Latar Belakang")
    set_style(paragraph, "Heading2")
    document.add_paragraph("Isi paragraf pertama.")

    paragraph = document.add_paragraph("1.2 Rumusan Masalah")
    set_style(paragraph, "Heading2")
    paragraph = document.add_paragraph("1.2.1 Tujuan")
    set_style(paragraph, "Heading3")
    document.add_paragraph("Isi setelah Heading3.")

    paragraph = document.add_paragraph("Tabel 1.1 Data")
    set_style(paragraph, "TableCaption")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Sel tabel."
    document.add_paragraph("Isi setelah tabel.")

    paragraph = document.add_paragraph()
    add_dummy_image(paragraph)
    paragraph = document.add_paragraph("Gambar 1.1 Diagram")
    set_style(paragraph, "ImageCaption")
    document.add_paragraph("Isi setelah gambar.")

    paragraph = document.add_paragraph("BAB II TINJAUAN PUSTAKA")
    set_style(paragraph, "Heading1")
    document.add_paragraph("Isi setelah Heading1 kedua.")

    document.save(path)
    return path


@pytest.fixture()
def source_docx(tmp_path: Path) -> Path:
    return build_fixture(tmp_path / "input.docx")


# ---------------------------------------------------------------------------
# Utilitas tes


def run_tool(source: Path, tmp_path: Path, stem: str = "out") -> tuple[Path, api.BlankLineReport]:
    output = tmp_path / f"{stem}.docx"
    report = api.insert_blank_lines(source, output)
    return output, report


def document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read(DOCUMENT_PART))


def body_children(path: Path) -> list[etree._Element]:
    root = document_root(path)
    body = root.find(W_BODY)
    assert body is not None
    return list(body)


def paragraph_text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.iter(qn("w:t")))


def paragraph_style(element: etree._Element) -> str | None:
    style = element.find(f"{W_PPR}/{W_PSTYLE}")
    return style.get(W_VAL) if style is not None else None


def is_blank(element: etree._Element) -> bool:
    return (
        element.tag == W_P
        and not paragraph_text(element).strip()
        and element.find(f".//{W_DRAWING}") is None
    )


def find_index(children: list[etree._Element], text: str) -> int:
    matches = [
        index
        for index, element in enumerate(children)
        if element.tag == W_P and paragraph_text(element) == text
    ]
    assert len(matches) == 1, f"penanda {text!r} tidak tunggal"
    return matches[0]


def find_image_index(children: list[etree._Element]) -> int:
    matches = [
        index
        for index, element in enumerate(children)
        if element.tag == W_P and element.find(f".//{W_DRAWING}") is not None
    ]
    assert len(matches) == 1, "fixture harus punya tepat satu gambar uji"
    return matches[0]


def zip_hashes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
        }


# ---------------------------------------------------------------------------
# Tes posisi paragraf kosong


def test_posisi_paragraf_kosong(source_docx: Path, tmp_path: Path) -> None:
    output, report = run_tool(source_docx, tmp_path)
    children = body_children(output)

    # Satu paragraf kosong setelah setiap Heading1.
    for marker in ("BAB I PENDAHULUAN", "BAB II TINJAUAN PUSTAKA"):
        index = find_index(children, marker)
        assert paragraph_style(children[index]) == "Heading1"
        assert is_blank(children[index + 1])

    # H2 yang mengikuti H1 hanya mendapat satu paragraf kosong (tidak ganda).
    h2_index = find_index(children, "1.2 Rumusan Masalah")
    assert is_blank(children[h2_index - 1])
    assert not is_blank(children[h2_index - 2])

    # H2 langsung diikuti H3 tanpa isi: nol paragraf kosong.
    h3_index = find_index(children, "1.2.1 Tujuan")
    assert h3_index == h2_index + 1

    # Tabel ber-caption: kosong sebelum caption, caption menempel tabel,
    # dan kosong setelah tabel.
    caption_index = find_index(children, "Tabel 1.1 Data")
    assert is_blank(children[caption_index - 1])
    assert children[caption_index + 1].tag == W_TBL
    assert is_blank(children[caption_index + 2])

    # Gambar ber-caption: kosong sebelum gambar, caption menempel gambar,
    # dan kosong setelah caption.
    image_index = find_image_index(children)
    assert is_blank(children[image_index - 1])
    assert paragraph_style(children[image_index + 1]) == "ImageCaption"
    assert is_blank(children[image_index + 2])

    assert report.inserted > 0
    assert report.before_heading >= 1
    assert report.before_object >= 2
    assert report.after_object >= 2


def test_paragraf_kosong_format_tnr_12_line_360(
    source_docx: Path, tmp_path: Path
) -> None:
    output, _ = run_tool(source_docx, tmp_path)
    children = body_children(output)

    index = find_index(children, "BAB I PENDAHULUAN")
    blank = children[index + 1]
    assert is_blank(blank)

    spacing = blank.find(f"{W_PPR}/{W_SPACING}")
    assert spacing is not None
    assert spacing.get(qn("w:before")) == "0"
    assert spacing.get(qn("w:after")) == "0"
    assert spacing.get(qn("w:line")) == "360"
    assert spacing.get(qn("w:lineRule")) == "auto"

    properties = blank.find(f"{W_PPR}/{W_RPR}")
    assert properties is not None
    fonts = properties.find(W_RFONTS)
    assert fonts is not None
    assert fonts.get(qn("w:ascii")) == "Times New Roman"
    assert fonts.get(qn("w:hAnsi")) == "Times New Roman"
    assert fonts.get(qn("w:cs")) == "Times New Roman"
    assert properties.find(W_SZ).get(W_VAL) == "24"
    assert properties.find(W_SZCS).get(W_VAL) == "24"


def test_tidak_duplikasi_dan_idempoten(source_docx: Path, tmp_path: Path) -> None:
    first, _ = run_tool(source_docx, tmp_path, stem="first")
    second, report_second = run_tool(first, tmp_path, stem="second")

    with zipfile.ZipFile(first) as archive:
        first_xml = archive.read(DOCUMENT_PART)
    with zipfile.ZipFile(second) as archive:
        second_xml = archive.read(DOCUMENT_PART)

    assert first_xml == second_xml
    assert report_second.inserted == 0


def test_paragraf_kosong_yang_sudah_ada_tidak_digandakan(tmp_path: Path) -> None:
    document = Document()
    paragraph = document.add_paragraph("BAB I PENDAHULUAN")
    set_style(paragraph, "Heading1")
    document.add_paragraph("")
    document.add_paragraph("Isi.")
    document.add_paragraph("")
    paragraph = document.add_paragraph("1.1 Subbab")
    set_style(paragraph, "Heading2")
    document.add_paragraph("Isi subbab.")
    source = tmp_path / "existing.docx"
    document.save(source)

    output, report = run_tool(source, tmp_path, stem="existing-out")
    assert report.inserted == 0

    children = body_children(output)
    h1 = find_index(children, "BAB I PENDAHULUAN")
    assert is_blank(children[h1 + 1])
    assert not is_blank(children[h1 + 2])
    h2 = find_index(children, "1.1 Subbab")
    assert is_blank(children[h2 - 1])
    assert not is_blank(children[h2 - 2])


# ---------------------------------------------------------------------------
# Tes TOC, header, dan footer


def test_toc_header_footer_tidak_disentuh(
    source_docx: Path, tmp_path: Path
) -> None:
    output, _ = run_tool(source_docx, tmp_path)

    before_hashes = zip_hashes(source_docx)
    after_hashes = zip_hashes(output)
    assert before_hashes.keys() == after_hashes.keys()
    for name in before_hashes:
        if name != DOCUMENT_PART:
            assert before_hashes[name] == after_hashes[name], name

    before_children = body_children(source_docx)
    after_children = body_children(output)
    toc_heading = find_index(after_children, "DAFTAR ISI")
    assert paragraph_style(after_children[toc_heading]) == "TOCHeading"
    assert paragraph_style(after_children[toc_heading + 1]) == "TOC1"
    assert not is_blank(after_children[toc_heading + 1])

    toc_after = next(
        index
        for index, element in enumerate(after_children)
        if paragraph_style(element) == "TOC1"
    )
    toc_before = next(
        index
        for index, element in enumerate(before_children)
        if paragraph_style(element) == "TOC1"
    )
    assert etree.tostring(after_children[toc_after], method="c14n") == etree.tostring(
        before_children[toc_before], method="c14n"
    )


def test_output_dapat_dibuka_python_docx(source_docx: Path, tmp_path: Path) -> None:
    output, _ = run_tool(source_docx, tmp_path)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    document = Document(output)
    assert any(
        paragraph.text == "BAB I PENDAHULUAN" for paragraph in document.paragraphs
    )


def test_cli_dan_output_boleh_menimpa_input(source_docx: Path, tmp_path: Path) -> None:
    assert api.main(["--docx", str(source_docx), "--out", str(source_docx)]) == 0

    children = body_children(source_docx)
    index = find_index(children, "BAB I PENDAHULUAN")
    assert is_blank(children[index + 1])

    # Menjalankan ulang pada input yang sudah diproses tidak menambah apa pun.
    output = tmp_path / "rerun.docx"
    report = api.insert_blank_lines(source_docx, output)
    assert report.inserted == 0
