"""Tabel native PPTX dengan border, fill, dan key sel dari token."""

import re
from collections.abc import Mapping

from lxml import etree
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide
from pptx.table import _Cell
from pptx.util import Emu

from autooffice.deck.layout.measure import measure_text
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

from .shapes import (
    KEY_EXTENSION_TAG,
    TABLE_MARKER,
    Box,
    PptxRenderError,
    add_extension_keys,
    apply_paragraph_style,
    apply_run_style,
    field_optional_text,
    field_rows,
    field_sequence,
    record_render_warning,
    rgb,
    set_namespace_marker,
)
from .textbox import TextStyle, add_keyed_text, body_style

# Angka ketat: tanda opsional, kelompok ribuan tiga digit dengan pemisah yang
# konsisten, desimal opsional memakai pemisah berbeda dari ribuan, persen
# opsional. String seperti "1.2.3", "1,2,3", "1,234,56", "nan", dan "inf"
# ditolak; pemisah ribuan tidak boleh dipakai ulang sebagai pemisah desimal.
_NUMERIC_PATTERN = re.compile(
    r"^[+-]?(?:"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|\d{1,3}(?:\.\d{3})+(?:,\d+)?"
    r"|\d+(?:[.,]\d+)?"
    r"|[.,]\d+"
    r")%?$"
)


def table_cell_key(cell: _Cell) -> str | None:
    """Baca key satu sel tabel dari ``a:tcPr/a:extLst`` native."""
    tc_pr = cell._tc.tcPr
    if tc_pr is None:
        return None
    keys = tuple(element.text for element in tc_pr.iter(KEY_EXTENSION_TAG) if element.text)
    return keys[0] if keys else None


def set_table_cell_key(cell: _Cell, key: str) -> None:
    """Simpan key sel di extension ``a:tcPr`` tanpa mengganti tabel native."""
    if not key:
        raise PptxRenderError("Key sel tabel tidak boleh kosong.")
    add_extension_keys(cell._tc.get_or_add_tcPr(), (key,))


def render_table_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
) -> tuple[BaseShape, ...]:
    """Render block table sebagai ``shapes.add_table`` native."""
    columns = field_sequence(block.fields, "columns", block_id=block.block_id)
    rows = field_rows(block.fields, "rows", block_id=block.block_id)
    if not columns:
        raise PptxRenderError(f"Block table '{block.block_id}' tidak memiliki kolom.")
    if not rows:
        raise PptxRenderError(f"Block table '{block.block_id}' tidak memiliki baris.")
    width_mismatch = [index for index, row in enumerate(rows, start=1) if len(row) != len(columns)]
    if width_mismatch:
        row_index = width_mismatch[0]
        raise PptxRenderError(
            f"Block table '{block.block_id}' baris {row_index} memiliki "
            f"{len(rows[row_index - 1])} sel; jumlah kolom adalah {len(columns)}."
        )

    namespace = f"{slide_id}.{block.block_id}"
    inner = box.inset(theme.spacing.card_padding_emu)
    header_style = TextStyle(
        size_pt=max(theme.typography.body_pt, theme.typography.minimum_pt),
        weight=600,
        color=theme.colors.accent_ink,
        family=theme.typography.family,
        line_height=theme.typography.line_height,
    )
    body_text_style = TextStyle(
        size_pt=max(theme.typography.body_pt, theme.typography.minimum_pt),
        weight=400,
        color=theme.colors.ink,
        family=theme.typography.family,
        line_height=theme.typography.line_height,
    )
    caption_style = body_style(theme, weight=400, color=theme.colors.muted)
    caption = field_optional_text(block.fields, "caption")
    caption_height = 0
    gap = 0
    if caption:
        caption_height = measure_text(
            caption,
            available_width_emu=inner.width,
            theme=theme,
            font_size_pt=caption_style.size_pt,
            weight=caption_style.weight,
        ).height_emu
        gap = theme.spacing.sm_emu
    table_height = inner.height - caption_height - gap
    if table_height <= 0:
        raise PptxRenderError(f"Block table '{block.block_id}' tidak memiliki ruang untuk tabel.")
    table_box = Box(
        left=inner.left,
        top=inner.top,
        width=inner.width,
        height=table_height,
    )
    emphasis = _emphasis_column(block.fields, column_count=len(columns))
    header_emphasis_style = TextStyle(
        size_pt=header_style.size_pt,
        weight=700,
        color=header_style.color,
        family=header_style.family,
        line_height=header_style.line_height,
    )
    body_emphasis_style = TextStyle(
        size_pt=body_text_style.size_pt,
        weight=600,
        color=body_text_style.color,
        family=body_text_style.family,
        line_height=body_text_style.line_height,
    )
    row_content_heights = _measure_row_content_heights(
        columns,
        rows,
        table_width=table_box.width,
        theme=theme,
        header_style=header_style,
        body_style=body_text_style,
        emphasis_column=emphasis,
        header_emphasis_style=header_emphasis_style,
        body_emphasis_style=body_emphasis_style,
    )
    row_heights = _allocate_row_heights(
        row_content_heights,
        margin_emu=2 * theme.spacing.sm_emu,
        available_height_emu=table_box.height,
        block_id=block.block_id,
    )
    frame = slide.shapes.add_table(
        rows=len(rows) + 1,
        cols=len(columns),
        left=Emu(table_box.left),
        top=Emu(table_box.top),
        width=Emu(table_box.width),
        height=Emu(table_box.height),
    )
    table = frame.table
    table.first_row = True
    table.horz_banding = False
    table.first_col = False
    table.last_row = False
    table.last_col = False
    _remove_table_style(frame)
    _distribute_columns(frame, table_box.width)
    _distribute_rows(frame, row_heights)
    alt = ", ".join(columns)
    set_namespace_marker(frame, TABLE_MARKER, namespace, description=alt)

    for column_index, header in enumerate(columns, start=1):
        cell = table.cell(0, column_index - 1)
        emphasized = emphasis == column_index
        _style_cell(
            cell,
            header,
            style=header_emphasis_style if emphasized else header_style,
            theme=theme,
            fill=theme.colors.accent_deep if emphasized else theme.colors.accent,
            numeric=False,
            key=f"{namespace}.h{column_index}",
        )
    for row_index, row in enumerate(rows, start=1):
        fill = theme.colors.surface if row_index % 2 == 1 else theme.colors.surface_alt
        for column_index, value in enumerate(row, start=1):
            cell = table.cell(row_index, column_index - 1)
            emphasized = emphasis == column_index
            _style_cell(
                cell,
                value,
                style=body_emphasis_style if emphasized else body_text_style,
                theme=theme,
                fill=theme.colors.accent_soft if emphasized else fill,
                numeric=_looks_numeric(value),
                key=f"{namespace}.r{row_index}.c{column_index}",
            )
    shapes: list[BaseShape] = [frame]
    if caption:
        caption_box = Box(
            left=inner.left,
            top=inner.bottom - caption_height,
            width=inner.width,
            height=caption_height,
        )
        shapes.append(
            add_keyed_text(
                slide,
                caption_box,
                key=f"{namespace}.caption",
                text=caption,
                style=caption_style,
                theme=theme,
            )
        )
    return tuple(shapes)


def _remove_table_style(frame: GraphicFrame) -> None:
    tbl_pr = frame._element.find(".//" + qn("a:tblPr"))
    if tbl_pr is None:
        return
    style_id = tbl_pr.find(qn("a:tableStyleId"))
    if style_id is not None:
        tbl_pr.remove(style_id)


def _distribute_columns(frame: GraphicFrame, width_emu: int) -> None:
    table = frame.table
    column_count = len(table.columns)
    base = width_emu // column_count
    for index in range(column_count):
        extra = width_emu - base * column_count if index == column_count - 1 else 0
        table.columns[index].width = Emu(base + extra)


def _distribute_rows(frame: GraphicFrame, row_heights: tuple[int, ...]) -> None:
    table = frame.table
    if len(row_heights) != len(table.rows):
        raise PptxRenderError(
            f"Jumlah tinggi baris {len(row_heights)} tidak cocok dengan tabel "
            f"{len(table.rows)} baris."
        )
    for index, height in enumerate(row_heights):
        if height <= 0:
            raise PptxRenderError(f"Tinggi baris tabel ke-{index + 1} harus positif.")
        table.rows[index].height = Emu(height)


def _measure_row_content_heights(
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    *,
    table_width: int,
    theme: Theme,
    header_style: TextStyle,
    body_style: TextStyle,
    emphasis_column: int | None,
    header_emphasis_style: TextStyle,
    body_emphasis_style: TextStyle,
) -> tuple[int, ...]:
    """Ukur tinggi konten setiap baris dengan lebar sel yang sama saat render.

    Sel pada kolom emphasis diukur memakai bobot font yang benar-benar dipakai
    renderer (700 untuk header, 600 untuk body), supaya baris tidak kekurangan
    tinggi saat bobot tebal membungkus lebih banyak.
    """
    column_count = len(columns)
    column_width = max(1, table_width // column_count)
    cell_width = max(1, column_width - 2 * theme.spacing.sm_emu)

    def measure(
        row: tuple[str, ...],
        style: TextStyle,
        emphasis_style: TextStyle,
    ) -> int:
        return max(
            measure_text(
                cell,
                available_width_emu=cell_width,
                theme=theme,
                font_size_pt=(
                    emphasis_style.size_pt if emphasis_column == column_index else style.size_pt
                ),
                weight=(emphasis_style.weight if emphasis_column == column_index else style.weight),
            ).height_emu
            for column_index, cell in enumerate(row, start=1)
        )

    content_heights = [
        measure(columns, header_style, header_emphasis_style),
    ]
    content_heights.extend(measure(row, body_style, body_emphasis_style) for row in rows)
    return tuple(content_heights)


def _allocate_row_heights(
    content_heights: tuple[int, ...],
    *,
    margin_emu: int,
    available_height_emu: int,
    block_id: str,
) -> tuple[int, ...]:
    """Bagi tinggi tabel proporsional terhadap konten, dengan margin minimum."""
    if margin_emu < 0:
        raise PptxRenderError("Margin vertikal sel tabel tidak boleh negatif.")
    minimums = [height + margin_emu for height in content_heights]
    total_minimum = sum(minimums)
    if total_minimum > available_height_emu:
        raise PptxRenderError(
            f"Block table '{block_id}' memerlukan tinggi minimum {total_minimum} EMU, "
            f"melebihi kotak tabel {available_height_emu} EMU."
        )
    extra = available_height_emu - total_minimum
    if extra == 0:
        return tuple(minimums)
    total_content = sum(content_heights)
    allocated = [
        minimum + extra * content // total_content
        for minimum, content in zip(minimums, content_heights, strict=True)
    ]
    remainder = available_height_emu - sum(allocated)
    largest = max(range(len(content_heights)), key=lambda index: content_heights[index])
    allocated[largest] += remainder
    return tuple(allocated)


def _emphasis_column(fields: Mapping[str, object], *, column_count: int) -> int | None:
    """Baca kolom emphasis 1-based bila valid untuk jumlah kolom tabel."""
    value = fields.get("emphasis_column")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 1 <= value <= column_count:
        return value
    return None


def _style_cell(
    cell: _Cell,
    text: str,
    *,
    style: TextStyle,
    theme: Theme,
    fill: str,
    numeric: bool,
    key: str,
) -> None:
    text_frame = cell.text_frame
    text_frame.word_wrap = True
    text_frame.auto_size = MSO_AUTO_SIZE.NONE
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = Emu(theme.spacing.sm_emu)
    cell.margin_right = Emu(theme.spacing.sm_emu)
    cell.margin_top = Emu(theme.spacing.sm_emu)
    cell.margin_bottom = Emu(theme.spacing.sm_emu)
    paragraph = text_frame.paragraphs[0]
    paragraph.text = text
    apply_paragraph_style(
        paragraph,
        line_height=style.line_height,
        font_size_pt=style.size_pt,
        alignment=PP_ALIGN.RIGHT if numeric else PP_ALIGN.LEFT,
    )
    for run in paragraph.runs:
        warning = apply_run_style(
            run,
            family=style.family,
            size_pt=style.size_pt,
            weight=style.weight,
            color=style.color,
            tracking_em=theme.typography.tracking_em,
        )
        if warning is not None:
            record_render_warning(warning)
    cell.fill.solid()  # type: ignore[no-untyped-call]
    cell.fill.fore_color.rgb = rgb(fill)
    _set_cell_borders(cell._tc.get_or_add_tcPr(), theme)
    set_table_cell_key(cell, key)


def _set_cell_borders(tc_pr: etree._Element, theme: Theme) -> None:
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        existing = tc_pr.find(qn(tag))
        if existing is not None:
            tc_pr.remove(existing)
    for side in ("lnB", "lnT", "lnR", "lnL"):
        line = _border_line(side, theme)
        tc_pr.insert(0, line)


def _border_line(side: str, theme: Theme) -> etree._Element:
    line = OxmlElement(f"a:{side}")
    line.set("w", str(theme.spacing.divider_emu))
    line.set("cap", "flat")
    line.set("cmpd", "sng")
    line.set("algn", "ctr")
    fill = OxmlElement("a:solidFill")
    color = OxmlElement("a:srgbClr")
    color.set("val", theme.colors.border[1:].upper())
    fill.append(color)
    line.append(fill)
    dash = OxmlElement("a:prstDash")
    dash.set("val", "solid")
    line.append(dash)
    return line


def _looks_numeric(text: str) -> bool:
    """Angka ketat agar sel teks seperti versi atau rentang tidak rata kanan."""
    return _NUMERIC_PATTERN.fullmatch(text.strip()) is not None
