"""Pembentukan KeyBinding dari deck authoring yang sudah tervalidasi."""

from collections.abc import Mapping
from typing import cast

from .deck_ir import KeyBinding, KeyKind, KeyManifest
from .keys import KeyGrammarError, KeyRegistry, make_key
from .markdown import parse_inline
from .schema import (
    BlockDefinition,
    ChartSeries,
    DeckDefinition,
    SlideDefinition,
    SourceDefinition,
)


def build_bindings(definition: DeckDefinition) -> tuple[KeyBinding, ...]:
    """Bentuk seluruh binding deck dalam urutan slide dan block yang stabil."""
    bindings: list[KeyBinding] = []
    for slide_index, slide in enumerate(definition.slides):
        bindings.extend(build_slide_bindings(slide, slide_index=slide_index))
    return tuple(bindings)


def build_key_manifest(definition: DeckDefinition) -> KeyManifest:
    """Validasi binding deck melalui registry dan kembalikan manifest."""
    registry = KeyRegistry()
    registry.extend(build_bindings(definition))
    return registry.manifest()


def build_slide_bindings(slide: SlideDefinition, *, slide_index: int) -> tuple[KeyBinding, ...]:
    """Bentuk binding slide, notes, source, dan block di dalamnya."""
    bindings: list[KeyBinding] = []
    if slide.notes is not None:
        bindings.append(
            _preserve_binding(
                slide_id=slide.slide_id,
                block_id=None,
                leaf="notes",
                kind="notes",
                value=slide.notes,
                yaml_path=("slides", slide_index, "notes"),
            )
        )
    if slide.source is not None:
        bindings.append(
            _source_binding(
                slide_id=slide.slide_id,
                source=slide.source,
                slide_index=slide_index,
            )
        )
    if slide.layout == "custom":
        for row_index, row in enumerate(slide.rows):
            for block_index, block in enumerate(row):
                bindings.extend(
                    block_bindings(
                        block,
                        slide_id=slide.slide_id,
                        yaml_base=("slides", slide_index, "rows", row_index, "blocks", block_index),
                    )
                )
    else:
        for block_index, block in enumerate(slide.blocks):
            bindings.extend(
                block_bindings(
                    block,
                    slide_id=slide.slide_id,
                    yaml_base=("slides", slide_index, "blocks", block_index),
                )
            )
    return tuple(bindings)


def block_bindings(
    block: BlockDefinition,
    *,
    slide_id: str,
    yaml_base: tuple[str | int, ...],
) -> tuple[KeyBinding, ...]:
    """Bentuk seluruh binding untuk satu block."""
    fields = block.fields
    bindings: list[KeyBinding] = []

    if block.block_type == "text":
        bindings.append(
            _inline_binding(
                slide_id=slide_id,
                block_id=block.block_id,
                leaf="text",
                kind="text",
                raw=_field_str(fields, "text"),
                yaml_path=(*yaml_base, "text"),
            )
        )
        if "heading" in fields:
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="heading",
                    kind="text",
                    raw=_field_str(fields, "heading"),
                    yaml_path=(*yaml_base, "heading"),
                )
            )
    elif block.block_type == "bullets":
        for item_index, item in enumerate(_field_str_tuple(fields, "items"), start=1):
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf=f"item{item_index}.text",
                    kind="text",
                    raw=item,
                    yaml_path=(*yaml_base, "items", item_index - 1),
                )
            )
    elif block.block_type == "image":
        if "caption" in fields:
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="caption",
                    kind="media_text",
                    raw=_field_str(fields, "caption"),
                    yaml_path=(*yaml_base, "caption"),
                )
            )
    elif block.block_type == "table":
        for column_index, column in enumerate(_field_str_tuple(fields, "columns"), start=1):
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf=f"h{column_index}",
                    kind="text",
                    raw=column,
                    yaml_path=(*yaml_base, "columns", column_index - 1),
                )
            )
        for row_index, row in enumerate(_field_str_rows(fields, "rows"), start=1):
            for column_index, cell in enumerate(row, start=1):
                bindings.append(
                    _inline_binding(
                        slide_id=slide_id,
                        block_id=block.block_id,
                        leaf=f"r{row_index}.c{column_index}",
                        kind="text",
                        raw=cell,
                        yaml_path=(*yaml_base, "rows", row_index - 1, column_index - 1),
                    )
                )
        if "caption" in fields:
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="caption",
                    kind="text",
                    raw=_field_str(fields, "caption"),
                    yaml_path=(*yaml_base, "caption"),
                )
            )
    elif block.block_type == "chart":
        bindings.append(
            _plain_binding(
                slide_id=slide_id,
                block_id=block.block_id,
                leaf="title",
                kind="text",
                sync=False,
                value=_field_str(fields, "title"),
                yaml_path=(*yaml_base, "title"),
            )
        )
        for category_index, category in enumerate(_field_str_tuple(fields, "categories"), start=1):
            bindings.append(
                _plain_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf=f"cat{category_index}",
                    kind="text",
                    sync=False,
                    value=category,
                    yaml_path=(*yaml_base, "categories", category_index - 1),
                )
            )
        for series_index, series in enumerate(_field_series(fields), start=1):
            bindings.append(
                _plain_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf=f"series{series_index}.name",
                    kind="text",
                    sync=False,
                    value=series.name,
                    yaml_path=(*yaml_base, "series", series_index - 1, "name"),
                )
            )
            for value_index, value in enumerate(series.values, start=1):
                bindings.append(
                    _number_binding(
                        slide_id=slide_id,
                        block_id=block.block_id,
                        leaf=f"series{series_index}.value{value_index}",
                        value=value,
                        yaml_path=(
                            *yaml_base,
                            "series",
                            series_index - 1,
                            "values",
                            value_index - 1,
                        ),
                    )
                )
        if "caption" in fields:
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="caption",
                    kind="media_text",
                    raw=_field_str(fields, "caption"),
                    yaml_path=(*yaml_base, "caption"),
                )
            )
    elif block.block_type == "code":
        bindings.append(
            _preserve_binding(
                slide_id=slide_id,
                block_id=block.block_id,
                leaf="code",
                kind="text",
                value=_field_str(fields, "code"),
                yaml_path=(*yaml_base, "code"),
            )
        )
        if "filename" in fields:
            bindings.append(
                _plain_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="filename",
                    kind="text",
                    sync=True,
                    value=_field_str(fields, "filename"),
                    yaml_path=(*yaml_base, "filename"),
                )
            )
    elif block.block_type == "quote":
        bindings.append(
            _inline_binding(
                slide_id=slide_id,
                block_id=block.block_id,
                leaf="text",
                kind="text",
                raw=_field_str(fields, "text"),
                yaml_path=(*yaml_base, "text"),
            )
        )
        if "attribution" in fields:
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="attribution",
                    kind="text",
                    raw=_field_str(fields, "attribution"),
                    yaml_path=(*yaml_base, "attribution"),
                )
            )
    elif block.block_type == "diagram":
        if "caption" in fields:
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="caption",
                    kind="media_text",
                    raw=_field_str(fields, "caption"),
                    yaml_path=(*yaml_base, "caption"),
                )
            )
    elif block.block_type == "metric":
        bindings.append(
            _inline_binding(
                slide_id=slide_id,
                block_id=block.block_id,
                leaf="label",
                kind="text",
                raw=_field_str(fields, "label"),
                yaml_path=(*yaml_base, "label"),
            )
        )
        bindings.append(
            _inline_binding(
                slide_id=slide_id,
                block_id=block.block_id,
                leaf="value",
                kind="text",
                raw=_field_str(fields, "value"),
                yaml_path=(*yaml_base, "value"),
            )
        )
        if "caption" in fields:
            bindings.append(
                _inline_binding(
                    slide_id=slide_id,
                    block_id=block.block_id,
                    leaf="caption",
                    kind="text",
                    raw=_field_str(fields, "caption"),
                    yaml_path=(*yaml_base, "caption"),
                )
            )
    elif block.block_type not in {"divider", "spacer"}:
        raise KeyGrammarError(
            f"Block '{block.block_id}' memiliki type '{block.block_type}' tanpa binding."
        )
    return tuple(bindings)


def number_text(value: int | float) -> str:
    """Format angka chart deterministik untuk ``plain_text``."""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def _source_binding(
    *,
    slide_id: str,
    source: SourceDefinition,
    slide_index: int,
) -> KeyBinding:
    return KeyBinding(
        key=make_key(slide_id, None, "source.text"),
        slide_id=slide_id,
        block_id=None,
        leaf="source.text",
        kind="source",
        sync=True,
        yaml_path=("slides", slide_index, "source", "text"),
        value=source.text,
        plain_text=source.text,
    )


def _inline_binding(
    *,
    slide_id: str,
    block_id: str,
    leaf: str,
    kind: KeyKind,
    raw: str,
    yaml_path: tuple[str | int, ...],
    sync: bool = True,
) -> KeyBinding:
    parsed = parse_inline(raw, field=leaf)
    if kind not in {"text", "media_text"}:
        raise KeyGrammarError(f"Binding inline '{leaf}' harus kind text atau media_text.")
    return KeyBinding(
        key=make_key(slide_id, block_id, leaf),
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=sync,
        yaml_path=yaml_path,
        value=raw,
        plain_text=parsed.plain_text,
    )


def _plain_binding(
    *,
    slide_id: str,
    block_id: str,
    leaf: str,
    kind: KeyKind,
    sync: bool,
    value: str,
    yaml_path: tuple[str | int, ...],
) -> KeyBinding:
    if kind not in {"text", "media_text"}:
        raise KeyGrammarError(f"Binding plain '{leaf}' harus kind text atau media_text.")
    return KeyBinding(
        key=make_key(slide_id, block_id, leaf),
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=sync,
        yaml_path=yaml_path,
        value=value,
        plain_text=value,
    )


def _preserve_binding(
    *,
    slide_id: str,
    block_id: str | None,
    leaf: str,
    kind: KeyKind,
    value: str,
    yaml_path: tuple[str | int, ...],
) -> KeyBinding:
    if kind not in {"text", "notes"}:
        raise KeyGrammarError(f"Binding preserve '{leaf}' harus kind text atau notes.")
    return KeyBinding(
        key=make_key(slide_id, block_id, leaf),
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=True,
        yaml_path=yaml_path,
        value=value,
        plain_text=value,
    )


def _number_binding(
    *,
    slide_id: str,
    block_id: str,
    leaf: str,
    value: int | float,
    yaml_path: tuple[str | int, ...],
) -> KeyBinding:
    return KeyBinding(
        key=make_key(slide_id, block_id, leaf),
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind="data",
        sync=False,
        yaml_path=yaml_path,
        value=value,
        plain_text=number_text(value),
    )


def _field_str(fields: Mapping[str, object], name: str) -> str:
    value = fields[name]
    if not isinstance(value, str):
        raise KeyGrammarError(f"Field '{name}' harus string pada binding.")
    return value


def _field_str_tuple(fields: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = fields[name]
    if not isinstance(value, tuple):
        raise KeyGrammarError(f"Field '{name}' harus tuple string pada binding.")
    items: list[str] = []
    for item in cast("tuple[object, ...]", value):
        if not isinstance(item, str):
            raise KeyGrammarError(f"Field '{name}' harus tuple string pada binding.")
        items.append(item)
    return tuple(items)


def _field_str_rows(fields: Mapping[str, object], name: str) -> tuple[tuple[str, ...], ...]:
    value = fields[name]
    if not isinstance(value, tuple):
        raise KeyGrammarError(f"Field '{name}' harus tuple baris string pada binding.")
    rows: list[tuple[str, ...]] = []
    for raw_row in cast("tuple[object, ...]", value):
        if not isinstance(raw_row, tuple):
            raise KeyGrammarError(f"Field '{name}' harus tuple baris string pada binding.")
        row: list[str] = []
        for cell in cast("tuple[object, ...]", raw_row):
            if not isinstance(cell, str):
                raise KeyGrammarError(f"Field '{name}' harus tuple baris string pada binding.")
            row.append(cell)
        rows.append(tuple(row))
    return tuple(rows)


def _field_series(fields: Mapping[str, object]) -> tuple[ChartSeries, ...]:
    value = fields["series"]
    if not isinstance(value, tuple):
        raise KeyGrammarError("Field 'series' harus tuple ChartSeries pada binding.")
    series: list[ChartSeries] = []
    for item in cast("tuple[object, ...]", value):
        if not isinstance(item, ChartSeries):
            raise KeyGrammarError("Field 'series' harus tuple ChartSeries pada binding.")
        series.append(item)
    return tuple(series)
