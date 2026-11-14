"""Preset layout ``matrix``: tabel matriks, legend bullet, dan catatan."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="matrix",
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
            slot_id="matrix1",
            required=True,
            block_types=("table",),
            span=7,
        ),
        SlotSpec(
            slot_id="legend",
            required=False,
            block_types=("bullets",),
            span=5,
        ),
        SlotSpec(
            slot_id="note",
            required=False,
            block_types=("text",),
            role="caption",
            span=12,
        ),
    ),
    rows=(("title",), ("lead",), ("matrix1", "legend"), ("note",)),
    accepts_source=True,
)
