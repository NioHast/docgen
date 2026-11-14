"""Resolusi warna chart dari token ``Theme.chart`` tanpa palet literal."""

from typing import Literal

from pptx.dml.color import RGBColor

from autooffice.design.theme import Theme

from .spec import ChartSpecError

ChartElement = Literal["grid", "axis", "legend", "title"]

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_MAX_SERIES_COLORS = 4
_MIN_DONUT_COLORS = 2


def rgb_from_hex(value: str) -> RGBColor:
    """Ubah warna token ``#RRGGBB`` menjadi ``RGBColor`` python-pptx."""
    if not isinstance(value, str):
        raise ChartSpecError("Warna chart wajib berupa string heksadesimal.")
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6 or any(character not in _HEX_DIGITS for character in text):
        raise ChartSpecError(f"Warna chart tidak valid: {value!r}; pakai RRGGBB.")
    return RGBColor(  # type: ignore[no-untyped-call]
        int(text[0:2], 16),
        int(text[2:4], 16),
        int(text[4:6], 16),
    )


def chart_series_colors(theme: Theme, count: int) -> tuple[RGBColor, ...]:
    """Ambil ``count`` slot pertama ``chartSeries`` theme secara deterministik."""
    palette = _series_palette(theme)
    if not 1 <= count <= _MAX_SERIES_COLORS:
        raise ChartSpecError(
            f"Chart membutuhkan 1 sampai {_MAX_SERIES_COLORS} warna seri, bukan {count}."
        )
    return palette[:count]


def chart_category_colors(theme: Theme, count: int) -> tuple[RGBColor, ...]:
    """Ambil warna kategori donut dari slot ``chartSeries`` theme."""
    if not _MIN_DONUT_COLORS <= count <= _MAX_SERIES_COLORS:
        raise ChartSpecError(
            f"Donut membutuhkan {_MIN_DONUT_COLORS} sampai {_MAX_SERIES_COLORS} "
            f"warna kategori, bukan {count}."
        )
    return chart_series_colors(theme, count)


def chart_element_color(theme: Theme, element: ChartElement) -> RGBColor:
    """Ambil warna grid, axis, legend, atau title dari token theme."""
    if element == "grid":
        return rgb_from_hex(theme.chart.grid)
    if element == "axis":
        return rgb_from_hex(theme.chart.axis)
    if element == "legend":
        return rgb_from_hex(theme.chart.legend)
    return rgb_from_hex(theme.chart.title)


def _series_palette(theme: Theme) -> tuple[RGBColor, ...]:
    colors = tuple(rgb_from_hex(value) for value in theme.chart.series)
    if len(colors) != _MAX_SERIES_COLORS:
        raise ChartSpecError(
            f"chartSeries theme '{theme.name}' wajib berisi tepat "
            f"{_MAX_SERIES_COLORS} warna, bukan {len(colors)}."
        )
    return colors


__all__ = [
    "ChartElement",
    "chart_category_colors",
    "chart_element_color",
    "chart_series_colors",
    "rgb_from_hex",
]
