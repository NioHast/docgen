"""Test perakitan plan deterministik, row height, dan gate overflow."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from autooffice.deck.layout.grid import Grid
from autooffice.deck.layout.measure import measure_block, measure_code_text, measure_text
from autooffice.deck.layout.overflow import (
    LayoutOverflowError,
    assert_no_overflow,
    build_layout_plan,
    plan_deck,
    plan_overflow_keys,
    plan_slide,
)
from autooffice.deck.layout.presets import code as code_preset
from autooffice.deck.layout.slot import UnknownLayoutError
from autooffice.deck.layout.spec import LayoutSpec, PlacedBlock
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyBinding, KeyManifest, SlideIR


def _slide(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    body_text: str,
    *,
    with_note: bool = False,
    source: dict[str, str] | None = None,
) -> SlideIR:
    blocks = [
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("body", "text", fields={"text": body_text}, role="body"),
    ]
    if with_note:
        blocks.append(
            block_factory("note", "text", fields={"text": "Catatan singkat"}, role="caption")
        )
    return slide_factory(tuple(blocks), source=source)


def _layout_map(spec: LayoutSpec) -> dict[str, LayoutSpec]:
    return {spec.layout_id: spec}


def test_plan_is_deterministic_and_follows_grid(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
    grid: Grid,
) -> None:
    slide = _slide(block_factory, slide_factory, "Isi singkat")
    deck = deck_factory((slide,))
    layouts = _layout_map(demo_spec)

    first = plan_deck(deck, theme, layouts=layouts)
    second = plan_deck(deck, theme, layouts=layouts)

    assert first == second
    assert len(first.slides) == 1
    title_box, body_box = first.slides[0].boxes
    full_width = grid.span_width(12)
    title_measurement = measure_block(
        slide.blocks[0],
        width_emu=full_width,
        theme=theme,
    )
    body_width = grid.span_width(6)
    body_measurement = measure_block(
        slide.blocks[1],
        width_emu=body_width,
        theme=theme,
    )

    assert title_box == PlacedBlock(
        block_id="title",
        left_emu=grid.content_left_emu,
        top_emu=grid.content_top_emu,
        width_emu=full_width,
        height_emu=title_measurement.height_emu,
    )
    assert body_box.left_emu == grid.content_left_emu
    assert body_box.top_emu == (
        grid.content_top_emu + title_measurement.height_emu + grid.row_gap_emu
    )
    assert body_box.width_emu == body_width
    assert body_box.height_emu == body_measurement.height_emu
    assert first.slides[0].overflow_keys == ()


def test_row_height_uses_tallest_block_in_row(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
    grid: Grid,
) -> None:
    slide = _slide(block_factory, slide_factory, "Isi singkat", with_note=True)
    plan = plan_deck(deck_factory((slide,)), theme, layouts=_layout_map(demo_spec))
    body_box, note_box = plan.slides[0].boxes[1:]

    body_measurement = measure_block(
        slide.blocks[1],
        width_emu=grid.span_width(6),
        theme=theme,
    )
    note_measurement = measure_block(
        slide.blocks[2],
        width_emu=grid.span_width(6),
        theme=theme,
    )
    expected_height = max(body_measurement.height_emu, note_measurement.height_emu)

    assert body_box.width_emu == grid.span_width(6)
    assert note_box.left_emu == grid.column_left(6)
    assert body_box.height_emu == expected_height
    assert note_box.height_emu == expected_height


def test_asymmetric_preset_slots_use_slot_spans(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
    grid: Grid,
) -> None:
    asymmetric = replace(
        demo_spec,
        slots=(
            replace(demo_spec.slots[0], span=12),
            replace(demo_spec.slots[1], span=7),
            replace(demo_spec.slots[2], span=5),
        ),
    )
    slide = _slide(block_factory, slide_factory, "Isi singkat", with_note=True)

    plan = plan_deck(
        deck_factory((slide,)),
        theme,
        layouts=_layout_map(asymmetric),
    )
    body_box, note_box = plan.slides[0].boxes[1:]

    assert body_box.left_emu == grid.column_left(0)
    assert body_box.width_emu == grid.span_width(7)
    assert note_box.left_emu == grid.column_left(7)
    assert note_box.width_emu == grid.span_width(5)
    assert note_box.left_emu + note_box.width_emu == grid.content_right_emu


def test_missing_optional_slot_does_not_redistribute_span(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
    grid: Grid,
) -> None:
    asymmetric = replace(
        demo_spec,
        slots=(
            replace(demo_spec.slots[0], span=12),
            replace(demo_spec.slots[1], span=7),
            replace(demo_spec.slots[2], span=5),
        ),
    )
    slide = _slide(block_factory, slide_factory, "Isi singkat")

    plan = plan_deck(
        deck_factory((slide,)),
        theme,
        layouts=_layout_map(asymmetric),
    )
    body_box = plan.slides[0].boxes[1]

    assert body_box.width_emu == grid.span_width(7)


def test_source_is_not_placed_as_a_block(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    slide = _slide(
        block_factory,
        slide_factory,
        "Isi",
        source={"text": "Sumber internal"},
    )

    plan = plan_deck(deck_factory((slide,)), theme, layouts=_layout_map(demo_spec))

    assert tuple(box.block_id for box in plan.slides[0].boxes) == ("title", "body")


def test_horizontal_overflow_returns_keys_and_fails_default_gate(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
    grid: Grid,
) -> None:
    slide = _slide(block_factory, slide_factory, "W" * 400)
    deck = deck_factory((slide,))
    layouts = _layout_map(demo_spec)

    raw = plan_deck(deck, theme, layouts=layouts, fail_on_overflow=False)

    assert raw.slides[0].overflow_keys == ("s01.body.text",)
    assert raw.slides[0].boxes[1].width_emu == grid.span_width(6)
    assert raw.slides[0].boxes[1].height_emu > 0
    with pytest.raises(LayoutOverflowError) as error:
        plan_deck(deck, theme, layouts=layouts)
    assert error.value.overflow_keys == ("s01.body.text",)
    assert "slide 's01'" in str(error.value)
    assert "block 'body'" in str(error.value)
    assert "s01.body.text" in str(error.value)
    assert "EMU" in str(error.value)
    assert error.value.findings[0].estimated_overflow_emu > 0


def test_vertical_overflow_is_detected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    slide = _slide(block_factory, slide_factory, "\n".join(["baris"] * 1_000))
    deck = deck_factory((slide,))

    plan = plan_deck(deck, theme, layouts=_layout_map(demo_spec), fail_on_overflow=False)
    assert "s01.body.text" in plan.slides[0].overflow_keys
    with pytest.raises(LayoutOverflowError) as error:
        plan_deck(deck, theme, layouts=_layout_map(demo_spec))
    assert any(finding.kind == "tinggi" for finding in error.value.findings)


def test_build_layout_plan_and_assert_no_overflow_fail_on_overflow(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    slide = _slide(block_factory, slide_factory, "W" * 400)
    deck = deck_factory((slide,))
    layouts = _layout_map(demo_spec)
    raw = plan_deck(deck, theme, layouts=layouts, fail_on_overflow=False)

    with pytest.raises(LayoutOverflowError):
        build_layout_plan(deck, theme, layouts=layouts)
    with pytest.raises(LayoutOverflowError):
        assert_no_overflow(raw)
    assert plan_overflow_keys(raw) == ("s01.body.text",)


def test_clean_plan_passes_assert_no_overflow(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    deck = deck_factory((_slide(block_factory, slide_factory, "Isi singkat"),))

    plan = plan_deck(deck, theme, layouts=_layout_map(demo_spec))

    assert assert_no_overflow(plan) is plan
    assert plan_overflow_keys(plan) == ()


def test_assert_no_overflow_retains_findings_context(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    raw = plan_deck(
        deck_factory((_slide(block_factory, slide_factory, "W" * 400),)),
        theme,
        layouts=_layout_map(demo_spec),
        fail_on_overflow=False,
    )

    with pytest.raises(LayoutOverflowError) as error:
        assert_no_overflow(raw)

    assert error.value.findings
    assert "slide 's01'" in str(error.value)
    assert "block 'body'" in str(error.value)
    assert "EMU" in str(error.value)


def test_code_plan_box_has_room_for_filename_and_code(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme,
    grid: Grid,
) -> None:
    code_text = "def key():\n    return 1"
    filename = "keys.py"
    title = block_factory("title", "text", fields={"text": "Kode"}, role="title")
    code = block_factory(
        "code1",
        "code",
        fields={"code": code_text, "filename": filename},
    )
    slide = slide_factory((title, code), layout="code")
    plan = plan_deck(
        deck_factory((slide,)),
        theme,
        layouts={"code": code_preset.LAYOUT},
    )
    code_box = plan.slides[0].boxes[1]
    width = grid.span_width(12)
    measurement = measure_block(code, width_emu=width, theme=theme)
    filename_height = measure_text(
        filename,
        available_width_emu=width - 2 * theme.spacing.card_padding_emu,
        theme=theme,
        font_size_pt=max(theme.typography.body_pt, theme.typography.minimum_pt),
        weight=600,
    ).height_emu
    code_height = measure_code_text(
        code_text,
        available_width_emu=width - 2 * theme.spacing.card_padding_emu,
        theme=theme,
    ).height_emu

    assert plan.slides[0].overflow_keys == ()
    assert code_box.height_emu == measurement.height_emu
    inner_height = code_box.height_emu - 2 * theme.spacing.card_padding_emu
    assert inner_height >= filename_height + theme.spacing.sm_emu + code_height


def test_manifest_key_is_used_for_overflow(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    slide = _slide(block_factory, slide_factory, "W" * 400)
    manifest = KeyManifest(
        bindings=(
            KeyBinding(
                key="s01.body.text",
                slide_id="s01",
                block_id="body",
                leaf="text",
                kind="text",
                sync=True,
                yaml_path=("slides", 0, "blocks", 1, "text"),
                value="W" * 400,
                plain_text="W" * 400,
            ),
        )
    )
    deck = deck_factory((slide,), keys=manifest)

    raw = plan_deck(deck, theme, layouts=_layout_map(demo_spec), fail_on_overflow=False)

    assert raw.slides[0].overflow_keys == ("s01.body.text",)


def test_unknown_layout_is_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme,
) -> None:
    slide = _slide(block_factory, slide_factory, "Isi")

    with pytest.raises(UnknownLayoutError, match="demo"):
        plan_deck(deck_factory((slide,)), theme, layouts={})


def test_custom_layout_is_planned_without_a_preset_spec(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme,
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    slide = slide_factory((block,), layout="custom", rows=(("body",),))

    plan = plan_deck(deck_factory((slide,)), theme, layouts={})

    assert tuple(box.block_id for box in plan.slides[0].boxes) == ("body",)
    assert plan.slides[0].overflow_keys == ()


def test_plan_slide_returns_overflow_keys_without_raising(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
    theme,
) -> None:
    slide = _slide(block_factory, slide_factory, "W" * 400)

    layout = plan_slide(slide, demo_spec, theme)

    assert layout.overflow_keys == ("s01.body.text",)
