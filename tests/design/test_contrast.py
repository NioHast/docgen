"""Tes kontras WCAG untuk teks dan palet chart setiap theme."""

import pytest

from autooffice.design import resolve_theme
from autooffice.design.contrast import contrast_ratio, meets_contrast, relative_luminance

TEXT_MINIMUM = 4.5
CHART_MINIMUM = 3.0


def test_relative_luminance_extremes() -> None:
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0)
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)
    assert relative_luminance((0, 0, 0)) == pytest.approx(0.0)


def test_contrast_ratio_extremes_and_symmetry() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_contrast_threshold_examples() -> None:
    assert contrast_ratio("#767676", "#FFFFFF") == pytest.approx(4.5422, abs=0.0001)
    assert meets_contrast("#767676", "#FFFFFF", TEXT_MINIMUM) is True
    assert meets_contrast("#777777", "#FFFFFF", TEXT_MINIMUM) is False


def test_contrast_meets_exact_boundary_only_when_reached() -> None:
    maximum = contrast_ratio("#000000", "#FFFFFF")

    assert maximum == pytest.approx(21.0)
    assert meets_contrast("#000000", "#FFFFFF", maximum) is True
    assert meets_contrast("#000000", "#FFFFFF", 21.0001) is False


def test_hex_parser_trims_whitespace_and_ignores_case() -> None:
    assert relative_luminance("  #FFFFFF  ") == pytest.approx(1.0)
    assert relative_luminance("#fff") == relative_luminance("#FFF")


def test_shorthand_hex_is_supported() -> None:
    assert relative_luminance("#fff") == pytest.approx(relative_luminance("#FFFFFF"))
    assert contrast_ratio("#000", "#fff") == pytest.approx(21.0)


@pytest.mark.parametrize(
    "color",
    ["red", "#12345", "#1234567", "#GGGGGG", ""],
    ids=["name", "too-short", "too-long", "not-hex", "empty"],
)
def test_invalid_hex_color_is_rejected(color: str) -> None:
    with pytest.raises(ValueError, match="warna tidak valid"):
        relative_luminance(color)


@pytest.mark.parametrize(
    "color",
    [(256, 0, 0), (-1, 0, 0), (1, 2), (True, 0, 0)],
    ids=["above-range", "below-range", "wrong-length", "bool-channel"],
)
def test_invalid_rgb_tuple_is_rejected(color: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match=r"RGB|kanal"):
        relative_luminance(color)


@pytest.mark.parametrize("name", ["indigo", "hitam"])
def test_body_text_meets_wcag_aa(name: str) -> None:
    theme = resolve_theme(name)
    text_colors = {
        "ink": theme.colors.ink,
        "ink_secondary": theme.colors.ink_secondary,
        "muted": theme.colors.muted,
        "accent": theme.colors.accent,
        "neutral": theme.colors.status["neutral"],
        "success": theme.colors.status["success"],
        "warning": theme.colors.status["warning"],
        "danger": theme.colors.status["danger"],
    }

    for label, color in text_colors.items():
        for surface_name in ("background", "surface"):
            surface = getattr(theme.colors, surface_name)
            ratio = contrast_ratio(color, surface)
            assert ratio >= TEXT_MINIMUM, f"{name}:{label} on {surface_name} = {ratio:.3f}"


@pytest.mark.parametrize("name", ["indigo", "hitam"])
def test_accent_ink_meets_wcag_aa_on_accent(name: str) -> None:
    theme = resolve_theme(name)

    assert contrast_ratio(theme.colors.accent_ink, theme.colors.accent) >= TEXT_MINIMUM


@pytest.mark.parametrize("name", ["indigo", "hitam"])
def test_chart_text_meets_wcag_aa(name: str) -> None:
    theme = resolve_theme(name)

    for label in ("axis", "legend", "title"):
        color = getattr(theme.chart, label)
        ratio = contrast_ratio(color, theme.colors.surface)
        assert ratio >= TEXT_MINIMUM, f"{name}:{label} = {ratio:.3f}"


@pytest.mark.parametrize("name", ["indigo", "hitam"])
def test_chart_series_meets_wcag_non_text_contrast(name: str) -> None:
    theme = resolve_theme(name)

    assert len(theme.chart.series) == 4
    for index, color in enumerate(theme.chart.series):
        for surface in (theme.colors.surface, theme.colors.background):
            ratio = contrast_ratio(color, surface)
            assert ratio >= CHART_MINIMUM, f"{name}:series[{index}] = {ratio:.3f}"
