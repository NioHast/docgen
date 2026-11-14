"""Coverage plan pre-render untuk deck AutoOffice v1."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .deck_ir import BlockIR, DeckIR
from .schema import ChartSeries

COVERAGE_SCHEMA = "autooffice.coverage/v1"
_VISIBLE_KINDS = frozenset({"text", "source", "media_text"})


@dataclass(frozen=True, slots=True)
class ChartCoverage:
    """Satu chart yang wajib hadir native atau linked di target."""

    chart_id: str
    key: str
    native: bool = True


@dataclass(frozen=True, slots=True)
class CoverageFindings:
    """Temuan coverage setelah key render dibandingkan dengan plan."""

    missing: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    duplicate: tuple[str, ...] = ()
    unkeyed_visible: tuple[str, ...] = ()
    missing_alt: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """True bila tidak ada temuan yang menghalangi build."""
        return not (
            self.missing or self.extra or self.duplicate or self.unkeyed_visible or self.missing_alt
        )


@dataclass(frozen=True, slots=True)
class CoveragePlan:
    """Daftar key dan objek yang wajib muncul pada output deck."""

    deck_id: str
    declared_keys: tuple[str, ...]
    visible_keys: tuple[str, ...]
    sync_keys: tuple[str, ...]
    data_keys: tuple[str, ...]
    unkeyed_visible: tuple[str, ...]
    missing_alt: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    charts: tuple[ChartCoverage, ...]
    schema: str = COVERAGE_SCHEMA

    @property
    def ok(self) -> bool:
        """True bila plan tidak memiliki temuan struktural."""
        return not (self.unkeyed_visible or self.missing_alt or self.duplicate_keys)

    def findings(self, rendered_keys: Iterable[str]) -> CoverageFindings:
        """Bandingkan key yang benar-benar dirender dengan plan."""
        rendered = tuple(rendered_keys)
        rendered_counts = Counter(rendered)
        declared_set = set(self.declared_keys)
        rendered_set = set(rendered)
        duplicate = {key for key, count in rendered_counts.items() if count > 1} | set(
            self.duplicate_keys
        )
        return CoverageFindings(
            missing=tuple(sorted(declared_set - rendered_set)),
            extra=tuple(sorted(rendered_set - declared_set)),
            duplicate=tuple(sorted(duplicate)),
            unkeyed_visible=self.unkeyed_visible,
            missing_alt=self.missing_alt,
        )

    def to_report(self, rendered_keys: Iterable[str]) -> dict[str, object]:
        """Bentuk report coverage deterministik tanpa timestamp."""
        rendered = tuple(rendered_keys)
        findings = self.findings(rendered)
        return {
            "schema": self.schema,
            "deck_id": self.deck_id,
            "declared": len(self.declared_keys),
            "rendered": len(rendered),
            "missing": list(findings.missing),
            "extra": list(findings.extra),
            "duplicate": list(findings.duplicate),
            "unkeyed_visible": list(findings.unkeyed_visible),
            "missing_alt": list(findings.missing_alt),
            "charts": [
                {
                    "chart_id": chart.chart_id,
                    "native": chart.native,
                    "key": chart.key,
                }
                for chart in self.charts
            ],
        }


def build_coverage_plan(deck: DeckIR) -> CoveragePlan:
    """Bangun coverage plan dari DeckIR dan KeyManifest."""
    bindings = deck.keys.bindings
    declared_keys = tuple(binding.key for binding in bindings)
    counts = Counter(declared_keys)
    duplicate_keys = tuple(sorted(key for key, count in counts.items() if count > 1))
    visible_keys = tuple(binding.key for binding in bindings if binding.kind in _VISIBLE_KINDS)
    sync_keys = tuple(binding.key for binding in bindings if binding.sync)
    data_keys = tuple(binding.key for binding in bindings if binding.kind == "data")

    declarations: dict[str, set[str]] = {}
    for binding in bindings:
        if binding.block_id is None:
            continue
        namespace = f"{binding.slide_id}.{binding.block_id}"
        declarations.setdefault(namespace, set()).add(binding.leaf)

    unkeyed_visible: list[str] = []
    missing_alt: list[str] = []
    charts: list[ChartCoverage] = []
    for slide in deck.slides:
        slide_leaves = {
            binding.leaf
            for binding in bindings
            if binding.slide_id == slide.slide_id and binding.block_id is None
        }
        if slide.source is not None and "source.text" not in slide_leaves:
            unkeyed_visible.append(f"{slide.slide_id}.source")
        for block in slide.blocks:
            namespace = f"{slide.slide_id}.{block.block_id}"
            expected = set(_expected_leaves(block))
            missing = expected - declarations.get(namespace, set())
            if missing:
                unkeyed_visible.append(namespace)
            if _requires_alt(block) and _missing_alt(block):
                missing_alt.append(namespace)
            if block.block_type == "chart":
                charts.append(ChartCoverage(chart_id=namespace, key=namespace))
    return CoveragePlan(
        deck_id=_deck_id(deck),
        declared_keys=declared_keys,
        visible_keys=visible_keys,
        sync_keys=sync_keys,
        data_keys=data_keys,
        unkeyed_visible=tuple(unkeyed_visible),
        missing_alt=tuple(missing_alt),
        duplicate_keys=duplicate_keys,
        charts=tuple(charts),
    )


def check_coverage(deck: DeckIR, rendered_keys: Iterable[str]) -> CoverageFindings:
    """Bangun plan lalu bandingkan dengan key yang dirender."""
    return build_coverage_plan(deck).findings(rendered_keys)


def _deck_id(deck: DeckIR) -> str:
    title = deck.meta.get("title", "")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "deck"


def _expected_leaves(block: BlockIR) -> tuple[str, ...]:
    fields = block.fields
    if block.block_type == "text":
        leaves = ["text"]
        if "heading" in fields:
            leaves.append("heading")
        return tuple(leaves)
    if block.block_type == "bullets":
        return tuple(
            f"item{index}.text" for index in range(1, len(_sequence(fields.get("items"))) + 1)
        )
    if block.block_type == "image":
        return ("caption",) if "caption" in fields else ()
    if block.block_type == "table":
        columns = _sequence(fields.get("columns"))
        rows = _sequence(fields.get("rows"))
        leaves = [f"h{index}" for index in range(1, len(columns) + 1)]
        for row_index, row in enumerate(rows, start=1):
            for column_index in range(1, len(_sequence(row)) + 1):
                leaves.append(f"r{row_index}.c{column_index}")
        if "caption" in fields:
            leaves.append("caption")
        return tuple(leaves)
    if block.block_type == "chart":
        leaves = ["title"]
        leaves.extend(
            f"cat{index}" for index in range(1, len(_sequence(fields.get("categories"))) + 1)
        )
        for series_index, series in enumerate(_series_parts(fields.get("series")), start=1):
            leaves.append(f"series{series_index}.name")
            leaves.extend(
                f"series{series_index}.value{value_index}" for value_index in range(1, series + 1)
            )
        if "caption" in fields:
            leaves.append("caption")
        return tuple(leaves)
    if block.block_type == "code":
        leaves = ["code"]
        if "filename" in fields:
            leaves.append("filename")
        return tuple(leaves)
    if block.block_type == "quote":
        leaves = ["text"]
        if "attribution" in fields:
            leaves.append("attribution")
        return tuple(leaves)
    if block.block_type == "diagram":
        return ("caption",) if "caption" in fields else ()
    if block.block_type == "metric":
        leaves = ["label", "value"]
        if "caption" in fields:
            leaves.append("caption")
        return tuple(leaves)
    return ()


def _requires_alt(block: BlockIR) -> bool:
    return block.block_type in {"image", "diagram", "chart"}


def _missing_alt(block: BlockIR) -> bool:
    alt = block.fields.get("alt")
    return not isinstance(alt, str) or not alt.strip()


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return tuple(value)
    if isinstance(value, list):
        return tuple(value)
    return ()


def _series_parts(value: object) -> tuple[int, ...]:
    if not isinstance(value, tuple | list):
        return ()
    result: list[int] = []
    for item in value:
        if isinstance(item, ChartSeries):
            result.append(len(item.values))
            continue
        if isinstance(item, Mapping):
            values = item.get("values")
            result.append(len(_sequence(values)))
            continue
        result.append(0)
    return tuple(result)
