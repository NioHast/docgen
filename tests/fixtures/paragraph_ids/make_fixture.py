"""Pembuat fixture DOCX untuk tes injeksi ID paragraf.

Fixture sengaja memakai python-docx, bukan Laporan.docx, supaya tes tidak
bergantung pada hasil build pipeline. Jalankan:

    python tests/fixtures/paragraph_ids/make_fixture.py
"""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def ensure_style(document: Document, name: str):
    for style in document.styles:
        if style.name == name or style.style_id == name:
            return style
    return document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def add_field_char(paragraph, field_type: str) -> None:
    run = paragraph.add_run()
    field = OxmlElement("w:fldChar")
    field.set(qn("w:fldCharType"), field_type)
    run._r.append(field)


def add_instruction(paragraph, instruction: str) -> None:
    run = paragraph.add_run()
    text = OxmlElement("w:instrText")
    text.set(qn("xml:space"), "preserve")
    text.text = instruction
    run._r.append(text)


def add_complex_field(paragraph, instruction: str, result: str) -> None:
    add_field_char(paragraph, "begin")
    add_instruction(paragraph, instruction)
    add_field_char(paragraph, "separate")
    paragraph.add_run(result)
    add_field_char(paragraph, "end")


def configure_header_footer(section, label: str) -> None:
    header = section.header
    header.is_linked_to_previous = False
    header.paragraphs[0].text = f"Header {label}"
    footer = section.footer
    footer.is_linked_to_previous = False
    footer.paragraphs[0].text = f"Footer {label}"


def build_fixture(path: Path) -> Path:
    document = Document()

    styles = {
        name: ensure_style(document, name)
        for name in (
            "Heading 1",
            "Heading 2",
            "Body Text",
            "Image Caption",
            "Table Caption",
            "Bibliography",
            "Cover Title",
            "Cover Name",
            "TOC Heading",
            "TOC 1",
            "TOC 2",
        )
    }

    document.add_paragraph("JUDUL SAMPUL", style=styles["Cover Title"])
    document.add_paragraph("Nama Mahasiswa", style=styles["Cover Name"])
    configure_header_footer(document.sections[0], "sampul")

    document.add_section(WD_SECTION.NEW_PAGE)
    configure_header_footer(document.sections[-1], "front matter")

    document.add_paragraph("DAFTAR ISI", style=styles["TOC Heading"])

    toc_start = document.add_paragraph(style=styles["TOC 1"])
    add_field_char(toc_start, "begin")
    add_instruction(toc_start, ' TOC \\o "1-3" \\h \\z \\u ')
    add_field_char(toc_start, "separate")

    toc_entry = document.add_paragraph(style=styles["TOC 1"])
    toc_entry.add_run("BAB I PENDAHULUAN")
    add_complex_field(toc_entry, " PAGEREF _Toc1 \\h ", "1")

    toc_entry_2 = document.add_paragraph(style=styles["TOC 2"])
    toc_entry_2.add_run("1.1 Latar Belakang")
    add_complex_field(toc_entry_2, " PAGEREF _Toc2 \\h ", "1")

    toc_end = document.add_paragraph(style=styles["TOC 1"])
    add_field_char(toc_end, "end")

    document.add_section(WD_SECTION.NEW_PAGE)
    configure_header_footer(document.sections[-1], "body")

    document.add_paragraph("BAB I PENDAHULUAN", style=styles["Heading 1"])
    document.add_paragraph("1.1 Latar Belakang", style=styles["Heading 2"])
    document.add_paragraph("Paragraf pertama di bawah subbab.")
    document.add_paragraph("Gambar 1. Diagram alur.", style=styles["Image Caption"])
    document.add_paragraph("Tabel 1. Data uji.", style=styles["Table Caption"])
    document.add_paragraph(
        "American Psychological Association. (2020). Publication manual.",
        style=styles["Bibliography"],
    )

    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Sel A1"
    table.cell(0, 1).text = "Sel B1"
    table.cell(1, 0).text = "Sel A2"
    table.cell(1, 1).text = "Sel B2"

    document.add_paragraph("Paragraf dengan nomor gambar: ", style=styles["Body Text"])
    seq_paragraph = document.paragraphs[-1]
    add_complex_field(seq_paragraph, " SEQ Gambar \\* ARABIC ", "1")

    page_paragraph = document.add_paragraph("Paragraf dengan nomor halaman: ")
    add_complex_field(page_paragraph, " PAGE ", "2")

    pageref_paragraph = document.add_paragraph("Lihat halaman ")
    add_complex_field(pageref_paragraph, " PAGEREF _Toc1 \\h ", "1")

    document.add_paragraph("1.2 Rumusan Masalah", style=styles["Heading 2"])
    document.add_paragraph("Paragraf kedua di bawah subbab.")

    document.save(path)
    return path


if __name__ == "__main__":
    target = Path(__file__).with_name("contoh.docx")
    build_fixture(target)
    print(target)
