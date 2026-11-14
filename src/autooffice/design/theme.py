"""Model theme yang sudah diresolusi untuk renderer."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


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
