"""Helper tabel DOCX: border, margin, header, dan tabel kode 1x1.

Modul ini adalah satu-satunya tempat yang membangun ``w:tblPr``/``w:tcPr``
untuk stage ``code`` dan ``captions``. Semua perubahan XML memakai
``docgen.docx.xml``; tidak ada ``python-docx`` atau ``zipfile`` di sini.

Tabel kode tidak pernah dianggap tabel data: ``is_code_table`` dipakai stage
caption untuk melewati tabel 1x1 yang seluruh paragrafnya bergaya kode.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lxml import etree

from . import DocxError, names
from .package import DOCUMENT_PART
from .xml import (
    RPR_ORDER,
    TBLPR_ORDER,
    TCPR_ORDER,
    ensure_rpr,
    ensure_tblpr,
    ensure_tcpr,
    get_or_add,
    insert_ordered,
    paragraph_text,
    qn,
    sha256_c14n,
)

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from .package import DocumentPackage


class TableError(DocxError):
    """Struktur tabel tidak valid atau operasi melanggar invariant."""

    default_code = "TABLE"


DEFAULT_CODE_STYLES: tuple[str, ...] = (
    "Source Code",
    "Verbatim Char",
    "HTML Code",
    "HTML Preformatted",
)

# Border tabel ilmiah: garis atas/bawah 1 pt, tanpa garis vertikal.
SCIENTIFIC_TABLE_BORDERS: tuple[tuple[str, str, int | None], ...] = (
    ("w:top", "single", 8),
    ("w:left", "nil", None),
    ("w:bottom", "single", 8),
    ("w:right", "nil", None),
    ("w:insideH", "nil", None),
    ("w:insideV", "nil", None),
)

# Border tabel kode: kotak penuh 1 pt, tanpa border dalam.
CODE_TABLE_BORDERS: tuple[tuple[str, str, int | None], ...] = (
    ("w:top", "single", 8),
    ("w:left", "single", 8),
    ("w:bottom", "single", 8),
    ("w:right", "single", 8),
    ("w:insideH", "nil", None),
    ("w:insideV", "nil", None),
)

CELL_MARGIN_TAGS: tuple[str, ...] = (
    "w:top",
    "w:left",
    "w:bottom",
    "w:right",
)

CELL_MARGIN_ORDER: tuple[str, ...] = tuple(qn(tag) for tag in CELL_MARGIN_TAGS)

CONTENT_WIDTH_FALLBACK = 9360  # letter: 12240 - 2 x 1440 twip

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
W_DEL_TEXT = names.W_DELTEXT
W_FLD_CHAR = names.W_FLDCHAR
W_FLD_SIMPLE = names.W_FLDSIMPLE
W_DRAWING = names.W_DRAWING
W_PICT = names.W_PICT
W_OBJECT = names.W_OBJECT
W_TXBX_CONTENT = names.W_TXBXCONTENT
W_SECTPR = names.W_SECTPR
W_TBL = names.W_TBL
W_TR = names.W_TR
W_TC = names.W_TC
W_PG_SZ = qn("w:pgSz")
W_PG_MAR = qn("w:pgMar")
W_W = qn("w:w")
W_TYPE = qn("w:type")
W_GUTTER = qn("w:gutter")
W_LEFT = qn("w:left")
W_RIGHT = qn("w:right")
W_FIRST_LINE = qn("w:firstLine")
W_SHD = qn("w:shd")
W_TBL_GRID = qn("w:tblGrid")
W_GRID_COL = qn("w:gridCol")
W_TBL_LAYOUT = qn("w:tblLayout")
W_TBL_W = qn("w:tblW")
W_TR_PR = qn("w:trPr")
W_TBL_PR_EX = qn("w:tblPrEx")
W_TBL_HEADER = qn("w:tblHeader")
W_TBL_BORDERS = qn("w:tblBorders")
W_TBL_CELL_MAR = qn("w:tblCellMar")
W_TC_BORDERS = qn("w:tcBorders")
W_TC_MAR = qn("w:tcMar")
W_SZ = qn("w:sz")
W_COLOR = qn("w:color")
W_SPACE = qn("w:space")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_LINE = qn("w:line")
W_LINE_RULE = qn("w:lineRule")
W_JC = qn("w:jc")
W_ASCII = qn("w:ascii")
W_HANSI = qn("w:hAnsi")
W_CS = qn("w:cs")
W_EAST_ASIA = qn("w:eastAsia")
XML_SPACE = names.XML + "space"

UNSAFE_CODE_TAGS = frozenset(
    {
        W_FLD_CHAR,
        W_FLD_SIMPLE,
        W_INSTR_TEXT,
        W_SECTPR,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_TXBX_CONTENT,
        qn("w:commentReference"),
        qn("w:footnoteReference"),
        qn("w:endnoteReference"),
        names.W_INS,
        names.W_DEL,
        names.W_MOVEFROM,
        names.W_MOVE_TO,
    }
)

NEUTRAL_BODY_TAGS = frozenset(
    {
        names.W_BOOKMARK_START,
        names.W_BOOKMARK_END,
        qn("w:commentRangeStart"),
        qn("w:commentRangeEnd"),
        qn("w:permStart"),
        qn("w:permEnd"),
        qn("w:proofErr"),
    }
)

MARKER_START_TAGS = frozenset(
    {
        names.W_BOOKMARK_START,
        qn("w:commentRangeStart"),
        qn("w:permStart"),
        qn("w:proofErr"),
    }
)
MARKER_END_TAGS = frozenset(
    {
        names.W_BOOKMARK_END,
        qn("w:commentRangeEnd"),
        qn("w:permEnd"),
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


# ---------------------------------------------------------------------------
# Spesifikasi
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BorderSpec:
    """Border tabel: daftar sisi, warna, dan jarak dari teks."""

    sides: tuple[tuple[str, str, int | None], ...] = SCIENTIFIC_TABLE_BORDERS
    color: str = "000000"
    space: int = 0


SCIENTIFIC_BORDER_SPEC = BorderSpec(SCIENTIFIC_TABLE_BORDERS)
CODE_BORDER_SPEC = BorderSpec(CODE_TABLE_BORDERS)


@dataclass(frozen=True)
class TableSpec:
    """Bentuk final tabel data ilmiah."""

    borders: BorderSpec = SCIENTIFIC_BORDER_SPEC
    horizontal_margin: int = 108
    vertical_margin: int = 0
    header_border_size: int = 4
    header_border_color: str = "000000"
    clear_header_bold: bool = True


@dataclass(frozen=True)
class CodeSpec:
    """Nilai visual blok kode yang sudah dinormalisasi dari ``format.yml``."""

    style_id: str = "SourceCode"
    detect_styles: tuple[str, ...] = DEFAULT_CODE_STYLES
    font_family: str = "Courier New"
    font_size_half_points: int = 20
    color: str = "000000"
    alignment: str = "left"
    line_spacing: float = 1.0
    space_before: int = 0
    space_after: int = 0
    border_style: str = "single"
    border_size_eighth_points: int = 8
    border_color: str = "000000"
    cell_margin: int = 108
    width_percent: int = 100


@dataclass(frozen=True)
class TableInfo:
    """Ringkasan satu tabel untuk stage caption."""

    element: etree._Element
    is_code: bool
    has_caption: bool
    rows: int
    columns: int


@dataclass
class _Line:
    """Satu baris kode beserta penanda XML yang menempel padanya."""

    text: str = ""
    markers_start: list[etree._Element] = field(default_factory=list)
    markers_end: list[etree._Element] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utilitas XML
# ---------------------------------------------------------------------------


def document_root(package: DocumentPackage) -> etree._Element:
    """Kembalikan root ``word/document.xml`` yang hidup."""

    return package.xml(DOCUMENT_PART)


def document_body(package: DocumentPackage) -> etree._Element:
    """Kembalikan elemen ``w:body`` atau melempar ``TableError``."""

    body = document_root(package).find(W_BODY)
    if body is None:
        raise TableError(
            f"{DOCUMENT_PART} tidak memiliki elemen w:body",
            code="TABLE-NO-BODY",
        )
    return body


def _new_element(tag: str) -> etree._Element:
    return etree.Element(qn(tag))


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


def _normalized_detect_styles(detect_styles: Sequence[str] | None) -> frozenset[str]:
    names_to_use = DEFAULT_CODE_STYLES if detect_styles is None else detect_styles
    return frozenset(names.normalize_style_id(name) for name in names_to_use)


def is_code_paragraph(
    paragraph: etree._Element,
    detect_styles: Sequence[str] | None = None,
) -> bool:
    """True bila paragraf memakai salah satu style blok kode."""

    if paragraph.tag != W_P:
        return False
    style_id = _paragraph_style_id(paragraph)
    if style_id is None:
        return False
    normalized = names.normalize_style_id(style_id)
    configured = _normalized_detect_styles(detect_styles)
    if normalized in configured:
        return True
    return detect_styles is None and names.is_code_style(style_id)


def _is_code_table(
    table: etree._Element,
    detect_styles: Sequence[str] | None = None,
) -> bool:
    """Tabel 1x1 berisi paragraf kode adalah blok kode, bukan tabel data."""

    if table.tag != W_TBL:
        return False
    rows = table.findall(W_TR)
    if len(rows) != 1:
        return False
    cells = rows[0].findall(W_TC)
    if len(cells) != 1:
        return False
    paragraphs = cells[0].findall(W_P)
    if not paragraphs:
        return False
    return all(is_code_paragraph(paragraph, detect_styles) for paragraph in paragraphs)


def is_code_table(
    table: etree._Element,
    detect_styles: Sequence[str] | None = None,
) -> bool:
    """Alias publik ``_is_code_table`` untuk stage caption."""

    return _is_code_table(table, detect_styles)


def _new_border(
    tag: str,
    value: str,
    size: int | None,
    *,
    color: str = "000000",
    space: int = 0,
) -> etree._Element:
    border = _new_element(tag)
    border.set(W_VAL, value)
    if size is not None:
        border.set(W_SZ, str(size))
    border.set(W_SPACE, str(space))
    border.set(W_COLOR, color)
    return border


def _set_table_borders(table_properties: etree._Element, spec: BorderSpec) -> None:
    _remove_direct_children(table_properties, W_TBL_BORDERS)
    borders = get_or_add(table_properties, W_TBL_BORDERS, TBLPR_ORDER)
    for tag, value, size in spec.sides:
        borders.append(
            _new_border(
                tag,
                value,
                size,
                color=spec.color,
                space=spec.space,
            )
        )


def _set_margin_values(
    table_properties: etree._Element,
    *,
    top: int,
    left: int,
    bottom: int,
    right: int,
) -> None:
    _remove_direct_children(table_properties, W_TBL_CELL_MAR)
    margins = get_or_add(table_properties, W_TBL_CELL_MAR, TBLPR_ORDER)
    for tag, value in (
        ("w:top", top),
        ("w:left", left),
        ("w:bottom", bottom),
        ("w:right", right),
    ):
        margin = get_or_add(margins, qn(tag), CELL_MARGIN_ORDER)
        margin.set(W_W, str(value))
        margin.set(W_TYPE, "dxa")


def _margin_element(tag: str, value: int) -> etree._Element:
    margins = _new_element(tag)
    for side in CELL_MARGIN_TAGS:
        margin = _new_element(side)
        margin.set(W_W, str(value))
        margin.set(W_TYPE, "dxa")
        margins.append(margin)
    return margins


def _set_cell_margin_element(cell_properties: etree._Element, value: int) -> None:
    _remove_direct_children(cell_properties, W_TC_MAR)
    insert_ordered(
        cell_properties,
        _margin_element("w:tcMar", value),
        TCPR_ORDER,
    )


def _set_header_cell_bottom_border(
    cell: etree._Element,
    *,
    size: int,
    color: str,
) -> None:
    cell_properties = ensure_tcpr(cell)
    _remove_direct_children(cell_properties, W_TC_BORDERS)
    borders = get_or_add(cell_properties, W_TC_BORDERS, TCPR_ORDER)
    borders.append(_new_border("w:bottom", "single", size, color=color, space=0))


def _clear_run_bold(run: etree._Element) -> None:
    properties = ensure_rpr(run)
    for tag in ("w:b", "w:bCs"):
        bold = get_or_add(properties, qn(tag), RPR_ORDER)
        bold.set(W_VAL, "0")


def _row_is_header(row: etree._Element) -> bool:
    row_properties = row.find(W_TR_PR)
    if row_properties is None:
        return False
    marker = row_properties.find(W_TBL_HEADER)
    if marker is None:
        return False
    value = marker.get(W_VAL)
    return value is None or value.lower() not in {"0", "false", "off"}


def _header_row_indexes(rows: Sequence[etree._Element]) -> list[int]:
    marked = [index for index, row in enumerate(rows) if _row_is_header(row)]
    if marked:
        return marked
    # Pandoc menandai baris header dengan w:tblHeader. Bila penanda tidak ada,
    # baris pertama tabel multi-baris diperlakukan sebagai header.
    return [0] if len(rows) > 1 else []


def _table_caption_text(table: etree._Element) -> str:
    table_properties = table.find(names.W_TBLPR)
    if table_properties is None:
        return ""
    caption = table_properties.find(qn("w:tblCaption"))
    if caption is None:
        return ""
    return (caption.get(W_VAL) or "").strip()


def _is_table_caption_paragraph(paragraph: etree._Element) -> bool:
    style_id = _paragraph_style_id(paragraph)
    if not names.is_caption_style(style_id):
        return False
    normalized = names.normalize_style_id(style_id)
    if normalized == "tablecaption":
        return True
    if normalized != "caption":
        return False
    text = paragraph_text(paragraph).strip()
    return text.lower().startswith("tabel")


def _previous_meaningful(element: etree._Element) -> etree._Element | None:
    sibling = element.getprevious()
    while sibling is not None:
        if sibling.tag in NEUTRAL_BODY_TAGS:
            sibling = sibling.getprevious()
            continue
        if sibling.tag == W_P and not paragraph_text(sibling).strip():
            sibling = sibling.getprevious()
            continue
        break
    return sibling


def _next_meaningful(element: etree._Element) -> etree._Element | None:
    sibling = element.getnext()
    while sibling is not None:
        if sibling.tag in NEUTRAL_BODY_TAGS:
            sibling = sibling.getnext()
            continue
        if sibling.tag == W_P and not paragraph_text(sibling).strip():
            sibling = sibling.getnext()
            continue
        break
    return sibling


def _has_caption(table: etree._Element) -> bool:
    if _table_caption_text(table):
        return True
    previous = _previous_meaningful(table)
    if previous is not None and previous.tag == W_P and _is_table_caption_paragraph(previous):
        return True
    following = _next_meaningful(table)
    return following is not None and following.tag == W_P and _is_table_caption_paragraph(following)


# ---------------------------------------------------------------------------
# Normalisasi tabel data
# ---------------------------------------------------------------------------


def _normalize_table_rows(
    rows: Sequence[etree._Element],
    header_bottom_index: int | None,
    spec: TableSpec,
) -> None:
    for row_index, row in enumerate(rows):
        table_exception = row.find(W_TBL_PR_EX)
        if table_exception is not None:
            _remove_direct_children(table_exception, W_TBL_BORDERS)
            _remove_direct_children(table_exception, W_SHD)
            _remove_direct_children(table_exception, W_TBL_CELL_MAR)

        row_properties = row.find(W_TR_PR)
        if row_properties is not None:
            _remove_direct_children(row_properties, W_SHD)

        for cell in row.findall(W_TC):
            cell_properties = cell.find(qn("w:tcPr"))
            if cell_properties is not None:
                _remove_direct_children(cell_properties, W_SHD)
                _remove_direct_children(cell_properties, W_TC_BORDERS)
                _remove_direct_children(cell_properties, W_TC_MAR)
            if row_index == header_bottom_index:
                _set_header_cell_bottom_border(
                    cell,
                    size=spec.header_border_size,
                    color=spec.header_border_color,
                )


def _normalize_table(table: etree._Element, spec: TableSpec) -> bool:
    before = sha256_c14n(table)

    table_properties = ensure_tblpr(table)
    _remove_direct_children(table_properties, W_SHD)
    _set_table_borders(table_properties, spec.borders)
    _set_margin_values(
        table_properties,
        top=spec.vertical_margin,
        left=spec.horizontal_margin,
        bottom=spec.vertical_margin,
        right=spec.horizontal_margin,
    )

    rows = table.findall(W_TR)
    header_indexes = _header_row_indexes(rows)
    header_bottom_index = (
        header_indexes[-1] if header_indexes and header_indexes[-1] < len(rows) - 1 else None
    )
    _normalize_table_rows(rows, header_bottom_index, spec)

    if spec.clear_header_bold:
        for row_index in header_indexes:
            for run in rows[row_index].iter(names.W_R):
                _clear_run_bold(run)

    return sha256_c14n(table) != before


def normalize_table(
    package: DocumentPackage,
    table: etree._Element,
    spec: TableSpec,
) -> None:
    """Seragamkan satu tabel data menjadi gaya tabel ilmiah."""

    _normalize_table(table, spec)


def set_borders(table: etree._Element, spec: BorderSpec) -> None:
    """Terapkan border pada ``w:tblPr`` tabel."""

    _set_table_borders(ensure_tblpr(table), spec)


def set_cell_margins(table: etree._Element, twips: int) -> None:
    """Terapkan cell margin seragam pada tabel."""

    _set_margin_values(
        ensure_tblpr(table),
        top=twips,
        left=twips,
        bottom=twips,
        right=twips,
    )


def set_table_width(table: etree._Element, percent: int) -> None:
    """Set lebar tabel dalam persen (100% -> ``w:w=5000`` ``pct``)."""

    if percent <= 0:
        raise TableError(
            f"lebar tabel harus > 0, bukan {percent}",
            code="TABLE-WIDTH",
        )
    width = ensure_tblpr(table).find(W_TBL_W)
    if width is None:
        width = _new_element("w:tblW")
        insert_ordered(ensure_tblpr(table), width, TBLPR_ORDER)
    width.set(W_W, str(round(percent * 50)))
    width.set(W_TYPE, "pct")


# ---------------------------------------------------------------------------
# Tabel kode
# ---------------------------------------------------------------------------


def _code_border_spec(spec: CodeSpec) -> BorderSpec:
    sides: list[tuple[str, str, int | None]] = []
    for tag, value, _size in CODE_TABLE_BORDERS:
        if value == "nil":
            sides.append((tag, "nil", None))
        else:
            sides.append((tag, spec.border_style, spec.border_size_eighth_points))
    return BorderSpec(tuple(sides), spec.border_color)


def _format_code_table(table: etree._Element, spec: CodeSpec) -> bool:
    before = sha256_c14n(table)

    table_properties = ensure_tblpr(table)
    _remove_direct_children(table_properties, W_SHD)
    _set_table_borders(table_properties, _code_border_spec(spec))
    _set_margin_values(
        table_properties,
        top=spec.cell_margin,
        left=spec.cell_margin,
        bottom=spec.cell_margin,
        right=spec.cell_margin,
    )
    set_table_width(table, spec.width_percent)

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
            cell_properties = ensure_tcpr(cell)
            _remove_direct_children(cell_properties, W_SHD)
            _remove_direct_children(cell_properties, W_TC_BORDERS)
            _set_cell_margin_element(cell_properties, spec.cell_margin)

    return sha256_c14n(table) != before


def format_code_table(
    package: DocumentPackage,
    table: etree._Element,
    spec: CodeSpec | None = None,
) -> bool:
    """Normalisasi tabel kode ke kotak penuh; ``True`` bila berubah."""

    return _format_code_table(table, spec or CodeSpec())


def normalize_code_tables(
    package: DocumentPackage,
    *,
    spec: CodeSpec | None = None,
) -> int:
    """Normalisasi semua tabel kode lama dan hitung yang benar-benar berubah."""

    code_spec = spec or CodeSpec()
    normalized = 0
    body = document_body(package)
    for table in body.iter(W_TBL):
        if _is_code_table(table, code_spec.detect_styles) and _format_code_table(table, code_spec):
            normalized += 1
    return normalized


# ---------------------------------------------------------------------------
# Pembuatan tabel kode
# ---------------------------------------------------------------------------


def _int_attribute(element: etree._Element, name: str) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _content_width(body: etree._Element) -> int:
    section = body.find(W_SECTPR)
    if section is None:
        sections = body.findall(f".//{W_SECTPR}")
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


def _paragraph_lines(paragraph: etree._Element) -> list[_Line]:
    """Ambil baris kode dari satu paragraf.

    Pandoc menulis satu blok kode sebagai paragraf dengan ``w:br`` antarbaris,
    sedangkan sumber lain dapat memakai beberapa paragraf berurutan. Keduanya
    didukung: ``w:br``/``w:cr`` memulai baris baru.
    """

    lines = [_Line()]

    def walk(element: etree._Element) -> None:
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


def _run_properties(spec: CodeSpec) -> etree._Element:
    properties = _new_element("w:rPr")

    fonts = _new_element("w:rFonts")
    for attribute in (W_ASCII, W_HANSI, W_CS, W_EAST_ASIA):
        fonts.set(attribute, spec.font_family)
    properties.append(fonts)

    for tag in ("w:b", "w:bCs", "w:i", "w:iCs"):
        element = _new_element(tag)
        element.set(W_VAL, "0")
        properties.append(element)

    color = _new_element("w:color")
    color.set(W_VAL, spec.color)
    properties.append(color)

    for tag in ("w:sz", "w:szCs"):
        size = _new_element(tag)
        size.set(W_VAL, str(spec.font_size_half_points))
        properties.append(size)

    return properties


def _append_text_run(paragraph: etree._Element, text: str, spec: CodeSpec) -> None:
    """Tambahkan run kode; tab dipertahankan sebagai ``w:tab``."""

    run = _new_element("w:r")
    run.append(_run_properties(spec))

    parts = text.split("\t")
    for index, part in enumerate(parts):
        if index:
            run.append(_new_element("w:tab"))
        if part:
            text_node = _new_element("w:t")
            text_node.set(XML_SPACE, "preserve")
            text_node.text = part
            run.append(text_node)

    paragraph.append(run)


def _make_code_paragraph(
    line: _Line,
    style_id: str | None,
    spec: CodeSpec,
) -> etree._Element:
    paragraph = _new_element("w:p")
    properties = _new_element("w:pPr")

    if style_id:
        style = _new_element("w:pStyle")
        style.set(W_VAL, style_id)
        properties.append(style)

    spacing = _new_element("w:spacing")
    spacing.set(W_BEFORE, str(spec.space_before))
    spacing.set(W_AFTER, str(spec.space_after))
    spacing.set(W_LINE, str(max(1, round(spec.line_spacing * 240))))
    spacing.set(W_LINE_RULE, "auto")
    properties.append(spacing)

    indentation = _new_element("w:ind")
    indentation.set(W_LEFT, "0")
    indentation.set(W_RIGHT, "0")
    indentation.set(W_FIRST_LINE, "0")
    properties.append(indentation)

    if spec.alignment != "left":
        justification = _new_element("w:jc")
        justification.set(W_VAL, spec.alignment)
        properties.append(justification)

    paragraph.append(properties)

    for marker in line.markers_start:
        paragraph.append(marker)
    _append_text_run(paragraph, line.text, spec)
    for marker in line.markers_end:
        paragraph.append(marker)

    return paragraph


def _build_code_borders(spec: CodeSpec) -> etree._Element:
    borders = _new_element("w:tblBorders")
    for tag, value, _size in CODE_TABLE_BORDERS:
        if value == "nil":
            border_value = "nil"
            border_size = None
        else:
            border_value = spec.border_style
            border_size = spec.border_size_eighth_points
        borders.append(
            _new_border(
                tag,
                border_value,
                border_size,
                color=spec.border_color,
                space=0,
            )
        )
    return borders


def _build_code_table_properties(spec: CodeSpec) -> etree._Element:
    properties = _new_element("w:tblPr")

    width = _new_element("w:tblW")
    width.set(W_W, str(spec.width_percent * 50))
    width.set(W_TYPE, "pct")
    properties.append(width)

    properties.append(_build_code_borders(spec))

    layout = _new_element("w:tblLayout")
    layout.set(W_TYPE, "fixed")
    properties.append(layout)

    properties.append(_margin_element("w:tblCellMar", spec.cell_margin))
    return properties


def _build_code_cell(
    lines: Sequence[_Line],
    style_id: str | None,
    spec: CodeSpec,
    content_width: int,
) -> etree._Element:
    cell = _new_element("w:tc")

    cell_properties = _new_element("w:tcPr")
    cell_width = _new_element("w:tcW")
    cell_width.set(W_W, str(content_width))
    cell_width.set(W_TYPE, "dxa")
    cell_properties.append(cell_width)
    cell_properties.append(_margin_element("w:tcMar", spec.cell_margin))
    cell.append(cell_properties)

    for line in lines:
        cell.append(_make_code_paragraph(line, style_id, spec))
    return cell


def make_code_table(
    package: DocumentPackage,
    paragraphs: Sequence[etree._Element],
    spec: CodeSpec | None = None,
) -> etree._Element:
    """Bangun tabel kode 1x1 dari paragraf kode berurutan.

    Tabel dikembalikan tanpa disisipkan; caller yang memindahkan paragraf.
    """

    code_spec = spec or CodeSpec()
    body = document_body(package)
    content_width = _content_width(body)
    if not paragraphs:
        raise TableError(
            "tabel kode membutuhkan minimal satu paragraf",
            code="TABLE-NO-CODE",
        )
    style_id = _paragraph_style_id(paragraphs[0])

    lines: list[_Line] = []
    for paragraph in paragraphs:
        lines.extend(_paragraph_lines(paragraph))

    table = _new_element("w:tbl")
    table.append(_build_code_table_properties(code_spec))

    grid = _new_element("w:tblGrid")
    grid_column = _new_element("w:gridCol")
    grid_column.set(W_W, str(content_width))
    grid.append(grid_column)
    table.append(grid)

    row = _new_element("w:tr")
    row.append(_build_code_cell(lines, style_id, code_spec, content_width))
    table.append(row)
    return table


# ---------------------------------------------------------------------------
# Iterasi dan pemformatan tabel
# ---------------------------------------------------------------------------


def _format_table(
    table: etree._Element,
    spec: TableSpec | None,
    code_spec: CodeSpec | None,
) -> bool:
    if _is_code_table(table, (code_spec or CodeSpec()).detect_styles):
        return _format_code_table(table, code_spec or CodeSpec())
    return _normalize_table(table, spec or TableSpec())


def format_tables(
    package: DocumentPackage,
    *,
    spec: TableSpec | None = None,
    code_spec: CodeSpec | None = None,
) -> int:
    """Format semua tabel (data dan kode) dan kembalikan jumlah yang berubah."""

    changed = 0
    for table in document_body(package).iter(W_TBL):
        if _format_table(table, spec, code_spec):
            changed += 1
    return changed


def iter_tables(
    package: DocumentPackage,
    *,
    detect_styles: Sequence[str] | None = None,
) -> tuple[TableInfo, ...]:
    """Iterasi tabel body beserta status kode dan caption."""

    tables: list[TableInfo] = []
    for table in document_body(package).iter(W_TBL):
        rows = table.findall(W_TR)
        columns = len(rows[0].findall(W_TC)) if rows else 0
        tables.append(
            TableInfo(
                element=table,
                is_code=_is_code_table(table, detect_styles),
                has_caption=_has_caption(table),
                rows=len(rows),
                columns=columns,
            )
        )
    return tuple(tables)


def collect_unsafe_children(paragraph: etree._Element) -> bool:
    """True bila paragraf kode memuat field/section/objek/perubahan terlacak."""

    for element in paragraph.iter():
        if element is paragraph:
            continue
        if element.tag in UNSAFE_CODE_TAGS:
            return True
    return False


__all__ = [
    "CELL_MARGIN_TAGS",
    "CODE_BORDER_SPEC",
    "CODE_TABLE_BORDERS",
    "DEFAULT_CODE_STYLES",
    "NEUTRAL_BODY_TAGS",
    "SCIENTIFIC_BORDER_SPEC",
    "SCIENTIFIC_TABLE_BORDERS",
    "BorderSpec",
    "CodeSpec",
    "TableError",
    "TableInfo",
    "TableSpec",
    "collect_unsafe_children",
    "document_body",
    "document_root",
    "format_code_table",
    "format_tables",
    "is_code_paragraph",
    "is_code_table",
    "iter_tables",
    "make_code_table",
    "normalize_code_tables",
    "normalize_table",
    "set_borders",
    "set_cell_margins",
    "set_table_width",
]
