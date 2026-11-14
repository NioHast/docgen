"""Test pengukuran code dengan gutter nomor baris seperti renderer PPTX."""

from collections.abc import Callable
from dataclasses import replace

from autooffice.deck.layout.custom import plan_custom_slide_with_findings
from autooffice.deck.layout.grid import Grid
from autooffice.deck.layout.measure import (
    code_text_width,
    measure_block,
    measure_code_text,
)
from autooffice.deck.model.deck_ir import BlockIR, SlideIR
from autooffice.design.theme import Theme

WIDTH = 2_000_000


def _inner_width(theme: Theme, width: int = WIDTH) -> int:
    return width - 2 * theme.spacing.card_padding_emu


def _custom_slide(block: BlockIR) -> SlideIR:
    return SlideIR(
        slide_id="s01",
        layout="custom",
        order=0,
        blocks=(block,),
        notes=None,
        source=None,
        rows=((block.block_id,),),
    )


def test_line_numbers_reduce_capacity_and_add_wrapped_lines(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    inner = _inner_width(theme)
    character_width = measure_code_text("x", available_width_emu=inner, theme=theme).width_emu
    capacity = inner // character_width
    code = "x" * capacity
    plain = block_factory(
        "code1",
        "code",
        span=12,
        fields={"code": code, "line_numbers": False},
    )
    numbered = block_factory(
        "code2",
        "code",
        span=12,
        fields={"code": code, "line_numbers": True},
    )

    plain_width = code_text_width(
        code,
        inner_width_emu=inner,
        theme=theme,
        line_numbers=False,
    )
    numbered_width = code_text_width(
        code,
        inner_width_emu=inner,
        theme=theme,
        line_numbers=True,
    )
    plain_measurement = measure_block(plain, width_emu=WIDTH, theme=theme)
    numbered_measurement = measure_block(numbered, width_emu=WIDTH, theme=theme)

    assert numbered_width < plain_width
    assert numbered_width // character_width < capacity
    assert plain_measurement.line_count == 1
    assert numbered_measurement.line_count > plain_measurement.line_count
    assert numbered_measurement.height_emu > plain_measurement.height_emu


def test_code_without_line_numbers_field_uses_renderer_default(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    code = "x" * 200
    missing = block_factory("code1", "code", fields={"code": code})
    explicit_true = block_factory(
        "code2",
        "code",
        fields={"code": code, "line_numbers": True},
    )
    explicit_false = block_factory(
        "code3",
        "code",
        fields={"code": code, "line_numbers": False},
    )

    assert measure_block(missing, width_emu=WIDTH, theme=theme) == measure_block(
        explicit_true,
        width_emu=WIDTH,
        theme=theme,
    )
    assert measure_block(missing, width_emu=WIDTH, theme=theme).line_count > (
        measure_block(explicit_false, width_emu=WIDTH, theme=theme).line_count
    )


def test_numbered_code_overflow_is_not_missed_by_custom_layout(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    base = Grid.from_theme(theme)
    width = base.span_width(12)
    inner = width - 2 * theme.spacing.card_padding_emu
    character_width = measure_code_text("x", available_width_emu=inner, theme=theme).width_emu
    capacity = inner // character_width
    code = "x" * capacity
    plain = block_factory(
        "code1",
        "code",
        span=12,
        fields={"code": code, "line_numbers": False},
    )
    numbered = block_factory(
        "code1",
        "code",
        span=12,
        fields={"code": code, "line_numbers": True},
    )
    plain_height = measure_block(plain, width_emu=width, theme=theme).height_emu
    numbered_height = measure_block(numbered, width_emu=width, theme=theme).height_emu
    grid = replace(
        base,
        slide_height_emu=base.margin_top_emu + plain_height + base.margin_bottom_emu,
    )

    plain_plan = plan_custom_slide_with_findings(_custom_slide(plain), theme, grid=grid)
    numbered_plan = plan_custom_slide_with_findings(
        _custom_slide(numbered),
        theme,
        grid=grid,
    )

    assert numbered_height > plain_height
    assert plain_plan.layout.overflow_keys == ()
    assert numbered_plan.layout.overflow_keys == ("s01.code1.code",)
