"""Kontrak slot, layout, penempatan block, dan layout plan."""

from collections import Counter
from dataclasses import dataclass

from autooffice.errors import AutoOfficeError

LAYOUT_COLUMNS = 12
MIN_SPAN = 1
MAX_SPAN = LAYOUT_COLUMNS
CHART_KINDS = ("bar", "line", "donut")


class LayoutError(AutoOfficeError, ValueError):
    """Error dasar layout engine yang bisa ditampilkan ke pengguna."""


class LayoutSpecError(LayoutError):
    """Definisi ``LayoutSpec`` tidak konsisten."""


@dataclass(frozen=True, slots=True)
class SlotSpec:
    """Satu slot preset beserta tipe block yang boleh mengisinya.

    ``span`` adalah lebar slot dalam kolom grid 12 kolom dan hanya berlaku
    untuk layout preset. Layout custom memakai ``BlockIR.span``.
    ``chart_kind`` mengikat block chart pada slot preset ke kind ``bar``,
    ``line``, atau ``donut``; ``None`` berarti tidak membatasi kind.
    """

    slot_id: str
    required: bool
    block_types: tuple[str, ...]
    role: str | None = None
    span: int = 1
    chart_kind: str | None = None


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    """Kontrak layout preset berupa slot dan susunan baris slot.

    ``min_one_of`` menyatakan grup slot opsional yang harus diisi minimal satu
    anggotanya pada setiap slide. Setiap grup tidak kosong, seluruh slot ID-nya
    harus ada di ``slots``, dan satu slot hanya boleh muncul di satu grup.
    Slot di dalam grup tidak otomatis menjadi ``required``.
    """

    layout_id: str
    slots: tuple[SlotSpec, ...]
    rows: tuple[tuple[str, ...], ...]
    accepts_source: bool
    min_one_of: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        validate_layout_spec(self)


def validate_layout_spec(spec: LayoutSpec) -> None:
    """Validasi otoritas ``slots``, ``span``/``chart_kind`` slot, dan ``rows``."""
    if not spec.layout_id:
        raise LayoutSpecError("LayoutSpec.layout_id tidak boleh kosong.")
    if not spec.rows:
        raise LayoutSpecError(f"Layout '{spec.layout_id}' harus memiliki minimal satu row.")
    if not spec.slots:
        raise LayoutSpecError(f"Layout '{spec.layout_id}' tidak memiliki slot.")
    if not isinstance(spec.accepts_source, bool):
        raise LayoutSpecError(f"Layout '{spec.layout_id}' memiliki accepts_source yang bukan bool.")

    slot_ids: list[str] = []
    for slot in spec.slots:
        if not slot.slot_id:
            raise LayoutSpecError(f"Layout '{spec.layout_id}' memiliki slot tanpa slot_id.")
        if not slot.block_types:
            raise LayoutSpecError(
                f"Slot '{slot.slot_id}' pada layout '{spec.layout_id}' "
                "harus menerima minimal satu block type."
            )
        for block_type in slot.block_types:
            if not block_type:
                raise LayoutSpecError(
                    f"Slot '{slot.slot_id}' pada layout '{spec.layout_id}' "
                    "memiliki block type kosong."
                )
        if slot.role is not None and not slot.role:
            raise LayoutSpecError(
                f"Slot '{slot.slot_id}' pada layout '{spec.layout_id}' memiliki role kosong."
            )
        if isinstance(slot.span, bool) or not isinstance(slot.span, int):
            raise LayoutSpecError(
                f"Slot '{slot.slot_id}' pada layout '{spec.layout_id}' memiliki span "
                f"{slot.span!r}; span harus bilangan bulat {MIN_SPAN} sampai {MAX_SPAN}."
            )
        if not MIN_SPAN <= slot.span <= MAX_SPAN:
            raise LayoutSpecError(
                f"Slot '{slot.slot_id}' pada layout '{spec.layout_id}' memiliki span "
                f"{slot.span}; span harus {MIN_SPAN} sampai {MAX_SPAN}."
            )
        if slot.chart_kind is not None and slot.chart_kind not in CHART_KINDS:
            allowed = ", ".join(CHART_KINDS)
            raise LayoutSpecError(
                f"Slot '{slot.slot_id}' pada layout '{spec.layout_id}' memiliki "
                f"chart_kind {slot.chart_kind!r}; chart_kind harus salah satu dari "
                f"{allowed}, atau None."
            )
        slot_ids.append(slot.slot_id)

    duplicate_slots = sorted(slot_id for slot_id, count in Counter(slot_ids).items() if count > 1)
    if duplicate_slots:
        raise LayoutSpecError(
            f"Layout '{spec.layout_id}' memiliki slot duplikat: {', '.join(duplicate_slots)}."
        )

    declared = set(slot_ids)
    grouped_ids: list[str] = []
    for group_index, group in enumerate(spec.min_one_of):
        if not group:
            raise LayoutSpecError(
                f"Layout '{spec.layout_id}' memiliki min_one_of group {group_index} yang kosong."
            )
        for slot_id in group:
            if not slot_id:
                raise LayoutSpecError(
                    f"Layout '{spec.layout_id}' memiliki slot_id kosong di "
                    f"min_one_of group {group_index}."
                )
        unknown = sorted(set(group) - declared)
        if unknown:
            raise LayoutSpecError(
                f"Layout '{spec.layout_id}' memiliki min_one_of group {group_index} "
                f"yang merujuk slot tidak dikenal: {', '.join(unknown)}."
            )
        grouped_ids.extend(group)

    duplicate_grouped = sorted(
        slot_id for slot_id, count in Counter(grouped_ids).items() if count > 1
    )
    if duplicate_grouped:
        raise LayoutSpecError(
            f"Layout '{spec.layout_id}' memiliki slot duplikat di min_one_of: "
            f"{', '.join(duplicate_grouped)}."
        )

    row_ids: list[str] = []
    for row_index, row in enumerate(spec.rows):
        if not row:
            raise LayoutSpecError(
                f"Row {row_index} pada layout '{spec.layout_id}' tidak boleh kosong."
            )
        if len(row) > LAYOUT_COLUMNS:
            raise LayoutSpecError(
                f"Row {row_index} pada layout '{spec.layout_id}' memiliki "
                f"{len(row)} slot; maksimal {LAYOUT_COLUMNS} kolom."
            )
        for slot_id in row:
            if not slot_id:
                raise LayoutSpecError(
                    f"Row {row_index} pada layout '{spec.layout_id}' memiliki slot_id kosong."
                )
            row_ids.append(slot_id)

    duplicate_rows = sorted(slot_id for slot_id, count in Counter(row_ids).items() if count > 1)
    if duplicate_rows:
        raise LayoutSpecError(
            f"Layout '{spec.layout_id}' menempatkan slot lebih dari sekali: "
            f"{', '.join(duplicate_rows)}."
        )

    referenced = set(row_ids)
    unknown = sorted(referenced - declared)
    if unknown:
        raise LayoutSpecError(
            f"Layout '{spec.layout_id}' memiliki row yang merujuk slot tidak dikenal: "
            f"{', '.join(unknown)}."
        )
    missing = sorted(declared - referenced)
    if missing:
        raise LayoutSpecError(
            f"Layout '{spec.layout_id}' tidak menempatkan slot di rows: {', '.join(missing)}."
        )

    slots_by_id = {slot.slot_id: slot for slot in spec.slots}
    for row_index, row in enumerate(spec.rows):
        total = sum(slots_by_id[slot_id].span for slot_id in row)
        if total > LAYOUT_COLUMNS:
            raise LayoutSpecError(
                f"Jumlah span row {row_index} pada layout '{spec.layout_id}' adalah "
                f"{total}; maksimal {LAYOUT_COLUMNS} kolom."
            )


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


@dataclass(frozen=True, slots=True, weakref_slot=True)
class LayoutPlan:
    """Hasil layout engine: penempatan seluruh block untuk satu build."""

    slides: tuple[SlideLayout, ...]
