"""Test kontrak slot, role, source, dan penolakan authoring absolute."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from autooffice.deck.layout.presets import bars
from autooffice.deck.layout.slot import (
    SlotValidationError,
    assign_slide_blocks,
    validate_slide,
)
from autooffice.deck.layout.spec import LayoutSpec, LayoutSpecError, SlotSpec
from autooffice.deck.model.deck_ir import BlockIR, SlideIR


def _blocks(block_factory: Callable[..., BlockIR]) -> tuple[BlockIR, ...]:
    return (
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("body", "text", fields={"text": "Isi"}, role="body"),
    )


def test_required_slot_missing_is_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    slide = slide_factory((block_factory("title", "text", fields={"text": "Judul"}, role="title"),))

    with pytest.raises(SlotValidationError, match=r"Slot wajib.*body"):
        validate_slide(slide, demo_spec)


def test_optional_slot_may_be_absent(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    slide = slide_factory(_blocks(block_factory))

    assignments = validate_slide(slide, demo_spec)

    assert tuple(item.slot.slot_id for item in assignments) == ("title", "body")


def test_optional_slot_is_placed_in_row_order(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    blocks = (
        *_blocks(block_factory),
        block_factory("note", "text", fields={"text": "Catatan"}, role="caption"),
    )

    assignments = assign_slide_blocks(slide_factory(blocks), demo_spec)

    assert tuple(item.slot.slot_id for item in assignments) == ("title", "body", "note")


def test_block_outside_slot_is_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    blocks = (
        *_blocks(block_factory),
        block_factory("extra", "text", fields={"text": "Luar"}, role="body"),
    )

    with pytest.raises(SlotValidationError, match="di luar slot"):
        validate_slide(slide_factory(blocks), demo_spec)


def test_block_type_must_be_allowed_by_slot(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    blocks = (
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("body", "image", fields={"path": "x.png", "alt": "X"}),
    )

    with pytest.raises(SlotValidationError, match="tidak diterima slot 'body'"):
        validate_slide(slide_factory(blocks), demo_spec)


def test_role_must_match_slot(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    blocks = (
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("body", "text", fields={"text": "Isi"}, role="caption"),
    )

    with pytest.raises(SlotValidationError, match="membutuhkan role 'body'"):
        validate_slide(slide_factory(blocks), demo_spec)


def test_preset_span_is_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    blocks = (
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("body", "text", fields={"text": "Isi"}, role="body", span=6),
    )

    with pytest.raises(SlotValidationError, match="tidak boleh memiliki span"):
        validate_slide(slide_factory(blocks), demo_spec)


def test_source_requires_accepting_layout(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    slide = slide_factory(_blocks(block_factory), source={"text": "Sumber internal"})

    with pytest.raises(SlotValidationError, match="tidak menerima source"):
        validate_slide(slide, replace(demo_spec, accepts_source=False))


def test_source_is_not_a_slot_assignment(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    slide = slide_factory(
        _blocks(block_factory),
        source={"text": "Sumber internal", "url": "https://example.com"},
    )

    assignments = validate_slide(slide, demo_spec)

    assert tuple(item.slot.slot_id for item in assignments) == ("title", "body")
    assert all(item.slot.slot_id != "source" for item in assignments)


def test_notes_are_not_a_slot(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    slide = slide_factory(_blocks(block_factory), notes="Catatan pembicara")

    assignments = validate_slide(slide, demo_spec)

    assert tuple(item.slot.slot_id for item in assignments) == ("title", "body")


def _chart_blocks(
    block_factory: Callable[..., BlockIR],
    kind: object,
) -> tuple[BlockIR, ...]:
    return (
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("chart1", "chart", fields={"kind": kind}),
    )


def test_preset_chart_kind_rejects_mismatched_chart(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
) -> None:
    slide = slide_factory(_chart_blocks(block_factory, "line"), layout="bars")

    with pytest.raises(
        LayoutSpecError,
        match=r"Slide 's01' block 'chart1' pada slot 'chart1'.*'line'.*'bar'",
    ):
        validate_slide(slide, bars.LAYOUT)


def test_preset_chart_kind_accepts_matching_chart(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
) -> None:
    slide = slide_factory(_chart_blocks(block_factory, "bar"), layout="bars")

    assignments = validate_slide(slide, bars.LAYOUT)

    assert tuple(item.slot.slot_id for item in assignments) == ("title", "chart1")


def test_slot_without_chart_kind_ignores_chart_kind(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
) -> None:
    spec = LayoutSpec(
        layout_id="chart-only",
        slots=(SlotSpec(slot_id="chart1", required=True, block_types=("chart",)),),
        rows=(("chart1",),),
        accepts_source=True,
    )
    slide = slide_factory(
        (block_factory("chart1", "chart", fields={"kind": "line"}),),
        layout="chart-only",
    )

    assignments = validate_slide(slide, spec)

    assert tuple(item.slot.slot_id for item in assignments) == ("chart1",)


def test_chart_kind_is_ignored_for_non_chart_block(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
) -> None:
    spec = LayoutSpec(
        layout_id="text-only",
        slots=(
            SlotSpec(
                slot_id="body",
                required=True,
                block_types=("text",),
                chart_kind="bar",
            ),
        ),
        rows=(("body",),),
        accepts_source=True,
    )
    slide = slide_factory(
        (block_factory("body", "text", fields={"text": "Isi"}),),
        layout="text-only",
    )

    assignments = validate_slide(slide, spec)

    assert tuple(item.slot.slot_id for item in assignments) == ("body",)


def test_absolute_geometry_field_is_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    blocks = (
        block_factory("title", "text", fields={"text": "Judul"}, role="title"),
        block_factory("body", "text", fields={"text": "Isi", "x": 10}, role="body"),
    )

    with pytest.raises(SlotValidationError, match="geometri terlarang: x"):
        validate_slide(slide_factory(blocks), demo_spec)


def test_layout_spec_unknown_row_slot_is_rejected() -> None:
    with pytest.raises(LayoutSpecError, match="tidak dikenal: hantu"):
        LayoutSpec(
            layout_id="rusak",
            slots=(SlotSpec(slot_id="title", required=True, block_types=("text",), role="title"),),
            rows=(("title", "hantu"),),
            accepts_source=True,
        )


def test_layout_spec_missing_slot_from_rows_is_rejected() -> None:
    spec = LayoutSpec(
        layout_id="rusak",
        slots=(SlotSpec(slot_id="title", required=True, block_types=("text",), role=None),),
        rows=(("title",),),
        accepts_source=True,
    )

    with pytest.raises(LayoutSpecError, match="tidak menempatkan slot di rows: body"):
        replace(
            spec,
            slots=(
                *spec.slots,
                SlotSpec(slot_id="body", required=True, block_types=("text",), role=None),
            ),
        )


def test_layout_spec_duplicate_row_slot_is_rejected() -> None:
    with pytest.raises(LayoutSpecError, match="lebih dari sekali"):
        LayoutSpec(
            layout_id="rusak",
            slots=(SlotSpec(slot_id="title", required=True, block_types=("text",), role=None),),
            rows=(("title", "title"),),
            accepts_source=True,
        )


def test_row_may_not_have_more_than_twelve_slots() -> None:
    slots = tuple(
        SlotSpec(slot_id=f"slot{index}", required=True, block_types=("text",), role=None)
        for index in range(13)
    )

    with pytest.raises(LayoutSpecError, match="maksimal 12 kolom"):
        LayoutSpec(
            layout_id="rusak",
            slots=slots,
            rows=(tuple(slot.slot_id for slot in slots),),
            accepts_source=True,
        )


@pytest.mark.parametrize("span", [0, 13])
def test_layout_spec_slot_span_outside_one_to_twelve_is_rejected(span: int) -> None:
    with pytest.raises(LayoutSpecError, match="span harus 1 sampai 12"):
        LayoutSpec(
            layout_id="rusak",
            slots=(
                SlotSpec(
                    slot_id="title",
                    required=True,
                    block_types=("text",),
                    role=None,
                    span=span,
                ),
            ),
            rows=(("title",),),
            accepts_source=True,
        )


def test_layout_spec_row_span_sum_over_twelve_is_rejected() -> None:
    with pytest.raises(LayoutSpecError, match="maksimal 12 kolom"):
        LayoutSpec(
            layout_id="rusak",
            slots=(
                SlotSpec(
                    slot_id="left",
                    required=True,
                    block_types=("text",),
                    role=None,
                    span=7,
                ),
                SlotSpec(
                    slot_id="right",
                    required=True,
                    block_types=("text",),
                    role=None,
                    span=6,
                ),
            ),
            rows=(("left", "right"),),
            accepts_source=True,
        )


def test_layout_spec_min_one_of_unknown_slot_is_rejected() -> None:
    with pytest.raises(LayoutSpecError, match=r"min_one_of.*tidak dikenal: hantu"):
        LayoutSpec(
            layout_id="rusak",
            slots=(SlotSpec(slot_id="title", required=True, block_types=("text",), role=None),),
            rows=(("title",),),
            accepts_source=True,
            min_one_of=(("title", "hantu"),),
        )


def test_layout_spec_min_one_of_empty_group_is_rejected() -> None:
    with pytest.raises(LayoutSpecError, match=r"min_one_of group 0 yang kosong"):
        LayoutSpec(
            layout_id="rusak",
            slots=(SlotSpec(slot_id="title", required=True, block_types=("text",), role=None),),
            rows=(("title",),),
            accepts_source=True,
            min_one_of=((),),
        )


def test_layout_spec_min_one_of_duplicate_slot_across_groups_is_rejected() -> None:
    with pytest.raises(LayoutSpecError, match=r"slot duplikat di min_one_of: note"):
        LayoutSpec(
            layout_id="rusak",
            slots=(
                SlotSpec(slot_id="title", required=True, block_types=("text",), role=None),
                SlotSpec(slot_id="body", required=False, block_types=("text",), role=None),
                SlotSpec(slot_id="note", required=False, block_types=("text",), role=None),
            ),
            rows=(("title",), ("body", "note")),
            accepts_source=True,
            min_one_of=(("body", "note"), ("note",)),
        )


def _spec_with(**overrides: object) -> LayoutSpec:
    values: dict[str, object] = {
        "layout_id": "demo",
        "slots": (SlotSpec(slot_id="title", required=True, block_types=("text",), role="title"),),
        "rows": (("title",),),
        "accepts_source": True,
    }
    values.update(overrides)
    return LayoutSpec(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"layout_id": ""}, "layout_id tidak boleh kosong"),
        ({"rows": ()}, "minimal satu row"),
        ({"slots": ()}, "tidak memiliki slot"),
        ({"accepts_source": "yes"}, "bukan bool"),
    ],
)
def test_layout_spec_requires_core_contract(
    overrides: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(LayoutSpecError, match=match):
        _spec_with(**overrides)


@pytest.mark.parametrize(
    ("slot", "match"),
    [
        (SlotSpec("", True, ("text",)), "slot tanpa slot_id"),
        (SlotSpec("title", True, ()), "minimal satu block type"),
        (SlotSpec("title", True, ("text", "")), "block type kosong"),
        (SlotSpec("title", True, ("text",), role=""), "role kosong"),
    ],
)
def test_layout_spec_rejects_invalid_slot_definition(
    slot: SlotSpec,
    match: str,
) -> None:
    with pytest.raises(LayoutSpecError, match=match):
        _spec_with(slots=(slot,))


@pytest.mark.parametrize("chart_kind", ["pie", "", 1, True])
def test_layout_spec_rejects_invalid_chart_kind(chart_kind: object) -> None:
    slot = SlotSpec(
        slot_id="title",
        required=True,
        block_types=("text",),
        role="title",
        chart_kind=chart_kind,  # type: ignore[arg-type]
    )

    with pytest.raises(LayoutSpecError, match="chart_kind"):
        _spec_with(slots=(slot,))


def test_layout_spec_duplicate_slot_ids_are_rejected() -> None:
    duplicate = SlotSpec(slot_id="title", required=True, block_types=("text",), role="title")

    with pytest.raises(LayoutSpecError, match="slot duplikat: title"):
        _spec_with(slots=(duplicate, duplicate))


@pytest.mark.parametrize("span", [True, 6.0, "6"])
def test_layout_spec_rejects_non_integer_span(span: object) -> None:
    slot = SlotSpec(
        slot_id="title",
        required=True,
        block_types=("text",),
        role="title",
        span=span,  # type: ignore[arg-type]
    )

    with pytest.raises(LayoutSpecError, match="bilangan bulat"):
        _spec_with(slots=(slot,))


def test_layout_spec_min_one_of_rejects_empty_slot_id() -> None:
    with pytest.raises(LayoutSpecError, match="slot_id kosong"):
        _spec_with(min_one_of=(("",),))


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        (((),), r"Row 0 .*tidak boleh kosong"),
        ((("",),), "slot_id kosong"),
    ],
)
def test_layout_spec_rejects_empty_row_and_row_slot_id(
    rows: object,
    match: str,
) -> None:
    with pytest.raises(LayoutSpecError, match=match):
        _spec_with(rows=rows)


def test_slide_missing_every_min_one_of_slot_is_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
) -> None:
    spec = LayoutSpec(
        layout_id="demo",
        slots=(
            SlotSpec(
                slot_id="title",
                required=True,
                block_types=("text",),
                role="title",
            ),
            SlotSpec(
                slot_id="body",
                required=False,
                block_types=("text",),
                role="body",
            ),
            SlotSpec(
                slot_id="note",
                required=False,
                block_types=("text",),
                role="caption",
            ),
        ),
        rows=(("title",), ("body", "note")),
        accepts_source=True,
        min_one_of=(("body", "note"),),
    )
    slide = slide_factory((block_factory("title", "text", fields={"text": "Judul"}, role="title"),))

    with pytest.raises(LayoutSpecError, match=r"s01.*min_one_of.*body.*note"):
        validate_slide(slide, spec)
