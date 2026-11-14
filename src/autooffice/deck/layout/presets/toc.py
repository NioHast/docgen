"""Preset layout toc untuk daftar isi satu sampai tiga kelompok."""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="toc",
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
            slot_id="group1",
            required=False,
            block_types=("bullets",),
            span=4,
        ),
        SlotSpec(
            slot_id="group2",
            required=False,
            block_types=("bullets",),
            span=4,
        ),
        SlotSpec(
            slot_id="group3",
            required=False,
            block_types=("bullets",),
            span=4,
        ),
    ),
    rows=(
        ("title",),
        ("lead",),
        ("group1", "group2", "group3"),
    ),
    accepts_source=True,
    min_one_of=(("group1", "group2", "group3"),),
)
