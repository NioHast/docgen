"""Preset layout ``diagram``: judul, subtitle, dan gambar Mermaid.

Caption diagram adalah field block ``diagram``, bukan slot terpisah.
"""

from autooffice.deck.layout.spec import LayoutSpec, SlotSpec

LAYOUT = LayoutSpec(
    layout_id="diagram",
    slots=(
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
            slot_id="diagram1",
            required=True,
            block_types=("diagram",),
            span=12,
        ),
    ),
    rows=(
        ("title",),
        ("subtitle",),
        ("diagram1",),
    ),
    accepts_source=True,
)
