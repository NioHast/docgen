"""Ekstraksi key nyata dari PPTX dan perbandingan dengan ``KeyManifest``."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import cast

from pptx.presentation import Presentation
from pptx.shapes.autoshape import Shape
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide

from autooffice.deck.model.deck_ir import BlockIR, DeckIR, SlideIR
from autooffice.deck.render.protocol import CoverageReport

from .notes import notes_text
from .shapes import (
    CHART_MARKER,
    CHROME_PREFIX,
    DIAGRAM_MARKER,
    IMAGE_MARKER,
    KEY_MARKER,
    TABLE_MARKER,
    PptxRenderError,
    key_from_shape,
    namespace_from_shape,
    shape_description,
    shape_extension_keys,
    shape_name,
)
from .table import table_cell_key

_ALT_MARKERS = {
    "chart": CHART_MARKER,
    "diagram": DIAGRAM_MARKER,
    "image": IMAGE_MARKER,
}


class CoverageError(PptxRenderError):
    """Coverage output tidak lengkap sehingga PPTX final tidak boleh ditulis."""

    def __init__(self, report: CoverageReport) -> None:
        self.report = report
        super().__init__(_message(report))


@dataclass(slots=True)
class _Scan:
    keys_by_slide: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    unkeyed: list[str] = field(default_factory=list)
    missing_alt: list[str] = field(default_factory=list)


def collect_coverage(presentation: Presentation, deck: DeckIR) -> CoverageReport:
    """Baca key shape, table cell, chart metadata, dan notes dari PPTX nyata."""
    if len(presentation.slides) != len(deck.slides):
        raise PptxRenderError(
            f"Jumlah slide PPTX {len(presentation.slides)} tidak sama dengan DeckIR "
            f"{len(deck.slides)}."
        )
    scan = _Scan()
    for slide, slide_ir in zip(presentation.slides, deck.slides, strict=True):
        _scan_slide(slide, slide_ir, scan)
        _check_notes(slide, slide_ir, scan)
        _check_alt(slide, slide_ir, scan)

    bindings = deck.keys.bindings
    declared = tuple(binding.key for binding in bindings)
    declared_set = set(declared)
    rendered = [key for keys in scan.keys_by_slide.values() for key in keys]
    rendered_set = set(rendered)
    counts = Counter(rendered)
    declared_counts = Counter(declared)
    duplicate = {key for key, count in counts.items() if count > 1} | {
        key for key, count in declared_counts.items() if count > 1
    }
    missing = sorted(
        {
            binding.key
            for binding in bindings
            if binding.key not in set(scan.keys_by_slide.get(binding.slide_id, ()))
        }
    )
    unkeyed = list(scan.unkeyed)
    unkeyed.extend(sorted(rendered_set - declared_set))
    for key in sorted(rendered_set & declared_set):
        expected = {binding.slide_id for binding in bindings if binding.key == key}
        actual = {slide_id for slide_id, keys in scan.keys_by_slide.items() if key in keys}
        for slide_id in sorted(actual - expected):
            unkeyed.append(f"{slide_id}:{key}")
    return CoverageReport(
        missing_keys=tuple(missing),
        duplicate_keys=tuple(sorted(duplicate)),
        unkeyed_visible=tuple(sorted(set(unkeyed))),
        missing_alt=tuple(sorted(set(scan.missing_alt))),
    )


def raise_if_incomplete(report: CoverageReport) -> CoverageReport:
    """Gagalkan build bila report coverage belum bersih."""
    if not report.ok:
        raise CoverageError(report)
    return report


def _scan_slide(slide: Slide, slide_ir: SlideIR, scan: _Scan) -> None:
    slide_id = slide_ir.slide_id
    for shape in slide.shapes:
        name = shape_name(shape)
        if name.startswith(CHROME_PREFIX):
            continue
        if shape.has_table:
            _scan_table(shape, slide_id, scan)
            continue
        if shape.has_text_frame:
            key = key_from_shape(shape)
            text = cast("Shape", shape).text_frame.text
            if key is not None:
                scan.keys_by_slide[slide_id].append(key)
                continue
            if text.strip():
                scan.unkeyed.append(f"{slide_id}:{name or 'unnamed-shape'}")
                continue
        if name.startswith(CHART_MARKER):
            scan.keys_by_slide[slide_id].extend(shape_extension_keys(shape))
        elif name.startswith(KEY_MARKER):
            key = key_from_shape(shape)
            if key is not None:
                scan.keys_by_slide[slide_id].append(key)


def _scan_table(shape: BaseShape, slide_id: str, scan: _Scan) -> None:
    frame = cast("GraphicFrame", shape)
    namespace = namespace_from_shape(frame, TABLE_MARKER)
    table = frame.table
    for row_index, row in enumerate(table.rows, start=1):
        for column_index, cell in enumerate(row.cells, start=1):
            key = table_cell_key(cell)
            if key is not None:
                scan.keys_by_slide[slide_id].append(key)
                continue
            if cell.text.strip():
                prefix = namespace if namespace is not None else f"{slide_id}:table"
                scan.unkeyed.append(f"{prefix}.r{row_index}.c{column_index}")


def _check_notes(slide: Slide, slide_ir: SlideIR, scan: _Scan) -> None:
    if not slide.has_notes_slide:
        return
    text = notes_text(slide) or ""
    if text.strip():
        scan.keys_by_slide[slide_ir.slide_id].append(f"{slide_ir.slide_id}.notes")


def _check_alt(slide: Slide, slide_ir: SlideIR, scan: _Scan) -> None:
    shapes = tuple(slide.shapes)
    for block in slide_ir.blocks:
        marker = _ALT_MARKERS.get(block.block_type)
        if marker is None:
            continue
        namespace = f"{slide_ir.slide_id}.{block.block_id}"
        alt = _alt_value(block)
        if not alt:
            scan.missing_alt.append(namespace)
            continue
        shape = next(
            (
                candidate
                for candidate in shapes
                if namespace_from_shape(candidate, marker) == namespace
            ),
            None,
        )
        if shape is None or not shape_description(shape).strip():
            scan.missing_alt.append(namespace)


def _alt_value(block: BlockIR) -> str:
    value = block.fields.get("alt")
    return value.strip() if isinstance(value, str) else ""


def _message(report: CoverageReport) -> str:
    findings: list[str] = []
    if report.missing_keys:
        findings.append(f"missing={list(report.missing_keys)}")
    if report.duplicate_keys:
        findings.append(f"duplicate={list(report.duplicate_keys)}")
    if report.unkeyed_visible:
        findings.append(f"unkeyed_visible={list(report.unkeyed_visible)}")
    if report.missing_alt:
        findings.append(f"missing_alt={list(report.missing_alt)}")
    detail = "; ".join(findings) if findings else "tanpa detail"
    return f"Coverage PPTX gagal: {detail}."
