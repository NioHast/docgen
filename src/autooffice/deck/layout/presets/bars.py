"""Preset layout ``bars``: judul, lead, chart batang, dan catatan."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="bars",
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
            slot_id="chart1",
            required=True,
            block_types=("chart",),
            span=7,
            chart_kind="bar",
        ),
        SlotSpec(
            slot_id="note",
            required=False,
            block_types=("text",),
            role="caption",
            span=5,
        ),
    ),
    rows=(("title",), ("lead",), ("chart1", "note")),
    accepts_source=True,
)
