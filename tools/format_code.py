"""Format blok kode DOCX sebagai tabel 1x1 bergaris.

Alat ini mencari deretan paragraf berurutan bergaya ``Source Code`` (atau
``Verbatim Char``/``HTML Code``/``HTML Preformatted``) lalu menggabungkannya
menjadi satu tabel 1x1. Setiap baris kode menjadi paragraf tersendiri di dalam
sel, memakai Courier New 10 pt hitam tanpa bold/italic, line spacing 1,0, dan
spasi sebelum/sesudah 0.

Hanya ``word/document.xml`` yang ditulis ulang. Part lain (header, footer,
style, numbering, media, relasi, dan section) disalin byte-per-byte dari DOCX
asli. Paragraf yang memuat field, section break, objek, atau perubahan
terlacak dilewati agar tidak merusak struktur dokumen.

Jalankan:

    python tools/format_code.py --docx input.docx --out output.docx
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
from lxml.etree import _Element

DOCUMENT_PART = "word/document.xml"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_VAL = qn("w:val")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_PTAB = qn("w:ptab")
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_NO_BREAK_HYPHEN = qn("w:noBreakHyphen")
W_INSTR_TEXT = qn("w:instrText")
W_DEL_TEXT = qn("w:delText")
W_FLD_CHAR = qn("w:fldChar")
W_FLD_SIMPLE = qn("w:fldSimple")
W_DRAWING = qn("w:drawing")
W_PICT = qn("w:pict")
W_OBJECT = qn("w:object")
W_TXBX_CONTENT = qn("w:txbxContent")
W_SECT_PR = qn("w:sectPr")
W_COMMENT_REFERENCE = qn("w:commentReference")
W_FOOTNOTE_REFERENCE = qn("w:footnoteReference")
W_ENDNOTE_REFERENCE = qn("w:endnoteReference")
W_INS = qn("w:ins")
W_DEL = qn("w:del")
W_MOVE_FROM = qn("w:moveFrom")
W_MOVE_TO = qn("w:moveTo")

W_BOOKMARK_START = qn("w:bookmarkStart")
W_BOOKMARK_END = qn("w:bookmarkEnd")
W_COMMENT_RANGE_START = qn("w:commentRangeStart")
W_COMMENT_RANGE_END = qn("w:commentRangeEnd")
W_PERM_START = qn("w:permStart")
W_PERM_END = qn("w:permEnd")
W_PROOF_ERR = qn("w:proofErr")

W_W = qn("w:w")
W_TYPE = qn("w:type")
W_SZ = qn("w:sz")
W_COLOR = qn("w:color")
W_SPACE = qn("w:space")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_LINE = qn("w:line")
W_LINE_RULE = qn("w:lineRule")
W_LEFT = qn("w:left")
W_RIGHT = qn("w:right")
W_FIRST_LINE = qn("w:firstLine")
W_PG_SZ = qn("w:pgSz")
W_PG_MAR = qn("w:pgMar")
W_GUTTER = qn("w:gutter")
W_ASCII = qn("w:ascii")
W_HANSI = qn("w:hAnsi")
W_CS = qn("w:cs")
W_EAST_ASIA = qn("w:eastAsia")

# Normalisasi styleId: huruf kecil tanpa spasi/garis bawah/tanda hubung.
# Dengan begitu "Source Code", "SourceCode", dan "source_code" dianggap sama.
CODE_BLOCK_STYLES = frozenset(
    {
        "sourcecode",
        "verbatimchar",
        "htmlcode",
        "htmlpreformatted",
    }
)

# Elemen yang membuat paragraf kode tidak aman direkonstruksi. Field, section
# break, objek, dan perubahan terlacak harus tetap berada di struktur aslinya.
UNSAFE_DESCENDANT_TAGS = frozenset(
    {
        W_FLD_CHAR,
        W_FLD_SIMPLE,
        W_INSTR_TEXT,
        W_SECT_PR,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_TXBX_CONTENT,
        W_COMMENT_REFERENCE,
        W_FOOTNOTE_REFERENCE,
        W_ENDNOTE_REFERENCE,
        W_INS,
        W_DEL,
        W_MOVE_FROM,
        W_MOVE_TO,
    }
)

# Elemen penanda zero-width yang boleh berada di antara paragraf kode tanpa
# memutus satu blok (mis. bookmarkStart/bookmarkEnd di level body).
NEUTRAL_BODY_TAGS = frozenset(
    {
        W_BOOKMARK_START,
        W_BOOKMARK_END,
        W_COMMENT_RANGE_START,
        W_COMMENT_RANGE_END,
        W_PERM_START,
        W_PERM_END,
        W_PROOF_ERR,
    }
)

MARKER_START_TAGS = frozenset(
    {
        W_BOOKMARK_START,
        W_COMMENT_RANGE_START,
        W_PERM_START,
        W_PROOF_ERR,
    }
)
MARKER_END_TAGS = frozenset(
    {
        W_BOOKMARK_END,
        W_COMMENT_RANGE_END,
        W_PERM_END,
    }
)

TEXT_SKIP_TAGS = frozenset(
    {
        W_PPR,
        W_INSTR_TEXT,
        W_DEL_TEXT,
        W_FLD_CHAR,
        W_FLD_SIMPLE,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_TXBX_CONTENT,
    }
)

BORDER_TAGS = ("w:top", "w:left", "w:bottom", "w:right")
CELL_MARGIN_VALUE = 108
CODE_FONT = "Courier New"
CODE_FONT_SIZE_HALF_POINTS = "20"  # 10 pt
CONTENT_WIDTH_FALLBACK = 9360  # letter default: 12240 - 2 x 1440 twip


class FormatCodeError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass
class _Line:
    """Satu baris kode beserta penanda XML yang menempel padanya."""

    text: str = ""
    markers_start: list[_Element] = field(default_factory=list)
    markers_end: list[_Element] = field(default_factory=list)


@dataclass
class FormatCodeReport:
    """Ringkasan pekerjaan yang dilakukan."""

    tables: int = 0
    paragraphs: int = 0
    lines: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "tables": self.tables,
            "paragraphs": self.paragraphs,
            "lines": self.lines,
            "skipped": self.skipped,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Pembacaan dan penulisan DOCX


def _read_document_xml(docx_path: Path) -> bytes:
    try:
        with zipfile.ZipFile(docx_path, "r") as archive:
            try:
                return archive.read(DOCUMENT_PART)
            except KeyError as exc:
                raise FormatCodeError(
                    f"{docx_path} bukan DOCX valid: part {DOCUMENT_PART} tidak ada."
                ) from exc
    except FileNotFoundError as exc:
        raise FormatCodeError(f"File input tidak ditemukan: {docx_path}") from exc
    except zipfile.BadZipFile as exc:
        raise FormatCodeError(
            f"{docx_path} bukan arsip DOCX/ZIP yang valid."
        ) from exc
    except OSError as exc:
        raise FormatCodeError(f"Tidak dapat membaca {docx_path}: {exc}") from exc


def _parse_document(document_xml: bytes) -> tuple[_Element, _Element]:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    try:
        root = etree.fromstring(document_xml, parser)
    except etree.XMLSyntaxError as exc:
        raise FormatCodeError(f"XML {DOCUMENT_PART} tidak valid: {exc}") from exc

    body = root.find(W_BODY)
    if body is None:
        raise FormatCodeError(f"{DOCUMENT_PART} tidak memiliki elemen w:body.")
    return root, body


def _write_docx(input_path: Path, output_path: Path, document_xml: bytes) -> None:
    """Tulis DOCX baru dengan mengganti document.xml saja.

    Part lain disalin dari ZIP asli tanpa parsing ulang agar header, footer,
    style, numbering, media, dan relasi tetap identik.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    temp_path = Path(temp_name)

    try:
        with zipfile.ZipFile(input_path, "r") as source, zipfile.ZipFile(
            temp_path, "w"
        ) as target:
            target.comment = source.comment
            for info in source.infolist():
                data = (
                    document_xml
                    if info.filename == DOCUMENT_PART
                    else source.read(info.filename)
                )
                new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.comment = info.comment
                new_info.extra = info.extra
                new_info.internal_attr = info.internal_attr
                new_info.external_attr = info.external_attr
                new_info.create_system = info.create_system
                target.writestr(new_info, data)
        os.replace(temp_path, output_path)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Deteksi paragraf kode


def _normalize_style_id(style_id: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (style_id or "").lower())


def _paragraph_style_id(paragraph: _Element) -> str | None:
    style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
    if style is None:
        return None
    return style.get(W_VAL)


def _is_code_paragraph(paragraph: _Element) -> bool:
    return (
        _normalize_style_id(_paragraph_style_id(paragraph)) in CODE_BLOCK_STYLES
    )


def _has_unsafe_content(paragraph: _Element) -> bool:
    for element in paragraph.iter():
        if element is paragraph:
            continue
        if element.tag in UNSAFE_DESCENDANT_TAGS:
            return True
    return False


def _paragraph_lines(paragraph: _Element) -> list[_Line]:
    """Ambil baris kode dari satu paragraf.

    Pandoc menulis satu blok kode sebagai paragraf dengan ``w:br`` antarbaris,
    sedangkan sumber lain dapat memakai beberapa paragraf berurutan. Keduanya
    didukung: ``w:br``/``w:cr`` memulai baris baru.
    """

    lines = [_Line()]

    def walk(element: _Element) -> None:
        for child in element:
            tag = child.tag
            if tag in MARKER_START_TAGS:
                lines[-1].markers_start.append(child)
                continue
            if tag in MARKER_END_TAGS:
                lines[-1].markers_end.append(child)
                continue
            if tag == W_T:
                lines[-1].text += child.text or ""
            elif tag in (W_TAB, W_PTAB):
                lines[-1].text += "\t"
            elif tag in (W_BR, W_CR):
                lines.append(_Line())
            elif tag == W_NO_BREAK_HYPHEN:
                lines[-1].text += "\u2011"
            elif tag in TEXT_SKIP_TAGS:
                continue
            else:
                walk(child)

    walk(paragraph)
    return lines


def _collect_code_blocks(
    body: _Element, report: FormatCodeReport
) -> list[list[_Element]]:
    """Kumpulkan deretan paragraf kode yang berurutan di level body."""

    blocks: list[list[_Element]] = []
    current: list[_Element] = []

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append(current)
            current = []

    for child in body:
        if child.tag == W_P:
            if _is_code_paragraph(child):
                if _has_unsafe_content(child):
                    report.skipped += 1
                    flush()
                else:
                    current.append(child)
            else:
                flush()
        elif child.tag in NEUTRAL_BODY_TAGS:
            # Penanda bookmark/comment tidak memutus blok kode.
            continue
        else:
            flush()

    flush()
    return blocks


# ---------------------------------------------------------------------------
# Pembuatan tabel dan paragraf kode


def _int_attribute(element: _Element, name: str) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _content_width(body: _Element) -> int:
    section = body.find(W_SECT_PR)
    if section is None:
        sections = body.findall(f".//{W_SECT_PR}")
        section = sections[-1] if sections else None
    if section is None:
        return CONTENT_WIDTH_FALLBACK

    page_size = section.find(W_PG_SZ)
    page_margin = section.find(W_PG_MAR)
    if page_size is None or page_margin is None:
        return CONTENT_WIDTH_FALLBACK

    width = _int_attribute(page_size, W_W)
    left = _int_attribute(page_margin, W_LEFT)
    right = _int_attribute(page_margin, W_RIGHT)
    if width is None or left is None or right is None:
        return CONTENT_WIDTH_FALLBACK
    gutter = _int_attribute(page_margin, W_GUTTER) or 0

    content_width = width - left - right - gutter
    return content_width if content_width > 0 else CONTENT_WIDTH_FALLBACK


def _run_properties() -> _Element:
    properties = OxmlElement("w:rPr")

    fonts = OxmlElement("w:rFonts")
    for attribute in (W_ASCII, W_HANSI, W_CS, W_EAST_ASIA):
        fonts.set(attribute, CODE_FONT)
    properties.append(fonts)

    for tag in ("w:b", "w:bCs", "w:i", "w:iCs"):
        element = OxmlElement(tag)
        element.set(W_VAL, "0")
        properties.append(element)

    color = OxmlElement("w:color")
    color.set(W_VAL, "000000")
    properties.append(color)

    for tag in ("w:sz", "w:szCs"):
        size = OxmlElement(tag)
        size.set(W_VAL, CODE_FONT_SIZE_HALF_POINTS)
        properties.append(size)

    return properties


def _append_text_run(paragraph: _Element, text: str) -> None:
    """Tambahkan run Courier New 10 pt; tab dipertahankan sebagai w:tab."""

    run = OxmlElement("w:r")
    run.append(_run_properties())

    parts = text.split("\t")
    for index, part in enumerate(parts):
        if index:
            run.append(OxmlElement("w:tab"))
        if part:
            text_node = OxmlElement("w:t")
            text_node.set(XML_SPACE, "preserve")
            text_node.text = part
            run.append(text_node)

    paragraph.append(run)


def _make_code_paragraph(
    line: _Line, style_id: str | None
) -> _Element:
    paragraph = OxmlElement("w:p")
    properties = OxmlElement("w:pPr")

    if style_id:
        style = OxmlElement("w:pStyle")
        style.set(W_VAL, style_id)
        properties.append(style)

    spacing = OxmlElement("w:spacing")
    spacing.set(W_BEFORE, "0")
    spacing.set(W_AFTER, "0")
    spacing.set(W_LINE, "240")
    spacing.set(W_LINE_RULE, "auto")
    properties.append(spacing)

    indentation = OxmlElement("w:ind")
    indentation.set(W_LEFT, "0")
    indentation.set(W_RIGHT, "0")
    indentation.set(W_FIRST_LINE, "0")
    properties.append(indentation)

    paragraph.append(properties)

    for marker in line.markers_start:
        paragraph.append(marker)
    _append_text_run(paragraph, line.text)
    for marker in line.markers_end:
        paragraph.append(marker)

    return paragraph


def _make_table(
    lines: Sequence[_Line], style_id: str | None, content_width: int
) -> _Element:
    table = OxmlElement("w:tbl")

    table_properties = OxmlElement("w:tblPr")

    width = OxmlElement("w:tblW")
    width.set(W_W, "5000")
    width.set(W_TYPE, "pct")
    table_properties.append(width)

    borders = OxmlElement("w:tblBorders")
    for tag in BORDER_TAGS:
        border = OxmlElement(tag)
        border.set(W_VAL, "single")
        border.set(W_SZ, "4")
        border.set(W_SPACE, "0")
        border.set(W_COLOR, "000000")
        borders.append(border)
    table_properties.append(borders)

    table_layout = OxmlElement("w:tblLayout")
    table_layout.set(W_TYPE, "fixed")
    table_properties.append(table_layout)

    cell_margins = OxmlElement("w:tblCellMar")
    for tag in BORDER_TAGS:
        margin = OxmlElement(tag)
        margin.set(W_W, str(CELL_MARGIN_VALUE))
        margin.set(W_TYPE, "dxa")
        cell_margins.append(margin)
    table_properties.append(cell_margins)

    table.append(table_properties)

    grid = OxmlElement("w:tblGrid")
    grid_column = OxmlElement("w:gridCol")
    grid_column.set(W_W, str(content_width))
    grid.append(grid_column)
    table.append(grid)

    row = OxmlElement("w:tr")
    cell = OxmlElement("w:tc")

    cell_properties = OxmlElement("w:tcPr")
    cell_width = OxmlElement("w:tcW")
    cell_width.set(W_W, str(content_width))
    cell_width.set(W_TYPE, "dxa")
    cell_properties.append(cell_width)

    cell_margins = OxmlElement("w:tcMar")
    for tag in BORDER_TAGS:
        margin = OxmlElement(tag)
        margin.set(W_W, str(CELL_MARGIN_VALUE))
        margin.set(W_TYPE, "dxa")
        cell_margins.append(margin)
    cell_properties.append(cell_margins)

    cell.append(cell_properties)

    for line in lines:
        cell.append(_make_code_paragraph(line, style_id))

    row.append(cell)
    table.append(row)
    return table


def _apply_code_blocks(body: _Element, report: FormatCodeReport) -> None:
    content_width = _content_width(body)

    for block in _collect_code_blocks(body, report):
        style_id = _paragraph_style_id(block[0])
        lines: list[_Line] = []
        for paragraph in block:
            lines.extend(_paragraph_lines(paragraph))
        if not lines:
            lines.append(_Line())

        table = _make_table(lines, style_id, content_width)
        block[0].addprevious(table)
        for paragraph in block:
            body.remove(paragraph)

        report.tables += 1
        report.paragraphs += len(block)
        report.lines += len(lines)


# ---------------------------------------------------------------------------
# API dan CLI


def format_code(docx_path: str | Path, out_docx: str | Path) -> FormatCodeReport:
    """Format seluruh blok kode dari ``docx_path`` ke ``out_docx``."""

    input_path = Path(docx_path)
    output_path = Path(out_docx)

    document_xml = _read_document_xml(input_path)
    root, body = _parse_document(document_xml)

    report = FormatCodeReport()
    _apply_code_blocks(body, report)

    if report.skipped:
        report.warnings.append(
            f"{report.skipped} paragraf kode dilewati karena memuat field, "
            "section break, objek, atau perubahan terlacak; paragraf itu "
            "dibiarkan utuh."
        )

    revised_xml = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    _write_docx(input_path, output_path, revised_xml)
    return report


def _summary(report: FormatCodeReport) -> str:
    return "\n".join(
        [
            f"Blok kode menjadi tabel: {report.tables}",
            f"Paragraf kode digabung: {report.paragraphs}",
            f"Baris kode di dalam sel: {report.lines}",
        ]
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Format blok kode DOCX sebagai tabel 1x1 bergaris dengan "
            "Courier New 10 pt."
        )
    )
    parser.add_argument("--docx", type=Path, required=True, help="file DOCX input")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="lokasi DOCX hasil (boleh sama dengan input)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        report = format_code(args.docx, args.out)
    except (FormatCodeError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_summary(report))
    for warning in report.warnings:
        print(f"PERINGATAN: {warning}", file=sys.stderr)
    print(f"DOCX: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
