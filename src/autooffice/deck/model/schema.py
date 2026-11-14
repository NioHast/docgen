"""Validasi schema authoring deck YAML AutoOffice v1.

Modul ini adalah satu-satunya validasi bentuk ``deck.yaml`` sebelum compiler.
Semua field yang tidak dikenal, field geometri/style, ID duplikat, path tidak
aman, dan kombinasi ``blocks``/``rows`` ditolak dengan error eksplisit.
"""

import math
import re
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal, cast
from urllib.parse import urlsplit

from autooffice.deck.blocks.registry import block_specs
from autooffice.deck.layout.registry import layout_names
from autooffice.errors import AutoOfficeError

from .keys import KeyGrammarError, validate_block_id, validate_slide_id
from .markdown import (
    MarkdownError,
    normalize_preserve_newlines,
    parse_inline,
    validate_plain_text,
)

Language = Literal["id", "en"]
ImageFit = Literal["contain", "cover"]
ChartKind = Literal["bar", "line", "donut"]
Number = int | float

SCHEMA_ID = "autooffice.deck/v1"
DEFAULT_LANGUAGE: Language = "id"
SUPPORTED_THEMES = ("indigo", "hitam")
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
DIAGRAM_SUFFIXES = frozenset({".mmd"})
ROLE_VALUES = ("display", "title", "lead", "body", "caption", "label", "kicker")
IMAGE_FIT_VALUES = ("contain", "cover")
CHART_KINDS = ("bar", "line", "donut")
CHART_ORIENTATIONS = ("vertical", "horizontal")
SPACER_SIZES = ("sm", "md", "lg")
METRIC_STATUSES = ("neutral", "success", "warning", "danger")

GEOMETRY_FIELDS = frozenset(
    {
        "x",
        "y",
        "left",
        "top",
        "right",
        "bottom",
        "width",
        "height",
        "position",
        "absolute",
        "anchor",
        "translate",
        "rotate",
        "z",
        "z_index",
    }
)
STYLE_FIELDS = frozenset(
    {
        "align",
        "background",
        "bold",
        "border",
        "border_color",
        "color",
        "colour",
        "fill",
        "font",
        "font_family",
        "font_size",
        "font_weight",
        "gap",
        "italic",
        "letter_spacing",
        "line_height",
        "margin",
        "opacity",
        "padding",
        "radius",
        "shadow",
        "spacing",
        "stroke",
        "style",
        "text_align",
        "theme_color",
        "underline",
        "valign",
        "vertical_align",
    }
)

_BCP47_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{1,8})*$")
_URL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")

_META_FIELDS = (
    "title",
    "subtitle",
    "author",
    "organization",
    "date",
    "language",
    "description",
)
_THEME_FIELDS = ("name",)
_DEFAULTS_FIELDS = ("layout", "image_fit", "code_language")
_SLIDE_FIELDS = ("id", "layout", "notes", "source", "blocks", "rows")
_SOURCE_FIELDS = ("text", "url")
_ROW_FIELDS = ("blocks",)
_SERIES_FIELDS = ("name", "values")
_LAYOUT_NAMES = frozenset(layout_names())
_SPECS = {spec.block_type: spec for spec in block_specs()}


class DeckSchemaError(AutoOfficeError):
    """Satu nilai deck melanggar kontrak schema."""

    def __init__(
        self,
        message: str,
        *,
        path: tuple[str | int, ...] = (),
        slide_id: str | None = None,
        block_id: str | None = None,
        key: str | None = None,
    ) -> None:
        self.message = message
        self.path = path
        self.slide_id = slide_id
        self.block_id = block_id
        self.key = key
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        location = format_yaml_path(self.path)
        context: list[str] = []
        if self.slide_id is not None:
            context.append(f"slide={self.slide_id}")
        if self.block_id is not None:
            context.append(f"block={self.block_id}")
        if self.key is not None:
            context.append(f"key={self.key}")
        suffix = f" ({', '.join(context)})" if context else ""
        return f"{location}: {self.message}{suffix}"


@dataclass(frozen=True, slots=True)
class DeckMeta:
    """Metadata deck yang sudah divalidasi dan dinormalisasi."""

    title: str
    author: str
    subtitle: str | None = None
    organization: str | None = None
    date: str | None = None
    language: Language = DEFAULT_LANGUAGE
    description: str | None = None

    def as_mapping(self) -> dict[str, str]:
        """Kembalikan mapping string untuk ``DeckIR.meta``."""
        data = {"title": self.title, "author": self.author, "language": self.language}
        if self.subtitle is not None:
            data["subtitle"] = self.subtitle
        if self.organization is not None:
            data["organization"] = self.organization
        if self.date is not None:
            data["date"] = self.date
        if self.description is not None:
            data["description"] = self.description
        return data


@dataclass(frozen=True, slots=True)
class DeckDefaults:
    """Default authoring yang tidak mendefinisikan nilai visual."""

    layout: str = "content"
    image_fit: ImageFit = "contain"
    code_language: str = "text"


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """Sumber slide yang sudah divalidasi."""

    text: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class ChartSeries:
    """Satu seri chart beserta nilai numeriknya."""

    name: str
    values: tuple[Number, ...]


@dataclass(frozen=True, slots=True)
class BlockDefinition:
    """Satu block authoring yang sudah divalidasi."""

    block_id: str
    block_type: str
    span: int | None
    role: str | None
    fields: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True, slots=True)
class SlideDefinition:
    """Satu slide authoring yang sudah divalidasi."""

    slide_id: str
    layout: str
    notes: str | None
    source: SourceDefinition | None
    blocks: tuple[BlockDefinition, ...]
    rows: tuple[tuple[BlockDefinition, ...], ...]


@dataclass(frozen=True, slots=True)
class DeckDefinition:
    """Deck authoring lengkap yang siap dikompilasi menjadi Deck IR."""

    schema: str
    meta: DeckMeta
    theme_name: str
    defaults: DeckDefaults
    slides: tuple[SlideDefinition, ...]


def validate_deck(data: object, *, base_dir: str | Path | None = None) -> DeckDefinition:
    """Validasi objek hasil load YAML menjadi ``DeckDefinition``."""
    root = _require_mapping(data, path=(), context="root deck")
    _check_fields(
        root, ("schema", "meta", "theme", "defaults", "slides"), path=(), context="root deck"
    )

    schema = _require_str(
        _require_field(root, "schema", path=(), context="root deck"),
        field="schema",
        path=("schema",),
    )
    if schema != SCHEMA_ID:
        raise _schema_error(f"Schema harus '{SCHEMA_ID}', bukan '{schema}'.", path=("schema",))

    meta = _validate_meta(
        _require_field(root, "meta", path=(), context="root deck"), path=("meta",)
    )
    theme_name = _validate_theme(root["theme"], path=("theme",)) if "theme" in root else "indigo"
    defaults = (
        _validate_defaults(root["defaults"], path=("defaults",))
        if "defaults" in root
        else DeckDefaults()
    )
    raw_slides = _require_list(
        _require_field(root, "slides", path=(), context="root deck"),
        field="slides",
        path=("slides",),
    )
    if not raw_slides:
        raise _schema_error("Deck harus memiliki minimal satu slide.", path=("slides",))

    base = Path(base_dir) if base_dir is not None else None
    seen_slide_ids: dict[str, int] = {}
    slides = tuple(
        _validate_slide(
            raw_slide,
            index=index,
            defaults=defaults,
            base_dir=base,
            seen_slide_ids=seen_slide_ids,
        )
        for index, raw_slide in enumerate(raw_slides)
    )
    return DeckDefinition(
        schema=schema,
        meta=meta,
        theme_name=theme_name,
        defaults=defaults,
        slides=slides,
    )


def normalize_language(value: object, *, path: tuple[str | int, ...] = ()) -> Language:
    """Normalisasi BCP 47 sederhana ke bahasa utama ``id`` atau ``en``."""
    if not isinstance(value, str):
        raise _schema_error("meta.language harus string.", path=path)
    normalized = value.strip().lower()
    if not normalized or _BCP47_PATTERN.fullmatch(normalized) is None:
        raise _schema_error(
            f"meta.language '{value}' bukan BCP 47 sederhana; hanya id dan en yang didukung.",
            path=path,
        )
    primary = normalized.split("-", 1)[0]
    if primary == "id":
        return "id"
    if primary == "en":
        return "en"
    raise _schema_error(
        f"meta.language '{value}' tidak didukung; hanya id dan en yang didukung.",
        path=path,
    )


def format_yaml_path(path: tuple[str | int, ...]) -> str:
    """Format path YAML deterministik untuk pesan error."""
    parts: list[str] = []
    for segment in path:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        elif parts:
            parts.append(f".{segment}")
        else:
            parts.append(segment)
    return "".join(parts) or "deck"


def _validate_meta(value: object, *, path: tuple[str | int, ...]) -> DeckMeta:
    mapping = _require_mapping(value, path=path, context="meta")
    _check_fields(mapping, _META_FIELDS, path=path, context="meta")
    title = _plain_value(
        _require_field(mapping, "title", path=path, context="meta"),
        field="meta.title",
        path=(*path, "title"),
    )
    author = _plain_value(
        _require_field(mapping, "author", path=path, context="meta"),
        field="meta.author",
        path=(*path, "author"),
    )
    subtitle = _optional_plain(mapping, "subtitle", path=path, field="meta.subtitle")
    organization = _optional_plain(mapping, "organization", path=path, field="meta.organization")
    date = _optional_plain(mapping, "date", path=path, field="meta.date")
    description = _optional_plain(
        mapping,
        "description",
        path=path,
        field="meta.description",
        multiline=True,
    )
    language: Language = DEFAULT_LANGUAGE
    if "language" in mapping:
        language = normalize_language(mapping["language"], path=(*path, "language"))
    return DeckMeta(
        title=title,
        author=author,
        subtitle=subtitle,
        organization=organization,
        date=date,
        language=language,
        description=description,
    )


def _validate_theme(value: object, *, path: tuple[str | int, ...]) -> str:
    mapping = _require_mapping(value, path=path, context="theme")
    _check_fields(mapping, _THEME_FIELDS, path=path, context="theme")
    name = _require_str(
        _require_field(mapping, "name", path=path, context="theme"),
        field="theme.name",
        path=(*path, "name"),
    )
    if name not in SUPPORTED_THEMES:
        raise _schema_error(
            f"Theme '{name}' tidak dikenal; hanya indigo dan hitam.",
            path=(*path, "name"),
        )
    return name


def _validate_defaults(value: object, *, path: tuple[str | int, ...]) -> DeckDefaults:
    mapping = _require_mapping(value, path=path, context="defaults")
    _check_fields(mapping, _DEFAULTS_FIELDS, path=path, context="defaults")
    layout = "content"
    if "layout" in mapping:
        layout = _require_str(mapping["layout"], field="defaults.layout", path=(*path, "layout"))
        if layout not in _LAYOUT_NAMES:
            raise _schema_error(
                f"Layout default '{layout}' tidak dikenal.",
                path=(*path, "layout"),
            )
    image_fit: ImageFit = "contain"
    if "image_fit" in mapping:
        image_fit = cast(
            "ImageFit",
            _choice(
                mapping["image_fit"],
                field="defaults.image_fit",
                path=(*path, "image_fit"),
                choices=IMAGE_FIT_VALUES,
            ),
        )
    code_language = "text"
    if "code_language" in mapping:
        code_language = _plain_value(
            mapping["code_language"],
            field="defaults.code_language",
            path=(*path, "code_language"),
        )
    return DeckDefaults(layout=layout, image_fit=image_fit, code_language=code_language)


def _validate_slide(
    value: object,
    *,
    index: int,
    defaults: DeckDefaults,
    base_dir: Path | None,
    seen_slide_ids: dict[str, int],
) -> SlideDefinition:
    path = ("slides", index)
    mapping = _require_mapping(value, path=path, context="slide")
    _check_fields(mapping, _SLIDE_FIELDS, path=path, context="slide")

    slide_id_value = _require_field(mapping, "id", path=path, context="slide")
    slide_id = _validate_slide_id_value(slide_id_value, path=(*path, "id"))
    previous = seen_slide_ids.get(slide_id)
    if previous is not None:
        raise _schema_error(
            f"Slide ID '{slide_id}' duplikat pada slide index {previous} dan {index}.",
            path=(*path, "id"),
            slide_id=slide_id,
        )
    seen_slide_ids[slide_id] = index

    layout = defaults.layout
    if "layout" in mapping:
        layout = _require_str(
            mapping["layout"],
            field="layout",
            path=(*path, "layout"),
            slide_id=slide_id,
        )
        if layout not in _LAYOUT_NAMES:
            raise _schema_error(
                f"Layout '{layout}' tidak dikenal.",
                path=(*path, "layout"),
                slide_id=slide_id,
            )

    notes: str | None = None
    if "notes" in mapping:
        notes = _preserve_value(
            mapping["notes"],
            field="notes",
            path=(*path, "notes"),
            slide_id=slide_id,
        )

    source: SourceDefinition | None = None
    if "source" in mapping:
        source = _validate_source(
            mapping["source"],
            path=(*path, "source"),
            slide_id=slide_id,
        )

    has_blocks = "blocks" in mapping
    has_rows = "rows" in mapping
    if has_blocks and has_rows:
        raise _schema_error(
            "Slide tidak boleh memiliki blocks dan rows sekaligus.",
            path=path,
            slide_id=slide_id,
        )

    seen_block_ids: dict[str, str] = {}
    blocks: tuple[BlockDefinition, ...] = ()
    rows: tuple[tuple[BlockDefinition, ...], ...] = ()
    if layout == "custom":
        if has_blocks:
            raise _schema_error(
                "Layout custom wajib memakai rows, bukan blocks.",
                path=(*path, "blocks"),
                slide_id=slide_id,
            )
        if not has_rows:
            raise _schema_error(
                "Layout custom wajib memiliki rows.",
                path=path,
                slide_id=slide_id,
            )
        rows = _validate_rows(
            mapping["rows"],
            path=(*path, "rows"),
            slide_id=slide_id,
            base_dir=base_dir,
            defaults=defaults,
            seen_block_ids=seen_block_ids,
        )
    else:
        if has_rows:
            raise _schema_error(
                "Layout preset tidak boleh memiliki rows.",
                path=(*path, "rows"),
                slide_id=slide_id,
            )
        if not has_blocks:
            raise _schema_error(
                "Layout preset wajib memiliki blocks.",
                path=path,
                slide_id=slide_id,
            )
        blocks = _validate_blocks(
            mapping["blocks"],
            path=(*path, "blocks"),
            slide_id=slide_id,
            layout=layout,
            base_dir=base_dir,
            defaults=defaults,
            seen_block_ids=seen_block_ids,
        )

    return SlideDefinition(
        slide_id=slide_id,
        layout=layout,
        notes=notes,
        source=source,
        blocks=blocks,
        rows=rows,
    )


def _validate_blocks(
    value: object,
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    layout: str,
    base_dir: Path | None,
    defaults: DeckDefaults,
    seen_block_ids: dict[str, str],
) -> tuple[BlockDefinition, ...]:
    raw_blocks = _require_list(value, field="blocks", path=path, slide_id=slide_id)
    return tuple(
        _validate_block(
            raw_block,
            path=(*path, index),
            slide_id=slide_id,
            layout=layout,
            base_dir=base_dir,
            defaults=defaults,
            seen_block_ids=seen_block_ids,
        )
        for index, raw_block in enumerate(raw_blocks)
    )


def _validate_rows(
    value: object,
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    base_dir: Path | None,
    defaults: DeckDefaults,
    seen_block_ids: dict[str, str],
) -> tuple[tuple[BlockDefinition, ...], ...]:
    raw_rows = _require_list(value, field="rows", path=path, slide_id=slide_id)
    if not raw_rows:
        raise _schema_error(
            "Layout custom wajib memiliki minimal satu row.",
            path=path,
            slide_id=slide_id,
        )
    rows: list[tuple[BlockDefinition, ...]] = []
    for row_index, raw_row in enumerate(raw_rows):
        row_path = (*path, row_index)
        row_mapping = _require_mapping(raw_row, path=row_path, context="row")
        _check_fields(row_mapping, _ROW_FIELDS, path=row_path, context="row")
        raw_blocks = _require_list(
            _require_field(row_mapping, "blocks", path=row_path, context="row"),
            field="row.blocks",
            path=(*row_path, "blocks"),
            slide_id=slide_id,
        )
        if not raw_blocks:
            raise _schema_error(
                "Setiap row wajib memiliki minimal satu block.",
                path=(*row_path, "blocks"),
                slide_id=slide_id,
            )
        blocks = tuple(
            _validate_block(
                raw_block,
                path=(*row_path, "blocks", block_index),
                slide_id=slide_id,
                layout="custom",
                base_dir=base_dir,
                defaults=defaults,
                seen_block_ids=seen_block_ids,
            )
            for block_index, raw_block in enumerate(raw_blocks)
        )
        spans = [block.span for block in blocks]
        if any(span is None for span in spans):
            raise _schema_error(
                "Setiap block pada layout custom wajib memiliki span.",
                path=(*row_path, "blocks"),
                slide_id=slide_id,
            )
        total_span = sum(span for span in spans if span is not None)
        if total_span > 12:
            raise _schema_error(
                f"Jumlah span pada row {row_index} adalah {total_span}; maksimal 12.",
                path=row_path,
                slide_id=slide_id,
            )
        rows.append(blocks)
    return tuple(rows)


def _validate_block(
    value: object,
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    layout: str,
    base_dir: Path | None,
    defaults: DeckDefaults,
    seen_block_ids: dict[str, str],
) -> BlockDefinition:
    mapping = _require_mapping(value, path=path, context="block")
    block_id_value = _require_field(mapping, "id", path=path, context="block")
    block_id = _validate_block_id_value(block_id_value, path=(*path, "id"))
    if block_id == "source":
        raise _schema_error(
            "Block ID 'source' bertabrakan dengan key slide 'source.text' "
            f"('{slide_id}.source.text'); gunakan ID block lain.",
            path=(*path, "id"),
            slide_id=slide_id,
            block_id=block_id,
        )
    previous = seen_block_ids.get(block_id)
    if previous is not None:
        raise _schema_error(
            f"Block ID '{block_id}' duplikat pada slide '{slide_id}'; "
            f"sudah dipakai di {previous} dan {format_yaml_path(path)}.",
            path=(*path, "id"),
            slide_id=slide_id,
            block_id=block_id,
        )
    seen_block_ids[block_id] = format_yaml_path(path)

    block_type = _require_str(
        _require_field(mapping, "type", path=path, context="block"),
        field="type",
        path=(*path, "type"),
        slide_id=slide_id,
        block_id=block_id,
    )
    spec = _SPECS.get(block_type)
    if spec is None:
        raise _schema_error(
            f"Block type '{block_type}' tidak dikenal.",
            path=(*path, "type"),
            slide_id=slide_id,
            block_id=block_id,
        )

    allowed = ("id", "type", "span", *spec.required, *spec.optional)
    _check_fields(
        mapping,
        allowed,
        path=path,
        context="block",
        slide_id=slide_id,
        block_id=block_id,
    )

    if not spec.allowed_in_preset and layout != "custom":
        raise _schema_error(
            f"Block type '{block_type}' hanya boleh dipakai pada layout custom.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )

    span: int | None = None
    if layout == "custom":
        span = _int_value(
            _require_field(mapping, "span", path=path, context="block"),
            field="span",
            path=(*path, "span"),
            slide_id=slide_id,
            block_id=block_id,
        )
        if not 1 <= span <= 12:
            raise _schema_error(
                f"Span block '{block_id}' harus 1 sampai 12, bukan {span}.",
                path=(*path, "span"),
                slide_id=slide_id,
                block_id=block_id,
            )
    elif "span" in mapping:
        raise _schema_error(
            "Span hanya boleh ditulis pada layout custom.",
            path=(*path, "span"),
            slide_id=slide_id,
            block_id=block_id,
        )

    for required_field in spec.required:
        if required_field not in mapping:
            raise _schema_error(
                f"Block '{block_id}' tipe '{block_type}' wajib memiliki '{required_field}'.",
                path=path,
                slide_id=slide_id,
                block_id=block_id,
            )

    role: str | None = None
    if "role" in mapping:
        role = _choice(
            mapping["role"],
            field="role",
            path=(*path, "role"),
            choices=ROLE_VALUES,
            slide_id=slide_id,
            block_id=block_id,
        )
        if block_type != "text":
            raise _schema_error(
                "Field role hanya boleh dipakai pada block text.",
                path=(*path, "role"),
                slide_id=slide_id,
                block_id=block_id,
            )
    elif block_type == "text" and layout == "custom":
        role = "body"

    fields = _validate_block_fields(
        mapping,
        block_type=block_type,
        path=path,
        slide_id=slide_id,
        block_id=block_id,
        layout=layout,
        base_dir=base_dir,
        defaults=defaults,
    )
    return BlockDefinition(
        block_id=block_id,
        block_type=block_type,
        span=span,
        role=role,
        fields=fields,
    )


def _validate_block_fields(
    mapping: Mapping[str, object],
    *,
    block_type: str,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    layout: str,
    base_dir: Path | None,
    defaults: DeckDefaults,
) -> Mapping[str, object]:
    if block_type == "text":
        return _text_fields(mapping, path=path, slide_id=slide_id, block_id=block_id)
    if block_type == "bullets":
        return _bullets_fields(mapping, path=path, slide_id=slide_id, block_id=block_id)
    if block_type == "image":
        return _image_fields(
            mapping,
            path=path,
            slide_id=slide_id,
            block_id=block_id,
            base_dir=base_dir,
            defaults=defaults,
        )
    if block_type == "table":
        return _table_fields(
            mapping,
            path=path,
            slide_id=slide_id,
            block_id=block_id,
            layout=layout,
        )
    if block_type == "chart":
        return _chart_fields(mapping, path=path, slide_id=slide_id, block_id=block_id)
    if block_type == "code":
        return _code_fields(
            mapping,
            path=path,
            slide_id=slide_id,
            block_id=block_id,
            defaults=defaults,
        )
    if block_type == "quote":
        return _quote_fields(mapping, path=path, slide_id=slide_id, block_id=block_id)
    if block_type == "diagram":
        return _diagram_fields(
            mapping,
            path=path,
            slide_id=slide_id,
            block_id=block_id,
            base_dir=base_dir,
        )
    if block_type == "divider":
        return {}
    if block_type == "spacer":
        return _spacer_fields(mapping, path=path, slide_id=slide_id, block_id=block_id)
    return _metric_fields(mapping, path=path, slide_id=slide_id, block_id=block_id)


def _text_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "text": _inline_value(
            _require_field(mapping, "text", path=path, context="block text"),
            field="text",
            path=(*path, "text"),
            slide_id=slide_id,
            block_id=block_id,
            multiline=True,
        )
    }
    if "heading" in mapping:
        fields["heading"] = _inline_value(
            mapping["heading"],
            field="heading",
            path=(*path, "heading"),
            slide_id=slide_id,
            block_id=block_id,
        )
    return fields


def _bullets_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> dict[str, object]:
    raw_items = _require_list(
        _require_field(mapping, "items", path=path, context="block bullets"),
        field="items",
        path=(*path, "items"),
        slide_id=slide_id,
        block_id=block_id,
    )
    if not raw_items:
        raise _schema_error(
            "Block bullets wajib memiliki minimal satu item.",
            path=(*path, "items"),
            slide_id=slide_id,
            block_id=block_id,
        )
    items = tuple(
        _inline_value(
            item,
            field=f"items[{index}]",
            path=(*path, "items", index),
            slide_id=slide_id,
            block_id=block_id,
        )
        for index, item in enumerate(raw_items)
    )
    ordered = False
    if "ordered" in mapping:
        ordered = _bool_value(
            mapping["ordered"],
            field="ordered",
            path=(*path, "ordered"),
            slide_id=slide_id,
            block_id=block_id,
        )
    return {"items": items, "ordered": ordered}


def _image_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    base_dir: Path | None,
    defaults: DeckDefaults,
) -> dict[str, object]:
    asset_path = _asset_path(
        _require_field(mapping, "path", path=path, context="block image"),
        field="path",
        path=(*path, "path"),
        slide_id=slide_id,
        block_id=block_id,
        base_dir=base_dir,
        suffixes=IMAGE_SUFFIXES,
    )
    alt = _plain_value(
        _require_field(mapping, "alt", path=path, context="block image"),
        field="alt",
        path=(*path, "alt"),
        slide_id=slide_id,
        block_id=block_id,
    )
    fit: ImageFit = defaults.image_fit
    if "fit" in mapping:
        fit = cast(
            "ImageFit",
            _choice(
                mapping["fit"],
                field="fit",
                path=(*path, "fit"),
                choices=IMAGE_FIT_VALUES,
                slide_id=slide_id,
                block_id=block_id,
            ),
        )
    fields: dict[str, object] = {"path": asset_path, "alt": alt, "fit": fit}
    if "caption" in mapping:
        fields["caption"] = _inline_value(
            mapping["caption"],
            field="caption",
            path=(*path, "caption"),
            slide_id=slide_id,
            block_id=block_id,
        )
    return fields


def _table_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    layout: str,
) -> dict[str, object]:
    raw_columns = _require_list(
        _require_field(mapping, "columns", path=path, context="block table"),
        field="columns",
        path=(*path, "columns"),
        slide_id=slide_id,
        block_id=block_id,
    )
    if not raw_columns:
        raise _schema_error(
            "Block table wajib memiliki minimal satu kolom.",
            path=(*path, "columns"),
            slide_id=slide_id,
            block_id=block_id,
        )
    columns = tuple(
        _inline_value(
            column,
            field=f"columns[{index}]",
            path=(*path, "columns", index),
            slide_id=slide_id,
            block_id=block_id,
        )
        for index, column in enumerate(raw_columns)
    )
    raw_rows = _require_list(
        _require_field(mapping, "rows", path=path, context="block table"),
        field="rows",
        path=(*path, "rows"),
        slide_id=slide_id,
        block_id=block_id,
    )
    if not raw_rows:
        raise _schema_error(
            "Block table wajib memiliki minimal satu baris.",
            path=(*path, "rows"),
            slide_id=slide_id,
            block_id=block_id,
        )
    rows: list[tuple[str, ...]] = []
    for row_index, raw_row in enumerate(raw_rows):
        cells = _require_list(
            raw_row,
            field=f"rows[{row_index}]",
            path=(*path, "rows", row_index),
            slide_id=slide_id,
            block_id=block_id,
        )
        if len(cells) != len(columns):
            raise _schema_error(
                f"Baris tabel {row_index + 1} memiliki {len(cells)} sel; "
                f"jumlah kolom adalah {len(columns)}.",
                path=(*path, "rows", row_index),
                slide_id=slide_id,
                block_id=block_id,
            )
        rows.append(
            tuple(
                _inline_value(
                    cell,
                    field=f"rows[{row_index}][{column_index}]",
                    path=(*path, "rows", row_index, column_index),
                    slide_id=slide_id,
                    block_id=block_id,
                )
                for column_index, cell in enumerate(cells)
            )
        )
    fields: dict[str, object] = {"columns": columns, "rows": tuple(rows)}
    if "caption" in mapping:
        fields["caption"] = _inline_value(
            mapping["caption"],
            field="caption",
            path=(*path, "caption"),
            slide_id=slide_id,
            block_id=block_id,
        )
    if "emphasis_column" in mapping:
        emphasis = _int_value(
            mapping["emphasis_column"],
            field="emphasis_column",
            path=(*path, "emphasis_column"),
            slide_id=slide_id,
            block_id=block_id,
        )
        if layout != "comparison":
            raise _schema_error(
                "emphasis_column hanya valid pada layout comparison.",
                path=(*path, "emphasis_column"),
                slide_id=slide_id,
                block_id=block_id,
            )
        if not 1 <= emphasis <= len(columns):
            raise _schema_error(
                f"emphasis_column {emphasis} di luar jumlah kolom {len(columns)}.",
                path=(*path, "emphasis_column"),
                slide_id=slide_id,
                block_id=block_id,
            )
        fields["emphasis_column"] = emphasis
    return fields


def _chart_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> dict[str, object]:
    kind = _choice(
        _require_field(mapping, "kind", path=path, context="block chart"),
        field="kind",
        path=(*path, "kind"),
        choices=CHART_KINDS,
        slide_id=slide_id,
        block_id=block_id,
    )
    title = _plain_value(
        _require_field(mapping, "title", path=path, context="block chart"),
        field="title",
        path=(*path, "title"),
        slide_id=slide_id,
        block_id=block_id,
    )
    alt = _plain_value(
        _require_field(mapping, "alt", path=path, context="block chart"),
        field="alt",
        path=(*path, "alt"),
        slide_id=slide_id,
        block_id=block_id,
    )
    raw_categories = _require_list(
        _require_field(mapping, "categories", path=path, context="block chart"),
        field="categories",
        path=(*path, "categories"),
        slide_id=slide_id,
        block_id=block_id,
    )
    if len(raw_categories) < 2:
        raise _schema_error(
            "Chart wajib memiliki minimal dua kategori.",
            path=(*path, "categories"),
            slide_id=slide_id,
            block_id=block_id,
        )
    categories = tuple(
        _plain_value(
            category,
            field=f"categories[{index}]",
            path=(*path, "categories", index),
            slide_id=slide_id,
            block_id=block_id,
        )
        for index, category in enumerate(raw_categories)
    )
    series = _chart_series(
        _require_field(mapping, "series", path=path, context="block chart"),
        path=(*path, "series"),
        slide_id=slide_id,
        block_id=block_id,
        categories=categories,
    )
    if kind == "donut":
        if len(series) != 1:
            raise _schema_error(
                f"Chart donut wajib memiliki tepat satu seri, bukan {len(series)}.",
                path=(*path, "series"),
                slide_id=slide_id,
                block_id=block_id,
            )
        if not 2 <= len(categories) <= 4:
            raise _schema_error(
                f"Chart donut wajib memiliki 2 sampai 4 kategori berwarna, "
                f"bukan {len(categories)}.",
                path=(*path, "categories"),
                slide_id=slide_id,
                block_id=block_id,
            )
    elif not 1 <= len(series) <= 4:
        raise _schema_error(
            f"Chart {kind} wajib memiliki 1 sampai 4 seri, bukan {len(series)}.",
            path=(*path, "series"),
            slide_id=slide_id,
            block_id=block_id,
        )

    orientation = "vertical" if kind == "bar" else None
    if "orientation" in mapping:
        if kind != "bar":
            raise _schema_error(
                "orientation hanya valid untuk chart bar.",
                path=(*path, "orientation"),
                slide_id=slide_id,
                block_id=block_id,
            )
        orientation = _choice(
            mapping["orientation"],
            field="orientation",
            path=(*path, "orientation"),
            choices=CHART_ORIENTATIONS,
            slide_id=slide_id,
            block_id=block_id,
        )
    fields: dict[str, object] = {
        "kind": kind,
        "title": title,
        "alt": alt,
        "categories": categories,
        "series": series,
    }
    if orientation is not None:
        fields["orientation"] = orientation
    if "unit" in mapping:
        fields["unit"] = _plain_value(
            mapping["unit"],
            field="unit",
            path=(*path, "unit"),
            slide_id=slide_id,
            block_id=block_id,
        )
    if "caption" in mapping:
        fields["caption"] = _inline_value(
            mapping["caption"],
            field="caption",
            path=(*path, "caption"),
            slide_id=slide_id,
            block_id=block_id,
        )
    return fields


def _chart_series(
    value: object,
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    categories: tuple[str, ...],
) -> tuple[ChartSeries, ...]:
    raw_series = _require_list(
        value,
        field="series",
        path=path,
        slide_id=slide_id,
        block_id=block_id,
    )
    if not raw_series:
        raise _schema_error(
            "Chart wajib memiliki minimal satu seri.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    result: list[ChartSeries] = []
    for series_index, raw_item in enumerate(raw_series):
        item_path = (*path, series_index)
        item = _require_mapping(raw_item, path=item_path, context="chart series")
        _check_fields(
            item,
            _SERIES_FIELDS,
            path=item_path,
            context="chart series",
            slide_id=slide_id,
            block_id=block_id,
        )
        name = _plain_value(
            _require_field(item, "name", path=item_path, context="chart series"),
            field=f"series[{series_index}].name",
            path=(*item_path, "name"),
            slide_id=slide_id,
            block_id=block_id,
        )
        raw_values = _require_list(
            _require_field(item, "values", path=item_path, context="chart series"),
            field=f"series[{series_index}].values",
            path=(*item_path, "values"),
            slide_id=slide_id,
            block_id=block_id,
        )
        if len(raw_values) != len(categories):
            raise _schema_error(
                f"Seri '{name}' memiliki {len(raw_values)} nilai; "
                f"jumlah kategori adalah {len(categories)}.",
                path=(*item_path, "values"),
                slide_id=slide_id,
                block_id=block_id,
            )
        values = tuple(
            _number_value(
                raw_value,
                field=f"series[{series_index}].values[{value_index}]",
                path=(*item_path, "values", value_index),
                slide_id=slide_id,
                block_id=block_id,
            )
            for value_index, raw_value in enumerate(raw_values)
        )
        result.append(ChartSeries(name=name, values=values))
    return tuple(result)


def _code_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    defaults: DeckDefaults,
) -> dict[str, object]:
    code = _preserve_value(
        _require_field(mapping, "code", path=path, context="block code"),
        field="code",
        path=(*path, "code"),
        slide_id=slide_id,
        block_id=block_id,
    )
    language = defaults.code_language
    if "language" in mapping:
        language = _plain_value(
            mapping["language"],
            field="language",
            path=(*path, "language"),
            slide_id=slide_id,
            block_id=block_id,
        )
    line_numbers = True
    if "line_numbers" in mapping:
        line_numbers = _bool_value(
            mapping["line_numbers"],
            field="line_numbers",
            path=(*path, "line_numbers"),
            slide_id=slide_id,
            block_id=block_id,
        )
    fields: dict[str, object] = {
        "code": code,
        "language": language,
        "line_numbers": line_numbers,
    }
    if "filename" in mapping:
        fields["filename"] = _plain_value(
            mapping["filename"],
            field="filename",
            path=(*path, "filename"),
            slide_id=slide_id,
            block_id=block_id,
        )
    return fields


def _quote_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "text": _inline_value(
            _require_field(mapping, "text", path=path, context="block quote"),
            field="text",
            path=(*path, "text"),
            slide_id=slide_id,
            block_id=block_id,
            multiline=True,
        )
    }
    if "attribution" in mapping:
        fields["attribution"] = _inline_value(
            mapping["attribution"],
            field="attribution",
            path=(*path, "attribution"),
            slide_id=slide_id,
            block_id=block_id,
        )
    return fields


def _diagram_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    base_dir: Path | None,
) -> dict[str, object]:
    source = _asset_path(
        _require_field(mapping, "source", path=path, context="block diagram"),
        field="source",
        path=(*path, "source"),
        slide_id=slide_id,
        block_id=block_id,
        base_dir=base_dir,
        suffixes=DIAGRAM_SUFFIXES,
    )
    alt = _plain_value(
        _require_field(mapping, "alt", path=path, context="block diagram"),
        field="alt",
        path=(*path, "alt"),
        slide_id=slide_id,
        block_id=block_id,
    )
    fields: dict[str, object] = {"source": source, "alt": alt}
    if "caption" in mapping:
        fields["caption"] = _inline_value(
            mapping["caption"],
            field="caption",
            path=(*path, "caption"),
            slide_id=slide_id,
            block_id=block_id,
        )
    return fields


def _spacer_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> dict[str, object]:
    size = "md"
    if "size" in mapping:
        size = _choice(
            mapping["size"],
            field="size",
            path=(*path, "size"),
            choices=SPACER_SIZES,
            slide_id=slide_id,
            block_id=block_id,
        )
    return {"size": size}


def _metric_fields(
    mapping: Mapping[str, object],
    *,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "label": _inline_value(
            _require_field(mapping, "label", path=path, context="block metric"),
            field="label",
            path=(*path, "label"),
            slide_id=slide_id,
            block_id=block_id,
        ),
        "value": _inline_value(
            _require_field(mapping, "value", path=path, context="block metric"),
            field="value",
            path=(*path, "value"),
            slide_id=slide_id,
            block_id=block_id,
        ),
        "status": "neutral",
    }
    if "caption" in mapping:
        fields["caption"] = _inline_value(
            mapping["caption"],
            field="caption",
            path=(*path, "caption"),
            slide_id=slide_id,
            block_id=block_id,
        )
    if "status" in mapping:
        fields["status"] = _choice(
            mapping["status"],
            field="status",
            path=(*path, "status"),
            choices=METRIC_STATUSES,
            slide_id=slide_id,
            block_id=block_id,
        )
    return fields


def _validate_source(
    value: object,
    *,
    path: tuple[str | int, ...],
    slide_id: str,
) -> SourceDefinition:
    mapping = _require_mapping(value, path=path, context="source")
    _check_fields(mapping, _SOURCE_FIELDS, path=path, context="source", slide_id=slide_id)
    text = _plain_value(
        _require_field(mapping, "text", path=path, context="source"),
        field="source.text",
        path=(*path, "text"),
        slide_id=slide_id,
        multiline=True,
    )
    url: str | None = None
    if "url" in mapping:
        url = _source_url(mapping["url"], path=(*path, "url"), slide_id=slide_id)
    return SourceDefinition(text=text, url=url)


def _source_url(value: object, *, path: tuple[str | int, ...], slide_id: str) -> str:
    url = _require_str(value, field="source.url", path=path, slide_id=slide_id)
    if any(character.isspace() or ord(character) < 32 for character in url):
        raise _schema_error(
            "source.url tidak boleh memuat spasi atau karakter kontrol.",
            path=path,
            slide_id=slide_id,
        )
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as error:
        raise _schema_error(
            f"source.url '{url}' tidak valid: {error}.",
            path=path,
            slide_id=slide_id,
        ) from error
    if parsed.scheme not in {"http", "https"} or hostname is None:
        raise _schema_error(
            "source.url hanya menerima URL http:// atau https:// dengan host.",
            path=path,
            slide_id=slide_id,
        )
    return url


def _validated_asset_path(
    value: str,
    *,
    suffixes: frozenset[str],
    field: str,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    base_dir: Path | None,
) -> str:
    if _URL_PATTERN.match(value):
        raise _schema_error(
            f"{field} tidak boleh memakai URL remote.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    if any(ord(character) < 32 for character in value):
        raise _schema_error(
            f"{field} tidak boleh memuat karakter kontrol.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    if "\\" in value:
        raise _schema_error(
            f"{field} harus memakai '/' dan tidak boleh memuat backslash.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    if value.startswith("/") or _DRIVE_PATTERN.match(value) or ":" in value:
        raise _schema_error(
            f"{field} harus path relatif terhadap direktori YAML.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise _schema_error(
            f"{field} tidak boleh memuat segmen kosong, '.', atau '..'.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    suffix = PurePosixPath(value).suffix.lower()
    if suffix not in suffixes:
        allowed = ", ".join(sorted(suffixes))
        raise _schema_error(
            f"{field} harus berekstensi {allowed}, bukan '{suffix or 'tanpa ekstensi'}'.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    if base_dir is not None:
        try:
            root = base_dir.resolve()
            candidate = root / value
            resolved = candidate.resolve()
            if candidate.is_symlink():
                with suppress(FileNotFoundError):
                    resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise _schema_error(
                f"{field} '{value}' tidak dapat di-resolve; periksa symlink loop.",
                path=path,
                slide_id=slide_id,
                block_id=block_id,
            ) from error
        if not resolved.is_relative_to(root):
            raise _schema_error(
                f"{field} keluar dari direktori deck.",
                path=path,
                slide_id=slide_id,
                block_id=block_id,
            )
    return value


def _asset_path(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
    base_dir: Path | None,
    suffixes: frozenset[str],
) -> str:
    text = _require_str(
        value,
        field=field,
        path=path,
        slide_id=slide_id,
        block_id=block_id,
    )
    return _validated_asset_path(
        text,
        suffixes=suffixes,
        field=field,
        path=path,
        slide_id=slide_id,
        block_id=block_id,
        base_dir=base_dir,
    )


def _schema_error(
    message: str,
    *,
    path: tuple[str | int, ...] = (),
    slide_id: str | None = None,
    block_id: str | None = None,
    key: str | None = None,
) -> DeckSchemaError:
    return DeckSchemaError(message, path=path, slide_id=slide_id, block_id=block_id, key=key)


def _require_mapping(
    value: object,
    *,
    path: tuple[str | int, ...],
    context: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _schema_error(f"{context} harus mapping.", path=path)
    result: dict[str, object] = {}
    for raw_key, raw_value in cast("dict[object, object]", value).items():
        if not isinstance(raw_key, str):
            raise _schema_error(
                f"Key {context} harus string, bukan {type(raw_key).__name__}.",
                path=path,
            )
        result[raw_key] = raw_value
    return result


def _require_list(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str | None = None,
    block_id: str | None = None,
) -> list[object]:
    if not isinstance(value, list):
        raise _schema_error(
            f"{field} harus array.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    return list(cast("list[object]", value))


def _require_field(
    mapping: Mapping[str, object],
    name: str,
    *,
    path: tuple[str | int, ...],
    context: str,
) -> object:
    if name not in mapping:
        raise _schema_error(f"{context} wajib memiliki '{name}'.", path=path)
    return mapping[name]


def _check_fields(
    mapping: Mapping[str, object],
    allowed: tuple[str, ...],
    *,
    path: tuple[str | int, ...],
    context: str,
    slide_id: str | None = None,
    block_id: str | None = None,
) -> None:
    allowed_set = set(allowed)
    unknown = sorted(set(mapping) - allowed_set)
    if not unknown:
        return
    name = unknown[0]
    field_path = (*path, name)
    if name in GEOMETRY_FIELDS:
        raise _schema_error(
            f"Field geometri '{name}' dilarang pada {context}; posisi dihitung layout.",
            path=field_path,
            slide_id=slide_id,
            block_id=block_id,
        )
    if name in STYLE_FIELDS:
        raise _schema_error(
            f"Field style '{name}' dilarang pada {context}; nilai visual berasal dari token.",
            path=field_path,
            slide_id=slide_id,
            block_id=block_id,
        )
    raise _schema_error(
        f"Field '{name}' tidak dikenal pada {context}.",
        path=field_path,
        slide_id=slide_id,
        block_id=block_id,
    )


def _require_str(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str | None = None,
    block_id: str | None = None,
) -> str:
    if not isinstance(value, str):
        raise _schema_error(
            f"{field} harus string.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    if not value.strip():
        raise _schema_error(
            f"{field} tidak boleh kosong.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    return value


def _optional_plain(
    mapping: Mapping[str, object],
    name: str,
    *,
    path: tuple[str | int, ...],
    field: str,
    multiline: bool = False,
) -> str | None:
    if name not in mapping:
        return None
    return _plain_value(
        mapping[name],
        field=field,
        path=(*path, name),
        multiline=multiline,
    )


def _inline_value(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str | None = None,
    block_id: str | None = None,
    multiline: bool = False,
) -> str:
    text = _require_str(
        value,
        field=field,
        path=path,
        slide_id=slide_id,
        block_id=block_id,
    )
    try:
        return parse_inline(text, field=field, multiline=multiline).source
    except MarkdownError as error:
        raise _schema_error(
            str(error),
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        ) from error


def _plain_value(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str | None = None,
    block_id: str | None = None,
    multiline: bool = False,
) -> str:
    text = _require_str(
        value,
        field=field,
        path=path,
        slide_id=slide_id,
        block_id=block_id,
    )
    try:
        return validate_plain_text(text, field=field, multiline=multiline)
    except MarkdownError as error:
        raise _schema_error(
            str(error),
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        ) from error


def _preserve_value(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str | None = None,
    block_id: str | None = None,
) -> str:
    text = _require_str(
        value,
        field=field,
        path=path,
        slide_id=slide_id,
        block_id=block_id,
    )
    try:
        return normalize_preserve_newlines(text, field=field)
    except MarkdownError as error:
        raise _schema_error(
            str(error),
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        ) from error


def _bool_value(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> bool:
    if not isinstance(value, bool):
        raise _schema_error(
            f"{field} harus boolean.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    return value


def _int_value(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _schema_error(
            f"{field} harus bilangan bulat.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    return value


def _number_value(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    slide_id: str,
    block_id: str,
) -> Number:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _schema_error(
            f"{field} harus angka.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise _schema_error(
            f"{field} harus angka finite.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    return value


def _choice(
    value: object,
    *,
    field: str,
    path: tuple[str | int, ...],
    choices: tuple[str, ...],
    slide_id: str | None = None,
    block_id: str | None = None,
) -> str:
    text = _require_str(
        value,
        field=field,
        path=path,
        slide_id=slide_id,
        block_id=block_id,
    )
    if text not in choices:
        allowed = ", ".join(choices)
        raise _schema_error(
            f"{field} harus salah satu dari {allowed}, bukan '{text}'.",
            path=path,
            slide_id=slide_id,
            block_id=block_id,
        )
    return text


def _validate_slide_id_value(
    value: object,
    *,
    path: tuple[str | int, ...],
) -> str:
    text = _require_str(value, field="id", path=path)
    try:
        return validate_slide_id(text)
    except KeyGrammarError as error:
        raise _schema_error(str(error), path=path) from error


def _validate_block_id_value(
    value: object,
    *,
    path: tuple[str | int, ...],
) -> str:
    text = _require_str(value, field="id", path=path)
    try:
        return validate_block_id(text)
    except KeyGrammarError as error:
        raise _schema_error(str(error), path=path) from error
