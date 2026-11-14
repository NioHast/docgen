"""Validasi kontrak slot dan pemetaan block ke slot layout.

Layout preset menentukan slot, tipe block yang diterima, role, dan urutan row.
Author hanya mengisi block dengan ID slot; posisi tidak pernah berasal dari
field geometri authoring.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autooffice.deck.layout.spec import (
    LayoutError,
    LayoutSpec,
    SlotSpec,
    validate_layout_spec,
)
from autooffice.deck.layout.spec import (
    LayoutSpecError as LayoutSpecError,
)
from autooffice.deck.model.deck_ir import BlockIR, SlideIR

if TYPE_CHECKING:
    from collections.abc import Mapping


class SlotValidationError(LayoutError):
    """Block slide tidak cocok dengan kontrak slot layout."""


class UnknownLayoutError(LayoutError):
    """Layout yang diminta tidak ada di registry."""


# Salinan kontrak schema; layout tidak ingin mengimpor modul schema saat import
# karena schema sendiri membaca registry layout. Pemeriksaan ini adalah sabuk
# pengaman terakhir untuk IR yang dibuat di luar compiler.
_GEOMETRY_FIELDS = frozenset(
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


@dataclass(frozen=True, slots=True)
class SlotAssignment:
    """Satu block yang sudah divalidasi untuk mengisi satu slot."""

    slot: SlotSpec
    block: BlockIR


def validate_slide(slide: SlideIR, spec: LayoutSpec) -> tuple[SlotAssignment, ...]:
    """Validasi slide terhadap kontrak slot dan kembalikan assignment row-order."""
    validate_layout_spec(spec)
    if slide.layout != spec.layout_id:
        raise SlotValidationError(
            f"Slide '{slide.slide_id}' memakai layout '{slide.layout}', bukan '{spec.layout_id}'."
        )
    if slide.source is not None and not spec.accepts_source:
        raise SlotValidationError(
            f"Slide '{slide.slide_id}' memiliki source, tetapi layout "
            f"'{spec.layout_id}' tidak menerima source (accepts_source=False)."
        )

    slots_by_id = {slot.slot_id: slot for slot in spec.slots}
    blocks_by_id: dict[str, BlockIR] = {}
    for block in slide.blocks:
        if block.block_id in blocks_by_id:
            raise SlotValidationError(
                f"Block ID '{block.block_id}' duplikat pada slide '{slide.slide_id}'."
            )
        blocks_by_id[block.block_id] = block
        if block.block_id not in slots_by_id:
            raise SlotValidationError(
                f"Block '{block.block_id}' berada di luar slot layout "
                f"'{spec.layout_id}' pada slide '{slide.slide_id}'."
            )
        _validate_block_for_slot(slide, spec, slots_by_id[block.block_id], block)

    assignments: list[SlotAssignment] = []
    missing: list[str] = []
    for row in spec.rows:
        for slot_id in row:
            present_block = blocks_by_id.get(slot_id)
            slot = slots_by_id[slot_id]
            if present_block is None:
                if slot.required:
                    missing.append(slot_id)
                continue
            assignments.append(SlotAssignment(slot=slot, block=present_block))
    if missing:
        raise SlotValidationError(
            f"Slot wajib tidak terisi pada slide '{slide.slide_id}' layout "
            f"'{spec.layout_id}': {', '.join(missing)}."
        )
    for group in spec.min_one_of:
        if not any(slot_id in blocks_by_id for slot_id in group):
            raise LayoutSpecError(
                f"Slide '{slide.slide_id}' layout '{spec.layout_id}' tidak mengisi "
                f"satu pun slot dari min_one_of group {group!r}."
            )
    return tuple(assignments)


def assign_slide_blocks(slide: SlideIR, spec: LayoutSpec) -> tuple[SlotAssignment, ...]:
    """Alias eksplisit untuk :func:`validate_slide`."""
    return validate_slide(slide, spec)


def _validate_block_for_slot(
    slide: SlideIR,
    spec: LayoutSpec,
    slot: SlotSpec,
    block: BlockIR,
) -> None:
    if block.block_type not in slot.block_types:
        allowed = ", ".join(slot.block_types)
        raise SlotValidationError(
            f"Block '{block.block_id}' bertipe '{block.block_type}' tidak diterima "
            f"slot '{slot.slot_id}'; tipe yang diizinkan: {allowed}."
        )
    if slot.chart_kind is not None and block.block_type == "chart":
        actual_kind = block.fields.get("kind")
        if actual_kind != slot.chart_kind:
            raise LayoutSpecError(
                f"Slide '{slide.slide_id}' block '{block.block_id}' pada slot "
                f"'{slot.slot_id}' memakai chart kind {actual_kind!r}; slot "
                f"mensyaratkan chart kind {slot.chart_kind!r}."
            )
    if slot.role is not None and block.role != slot.role:
        raise SlotValidationError(
            f"Role block '{block.block_id}' adalah {block.role!r}; slot "
            f"'{slot.slot_id}' membutuhkan role {slot.role!r} pada slide "
            f"'{slide.slide_id}'."
        )
    if block.span is not None:
        raise SlotValidationError(
            f"Block '{block.block_id}' tidak boleh memiliki span pada layout "
            f"preset '{spec.layout_id}'."
        )
    forbidden = sorted(_GEOMETRY_FIELDS.intersection(block.fields))
    if forbidden:
        raise SlotValidationError(
            f"Block '{block.block_id}' pada slide '{slide.slide_id}' memuat field "
            f"geometri terlarang: {', '.join(forbidden)}."
        )


def require_layout(specs: Mapping[str, LayoutSpec], layout_id: str) -> LayoutSpec:
    """Ambil layout dari registry atau gagalkan dengan error terstruktur."""
    spec = specs.get(layout_id)
    if spec is None:
        available = ", ".join(sorted(specs)) or "(kosong)"
        raise UnknownLayoutError(
            f"Layout '{layout_id}' tidak ada di registry. Tersedia: {available}."
        )
    return spec
