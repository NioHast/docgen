"""Tes cabang edge tabel native: validasi, caption, dan border berulang."""

from types import SimpleNamespace

import pytest
from _edge_helpers import new_slide
from lxml import etree
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement

from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError
from autooffice.deck.render.pptx.table import (
    _looks_numeric,
    _remove_table_style,
    _set_cell_borders,
    render_table_block,
    set_table_cell_key,
    table_cell_key,
)


def _render(block: BlockIR, box: Box, theme, slide=None):
    return render_table_block(
        new_slide() if slide is None else slide,
        block,
        box,
        theme,
        slide_id="s01",
    )


def test_table_cell_key_returns_none_without_tc_pr() -> None:
    cell = SimpleNamespace(_tc=SimpleNamespace(tcPr=None))

    assert table_cell_key(cell) is None


def test_set_table_cell_key_rejects_empty_key() -> None:
    with pytest.raises(PptxRenderError, match="Key sel tabel tidak boleh kosong"):
        set_table_cell_key(SimpleNamespace(), "")


def test_render_table_block_rejects_empty_columns(theme) -> None:
    block = BlockIR("t1", "table", None, None, {"columns": (), "rows": (("a",),)})

    with pytest.raises(PptxRenderError, match="tidak memiliki kolom"):
        _render(block, Box(left=0, top=0, width=4_000_000, height=2_000_000), theme)


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


def test_remove_table_style_ignores_missing_tbl_pr() -> None:
    element = etree.Element(qn("p:graphicFrame"))
    marker = etree.SubElement(element, qn("p:extLst"))

    _remove_table_style(SimpleNamespace(_element=element))

    assert element.find(qn("p:extLst")) is marker
    assert element.find(".//" + qn("a:tblPr")) is None


def test_remove_table_style_removes_existing_style_id() -> None:
    element = etree.Element(qn("p:graphicFrame"))
    tbl_pr = etree.SubElement(element, qn("a:tblPr"))
    style_id = etree.SubElement(tbl_pr, qn("a:tableStyleId"))
    style_id.text = "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"
    marker = etree.SubElement(tbl_pr, qn("a:extLst"))

    _remove_table_style(SimpleNamespace(_element=element))

    assert tbl_pr.find(qn("a:tableStyleId")) is None
    assert tbl_pr.find(qn("a:extLst")) is marker


def test_remove_table_style_ignores_missing_style_id() -> None:
    element = etree.Element(qn("p:graphicFrame"))
    etree.SubElement(element, qn("a:tblPr"))

    _remove_table_style(SimpleNamespace(_element=element))

    assert element.find(".//" + qn("a:tableStyleId")) is None


def test_set_cell_borders_replaces_existing_lines(theme) -> None:
    tc_pr = OxmlElement("a:tcPr")

    _set_cell_borders(tc_pr, theme)
    _set_cell_borders(tc_pr, theme)

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
