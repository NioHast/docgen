"""Preset layout cover untuk slide pembuka deck."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="cover",
    slots=(
        SlotSpec(
            slot_id="kicker",
            required=False,
            block_types=("text",),
            role="kicker",
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
        SlotSpec(
            slot_id="author",
            required=True,
            block_types=("text",),
            role="label",
            span=6,
        ),
        SlotSpec(
            slot_id="role",
            required=False,
            block_types=("text",),
            role="caption",
            span=6,
        ),
        SlotSpec(
            slot_id="summary",
            required=False,
            block_types=("metric",),
            span=4,
        ),
    ),
    rows=(
        ("kicker",),
        ("title",),
        ("subtitle",),
        ("author", "role"),
        ("summary",),
    ),
    accepts_source=True,
)
