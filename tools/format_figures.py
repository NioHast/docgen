"""Post-process caption, gambar, dan tabel pada DOCX hasil build.

Alat ini hanya menulis ulang ``word/document.xml``. Part lain (header, footer,
footnote, style, numbering, media, dan relasi) disalin byte-per-byte dari arsip
asli sehingga tidak tersentuh.

Yang dilakukan:

1. Memberi nomor ``Gambar <bab>.<n>`` / ``Tabel <bab>.<n>`` pada paragraf
   caption, dengan nomor bab dari Heading1 terakhir yang berformat
   ``BAB <romawi/arab>`` atau ``<nomor arab>. <judul>`` (proposal), dan
   counter terpisah yang direset per bab.
2. Memusatkan paragraf gambar, menghapus spasi sebelum/sesudahnya, dan
   meng-clamp lebar gambar maksimum ke 14,0 cm (5.040.000 EMU).
3. Menyeragamkan border tabel body (single 0,5 pt hitam), menghapus shading
   tabel/baris/sel, dan menetapkan cell margin atas/bawah 108 twip serta
   kiri/kanan 0.

Jalankan:

    python tools/format_figures.py --docx input.docx --out output.docx
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

EMU_PER_CM = 360_000
MAX_IMAGE_WIDTH_EMU = 14 * EMU_PER_CM  # 5.040.000 EMU = 14,0 cm

CAPTION_PREFIX_RE = re.compile(
    r"^\s*(Gambar|Tabel)\s+\d+(?:\.\d+)?\.?\s*",
    re.IGNORECASE,
)
CAPTION_LABEL_RE = re.compile(r"^\s*(Gambar|Tabel)\b", re.IGNORECASE)
BAB_RE = re.compile(
    r"^\s*BAB\s+(?P<number>[IVXLCDM]+|\d+)(?=\s|[.:;,\-–—]|$)",
    re.IGNORECASE,
)
ARABIC_CHAPTER_RE = re.compile(r"^\s*(?P<number>\d+)(?!\.\d)[\.\s]+")

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_PTAB = qn("w:ptab")
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_NO_BREAK_HYPHEN = qn("w:noBreakHyphen")
W_INSTR_TEXT = qn("w:instrText")
W_FLD_CHAR = qn("w:fldChar")
W_FLD_CHAR_TYPE = qn("w:fldCharType")
W_FLD_SIMPLE = qn("w:fldSimple")
W_DEL = qn("w:del")
W_MOVE_FROM = qn("w:moveFrom")
W_DEL_TEXT = qn("w:delText")
W_DRAWING = qn("w:drawing")
W_PICT = qn("w:pict")
W_OBJECT = qn("w:object")
W_TXBX_CONTENT = qn("w:txbxContent")

W_SPACING = qn("w:spacing")
W_JC = qn("w:jc")
W_VAL = qn("w:val")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_BEFORE_LINES = qn("w:beforeLines")
W_AFTER_LINES = qn("w:afterLines")
W_BEFORE_AUTO = qn("w:beforeAutospacing")
W_AFTER_AUTO = qn("w:afterAutospacing")

W_TBL = qn("w:tbl")
W_TBL_PR = qn("w:tblPr")
W_TBL_PR_EX = qn("w:tblPrEx")
W_TBL_BORDERS = qn("w:tblBorders")
W_TBL_CELL_MAR = qn("w:tblCellMar")
W_TR = qn("w:tr")
W_TR_PR = qn("w:trPr")
W_TC = qn("w:tc")
W_TC_PR = qn("w:tcPr")
W_TC_BORDERS = qn("w:tcBorders")
W_TC_MAR = qn("w:tcMar")
W_SHD = qn("w:shd")
W_W = qn("w:w")
W_TYPE = qn("w:type")
W_SZ = qn("w:sz")
W_COLOR = qn("w:color")
W_SPACE = qn("w:space")

WP_INLINE = qn("wp:inline")
WP_ANCHOR = qn("wp:anchor")
WP_EXTENT = qn("wp:extent")
PIC_PIC = qn("pic:pic")
PIC_SPPR = qn("pic:spPr")
A_XFRM = qn("a:xfrm")
A_EXT = qn("a:ext")

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

PPR_ORDER = tuple(
    qn(tag)
    for tag in (
        "w:pStyle",
        "w:keepNext",
        "w:keepLines",
        "w:pageBreakBefore",
        "w:framePr",
        "w:widowControl",
        "w:numPr",
        "w:suppressLineNumbers",
        "w:pBdr",
        "w:shd",
        "w:tabs",
        "w:suppressAutoHyphens",
        "w:kinsoku",
        "w:wordWrap",
        "w:overflowPunct",
        "w:topLinePunct",
        "w:autoSpaceDE",
        "w:autoSpaceDN",
        "w:bidi",
        "w:adjustRightInd",
        "w:snapToGrid",
        "w:spacing",
        "w:ind",
        "w:contextualSpacing",
        "w:mirrorIndents",
        "w:suppressOverlap",
        "w:jc",
        "w:textDirection",
        "w:textAlignment",
        "w:textboxTightWrap",
        "w:outlineLvl",
        "w:divId",
        "w:cnfStyle",
        "w:rPr",
        "w:sectPr",
        "w:pPrChange",
    )
)

TBLPR_ORDER = tuple(
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
        "w:tblPrChange",
    )
)

CELLMAR_ORDER = tuple(
    qn(tag)
    for tag in ("w:top", "w:start", "w:left", "w:bottom", "w:end", "w:right")
)

BORDER_TAGS = (
    "w:top",
    "w:left",
    "w:bottom",
    "w:right",
    "w:insideH",
    "w:insideV",
)

TEXT_NODE_SKIP_TAGS = frozenset(
    {
        W_PPR,
        W_P,
        W_TXBX_CONTENT,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_INSTR_TEXT,
        W_FLD_CHAR,
        W_DEL,
        W_MOVE_FROM,
        W_DEL_TEXT,
    }
)

PARAGRAPH_TEXT_SKIP_TAGS = TEXT_NODE_SKIP_TAGS

IMAGE_CAPTION_STYLES = frozenset({"imagecaption"})
TABLE_CAPTION_STYLES = frozenset({"tablecaption"})
GENERIC_CAPTION_STYLES = frozenset({"caption"})
HEADING1_STYLES = frozenset({"heading1"})

ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}


class FormatFiguresError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass
class FormatReport:
    """Ringkasan pekerjaan yang dilakukan beserta peringatan yang muncul."""

    heading1_count: int = 0
    bab_headings: int = 0
    image_captions: int = 0
    table_captions: int = 0
    skipped_no_chapter: int = 0
    skipped_field: int = 0
    image_paragraphs: int = 0
    images_clamped: int = 0
    tables: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "heading1_count": self.heading1_count,
            "bab_headings": self.bab_headings,
            "image_captions": self.image_captions,
            "table_captions": self.table_captions,
            "skipped_no_chapter": self.skipped_no_chapter,
            "skipped_field": self.skipped_field,
            "image_paragraphs": self.image_paragraphs,
            "images_clamped": self.images_clamped,
            "tables": self.tables,
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
                raise FormatFiguresError(
                    f"{docx_path} bukan DOCX valid: part {DOCUMENT_PART} tidak ada."
                ) from exc
    except FileNotFoundError as exc:
        raise FormatFiguresError(f"File input tidak ditemukan: {docx_path}") from exc
    except zipfile.BadZipFile as exc:
        raise FormatFiguresError(
            f"{docx_path} bukan arsip DOCX/ZIP yang valid."
        ) from exc
    except OSError as exc:
        raise FormatFiguresError(f"Tidak dapat membaca {docx_path}: {exc}") from exc


def _parse_document(document_xml: bytes) -> tuple[_Element, _Element]:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    try:
        root = etree.fromstring(document_xml, parser)
    except etree.XMLSyntaxError as exc:
        raise FormatFiguresError(
            f"XML {DOCUMENT_PART} tidak valid: {exc}"
        ) from exc

    body = root.find(W_BODY)
    if body is None:
        raise FormatFiguresError(f"{DOCUMENT_PART} tidak memiliki elemen w:body.")
    return root, body


def _write_docx(input_path: Path, output_path: Path, document_xml: bytes) -> None:
    """Tulis DOCX baru dengan mengganti document.xml saja.

    Semua part lain disalin dari ZIP asli tanpa parsing ulang agar header,
    footer, footnote, style, numbering, media, dan relasi tetap identik.
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
# Utilitas XML


def _normalize_style_id(style_id: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (style_id or "").lower())


def _paragraph_style_id(paragraph: _Element) -> str | None:
    style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
    if style is None:
        return None
    return style.get(W_VAL)


def _get_or_add_ppr(paragraph: _Element) -> _Element:
    ppr = paragraph.find(W_PPR)
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        paragraph.insert(0, ppr)
    return ppr


def _insert_ordered(
    parent: _Element, element: _Element, order: Sequence[str]
) -> None:
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


def _get_or_add_child(
    parent: _Element, nsptag: str, order: Sequence[str]
) -> _Element:
    tag = qn(nsptag)
    existing = parent.find(tag)
    if existing is not None:
        return existing
    element = OxmlElement(nsptag)
    _insert_ordered(parent, element, order)
    return element


def _remove_direct_children(parent: _Element, tag: str) -> None:
    for child in parent.findall(tag):
        parent.remove(child)


def _set_text(node: _Element, text: str) -> None:
    node.text = text
    if text != text.strip():
        node.set(XML_SPACE, "preserve")


# ---------------------------------------------------------------------------
# Teks paragraf


def _caption_text_nodes(paragraph: _Element) -> list[_Element]:
    """Node w:t milik paragraf ini, tanpa isi paragraf bersarang/gambar."""

    nodes: list[_Element] = []

    def walk(element: _Element) -> None:
        for child in element:
            tag = child.tag
            if tag == W_T:
                nodes.append(child)
            elif tag in TEXT_NODE_SKIP_TAGS:
                continue
            else:
                walk(child)

    walk(paragraph)
    return nodes


def _caption_text(paragraph: _Element) -> str:
    return "".join(node.text or "" for node in _caption_text_nodes(paragraph))


def _paragraph_text(paragraph: _Element) -> str:
    """Teks paragraf untuk deteksi Heading1 (tab/line break ikut dipetakan)."""

    parts: list[str] = []

    def walk(element: _Element) -> None:
        for child in element:
            tag = child.tag
            if tag == W_T:
                parts.append(child.text or "")
            elif tag in (W_TAB, W_PTAB):
                parts.append("\t")
            elif tag in (W_BR, W_CR):
                parts.append("\n")
            elif tag == W_NO_BREAK_HYPHEN:
                parts.append("\u2011")
            elif tag in PARAGRAPH_TEXT_SKIP_TAGS:
                continue
            else:
                walk(child)

    walk(paragraph)
    return "".join(parts)


def _field_ranges(paragraph: _Element) -> list[tuple[int, int]]:
    """Rentang offset teks yang ditempati field (fldSimple atau fldChar)."""

    ranges: list[tuple[int, int]] = []
    stack: list[int] = []
    offset = 0

    def walk(element: _Element) -> None:
        nonlocal offset
        for child in element:
            tag = child.tag
            if tag == W_FLD_SIMPLE:
                start = offset
                stack.append(start)
                walk(child)
                start = stack.pop()
                if offset > start:
                    ranges.append((start, offset))
            elif tag == W_FLD_CHAR:
                field_type = child.get(W_FLD_CHAR_TYPE)
                if field_type == "begin":
                    stack.append(offset)
                elif field_type == "end" and stack:
                    start = stack.pop()
                    if offset > start:
                        ranges.append((start, offset))
            elif tag == W_T:
                offset += len(child.text or "")
            elif tag in TEXT_NODE_SKIP_TAGS:
                continue
            else:
                walk(child)

    walk(paragraph)
    return ranges


def _prefix_overlaps_field(
    match_end: int, ranges: Sequence[tuple[int, int]]
) -> bool:
    for start, end in ranges:
        if end <= start:
            continue
        if start < match_end and end > 0:
            return True
        # match_end == 0 berarti kita akan menyisipkan prefix di awal. Jangan
        # menyisipkan ke dalam hasil field yang memang mulai di offset 0.
        if match_end == 0 and start == 0 and end > 0:
            return True
    return False


def _replace_caption_prefix(
    paragraph: _Element,
    text: str,
    match_end: int,
    new_prefix: str,
) -> bool:
    """Hapus prefix lama dan sisipkan prefix baru tanpa merusak run/rPr."""

    nodes = _caption_text_nodes(paragraph)
    if not nodes:
        return False

    match_end = min(max(match_end, 0), len(text))
    offset = 0
    for node in nodes:
        node_text = node.text or ""
        start = offset
        end = start + len(node_text)
        if end <= match_end:
            if node_text:
                _set_text(node, "")
        elif start < match_end:
            _set_text(node, node_text[match_end - start :])
        else:
            break
        offset = end

    remaining = "".join(node.text or "" for node in nodes)
    insertion = new_prefix + (" " if remaining else "")
    first_text = nodes[0].text or ""
    _set_text(nodes[0], insertion + first_text)
    return True


# ---------------------------------------------------------------------------
# Caption


def _roman_to_int(token: str) -> int | None:
    total = 0
    previous = 0
    for character in reversed(token.upper()):
        value = ROMAN_VALUES.get(character)
        if value is None:
            return None
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total or None


def _chapter_number(text: str) -> int | None:
    match = BAB_RE.match(text)
    if match is not None:
        token = match.group("number")
        if token.isdigit():
            return int(token)
        return _roman_to_int(token)

    # Proposal memakai Heading1 bernomor arab, mis. "1. PENDAHULUAN".
    # Lookahead menolak subbab seperti "1.1 Latar Belakang" agar tidak
    # dianggap sebagai nomor bab.
    match = ARABIC_CHAPTER_RE.match(text)
    if match is not None:
        return int(match.group("number"))
    return None


def _caption_kind(style_id: str | None, text: str) -> str | None:
    normalized = _normalize_style_id(style_id)
    if normalized in IMAGE_CAPTION_STYLES:
        return "image"
    if normalized in TABLE_CAPTION_STYLES:
        return "table"
    if normalized in GENERIC_CAPTION_STYLES:
        match = CAPTION_LABEL_RE.match(text)
        if match is not None:
            return "image" if match.group(1).lower() == "gambar" else "table"
    return None


def _process_captions(body: _Element, report: FormatReport) -> None:
    current_chapter: int | None = None
    counters = {"image": 0, "table": 0}

    for paragraph in body.iter(W_P):
        style_id = _paragraph_style_id(paragraph)

        if _normalize_style_id(style_id) in HEADING1_STYLES:
            report.heading1_count += 1
            chapter = _chapter_number(_paragraph_text(paragraph))
            if chapter is not None:
                report.bab_headings += 1
                current_chapter = chapter
                counters = {"image": 0, "table": 0}
            continue

        text = _caption_text(paragraph)
        kind = _caption_kind(style_id, text)
        if kind is None or not text.strip():
            continue

        if current_chapter is None:
            report.skipped_no_chapter += 1
            continue

        counters[kind] += 1
        label = "Gambar" if kind == "image" else "Tabel"
        new_prefix = f"{label} {current_chapter}.{counters[kind]}"

        match = CAPTION_PREFIX_RE.match(text)
        match_end = match.end() if match is not None else 0

        if _prefix_overlaps_field(match_end, _field_ranges(paragraph)):
            report.skipped_field += 1
            continue

        if not _replace_caption_prefix(paragraph, text, match_end, new_prefix):
            continue

        if kind == "image":
            report.image_captions += 1
        else:
            report.table_captions += 1


# ---------------------------------------------------------------------------
# Gambar


def _int_attribute(element: _Element, name: str) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _scale_extent(element: _Element, ratio: float) -> None:
    cx = _int_attribute(element, "cx")
    cy = _int_attribute(element, "cy")
    if cx is not None and cx > 0:
        element.set("cx", str(max(1, int(round(cx * ratio)))))
    if cy is not None and cy > 0:
        element.set("cy", str(max(1, int(round(cy * ratio)))))


def _clamp_container(container: _Element) -> bool:
    extent = container.find(WP_EXTENT)
    if extent is None:
        return False

    cx = _int_attribute(extent, "cx")
    cy = _int_attribute(extent, "cy")
    if cx is None or cx <= MAX_IMAGE_WIDTH_EMU:
        return False

    ratio = MAX_IMAGE_WIDTH_EMU / cx
    extent.set("cx", str(MAX_IMAGE_WIDTH_EMU))
    if cy is not None and cy > 0:
        extent.set("cy", str(max(1, int(round(cy * ratio)))))

    # Jaga agar transformasi gambar di pic:spPr tetap sebanding dengan
    # ukuran tampilan (wp:extent).
    for picture in container.findall(f".//{PIC_PIC}"):
        transform_extent = picture.find(f"{PIC_SPPR}/{A_XFRM}/{A_EXT}")
        if transform_extent is not None:
            _scale_extent(transform_extent, ratio)
    return True


def _set_image_paragraph_properties(paragraph: _Element) -> None:
    ppr = _get_or_add_ppr(paragraph)

    spacing = _get_or_add_child(ppr, "w:spacing", PPR_ORDER)
    spacing.set(W_BEFORE, "0")
    spacing.set(W_AFTER, "0")
    for attribute in (
        W_BEFORE_LINES,
        W_AFTER_LINES,
        W_BEFORE_AUTO,
        W_AFTER_AUTO,
    ):
        if spacing.get(attribute) is not None:
            spacing.set(attribute, "0")

    justification = _get_or_add_child(ppr, "w:jc", PPR_ORDER)
    justification.set(W_VAL, "center")


def _format_images(body: _Element, report: FormatReport) -> None:
    for paragraph in body.iter(W_P):
        drawings = list(paragraph.iter(W_DRAWING))
        if not drawings:
            continue

        report.image_paragraphs += 1
        _set_image_paragraph_properties(paragraph)

        for drawing in drawings:
            containers = list(drawing.findall(WP_INLINE))
            containers.extend(drawing.findall(WP_ANCHOR))
            for container in containers:
                if _clamp_container(container):
                    report.images_clamped += 1


# ---------------------------------------------------------------------------
# Tabel


def _get_or_add_tbl_pr(table: _Element) -> _Element:
    tbl_pr = table.find(W_TBL_PR)
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        table.insert(0, tbl_pr)
    return tbl_pr


def _set_table_borders(tbl_pr: _Element) -> None:
    existing = tbl_pr.find(W_TBL_BORDERS)
    if existing is not None:
        tbl_pr.remove(existing)

    borders = _get_or_add_child(tbl_pr, "w:tblBorders", TBLPR_ORDER)
    for tag in BORDER_TAGS:
        border = OxmlElement(tag)
        border.set(W_VAL, "single")
        border.set(W_SZ, "4")
        border.set(W_SPACE, "0")
        border.set(W_COLOR, "000000")
        borders.append(border)


def _set_cell_margins(tbl_pr: _Element) -> None:
    cell_margins = _get_or_add_child(tbl_pr, "w:tblCellMar", TBLPR_ORDER)
    for tag, value in (
        ("w:top", 108),
        ("w:left", 0),
        ("w:bottom", 108),
        ("w:right", 0),
    ):
        margin = _get_or_add_child(cell_margins, tag, CELLMAR_ORDER)
        margin.set(W_W, str(value))
        margin.set(W_TYPE, "dxa")


def _format_table(table: _Element) -> None:
    tbl_pr = _get_or_add_tbl_pr(table)

    _remove_direct_children(tbl_pr, W_SHD)
    _set_table_borders(tbl_pr)
    _set_cell_margins(tbl_pr)

    for row in table.findall(W_TR):
        table_exception = row.find(W_TBL_PR_EX)
        if table_exception is not None:
            _remove_direct_children(table_exception, W_TBL_BORDERS)
            _remove_direct_children(table_exception, W_SHD)
            _remove_direct_children(table_exception, W_TBL_CELL_MAR)

        row_properties = row.find(W_TR_PR)
        if row_properties is not None:
            _remove_direct_children(row_properties, W_SHD)

        for cell in row.findall(W_TC):
            cell_properties = cell.find(W_TC_PR)
            if cell_properties is None:
                continue
            _remove_direct_children(cell_properties, W_SHD)
            _remove_direct_children(cell_properties, W_TC_BORDERS)
            _remove_direct_children(cell_properties, W_TC_MAR)


def _format_tables(body: _Element, report: FormatReport) -> None:
    for table in body.iter(W_TBL):
        _format_table(table)
        report.tables += 1


# ---------------------------------------------------------------------------
# Analisis dan API


def _add_warnings(report: FormatReport) -> None:
    if report.bab_headings == 0:
        if report.heading1_count == 0:
            report.warnings.append(
                "Tidak ada paragraf Heading1; penomoran caption dilewati."
            )
        else:
            report.warnings.append(
                "Tidak ada Heading1 berformat 'BAB <romawi/arab>' atau "
                "'<nomor arab>. <judul>'; penomoran caption dilewati."
            )
    elif report.skipped_no_chapter:
        report.warnings.append(
            f"{report.skipped_no_chapter} caption sebelum bab pertama "
            "dilewati (belum ada nomor bab)."
        )

    if report.skipped_field:
        report.warnings.append(
            f"{report.skipped_field} caption dilewati karena prefix nomornya "
            "memuat field; field dibiarkan utuh."
        )


def format_figures(
    docx_path: str | Path, out_docx: str | Path
) -> FormatReport:
    """Post-process caption, gambar, dan tabel dari ``docx_path`` ke ``out_docx``."""

    input_path = Path(docx_path)
    output_path = Path(out_docx)

    document_xml = _read_document_xml(input_path)
    root, body = _parse_document(document_xml)

    report = FormatReport()
    _format_tables(body, report)
    _format_images(body, report)
    _process_captions(body, report)
    _add_warnings(report)

    revised_xml = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    _write_docx(input_path, output_path, revised_xml)
    return report


def _summary(report: FormatReport) -> str:
    lines = [
        f"Caption gambar bernomor: {report.image_captions}",
        f"Caption tabel bernomor: {report.table_captions}",
        f"Paragraf gambar dirapikan: {report.image_paragraphs} "
        f"({report.images_clamped} gambar di-clamp)",
        f"Tabel diformat: {report.tables}",
        f"Bab terdeteksi: {report.bab_headings}",
    ]
    if report.skipped_no_chapter:
        lines.append(f"Caption tanpa bab: {report.skipped_no_chapter}")
    if report.skipped_field:
        lines.append(f"Caption dengan prefix field: {report.skipped_field}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Post-process caption, gambar, dan tabel DOCX: nomor caption per "
            "bab, clamp gambar 14 cm, dan seragamkan border/margin tabel."
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
        report = format_figures(args.docx, args.out)
    except (FormatFiguresError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_summary(report))
    for warning in report.warnings:
        print(f"PERINGATAN: {warning}", file=sys.stderr)
    print(f"DOCX: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
