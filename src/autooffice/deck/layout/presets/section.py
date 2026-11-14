"""Preset layout section untuk slide pembatas bab."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="section",
    slots=(
        SlotSpec(
            slot_id="number",
            required=False,
            block_types=("text",),
            role="display",
            span=12,
        ),
        SlotSpec(
            slot_id="title",
            required=True,
            block_types=("text",),
            role="title",
            span=12,
        ),
        SlotSpec(
            slot_id="subtitle",
            required=False,
            block_types=("text",),
            role="lead",
            span=12,
        ),
    ),
    rows=(
        ("number",),
        ("title",),
        ("subtitle",),
    ),
    accepts_source=True,
)
