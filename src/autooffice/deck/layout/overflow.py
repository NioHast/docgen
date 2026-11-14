"""Perakitan ``LayoutPlan`` dan kebijakan overflow fail-hard.

Layout engine tidak melakukan shrink atau ellipsis. Perencanaan slide dan deck
dengan ``fail_on_overflow=False`` mengembalikan ``overflow_keys`` untuk
diagnostik; gate build default mengangkat :class:`LayoutOverflowError` bila
daftar tersebut tidak kosong.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from weakref import WeakKeyDictionary

from autooffice.deck.layout.custom import plan_custom_slide_with_findings
from autooffice.deck.layout.grid import Grid, RowItem, place_row
from autooffice.deck.layout.measure import (
    BlockMeasurement,
    measure_block,
    minimum_block_height,
)
from autooffice.deck.layout.registry import layout_registry
from autooffice.deck.layout.slot import SlotAssignment, require_layout, validate_slide
from autooffice.deck.layout.spec import (
    LayoutError,
    LayoutPlan,
    LayoutSpec,
    PlacedBlock,
    SlideLayout,
)
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyManifest, SlideIR
from autooffice.design.theme import Theme

CUSTOM_LAYOUT = "custom"


class LayoutOverflowError(LayoutError):
    """Satu atau lebih block tidak muat tanpa shrink atau ellipsis."""

    def __init__(
        self,
        plan: LayoutPlan,
        findings: Sequence[OverflowFinding] = (),
    ) -> None:
        self.plan = plan
        self.findings = tuple(findings)
        self.overflow_keys = (
            _finding_keys(self.findings) if self.findings else plan_overflow_keys(plan)
        )
        super().__init__(_overflow_message(self.findings, self.overflow_keys))


@dataclass(frozen=True, slots=True)
class OverflowFinding:
    """Satu temuan overflow dengan konteks slide, block, dan key."""

    slide_id: str
    block_id: str
    key: str
    kind: str
    estimated_overflow_emu: int

    @property
    def message(self) -> str:
        """Pesan ringkas yang menyebut slide, block, key, dan estimasi."""
        return (
            f"slide '{self.slide_id}', block '{self.block_id}', key '{self.key}': "
            f"overflow {self.kind} sekitar {self.estimated_overflow_emu} EMU"
        )


_FINDINGS_BY_PLAN: WeakKeyDictionary[LayoutPlan, tuple[OverflowFinding, ...]] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class _PlanResult:
    plan: LayoutPlan
    findings: tuple[OverflowFinding, ...]


def plan_slide(
    slide: SlideIR,
    spec: LayoutSpec,
    theme: Theme,
    *,
    keys: KeyManifest | None = None,
) -> SlideLayout:
    """Tempatkan satu slide dan kembalikan overflow keys tanpa raise."""
    layout, _ = _plan_slide(slide, spec, theme, keys)
    return layout


def build_layout_plan(
    deck: DeckIR,
    theme: Theme,
    *,
    layouts: Mapping[str, LayoutSpec] | None = None,
    fail_on_overflow: bool = True,
) -> LayoutPlan:
    """Bangun ``LayoutPlan`` dan gagal bila ada overflow.

    ``fail_on_overflow=False`` tersedia untuk inspeksi diagnostik dan tidak
    mengubah geometri rencana layout.
    """
    return plan_deck(
        deck,
        theme,
        layouts=layouts,
        fail_on_overflow=fail_on_overflow,
    )


def plan_deck(
    deck: DeckIR,
    theme: Theme,
    *,
    layouts: Mapping[str, LayoutSpec] | None = None,
    fail_on_overflow: bool = True,
) -> LayoutPlan:
    """Tempatkan seluruh slide secara deterministik.

    ``fail_on_overflow`` default ``True`` sesuai kebijakan build fail-hard.
    Set ``False`` hanya untuk inspeksi ``overflow_keys``; nilainya tidak
    mengubah geometri atau hasil rencana layout.
    """
    result = _build_plan(deck, theme, layouts=layouts)
    if fail_on_overflow and result.findings:
        raise LayoutOverflowError(result.plan, result.findings)
    return result.plan


def assert_no_overflow(plan: LayoutPlan) -> LayoutPlan:
    """Gagalkan rencana layout yang masih memiliki ``overflow_keys``.

    Rencana layout hasil perencanaan deck menyimpan findings aslinya, sehingga
    error tetap membawa slide, block, key, dan estimasi EMU.
    """
    keys = plan_overflow_keys(plan)
    if keys:
        raise LayoutOverflowError(plan, _FINDINGS_BY_PLAN.get(plan, ()))
    return plan


def plan_overflow_keys(plan: LayoutPlan) -> tuple[str, ...]:
    """Kumpulkan overflow key satu rencana layout dalam urutan slide dan slot."""
    keys: list[str] = []
    for slide in plan.slides:
        for key in slide.overflow_keys:
            if key not in keys:
                keys.append(key)
    return tuple(keys)


def _build_plan(
    deck: DeckIR,
    theme: Theme,
    *,
    layouts: Mapping[str, LayoutSpec] | None,
) -> _PlanResult:
    registry = dict(layout_registry() if layouts is None else layouts)
    grid = Grid.from_theme(theme)
    slides: list[SlideLayout] = []
    findings: list[OverflowFinding] = []
    for slide in deck.slides:
        if slide.layout == CUSTOM_LAYOUT:
            layout, slide_findings = _plan_custom_slide(slide, theme, deck.keys, grid=grid)
        else:
            spec = require_layout(registry, slide.layout)
            layout, slide_findings = _plan_slide(slide, spec, theme, deck.keys, grid=grid)
        slides.append(layout)
        findings.extend(slide_findings)
    plan = LayoutPlan(slides=tuple(slides))
    findings_tuple = tuple(findings)
    if findings_tuple:
        _FINDINGS_BY_PLAN[plan] = findings_tuple
    return _PlanResult(plan=plan, findings=findings_tuple)


def _plan_custom_slide(
    slide: SlideIR,
    theme: Theme,
    keys: KeyManifest | None,
    *,
    grid: Grid,
) -> tuple[SlideLayout, tuple[OverflowFinding, ...]]:
    key_map = _key_map(keys)
    custom = plan_custom_slide_with_findings(
        slide,
        theme,
        grid=grid,
        key_for_block=lambda block, leaf: _key_for_block(
            slide,
            block,
            key_map,
            keys,
            leaf=leaf,
        ),
    )
    findings = tuple(
        OverflowFinding(
            slide_id=slide.slide_id,
            block_id=overflow.block_id,
            key=overflow.key,
            kind=overflow.kind,
            estimated_overflow_emu=overflow.estimated_overflow_emu,
        )
        for overflow in custom.overflows
    )
    return custom.layout, findings


def _plan_slide(
    slide: SlideIR,
    spec: LayoutSpec,
    theme: Theme,
    keys: KeyManifest | None,
    *,
    grid: Grid | None = None,
) -> tuple[SlideLayout, tuple[OverflowFinding, ...]]:
    active_grid = Grid.from_theme(theme) if grid is None else grid
    assignments = validate_slide(slide, spec)
    assignments_by_slot = {assignment.slot.slot_id: assignment for assignment in assignments}
    blocks_by_id = {assignment.block.block_id: assignment.block for assignment in assignments}
    key_map = _key_map(keys)
    boxes: list[PlacedBlock] = []
    findings: list[OverflowFinding] = []
    top_emu = active_grid.content_top_emu
    present_rows = tuple(
        tuple(assignments_by_slot[slot_id] for slot_id in row if slot_id in assignments_by_slot)
        for row in spec.rows
    )

    for row_index, present in enumerate(present_rows):
        if not present:
            continue
        reserved_height_emu = _reserved_row_height(
            present_rows[row_index + 1 :],
            active_grid,
            theme,
        )
        remaining_height_emu = active_grid.content_bottom_emu - top_emu
        row_budget_emu = max(0, remaining_height_emu - reserved_height_emu)
        items: list[RowItem] = []
        measurements: dict[str, BlockMeasurement] = {}
        for assignment in present:
            span = assignment.slot.span
            width_emu = active_grid.span_width(span)
            measurement = measure_block(
                assignment.block,
                width_emu=width_emu,
                theme=theme,
                max_height_emu=row_budget_emu,
            )
            measurements[assignment.block.block_id] = measurement
            items.append(
                RowItem(
                    block_id=assignment.block.block_id,
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
                findings.append(
                    _finding(
                        slide,
                        block,
                        key_map,
                        keys,
                        kind="lebar",
                        estimated_overflow_emu=measurement.overflow_width_emu,
                        leaf=measurement.overflow_width_leaf,
                    )
                )
            if measurement.overflow_height_emu > 0:
                findings.append(
                    _finding(
                        slide,
                        block,
                        key_map,
                        keys,
                        kind="tinggi",
                        estimated_overflow_emu=measurement.overflow_height_emu,
                        leaf=measurement.overflow_height_leaf,
                    )
                )
                height_findings.add(box.block_id)
        if placement.bottom_emu > active_grid.content_bottom_emu:
            estimated = placement.bottom_emu - active_grid.content_bottom_emu
            candidates = [box for box in placement.boxes if box.block_id not in height_findings]
            if candidates:
                overflow_box = max(
                    candidates,
                    key=lambda box: measurements[box.block_id].height_emu,
                )
                measurement = measurements[overflow_box.block_id]
                findings.append(
                    _finding(
                        slide,
                        blocks_by_id[overflow_box.block_id],
                        key_map,
                        keys,
                        kind="tinggi",
                        estimated_overflow_emu=estimated,
                        leaf=measurement.overflow_height_leaf or measurement.height_leaf,
                    )
                )
        top_emu = placement.bottom_emu + active_grid.row_gap_emu

    overflow_keys = _finding_keys(findings)
    return (
        SlideLayout(
            slide_id=slide.slide_id,
            boxes=tuple(boxes),
            overflow_keys=overflow_keys,
        ),
        tuple(findings),
    )


def _reserved_row_height(
    rows: Sequence[Sequence[SlotAssignment]],
    grid: Grid,
    theme: Theme,
) -> int:
    """Reservasi tinggi minimum row-row berikutnya.

    Media pada row saat ini tidak boleh memakai seluruh sisa area sampai row
    setelahnya kehabisan ruang. Setiap row berikutnya menyumbang tinggi
    minimum block tertingginya ditambah satu row gap.
    """
    reserved = 0
    for row in rows:
        if not row:
            continue
        heights = [
            minimum_block_height(
                assignment.block,
                width_emu=grid.span_width(assignment.slot.span),
                theme=theme,
            )
            for assignment in row
        ]
        if heights:
            reserved += max(heights) + grid.row_gap_emu
    return reserved


def _finding_keys(findings: Sequence[OverflowFinding]) -> tuple[str, ...]:
    keys: list[str] = []
    for finding in findings:
        if finding.key not in keys:
            keys.append(finding.key)
    return tuple(keys)


def _overflow_message(
    findings: Sequence[OverflowFinding],
    keys: Sequence[str],
) -> str:
    if findings:
        detail = "; ".join(finding.message for finding in findings)
        return f"Layout overflow pada {len(keys)} key: {detail}."
    return f"Layout overflow pada key: {', '.join(keys)}."


def _key_map(manifest: KeyManifest | None) -> dict[tuple[str, str, str], str]:
    if manifest is None:
        return {}
    result: dict[tuple[str, str, str], str] = {}
    for binding in manifest.bindings:
        if binding.block_id is None:
            continue
        result[(binding.slide_id, binding.block_id, binding.leaf)] = binding.key
    return result


def _finding(
    slide: SlideIR,
    block: BlockIR,
    key_map: Mapping[tuple[str, str, str], str],
    manifest: KeyManifest | None,
    *,
    kind: str,
    estimated_overflow_emu: int,
    leaf: str | None = None,
) -> OverflowFinding:
    return OverflowFinding(
        slide_id=slide.slide_id,
        block_id=block.block_id,
        key=_key_for_block(slide, block, key_map, manifest, leaf=leaf),
        kind=kind,
        estimated_overflow_emu=max(0, estimated_overflow_emu),
    )


def _key_for_block(
    slide: SlideIR,
    block: BlockIR,
    key_map: Mapping[tuple[str, str, str], str],
    manifest: KeyManifest | None,
    *,
    leaf: str | None = None,
) -> str:
    candidates = (leaf,) if leaf is not None else _leaf_candidates(block)
    for candidate in candidates:
        key = key_map.get((slide.slide_id, block.block_id, candidate))
        if key is not None:
            return key
    if manifest is not None:
        for binding in manifest.bindings:
            if binding.slide_id == slide.slide_id and binding.block_id == block.block_id:
                return binding.key
    if not candidates:
        return f"{slide.slide_id}.{block.block_id}"
    return f"{slide.slide_id}.{block.block_id}.{candidates[0]}"


def _leaf_candidates(block: BlockIR) -> tuple[str, ...]:
    candidates: dict[str, tuple[str, ...]] = {
        "text": ("text", "heading"),
        "bullets": ("item1.text",),
        "quote": ("text", "attribution"),
        "metric": ("value", "label", "caption"),
        "code": ("code",),
        "table": ("caption", "r1.c1", "h1"),
        "chart": ("title", "caption"),
    }
    if block.block_type in {"image", "diagram"}:
        return ("caption",) if block.fields.get("caption") else ()
    return candidates.get(block.block_type, ("text",))
