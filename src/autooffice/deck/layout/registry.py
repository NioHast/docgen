"""Registry statis 19 layout preset dan layout ``custom`` AutoOffice v1.

Discovery preset berbasis file belum diimplementasikan pada F0; discovery
dijadwalkan pada lane F1-LAYOUT. Sampai saat itu registry ini adalah daftar
tunggal nama layout yang valid.
"""

_LAYOUT_NAMES: tuple[str, ...] = (
    "cover",
    "toc",
    "content",
    "section",
    "closing",
    "kpi",
    "bars",
    "line",
    "donut",
    "table",
    "comparison",
    "matrix",
    "background",
    "flow",
    "code",
    "diagram",
    "image-split",
    "image-full",
    "image-grid",
    "custom",
)


def layout_names() -> tuple[str, ...]:
    """Kembalikan nama layout v1 dalam urutan katalog bagian 6.2."""
    return _LAYOUT_NAMES
