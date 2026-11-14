"""Test paritas kotak code renderer PPTX dengan pengukuran layout."""

import pytest
from _edge_helpers import new_slide

from autooffice.deck.layout.measure import (
    code_line_count,
    code_text_width,
    line_number_gutter_width,
    measure_block,
    measure_code_text,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx.shapes import Box
from autooffice.deck.render.pptx.textbox import render_code_block


@pytest.mark.parametrize(
    "code",
    [
        "print(1)",
        "satu\ndua",
        "\r\ntiga\r\n",
        "\n".join("baris" for _ in range(9)),
        "\n".join("baris" for _ in range(10)),
        "\n".join("baris" for _ in range(99)),
        "\n".join("baris" for _ in range(100)),
    ],
    ids=[
        "single-line",
        "two-lines",
        "crlf",
        "nine-lines",
        "ten-lines",
        "ninety-nine-lines",
        "one-hundred-lines",
    ],
)
def test_measured_code_box_matches_rendered_code_box(theme, code: str) -> None:
    block = BlockIR("c1", "code", None, None, {"code": code, "line_numbers": True})
    box = Box(left=100, top=200, width=4_000_000, height=3_000_000)
    inner = box.inset(theme.spacing.card_padding_emu)
    gutter_width = line_number_gutter_width(
        code_line_count(code),
        theme=theme,
        available_width_emu=inner.width,
    )

    shapes = render_code_block(new_slide(), block, box, theme, slide_id="s01")
    names = {shape.name: shape for shape in shapes}
    numbers = names["chrome:code-lines:s01.c1"]
    code_shape = names["autooffice:key:s01.c1.code"]
    measurement = measure_block(block, width_emu=box.width, theme=theme)
    expected_code = measure_code_text(
        code,
        available_width_emu=code_shape.width,
        theme=theme,
    )

    assert code_shape.width == code_text_width(
        code,
        inner_width_emu=inner.width,
        theme=theme,
        line_numbers=True,
    )
    assert numbers.width == gutter_width
    assert code_shape.left == inner.left + gutter_width + theme.spacing.sm_emu
    assert code_shape.width + gutter_width + theme.spacing.sm_emu == inner.width
    assert measurement.line_count == expected_code.line_count
    assert measurement.width_emu == expected_code.width_emu
    assert measurement.height_emu == (expected_code.height_emu + 2 * theme.spacing.card_padding_emu)
