"""Registry 11 block type deck AutoOffice v1.

``key_leaves`` memakai notasi ``N`` dan ``M`` untuk indeks 1-based yang
dihasilkan dari field berulang, misalnya ``itemN.text`` atau ``rN.cM``.
"""

from .spec import BlockSpec

BLOCK_SPECS: tuple[BlockSpec, ...] = (
    BlockSpec(
        block_type="text",
        required=("text",),
        optional=("heading", "role"),
        key_leaves=("text", "heading"),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="bullets",
        required=("items",),
        optional=("ordered",),
        key_leaves=("itemN.text",),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="image",
        required=("path", "alt"),
        optional=("caption", "fit"),
        key_leaves=("caption",),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="table",
        required=("columns", "rows"),
        optional=("caption", "emphasis_column"),
        key_leaves=("caption", "hN", "rN.cM"),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="chart",
        required=("kind", "title", "alt", "categories", "series"),
        optional=("orientation", "unit", "caption"),
        key_leaves=("title", "catN", "seriesN.name", "seriesN.valueN", "caption"),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="code",
        required=("code",),
        optional=("language", "filename", "line_numbers"),
        key_leaves=("code", "filename"),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="quote",
        required=("text",),
        optional=("attribution",),
        key_leaves=("text", "attribution"),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="diagram",
        required=("source", "alt"),
        optional=("caption",),
        key_leaves=("caption",),
        allowed_in_preset=True,
    ),
    BlockSpec(
        block_type="divider",
        required=(),
        optional=(),
        key_leaves=(),
        allowed_in_preset=False,
    ),
    BlockSpec(
        block_type="spacer",
        required=(),
        optional=("size",),
        key_leaves=(),
        allowed_in_preset=False,
    ),
    BlockSpec(
        block_type="metric",
        required=("label", "value"),
        optional=("caption", "status"),
        key_leaves=("label", "value", "caption"),
        allowed_in_preset=True,
    ),
)


def block_specs() -> tuple[BlockSpec, ...]:
    """Kembalikan kontrak seluruh block type v1 dalam urutan stabil."""
    return BLOCK_SPECS


def block_names() -> tuple[str, ...]:
    """Kembalikan nama seluruh block type v1 dalam urutan registry."""
    return tuple(spec.block_type for spec in BLOCK_SPECS)
