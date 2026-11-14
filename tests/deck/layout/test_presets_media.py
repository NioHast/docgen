"""Contract tests for the seven remaining preset layouts."""

from dataclasses import dataclass

import pytest

from autooffice.deck.layout.presets import (
    background,
    code,
    diagram,
    flow,
    image_full,
    image_grid,
    image_split,
)
from autooffice.deck.layout.registry import discover_layouts, layout_names
from autooffice.deck.layout.spec import LAYOUT_COLUMNS, LayoutSpec

ALLOWED_BLOCK_TYPES = frozenset({"code", "diagram", "image", "text"})


@dataclass(frozen=True, slots=True)
class PresetCase:
    layout: LayoutSpec
    layout_id: str
    slot_contract: tuple[tuple[str, bool, tuple[str, ...], str | None, int], ...]
    rows: tuple[tuple[str, ...], ...]


CASES = (
    PresetCase(
        layout=background.LAYOUT,
        layout_id="background",
        slot_contract=(
            ("kicker", False, ("text",), "kicker", 12),
            ("title", True, ("text",), "title", 12),
            ("lead", False, ("text",), "lead", 12),
            ("point1", True, ("text",), "body", 4),
            ("point2", True, ("text",), "body", 4),
            ("point3", True, ("text",), "body", 4),
        ),
        rows=(
            ("kicker",),
            ("title",),
            ("lead",),
            ("point1", "point2", "point3"),
        ),
    ),
    PresetCase(
        layout=flow.LAYOUT,
        layout_id="flow",
        slot_contract=(
            ("title", True, ("text",), "title", 12),
            ("lead", False, ("text",), "lead", 12),
            ("step1", True, ("text",), "body", 3),
            ("step2", True, ("text",), "body", 3),
            ("step3", True, ("text",), "body", 3),
            ("step4", True, ("text",), "body", 3),
        ),
        rows=(
            ("title",),
            ("lead",),
            ("step1", "step2", "step3", "step4"),
        ),
    ),
    PresetCase(
        layout=code.LAYOUT,
        layout_id="code",
        slot_contract=(
            ("title", True, ("text",), "title", 12),
            ("lead", False, ("text",), "lead", 12),
            ("code1", True, ("code",), None, 12),
            ("note", False, ("text",), "caption", 12),
        ),
        rows=(
            ("title",),
            ("lead",),
            ("code1",),
            ("note",),
        ),
    ),
    PresetCase(
        layout=diagram.LAYOUT,
        layout_id="diagram",
        slot_contract=(
            ("title", True, ("text",), "title", 12),
            ("subtitle", False, ("text",), "lead", 12),
            ("diagram1", True, ("diagram",), None, 12),
        ),
        rows=(
            ("title",),
            ("subtitle",),
            ("diagram1",),
        ),
    ),
    PresetCase(
        layout=image_split.LAYOUT,
        layout_id="image-split",
        slot_contract=(
            ("title", True, ("text",), "title", 12),
            ("lead", False, ("text",), "lead", 12),
            ("body", True, ("text",), "body", 7),
            ("image1", True, ("image",), None, 5),
        ),
        rows=(
            ("title",),
            ("lead",),
            ("body", "image1"),
        ),
    ),
    PresetCase(
        layout=image_full.LAYOUT,
        layout_id="image-full",
        slot_contract=(
            ("title", True, ("text",), "title", 12),
            ("image1", True, ("image",), None, 12),
            ("subtitle", False, ("text",), "lead", 12),
            ("credit", False, ("text",), "caption", 12),
        ),
        rows=(
            ("title",),
            ("image1",),
            ("subtitle",),
            ("credit",),
        ),
    ),
    PresetCase(
        layout=image_grid.LAYOUT,
        layout_id="image-grid",
        slot_contract=(
            ("title", True, ("text",), "title", 12),
            ("lead", False, ("text",), "lead", 12),
            ("image1", True, ("image",), None, 4),
            ("image2", True, ("image",), None, 4),
            ("image3", True, ("image",), None, 4),
        ),
        rows=(
            ("title",),
            ("lead",),
            ("image1", "image2", "image3"),
        ),
    ),
)

CASE_IDS = [case.layout_id for case in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_layout_id_and_slots_match_contract(case: PresetCase) -> None:
    assert case.layout.layout_id == case.layout_id
    actual = tuple(
        (slot.slot_id, slot.required, slot.block_types, slot.role, slot.span)
        for slot in case.layout.slots
    )
    assert actual == case.slot_contract


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_required_flags_match_contract(case: PresetCase) -> None:
    actual = tuple((slot.slot_id, slot.required) for slot in case.layout.slots)
    expected = tuple((slot_id, required) for slot_id, required, *_ in case.slot_contract)
    assert actual == expected


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_rows_match_contract(case: PresetCase) -> None:
    assert case.layout.rows == case.rows


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_rows_fit_twelve_column_grid(case: PresetCase) -> None:
    slots_by_id = {slot.slot_id: slot for slot in case.layout.slots}
    placed = tuple(slot_id for row in case.layout.rows for slot_id in row)

    assert all(row for row in case.layout.rows)
    assert sorted(placed) == sorted(slots_by_id)
    assert len(placed) == len(set(placed))
    assert all(1 <= slot.span <= LAYOUT_COLUMNS for slot in case.layout.slots)
    for row in case.layout.rows:
        total = sum(slots_by_id[slot_id].span for slot_id in row)
        assert total <= LAYOUT_COLUMNS


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_presets_use_only_known_block_types(case: PresetCase) -> None:
    for slot in case.layout.slots:
        assert set(slot.block_types) <= ALLOWED_BLOCK_TYPES
        assert "callout" not in slot.block_types


def test_all_remaining_presets_accept_source() -> None:
    assert all(case.layout.accepts_source for case in CASES)


def test_registry_discovers_all_seven_presets() -> None:
    discovered = {layout.layout_id: layout for layout in discover_layouts()}
    names = layout_names()

    for case in CASES:
        assert discovered[case.layout_id] == case.layout
        assert case.layout_id in names

    discovered_ids = tuple(layout.layout_id for layout in discover_layouts())
    assert discovered_ids == tuple(sorted(discovered_ids))
