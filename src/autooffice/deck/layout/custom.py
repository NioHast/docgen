"""Komposisi layout custom satu tingkat row pada grid 12 kolom.

Layout custom adalah satu-satunya layout yang memakai ``rows`` author. Compiler
menyimpan batas row tersebut di ``SlideIR.rows``; modul ini memvalidasi ulang
IR yang sudah dikompilasi (sabuk pengaman terakhir), mengukur setiap block
dengan primitive layout yang sama seperti preset, lalu menempatkan row dari kiri
ke kanan. Tidak ada posisi absolut, nested row, shrinking, atau tinggi tetap.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from autooffice.deck.blocks.registry import block_names
from autooffice.deck.layout.grid import (
    Grid,
    RowItem,
    SpanError,
    place_row,
    validate_row_spans,
    validate_span,
)
from autooffice.deck.layout.measure import (
    BlockMeasurement,
    measure_block,
    minimum_block_height,
)
from autooffice.deck.layout.spec import LayoutError, PlacedBlock, SlideLayout
from autooffice.deck.model.deck_ir import BlockIR, SlideIR
from autooffice.design.theme import Theme

CUSTOM_LAYOUT = "custom"

# Salinan kontrak schema: layout tidak mengimpor schema karena schema membaca
# registry layout. Pemeriksaan ini menjaga IR yang dibuat di luar compiler.
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
SLOT_FIELDS = frozenset({"slot", "slot_id"})
VALID_BLOCK_TYPES = frozenset(block_names())
_CAPTION_LEAF = "caption"
_LEAF_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    "text": ("text", "heading"),
    "bullets": ("item1.text",),
    "quote": ("text", "attribution"),
    "metric": ("value", "label", "caption"),
    "code": ("code",),
    "table": ("caption", "r1.c1", "h1"),
    "chart": ("title", "caption"),
    "image": ("caption",),
    "diagram": ("caption",),
}

KeyForBlock = Callable[[BlockIR, str | None], str]


class CustomLayoutError(LayoutError):
    """Rows atau block layout custom tidak memenuhi kontrak."""


@dataclass(frozen=True, slots=True)
class CustomOverflow:
    """Satu temuan overflow mentah dari planner custom."""

    block_id: str
    key: str
    kind: str
    estimated_overflow_emu: int


@dataclass(frozen=True, slots=True)
class CustomPlan:
    """Hasil planner custom: layout siap pakai dan temuan mentahnya."""

    layout: SlideLayout
    overflows: tuple[CustomOverflow, ...]


def plan_custom_slide(
    slide: SlideIR,
    theme: Theme,
    *,
    rows: Sequence[Sequence[BlockIR]] | None = None,
    grid: Grid | None = None,
    key_for_block: KeyForBlock | None = None,
) -> SlideLayout:
    """Tempatkan satu slide custom tanpa melempar overflow.

    ``rows`` dipakai bila pemanggil sudah memiliki batas row eksplisit. Bila
    tidak, row diambil dari ``SlideIR.rows`` hasil compiler. IR lama yang belum
    membawa rows memakai fallback span deterministik.
    """
    return plan_custom_slide_with_findings(
        slide,
        theme,
        rows=rows,
        grid=grid,
        key_for_block=key_for_block,
    ).layout


def plan_custom_slide_with_findings(
    slide: SlideIR,
    theme: Theme,
    *,
    rows: Sequence[Sequence[BlockIR]] | None = None,
    grid: Grid | None = None,
    key_for_block: KeyForBlock | None = None,
) -> CustomPlan:
    """Validasi, ukur, dan tempatkan seluruh row custom."""
    if slide.layout != CUSTOM_LAYOUT:
        raise CustomLayoutError(
            f"Slide '{slide.slide_id}' memakai layout '{slide.layout}', bukan '{CUSTOM_LAYOUT}'."
        )
    active_grid = Grid.from_theme(theme) if grid is None else grid
    explicit_rows = rows if rows is not None else _rows_from_ir(slide)
    custom_rows = validate_custom_rows(explicit_rows, slide_id=slide.slide_id)
    _validate_slide_block_coverage(slide, custom_rows)
    blocks_by_id = {block.block_id: block for row in custom_rows for block in row}
    resolve_key = key_for_block or _default_key_for_slide(slide.slide_id)

    boxes: list[PlacedBlock] = []
    overflows: list[CustomOverflow] = []
    top_emu = active_grid.content_top_emu
    for row_index, row in enumerate(custom_rows):
        reserved_height_emu = _reserved_custom_height(
            custom_rows[row_index + 1 :],
            active_grid,
            theme,
        )
        remaining_height_emu = active_grid.content_bottom_emu - top_emu
        row_budget_emu = max(0, remaining_height_emu - reserved_height_emu)
        items: list[RowItem] = []
        measurements: dict[str, BlockMeasurement] = {}
        for block in row:
            span = _span_value(block)
            width_emu = active_grid.span_width(span)
            measurement = measure_block(
                block,
                width_emu=width_emu,
                theme=theme,
                max_height_emu=row_budget_emu,
            )
            measurements[block.block_id] = measurement
            items.append(
                RowItem(
                    block_id=block.block_id,
                    span=span,
                    height_emu=measurement.height_emu,
                )
            )
        placement = place_row(active_grid, items, top_emu=top_emu)
        boxes.extend(placement.boxes)
        height_findings: set[str] = set()
        for box in placement.boxes:
            block = blocks_by_id[box.block_id]
            measurement = measurements[box.block_id]
            if measurement.overflow_width_emu > 0:
                overflows.append(
                    CustomOverflow(
                        block_id=block.block_id,
                        key=resolve_key(block, measurement.overflow_width_leaf),
                        kind="lebar",
                        estimated_overflow_emu=measurement.overflow_width_emu,
                    )
                )
            if measurement.overflow_height_emu > 0:
                overflows.append(
                    CustomOverflow(
                        block_id=block.block_id,
                        key=resolve_key(block, measurement.overflow_height_leaf),
                        kind="tinggi",
                        estimated_overflow_emu=measurement.overflow_height_emu,
                    )
                )
                height_findings.add(block.block_id)
        if placement.bottom_emu > active_grid.content_bottom_emu:
            estimated = placement.bottom_emu - active_grid.content_bottom_emu
            candidates = [box for box in placement.boxes if box.block_id not in height_findings]
            if candidates:
                overflow_box = max(
                    candidates,
                    key=lambda box: measurements[box.block_id].height_emu,
                )
                block = blocks_by_id[overflow_box.block_id]
                measurement = measurements[overflow_box.block_id]
                overflows.append(
                    CustomOverflow(
                        block_id=block.block_id,
                        key=resolve_key(
                            block,
                            measurement.overflow_height_leaf or measurement.height_leaf,
                        ),
                        kind="tinggi",
                        estimated_overflow_emu=estimated,
                    )
                )
        top_emu = placement.bottom_emu + active_grid.row_gap_emu

    overflow_keys = _overflow_keys(overflows)
    return CustomPlan(
        layout=SlideLayout(
            slide_id=slide.slide_id,
            boxes=tuple(boxes),
            overflow_keys=overflow_keys,
        ),
        overflows=tuple(overflows),
    )


def _reserved_custom_height(
    rows: Sequence[Sequence[BlockIR]],
    grid: Grid,
    theme: Theme,
) -> int:
    """Reservasi tinggi minimum row custom berikutnya."""
    reserved = 0
    for row in rows:
        if not row:
            continue
        heights = [
            minimum_block_height(
                block,
                width_emu=grid.span_width(_span_value(block)),
                theme=theme,
            )
            for block in row
        ]
        if heights:
            reserved += max(heights) + grid.row_gap_emu
    return reserved


def validate_custom_rows(
    rows: object,
    *,
    slide_id: str,
) -> tuple[tuple[BlockIR, ...], ...]:
    """Validasi rows custom non-kosong, satu tingkat, dan berisi BlockIR valid."""
    raw_rows = _as_rows(rows, slide_id=slide_id)
    seen_block_ids: dict[str, int] = {}
    validated: list[tuple[BlockIR, ...]] = []
    for row_index, raw_row in enumerate(raw_rows):
        row = _as_row(raw_row, row_index=row_index, slide_id=slide_id)
        if not row:
            raise CustomLayoutError(
                f"Row {row_index} pada slide '{slide_id}' layout custom minimal "
                "memiliki satu block."
            )
        spans: list[int] = []
        for block in row:
            _validate_custom_block(block, slide_id=slide_id, row_index=row_index)
            previous_row = seen_block_ids.get(block.block_id)
            if previous_row is not None:
                raise CustomLayoutError(
                    f"Block ID '{block.block_id}' duplikat pada slide '{slide_id}' layout "
                    f"custom; sudah dipakai di row {previous_row} dan row {row_index}."
                )
            seen_block_ids[block.block_id] = row_index
            spans.append(_span_value(block))
        try:
            validate_row_spans(spans)
        except SpanError as exc:
            raise CustomLayoutError(
                f"Row {row_index} pada slide '{slide_id}' layout custom: {exc}"
            ) from exc
        validated.append(row)
    return tuple(validated)


def rows_for_slide(
    slide: SlideIR,
) -> tuple[tuple[BlockIR, ...], ...]:
    """Kembalikan rows custom untuk satu slide IR."""
    if slide.layout != CUSTOM_LAYOUT:
        raise CustomLayoutError(
            f"Slide '{slide.slide_id}' memakai layout '{slide.layout}', bukan '{CUSTOM_LAYOUT}'."
        )
    return validate_custom_rows(_rows_from_ir(slide), slide_id=slide.slide_id)


def _validate_slide_block_coverage(
    slide: SlideIR,
    rows: tuple[tuple[BlockIR, ...], ...],
) -> None:
    row_blocks = tuple(block for row in rows for block in row)
    expected = tuple(block.block_id for block in slide.blocks)
    actual = tuple(block.block_id for block in row_blocks)
    if actual != expected:
        raise CustomLayoutError(
            f"Rows slide '{slide.slide_id}' layout custom tidak cocok dengan urutan block "
            f"slide; rows: {', '.join(actual) or '(kosong)'}; slide: "
            f"{', '.join(expected) or '(kosong)'}."
        )


def _rows_from_ir(slide: SlideIR) -> tuple[tuple[BlockIR, ...], ...]:
    if slide.rows:
        return _rows_from_block_ids(slide)
    if not slide.blocks:
        raise CustomLayoutError(
            f"Slide '{slide.slide_id}' layout custom tidak memiliki rows eksplisit di "
            "SlideIR; compiler wajib mengisi SlideIR.rows."
        )
    return _rows_from_spans(slide.blocks)


def _rows_from_block_ids(slide: SlideIR) -> tuple[tuple[BlockIR, ...], ...]:
    """Petakan block ID di ``SlideIR.rows`` kembali ke BlockIR."""
    blocks_by_id = {block.block_id: block for block in slide.blocks}
    missing = sorted(
        {block_id for row in slide.rows for block_id in row if block_id not in blocks_by_id}
    )
    if missing:
        raise CustomLayoutError(
            f"Rows slide '{slide.slide_id}' layout custom memuat block ID yang tidak ada "
            f"di blocks: {', '.join(missing)}."
        )
    return tuple(tuple(blocks_by_id[block_id] for block_id in row) for row in slide.rows)


def _rows_from_spans(blocks: Sequence[BlockIR]) -> tuple[tuple[BlockIR, ...], ...]:
    """Fallback untuk IR lama tanpa rows eksplisit.

    Row ditutup saat jumlah span mencapai 12 atau block berikutnya tidak muat.
    Fallback ini tidak dipakai compiler karena ``SlideIR.rows`` selalu terisi
    untuk slide custom hasil kompilasi.
    """
    rows: list[tuple[BlockIR, ...]] = []
    current: list[BlockIR] = []
    total = 0
    for block in blocks:
        span = _span_value(block)
        if current and (total == 12 or total + span > 12):
            rows.append(tuple(current))
            current = []
            total = 0
        current.append(block)
        total += span
    if current:
        rows.append(tuple(current))
    return tuple(rows)


def _as_rows(rows: object, *, slide_id: str) -> tuple[object, ...]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise CustomLayoutError(f"Rows slide '{slide_id}' layout custom harus berupa list row.")
    if not rows:
        raise CustomLayoutError(
            f"Slide '{slide_id}' layout custom harus memiliki minimal satu row."
        )
    return tuple(cast("Sequence[object]", rows))


def _as_row(raw_row: object, *, row_index: int, slide_id: str) -> tuple[BlockIR, ...]:
    if isinstance(raw_row, (str, bytes)) or not isinstance(raw_row, Sequence):
        raise CustomLayoutError(
            f"Row {row_index} pada slide '{slide_id}' layout custom harus berupa list block."
        )
    row: list[BlockIR] = []
    for item in cast("Sequence[object]", raw_row):
        if isinstance(item, BlockIR):
            row.append(item)
            continue
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            raise CustomLayoutError(
                f"Row {row_index} pada slide '{slide_id}' layout custom memuat nested "
                "row/column; hanya satu tingkat rows yang didukung."
            )
        raise CustomLayoutError(
            f"Row {row_index} pada slide '{slide_id}' layout custom hanya boleh berisi BlockIR."
        )
    return tuple(row)


def _validate_custom_block(block: BlockIR, *, slide_id: str, row_index: int) -> None:
    if not block.block_id:
        raise CustomLayoutError(
            f"Row {row_index} pada slide '{slide_id}' layout custom memuat block tanpa block_id."
        )
    if block.block_type not in VALID_BLOCK_TYPES:
        allowed = ", ".join(sorted(VALID_BLOCK_TYPES))
        raise CustomLayoutError(
            f"Block '{block.block_id}' pada slide '{slide_id}' memiliki type "
            f"'{block.block_type}' yang tidak dikenal; tipe yang valid: {allowed}."
        )
    forbidden = sorted(GEOMETRY_FIELDS.intersection(block.fields))
    if forbidden:
        raise CustomLayoutError(
            f"Block '{block.block_id}' pada slide '{slide_id}' layout custom memuat field "
            f"geometri terlarang: {', '.join(forbidden)}."
        )
    slots = sorted(SLOT_FIELDS.intersection(block.fields))
    if slots:
        raise CustomLayoutError(
            f"Block '{block.block_id}' pada slide '{slide_id}' layout custom memuat field "
            f"slot preset: {', '.join(slots)}."
        )
    _span_value(block)


def _span_value(block: BlockIR) -> int:
    span = block.span
    if span is None:
        raise CustomLayoutError(
            f"Block '{block.block_id}' pada layout custom wajib memiliki span 1 sampai 12."
        )
    if isinstance(span, bool) or not isinstance(span, int):
        raise CustomLayoutError(
            f"Block '{block.block_id}' pada layout custom memiliki span bukan bilangan bulat."
        )
    try:
        return validate_span(span)
    except SpanError as exc:
        raise CustomLayoutError(f"Block '{block.block_id}' pada layout custom: {exc}") from exc


def _default_key_for_slide(slide_id: str) -> KeyForBlock:
    def resolve(block: BlockIR, leaf: str | None) -> str:
        return _default_key(slide_id, block, leaf)

    return resolve


def _default_key(slide_id: str, block: BlockIR, leaf: str | None) -> str:
    if leaf is not None:
        return f"{slide_id}.{block.block_id}.{leaf}"
    candidates = _leaf_candidates(block)
    if not candidates:
        return f"{slide_id}.{block.block_id}"
    return f"{slide_id}.{block.block_id}.{candidates[0]}"


def _leaf_candidates(block: BlockIR) -> tuple[str, ...]:
    if block.block_type in {"image", "diagram"}:
        return (_CAPTION_LEAF,) if block.fields.get(_CAPTION_LEAF) else ()
    return _LEAF_CANDIDATES.get(block.block_type, ("text",))


def _overflow_keys(overflows: Sequence[CustomOverflow]) -> tuple[str, ...]:
    keys: list[str] = []
    for overflow in overflows:
        if overflow.key not in keys:
            keys.append(overflow.key)
    return tuple(keys)


__all__ = [
    "CUSTOM_LAYOUT",
    "GEOMETRY_FIELDS",
    "SLOT_FIELDS",
    "VALID_BLOCK_TYPES",
    "CustomLayoutError",
    "CustomOverflow",
    "CustomPlan",
    "plan_custom_slide",
    "plan_custom_slide_with_findings",
    "rows_for_slide",
    "validate_custom_rows",
]
