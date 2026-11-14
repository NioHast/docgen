"""Test resolusi warna chart dari token theme dan kontras non-teks."""

from dataclasses import replace

import pytest

from autooffice.deck.charts import (
    ChartSpecError,
    chart_category_colors,
    chart_element_color,
    chart_series_colors,
    rgb_from_hex,
)
from autooffice.design import resolve_theme
from autooffice.design.contrast import contrast_ratio

CHART_MINIMUM = 3.0


def _rgb_text(color: object) -> str:
    return f"#{color}"


@pytest.mark.parametrize("name", ["indigo", "hitam"])
def test_four_series_colors_come_from_theme(name: str) -> None:
    theme = resolve_theme(name)

    colors = chart_series_colors(theme, 4)

    assert tuple(_rgb_text(color) for color in colors) == theme.chart.series


def test_series_color_slice_is_deterministic() -> None:
    theme = resolve_theme("indigo")

    assert chart_series_colors(theme, 1) == chart_series_colors(theme, 4)[:1]
    assert chart_series_colors(theme, 2) == chart_series_colors(theme, 4)[:2]


@pytest.mark.parametrize("count", [0, 5], ids=["zero", "five"])
def test_series_color_count_outside_limit_is_rejected(count: int) -> None:
    theme = resolve_theme("indigo")

    with pytest.raises(ChartSpecError, match="1 sampai 4 warna seri"):
        chart_series_colors(theme, count)


@pytest.mark.parametrize("count", [2, 3, 4])
def test_donut_category_colors_use_theme_series(count: int) -> None:
    theme = resolve_theme("hitam")

    colors = chart_category_colors(theme, count)

    assert tuple(_rgb_text(color) for color in colors) == theme.chart.series[:count]


@pytest.mark.parametrize("count", [1, 5], ids=["one", "five"])
def test_donut_category_count_outside_limit_is_rejected(count: int) -> None:
    theme = resolve_theme("indigo")

    with pytest.raises(ChartSpecError, match="2 sampai 4 warna kategori"):
        chart_category_colors(theme, count)


@pytest.mark.parametrize("name", ["indigo", "hitam"])
def test_chart_element_colors_come_from_theme(name: str) -> None:
    theme = resolve_theme(name)

    assert _rgb_text(chart_element_color(theme, "grid")) == theme.chart.grid
    assert _rgb_text(chart_element_color(theme, "axis")) == theme.chart.axis
    assert _rgb_text(chart_element_color(theme, "legend")) == theme.chart.legend
    assert _rgb_text(chart_element_color(theme, "title")) == theme.chart.title


@pytest.mark.parametrize("name", ["indigo", "hitam"])
def test_chart_series_meets_non_text_contrast(name: str) -> None:
    theme = resolve_theme(name)

    for color in theme.chart.series:
        for surface in (theme.colors.surface, theme.colors.background):
            assert contrast_ratio(color, surface) >= CHART_MINIMUM


def test_rgb_from_hex_accepts_uppercase_and_lowercase() -> None:
    assert rgb_from_hex("#4f46e5") == rgb_from_hex("#4F46E5")


@pytest.mark.parametrize(
    "value",
    ["4F46E", "#4F46E55", "#GGGGGG", "", "indigo"],
    ids=["too-short", "too-long", "not-hex", "empty", "name"],
)
def test_rgb_from_hex_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ChartSpecError, match="Warna chart tidak valid"):
        rgb_from_hex(value)


def test_rgb_from_hex_rejects_non_string() -> None:
    with pytest.raises(ChartSpecError, match="wajib berupa string"):
        rgb_from_hex(123)  # type: ignore[arg-type]


def test_theme_must_have_exactly_four_series_colors() -> None:
    theme = resolve_theme("indigo")
    broken = replace(theme, chart=replace(theme.chart, series=("#111111", "#222222", "#333333")))

    with pytest.raises(ChartSpecError, match="tepat 4 warna"):
        chart_series_colors(broken, 1)
