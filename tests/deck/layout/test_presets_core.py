"""Contract tests for the six core F2 preset layouts."""

from dataclasses import dataclass

import pytest

from autooffice.deck.layout.presets.closing import LAYOUT as CLOSING_LAYOUT
from autooffice.deck.layout.presets.content import LAYOUT as CONTENT_LAYOUT
from autooffice.deck.layout.presets.cover import LAYOUT as COVER_LAYOUT
from autooffice.deck.layout.presets.kpi import LAYOUT as KPI_LAYOUT
from autooffice.deck.layout.presets.section import LAYOUT as SECTION_LAYOUT
from autooffice.deck.layout.presets.toc import LAYOUT as TOC_LAYOUT
from autooffice.deck.layout.registry import discover_layouts, layout_names
from autooffice.deck.layout.slot import validate_slide
from autooffice.deck.layout.spec import LAYOUT_COLUMNS, LayoutSpec
from autooffice.deck.model.deck_ir import BlockIR, SlideIR

ALLOWED_BLOCK_TYPES = frozenset({"bullets", "metric", "text"})


@dataclass(frozen=True, slots=True)
class PresetCase:
    layout: LayoutSpec
    layout_id: str
    slot_ids: tuple[str, ...]
    required: frozenset[str]
    min_one_of: tuple[tuple[str, ...], ...]
    block_types: tuple[tuple[str, tuple[str, ...]], ...]
    roles: tuple[tuple[str, str | None], ...]


CASES = (
    PresetCase(
        layout=COVER_LAYOUT,
        layout_id="cover",
        slot_ids=("kicker", "title", "subtitle", "author", "role", "summary"),
        required=frozenset({"title", "author"}),
        min_one_of=(),
        block_types=(
            ("kicker", ("text",)),
            ("title", ("text",)),
            ("subtitle", ("text",)),
            ("author", ("text",)),
            ("role", ("text",)),
            ("summary", ("metric",)),
        ),
        roles=(
            ("kicker", "kicker"),
            ("title", "title"),
            ("subtitle", "lead"),
            ("author", "label"),
            ("role", "caption"),
            ("summary", None),
        ),
    ),
    PresetCase(
        layout=TOC_LAYOUT,
        layout_id="toc",
        slot_ids=("title", "lead", "group1", "group2", "group3"),
        required=frozenset({"title"}),
        min_one_of=(("group1", "group2", "group3"),),
        block_types=(
            ("title", ("text",)),
            ("lead", ("text",)),
            ("group1", ("bullets",)),
            ("group2", ("bullets",)),
            ("group3", ("bullets",)),
        ),
        roles=(
            ("title", "title"),
            ("lead", "lead"),
            ("group1", None),
            ("group2", None),
            ("group3", None),
        ),
    ),
    PresetCase(
        layout=CONTENT_LAYOUT,
        layout_id="content",
        slot_ids=("title", "lead", "points", "note"),
        required=frozenset({"title", "points"}),
        min_one_of=(),
        block_types=(
            ("title", ("text",)),
            ("lead", ("text",)),
            ("points", ("bullets",)),
            ("note", ("text",)),
        ),
        roles=(
            ("title", "title"),
            ("lead", "lead"),
            ("points", None),
            ("note", "caption"),
        ),
    ),
    PresetCase(
        layout=SECTION_LAYOUT,
        layout_id="section",
        slot_ids=("number", "title", "subtitle"),
        required=frozenset({"title"}),
        min_one_of=(),
        block_types=(
            ("number", ("text",)),
            ("title", ("text",)),
            ("subtitle", ("text",)),
        ),
        roles=(
            ("number", "display"),
            ("title", "title"),
            ("subtitle", "lead"),
        ),
    ),
    PresetCase(
        layout=CLOSING_LAYOUT,
        layout_id="closing",
        slot_ids=("title", "lead", "contact", "note"),
        required=frozenset({"title", "contact"}),
        min_one_of=(),
        block_types=(
            ("title", ("text",)),
            ("lead", ("text",)),
            ("contact", ("text",)),
            ("note", ("text",)),
        ),
        roles=(
            ("title", "title"),
            ("lead", "lead"),
            ("contact", "body"),
            ("note", "caption"),
        ),
    ),
    PresetCase(
        layout=KPI_LAYOUT,
        layout_id="kpi",
        slot_ids=("title", "lead", "kpi1", "kpi2", "kpi3", "kpi4", "note"),
        required=frozenset({"title"}),
        min_one_of=(("kpi1", "kpi2", "kpi3", "kpi4"),),
        block_types=(
            ("title", ("text",)),
            ("lead", ("text",)),
            ("kpi1", ("metric",)),
            ("kpi2", ("metric",)),
            ("kpi3", ("metric",)),
            ("kpi4", ("metric",)),
            ("note", ("text",)),
        ),
        roles=(
            ("title", "title"),
            ("lead", "lead"),
            ("kpi1", None),
            ("kpi2", None),
            ("kpi3", None),
            ("kpi4", None),
            ("note", "caption"),
        ),
    ),
)

CASE_IDS = [case.layout_id for case in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_layout_identity_and_slot_contract(case: PresetCase) -> None:
    assert case.layout.layout_id == case.layout_id
    assert tuple(slot.slot_id for slot in case.layout.slots) == case.slot_ids
    assert {slot.slot_id for slot in case.layout.slots if slot.required} == case.required
    assert case.layout.min_one_of == case.min_one_of
    assert tuple((slot.slot_id, slot.block_types) for slot in case.layout.slots) == case.block_types
    assert tuple((slot.slot_id, slot.role) for slot in case.layout.slots) == case.roles


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_rows_fit_twelve_column_grid(case: PresetCase) -> None:
    slots_by_id = {slot.slot_id: slot for slot in case.layout.slots}
    placed = tuple(slot_id for row in case.layout.rows for slot_id in row)

    assert sorted(placed) == sorted(case.slot_ids)
    assert len(placed) == len(set(placed))
    assert all(1 <= slot.span <= LAYOUT_COLUMNS for slot in case.layout.slots)
    for row in case.layout.rows:
        assert row
        assert sum(slots_by_id[slot_id].span for slot_id in row) <= LAYOUT_COLUMNS


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_required_slots_are_fillable(case: PresetCase) -> None:
    fillable = set(case.required)
    for group in case.min_one_of:
        fillable.add(group[0])
    blocks = tuple(
        BlockIR(
            block_id=slot.slot_id,
            block_type=slot.block_types[0],
            span=None,
            role=slot.role,
            fields={},
        )
        for slot in case.layout.slots
        if slot.slot_id in fillable
    )
    slide = SlideIR(
        slide_id="s01",
        layout=case.layout_id,
        order=0,
        blocks=blocks,
        notes=None,
        source=None,
    )

    assignments = validate_slide(slide, case.layout)

    assert {item.slot.slot_id for item in assignments} == fillable
    assert all(set(item.slot.block_types) <= ALLOWED_BLOCK_TYPES for item in assignments)


@pytest.mark.parametrize(
    ("layout", "layout_id", "slot_id", "block_type"),
    (
        (TOC_LAYOUT, "toc", "group2", "bullets"),
        (KPI_LAYOUT, "kpi", "kpi3", "metric"),
    ),
    ids=("toc-only-group2", "kpi-only-kpi3"),
)
def test_min_one_of_accepts_a_single_group_member(
    layout: LayoutSpec,
    layout_id: str,
    slot_id: str,
    block_type: str,
) -> None:
    title = next(slot for slot in layout.slots if slot.slot_id == "title")
    blocks = (
        BlockIR(
            block_id="title",
            block_type=title.block_types[0],
            span=None,
            role=title.role,
            fields={"text": "Judul"},
        ),
        BlockIR(
            block_id=slot_id,
            block_type=block_type,
            span=None,
            role=None,
            fields={},
        ),
    )
    slide = SlideIR(
        slide_id="s01",
        layout=layout_id,
        order=0,
        blocks=blocks,
        notes=None,
        source=None,
    )

    assignments = validate_slide(slide, layout)

    assert {item.slot.slot_id for item in assignments} == {"title", slot_id}


def test_core_presets_use_no_callout_block() -> None:
    for case in CASES:
        for slot in case.layout.slots:
            assert set(slot.block_types) <= ALLOWED_BLOCK_TYPES
            assert "callout" not in slot.block_types


def test_core_presets_accept_source() -> None:
    assert all(case.layout.accepts_source for case in CASES)


def test_registry_discovers_all_core_presets() -> None:
    discovered = {layout.layout_id: layout for layout in discover_layouts()}

    for case in CASES:
        assert discovered[case.layout_id] == case.layout
        assert case.layout_id in layout_names()

    discovered_ids = tuple(layout.layout_id for layout in discover_layouts())
    assert discovered_ids == tuple(sorted(discovered_ids))
    assert layout_names()[-1] == "custom"
