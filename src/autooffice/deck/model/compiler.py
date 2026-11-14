"""Compiler deterministik deck YAML menjadi Deck IR AutoOffice v1."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .bindings import build_bindings
from .deck_ir import BlockIR, DeckIR, KeyManifest, SlideIR
from .keys import KeyRegistry
from .loader import load_deck
from .markdown import parse_inline
from .schema import (
    BlockDefinition,
    ChartSeries,
    DeckDefinition,
    DeckSchemaError,
    SlideDefinition,
)


def compile_deck(definition: DeckDefinition) -> DeckIR:
    """Kompilasi ``DeckDefinition`` menjadi ``DeckIR`` dan ``KeyManifest``."""
    if not definition.slides:
        raise DeckSchemaError("Deck harus memiliki minimal satu slide.")
    seen_slide_ids: set[str] = set()
    for slide in definition.slides:
        if slide.slide_id in seen_slide_ids:
            raise DeckSchemaError(
                f"Slide ID '{slide.slide_id}' duplikat pada deck.",
                slide_id=slide.slide_id,
            )
        seen_slide_ids.add(slide.slide_id)

    registry = KeyRegistry()
    registry.extend(build_bindings(definition))
    manifest: KeyManifest = registry.manifest()

    slides = tuple(
        _compile_slide(slide, order=index) for index, slide in enumerate(definition.slides)
    )
    return DeckIR(
        schema=definition.schema,
        meta=definition.meta.as_mapping(),
        theme_name=definition.theme_name,
        slides=slides,
        keys=manifest,
    )


def compile_deck_file(
    path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> DeckIR:
    """Load satu berkas YAML lalu kompilasi menjadi ``DeckIR``."""
    return compile_deck(load_deck(path, base_dir=base_dir))


def compile_file(path: str | Path, *, base_dir: str | Path | None = None) -> DeckIR:
    """Alias ``compile_deck_file`` untuk pemakaian pipeline."""
    return compile_deck_file(path, base_dir=base_dir)


def _compile_slide(slide: SlideDefinition, *, order: int) -> SlideIR:
    if slide.layout == "custom":
        compiled_rows = tuple(tuple(_compile_block(block) for block in row) for row in slide.rows)
        blocks = tuple(block for row in compiled_rows for block in row)
        rows = tuple(tuple(block.block_id for block in row) for row in compiled_rows)
    else:
        blocks = tuple(_compile_block(block) for block in slide.blocks)
        rows = ()
    source: dict[str, str] | None = None
    if slide.source is not None:
        source = {"text": slide.source.text}
        if slide.source.url is not None:
            source["url"] = slide.source.url
    return SlideIR(
        slide_id=slide.slide_id,
        layout=slide.layout,
        order=order,
        blocks=blocks,
        notes=slide.notes,
        source=source,
        rows=rows,
    )


def _compile_block(block: BlockDefinition) -> BlockIR:
    fields = _compile_fields(block)
    return BlockIR(
        block_id=block.block_id,
        block_type=block.block_type,
        span=block.span,
        role=block.role,
        fields=fields,
    )


def _compile_fields(block: BlockDefinition) -> dict[str, object]:
    source = block.fields
    block_type = block.block_type
    if block_type == "text":
        fields: dict[str, object] = {"text": _inline_text(_field_str(source, "text"))}
        if "heading" in source:
            fields["heading"] = _inline_text(_field_str(source, "heading"))
        return fields
    if block_type == "bullets":
        items = tuple(_inline_text(item) for item in _field_str_tuple(source, "items"))
        return {"items": items, "ordered": _field_bool(source, "ordered")}
    if block_type == "image":
        fields = {
            "path": _field_str(source, "path"),
            "alt": _field_str(source, "alt"),
            "fit": _field_str(source, "fit"),
        }
        if "caption" in source:
            fields["caption"] = _inline_text(_field_str(source, "caption"))
        return fields
    if block_type == "table":
        columns = tuple(_inline_text(column) for column in _field_str_tuple(source, "columns"))
        rows = tuple(
            tuple(_inline_text(cell) for cell in row) for row in _field_str_rows(source, "rows")
        )
        fields = {"columns": columns, "rows": rows}
        if "caption" in source:
            fields["caption"] = _inline_text(_field_str(source, "caption"))
        if "emphasis_column" in source:
            fields["emphasis_column"] = _field_int(source, "emphasis_column")
        return fields
    if block_type == "chart":
        fields = {
            "kind": _field_str(source, "kind"),
            "title": _field_str(source, "title"),
            "alt": _field_str(source, "alt"),
            "categories": _field_str_tuple(source, "categories"),
            "series": _field_series(source),
        }
        if "orientation" in source:
            fields["orientation"] = _field_str(source, "orientation")
        if "unit" in source:
            fields["unit"] = _field_str(source, "unit")
        if "caption" in source:
            fields["caption"] = _inline_text(_field_str(source, "caption"))
        return fields
    if block_type == "code":
        fields = {
            "code": _field_str(source, "code"),
            "language": _field_str(source, "language"),
            "line_numbers": _field_bool(source, "line_numbers"),
        }
        if "filename" in source:
            fields["filename"] = _field_str(source, "filename")
        return fields
    if block_type == "quote":
        fields = {"text": _inline_text(_field_str(source, "text"))}
        if "attribution" in source:
            fields["attribution"] = _inline_text(_field_str(source, "attribution"))
        return fields
    if block_type == "diagram":
        fields = {
            "source": _field_str(source, "source"),
            "alt": _field_str(source, "alt"),
        }
        if "caption" in source:
            fields["caption"] = _inline_text(_field_str(source, "caption"))
        return fields
    if block_type == "divider":
        return {}
    if block_type == "spacer":
        return {"size": _field_str(source, "size")}
    if block_type == "metric":
        fields = {
            "label": _inline_text(_field_str(source, "label")),
            "value": _inline_text(_field_str(source, "value")),
            "status": _field_str(source, "status"),
        }
        if "caption" in source:
            fields["caption"] = _inline_text(_field_str(source, "caption"))
        return fields
    raise DeckSchemaError(
        f"Block '{block.block_id}' memiliki type '{block_type}' yang tidak dikenal.",
        block_id=block.block_id,
    )


def _inline_text(value: str) -> str:
    return parse_inline(value).plain_text


def _field_str(fields: Mapping[str, object], name: str) -> str:
    value = fields[name]
    if not isinstance(value, str):
        raise DeckSchemaError(f"Field '{name}' harus string pada compiler.")
    return value


def _field_bool(fields: Mapping[str, object], name: str) -> bool:
    value = fields[name]
    if not isinstance(value, bool):
        raise DeckSchemaError(f"Field '{name}' harus boolean pada compiler.")
    return value


def _field_int(fields: Mapping[str, object], name: str) -> int:
    value = fields[name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise DeckSchemaError(f"Field '{name}' harus bilangan bulat pada compiler.")
    return value


def _field_str_tuple(fields: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = fields[name]
    if not isinstance(value, tuple):
        raise DeckSchemaError(f"Field '{name}' harus tuple string pada compiler.")
    items: list[str] = []
    for item in cast("tuple[object, ...]", value):
        if not isinstance(item, str):
            raise DeckSchemaError(f"Field '{name}' harus tuple string pada compiler.")
        items.append(item)
    return tuple(items)


def _field_str_rows(
    fields: Mapping[str, object],
    name: str,
) -> tuple[tuple[str, ...], ...]:
    value = fields[name]
    if not isinstance(value, tuple):
        raise DeckSchemaError(f"Field '{name}' harus tuple baris string pada compiler.")
    rows: list[tuple[str, ...]] = []
    for raw_row in cast("tuple[object, ...]", value):
        if not isinstance(raw_row, tuple):
            raise DeckSchemaError(f"Field '{name}' harus tuple baris string pada compiler.")
        cells: list[str] = []
        for cell in cast("tuple[object, ...]", raw_row):
            if not isinstance(cell, str):
                raise DeckSchemaError(f"Field '{name}' harus tuple baris string pada compiler.")
            cells.append(cell)
        rows.append(tuple(cells))
    return tuple(rows)


def _field_series(fields: Mapping[str, object]) -> tuple[ChartSeries, ...]:
    value = fields["series"]
    if not isinstance(value, tuple):
        raise DeckSchemaError("Field 'series' harus tuple ChartSeries pada compiler.")
    series: list[ChartSeries] = []
    for item in cast("tuple[object, ...]", value):
        if not isinstance(item, ChartSeries):
            raise DeckSchemaError("Field 'series' harus tuple ChartSeries pada compiler.")
        series.append(item)
    return tuple(series)
