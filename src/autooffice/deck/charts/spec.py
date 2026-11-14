"""Spec chart AutoOffice yang diekstrak dari ``BlockIR`` tervalidasi."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.model.schema import (
    CHART_KINDS,
    CHART_ORIENTATIONS,
    ChartSeries,
    Number,
)
from autooffice.errors import AutoOfficeError

ChartKind = Literal["bar", "line", "donut"]
ChartOrientation = Literal["vertical", "horizontal"]

_MAX_SERIES = 4
_MAX_DONUT_CATEGORIES = 4
_MIN_DONUT_CATEGORIES = 2


class ChartSpecError(AutoOfficeError, ValueError):
    """Spec chart tidak valid atau tidak bisa diekstrak dari block."""


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """Spec chart immutable yang siap dipakai renderer dan Sheets adapter."""

    chart_id: str
    kind: ChartKind
    categories: tuple[str, ...]
    series: tuple[ChartSeries, ...]
    orientation: ChartOrientation | None
    title: str
    alt: str
    unit: str | None = None

    def __post_init__(self) -> None:
        chart_id = _validate_chart_id(self.chart_id)
        kind = _validate_kind(self.kind)
        categories = _validate_categories(self.categories)
        series = _validate_series(self.series, category_count=len(categories))
        orientation = _validate_orientation(kind, self.orientation)
        title = _required_text(self.title, field="title", context=f"chart '{chart_id}'")
        alt = _required_text(self.alt, field="alt", context=f"chart '{chart_id}'")
        unit = (
            None
            if self.unit is None
            else _required_text(self.unit, field="unit", context=f"chart '{chart_id}'")
        )
        _validate_limits(chart_id, kind, categories, series)
        object.__setattr__(self, "chart_id", chart_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "series", series)
        object.__setattr__(self, "orientation", orientation)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "alt", alt)
        object.__setattr__(self, "unit", unit)


def make_chart_id(slide_id: str, block_id: str) -> str:
    """Bentuk ``chart_id`` logis stabil ``<slide_id>.<block_id>``."""
    slide = _required_text(slide_id, field="slide_id", context="chart")
    block = _required_text(block_id, field="block_id", context="chart")
    return _validate_chart_id(f"{slide}.{block}")


def build_chart_spec(
    block: BlockIR,
    slide_id: str | None = None,
    *,
    chart_id: str | None = None,
) -> ChartSpec:
    """Ekstrak dan validasi ``ChartSpec`` dari satu block chart.

    ``chart_id`` eksplisit menang bila diberikan. Bila tidak, ID dibentuk dari
    ``slide_id`` dan ``block.block_id``. Tanpa ``slide_id``, ID memakai
    ``block.block_id`` agar pemakaian spec-only tetap deterministik; renderer
    wajib memberi ``slide_id`` supaya ID sesuai kontrak ``<slide>.<block>``.
    """
    if block.block_type != "chart":
        raise ChartSpecError(f"Block '{block.block_id}' bertipe '{block.block_type}', bukan chart.")
    fields = block.fields
    kind = _field_text(fields, "kind", block_id=block.block_id)
    if kind not in CHART_KINDS:
        allowed = ", ".join(CHART_KINDS)
        raise ChartSpecError(
            f"Block chart '{block.block_id}' memiliki kind '{kind}'; pilih {allowed}."
        )
    title = _field_text(fields, "title", block_id=block.block_id)
    alt = _field_text(fields, "alt", block_id=block.block_id)
    categories = _field_categories(fields.get("categories"), block_id=block.block_id)
    series = _field_series(fields.get("series"), block_id=block.block_id)
    orientation = _field_optional_text(fields, "orientation", block_id=block.block_id)
    unit = _field_optional_text(fields, "unit", block_id=block.block_id)
    resolved_id = (
        chart_id
        if chart_id is not None
        else (make_chart_id(slide_id, block.block_id) if slide_id is not None else block.block_id)
    )
    return ChartSpec(
        chart_id=resolved_id,
        kind=cast(ChartKind, kind),
        categories=categories,
        series=series,
        orientation=cast(ChartOrientation | None, orientation),
        title=title,
        alt=alt,
        unit=unit,
    )


def _validate_chart_id(value: object) -> str:
    chart_id = _required_text(value, field="chart_id", context="chart")
    if ":" in chart_id:
        raise ChartSpecError(f"chart_id '{chart_id}' tidak boleh memuat ':'.")
    if any(character.isspace() for character in chart_id):
        raise ChartSpecError(f"chart_id '{chart_id}' tidak boleh memuat whitespace.")
    return chart_id


def _validate_kind(value: object) -> ChartKind:
    if not isinstance(value, str) or value not in CHART_KINDS:
        allowed = ", ".join(CHART_KINDS)
        raise ChartSpecError(f"kind chart harus salah satu dari {allowed}, bukan {value!r}.")
    return cast(ChartKind, value)


def _validate_categories(value: object) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, tuple | list):
        raise ChartSpecError("categories chart wajib berupa daftar label.")
    return tuple(
        _required_text(item, field=f"categories[{index}]", context="chart")
        for index, item in enumerate(value)
    )


def _validate_series(
    value: object,
    *,
    category_count: int,
) -> tuple[ChartSeries, ...]:
    if not isinstance(value, tuple | list):
        raise ChartSpecError("series chart wajib berupa daftar seri.")
    series: list[ChartSeries] = []
    for index, item in enumerate(value):
        if not isinstance(item, ChartSeries):
            raise ChartSpecError(f"series[{index}] chart wajib berupa ChartSeries.")
        name = _required_text(item.name, field=f"series[{index}].name", context="chart")
        values = _numbers(
            item.values,
            series_name=name,
        )
        if len(values) != category_count:
            raise ChartSpecError(
                f"Seri '{name}' memiliki {len(values)} nilai; "
                f"jumlah kategori adalah {category_count}."
            )
        series.append(ChartSeries(name=name, values=values))
    return tuple(series)


def _validate_limits(
    chart_id: str,
    kind: ChartKind,
    categories: tuple[str, ...],
    series: tuple[ChartSeries, ...],
) -> None:
    if kind == "donut":
        if len(series) != 1:
            raise ChartSpecError(
                f"Chart donut '{chart_id}' wajib memiliki tepat satu seri, bukan {len(series)}."
            )
        if not _MIN_DONUT_CATEGORIES <= len(categories) <= _MAX_DONUT_CATEGORIES:
            raise ChartSpecError(
                f"Chart donut '{chart_id}' wajib memiliki "
                f"{_MIN_DONUT_CATEGORIES} sampai {_MAX_DONUT_CATEGORIES} kategori berwarna, "
                f"bukan {len(categories)}."
            )
        return
    if len(categories) < 2:
        raise ChartSpecError(f"Chart {kind} '{chart_id}' wajib memiliki minimal dua kategori.")
    if not series:
        raise ChartSpecError(f"Chart {kind} '{chart_id}' wajib memiliki minimal 1 seri.")
    if len(series) > _MAX_SERIES:
        raise ChartSpecError(
            f"Chart {kind} '{chart_id}' maksimal {_MAX_SERIES} seri, bukan {len(series)}."
        )


def _validate_orientation(kind: ChartKind, value: object) -> ChartOrientation | None:
    if value is None:
        return "vertical" if kind == "bar" else None
    if not isinstance(value, str) or value not in CHART_ORIENTATIONS:
        allowed = ", ".join(CHART_ORIENTATIONS)
        raise ChartSpecError(f"orientation chart harus {allowed}, bukan {value!r}.")
    if kind != "bar":
        raise ChartSpecError("orientation hanya valid untuk chart bar.")
    return cast(ChartOrientation, value)


def _field_text(fields: Mapping[str, object], field: str, *, block_id: str) -> str:
    value = fields.get(field)
    return _required_text(value, field=field, context=f"block chart '{block_id}'")


def _field_optional_text(
    fields: Mapping[str, object],
    field: str,
    *,
    block_id: str,
) -> str | None:
    if field not in fields or fields[field] is None:
        return None
    return _field_text(fields, field, block_id=block_id)


def _field_categories(value: object, *, block_id: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, tuple | list):
        raise ChartSpecError(
            f"Block chart '{block_id}' wajib memiliki categories berupa daftar label."
        )
    return tuple(
        _required_text(
            item,
            field=f"categories[{index}]",
            context=f"block chart '{block_id}'",
        )
        for index, item in enumerate(value)
    )


def _field_series(value: object, *, block_id: str) -> tuple[ChartSeries, ...]:
    if not isinstance(value, tuple | list):
        raise ChartSpecError(f"Block chart '{block_id}' wajib memiliki series berupa daftar seri.")
    result: list[ChartSeries] = []
    for index, item in enumerate(value):
        if isinstance(item, ChartSeries):
            result.append(item)
            continue
        if isinstance(item, Mapping):
            result.append(_series_from_mapping(item, index=index, block_id=block_id))
            continue
        raise ChartSpecError(
            f"series[{index}] pada block chart '{block_id}' wajib berupa mapping atau ChartSeries."
        )
    return tuple(result)


def _series_from_mapping(
    value: Mapping[str, object],
    *,
    index: int,
    block_id: str,
) -> ChartSeries:
    unexpected = set(value) - {"name", "values"}
    if unexpected:
        fields = ", ".join(sorted(str(field) for field in unexpected))
        raise ChartSpecError(
            f"series[{index}] pada block chart '{block_id}' memuat field tidak dikenal: {fields}."
        )
    if "name" not in value or "values" not in value:
        raise ChartSpecError(
            f"series[{index}] pada block chart '{block_id}' wajib memiliki name dan values."
        )
    name = _required_text(
        value["name"],
        field=f"series[{index}].name",
        context=f"block chart '{block_id}'",
    )
    raw_values = value["values"]
    if isinstance(raw_values, str) or not isinstance(raw_values, tuple | list):
        raise ChartSpecError(
            f"series[{index}].values pada block chart '{block_id}' wajib berupa daftar angka."
        )
    return ChartSeries(name=name, values=_numbers(raw_values, series_name=name))


def _numbers(value: object, *, series_name: str) -> tuple[Number, ...]:
    if isinstance(value, str) or not isinstance(value, tuple | list):
        raise ChartSpecError(f"Nilai seri '{series_name}' wajib berupa daftar angka.")
    numbers: list[Number] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise ChartSpecError(
                f"Nilai seri '{series_name}' indeks {index} harus angka, bukan {item!r}."
            )
        if isinstance(item, float) and not math.isfinite(item):
            raise ChartSpecError(f"Nilai seri '{series_name}' indeks {index} harus angka finite.")
        numbers.append(item)
    return tuple(numbers)


def _required_text(value: object, *, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChartSpecError(f"{context} wajib memiliki {field} berupa teks non-kosong.")
    return value


__all__ = [
    "ChartKind",
    "ChartOrientation",
    "ChartSpec",
    "ChartSpecError",
    "build_chart_spec",
    "make_chart_id",
]
