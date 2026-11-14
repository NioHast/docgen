"""Preset layout ``flow``: empat langkah proses dengan judul dan lead."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="flow",
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
            slot_id="step1",
            required=True,
            block_types=("text",),
            role="body",
            span=3,
        ),
        SlotSpec(
            slot_id="step2",
            required=True,
            block_types=("text",),
            role="body",
            span=3,
        ),
        SlotSpec(
            slot_id="step3",
            required=True,
            block_types=("text",),
            role="body",
            span=3,
        ),
        SlotSpec(
            slot_id="step4",
            required=True,
            block_types=("text",),
            role="body",
            span=3,
        ),
    ),
    rows=(
        ("title",),
        ("lead",),
        ("step1", "step2", "step3", "step4"),
    ),
    accepts_source=True,
)
