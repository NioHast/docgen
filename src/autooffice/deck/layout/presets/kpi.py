"""Preset layout kpi untuk sampai empat metric utama."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="kpi",
    slots=(
        SlotSpec(
            slot_id="title",
            required=True,
            block_types=("text",),
            role="title",
            span=12,
        ),
        SlotSpec(
            slot_id="lead",
            required=False,
            block_types=("text",),
            role="lead",
            span=12,
        ),
        SlotSpec(
            slot_id="kpi1",
            required=False,
            block_types=("metric",),
            span=3,
        ),
        SlotSpec(
            slot_id="kpi2",
            required=False,
            block_types=("metric",),
            span=3,
        ),
        SlotSpec(
            slot_id="kpi3",
            required=False,
            block_types=("metric",),
            span=3,
        ),
        SlotSpec(
            slot_id="kpi4",
            required=False,
            block_types=("metric",),
            span=3,
        ),
        SlotSpec(
            slot_id="note",
            required=False,
            block_types=("text",),
            role="caption",
            span=12,
        ),
    ),
    rows=(
        ("title",),
        ("lead",),
        ("kpi1", "kpi2", "kpi3", "kpi4"),
        ("note",),
    ),
    accepts_source=True,
    min_one_of=(("kpi1", "kpi2", "kpi3", "kpi4"),),
)
