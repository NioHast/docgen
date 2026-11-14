"""Preset layout ``image-full``: gambar penuh kanvas dengan overlay teks.

Overlay hanya berupa slot teks; tidak ada posisi absolut. Caption gambar
adalah field block ``image``, bukan slot terpisah.
"""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="image-full",
    slots=(
        SlotSpec(
            slot_id="title",
            required=True,
            block_types=("text",),
            role="title",
            span=12,
        ),
        SlotSpec(
            slot_id="image1",
            required=True,
            block_types=("image",),
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
            slot_id="credit",
            required=False,
            block_types=("text",),
            role="caption",
            span=12,
        ),
    ),
    rows=(
        ("title",),
        ("image1",),
        ("subtitle",),
        ("credit",),
    ),
    accepts_source=True,
)
