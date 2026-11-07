"""Pembuat fixture DOCX untuk tes ``format_figures.py``.

Fixture sengaja dibuat dengan python-docx, bukan dari ``Laporan.docx``, agar
tes tidak bergantung pada hasil build pipeline. Tes memanggil fungsi
``build_*`` ke direktori sementara. Untuk membuat contoh statis secara manual:

    python tests/fixtures/format_figures/make_fixture.py
"""

from __future__ import annotations

import struct
import zlib
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

TBL_PR_ORDER = tuple(
    qn(tag)
    for tag in (
        "w:tblStyle",
        "w:tblpPr",
        "w:tblOverlap",
        "w:bidiVisual",
        "w:tblStyleRowBandSize",
        "w:tblStyleColBandSize",
        "w:tblW",
        "w:jc",
        "w:tblCellSpacing",
        "w:tblInd",
        "w:tblBorders",
        "w:shd",
        "w:tblLayout",
        "w:tblCellMar",
        "w:tblLook",
        "w:tblCaption",
        "w:tblDescription",
    )
)

TC_PR_ORDER = tuple(
    qn(tag)
    for tag in (
        "w:cnfStyle",
        "w:tcW",
        "w:gridSpan",
        "w:hMerge",
        "w:vMerge",
        "w:tcBorders",
        "w:shd",
        "w:noWrap",
        "w:tcMar",
        "w:textDirection",
        "w:tcFitText",
        "w:vAlign",
        "w:hideMark",
    )
)


# ---------------------------------------------------------------------------
# Utilitas fixture


def _ensure_style(document: Document, name: str):
    for style in document.styles:
        if style.name == name or style.style_id == name:
            return style
    return document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def _insert_ordered(parent, element, order) -> None:
    try:
        target_index = order.index(element.tag)
    except ValueError:
        parent.append(element)
        return
    for index, child in enumerate(parent):
        try:
            child_index = order.index(child.tag)
        except ValueError:
            continue
        if child_index > target_index:
            parent.insert(index, element)
            return
    parent.append(element)


def _add_shading(parent, fill: str, order=None) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    if order is None:
        parent.append(shading)
    else:
        _insert_ordered(parent, shading, order)


def _add_tbl_borders(tbl_pr, color: str = "FF0000", size: str = "24") -> None:
    borders = OxmlElement("w:tblBorders")
    for tag in ("w:top", "w:left", "w:bottom", "w:right", "w:insideH", "w:insideV"):
        border = OxmlElement(tag)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), size)
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), color)
        borders.append(border)
    _insert_ordered(tbl_pr, borders, TBL_PR_ORDER)


def _add_tc_borders(tc_pr, color: str = "FF0000") -> None:
    borders = OxmlElement("w:tcBorders")
    for tag in ("w:top", "w:left", "w:bottom", "w:right"):
        border = OxmlElement(tag)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "24")
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), color)
        borders.append(border)
    _insert_ordered(tc_pr, borders, TC_PR_ORDER)


def _add_tc_mar(tc_pr, value: int = 28) -> None:
    margins = OxmlElement("w:tcMar")
    for tag in ("w:top", "w:left", "w:bottom", "w:right"):
        margin = OxmlElement(tag)
        margin.set(qn("w:w"), str(value))
        margin.set(qn("w:type"), "dxa")
        margins.append(margin)
    _insert_ordered(tc_pr, margins, TC_PR_ORDER)


def _png_bytes(width: int = 200, height: int = 100) -> bytes:
    """PNG RGB sederhana tanpa ketergantungan Pillow."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", checksum)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes((215, 225, 235)) * width
    pixels = b"".join(b"\x00" + row for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(pixels, 9))
        + chunk(b"IEND", b"")
    )


def _add_image(
    document: Document,
    width,
    height,
    align=WD_ALIGN_PARAGRAPH.JUSTIFY,
    before=Pt(6),
    after=Pt(6),
):
    paragraph = document.add_paragraph()
    paragraph.alignment = align
    paragraph.paragraph_format.space_before = before
    paragraph.paragraph_format.space_after = after
    run = paragraph.add_run()
    run.add_picture(
        BytesIO(_png_bytes()),
        width=width,
        height=height,
    )
    return paragraph


def _add_complex_field(paragraph, instruction: str, result: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    run._r.append(begin)

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


def _add_bookmark(paragraph, name: str, bookmark_id: int) -> tuple:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.append(start)
    return start, end


def _decorate_table(table) -> None:
    tbl_pr = table._tbl.tblPr
    _add_tbl_borders(tbl_pr)
    _add_shading(tbl_pr, "D9E2F3", TBL_PR_ORDER)

    row_properties = table.rows[0]._tr.get_or_add_trPr()
    _add_shading(row_properties, "FFF2CC")

    cell_properties = table.cell(0, 0)._tc.get_or_add_tcPr()
    _add_shading(cell_properties, "E2EFDA", TC_PR_ORDER)
    _add_tc_borders(cell_properties)
    _add_tc_mar(cell_properties, 28)


def _fill_table(table, values) -> None:
    for row_index, row_values in enumerate(values):
        for column_index, value in enumerate(row_values):
            cell = table.cell(row_index, column_index)
            cell.text = value
            if row_index == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True


def _set_column_widths(table, widths) -> None:
    table.autofit = False
    for column, width in zip(table.columns, widths):
        column.width = width


def _configure_header_footer(document: Document) -> None:
    section = document.sections[0]
    section.header.paragraphs[0].text = "Header fixture"
    section.footer.paragraphs[0].text = "Footer fixture"


# ---------------------------------------------------------------------------
# Fixture utama: 2 bab, 3 gambar, 2 tabel


def build_main_fixture(path: Path) -> Path:
    document = Document()
    heading1 = _ensure_style(document, "Heading 1")
    heading2 = _ensure_style(document, "Heading 2")
    image_caption = _ensure_style(document, "Image Caption")
    table_caption = _ensure_style(document, "Table Caption")
    _configure_header_footer(document)

    document.add_paragraph("BAB I PENDAHULUAN", style=heading1)

    _add_image(document, Cm(10), Cm(5))
    caption = document.add_paragraph(style=image_caption)
    caption.add_run("Gambar 1. ")
    _, end = _add_bookmark(caption, "_TocGambar1", 1)
    caption.add_run("Diagram alur")
    caption._p.append(end)

    _add_image(document, Cm(8), Cm(4))
    caption = document.add_paragraph(style=image_caption)
    caption.add_run("Gambar 1.2 ")
    italic_run = caption.add_run("Foto hasil")
    italic_run.italic = True

    document.add_paragraph("Tabel 1. Data responden", style=table_caption)
    table = document.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_column_widths(table, [Cm(4), Cm(6)])
    _fill_table(
        table,
        [
            ["Nama", "Nilai"],
            ["Ahmad", "90"],
            ["Budi", "85"],
        ],
    )
    table.cell(2, 0).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _decorate_table(table)

    page_paragraph = document.add_paragraph("Halaman ")
    _add_complex_field(page_paragraph, " PAGE ", "1")

    document.add_paragraph("1.1 Latar Belakang", style=heading2)
    document.add_paragraph("Paragraf isi pada bab pertama.")

    document.add_paragraph("BAB II TINJAUAN PUSTAKA", style=heading1)

    _add_image(document, Cm(12), Cm(6))
    document.add_paragraph("Gambar 2. Arsitektur sistem", style=image_caption)

    document.add_paragraph("Tabel 2. Hasil pengujian", style=table_caption)
    table = document.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.RIGHT
    _set_column_widths(table, [Cm(5), Cm(5)])
    _fill_table(
        table,
        [
            ["Skenario", "Hasil"],
            ["Login", "Berhasil"],
        ],
    )
    _decorate_table(table)

    document.add_paragraph("Paragraf isi pada bab kedua.")
    document.save(path)
    return path


# ---------------------------------------------------------------------------
# Fixture gambar besar: 20 cm harus di-clamp, 10 cm tidak berubah


def build_oversized_fixture(path: Path) -> Path:
    document = Document()
    heading1 = _ensure_style(document, "Heading 1")
    image_caption = _ensure_style(document, "Image Caption")

    document.add_paragraph("BAB III METODOLOGI PENELITIAN", style=heading1)
    _add_image(document, Cm(20), Cm(10))
    document.add_paragraph("Gambar 1. Diagram besar", style=image_caption)

    _add_image(document, Cm(10), Cm(5))
    document.add_paragraph("Gambar 2. Diagram kecil", style=image_caption)

    document.save(path)
    return path


# ---------------------------------------------------------------------------
# Fixture tanpa Heading1


def build_no_heading_fixture(path: Path) -> Path:
    document = Document()
    heading2 = _ensure_style(document, "Heading 2")
    image_caption = _ensure_style(document, "Image Caption")
    table_caption = _ensure_style(document, "Table Caption")
    generic_caption = document.styles["Caption"]

    document.add_paragraph("Subbab tanpa nomor bab", style=heading2)
    _add_image(document, Cm(10), Cm(5))
    document.add_paragraph("Gambar 4.2 Diagram tanpa bab", style=image_caption)
    document.add_paragraph("Gambar 9.9 Caption generik", style=generic_caption)

    document.add_paragraph("Tabel 4.1 Data tanpa bab", style=table_caption)
    table = document.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    _fill_table(table, [["A", "B"], ["C", "D"]])
    _decorate_table(table)

    document.save(path)
    return path


# ---------------------------------------------------------------------------
# Fixture caption bergaya Caption (bukan ImageCaption/TableCaption)


def build_generic_caption_fixture(path: Path) -> Path:
    document = Document()
    heading1 = _ensure_style(document, "Heading 1")
    generic_caption = document.styles["Caption"]

    document.add_paragraph("BAB IV HASIL DAN PEMBAHASAN", style=heading1)

    # Prefix sengaja dipecah ke beberapa run untuk menguji penggantian teks
    # lintas-run tanpa menghapus formatting run judul.
    split_caption = document.add_paragraph(style=generic_caption)
    split_caption.add_run("Gambar ")
    split_caption.add_run("5. ")
    title_run = split_caption.add_run("Diagram generik")
    title_run.italic = True

    document.add_paragraph("Tabel 9. Data generik", style=generic_caption)
    document.add_paragraph("Paragraf biasa, bukan caption.", style=generic_caption)

    document.save(path)
    return path


# ---------------------------------------------------------------------------
# Fixture caption dengan SEQ field di prefix


def build_field_caption_fixture(path: Path) -> Path:
    document = Document()
    heading1 = _ensure_style(document, "Heading 1")
    image_caption = _ensure_style(document, "Image Caption")

    document.add_paragraph("BAB V KESIMPULAN", style=heading1)

    caption = document.add_paragraph(style=image_caption)
    caption.add_run("Gambar 1.")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), " SEQ Gambar_5. \\* ARABIC ")
    field_run = OxmlElement("w:r")
    field_text = OxmlElement("w:t")
    field_text.text = "1"
    field_run.append(field_text)
    field.append(field_run)
    caption._p.append(field)
    caption.add_run(" Diagram field")

    document.add_paragraph("Gambar 2. Diagram literal", style=image_caption)
    document.save(path)
    return path


if __name__ == "__main__":
    target = Path(__file__).with_name("contoh.docx")
    build_main_fixture(target)
    print(target)
