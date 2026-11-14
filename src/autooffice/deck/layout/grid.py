"""Geometri grid 12 kolom dan primitive penempatan row.

Semua angka berasal dari :class:`autooffice.design.theme.GridTokens`. Modul ini
tidak menerima koordinat authoring; satu-satunya input geometri adalah urutan
row dan ``span`` 1 sampai 12.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from autooffice.deck.layout.spec import (
    LAYOUT_COLUMNS,
    MAX_SPAN,
    MIN_SPAN,
    LayoutError,
    PlacedBlock,
)
from autooffice.design.theme import GridTokens, Theme


class GridError(LayoutError):
    """Token grid atau geometri kanvas tidak valid."""


class SpanError(LayoutError):
    """Nilai span atau komposisi span satu row tidak valid."""


class RowError(LayoutError):
    """Urutan item row tidak valid."""


def validate_span(span: int) -> int:
    """Validasi satu span dan kembalikan nilainya."""
    if not isinstance(span, int):
        raise SpanError(f"Span harus bilangan bulat, bukan {type(span).__name__}.")
    if not MIN_SPAN <= span <= MAX_SPAN:
        raise SpanError(f"Span harus {MIN_SPAN} sampai {MAX_SPAN}, bukan {span}.")
    return span


def validate_row_spans(spans: Sequence[int]) -> int:
    """Validasi seluruh span satu row dan kembalikan jumlah span."""
    if not spans:
        raise RowError("Row minimal memiliki satu block.")
    total = 0
    for span in spans:
        total += validate_span(span)
    if total > LAYOUT_COLUMNS:
        raise SpanError(f"Jumlah span dalam satu row adalah {total}; maksimal {LAYOUT_COLUMNS}.")
    return total


@dataclass(frozen=True, slots=True)
class Grid:
    """Grid 12 kolom yang sudah dihitung dari token theme."""

    columns: int
    gutter_emu: int
    margin_left_emu: int
    margin_right_emu: int
    margin_top_emu: int
    margin_bottom_emu: int
    row_gap_emu: int
    slide_width_emu: int
    slide_height_emu: int

    def __post_init__(self) -> None:
        if self.columns != LAYOUT_COLUMNS:
            raise GridError(f"Grid layout harus {LAYOUT_COLUMNS} kolom, bukan {self.columns}.")
        if self.gutter_emu < 0:
            raise GridError("Gutter grid tidak boleh negatif.")
        if min(self.margin_left_emu, self.margin_right_emu) < 0:
            raise GridError("Margin horizontal tidak boleh negatif.")
        if min(self.margin_top_emu, self.margin_bottom_emu) < 0:
            raise GridError("Margin vertikal tidak boleh negatif.")
        if self.content_width_emu <= 0:
            raise GridError("Lebar konten slide harus positif; periksa margin dan lebar slide.")
        if self.content_height_emu <= 0:
            raise GridError("Tinggi konten slide harus positif; periksa margin dan tinggi slide.")
        if self.column_width_emu <= 0:
            raise GridError("Lebar kolom harus positif; periksa gutter dan lebar konten.")
        if self.row_gap_emu < 0:
            raise GridError("Row gap tidak boleh negatif.")

    @classmethod
    def from_theme(cls, theme: Theme) -> Grid:
        """Bentuk grid dari token grid theme yang sudah di-resolve."""
        return cls.from_tokens(theme.grid)

    @classmethod
    def from_tokens(cls, tokens: GridTokens) -> Grid:
        """Bentuk grid dari ``GridTokens`` tanpa membaca theme lain."""
        return cls(
            columns=tokens.columns,
            gutter_emu=tokens.gutter_emu,
            margin_left_emu=tokens.margin_left_emu,
            margin_right_emu=tokens.margin_right_emu,
            margin_top_emu=tokens.margin_top_emu,
            margin_bottom_emu=tokens.margin_bottom_emu,
            row_gap_emu=tokens.row_gap_emu,
            slide_width_emu=tokens.slide_width_emu,
            slide_height_emu=tokens.slide_height_emu,
        )

    @property
    def content_left_emu(self) -> int:
        """Batas kiri area konten."""
        return self.margin_left_emu

    @property
    def content_top_emu(self) -> int:
        """Batas atas area konten."""
        return self.margin_top_emu

    @property
    def content_width_emu(self) -> int:
        """Lebar area konten di antara margin kiri dan kanan."""
        return self.slide_width_emu - self.margin_left_emu - self.margin_right_emu

    @property
    def content_height_emu(self) -> int:
        """Tinggi area konten di antara margin atas dan bawah."""
        return self.slide_height_emu - self.margin_top_emu - self.margin_bottom_emu

    @property
    def content_right_emu(self) -> int:
        """Batas kanan area konten."""
        return self.margin_left_emu + self.content_width_emu

    @property
    def content_bottom_emu(self) -> int:
        """Batas bawah area konten."""
        return self.margin_top_emu + self.content_height_emu

    @property
    def column_width_emu(self) -> int:
        """Lebar satu kolom dari rumus kontrak.

        Nilai token kontrak habis dibagi 12. Pembagian eksak dipakai agar
        ``span_width(12)`` selalu sama dengan lebar konten, lalu hasil akhir
        dibulatkan ke EMU bulat.
        """
        remaining = self.content_width_emu - (self.columns - 1) * self.gutter_emu
        return round(Fraction(remaining, self.columns))

    def span_width(self, span: int) -> int:
        """Hitung lebar ``span`` kolom.

        ``span_width(span) = span * column_width + (span - 1) * gutter``.
        """
        valid_span = validate_span(span)
        numerator = (
            valid_span * self.content_width_emu + (valid_span - self.columns) * self.gutter_emu
        )
        return round(Fraction(numerator, self.columns))

    def column_left(self, start_column: int) -> int:
        """Hitung batas kiri kolom 0-based di dalam area konten."""
        if not isinstance(start_column, int):
            raise GridError(
                f"Kolom awal harus bilangan bulat, bukan {type(start_column).__name__}."
            )
        if not 0 <= start_column <= self.columns:
            raise GridError(f"Kolom awal harus 0 sampai {self.columns}, bukan {start_column}.")
        if start_column == self.columns:
            return self.content_right_emu
        numerator = start_column * (self.content_width_emu + self.gutter_emu)
        return self.content_left_emu + round(Fraction(numerator, self.columns))

    def row_width(self, spans: Sequence[int]) -> int:
        """Hitung lebar total block dan gutter dalam satu row."""
        validate_row_spans(spans)
        return sum(self.span_width(span) for span in spans) + (len(spans) - 1) * self.gutter_emu


def span_width(theme: Theme, span: int) -> int:
    """Hitung ``span_width(span)`` langsung dari token grid theme."""
    return Grid.from_theme(theme).span_width(span)


@dataclass(frozen=True, slots=True)
class RowItem:
    """Satu block yang akan ditempatkan pada row."""

    block_id: str
    span: int
    height_emu: int

    def __post_init__(self) -> None:
        if not self.block_id:
            raise RowError("Block ID pada row tidak boleh kosong.")
        validate_span(self.span)
        if self.height_emu < 0:
            raise RowError(f"Tinggi block '{self.block_id}' tidak boleh negatif.")


@dataclass(frozen=True, slots=True)
class RowPlacement:
    """Hasil penempatan satu row beserta tinggi barisnya."""

    boxes: tuple[PlacedBlock, ...]
    top_emu: int
    height_emu: int
    bottom_emu: int


def place_row(
    grid: Grid,
    items: Sequence[RowItem],
    *,
    top_emu: int,
    stretch: bool = True,
) -> RowPlacement:
    """Tempatkan item row dari kiri ke kanan.

    Tinggi row adalah tinggi konten tertinggi. Bila ``stretch`` benar, setiap
    ``PlacedBlock`` memakai tinggi row tersebut; bila salah, tinggi natural
    masing-masing block dipertahankan.
    """
    if top_emu < 0:
        raise RowError("Posisi atas row tidak boleh negatif.")
    if not items:
        raise RowError("Row minimal memiliki satu block.")
    seen: set[str] = set()
    for item in items:
        if item.block_id in seen:
            raise RowError(f"Block ID '{item.block_id}' duplikat dalam satu row.")
        seen.add(item.block_id)

    validate_row_spans([item.span for item in items])
    row_height = max(item.height_emu for item in items)
    boxes: list[PlacedBlock] = []
    start_column = 0
    for item in items:
        left_emu = grid.column_left(start_column)
        width_emu = grid.span_width(item.span)
        height_emu = row_height if stretch else item.height_emu
        boxes.append(
            PlacedBlock(
                block_id=item.block_id,
                left_emu=left_emu,
                top_emu=top_emu,
                width_emu=width_emu,
                height_emu=height_emu,
            )
        )
        start_column += item.span
    return RowPlacement(
        boxes=tuple(boxes),
        top_emu=top_emu,
        height_emu=row_height,
        bottom_emu=top_emu + row_height,
    )
