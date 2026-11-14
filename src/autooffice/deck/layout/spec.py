"""Kontrak slot, layout, penempatan block, dan layout plan."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlotSpec:
    """Satu slot preset beserta tipe block yang boleh mengisinya."""

    slot_id: str
    required: bool
    block_types: tuple[str, ...]
    role: str | None = None


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    """Kontrak layout preset berupa slot dan susunan baris slot."""

    layout_id: str
    slots: tuple[SlotSpec, ...]
    rows: tuple[tuple[str, ...], ...]
    accepts_source: bool


@dataclass(frozen=True, slots=True)
class PlacedBlock:
    """Block yang sudah diposisikan layout engine pada satu slide."""

    block_id: str
    left_emu: int
    top_emu: int
    width_emu: int
    height_emu: int


@dataclass(frozen=True, slots=True)
class SlideLayout:
    """Hasil penempatan block dan temuan overflow untuk satu slide."""

    slide_id: str
    boxes: tuple[PlacedBlock, ...]
    overflow_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LayoutPlan:
    """Hasil layout engine: penempatan seluruh block untuk satu build."""

    slides: tuple[SlideLayout, ...]
