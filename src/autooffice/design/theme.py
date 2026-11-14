"""Model theme yang sudah diresolusi untuk renderer."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from autooffice.design.tokens import ThemeData, TokensData, load_theme


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Warna theme yang siap dipakai renderer."""

    background: str
    surface: str
    surface_alt: str
    ink: str
    ink_secondary: str
    muted: str
    border: str
    accent: str
    accent_deep: str
    accent_soft: str
    accent_line: str
    accent_ink: str
    status: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", MappingProxyType(dict(self.status)))


@dataclass(frozen=True, slots=True)
class ChartPalette:
    """Empat slot warna chart beserta warna elemen pendukungnya."""

    series: tuple[str, str, str, str]
    grid: str
    axis: str
    legend: str
    title: str


@dataclass(frozen=True, slots=True)
class Typography:
    """Family, weight, dan ukuran tipografi deck."""

    family: str
    weights: tuple[int, int, int, int]
    title_pt: float
    body_pt: float
    minimum_pt: float
    line_height: float
    tracking_em: float


@dataclass(frozen=True, slots=True)
class GridTokens:
    """Token grid 12 kolom, jarak baris, dan dimensi kanvas."""

    columns: int
    gutter_emu: int
    margin_left_emu: int
    margin_right_emu: int
    margin_top_emu: int
    margin_bottom_emu: int
    row_gap_emu: int
    slide_width_emu: int
    slide_height_emu: int


@dataclass(frozen=True, slots=True)
class SpacingTokens:
    """Token jarak, padding kartu, dan divider."""

    sm_emu: int
    md_emu: int
    lg_emu: int
    card_padding_emu: int
    divider_emu: int


@dataclass(frozen=True, slots=True)
class RadiusTokens:
    """Token radius sudut kecil, sedang, dan besar."""

    sm_emu: int
    md_emu: int
    lg_emu: int


@dataclass(frozen=True, slots=True)
class ShadowTokens:
    """Token bayangan kartu, overlay, dan tanpa bayangan."""

    card: str
    overlay: str
    none: str


@dataclass(frozen=True, slots=True)
class CodeTokens:
    """Token tipografi blok kode."""

    family: str
    size_pt: float
    line_height: float


@dataclass(frozen=True, slots=True)
class Theme:
    """Theme lengkap yang sudah diresolusi untuk renderer."""

    name: str
    mode: Literal["light"]
    colors: ThemeColors
    chart: ChartPalette
    typography: Typography
    grid: GridTokens
    spacing: SpacingTokens
    radius: RadiusTokens
    shadow: ShadowTokens
    code: CodeTokens


def _theme_from_data(tokens: TokensData, data: ThemeData, name: str) -> Theme:
    colors_data = tokens["colors"]
    overrides = data["colors"]
    return Theme(
        name=name,
        mode="light",
        colors=ThemeColors(
            background=colors_data["background"],
            surface=colors_data["surface"],
            surface_alt=colors_data["surface_alt"],
            ink=colors_data["ink"],
            ink_secondary=colors_data["ink_secondary"],
            muted=colors_data["muted"],
            border=colors_data["border"],
            accent=overrides["accent"],
            accent_deep=overrides["accent_deep"],
            accent_soft=overrides["accent_soft"],
            accent_line=overrides["accent_line"],
            accent_ink=overrides["accent_ink"],
            status={
                "neutral": colors_data["status"]["neutral"],
                "success": colors_data["status"]["success"],
                "warning": colors_data["status"]["warning"],
                "danger": colors_data["status"]["danger"],
            },
        ),
        chart=ChartPalette(
            series=data["chart"]["series"],
            grid=data["chart"]["grid"],
            axis=data["chart"]["axis"],
            legend=data["chart"]["legend"],
            title=data["chart"]["title"],
        ),
        typography=Typography(
            family=tokens["typography"]["family"],
            weights=tokens["typography"]["weights"],
            title_pt=tokens["typography"]["title_pt"],
            body_pt=tokens["typography"]["body_pt"],
            minimum_pt=tokens["typography"]["minimum_pt"],
            line_height=tokens["typography"]["line_height"],
            tracking_em=tokens["typography"]["tracking_em"],
        ),
        grid=GridTokens(
            columns=tokens["grid"]["columns"],
            gutter_emu=tokens["grid"]["gutter_emu"],
            margin_left_emu=tokens["grid"]["margin_left_emu"],
            margin_right_emu=tokens["grid"]["margin_right_emu"],
            margin_top_emu=tokens["grid"]["margin_top_emu"],
            margin_bottom_emu=tokens["grid"]["margin_bottom_emu"],
            row_gap_emu=tokens["grid"]["row_gap_emu"],
            slide_width_emu=tokens["grid"]["slide_width_emu"],
            slide_height_emu=tokens["grid"]["slide_height_emu"],
        ),
        spacing=SpacingTokens(
            sm_emu=tokens["spacing"]["sm_emu"],
            md_emu=tokens["spacing"]["md_emu"],
            lg_emu=tokens["spacing"]["lg_emu"],
            card_padding_emu=tokens["spacing"]["card_padding_emu"],
            divider_emu=tokens["spacing"]["divider_emu"],
        ),
        radius=RadiusTokens(
            sm_emu=tokens["radius"]["sm_emu"],
            md_emu=tokens["radius"]["md_emu"],
            lg_emu=tokens["radius"]["lg_emu"],
        ),
        shadow=ShadowTokens(
            card=tokens["shadow"]["card"],
            overlay=tokens["shadow"]["overlay"],
            none=tokens["shadow"]["none"],
        ),
        code=CodeTokens(
            family=tokens["code"]["family"],
            size_pt=tokens["code"]["size_pt"],
            line_height=tokens["code"]["line_height"],
        ),
    )


def resolve_theme(name: str = "indigo") -> Theme:
    """Resolve data token YAML menjadi Theme immutable untuk renderer."""
    tokens, data = load_theme(name)
    return _theme_from_data(tokens, data, name)
