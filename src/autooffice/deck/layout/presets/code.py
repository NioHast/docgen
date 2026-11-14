"""Preset layout ``code``: judul, lead, code block, dan catatan."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="code",
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
            slot_id="code1",
            required=True,
            block_types=("code",),
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
        ("code1",),
        ("note",),
    ),
    accepts_source=True,
)
