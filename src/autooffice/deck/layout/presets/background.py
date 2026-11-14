"""Preset layout ``background``: konteks naratif dengan tiga poin."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="background",
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
            slot_id="lead",
            required=False,
            block_types=("text",),
            role="lead",
            span=12,
        ),
        SlotSpec(
            slot_id="point1",
            required=True,
            block_types=("text",),
            role="body",
            span=4,
        ),
        SlotSpec(
            slot_id="point2",
            required=True,
            block_types=("text",),
            role="body",
            span=4,
        ),
        SlotSpec(
            slot_id="point3",
            required=True,
            block_types=("text",),
            role="body",
            span=4,
        ),
    ),
    rows=(
        ("kicker",),
        ("title",),
        ("lead",),
        ("point1", "point2", "point3"),
    ),
    accepts_source=True,
)
