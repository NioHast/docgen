"""Kontrak preset layout data: bars, line, donut, table, comparison, matrix."""

import pytest

from autooffice.deck.layout.presets import bars, comparison, donut, line, matrix, table
from autooffice.deck.layout.registry import discover_layouts
from autooffice.deck.layout.spec import LayoutSpec

DATA_LAYOUTS = (
    bars.LAYOUT,
    line.LAYOUT,
    donut.LAYOUT,
    table.LAYOUT,
    comparison.LAYOUT,
    matrix.LAYOUT,
)

EXPECTED_SLOTS: dict[
    str, tuple[tuple[str, bool, tuple[str, ...], str | None, int, str | None], ...]
] = {
    "bars": (
        ("title", True, ("text",), "title", 12, None),
        ("lead", False, ("text",), "lead", 12, None),
        ("chart1", True, ("chart",), None, 7, "bar"),
        ("note", False, ("text",), "caption", 5, None),
    ),
    "line": (
        ("title", True, ("text",), "title", 12, None),
        ("lead", False, ("text",), "lead", 12, None),
        ("chart1", True, ("chart",), None, 7, "line"),
        ("note", False, ("text",), "caption", 5, None),
    ),
    "donut": (
        ("title", True, ("text",), "title", 12, None),
        ("lead", False, ("text",), "lead", 12, None),
        ("chart1", True, ("chart",), None, 7, "donut"),
        ("legend", False, ("bullets",), None, 5, None),
        ("note", False, ("text",), "caption", 12, None),
    ),
    "table": (
        ("title", True, ("text",), "title", 12, None),
        ("lead", False, ("text",), "lead", 12, None),
        ("table1", True, ("table",), None, 12, None),
        ("note", False, ("text",), "caption", 12, None),
    ),
    "comparison": (
        ("title", True, ("text",), "title", 12, None),
        ("lead", False, ("text",), "lead", 12, None),
        ("table1", True, ("table",), None, 12, None),
        ("note", False, ("text",), "caption", 12, None),
    ),
    "matrix": (
        ("title", True, ("text",), "title", 12, None),
        ("lead", False, ("text",), "lead", 12, None),
        ("matrix1", True, ("table",), None, 7, None),
        ("legend", False, ("bullets",), None, 5, None),
        ("note", False, ("text",), "caption", 12, None),
    ),
}

EXPECTED_ROWS: dict[str, tuple[tuple[str, ...], ...]] = {
    "bars": (("title",), ("lead",), ("chart1", "note")),
    "line": (("title",), ("lead",), ("chart1", "note")),
    "donut": (("title",), ("lead",), ("chart1", "legend"), ("note",)),
    "table": (("title",), ("lead",), ("table1",), ("note",)),
    "comparison": (("title",), ("lead",), ("table1",), ("note",)),
    "matrix": (("title",), ("lead",), ("matrix1", "legend"), ("note",)),
}


def test_layout_ids_match_expected_catalog() -> None:
    assert tuple(layout.layout_id for layout in DATA_LAYOUTS) == tuple(EXPECTED_SLOTS)


@pytest.mark.parametrize("layout", DATA_LAYOUTS, ids=lambda layout: layout.layout_id)
def test_slots_match_contract(layout: LayoutSpec) -> None:
    actual = tuple(
        (
            slot.slot_id,
            slot.required,
            slot.block_types,
            slot.role,
            slot.span,
            slot.chart_kind,
        )
        for slot in layout.slots
    )
    assert actual == EXPECTED_SLOTS[layout.layout_id]


@pytest.mark.parametrize("layout", DATA_LAYOUTS, ids=lambda layout: layout.layout_id)
def test_rows_match_contract(layout: LayoutSpec) -> None:
    assert layout.rows == EXPECTED_ROWS[layout.layout_id]


@pytest.mark.parametrize("layout", DATA_LAYOUTS, ids=lambda layout: layout.layout_id)
def test_row_spans_fit_twelve_column_grid(layout: LayoutSpec) -> None:
    slots_by_id = {slot.slot_id: slot for slot in layout.slots}
    placed = [slot_id for row in layout.rows for slot_id in row]
    assert all(row for row in layout.rows)
    assert sorted(placed) == sorted(slots_by_id)
    assert len(placed) == len(set(placed))
    for row in layout.rows:
        total = sum(slots_by_id[slot_id].span for slot_id in row)
        assert total <= 12


@pytest.mark.parametrize("layout", DATA_LAYOUTS, ids=lambda layout: layout.layout_id)
def test_data_layouts_accept_source(layout: LayoutSpec) -> None:
    assert layout.accepts_source is True


def test_registry_discovers_all_data_presets() -> None:
    registry = {layout.layout_id: layout for layout in discover_layouts()}
    assert set(EXPECTED_SLOTS) <= set(registry)
    for layout in DATA_LAYOUTS:
        assert registry[layout.layout_id] == layout
