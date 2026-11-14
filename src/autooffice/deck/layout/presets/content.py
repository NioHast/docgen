"""Preset layout content untuk halaman narasi dengan daftar poin."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="content",
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
            slot_id="points",
            required=True,
            block_types=("bullets",),
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
    rows=(
        ("title",),
        ("lead",),
        ("points",),
        ("note",),
    ),
    accepts_source=True,
)
