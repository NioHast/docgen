"""Preset layout ``table``: judul, lead, tabel native, dan catatan."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="table",
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
            slot_id="table1",
            required=True,
            block_types=("table",),
            span=12,
        ),
        SlotSpec(
            slot_id="note",
            required=False,
            block_types=("text",),
            role="caption",
            span=12,
        ),
    ),
    rows=(("title",), ("lead",), ("table1",), ("note",)),
    accepts_source=True,
)
