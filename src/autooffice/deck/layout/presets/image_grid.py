"""Preset layout ``image-grid``: tiga gambar dalam grid dengan caption.

Caption setiap gambar adalah field block ``image``, bukan slot terpisah.
"""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="image-grid",
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
            slot_id="image1",
            required=True,
            block_types=("image",),
            span=4,
        ),
        SlotSpec(
            slot_id="image2",
            required=True,
            block_types=("image",),
            span=4,
        ),
        SlotSpec(
            slot_id="image3",
            required=True,
            block_types=("image",),
            span=4,
        ),
    ),
    rows=(
        ("title",),
        ("lead",),
        ("image1", "image2", "image3"),
    ),
    accepts_source=True,
)
