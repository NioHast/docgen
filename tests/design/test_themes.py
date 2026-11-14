"""Tes resolusi theme, palet deck-studio, dan invariant data token."""

import re
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from autooffice.design import DesignTokenError, resolve_theme
from autooffice.design.theme import (
    ChartPalette,
    CodeTokens,
    GridTokens,
    RadiusTokens,
    ShadowTokens,
    SpacingTokens,
    Theme,
    Typography,
)
from autooffice.design.tokens import load_themes, load_tokens, theme_names

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOOFFICE_SRC = REPO_ROOT / "src" / "autooffice"
HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")

THEME_CASES = (
    (
        "indigo",
        "#4F46E5",
        "#3730A3",
        "#EEF2FF",
        "#C7D2FE",
        ("#4F46E5", "#0F766E", "#B45309", "#BE123C"),
        {"from": "#4F46E5", "mid": "#4338CA", "to": "#312E81"},
    ),
    (
        "hitam",
        "#111827",
        "#000000",
        "#F3F4F6",
        "#D1D5DB",
        ("#111827", "#374151", "#4B5563", "#6B7280"),
        {"from": "#111827", "mid": "#0B1220", "to": "#000000"},
    ),
)


@pytest.mark.parametrize(
    ("name", "accent", "accent_deep", "accent_soft", "accent_line", "series", "cover"),
    THEME_CASES,
    ids=[case[0] for case in THEME_CASES],
)
def test_theme_uses_deck_studio_palette(
    name: str,
    accent: str,
    accent_deep: str,
    accent_soft: str,
    accent_line: str,
    series: tuple[str, str, str, str],
    cover: dict[str, str],
) -> None:
    theme = resolve_theme(name)
    entry = load_themes()["themes"][name]

    assert theme.name == name
    assert theme.mode == "light"
    assert theme.colors.accent == accent
    assert theme.colors.accent_deep == accent_deep
    assert theme.colors.accent_soft == accent_soft
    assert theme.colors.accent_line == accent_line
    assert theme.colors.accent_ink == "#FFFFFF"
    assert theme.chart.series == series
    assert entry["cover"] == cover
    assert tuple(entry["cover"].values()) == (cover["from"], cover["mid"], cover["to"])


def test_default_theme_is_indigo_light_canvas() -> None:
    theme = resolve_theme()

    assert theme.name == "indigo"
    assert theme.mode == "light"
    assert theme.colors.background == "#FAFAFA"
    assert theme.colors.surface == "#FFFFFF"
    assert theme.colors.surface_alt == "#F9FAFB"
    assert theme.colors.ink == "#0B0B0F"
    assert theme.colors.ink_secondary == "#374151"
    assert theme.colors.muted == "#6B7280"
    assert theme.colors.border == "#E5E7EB"


def test_hitam_is_light_theme_with_black_accent() -> None:
    theme = resolve_theme("hitam")

    assert theme.mode == "light"
    assert theme.colors.background == "#FAFAFA"
    assert theme.colors.surface == "#FFFFFF"
    assert theme.colors.accent == "#111827"
    assert theme.colors.accent_deep == "#000000"


def test_theme_resolves_geometry_typography_and_code_tokens() -> None:
    theme = resolve_theme("indigo")

    assert theme.typography == Typography(
        family="Plus Jakarta Sans",
        weights=(400, 600, 700, 800),
        title_pt=30.0,
        body_pt=16.5,
        minimum_pt=10.0,
        line_height=1.2,
        tracking_em=-0.01,
    )
    assert theme.grid == GridTokens(
        columns=12,
        gutter_emu=91440,
        margin_left_emu=914400,
        margin_right_emu=914400,
        margin_top_emu=609600,
        margin_bottom_emu=609600,
        row_gap_emu=182880,
        slide_width_emu=12192000,
        slide_height_emu=6858000,
    )
    assert theme.spacing == SpacingTokens(
        sm_emu=45720,
        md_emu=91440,
        lg_emu=137160,
        card_padding_emu=182880,
        divider_emu=12700,
    )
    assert theme.radius == RadiusTokens(sm_emu=45720, md_emu=91440, lg_emu=182880)
    assert theme.shadow == ShadowTokens(
        card="0 1 2 0 rgba(17, 24, 39, 0.08)",
        overlay="0 8 24 0 rgba(17, 24, 39, 0.16)",
        none="none",
    )
    assert theme.code == CodeTokens(
        family="ui-monospace, 'Cascadia Mono', Consolas, monospace",
        size_pt=10.5,
        line_height=1.35,
    )
    assert theme.chart == ChartPalette(
        series=("#4F46E5", "#0F766E", "#B45309", "#BE123C"),
        grid="#E5E7EB",
        axis="#6B7280",
        legend="#374151",
        title="#0B0B0F",
    )


def test_token_chart_defaults_match_indigo_palette() -> None:
    chart = load_tokens()["chart"]

    assert chart["series"] == ("#4F46E5", "#0F766E", "#B45309", "#BE123C")
    assert chart["grid"] == "#E5E7EB"
    assert chart["axis"] == "#6B7280"


def test_status_palette_matches_accessible_contract_values() -> None:
    theme = resolve_theme("hitam")

    assert dict(theme.colors.status) == {
        "neutral": "#374151",
        "success": "#0F766E",
        "warning": "#B45309",
        "danger": "#BE123C",
    }


def test_theme_changes_color_but_not_geometry() -> None:
    indigo = resolve_theme("indigo")
    hitam = resolve_theme("hitam")

    assert indigo.colors != hitam.colors
    assert indigo.chart != hitam.chart
    assert indigo.grid == hitam.grid
    assert indigo.typography == hitam.typography
    assert indigo.spacing == hitam.spacing
    assert indigo.radius == hitam.radius
    assert indigo.shadow == hitam.shadow
    assert indigo.code == hitam.code


def test_only_two_product_themes_exist() -> None:
    themes = load_themes()

    assert themes["default"] == "indigo"
    assert theme_names() == ("indigo", "hitam")
    assert tuple(themes["themes"]) == ("indigo", "hitam")
    assert {
        "merah",
        "jingga",
        "amber",
        "biru",
        "hijau",
        "coklat",
        "teal",
        "plum",
        "marun",
        "malam",
    }.isdisjoint(themes["themes"])


def test_unknown_theme_raises_clear_error() -> None:
    with pytest.raises(DesignTokenError, match=r"unknown theme.*'malam'") as error:
        resolve_theme("malam")

    message = str(error.value)
    assert "indigo" in message
    assert "hitam" in message


def test_theme_is_frozen_and_status_is_read_only() -> None:
    theme = resolve_theme("indigo")

    with pytest.raises(FrozenInstanceError):
        theme.name = "hitam"
    with pytest.raises(TypeError):
        theme.colors.status["success"] = "#000000"


def test_resolved_theme_keeps_contract_shape() -> None:
    assert {field.name for field in fields(Theme)} == {
        "name",
        "mode",
        "colors",
        "chart",
        "typography",
        "grid",
        "spacing",
        "radius",
        "shadow",
        "code",
    }


def test_python_modules_do_not_hardcode_hex_colors() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in AUTOOFFICE_SRC.rglob("*.py")
        if HEX_COLOR.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
