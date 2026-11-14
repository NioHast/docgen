"""Preset layout ``image-split``: teks di samping satu gambar.

Caption gambar adalah field block ``image``, bukan slot terpisah.
"""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="image-split",
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
            slot_id="body",
            required=True,
            block_types=("text",),
            role="body",
            span=7,
        ),
        SlotSpec(
            slot_id="image1",
            required=True,
            block_types=("image",),
            span=5,
        ),
    ),
    rows=(
        ("title",),
        ("lead",),
        ("body", "image1"),
    ),
    accepts_source=True,
)
