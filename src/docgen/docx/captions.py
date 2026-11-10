"""Helper caption DOCX: teks, field, nomor bab, anchor, dan gambar.

Semua operasi berjalan pada elemen ``word/document.xml`` yang diberikan
``DocumentPackage``. Stage ``captions/figures`` memakai modul ini untuk
memastikan caption wajib, memberi nomor ``Gambar bab.n``/``Tabel bab.n``,
memindahkan caption ke sisi yang benar, dan menormalkan paragraf gambar.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from lxml import etree

from . import DocxError, names
from .package import DOCUMENT_PART
from .tables import is_code_table
from .xml import (
    PPR_ORDER,
    RPR_ORDER,
    ensure_ppr,
    ensure_rpr,
    get_or_add,
    paragraph_text,
    qn,
)

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from .package import DocumentPackage


class CaptionError(DocxError):
    """Caption hilang, anchor tidak valid, atau konflik nomor."""

    default_code = "CAPTION"

    def __init__(
        self,
        message: str,
        *,
        missing: Sequence[str] = (),
        **kwargs: object,
    ) -> None:
        super().__init__(message, **kwargs)  # type: ignore[arg-type]
        self.missing = tuple(missing)


class CaptionKind(Enum):
    FIGURE = "figure"
    TABLE = "table"


@dataclass(frozen=True)
class Caption:
    kind: CaptionKind
    paragraph: etree._Element
    anchor: etree._Element
    number: str
    text: str


@dataclass(frozen=True)
class CaptionFontSpec:
    family: str = "Times New Roman"
    size_half_points: int = 20
    bold: bool = False
    italic: bool = False
    color: str = "000000"
    space_before: int = 0
    space_after: int = 0
    line_spacing: float = 1.0


@dataclass(frozen=True)
class CaptionSpec:
    label: str
    separator: str = " "
    alignment: str = "left"
    keep_next: bool = False
    font: CaptionFontSpec = field(default_factory=CaptionFontSpec)


FIGURE_CAPTION_SPEC = CaptionSpec(
    label="Gambar",
    alignment="center",
    keep_next=False,
)
TABLE_CAPTION_SPEC = CaptionSpec(
    label="Tabel",
    alignment="left",
    keep_next=True,
)


@dataclass(frozen=True)
class CaptionSpecs:
    figure: CaptionSpec = FIGURE_CAPTION_SPEC
    table: CaptionSpec = TABLE_CAPTION_SPEC

    def for_kind(self, kind: CaptionKind) -> CaptionSpec:
        return self.figure if kind is CaptionKind.FIGURE else self.table


@dataclass(frozen=True)
class FigureLayoutSpec:
    caption_alignment: str = "center"
    image_alignment: str = "center"
    numbering: str = "chapter"
    space_before: int = 0
    space_after: int = 0
    first_line_indent: int = 0


@dataclass
class CaptionReport:
    heading1_count: int = 0
    bab_headings: int = 0
    image_captions: int = 0
    table_captions: int = 0
    created_image_captions: int = 0
    created_table_captions: int = 0
    skipped_no_chapter: int = 0
    skipped_field: int = 0
    image_paragraphs: int = 0
    images_clamped: int = 0
    tables: int = 0
    missing_captions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changed: bool = False


EMU_PER_CM = 360_000
MAX_IMAGE_WIDTH_EMU = 14 * EMU_PER_CM

CAPTION_PREFIX_RE = re.compile(
    r"^\s*(Gambar|Tabel)\s+\d+(?:\.\d+)?\.?\s*",
    re.IGNORECASE,
)
CAPTION_LABEL_RE = re.compile(r"^\s*(Gambar|Tabel)\b", re.IGNORECASE)
_LABEL_PREFIX_RE = re.compile(r"^\s*(Gambar|Tabel)\b[ \t]*", re.IGNORECASE)
BAB_RE = re.compile(
    r"^\s*BAB\s+(?P<number>[IVXLCDM]+|\d+)(?=\s|[.:;,\-\u2013\u2014]|$)",
    re.IGNORECASE,
)
ARABIC_CHAPTER_RE = re.compile(r"^\s*(?P<number>\d+)(?!\.\d)[\.\s]+")

ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

W_BODY = names.W_BODY
W_P = names.W_P
W_PPR = names.W_PPR
W_PSTYLE = names.W_PSTYLE
W_VAL = names.W_VAL
W_T = names.W_T
W_TAB = names.W_TAB
W_PTAB = names.W_PTAB
W_BR = names.W_BR
W_CR = names.W_CR
W_NO_BREAK_HYPHEN = names.W_NO_BREAK_HYPHEN
W_INSTR_TEXT = names.W_INSTRTEXT
W_FLD_CHAR = names.W_FLDCHAR
W_FLD_CHAR_TYPE = names.W_FLDCHARTYPE
W_FLD_SIMPLE = names.W_FLDSIMPLE
W_DEL = names.W_DEL
W_MOVE_FROM = names.W_MOVEFROM
W_DEL_TEXT = names.W_DELTEXT
W_DRAWING = names.W_DRAWING
W_PICT = names.W_PICT
W_OBJECT = names.W_OBJECT
W_TXBX_CONTENT = names.W_TXBXCONTENT
W_SECTPR = names.W_SECTPR
W_TBL = names.W_TBL
W_R = names.W_R
W_SPACING = qn("w:spacing")
W_JC = qn("w:jc")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_BEFORE_LINES = qn("w:beforeLines")
W_AFTER_LINES = qn("w:afterLines")
W_BEFORE_AUTO = qn("w:beforeAutospacing")
W_AFTER_AUTO = qn("w:afterAutospacing")
W_LINE = qn("w:line")
W_LINE_RULE = qn("w:lineRule")
W_KEEP_NEXT = qn("w:keepNext")
W_IND = qn("w:ind")
W_FIRST_LINE = qn("w:firstLine")
W_B = qn("w:b")
W_BCS = qn("w:bCs")
W_I = qn("w:i")
W_ICS = qn("w:iCs")
W_RFONTS = qn("w:rFonts")
W_SZ = qn("w:sz")
W_SZCS = qn("w:szCs")
W_COLOR = qn("w:color")
W_ASCII = qn("w:ascii")
W_HANSI = qn("w:hAnsi")
W_CS = qn("w:cs")
W_EAST_ASIA = qn("w:eastAsia")
W_TBL_CAPTION = qn("w:tblCaption")
WP_INLINE = qn("wp:inline")
WP_ANCHOR = qn("wp:anchor")
WP_EXTENT = qn("wp:extent")
WP_DOCPR = qn("wp:docPr")
PIC_PIC = qn("pic:pic")
PIC_SPPR = qn("pic:spPr")
A_XFRM = qn("a:xfrm")
A_EXT = qn("a:ext")
XML_SPACE = names.XML + "space"

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

NON_VISUAL_BODY_TAGS = frozenset(
    {
        names.W_BOOKMARK_START,
        names.W_BOOKMARK_END,
        qn("w:proofErr"),
        qn("w:commentRangeStart"),
        qn("w:commentRangeEnd"),
        qn("w:permStart"),
        qn("w:permEnd"),
    }
)

COVER_STYLE_PREFIX = "cover"


# ---------------------------------------------------------------------------
# Utilitas teks dan XML
# ---------------------------------------------------------------------------


def _body(package: DocumentPackage) -> etree._Element:
    root = package.xml(DOCUMENT_PART)
    body = root.find(W_BODY)
    if body is None:
        raise CaptionError(
            f"{DOCUMENT_PART} tidak memiliki elemen w:body",
            code="CAPTION-NO-BODY",
        )
    return body


def _set_text(node: etree._Element, text: str) -> None:
    node.text = text
    if text != text.strip():
        node.set(XML_SPACE, "preserve")


def _remove_direct_children(parent: etree._Element, tag: str) -> None:
    for child in parent.findall(tag):
        parent.remove(child)


def _paragraph_style_id(paragraph: etree._Element) -> str | None:
    properties = paragraph.find(W_PPR)
    if properties is None:
        return None
    style = properties.find(W_PSTYLE)
    if style is None:
        return None
    return style.get(W_VAL)


def _caption_text_nodes(paragraph: etree._Element) -> list[etree._Element]:
    """Node ``w:t`` milik paragraf ini, tanpa field/paragraf bersarang."""

    nodes: list[etree._Element] = []

    def walk(element: etree._Element) -> None:
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


def _caption_text(paragraph: etree._Element) -> str:
    return "".join(node.text or "" for node in _caption_text_nodes(paragraph))


def _field_ranges(paragraph: etree._Element) -> list[tuple[int, int]]:
    """Rentang offset teks yang ditempati field (``fldSimple``/``fldChar``)."""

    ranges: list[tuple[int, int]] = []
    stack: list[int] = []
    offset = 0

    def walk(element: etree._Element) -> None:
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
    match_end: int,
    ranges: Sequence[tuple[int, int]],
) -> bool:
    for start, end in ranges:
        if end <= start:
            continue
        if start < match_end and end > 0:
            return True
        if match_end == 0 and start == 0 and end > 0:
            return True
    return False


def _prefix_end(text: str) -> int:
    match = CAPTION_PREFIX_RE.match(text)
    if match is not None:
        return match.end()
    match = _LABEL_PREFIX_RE.match(text)
    return match.end() if match is not None else 0


def _caption_parts(text: str) -> tuple[str, str]:
    """Pisahkan caption menjadi ``(nomor, judul)`` tanpa prefix label."""

    match = CAPTION_PREFIX_RE.match(text)
    if match is not None:
        label = match.group(1)
        number = text[match.start(1) + len(label) : match.end()].strip()
        number = number.rstrip(".").strip()
        return number, text[match.end() :].strip()

    match = _LABEL_PREFIX_RE.match(text)
    if match is not None:
        return "", text[match.end() :].strip()
    return "", text.strip()


def _replace_caption_prefix(
    paragraph: etree._Element,
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


def _append_text(paragraph: etree._Element, text: str) -> None:
    run = etree.Element(W_R)
    text_node = etree.Element(W_T)
    _set_text(text_node, text)
    run.append(text_node)
    paragraph.append(run)


def _caption_kind(
    style_id: str | None,
    text: str,
) -> CaptionKind | None:
    normalized = names.normalize_style_id(style_id)
    if normalized == "imagecaption":
        return CaptionKind.FIGURE
    if normalized == "tablecaption":
        return CaptionKind.TABLE
    if normalized == "caption":
        match = CAPTION_LABEL_RE.match(text)
        if match is not None:
            return CaptionKind.FIGURE if match.group(1).lower() == "gambar" else CaptionKind.TABLE
    return None


def caption_style(kind: CaptionKind) -> str:
    """Nama style paragraf caption untuk jenis tertentu."""

    return "ImageCaption" if kind is CaptionKind.FIGURE else "TableCaption"


def is_caption_paragraph(
    paragraph: etree._Element,
    kind: CaptionKind | None = None,
) -> bool:
    """True bila paragraf adalah caption (opsional untuk jenis tertentu)."""

    if paragraph is None or paragraph.tag != W_P:
        return False
    style_id = _paragraph_style_id(paragraph)
    if not names.is_caption_style(style_id):
        return False
    if kind is None:
        return True
    normalized = names.normalize_style_id(style_id)
    if normalized == names.normalize_style_id(caption_style(kind)):
        return True
    if normalized != "caption":
        return False
    return _caption_kind(style_id, _caption_text(paragraph)) is kind


def _caption_from(
    kind: CaptionKind,
    paragraph: etree._Element,
    anchor: etree._Element,
) -> Caption:
    number, title = _caption_parts(_caption_text(paragraph))
    return Caption(
        kind=kind,
        paragraph=paragraph,
        anchor=anchor,
        number=number,
        text=title,
    )


# ---------------------------------------------------------------------------
# Format paragraf caption dan gambar
# ---------------------------------------------------------------------------


def _format_run(run: etree._Element, font: CaptionFontSpec) -> None:
    properties = ensure_rpr(run)

    fonts = get_or_add(properties, W_RFONTS, RPR_ORDER)
    for attribute in (W_ASCII, W_HANSI, W_CS, W_EAST_ASIA):
        fonts.set(attribute, font.family)

    for tag, enabled in (
        (W_B, font.bold),
        (W_BCS, font.bold),
        (W_I, font.italic),
        (W_ICS, font.italic),
    ):
        attribute = get_or_add(properties, tag, RPR_ORDER)
        attribute.set(W_VAL, "1" if enabled else "0")

    color = get_or_add(properties, W_COLOR, RPR_ORDER)
    color.set(W_VAL, font.color)

    for tag in (W_SZ, W_SZCS):
        size = get_or_add(properties, tag, RPR_ORDER)
        size.set(W_VAL, str(font.size_half_points))


def format_caption_paragraph(
    paragraph: etree._Element,
    kind: CaptionKind,
    spec: CaptionSpec | None = None,
) -> None:
    """Terapkan format caption final langsung pada paragraf dan run."""

    caption_spec = spec or (
        FIGURE_CAPTION_SPEC if kind is CaptionKind.FIGURE else TABLE_CAPTION_SPEC
    )
    font = caption_spec.font

    properties = ensure_ppr(paragraph)

    spacing = get_or_add(properties, W_SPACING, PPR_ORDER)
    spacing.set(W_BEFORE, str(font.space_before))
    spacing.set(W_AFTER, str(font.space_after))
    spacing.set(W_LINE, str(max(1, round(font.line_spacing * 240))))
    spacing.set(W_LINE_RULE, "auto")
    for attribute in (
        W_BEFORE_LINES,
        W_AFTER_LINES,
        W_BEFORE_AUTO,
        W_AFTER_AUTO,
    ):
        if spacing.get(attribute) is not None:
            spacing.set(attribute, "0")

    justification = get_or_add(properties, W_JC, PPR_ORDER)
    justification.set(W_VAL, caption_spec.alignment)

    if caption_spec.keep_next:
        keep_next = get_or_add(properties, W_KEEP_NEXT, PPR_ORDER)
        keep_next.attrib.pop(W_VAL, None)
    else:
        _remove_direct_children(properties, W_KEEP_NEXT)

    for run in paragraph.iter(W_R):
        _format_run(run, font)


def _set_image_paragraph_properties(
    paragraph: etree._Element,
    spec: FigureLayoutSpec,
) -> None:
    properties = ensure_ppr(paragraph)

    spacing = get_or_add(properties, W_SPACING, PPR_ORDER)
    spacing.set(W_BEFORE, str(spec.space_before))
    spacing.set(W_AFTER, str(spec.space_after))
    for attribute in (
        W_BEFORE_LINES,
        W_AFTER_LINES,
        W_BEFORE_AUTO,
        W_AFTER_AUTO,
    ):
        if spacing.get(attribute) is not None:
            spacing.set(attribute, "0")

    justification = get_or_add(properties, W_JC, PPR_ORDER)
    justification.set(W_VAL, spec.image_alignment)

    indentation = get_or_add(properties, W_IND, PPR_ORDER)
    indentation.set(W_FIRST_LINE, str(spec.first_line_indent))


def _int_attribute(element: etree._Element, name: str) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _scale_extent(element: etree._Element, ratio: float) -> None:
    cx = _int_attribute(element, "cx")
    cy = _int_attribute(element, "cy")
    if cx is not None and cx > 0:
        element.set("cx", str(max(1, round(cx * ratio))))
    if cy is not None and cy > 0:
        element.set("cy", str(max(1, round(cy * ratio))))


def _clamp_container(container: etree._Element) -> bool:
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
        extent.set("cy", str(max(1, round(cy * ratio))))

    for picture in container.findall(f".//{PIC_PIC}"):
        transform_extent = picture.find(f"{PIC_SPPR}/{A_XFRM}/{A_EXT}")
        if transform_extent is not None:
            _scale_extent(transform_extent, ratio)
    return True


def format_images(
    package: DocumentPackage,
    *,
    spec: FigureLayoutSpec | None = None,
) -> tuple[int, int]:
    """Rapikan paragraf gambar dan clamp lebar; kembalikan ``(jumlah, clamp)``."""

    layout = spec or FigureLayoutSpec()
    image_paragraphs = 0
    images_clamped = 0

    for paragraph in _body(package).iter(W_P):
        drawings = list(paragraph.iter(W_DRAWING))
        if not drawings:
            continue

        image_paragraphs += 1
        _set_image_paragraph_properties(paragraph, layout)

        for drawing in drawings:
            containers = list(drawing.findall(WP_INLINE))
            containers.extend(drawing.findall(WP_ANCHOR))
            for container in containers:
                if _clamp_container(container):
                    images_clamped += 1

    return image_paragraphs, images_clamped


def _style_is_cover(style_id: str | None) -> bool:
    return names.normalize_style_id(style_id).startswith(COVER_STYLE_PREFIX)


def iter_image_paragraphs(
    package: DocumentPackage,
) -> tuple[etree._Element, ...]:
    """Paragraf body bergambar yang wajib memiliki caption (kecuali cover)."""

    paragraphs: list[etree._Element] = []
    for paragraph in _body(package).iter(W_P):
        if not list(paragraph.iter(W_DRAWING)):
            continue
        if _style_is_cover(_paragraph_style_id(paragraph)):
            continue
        paragraphs.append(paragraph)
    return tuple(paragraphs)


def image_alt_text(paragraph: etree._Element) -> str:
    """Ambil alt text ``wp:docPr`` pertama yang tidak kosong."""

    for drawing in paragraph.iter(W_DRAWING):
        for doc_pr in drawing.iter(WP_DOCPR):
            for attribute in ("descr", "title"):
                value = doc_pr.get(attribute)
                if value and value.strip():
                    return value.strip()
    return ""


# ---------------------------------------------------------------------------
# Caption wajib
# ---------------------------------------------------------------------------


def _is_empty_layout_paragraph(paragraph: etree._Element) -> bool:
    """Paragraf kosong murni yang boleh dihapus untuk menutup jarak caption."""

    if paragraph.tag != W_P:
        return False
    if names.is_caption_style(_paragraph_style_id(paragraph)):
        # Placeholder caption kosong harus diisi, bukan dihapus.
        return False
    if paragraph.find(f".//{W_SECTPR}") is not None:
        return False
    for tag in NON_VISUAL_BODY_TAGS:
        if paragraph.find(f".//{tag}") is not None:
            return False
    for tag in (
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_FLD_SIMPLE,
        W_FLD_CHAR,
        W_INSTR_TEXT,
    ):
        if paragraph.find(f".//{tag}") is not None:
            return False
    for run in paragraph.iter(W_R):
        for child in run.iter():
            if child.tag in (W_TAB, W_PTAB, W_BR, W_CR, W_NO_BREAK_HYPHEN):
                return False
    return not _caption_text(paragraph).strip()


def _previous_meaningful_sibling(
    element: etree._Element,
) -> tuple[etree._Element | None, list[etree._Element]]:
    empties: list[etree._Element] = []
    sibling = element.getprevious()
    while sibling is not None:
        if sibling.tag in NON_VISUAL_BODY_TAGS:
            sibling = sibling.getprevious()
            continue
        if _is_empty_layout_paragraph(sibling):
            empties.append(sibling)
            sibling = sibling.getprevious()
            continue
        break
    return sibling, empties


def _next_meaningful_sibling(
    element: etree._Element,
) -> tuple[etree._Element | None, list[etree._Element]]:
    empties: list[etree._Element] = []
    sibling = element.getnext()
    while sibling is not None:
        if sibling.tag in NON_VISUAL_BODY_TAGS:
            sibling = sibling.getnext()
            continue
        if _is_empty_layout_paragraph(sibling):
            empties.append(sibling)
            sibling = sibling.getnext()
            continue
        break
    return sibling, empties


def _remove_elements(elements: Sequence[etree._Element]) -> None:
    for element in elements:
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)


def table_caption_text(table: etree._Element) -> str:
    """Caption sumber Pandoc dari ``w:tblCaption``, atau string kosong."""

    table_properties = table.find(names.W_TBLPR)
    if table_properties is None:
        return ""
    caption = table_properties.find(W_TBL_CAPTION)
    if caption is None:
        return ""
    return (caption.get(W_VAL) or "").strip()


def _table_caption_candidate(
    table: etree._Element,
) -> tuple[etree._Element, list[etree._Element], str] | None:
    before, before_empties = _previous_meaningful_sibling(table)
    if is_caption_paragraph(before, CaptionKind.TABLE):
        assert before is not None
        return before, before_empties, "above"

    after, after_empties = _next_meaningful_sibling(table)
    if is_caption_paragraph(after, CaptionKind.TABLE):
        assert after is not None
        following, _ = _next_meaningful_sibling(after)
        # Caption yang langsung diikuti tabel lain lebih mungkin milik tabel
        # berikutnya, bukan caption bawah tabel ini.
        if following is None or following.tag != W_TBL:
            return after, after_empties, "below"
    return None


def _figure_caption_candidate(
    paragraph: etree._Element,
) -> tuple[etree._Element, list[etree._Element], str] | None:
    after, after_empties = _next_meaningful_sibling(paragraph)
    if is_caption_paragraph(after, CaptionKind.FIGURE):
        assert after is not None
        return after, after_empties, "below"

    before, before_empties = _previous_meaningful_sibling(paragraph)
    if is_caption_paragraph(before, CaptionKind.FIGURE):
        assert before is not None
        previous_object, _ = _previous_meaningful_sibling(before)
        belongs_to_previous_image = (
            previous_object is not None
            and previous_object.tag == W_P
            and bool(list(previous_object.iter(W_DRAWING)))
        )
        if not belongs_to_previous_image:
            return before, before_empties, "above"
    return None


def _fill_empty_caption(paragraph: etree._Element, text: str) -> bool:
    """Isi caption kosong tanpa menyentuh field/bookmark yang sudah ada."""

    if _caption_text(paragraph).strip():
        return False
    nodes = _caption_text_nodes(paragraph)
    if nodes:
        _set_text(nodes[0], text)
        for node in nodes[1:]:
            _set_text(node, "")
        return True

    _append_text(paragraph, text)
    return True


def _make_caption_paragraph(kind: CaptionKind, text: str) -> etree._Element:
    paragraph = etree.Element(W_P)

    properties = etree.Element(W_PPR)
    style = etree.Element(W_PSTYLE)
    style.set(W_VAL, caption_style(kind))
    properties.append(style)
    paragraph.append(properties)

    _append_text(paragraph, text)
    return paragraph


def find_caption(
    package: DocumentPackage,
    *,
    kind: CaptionKind,
    anchor: etree._Element,
) -> Caption | None:
    """Cari caption yang sudah menempel pada anchor, tanpa membuat baru."""

    if kind is CaptionKind.TABLE:
        candidate = _table_caption_candidate(anchor)
    else:
        candidate = _figure_caption_candidate(anchor)
    if candidate is None:
        return None
    paragraph, _, _ = candidate
    return _caption_from(kind, paragraph, anchor)


def _caption_candidate(
    kind: CaptionKind,
    anchor: etree._Element,
) -> tuple[etree._Element, list[etree._Element], str] | None:
    if kind is CaptionKind.TABLE:
        if anchor.tag != W_TBL:
            raise CaptionError(
                "anchor caption tabel harus elemen w:tbl",
                code="CAPTION-ANCHOR",
            )
        if is_code_table(anchor):
            raise CaptionError(
                "tabel kode tidak boleh diberi caption tabel data",
                code="CAPTION-CODE-TABLE",
            )
        return _table_caption_candidate(anchor)
    if anchor.tag != W_P:
        raise CaptionError(
            "anchor caption gambar harus paragraf bergambar",
            code="CAPTION-ANCHOR",
        )
    return _figure_caption_candidate(anchor)


def _move_caption(
    kind: CaptionKind,
    anchor: etree._Element,
    paragraph: etree._Element,
    side: str,
) -> None:
    move = (kind is CaptionKind.TABLE and side == "below") or (
        kind is CaptionKind.FIGURE and side == "above"
    )
    if not move:
        return
    parent = paragraph.getparent()
    if parent is not None:
        parent.remove(paragraph)
    if kind is CaptionKind.TABLE:
        anchor.addprevious(paragraph)
    else:
        anchor.addnext(paragraph)


def ensure_caption(
    package: DocumentPackage,
    *,
    kind: CaptionKind,
    anchor: etree._Element,
    text: str,
) -> Caption:
    """Pastikan anchor memiliki caption; pakai teks sumber bila masih kosong."""

    source = (text or "").strip()
    candidate = _caption_candidate(kind, anchor)

    if candidate is not None:
        paragraph, empties, side = candidate
        if not _caption_text(paragraph).strip() and source:
            _fill_empty_caption(paragraph, source)
        if not _caption_text(paragraph).strip():
            raise CaptionError(
                "caption kosong dan tidak ada teks sumber",
                code="CAPTION-MISSING",
            )
        _remove_elements(empties)
        _move_caption(kind, anchor, paragraph, side)
        return _caption_from(kind, paragraph, anchor)

    if not source:
        raise CaptionError(
            "tidak ada caption dan tidak ada teks sumber",
            code="CAPTION-MISSING",
        )

    paragraph = _make_caption_paragraph(kind, source)
    if kind is CaptionKind.TABLE:
        anchor.addprevious(paragraph)
    else:
        anchor.addnext(paragraph)
    return _caption_from(kind, paragraph, anchor)


# ---------------------------------------------------------------------------
# Nomor dan iterasi caption
# ---------------------------------------------------------------------------


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
    # Lookahead menolak subbab seperti "1.1 Latar Belakang".
    match = ARABIC_CHAPTER_RE.match(text)
    if match is not None:
        return int(match.group("number"))
    return None


def _anchor_for_caption(
    kind: CaptionKind,
    caption: etree._Element,
) -> etree._Element | None:
    """Temukan tabel/gambar yang menjadi anchor paragraf caption."""

    if kind is CaptionKind.TABLE:
        after, _ = _next_meaningful_sibling(caption)
        if after is not None and after.tag == W_TBL:
            return after
        before, _ = _previous_meaningful_sibling(caption)
        if before is not None and before.tag == W_TBL:
            return before
        return None

    before, _ = _previous_meaningful_sibling(caption)
    if before is not None and before.tag == W_P and bool(list(before.iter(W_DRAWING))):
        return before
    after, _ = _next_meaningful_sibling(caption)
    if after is not None and after.tag == W_P and bool(list(after.iter(W_DRAWING))):
        return after
    return None


def iter_captions(package: DocumentPackage) -> tuple[Caption, ...]:
    """Iterasi caption body beserta anchor dan nomor yang terbaca."""

    captions: list[Caption] = []
    for paragraph in _body(package).iter(W_P):
        text = _caption_text(paragraph)
        kind = _caption_kind(_paragraph_style_id(paragraph), text)
        if kind is None or not text.strip():
            continue
        anchor = _anchor_for_caption(kind, paragraph)
        if anchor is None:
            continue
        captions.append(_caption_from(kind, paragraph, anchor))
    return tuple(captions)


def set_caption(
    package: DocumentPackage,
    caption: Caption,
    *,
    text: str,
    number: str,
    spec: CaptionSpecs | None = None,
) -> None:
    """Tulis ulang caption menjadi ``label nomor judul``."""

    specs = spec or CaptionSpecs()
    caption_spec = specs.for_kind(caption.kind)
    label = caption_spec.label
    separator = caption_spec.separator
    prefix = f"{label}{separator}{number}" if number else label
    desired = f"{prefix} {text}".strip()

    paragraph = caption.paragraph
    current = _caption_text(paragraph)
    match_end = _prefix_end(current)
    if _prefix_overlaps_field(match_end, _field_ranges(paragraph)):
        raise CaptionError(
            "caption memuat field pada prefix; field dibiarkan utuh",
            code="CAPTION-FIELD",
        )

    if current.strip() == desired:
        return

    nodes = _caption_text_nodes(paragraph)
    if not nodes:
        _append_text(paragraph, desired)
        return
    _set_text(nodes[0], desired)
    for node in nodes[1:]:
        _set_text(node, "")


def _heading_chapter(
    paragraph: etree._Element,
    report: CaptionReport,
    scope: str,
    counters: dict[CaptionKind, int],
) -> int | None:
    report.heading1_count += 1
    chapter = _chapter_number(paragraph_text(paragraph))
    if chapter is not None:
        report.bab_headings += 1
        if scope == "chapter":
            counters[CaptionKind.FIGURE] = 0
            counters[CaptionKind.TABLE] = 0
    return chapter


def _number_caption(
    paragraph: etree._Element,
    style_id: str | None,
    *,
    current_chapter: int | None,
    counters: dict[CaptionKind, int],
    scope: str,
    specs: CaptionSpecs,
    report: CaptionReport,
) -> None:
    text = _caption_text(paragraph)
    kind = _caption_kind(style_id, text)
    if kind is None or not text.strip():
        return

    caption_spec = specs.for_kind(kind)
    format_caption_paragraph(paragraph, kind, caption_spec)

    if scope == "chapter" and current_chapter is None:
        report.skipped_no_chapter += 1
        return

    counters[kind] += 1
    number = f"{current_chapter}.{counters[kind]}" if scope == "chapter" else str(counters[kind])
    prefix = f"{caption_spec.label}{caption_spec.separator}{number}"
    match_end = _prefix_end(text)
    if _prefix_overlaps_field(match_end, _field_ranges(paragraph)):
        report.skipped_field += 1
        return
    if not _replace_caption_prefix(paragraph, text, match_end, prefix):
        return

    if kind is CaptionKind.FIGURE:
        report.image_captions += 1
    else:
        report.table_captions += 1


def renumber_captions(
    package: DocumentPackage,
    *,
    scope: str = "chapter",
    spec: CaptionSpecs | None = None,
) -> CaptionReport:
    """Beri nomor caption per bab (``chapter``) atau per dokumen."""

    if scope not in {"chapter", "document"}:
        raise CaptionError(
            f"scope caption tidak dikenal: {scope!r}",
            code="CAPTION-SCOPE",
        )

    specs = spec or CaptionSpecs()
    report = CaptionReport()
    current_chapter: int | None = None
    counters = {CaptionKind.FIGURE: 0, CaptionKind.TABLE: 0}

    for paragraph in _body(package).iter(W_P):
        style_id = _paragraph_style_id(paragraph)
        if names.is_heading_style(style_id) and names.normalize_style_id(style_id) == "heading1":
            chapter = _heading_chapter(paragraph, report, scope, counters)
            if chapter is not None:
                current_chapter = chapter
            continue

        _number_caption(
            paragraph,
            style_id,
            current_chapter=current_chapter,
            counters=counters,
            scope=scope,
            specs=specs,
            report=report,
        )

    return report


__all__ = [
    "FIGURE_CAPTION_SPEC",
    "MAX_IMAGE_WIDTH_EMU",
    "TABLE_CAPTION_SPEC",
    "Caption",
    "CaptionError",
    "CaptionFontSpec",
    "CaptionKind",
    "CaptionReport",
    "CaptionSpec",
    "CaptionSpecs",
    "FigureLayoutSpec",
    "caption_style",
    "ensure_caption",
    "find_caption",
    "format_caption_paragraph",
    "format_images",
    "image_alt_text",
    "is_caption_paragraph",
    "iter_captions",
    "iter_image_paragraphs",
    "renumber_captions",
    "set_caption",
    "table_caption_text",
]
