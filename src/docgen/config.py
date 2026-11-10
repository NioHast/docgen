"""Pembacaan dan validasi ``format.yml`` serta ``structure.yml``.

Skema bersifat tertutup: key yang tidak dikenal ditolak. Key lama yang sudah
dihapus menghasilkan pesan migrasi. Semua nilai dimensi dikonversi ke twip
dan semua ukuran font dikonversi ke setengah poin di lapisan ini.
"""

import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any
from xml.etree import ElementTree

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError
from ruamel.yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from . import paths as path_mod
from .errors import ConfigError

# ---------------------------------------------------------------------------
# YAML
# ---------------------------------------------------------------------------

_ALLOWED_YAML_TAGS = frozenset(
    {
        "tag:yaml.org,2002:map",
        "tag:yaml.org,2002:seq",
        "tag:yaml.org,2002:str",
        "tag:yaml.org,2002:int",
        "tag:yaml.org,2002:float",
        "tag:yaml.org,2002:bool",
        "tag:yaml.org,2002:null",
    }
)


def _walk_yaml_nodes(node: Node, *, source: Path | str, label: str) -> None:
    tag = getattr(node, "tag", None)
    if getattr(node, "anchor", None) is not None:
        raise ConfigError(
            f"{label} memakai anchor/alias YAML; alias tidak didukung",
            code="CFG-YAML-ALIAS",
            path=str(source),
            key=label,
        )
    if tag not in _ALLOWED_YAML_TAGS:
        raise ConfigError(
            f"{label} memakai tag YAML yang tidak didukung: {tag}",
            code="CFG-YAML-TYPE",
            path=str(source),
            key=label,
        )
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode) and key_node.value == "<<":
                raise ConfigError(
                    f"{label} memakai merge key '<<'; alias tidak didukung",
                    code="CFG-YAML-ALIAS",
                    path=str(source),
                    key=label,
                )
            _walk_yaml_nodes(key_node, source=source, label=label)
            _walk_yaml_nodes(value_node, source=source, label=label)
    elif isinstance(node, SequenceNode):
        for child in node.value:
            _walk_yaml_nodes(child, source=source, label=label)


def _assert_safe_value(value: Any, *, source: Path | str, label: str, key: str = "") -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_safe_value(
                item,
                source=source,
                label=label,
                key=f"{key}[{index}]" if key else str(index),
            )
        return
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise ConfigError(
                    f"{label} memuat kunci non-teks: {child_key!r}",
                    code="CFG-YAML-TYPE",
                    path=str(source),
                    key=key or label,
                )
            _assert_safe_value(
                child,
                source=source,
                label=label,
                key=f"{key}.{child_key}" if key else child_key,
            )
        return
    raise ConfigError(
        f"{label} memuat tipe YAML yang tidak didukung: {type(value).__name__}",
        code="CFG-YAML-TYPE",
        path=str(source),
        key=key or label,
    )


def parse_yaml_mapping(
    text: str,
    *,
    source: Path | str,
    label: str = "YAML",
) -> dict[str, Any]:
    """Parse YAML menjadi mapping aman, menolak duplikat/alias/tag kustom."""

    if not text.strip():
        raise ConfigError(
            f"{label} kosong",
            code="CFG-REQUIRED",
            path=str(source),
            key=label,
        )
    try:
        composer = YAML(typ="safe", pure=True)
        root_node = composer.compose(text)
    except YAMLError as exc:
        raise ConfigError(
            f"{label} tidak valid: {exc}",
            code="CFG-YAML",
            path=str(source),
            key=label,
        ) from exc

    if root_node is None:
        raise ConfigError(
            f"{label} kosong",
            code="CFG-REQUIRED",
            path=str(source),
            key=label,
        )
    _walk_yaml_nodes(root_node, source=source, label=label)
    if not isinstance(root_node, MappingNode):
        raise ConfigError(
            f"{label} wajib berupa pemetaan YAML",
            code="CFG-YAML-TYPE",
            path=str(source),
            key=label,
        )

    try:
        loader = YAML(typ="safe", pure=True)
        loader.allow_duplicate_keys = False
        data = loader.load(text)
    except DuplicateKeyError as exc:
        raise ConfigError(
            f"{label} memuat kunci YAML duplikat: {exc}",
            code="CFG-YAML-DUPLICATE",
            path=str(source),
            key=label,
        ) from exc
    except YAMLError as exc:
        raise ConfigError(
            f"{label} tidak valid: {exc}",
            code="CFG-YAML",
            path=str(source),
            key=label,
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"{label} wajib berupa pemetaan YAML",
            code="CFG-YAML-TYPE",
            path=str(source),
            key=label,
        )
    _assert_safe_value(data, source=source, label=label)
    return {str(key): value for key, value in data.items()}


def load_yaml_mapping(path: Path, *, label: str = "YAML") -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"berkas tidak ditemukan: {path}",
            code="CFG-ASSET-MISSING",
            path=path,
        ) from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(
            f"berkas harus UTF-8: {exc}",
            code="CFG-YAML",
            path=path,
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"berkas tidak dapat dibaca: {exc}",
            code="CFG-ASSET-MISSING",
            path=path,
        ) from exc
    return parse_yaml_mapping(text, source=path, label=label)


# ---------------------------------------------------------------------------
# Tipe dan nilai
# ---------------------------------------------------------------------------

_DIMENSION_RE = re.compile(
    r"^(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?P<unit>cm|mm|in|pt|twip)$"
)
_COLOR_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_ALIGNMENTS = frozenset({"left", "right", "center", "justify", "both"})


def _err(message: str, *, code: str, path: Path, key: str) -> ConfigError:
    return ConfigError(message, code=code, path=path, key=key)


def _expect_mapping(value: Any, *, path: Path, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _err(
            f"'{key}' harus berupa pemetaan",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return value


def _expect_list(value: Any, *, path: Path, key: str) -> list[Any]:
    if not isinstance(value, list):
        raise _err(
            f"'{key}' harus berupa daftar",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return value


def _check_unknown(
    mapping: Mapping[str, Any],
    allowed: Iterable[str],
    *,
    path: Path,
    key: str,
    legacy: Mapping[str, str] | None = None,
) -> None:
    allowed_set = set(allowed)
    legacy = legacy or {}
    for raw_key in mapping:
        child = str(raw_key)
        if child in allowed_set:
            continue
        if child in legacy:
            raise _err(
                f"kunci '{child}' sudah dihapus; {legacy[child]}",
                code="CFG-LEGACY",
                path=path,
                key=f"{key}.{child}" if key else child,
            )
        raise _err(
            f"kunci '{child}' tidak dikenal",
            code="CFG-UNKNOWN-KEY",
            path=path,
            key=f"{key}.{child}" if key else child,
        )


def _required(mapping: Mapping[str, Any], child: str, *, path: Path, key: str) -> Any:
    if child not in mapping or mapping[child] is None:
        raise _err(
            f"kunci '{child}' wajib diisi",
            code="CFG-REQUIRED",
            path=path,
            key=f"{key}.{child}" if key else child,
        )
    return mapping[child]


def _text(
    value: Any,
    *,
    path: Path,
    key: str,
    default: str | None = None,
    allow_empty: bool = False,
) -> str:
    if value is None:
        if default is None:
            raise _err(
                f"'{key}' wajib diisi",
                code="CFG-REQUIRED",
                path=path,
                key=key,
            )
        text = default
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise _err(
            f"'{key}' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    if not text and not allow_empty:
        raise _err(
            f"'{key}' tidak boleh kosong",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    return text


def _boolean(value: Any, *, path: Path, key: str, default: bool | None = None) -> bool:
    if value is None:
        if default is None:
            raise _err(
                f"'{key}' wajib diisi",
                code="CFG-REQUIRED",
                path=path,
                key=key,
            )
        return default
    if not isinstance(value, bool):
        raise _err(
            f"'{key}' harus bernilai true/false",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return value


def _number(
    value: Any,
    *,
    path: Path,
    key: str,
    default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if value is None:
        if default is None:
            raise _err(
                f"'{key}' wajib diisi",
                code="CFG-REQUIRED",
                path=path,
                key=key,
            )
        result = default
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _err(
            f"'{key}' harus berupa angka",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    else:
        result = float(value)
    if minimum is not None and result < minimum:
        raise _err(
            f"'{key}' harus >= {minimum}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    if maximum is not None and result > maximum:
        raise _err(
            f"'{key}' harus <= {maximum}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return result


def _dimension(
    value: Any,
    *,
    path: Path,
    key: str,
    default: str | None = None,
    minimum: int = 0,
    positive: bool = False,
) -> int:
    raw = value if value is not None else default
    if raw is None:
        raise _err(
            f"'{key}' wajib diisi",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    if not isinstance(raw, str):
        raise _err(
            f"'{key}' harus berupa dimensi teks (mis. 4cm)",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    match = _DIMENSION_RE.fullmatch(raw.strip())
    if match is None:
        raise _err(
            f"'{key}' bukan dimensi yang valid: {raw!r}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    number = float(match.group("value"))
    unit = match.group("unit")
    factor = {"cm": 1440 / 2.54, "mm": 1440 / 25.4, "in": 1440, "pt": 20, "twip": 1}[unit]
    twips = round(number * factor)
    if positive and twips <= 0:
        raise _err(
            f"'{key}' harus > 0",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    if not positive and twips < minimum:
        raise _err(
            f"'{key}' harus >= {minimum} twip",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return twips


def _font_size(value: Any, *, path: Path, key: str, default: str | None = None) -> int:
    raw = value if value is not None else default
    if raw is None:
        raise _err(
            f"'{key}' wajib diisi",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    if not isinstance(raw, str):
        raise _err(
            f"'{key}' harus berupa ukuran font (mis. 12pt)",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    match = _DIMENSION_RE.fullmatch(raw.strip())
    if match is None or match.group("unit") != "pt":
        raise _err(
            f"'{key}' harus memakai satuan pt: {raw!r}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    points = float(match.group("value"))
    if points < 6 or points > 72:
        raise _err(
            f"'{key}' harus 6-72 pt",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return round(points * 2)


def _color(value: Any, *, path: Path, key: str, default: str = "000000") -> str:
    raw = value if value is not None else default
    if not isinstance(raw, str) or not _COLOR_RE.fullmatch(raw.strip()):
        raise _err(
            f"'{key}' harus berupa warna heksadesimal 6 digit",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return raw.strip().upper()


def _alignment(value: Any, *, path: Path, key: str, default: str = "justify") -> str:
    raw = value if value is not None else default
    if not isinstance(raw, str) or raw.strip().lower() not in _ALIGNMENTS:
        raise _err(
            f"'{key}' harus salah satu: {', '.join(sorted(_ALIGNMENTS))}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    text = raw.strip().lower()
    return "justify" if text == "both" else text


def _enum(
    value: Any,
    *,
    path: Path,
    key: str,
    choices: Iterable[str],
    default: str | None = None,
) -> str:
    raw = value if value is not None else default
    allowed = set(choices)
    if not isinstance(raw, str) or raw not in allowed:
        raise _err(
            f"'{key}' harus salah satu: {', '.join(sorted(allowed))}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return raw


def _text_list(
    value: Any, *, path: Path, key: str, default: tuple[str, ...] = ()
) -> tuple[str, ...]:
    raw = value if value is not None else list(default)
    if not isinstance(raw, list):
        raise _err(
            f"'{key}' harus berupa daftar teks",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, str) or not item.strip():
            raise _err(
                f"item ke-{index} pada '{key}' harus berupa teks tidak kosong",
                code="CFG-TYPE",
                path=path,
                key=f"{key}[{index}]",
            )
        text = item.strip()
        folded = text.casefold()
        if folded in seen:
            raise _err(
                f"item '{text}' duplikat pada '{key}'",
                code="CFG-DUPLICATE",
                path=path,
                key=key,
            )
        seen.add(folded)
        result.append(text)
    if not result:
        raise _err(
            f"'{key}' minimal memuat satu item",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    return tuple(result)


# ---------------------------------------------------------------------------
# Model format
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Margins:
    top: int
    bottom: int
    left: int
    right: int


@dataclass(frozen=True)
class PageFormat:
    size: str
    orientation: str
    margins: Margins
    header_distance: int
    footer_distance: int
    gutter: int


@dataclass(frozen=True)
class BodyFont:
    family: str
    size_half_points: int
    color: str
    line_spacing: float
    space_before: int
    space_after: int
    alignment: str
    first_line_indent: int


@dataclass(frozen=True)
class MonoFont:
    family: str
    size_half_points: int


@dataclass(frozen=True)
class FontFormat:
    body: BodyFont
    monospace: MonoFont


@dataclass(frozen=True)
class HeadingStyle:
    font_family: str
    font_size_half_points: int
    bold: bool
    color: str
    alignment: str
    space_before: int
    space_after: int
    line_spacing: float
    keep_next: bool
    keep_lines: bool
    outline_level: int
    first_line_indent: int
    indent_left: int
    indent_hanging: int


@dataclass(frozen=True)
class TocHeadingStyle:
    heading_style: str
    font_family: str
    font_size_half_points: int
    bold: bool
    color: str
    alignment: str
    space_before: int
    space_after: int
    line_spacing: float
    first_line_indent: int


@dataclass(frozen=True)
class CaptionFont:
    family: str
    size_half_points: int
    bold: bool
    italic: bool
    color: str
    alignment: str
    space_before: int
    space_after: int
    line_spacing: float


@dataclass(frozen=True)
class CaptionStyle:
    label: str
    separator: str
    font: CaptionFont
    keep_next: bool = False


@dataclass(frozen=True)
class CaptionsFormat:
    figure: CaptionStyle
    table: CaptionStyle


@dataclass(frozen=True)
class FigureStyle:
    caption_alignment: str
    image_alignment: str
    numbering: str
    space_before: int
    space_after: int
    first_line_indent: int


@dataclass(frozen=True)
class CodeFont:
    family: str
    size_half_points: int
    color: str


@dataclass(frozen=True)
class CodeBorder:
    style: str
    width: int
    color: str


@dataclass(frozen=True)
class CodeTable:
    width_percent: int
    cell_margin: int


@dataclass(frozen=True)
class CodeFormat:
    style: str
    font: CodeFont
    line_spacing: float
    space_before: int
    space_after: int
    alignment: str
    shading: str
    border: CodeBorder
    table: CodeTable
    detect_styles: tuple[str, ...]


@dataclass(frozen=True)
class BibliographyStyle:
    heading: str
    font_family: str
    font_size_half_points: int
    line_spacing: float
    space_before: int
    space_after: int
    indent_left: int
    indent_hanging: int


@dataclass(frozen=True)
class CitationFormat:
    csl: Path
    bibliography: str
    locale: str


@dataclass(frozen=True)
class AssetsFormat:
    logo: Path
    reference_docx: Path


@dataclass(frozen=True)
class Format:
    id: str
    name: str
    description: str
    path: Path
    data: Mapping[str, Any]
    page: PageFormat
    font: FontFormat
    headings: Mapping[str, HeadingStyle]
    toc_heading: TocHeadingStyle
    captions: CaptionsFormat
    figures: FigureStyle
    code: CodeFormat
    bibliography_style: BibliographyStyle
    citation: CitationFormat
    assets: AssetsFormat


_FORMAT_KEYS = frozenset(
    {
        "format",
        "name",
        "description",
        "page",
        "font",
        "headings",
        "toc_heading",
        "captions",
        "figures",
        "code",
        "bibliography_style",
        "citation",
        "assets",
    }
)
_FORMAT_LEGACY = {
    "presets": "gabungkan ke satu format.yml",
    "preset": "gunakan kunci 'format'",
    "margin_preset": "margin ditulis eksplisit di page.margins",
    "toc": "gunakan 'toc_heading'; toggle daftar isi ada di structure.toc",
    "bibliography": "gunakan 'bibliography_style' dan citation.bibliography",
}
_PAGE_KEYS = frozenset(
    {"size", "orientation", "margins", "header_distance", "footer_distance", "gutter"}
)
_MARGIN_KEYS = frozenset({"top", "bottom", "left", "right"})
_FONT_KEYS = frozenset({"body", "monospace"})
_BODY_FONT_KEYS = frozenset(
    {
        "family",
        "size",
        "color",
        "line_spacing",
        "space_before",
        "space_after",
        "alignment",
        "first_line_indent",
    }
)
_MONO_FONT_KEYS = frozenset({"family", "size"})
_HEADINGS_KEYS = frozenset({"styles"})
_HEADING_STYLE_KEYS = frozenset(
    {
        "font_family",
        "font_size",
        "bold",
        "color",
        "alignment",
        "space_before",
        "space_after",
        "line_spacing",
        "keep_next",
        "keep_lines",
        "outline_level",
        "first_line_indent",
        "indent_left",
        "indent_hanging",
    }
)
_TOC_HEADING_KEYS = frozenset(
    {
        "heading_style",
        "font",
        "size",
        "bold",
        "color",
        "alignment",
        "space_before",
        "space_after",
        "line_spacing",
        "first_line_indent",
    }
)
_CAPTIONS_KEYS = frozenset({"figure", "table"})
_CAPTION_KEYS = frozenset({"label", "separator", "keep_next", "font"})
_CAPTION_FONT_KEYS = frozenset(
    {
        "family",
        "size",
        "bold",
        "italic",
        "color",
        "space_before",
        "space_after",
        "line_spacing",
    }
)
_TABLE_CAPTION_FONT_KEYS = _CAPTION_FONT_KEYS | {"alignment"}
_FIGURE_KEYS = frozenset(
    {
        "caption_alignment",
        "image_alignment",
        "numbering",
        "space_before",
        "space_after",
        "first_line_indent",
    }
)
_CODE_KEYS = frozenset(
    {
        "style",
        "font",
        "line_spacing",
        "space_before",
        "space_after",
        "alignment",
        "shading",
        "border",
        "table",
        "detect_styles",
    }
)
_CODE_FONT_KEYS = frozenset({"family", "size", "color"})
_CODE_BORDER_KEYS = frozenset({"style", "width", "color"})
_CODE_TABLE_KEYS = frozenset({"width", "cell_margin"})
_BIBLIOGRAPHY_STYLE_KEYS = frozenset(
    {
        "heading",
        "font",
        "size",
        "line_spacing",
        "space_before",
        "space_after",
        "indent_left",
        "indent_hanging",
    }
)
_CITATION_KEYS = frozenset({"csl", "bibliography", "locale"})
_ASSETS_KEYS = frozenset({"logo", "reference_docx"})
_DEFAULT_DETECT_STYLES = (
    "Source Code",
    "Verbatim Char",
    "HTML Code",
    "HTML Preformatted",
)


def _parse_page(data: Mapping[str, Any], *, path: Path) -> PageFormat:
    _check_unknown(data, _PAGE_KEYS, path=path, key="page")
    margins = _expect_mapping(
        _required(data, "margins", path=path, key="page"),
        path=path,
        key="page.margins",
    )
    _check_unknown(margins, _MARGIN_KEYS, path=path, key="page.margins")
    return PageFormat(
        size=_enum(
            data.get("size"),
            path=path,
            key="page.size",
            choices=("A4", "Letter"),
            default="A4",
        ),
        orientation=_enum(
            data.get("orientation"),
            path=path,
            key="page.orientation",
            choices=("portrait", "landscape"),
            default="portrait",
        ),
        margins=Margins(
            top=_dimension(
                _required(margins, "top", path=path, key="page.margins"),
                path=path,
                key="page.margins.top",
                positive=True,
            ),
            bottom=_dimension(
                _required(margins, "bottom", path=path, key="page.margins"),
                path=path,
                key="page.margins.bottom",
                positive=True,
            ),
            left=_dimension(
                _required(margins, "left", path=path, key="page.margins"),
                path=path,
                key="page.margins.left",
                positive=True,
            ),
            right=_dimension(
                _required(margins, "right", path=path, key="page.margins"),
                path=path,
                key="page.margins.right",
                positive=True,
            ),
        ),
        header_distance=_dimension(
            data.get("header_distance"),
            path=path,
            key="page.header_distance",
            default="1.27cm",
        ),
        footer_distance=_dimension(
            data.get("footer_distance"),
            path=path,
            key="page.footer_distance",
            default="1.27cm",
        ),
        gutter=_dimension(
            data.get("gutter"),
            path=path,
            key="page.gutter",
            default="0cm",
        ),
    )


def _parse_body_font(data: Mapping[str, Any], *, path: Path) -> BodyFont:
    _check_unknown(data, _BODY_FONT_KEYS, path=path, key="font.body")
    return BodyFont(
        family=_text(
            _required(data, "family", path=path, key="font.body"),
            path=path,
            key="font.body.family",
        ),
        size_half_points=_font_size(
            _required(data, "size", path=path, key="font.body"),
            path=path,
            key="font.body.size",
        ),
        color=_color(data.get("color"), path=path, key="font.body.color"),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key="font.body.line_spacing",
            default=1.5,
            minimum=0.5,
            maximum=3.0,
        ),
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key="font.body.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key="font.body.space_after",
            default="0pt",
        ),
        alignment=_alignment(data.get("alignment"), path=path, key="font.body.alignment"),
        first_line_indent=_dimension(
            data.get("first_line_indent"),
            path=path,
            key="font.body.first_line_indent",
            default="1.25cm",
        ),
    )


def _parse_mono_font(data: Mapping[str, Any], *, path: Path) -> MonoFont:
    _check_unknown(data, _MONO_FONT_KEYS, path=path, key="font.monospace")
    return MonoFont(
        family=_text(
            data.get("family") or "Courier New",
            path=path,
            key="font.monospace.family",
        ),
        size_half_points=_font_size(
            data.get("size"),
            path=path,
            key="font.monospace.size",
            default="10pt",
        ),
    )


def _parse_heading_style(
    data: Mapping[str, Any],
    *,
    level: int,
    body: BodyFont,
    path: Path,
) -> HeadingStyle:
    key = f"headings.styles.heading{level}"
    _check_unknown(data, _HEADING_STYLE_KEYS, path=path, key=key)
    default_alignment = "center" if level == 1 else "justify"
    default_indent = "0cm" if level == 1 else "1.25cm"
    return HeadingStyle(
        font_family=_text(
            data.get("font_family") or body.family,
            path=path,
            key=f"{key}.font_family",
        ),
        font_size_half_points=_font_size(
            data.get("font_size"),
            path=path,
            key=f"{key}.font_size",
            default=f"{body.size_half_points / 2:g}pt",
        ),
        bold=_boolean(data.get("bold"), path=path, key=f"{key}.bold", default=True),
        color=_color(data.get("color"), path=path, key=f"{key}.color"),
        alignment=_alignment(
            data.get("alignment"),
            path=path,
            key=f"{key}.alignment",
            default=default_alignment,
        ),
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key=f"{key}.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key=f"{key}.space_after",
            default="0pt",
        ),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key=f"{key}.line_spacing",
            default=body.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
        keep_next=_boolean(data.get("keep_next"), path=path, key=f"{key}.keep_next", default=True),
        keep_lines=_boolean(
            data.get("keep_lines"), path=path, key=f"{key}.keep_lines", default=True
        ),
        outline_level=int(
            _number(
                data.get("outline_level"),
                path=path,
                key=f"{key}.outline_level",
                default=float(level - 1),
                minimum=0,
                maximum=8,
            )
        ),
        first_line_indent=_dimension(
            data.get("first_line_indent"),
            path=path,
            key=f"{key}.first_line_indent",
            default="0cm",
        ),
        indent_left=_dimension(
            data.get("indent_left"),
            path=path,
            key=f"{key}.indent_left",
            default=default_indent,
        ),
        indent_hanging=_dimension(
            data.get("indent_hanging"),
            path=path,
            key=f"{key}.indent_hanging",
            default=default_indent,
        ),
    )


def _parse_toc_heading(
    data: Mapping[str, Any] | None,
    *,
    heading1: HeadingStyle,
    path: Path,
) -> TocHeadingStyle:
    if data is None:
        return TocHeadingStyle(
            heading_style="TOCHeading",
            font_family=heading1.font_family,
            font_size_half_points=heading1.font_size_half_points,
            bold=heading1.bold,
            color=heading1.color,
            alignment=heading1.alignment,
            space_before=heading1.space_before,
            space_after=heading1.space_after,
            line_spacing=heading1.line_spacing,
            first_line_indent=heading1.first_line_indent,
        )

    _check_unknown(data, _TOC_HEADING_KEYS, path=path, key="toc_heading")
    font_raw = data.get("font")
    if font_raw is not None and not isinstance(font_raw, str):
        raise _err(
            "'toc_heading.font' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key="toc_heading.font",
        )
    return TocHeadingStyle(
        heading_style=_text(
            data.get("heading_style") or "TOCHeading",
            path=path,
            key="toc_heading.heading_style",
        ),
        font_family=_text(
            font_raw or heading1.font_family,
            path=path,
            key="toc_heading.font",
        ),
        font_size_half_points=_font_size(
            data.get("size"),
            path=path,
            key="toc_heading.size",
            default=f"{heading1.font_size_half_points / 2:g}pt",
        ),
        bold=_boolean(
            data.get("bold"),
            path=path,
            key="toc_heading.bold",
            default=heading1.bold,
        ),
        color=_color(
            data.get("color"),
            path=path,
            key="toc_heading.color",
            default=heading1.color,
        ),
        alignment=_alignment(
            data.get("alignment"),
            path=path,
            key="toc_heading.alignment",
            default=heading1.alignment,
        ),
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key="toc_heading.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key="toc_heading.space_after",
            default="0pt",
        ),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key="toc_heading.line_spacing",
            default=heading1.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
        first_line_indent=_dimension(
            data.get("first_line_indent"),
            path=path,
            key="toc_heading.first_line_indent",
            default="0cm",
        ),
    )


def _parse_caption_font(
    data: Mapping[str, Any],
    *,
    key: str,
    path: Path,
    defaults: CaptionFont,
    allow_alignment: bool,
) -> CaptionFont:
    _check_unknown(
        data,
        _TABLE_CAPTION_FONT_KEYS if allow_alignment else _CAPTION_FONT_KEYS,
        path=path,
        key=key,
    )
    alignment = defaults.alignment
    if allow_alignment:
        alignment = _alignment(
            data.get("alignment"),
            path=path,
            key=f"{key}.alignment",
            default=defaults.alignment,
        )
    return CaptionFont(
        family=_text(
            data.get("family") or defaults.family,
            path=path,
            key=f"{key}.family",
        ),
        size_half_points=_font_size(
            data.get("size"),
            path=path,
            key=f"{key}.size",
            default=f"{defaults.size_half_points / 2:g}pt",
        ),
        bold=_boolean(data.get("bold"), path=path, key=f"{key}.bold", default=defaults.bold),
        italic=_boolean(
            data.get("italic"), path=path, key=f"{key}.italic", default=defaults.italic
        ),
        color=_color(data.get("color"), path=path, key=f"{key}.color", default=defaults.color),
        alignment=alignment,
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key=f"{key}.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key=f"{key}.space_after",
            default="0pt",
        ),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key=f"{key}.line_spacing",
            default=defaults.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
    )


def _parse_captions(
    data: Mapping[str, Any] | None,
    *,
    body: BodyFont,
    path: Path,
) -> CaptionsFormat:
    default_figure_font = CaptionFont(
        family=body.family,
        size_half_points=20,
        bold=False,
        italic=False,
        color="000000",
        alignment="center",
        space_before=0,
        space_after=0,
        line_spacing=1.0,
    )
    default_table_font = replace(default_figure_font, alignment="left")
    if data is None:
        return CaptionsFormat(
            figure=CaptionStyle("Gambar", " ", default_figure_font),
            table=CaptionStyle("Tabel", " ", default_table_font, keep_next=True),
        )

    _check_unknown(data, _CAPTIONS_KEYS, path=path, key="captions")

    figure_raw = _expect_mapping(data.get("figure", {}), path=path, key="captions.figure")
    _check_unknown(figure_raw, _CAPTION_KEYS, path=path, key="captions.figure")
    figure_font_raw = _expect_mapping(
        figure_raw.get("font", {}), path=path, key="captions.figure.font"
    )
    figure_font = _parse_caption_font(
        figure_font_raw,
        key="captions.figure.font",
        path=path,
        defaults=default_figure_font,
        allow_alignment=False,
    )

    table_raw = _expect_mapping(data.get("table", {}), path=path, key="captions.table")
    _check_unknown(table_raw, _CAPTION_KEYS, path=path, key="captions.table")
    table_font_raw = _expect_mapping(
        table_raw.get("font", {}), path=path, key="captions.table.font"
    )
    table_font = _parse_caption_font(
        table_font_raw,
        key="captions.table.font",
        path=path,
        defaults=default_table_font,
        allow_alignment=True,
    )
    table_keep_next = _boolean(
        table_raw.get("keep_next"),
        path=path,
        key="captions.table.keep_next",
        default=True,
    )
    if not table_keep_next:
        raise _err(
            "captions.table.keep_next harus true",
            code="CFG-TYPE",
            path=path,
            key="captions.table.keep_next",
        )

    figure = CaptionStyle(
        label=_text(
            figure_raw.get("label") or "Gambar",
            path=path,
            key="captions.figure.label",
        ),
        separator=_text(
            figure_raw.get("separator", " "),
            path=path,
            key="captions.figure.separator",
            allow_empty=True,
        ),
        font=figure_font,
    )
    table = CaptionStyle(
        label=_text(
            table_raw.get("label") or "Tabel",
            path=path,
            key="captions.table.label",
        ),
        separator=_text(
            table_raw.get("separator", " "),
            path=path,
            key="captions.table.separator",
            allow_empty=True,
        ),
        font=table_font,
        keep_next=table_keep_next,
    )
    for separator_key, separator in (
        ("captions.figure.separator", figure.separator),
        ("captions.table.separator", table.separator),
    ):
        if "\n" in separator or "\r" in separator:
            raise _err(
                f"{separator_key} tidak boleh memuat baris baru",
                code="CFG-TYPE",
                path=path,
                key=separator_key,
            )
    return CaptionsFormat(figure=figure, table=table)


def _parse_figures(
    data: Mapping[str, Any] | None,
    *,
    path: Path,
) -> FigureStyle:
    raw = data or {}
    _check_unknown(raw, _FIGURE_KEYS, path=path, key="figures")
    return FigureStyle(
        caption_alignment=_alignment(
            raw.get("caption_alignment"),
            path=path,
            key="figures.caption_alignment",
            default="center",
        ),
        image_alignment=_alignment(
            raw.get("image_alignment"),
            path=path,
            key="figures.image_alignment",
            default="center",
        ),
        numbering=_enum(
            raw.get("numbering"),
            path=path,
            key="figures.numbering",
            choices=("chapter", "document"),
            default="chapter",
        ),
        space_before=_dimension(
            raw.get("space_before"),
            path=path,
            key="figures.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            raw.get("space_after"),
            path=path,
            key="figures.space_after",
            default="0pt",
        ),
        first_line_indent=_dimension(
            raw.get("first_line_indent"),
            path=path,
            key="figures.first_line_indent",
            default="0cm",
        ),
    )


def _parse_code(
    data: Mapping[str, Any] | None,
    *,
    mono: MonoFont,
    path: Path,
) -> CodeFormat:
    raw = data or {}
    _check_unknown(raw, _CODE_KEYS, path=path, key="code")
    font_raw = _expect_mapping(raw.get("font", {}), path=path, key="code.font")
    _check_unknown(font_raw, _CODE_FONT_KEYS, path=path, key="code.font")
    border_raw = _expect_mapping(raw.get("border", {}), path=path, key="code.border")
    _check_unknown(border_raw, _CODE_BORDER_KEYS, path=path, key="code.border")
    table_raw = _expect_mapping(raw.get("table", {}), path=path, key="code.table")
    _check_unknown(table_raw, _CODE_TABLE_KEYS, path=path, key="code.table")
    width = raw.get("table", {}).get("width", "100%")
    if width != "100%":
        raise _err(
            "code.table.width harus 100%",
            code="CFG-TYPE",
            path=path,
            key="code.table.width",
        )
    shading = raw.get("shading", "none")
    if shading != "none":
        raise _err(
            "code.shading hanya mendukung 'none'",
            code="CFG-TYPE",
            path=path,
            key="code.shading",
        )
    border_style = border_raw.get("style", "single")
    if border_style != "single":
        raise _err(
            "code.border.style harus 'single'",
            code="CFG-TYPE",
            path=path,
            key="code.border.style",
        )
    return CodeFormat(
        style=_text(raw.get("style") or "SourceCode", path=path, key="code.style"),
        font=CodeFont(
            family=_text(
                font_raw.get("family") or mono.family,
                path=path,
                key="code.font.family",
            ),
            size_half_points=_font_size(
                font_raw.get("size"),
                path=path,
                key="code.font.size",
                default=f"{mono.size_half_points / 2:g}pt",
            ),
            color=_color(font_raw.get("color"), path=path, key="code.font.color"),
        ),
        line_spacing=_number(
            raw.get("line_spacing"),
            path=path,
            key="code.line_spacing",
            default=1.0,
            minimum=0.5,
            maximum=3.0,
        ),
        space_before=_dimension(
            raw.get("space_before"),
            path=path,
            key="code.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            raw.get("space_after"),
            path=path,
            key="code.space_after",
            default="0pt",
        ),
        alignment=_alignment(
            raw.get("alignment"),
            path=path,
            key="code.alignment",
            default="left",
        ),
        shading=shading,
        border=CodeBorder(
            style=border_style,
            width=_dimension(
                border_raw.get("width"),
                path=path,
                key="code.border.width",
                default="1pt",
                positive=True,
            ),
            color=_color(border_raw.get("color"), path=path, key="code.border.color"),
        ),
        table=CodeTable(
            width_percent=100,
            cell_margin=_dimension(
                table_raw.get("cell_margin"),
                path=path,
                key="code.table.cell_margin",
                default="108twip",
            ),
        ),
        detect_styles=_text_list(
            raw.get("detect_styles"),
            path=path,
            key="code.detect_styles",
            default=_DEFAULT_DETECT_STYLES,
        ),
    )


def _parse_bibliography_style(
    data: Mapping[str, Any] | None,
    *,
    body: BodyFont,
    path: Path,
) -> BibliographyStyle:
    raw = data or {}
    _check_unknown(raw, _BIBLIOGRAPHY_STYLE_KEYS, path=path, key="bibliography_style")
    font_value = raw.get("font")
    if font_value is not None and not isinstance(font_value, str):
        raise _err(
            "'bibliography_style.font' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key="bibliography_style.font",
        )
    return BibliographyStyle(
        heading=_text(
            raw.get("heading") or "DAFTAR PUSTAKA",
            path=path,
            key="bibliography_style.heading",
        ),
        font_family=_text(
            font_value or body.family,
            path=path,
            key="bibliography_style.font",
        ),
        font_size_half_points=_font_size(
            raw.get("size"),
            path=path,
            key="bibliography_style.size",
            default=f"{body.size_half_points / 2:g}pt",
        ),
        line_spacing=_number(
            raw.get("line_spacing"),
            path=path,
            key="bibliography_style.line_spacing",
            default=body.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
        space_before=_dimension(
            raw.get("space_before"),
            path=path,
            key="bibliography_style.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            raw.get("space_after"),
            path=path,
            key="bibliography_style.space_after",
            default="0pt",
        ),
        indent_left=_dimension(
            raw.get("indent_left"),
            path=path,
            key="bibliography_style.indent_left",
            default="1.27cm",
        ),
        indent_hanging=_dimension(
            raw.get("indent_hanging"),
            path=path,
            key="bibliography_style.indent_hanging",
            default="1.27cm",
        ),
    )


def _validate_image(path: Path) -> None:
    try:
        data = path.read_bytes()[:16]
    except OSError as exc:
        raise _err(
            f"logo tidak dapat dibaca: {exc}",
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.logo",
        ) from exc
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        valid = data.startswith(b"\xff\xd8\xff")
    elif suffix == ".png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n")
    else:
        valid = False
    if not valid:
        raise _err(
            "logo harus berupa JPEG/PNG yang valid",
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.logo",
        )


def _validate_reference_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise _err(
                    f"reference.docx rusak pada part {bad}",
                    code="CFG-ASSET-INVALID",
                    path=path,
                    key="assets.reference_docx",
                )
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise _err(
            "reference.docx bukan ZIP yang valid",
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.reference_docx",
        ) from exc
    required = {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}
    missing = sorted(required - names)
    if missing:
        raise _err(
            "reference.docx tidak memuat part wajib: " + ", ".join(missing),
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.reference_docx",
        )


def _validate_csl(path: Path) -> None:
    try:
        ElementTree.parse(path)
    except (ElementTree.ParseError, OSError) as exc:
        raise _err(
            f"citation.csl bukan XML yang valid: {exc}",
            code="CFG-ASSET-INVALID",
            path=path,
            key="citation.csl",
        ) from exc


def _parse_citation(data: Mapping[str, Any], *, format_dir: Path, path: Path) -> CitationFormat:
    _check_unknown(data, _CITATION_KEYS, path=path, key="citation")
    csl = path_mod.safe_relative_path(
        _required(data, "csl", path=path, key="citation"),
        base=format_dir,
        label="citation.csl",
        code="CFG-ASSET-MISSING",
        must_exist=True,
        expect_file=True,
    )
    if csl.suffix.lower() != ".csl":
        raise _err(
            "citation.csl harus berekstensi .csl",
            code="CFG-TYPE",
            path=path,
            key="citation.csl",
        )
    _validate_csl(csl)
    bibliography = _text(
        data.get("bibliography") or "references.bib",
        path=path,
        key="citation.bibliography",
    )
    path_mod.safe_relative_path(
        bibliography,
        base=format_dir,
        label="citation.bibliography",
        code="CFG-PATH-ESCAPE",
    )
    if not bibliography.lower().endswith(".bib"):
        raise _err(
            "citation.bibliography harus berekstensi .bib",
            code="CFG-TYPE",
            path=path,
            key="citation.bibliography",
        )
    locale = _text(data.get("locale") or "id-ID", path=path, key="citation.locale")
    return CitationFormat(
        csl=csl,
        bibliography=bibliography,
        locale=locale,
    )


def _parse_assets(data: Mapping[str, Any] | None, *, format_dir: Path, path: Path) -> AssetsFormat:
    raw = data or {}
    _check_unknown(raw, _ASSETS_KEYS, path=path, key="assets")
    logo = path_mod.safe_relative_path(
        raw.get("logo") or "logo.jpg",
        base=format_dir,
        label="assets.logo",
        code="CFG-ASSET-MISSING",
        must_exist=True,
        expect_file=True,
    )
    if logo.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise _err(
            "assets.logo harus .jpg, .jpeg, atau .png",
            code="CFG-TYPE",
            path=path,
            key="assets.logo",
        )
    _validate_image(logo)
    reference = path_mod.safe_relative_path(
        raw.get("reference_docx") or "reference.docx",
        base=format_dir,
        label="assets.reference_docx",
        code="CFG-ASSET-MISSING",
        must_exist=True,
        expect_file=True,
    )
    _validate_reference_docx(reference)
    return AssetsFormat(
        logo=logo,
        reference_docx=reference,
    )


def load_format(format_id: str, *, root: Path | None = None) -> Format:
    """Muat dan validasi ``formats/<format_id>/format.yml``."""

    path_mod.validate_id(format_id, kind="format")
    directory = path_mod.format_dir(format_id, root=root)
    path = directory / "format.yml"
    if not path.is_file():
        raise ConfigError(
            f"format '{format_id}': format.yml tidak ditemukan",
            code="CFG-FORMAT-MISSING",
            path=path,
        )
    data = load_yaml_mapping(path, label="format.yml")
    _check_unknown(
        data,
        _FORMAT_KEYS,
        path=path,
        key="format",
        legacy=_FORMAT_LEGACY,
    )
    declared = _text(
        _required(data, "format", path=path, key="format"),
        path=path,
        key="format.format",
    )
    if declared != format_id:
        raise _err(
            f"key 'format' bernilai '{declared}', tetapi direktori bernama '{format_id}'",
            code="CFG-TYPE",
            path=path,
            key="format.format",
        )

    page = _parse_page(
        _expect_mapping(_required(data, "page", path=path, key="format"), path=path, key="page"),
        path=path,
    )
    font_raw = _expect_mapping(
        _required(data, "font", path=path, key="format"), path=path, key="font"
    )
    _check_unknown(font_raw, _FONT_KEYS, path=path, key="font")
    body = _parse_body_font(
        _expect_mapping(
            _required(font_raw, "body", path=path, key="font"), path=path, key="font.body"
        ),
        path=path,
    )
    mono = _parse_mono_font(
        _expect_mapping(font_raw.get("monospace", {}), path=path, key="font.monospace"),
        path=path,
    )
    font = FontFormat(body=body, monospace=mono)

    headings_raw = _expect_mapping(
        _required(data, "headings", path=path, key="format"),
        path=path,
        key="headings",
    )
    _check_unknown(headings_raw, _HEADINGS_KEYS, path=path, key="headings")
    styles_raw = _expect_mapping(
        _required(headings_raw, "styles", path=path, key="headings"),
        path=path,
        key="headings.styles",
    )
    expected_levels = {f"heading{level}" for level in (1, 2, 3)}
    _check_unknown(styles_raw, expected_levels, path=path, key="headings.styles")
    headings: dict[str, HeadingStyle] = {}
    for level in (1, 2, 3):
        style_key = f"heading{level}"
        style_raw = _expect_mapping(
            _required(styles_raw, style_key, path=path, key="headings.styles"),
            path=path,
            key=f"headings.styles.{style_key}",
        )
        headings[style_key] = _parse_heading_style(style_raw, level=level, body=body, path=path)

    toc_heading = _parse_toc_heading(
        _expect_mapping(data["toc_heading"], path=path, key="toc_heading")
        if data.get("toc_heading") is not None
        else None,
        heading1=headings["heading1"],
        path=path,
    )

    captions = _parse_captions(
        _expect_mapping(data["captions"], path=path, key="captions")
        if data.get("captions") is not None
        else None,
        body=body,
        path=path,
    )
    figures = _parse_figures(
        _expect_mapping(data["figures"], path=path, key="figures")
        if data.get("figures") is not None
        else None,
        path=path,
    )
    # Perataan caption gambar adalah milik figures.caption_alignment, bukan
    # captions.figure.font.alignment.
    captions = replace(
        captions,
        figure=replace(
            captions.figure,
            font=replace(captions.figure.font, alignment=figures.caption_alignment),
        ),
    )

    code = _parse_code(
        _expect_mapping(data["code"], path=path, key="code")
        if data.get("code") is not None
        else None,
        mono=mono,
        path=path,
    )
    bibliography_style = _parse_bibliography_style(
        _expect_mapping(data["bibliography_style"], path=path, key="bibliography_style")
        if data.get("bibliography_style") is not None
        else None,
        body=body,
        path=path,
    )
    citation = _parse_citation(
        _expect_mapping(
            _required(data, "citation", path=path, key="format"),
            path=path,
            key="citation",
        ),
        format_dir=directory,
        path=path,
    )
    assets = _parse_assets(
        _expect_mapping(data["assets"], path=path, key="assets")
        if data.get("assets") is not None
        else None,
        format_dir=directory,
        path=path,
    )
    path_mod.check_case_collisions(directory, label="format")

    return Format(
        id=format_id,
        name=_text(data.get("name") or format_id, path=path, key="name"),
        description=_text(
            data.get("description", ""),
            path=path,
            key="description",
            default="",
            allow_empty=True,
        ),
        path=directory,
        data=MappingProxyType(dict(data)),
        page=page,
        font=font,
        headings=MappingProxyType(headings),
        toc_heading=toc_heading,
        captions=captions,
        figures=figures,
        code=code,
        bibliography_style=bibliography_style,
        citation=citation,
        assets=assets,
    )


# ---------------------------------------------------------------------------
# Model struktur
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrontMatterItem:
    id: str
    source: str
    template: str | None = None


@dataclass(frozen=True)
class BodyChapter:
    id: str
    title: str


@dataclass(frozen=True)
class BackMatterItem:
    id: str
    source: str


@dataclass(frozen=True)
class Numbering:
    body: str
    sub_dot: bool
    subsub_dot: bool


@dataclass(frozen=True)
class ListSettings:
    figures: bool
    tables: bool


@dataclass(frozen=True)
class CoverOverrides:
    show_lecturer: bool = True
    logo_width: int = 2767  # 4.88 cm
    title_split: bool = True


@dataclass(frozen=True)
class Structure:
    id: str
    format_id: str
    path: Path
    data: Mapping[str, Any]
    front_matter: tuple[FrontMatterItem, ...]
    body: tuple[BodyChapter, ...]
    back_matter: tuple[BackMatterItem, ...]
    toc: bool
    numbering: Numbering
    lists: ListSettings
    cover: CoverOverrides = field(default_factory=CoverOverrides)

    @property
    def template_dir(self) -> Path:
        return self.path / "templates"


_STRUCTURE_KEYS = frozenset(
    {"format", "front_matter", "body", "back_matter", "toc", "numbering", "lists", "cover"}
)
_STRUCTURE_LEGACY = {
    "structure": "gunakan direktori structures/<id>/structure.yml",
    "chapters": "gunakan daftar body berisi {id, title}",
}
_FRONT_MATTER_RULES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "cover": frozenset({"generated"}),
        "approval": frozenset({"template"}),
        "statement": frozenset({"template"}),
        "preface": frozenset({"document"}),
        "abstract_id": frozenset({"document"}),
        "abstract_en": frozenset({"document"}),
        "toc": frozenset({"generated"}),
        "list_of_tables": frozenset({"generated"}),
        "list_of_figures": frozenset({"generated"}),
    }
)
_BACK_MATTER_RULES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "bibliography": frozenset({"generated"}),
        "appendices": frozenset({"document"}),
    }
)
_FRONT_ITEM_KEYS = frozenset({"id", "source", "template"})
_BODY_KEYS = frozenset({"id", "title"})
_BACK_KEYS = frozenset({"id", "source"})
_NUMBERING_KEYS = frozenset({"body", "sub_dot", "subsub_dot"})
_LISTS_KEYS = frozenset({"figures", "tables"})
_COVER_KEYS = frozenset({"show_lecturer", "logo_width", "title_split"})
_BODY_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _normalize_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def _parse_front_matter(
    data: Any,
    *,
    path: Path,
    templates: Path,
    toc: bool,
    lists: ListSettings,
) -> tuple[FrontMatterItem, ...]:
    entries = _expect_list(data, path=path, key="front_matter")
    if not entries:
        raise _err(
            "front_matter minimal memuat satu entri",
            code="CFG-REQUIRED",
            path=path,
            key="front_matter",
        )
    result: list[FrontMatterItem] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"front_matter[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _FRONT_ITEM_KEYS, path=path, key=key)
        item_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if item_id not in _FRONT_MATTER_RULES:
            raise _err(
                f"ID front matter '{item_id}' tidak didukung",
                code="CFG-UNKNOWN-FRONT-MATTER",
                path=path,
                key=f"{key}.id",
            )
        if item_id in seen:
            raise _err(
                f"ID front matter '{item_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        seen.add(item_id)
        source = _text(
            _required(item, "source", path=path, key=key),
            path=path,
            key=f"{key}.source",
        )
        if source not in _FRONT_MATTER_RULES[item_id]:
            allowed = ", ".join(sorted(_FRONT_MATTER_RULES[item_id]))
            raise _err(
                f"front matter '{item_id}' tidak mendukung source '{source}'; gunakan {allowed}",
                code="CFG-CONDITIONAL",
                path=path,
                key=f"{key}.source",
            )
        template_value = item.get("template")
        if source == "template":
            template = _text(
                template_value,
                path=path,
                key=f"{key}.template",
            )
            if not template.lower().endswith(".md"):
                raise _err(
                    f"template '{item_id}' harus berekstensi .md",
                    code="CFG-TYPE",
                    path=path,
                    key=f"{key}.template",
                )
            resolved = path_mod.safe_relative_path(
                template,
                base=templates,
                label=f"{key}.template",
                code="CFG-TEMPLATE-MISSING",
                must_exist=True,
                expect_file=True,
            )
            result.append(FrontMatterItem(id=item_id, source=source, template=resolved.name))
        else:
            if template_value is not None:
                raise _err(
                    f"template hanya boleh untuk source 'template' ({item_id})",
                    code="CFG-CONDITIONAL",
                    path=path,
                    key=f"{key}.template",
                )
            result.append(FrontMatterItem(id=item_id, source=source))

    if "cover" not in seen:
        raise _err(
            "front_matter wajib memuat 'cover'",
            code="CFG-REQUIRED",
            path=path,
            key="front_matter",
        )
    if toc and "toc" not in seen:
        raise _err(
            "front_matter wajib memuat 'toc' karena structure.toc bernilai true",
            code="CFG-CONDITIONAL",
            path=path,
            key="front_matter",
        )
    if not toc and "toc" in seen:
        raise _err(
            "front_matter tidak boleh memuat 'toc' karena structure.toc bernilai false",
            code="CFG-CONDITIONAL",
            path=path,
            key="front_matter",
        )
    tables_expected = "list_of_tables" in seen
    figures_expected = "list_of_figures" in seen
    if lists.tables != tables_expected:
        raise _err(
            "front_matter.list_of_tables tidak konsisten dengan lists.tables",
            code="CFG-CONDITIONAL",
            path=path,
            key="lists.tables",
        )
    if lists.figures != figures_expected:
        raise _err(
            "front_matter.list_of_figures tidak konsisten dengan lists.figures",
            code="CFG-CONDITIONAL",
            path=path,
            key="lists.figures",
        )
    return tuple(result)


def _parse_body(data: Any, *, path: Path) -> tuple[BodyChapter, ...]:
    entries = _expect_list(data, path=path, key="body")
    if not entries:
        raise _err(
            "body minimal memuat satu bab",
            code="CFG-REQUIRED",
            path=path,
            key="body",
        )
    result: list[BodyChapter] = []
    ids: set[str] = set()
    titles: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"body[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _BODY_KEYS, path=path, key=key)
        chapter_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if not _BODY_ID_RE.fullmatch(chapter_id):
            raise _err(
                f"ID bab '{chapter_id}' tidak valid; gunakan [a-z][a-z0-9-]*",
                code="CFG-TYPE",
                path=path,
                key=f"{key}.id",
            )
        if chapter_id in ids:
            raise _err(
                f"ID bab '{chapter_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        ids.add(chapter_id)
        title = _text(
            _required(item, "title", path=path, key=key),
            path=path,
            key=f"{key}.title",
        )
        normalized = _normalize_title(title)
        if normalized in titles:
            raise _err(
                f"judul bab '{title}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.title",
            )
        titles.add(normalized)
        result.append(BodyChapter(id=chapter_id, title=title))
    return tuple(result)


def _parse_back_matter(data: Any, *, path: Path) -> tuple[BackMatterItem, ...]:
    if data is None:
        return ()
    entries = _expect_list(data, path=path, key="back_matter")
    result: list[BackMatterItem] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"back_matter[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _BACK_KEYS, path=path, key=key)
        item_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if item_id not in _BACK_MATTER_RULES:
            raise _err(
                f"ID back matter '{item_id}' tidak didukung",
                code="CFG-UNKNOWN-FRONT-MATTER",
                path=path,
                key=f"{key}.id",
            )
        if item_id in seen:
            raise _err(
                f"ID back matter '{item_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        seen.add(item_id)
        source = _text(
            _required(item, "source", path=path, key=key),
            path=path,
            key=f"{key}.source",
        )
        if source not in _BACK_MATTER_RULES[item_id]:
            allowed = ", ".join(sorted(_BACK_MATTER_RULES[item_id]))
            raise _err(
                f"back matter '{item_id}' tidak mendukung source '{source}'; gunakan {allowed}",
                code="CFG-CONDITIONAL",
                path=path,
                key=f"{key}.source",
            )
        result.append(BackMatterItem(id=item_id, source=source))
    return tuple(result)


def _parse_numbering(data: Any, *, path: Path) -> Numbering:
    mapping = _expect_mapping(data, path=path, key="numbering")
    _check_unknown(mapping, _NUMBERING_KEYS, path=path, key="numbering")
    return Numbering(
        body=_enum(
            _required(mapping, "body", path=path, key="numbering"),
            path=path,
            key="numbering.body",
            choices=("BAB_ROMAN", "ARABIC_DOTTED"),
        ),
        sub_dot=_boolean(mapping.get("sub_dot"), path=path, key="numbering.sub_dot", default=True),
        subsub_dot=_boolean(
            mapping.get("subsub_dot"),
            path=path,
            key="numbering.subsub_dot",
            default=True,
        ),
    )


def _parse_lists(data: Any, *, path: Path) -> ListSettings:
    mapping = _expect_mapping(data, path=path, key="lists")
    _check_unknown(mapping, _LISTS_KEYS, path=path, key="lists")
    return ListSettings(
        figures=_boolean(
            _required(mapping, "figures", path=path, key="lists"),
            path=path,
            key="lists.figures",
        ),
        tables=_boolean(
            _required(mapping, "tables", path=path, key="lists"),
            path=path,
            key="lists.tables",
        ),
    )


def _parse_cover(data: Any, *, path: Path) -> CoverOverrides:
    if data is None:
        return CoverOverrides()
    mapping = _expect_mapping(data, path=path, key="cover")
    _check_unknown(mapping, _COVER_KEYS, path=path, key="cover")
    return CoverOverrides(
        show_lecturer=_boolean(
            mapping.get("show_lecturer"),
            path=path,
            key="cover.show_lecturer",
            default=True,
        ),
        logo_width=_dimension(
            mapping.get("logo_width"),
            path=path,
            key="cover.logo_width",
            default="4.88cm",
            positive=True,
        ),
        title_split=_boolean(
            mapping.get("title_split"),
            path=path,
            key="cover.title_split",
            default=True,
        ),
    )


def load_structure(structure_id: str, *, root: Path | None = None) -> Structure:
    """Muat dan validasi ``structures/<structure_id>/structure.yml``."""

    path_mod.validate_id(structure_id, kind="struktur")
    directory = path_mod.structure_dir(structure_id, root=root)
    path = directory / "structure.yml"
    if not path.is_file():
        raise ConfigError(
            f"struktur '{structure_id}': structure.yml tidak ditemukan",
            code="CFG-STRUCTURE-MISSING",
            path=path,
        )
    data = load_yaml_mapping(path, label="structure.yml")
    _check_unknown(
        data,
        _STRUCTURE_KEYS,
        path=path,
        key="structure",
        legacy=_STRUCTURE_LEGACY,
    )
    format_id = _text(
        _required(data, "format", path=path, key="structure"),
        path=path,
        key="format",
    )
    path_mod.validate_id(format_id, kind="format")

    toc = _boolean(
        _required(data, "toc", path=path, key="structure"),
        path=path,
        key="toc",
    )
    numbering = _parse_numbering(
        _required(data, "numbering", path=path, key="structure"),
        path=path,
    )
    lists = _parse_lists(
        _required(data, "lists", path=path, key="structure"),
        path=path,
    )
    templates = directory / "templates"
    if templates.exists() and not templates.is_dir():
        raise _err(
            "'templates' harus berupa direktori",
            code="CFG-ASSET-MISSING",
            path=templates,
            key="templates",
        )
    path_mod.check_case_collisions(templates, label="templates")
    front_matter = _parse_front_matter(
        _required(data, "front_matter", path=path, key="structure"),
        path=path,
        templates=templates,
        toc=toc,
        lists=lists,
    )
    body = _parse_body(
        _required(data, "body", path=path, key="structure"),
        path=path,
    )
    back_matter = _parse_back_matter(data.get("back_matter"), path=path)
    cover = _parse_cover(data.get("cover"), path=path)

    return Structure(
        id=structure_id,
        format_id=format_id,
        path=directory,
        data=MappingProxyType(dict(data)),
        front_matter=front_matter,
        body=body,
        back_matter=back_matter,
        toc=toc,
        numbering=numbering,
        lists=lists,
        cover=cover,
    )


def format_override_warning(document_format: str, structure: Structure) -> str | None:
    if document_format == structure.format_id:
        return None
    return (
        f"document.format '{document_format}' mengalahkan structure.format "
        f"'{structure.format_id}' (CFG-FORMAT-OVERRIDE)"
    )
