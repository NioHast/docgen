"""Tes tabel native, border token, fill, key sel, tinggi, dan alignment angka."""

import pytest
from _edge_helpers import new_slide
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

from autooffice.deck.layout.measure import measure_text
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError
from autooffice.deck.render.pptx.table import render_table_block, table_cell_key
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def _render(case, theme):
    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=case.workspace,
        )
    )


def _table_shape(result):
    presentation = Presentation(str(result.artifact_path))
    return next(
        shape
        for shape in presentation.slides[0].shapes
        if shape.name == "autooffice:table:s01.table1"
    )


def test_table_is_native_and_header_is_first_row(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    shape = _table_shape(result)

    assert shape.shape_type == MSO_SHAPE_TYPE.TABLE
    assert shape.has_table is True
    assert shape.table.cell(0, 0).text == "Lane"
    assert shape.table.cell(1, 0).text == "Model"
    node = shape._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("title") == "s01.table1"
    assert node.get("descr") == "Lane, Deliverable, Status"


def test_every_table_cell_has_native_key_extension(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table

    assert table_cell_key(table.cell(0, 2)) == "s01.table1.h3"
    assert table_cell_key(table.cell(2, 0)) == "s01.table1.r2.c1"
    assert table_cell_key(table.cell(2, 2)) == "s01.table1.r2.c3"


def test_table_header_uses_semibold_and_body_uses_regular(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table
    header_run = table.cell(0, 0).text_frame.paragraphs[0].runs[0]
    body_run = table.cell(1, 0).text_frame.paragraphs[0].runs[0]

    assert header_run.font.name == "Plus Jakarta Sans SemiBold"
    assert header_run.font.bold is False
    assert body_run.font.name == "Plus Jakarta Sans"
    assert body_run.font.bold is False
    assert _latin_typeface(header_run) == "Plus Jakarta Sans SemiBold"
    assert _latin_typeface(body_run) == "Plus Jakarta Sans"


def test_table_borders_and_fills_come_from_theme(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table
    header = table.cell(0, 0)
    body = table.cell(1, 0)
    tc_pr = header._tc.get_or_add_tcPr()

    assert header.fill.fore_color.rgb == _rgb(theme.colors.accent)
    assert body.fill.fore_color.rgb == _rgb(theme.colors.surface)
    assert tc_pr.find(qn("a:lnL")) is not None
    assert tc_pr.find(qn("a:lnR")) is not None
    assert tc_pr.find(qn("a:lnT")) is not None
    assert tc_pr.find(qn("a:lnB")) is not None


def test_numeric_cells_are_right_aligned(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    table = _table_shape(result).table

    numeric = table.cell(2, 2).text_frame.paragraphs[0]
    text = table.cell(1, 0).text_frame.paragraphs[0]

    assert numeric.alignment == PP_ALIGN.RIGHT
    assert text.alignment == PP_ALIGN.LEFT


def test_table_row_heights_follow_measured_content(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("Kolom A", "Kolom B"),
            "rows": (("panjang " * 25, "x"),),
        },
    )
    box = Box(left=0, top=0, width=4_000_000, height=4_500_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    table = shapes[0].table
    inner = box.inset(theme.spacing.card_padding_emu)
    column_width = inner.width // 2
    cell_width = column_width - 2 * theme.spacing.sm_emu
    body_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)
    tall_content = measure_text(
        "panjang " * 25,
        available_width_emu=cell_width,
        theme=theme,
        font_size_pt=body_size_pt,
        weight=400,
    ).height_emu

    header_height = table.rows[0].height
    body_height = table.rows[1].height
    assert body_height != header_height
    assert body_height >= tall_content + 2 * theme.spacing.sm_emu
    assert shapes[0].top + sum(row.height for row in table.rows) <= box.bottom


def test_table_rejects_content_taller_than_box(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A",), "rows": (("panjang " * 25,),)},
    )
    box = Box(left=0, top=0, width=2_000_000, height=800_000)

    with pytest.raises(PptxRenderError, match="melebihi kotak tabel"):
        render_table_block(new_slide(), block, box, theme, slide_id="s01")


def test_table_with_caption_fits_exact_box_and_keeps_caption_gap(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("A", "B"),
            "rows": (("1", "2"), ("3", "4")),
            "caption": "Status lane",
        },
    )
    padding = theme.spacing.card_padding_emu
    width = 4_000_000
    inner_width = width - 2 * padding
    column_width = inner_width // 2
    cell_width = column_width - 2 * theme.spacing.sm_emu
    body_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)

    def row_content(values: tuple[str, ...], weight: int) -> int:
        return max(
            measure_text(
                value,
                available_width_emu=cell_width,
                theme=theme,
                font_size_pt=body_size_pt,
                weight=weight,
            ).height_emu
            for value in values
        )

    margin = 2 * theme.spacing.sm_emu
    table_height = (
        row_content(("A", "B"), 600)
        + margin
        + row_content(("1", "2"), 400)
        + margin
        + row_content(("3", "4"), 400)
        + margin
    )
    caption_height = measure_text(
        "Status lane",
        available_width_emu=inner_width,
        theme=theme,
        font_size_pt=body_size_pt,
        weight=400,
    ).height_emu
    gap = theme.spacing.sm_emu
    box = Box(
        left=0,
        top=0,
        width=width,
        height=2 * padding + table_height + gap + caption_height,
    )

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    frame, caption = shapes
    inner = box.inset(padding)

    assert frame.top == inner.top
    assert sum(row.height for row in frame.table.rows) == table_height
    assert frame.top + frame.height == inner.top + table_height
    assert caption.top == frame.top + frame.height + gap
    assert caption.top + caption.height == inner.bottom
    assert frame.top + frame.height <= box.bottom
    assert caption.top + caption.height <= box.bottom


@pytest.mark.parametrize(
    "value",
    ["1.2.3", "1,2,3", "1,234,56", "1.234.56", "1,234,567,89", "nan", "inf", "", "12px"],
)
def test_malformed_numbers_align_left(theme, value: str) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("Value",), "rows": ((value,),)},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")

    assert shapes[0].table.cell(1, 0).text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT


@pytest.mark.parametrize(
    "value",
    ["42", "-3.5", "1,234.56", "72%", "+0.5", "1234", "1,234", "1.234,56", "12%"],
)
def test_strict_numeric_values_align_right(theme, value: str) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("Value",), "rows": ((value,),)},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")

    assert shapes[0].table.cell(1, 0).text_frame.paragraphs[0].alignment == PP_ALIGN.RIGHT


def test_emphasis_column_measures_emphasized_header_and_body(theme) -> None:
    header = "review eksperimen delta tambahan hasil"
    body = "arsitektur column arsitektur kontrak measurement arsitektur"
    caption = "Status emphasis"
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("A", header),
            "rows": (("1", body), ("2", body)),
            "caption": caption,
            "emphasis_column": 2,
        },
    )
    padding = theme.spacing.card_padding_emu
    width = 4_000_000
    inner_width = width - 2 * padding
    cell_width = inner_width // 2 - 2 * theme.spacing.sm_emu
    font_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)
    margin = 2 * theme.spacing.sm_emu

    def measure(text: str, weight: int):
        return measure_text(
            text,
            available_width_emu=cell_width,
            theme=theme,
            font_size_pt=font_size_pt,
            weight=weight,
        )

    header_emphasis = measure(header, 700)
    body_emphasis = measure(body, 600)
    assert header_emphasis.line_count > measure(header, 600).line_count
    assert body_emphasis.line_count > measure(body, 400).line_count

    caption_height = measure_text(
        caption,
        available_width_emu=inner_width,
        theme=theme,
        font_size_pt=font_size_pt,
        weight=400,
    ).height_emu
    gap = theme.spacing.sm_emu
    table_height = header_emphasis.height_emu + margin
    table_height += 2 * (body_emphasis.height_emu + margin)
    box = Box(
        left=0,
        top=0,
        width=width,
        height=2 * padding + table_height + gap + caption_height,
    )

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    frame, caption_shape = shapes
    rows = frame.table.rows

    assert rows[0].height >= header_emphasis.height_emu + margin
    assert rows[1].height >= body_emphasis.height_emu + margin
    assert rows[2].height >= body_emphasis.height_emu + margin
    assert sum(row.height for row in rows) == table_height
    assert caption_shape.top == frame.top + frame.height + gap


def test_emphasis_column_changes_fill_and_weight(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {
            "columns": ("A", "B", "C"),
            "rows": (("1", "2", "3"),),
            "emphasis_column": 2,
        },
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_table_block(new_slide(), block, box, theme, slide_id="s01")
    table = shapes[0].table
    header = table.cell(0, 1)
    body = table.cell(1, 1)
    plain_header = table.cell(0, 0)
    plain_body = table.cell(1, 0)

    assert header.fill.fore_color.rgb == _rgb(theme.colors.accent_deep)
    assert plain_header.fill.fore_color.rgb == _rgb(theme.colors.accent)
    assert body.fill.fore_color.rgb == _rgb(theme.colors.accent_soft)
    assert plain_body.fill.fore_color.rgb == _rgb(theme.colors.surface)
    emphasis_run = body.text_frame.paragraphs[0].runs[0]
    plain_run = plain_body.text_frame.paragraphs[0].runs[0]
    assert emphasis_run.font.name == "Plus Jakarta Sans SemiBold"
    assert plain_run.font.name == "Plus Jakarta Sans"


def _latin_typeface(run) -> str:
    latin = run.font._element.find(qn("a:latin"))
    assert latin is not None
    return latin.get("typeface", "")


def _rgb(color: str) -> object:
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(color[1:])
