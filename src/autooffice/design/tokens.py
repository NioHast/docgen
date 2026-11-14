"""Pemuat dan validator token desain AutoOffice dari data package."""

from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from autooffice.errors import AutoOfficeError

_DATA_DIR = Path(__file__).with_name("data")
TOKENS_PATH = _DATA_DIR / "tokens.yaml"
THEMES_PATH = _DATA_DIR / "themes.yaml"
TOKENS_SCHEMA = "autooffice.design-tokens/v1"
THEMES_SCHEMA = "autooffice.design-themes/v1"
THEME_NAMES: tuple[str, str] = ("indigo", "hitam")

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_COLOR_KEYS = (
    "background",
    "surface",
    "surface_alt",
    "ink",
    "ink_secondary",
    "muted",
    "border",
    "accent",
    "accent_deep",
    "accent_soft",
    "accent_line",
    "accent_ink",
    "status",
)
_STATUS_KEYS = ("neutral", "success", "warning", "danger")
_THEME_COLOR_KEYS = ("accent", "accent_deep", "accent_soft", "accent_line", "accent_ink")
_TOKEN_KEYS = (
    "schema",
    "colors",
    "typography",
    "grid",
    "spacing",
    "radius",
    "shadow",
    "chart",
    "code",
)
_THEME_KEYS = ("label", "mode", "colors", "cover", "chart")


class DesignTokenError(AutoOfficeError, ValueError):
    """Token desain tidak valid atau theme tidak tersedia."""


class StatusData(TypedDict):
    """Warna status yang ditempelkan ke setiap theme."""

    neutral: str
    success: str
    warning: str
    danger: str


class ColorsData(TypedDict):
    """Warna netral, aksen default, dan status."""

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
    status: StatusData


class TypographyData(TypedDict):
    """Tipografi deck yang sudah divalidasi."""

    family: str
    weights: tuple[int, int, int, int]
    title_pt: float
    body_pt: float
    minimum_pt: float
    line_height: float
    tracking_em: float


class GridData(TypedDict):
    """Grid, margin, dan ukuran kanvas dalam EMU."""

    columns: int
    gutter_emu: int
    margin_left_emu: int
    margin_right_emu: int
    margin_top_emu: int
    margin_bottom_emu: int
    row_gap_emu: int
    slide_width_emu: int
    slide_height_emu: int


class SpacingData(TypedDict):
    """Jarak, padding kartu, dan divider dalam EMU."""

    sm_emu: int
    md_emu: int
    lg_emu: int
    card_padding_emu: int
    divider_emu: int


class RadiusData(TypedDict):
    """Radius sudut dalam EMU."""

    sm_emu: int
    md_emu: int
    lg_emu: int


class ShadowData(TypedDict):
    """Bayangan kartu, overlay, dan tanpa bayangan."""

    card: str
    overlay: str
    none: str


class ChartDefaultsData(TypedDict):
    """Warna elemen chart yang dipakai bersama semua theme."""

    series: tuple[str, str, str, str]
    grid: str
    axis: str
    legend: str
    title: str


class CodeData(TypedDict):
    """Tipografi blok kode."""

    family: str
    size_pt: float
    line_height: float


class TokensData(TypedDict):
    """Dokumen token dasar yang sudah divalidasi."""

    schema: str
    colors: ColorsData
    typography: TypographyData
    grid: GridData
    spacing: SpacingData
    radius: RadiusData
    shadow: ShadowData
    chart: ChartDefaultsData
    code: CodeData


class ThemeColorsData(TypedDict, total=False):
    """Override warna aksen milik satu theme."""

    accent: str
    accent_deep: str
    accent_soft: str
    accent_line: str
    accent_ink: str


# Tiga stop gradient cover milik satu theme.
CoverData = TypedDict("CoverData", {"from": str, "mid": str, "to": str})


class ThemeChartData(TypedDict):
    """Palet chart milik satu theme."""

    series: tuple[str, str, str, str]
    grid: str
    axis: str
    legend: str
    title: str


class ThemeData(TypedDict):
    """Satu theme yang sudah divalidasi."""

    label: str
    mode: str
    colors: ThemeColorsData
    cover: CoverData
    chart: ThemeChartData


class ThemesData(TypedDict):
    """Dokumen theme yang sudah divalidasi."""

    schema: str
    default: str
    themes: dict[str, ThemeData]


def _read_yaml(path: Path) -> Mapping[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DesignTokenError(f"berkas token tidak dapat dibaca: {path}") from exc
    loader = YAML(typ="safe", pure=True)
    loader.allow_duplicate_keys = False
    try:
        loaded = loader.load(text)
    except YAMLError as exc:
        raise DesignTokenError(f"berkas token bukan YAML valid: {path}: {exc}") from exc
    return _mapping(loaded, str(path))


def _mapping(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DesignTokenError(f"{where} wajib berupa mapping")
    result: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise DesignTokenError(f"{where} memuat kunci non-string")
        result[raw_key] = raw_value
    return result


def _require_exact(mapping: Mapping[str, object], keys: tuple[str, ...], where: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise DesignTokenError(f"{where} kehilangan kunci: {', '.join(missing)}")
    unexpected = [key for key in mapping if key not in keys]
    if unexpected:
        raise DesignTokenError(f"{where} memuat kunci tak dikenal: {', '.join(unexpected)}")


def _text(mapping: Mapping[str, object], key: str, where: str) -> str:
    value = mapping[key]
    if not isinstance(value, str) or not value.strip():
        raise DesignTokenError(f"{where}.{key} wajib berupa teks tidak kosong")
    return value


def _number(mapping: Mapping[str, object], key: str, where: str) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DesignTokenError(f"{where}.{key} wajib berupa angka")
    return float(value)


def _integer(mapping: Mapping[str, object], key: str, where: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise DesignTokenError(f"{where}.{key} wajib berupa bilangan bulat")
    if value <= 0:
        raise DesignTokenError(f"{where}.{key} wajib lebih besar dari nol")
    return value


def _hex_value(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise DesignTokenError(f"{where} wajib berupa warna heksadesimal")
    valid = (
        len(value) == 7 and value.startswith("#") and all(char in _HEX_DIGITS for char in value[1:])
    )
    if not valid:
        raise DesignTokenError(f"{where} wajib berupa warna heksadesimal enam digit")
    return value.upper()


def _hex(mapping: Mapping[str, object], key: str, where: str) -> str:
    return _hex_value(mapping[key], f"{where}.{key}")


def _hex_sequence(
    mapping: Mapping[str, object], key: str, where: str, length: int
) -> tuple[str, ...]:
    value = mapping[key]
    if not isinstance(value, (list, tuple)):
        raise DesignTokenError(f"{where}.{key} wajib berupa daftar warna")
    if len(value) != length:
        raise DesignTokenError(f"{where}.{key} wajib berisi tepat {length} warna")
    colors = tuple(_hex_value(item, f"{where}.{key}[{index}]") for index, item in enumerate(value))
    return colors


def _validate_colors(mapping: Mapping[str, object], where: str) -> ColorsData:
    _require_exact(mapping, _COLOR_KEYS, where)
    status_mapping = _mapping(mapping["status"], f"{where}.status")
    _require_exact(status_mapping, _STATUS_KEYS, f"{where}.status")
    return ColorsData(
        background=_hex(mapping, "background", where),
        surface=_hex(mapping, "surface", where),
        surface_alt=_hex(mapping, "surface_alt", where),
        ink=_hex(mapping, "ink", where),
        ink_secondary=_hex(mapping, "ink_secondary", where),
        muted=_hex(mapping, "muted", where),
        border=_hex(mapping, "border", where),
        accent=_hex(mapping, "accent", where),
        accent_deep=_hex(mapping, "accent_deep", where),
        accent_soft=_hex(mapping, "accent_soft", where),
        accent_line=_hex(mapping, "accent_line", where),
        accent_ink=_hex(mapping, "accent_ink", where),
        status=StatusData(
            neutral=_hex(status_mapping, "neutral", f"{where}.status"),
            success=_hex(status_mapping, "success", f"{where}.status"),
            warning=_hex(status_mapping, "warning", f"{where}.status"),
            danger=_hex(status_mapping, "danger", f"{where}.status"),
        ),
    )


def _validate_typography(mapping: Mapping[str, object], where: str) -> TypographyData:
    _require_exact(
        mapping,
        ("family", "weights", "title_pt", "body_pt", "minimum_pt", "line_height", "tracking_em"),
        where,
    )
    raw_weights = mapping["weights"]
    if not isinstance(raw_weights, (list, tuple)) or len(raw_weights) != 4:
        raise DesignTokenError(f"{where}.weights wajib berisi empat bilangan bulat")
    weights: list[int] = []
    for index, item in enumerate(raw_weights):
        if isinstance(item, bool) or not isinstance(item, int) or not 100 <= item <= 900:
            raise DesignTokenError(f"{where}.weights[{index}] wajib bilangan bulat 100-900")
        weights.append(item)
    return TypographyData(
        family=_text(mapping, "family", where),
        weights=(weights[0], weights[1], weights[2], weights[3]),
        title_pt=_number(mapping, "title_pt", where),
        body_pt=_number(mapping, "body_pt", where),
        minimum_pt=_number(mapping, "minimum_pt", where),
        line_height=_number(mapping, "line_height", where),
        tracking_em=_number(mapping, "tracking_em", where),
    )


def _validate_grid(mapping: Mapping[str, object], where: str) -> GridData:
    _require_exact(
        mapping,
        (
            "columns",
            "gutter_emu",
            "margin_left_emu",
            "margin_right_emu",
            "margin_top_emu",
            "margin_bottom_emu",
            "row_gap_emu",
            "slide_width_emu",
            "slide_height_emu",
        ),
        where,
    )
    columns = _integer(mapping, "columns", where)
    if columns != 12:
        raise DesignTokenError(f"{where}.columns wajib bernilai 12")
    return GridData(
        columns=columns,
        gutter_emu=_integer(mapping, "gutter_emu", where),
        margin_left_emu=_integer(mapping, "margin_left_emu", where),
        margin_right_emu=_integer(mapping, "margin_right_emu", where),
        margin_top_emu=_integer(mapping, "margin_top_emu", where),
        margin_bottom_emu=_integer(mapping, "margin_bottom_emu", where),
        row_gap_emu=_integer(mapping, "row_gap_emu", where),
        slide_width_emu=_integer(mapping, "slide_width_emu", where),
        slide_height_emu=_integer(mapping, "slide_height_emu", where),
    )


def _validate_spacing(mapping: Mapping[str, object], where: str) -> SpacingData:
    _require_exact(
        mapping,
        ("sm_emu", "md_emu", "lg_emu", "card_padding_emu", "divider_emu"),
        where,
    )
    return SpacingData(
        sm_emu=_integer(mapping, "sm_emu", where),
        md_emu=_integer(mapping, "md_emu", where),
        lg_emu=_integer(mapping, "lg_emu", where),
        card_padding_emu=_integer(mapping, "card_padding_emu", where),
        divider_emu=_integer(mapping, "divider_emu", where),
    )


def _validate_radius(mapping: Mapping[str, object], where: str) -> RadiusData:
    _require_exact(mapping, ("sm_emu", "md_emu", "lg_emu"), where)
    return RadiusData(
        sm_emu=_integer(mapping, "sm_emu", where),
        md_emu=_integer(mapping, "md_emu", where),
        lg_emu=_integer(mapping, "lg_emu", where),
    )


def _validate_shadow(mapping: Mapping[str, object], where: str) -> ShadowData:
    _require_exact(mapping, ("card", "overlay", "none"), where)
    return ShadowData(
        card=_text(mapping, "card", where),
        overlay=_text(mapping, "overlay", where),
        none=_text(mapping, "none", where),
    )


def _validate_chart_defaults(mapping: Mapping[str, object], where: str) -> ChartDefaultsData:
    _require_exact(mapping, ("series", "grid", "axis", "legend", "title"), where)
    series = _hex_sequence(mapping, "series", where, 4)
    return ChartDefaultsData(
        series=(series[0], series[1], series[2], series[3]),
        grid=_hex(mapping, "grid", where),
        axis=_hex(mapping, "axis", where),
        legend=_hex(mapping, "legend", where),
        title=_hex(mapping, "title", where),
    )


def _validate_code(mapping: Mapping[str, object], where: str) -> CodeData:
    _require_exact(mapping, ("family", "size_pt", "line_height"), where)
    return CodeData(
        family=_text(mapping, "family", where),
        size_pt=_number(mapping, "size_pt", where),
        line_height=_number(mapping, "line_height", where),
    )


def load_tokens() -> TokensData:
    """Muat dan validasi token dasar dari data package."""
    data = _mapping(_read_yaml(TOKENS_PATH), "tokens")
    _require_exact(data, _TOKEN_KEYS, "tokens")
    schema = _text(data, "schema", "tokens")
    if schema != TOKENS_SCHEMA:
        raise DesignTokenError(f"tokens.schema wajib bernilai {TOKENS_SCHEMA!r}")
    return TokensData(
        schema=schema,
        colors=_validate_colors(_mapping(data["colors"], "tokens.colors"), "tokens.colors"),
        typography=_validate_typography(
            _mapping(data["typography"], "tokens.typography"), "tokens.typography"
        ),
        grid=_validate_grid(_mapping(data["grid"], "tokens.grid"), "tokens.grid"),
        spacing=_validate_spacing(_mapping(data["spacing"], "tokens.spacing"), "tokens.spacing"),
        radius=_validate_radius(_mapping(data["radius"], "tokens.radius"), "tokens.radius"),
        shadow=_validate_shadow(_mapping(data["shadow"], "tokens.shadow"), "tokens.shadow"),
        chart=_validate_chart_defaults(_mapping(data["chart"], "tokens.chart"), "tokens.chart"),
        code=_validate_code(_mapping(data["code"], "tokens.code"), "tokens.code"),
    )


def _validate_theme(entry: Mapping[str, object], name: str) -> ThemeData:
    where = f"themes.themes.{name}"
    _require_exact(entry, _THEME_KEYS, where)
    mode = _text(entry, "mode", where)
    if mode != "light":
        raise DesignTokenError(f"{where}.mode wajib bernilai 'light'")
    colors = _mapping(entry["colors"], f"{where}.colors")
    _require_exact(colors, _THEME_COLOR_KEYS, f"{where}.colors")
    cover = _mapping(entry["cover"], f"{where}.cover")
    _require_exact(cover, ("from", "mid", "to"), f"{where}.cover")
    cover_data: CoverData = {
        "from": _hex(cover, "from", f"{where}.cover"),
        "mid": _hex(cover, "mid", f"{where}.cover"),
        "to": _hex(cover, "to", f"{where}.cover"),
    }
    chart = _mapping(entry["chart"], f"{where}.chart")
    _require_exact(chart, ("series", "grid", "axis", "legend", "title"), f"{where}.chart")
    series = _hex_sequence(chart, "series", f"{where}.chart", 4)
    return ThemeData(
        label=_text(entry, "label", where),
        mode=mode,
        colors=ThemeColorsData(
            accent=_hex(colors, "accent", f"{where}.colors"),
            accent_deep=_hex(colors, "accent_deep", f"{where}.colors"),
            accent_soft=_hex(colors, "accent_soft", f"{where}.colors"),
            accent_line=_hex(colors, "accent_line", f"{where}.colors"),
            accent_ink=_hex(colors, "accent_ink", f"{where}.colors"),
        ),
        cover=cover_data,
        chart=ThemeChartData(
            series=(series[0], series[1], series[2], series[3]),
            grid=_hex(chart, "grid", f"{where}.chart"),
            axis=_hex(chart, "axis", f"{where}.chart"),
            legend=_hex(chart, "legend", f"{where}.chart"),
            title=_hex(chart, "title", f"{where}.chart"),
        ),
    )


def load_themes() -> ThemesData:
    """Muat dan validasi seluruh theme yang didukung."""
    data = _mapping(_read_yaml(THEMES_PATH), "themes")
    _require_exact(data, ("schema", "default", "themes"), "themes")
    schema = _text(data, "schema", "themes")
    if schema != THEMES_SCHEMA:
        raise DesignTokenError(f"themes.schema wajib bernilai {THEMES_SCHEMA!r}")
    default = _text(data, "default", "themes")
    if default != THEME_NAMES[0]:
        raise DesignTokenError(f"themes.default wajib bernilai {THEME_NAMES[0]!r}")
    raw_themes = _mapping(data["themes"], "themes.themes")
    if tuple(raw_themes) != THEME_NAMES:
        expected = ", ".join(THEME_NAMES)
        raise DesignTokenError(f"themes.themes wajib berisi tepat: {expected}")
    themes = {
        name: _validate_theme(_mapping(raw_themes[name], f"themes.themes.{name}"), name)
        for name in THEME_NAMES
    }
    return ThemesData(schema=schema, default=default, themes=themes)


def theme_names() -> tuple[str, ...]:
    """Kembalikan nama theme yang tersedia sesuai urutan data."""
    return tuple(load_themes()["themes"])


def load_theme(name: str) -> tuple[TokensData, ThemeData]:
    """Muat token dasar dan satu theme bernama."""
    themes = load_themes()
    try:
        entry = themes["themes"][name]
    except KeyError as exc:
        available = ", ".join(themes["themes"])
        raise DesignTokenError(
            f"unknown theme (theme tidak dikenal): {name!r}; pilihan yang tersedia: {available}"
        ) from exc
    return load_tokens(), entry
