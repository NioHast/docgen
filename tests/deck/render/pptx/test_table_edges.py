"""Tes cabang edge tabel native: validasi, caption, dan border berulang."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from _edge_helpers import new_slide
from pptx.oxml.ns import qn

from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError, collect_render_warnings
from autooffice.deck.render.pptx.table import (
    _looks_numeric,
    render_table_block,
    set_table_cell_key,
)


def _render(block: BlockIR, box: Box, theme, slide=None):
    return render_table_block(
        new_slide() if slide is None else slide,
        block,
        box,
        theme,
        slide_id="s01",
    )


def test_set_table_cell_key_rejects_empty_key() -> None:
    with pytest.raises(PptxRenderError, match="Key sel tabel tidak boleh kosong"):
        set_table_cell_key(SimpleNamespace(), "")


def test_render_table_block_rejects_empty_columns(theme) -> None:
    block = BlockIR("t1", "table", None, None, {"columns": (), "rows": (("a",),)})

    with pytest.raises(PptxRenderError, match="tidak memiliki kolom"):
        _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), theme)


def test_render_table_block_collects_font_weight_fallback_warning(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A",), "rows": (("1",),)},
    )
    fallback_theme = replace(theme, typography=replace(theme.typography, family="Inter"))

    with collect_render_warnings() as warnings:
        _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), fallback_theme)

    assert any("font-weight" in warning for warning in warnings)


def test_render_table_block_rejects_empty_rows(theme) -> None:
    block = BlockIR("t1", "table", None, None, {"columns": ("A",), "rows": ()})

    with pytest.raises(PptxRenderError, match="tidak memiliki baris"):
        _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), theme)


def test_render_table_block_rejects_row_width_mismatch(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A", "B"), "rows": (("hanya-satu",),)},
    )

    with pytest.raises(PptxRenderError, match="baris 1 memiliki 1 sel"):
        _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), theme)


def test_render_table_block_without_caption_returns_only_frame(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A", "B"), "rows": (("1", "2"),)},
    )

    shapes = _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), theme)

    assert len(shapes) == 1
    assert shapes[0].has_table is True


def test_render_table_block_rejects_caption_without_room(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A",), "rows": (("1",),), "caption": "Caption panjang"},
    )
    padding = theme.spacing.card_padding_emu
    box = Box(left=0, top=0, width=4_000_000, height=padding * 2 + 1)

    with pytest.raises(PptxRenderError, match="tidak memiliki ruang untuk tabel"):
        _render(block, box, theme)


def test_render_table_block_removes_default_table_style(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A", "B"), "rows": (("1", "2"),)},
    )

    shapes = _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), theme)
    element = shapes[0]._element

    assert element.find(".//" + qn("a:tblPr")) is not None
    assert element.find(".//" + qn("a:tableStyleId")) is None


def test_render_table_block_writes_one_border_per_cell_side(theme) -> None:
    block = BlockIR(
        "t1",
        "table",
        None,
        None,
        {"columns": ("A", "B"), "rows": (("1", "2"),)},
    )

    shapes = _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), theme)
    tc_pr = shapes[0].table.cell(0, 0)._tc.get_or_add_tcPr()

    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        assert len(tc_pr.findall(qn(tag))) == 1


def test_looks_numeric_returns_false_for_empty_candidate() -> None:
    assert _looks_numeric("%%") is False


@pytest.mark.parametrize("value", ["1,234,56", "1.234.56", "1,234,567,89"])
def test_looks_numeric_rejects_reused_thousands_separator(value: str) -> None:
    assert _looks_numeric(value) is False


@pytest.mark.parametrize("value", ["1234", "1,234", "1.234,56", "1,234.56", "12%"])
def test_looks_numeric_accepts_real_numbers(value: str) -> None:
    assert _looks_numeric(value) is True
