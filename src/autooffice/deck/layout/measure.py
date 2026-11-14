"""Pengukuran teks dan block memakai metrik font yang dibundel.

Pengukuran deterministik dan offline. Tidak ada browser, COM, autofit, shrink,
atau ellipsis. Line-height, tracking, padding, dan ukuran font berasal dari
``Theme``; ukuran font yang dipakai adalah ukuran asli, bukan ukuran turunan.

Ukuran dan bobot role disalin dari renderer PPTX supaya layout dan render
memakai kontrak tipografi yang sama. Code diukur dengan advance monospace
konservatif karena family code bukan Plus Jakarta Sans.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from PIL import ImageFont

from autooffice.deck.layout.spec import LayoutError
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.fonts import font_path
from autooffice.design.theme import Theme

_EMU_PER_POINT = 12700
_FONT_PIXEL_SIZE = 128
_TITLE_ROLES = frozenset({"display", "title"})
_SMALL_ROLES = frozenset({"caption", "label", "kicker"})
_ROLE_WEIGHTS = {
    "display": 800,
    "title": 700,
    "lead": 600,
    "body": 400,
    "caption": 400,
    "label": 600,
    "kicker": 700,
}
_FONT_BY_WEIGHT: tuple[tuple[int, str], ...] = (
    (400, "PlusJakartaSans-Regular.ttf"),
    (600, "PlusJakartaSans-SemiBold.ttf"),
    (700, "PlusJakartaSans-Bold.ttf"),
    (800, "PlusJakartaSans-ExtraBold.ttf"),
)

# Cascadia Mono/Consolas berada di sekitar 0.55-0.60 em. Nilai konservatif ini
# sengaja dilebihkan supaya code yang mendekati lebar slot tidak lolos.
_CODE_ADVANCE_EM = 0.62
_CODE_TAB_WIDTH = 4

# Kontrak gutter nomor baris dengan renderer PPTX:
# ``autooffice.deck.render.pptx.textbox.render_code_block`` mengukur teks nomor
# terlebar memakai ``measure_code_text`` lalu menambahkan
# ``theme.spacing.sm_emu`` sebagai jarak. Layout memakai fungsi
# ``line_number_gutter_width`` dan ``code_text_width`` di bawah sebagai sumber
# tunggal; salinan renderer harus tetap identik (dijaga test paritas).


class MeasurementError(LayoutError):
    """Parameter pengukuran tidak valid."""


@dataclass(frozen=True, slots=True)
class TextMeasurement:
    """Hasil pengukuran satu blok teks."""

    width_emu: int
    height_emu: int
    line_count: int
    overflow_width_emu: int


@dataclass(frozen=True, slots=True)
class BlockMeasurement:
    """Tinggi satu block beserta temuan overflow horizontal dan vertikal."""

    width_emu: int
    height_emu: int
    line_count: int
    overflow_width_emu: int
    overflow_height_emu: int = 0
    overflow_width_leaf: str | None = None
    overflow_height_leaf: str | None = None
    height_leaf: str | None = None


@dataclass(frozen=True, slots=True)
class _TextPart:
    """Satu bagian teks block beserta leaf key-nya."""

    leaf: str
    measurement: TextMeasurement


def measure_text(
    text: str,
    *,
    available_width_emu: int,
    theme: Theme,
    font_size_pt: float | None = None,
    weight: int = 400,
    line_height: float | None = None,
    tracking_em: float | None = None,
) -> TextMeasurement:
    """Ukur teks dengan word wrapping pada lebar yang tersedia.

    Teks yang tidak muat tetap dilaporkan melalui ``overflow_width_emu``;
    fungsi ini tidak memotong, mengecilkan font, atau menambahkan ellipsis.
    """
    if available_width_emu <= 0:
        raise MeasurementError("Lebar pengukuran teks harus positif.")
    size_pt = theme.typography.body_pt if font_size_pt is None else font_size_pt
    if size_pt <= 0:
        raise MeasurementError("Ukuran font pengukuran harus positif.")
    effective_line_height = theme.typography.line_height if line_height is None else line_height
    if effective_line_height <= 0:
        raise MeasurementError("Line-height pengukuran harus positif.")
    effective_tracking = theme.typography.tracking_em if tracking_em is None else tracking_em

    font = _load_font(_font_file_for_weight(weight))
    font_size_emu = _round_emu(size_pt * _EMU_PER_POINT)
    line_height_emu = max(1, _round_emu(font_size_emu * effective_line_height))
    scale = font_size_emu / _FONT_PIXEL_SIZE
    tracking_emu = effective_tracking * font_size_emu

    lines, overflow_width_emu = _wrap_text(
        text,
        width_emu=available_width_emu,
        font=font,
        scale=scale,
        tracking_emu=tracking_emu,
    )
    widths = tuple(
        _line_width_emu(line, font=font, scale=scale, tracking_emu=tracking_emu) for line in lines
    )
    content_width = max(widths, default=0)
    return TextMeasurement(
        width_emu=content_width,
        height_emu=len(lines) * line_height_emu,
        line_count=len(lines),
        overflow_width_emu=max(overflow_width_emu, content_width - available_width_emu),
    )


def measure_code_text(
    text: str,
    *,
    available_width_emu: int,
    theme: Theme,
    font_size_pt: float | None = None,
    line_height: float | None = None,
) -> TextMeasurement:
    """Ukur code dengan advance monospace dan preservasi spasi.

    Setiap baris eksplisit dipecah per karakter bila melebihi kapasitas slot.
    Spasi di awal dan spasi ganda ikut dihitung; tab diperluas ke tab stop
    empat kolom. Tidak ada glyph monospace yang dibundel, jadi advance diambil
    konservatif dari ukuran font.
    """
    if available_width_emu <= 0:
        raise MeasurementError("Lebar pengukuran teks harus positif.")
    size_pt = theme.code.size_pt if font_size_pt is None else font_size_pt
    size_pt = max(size_pt, theme.typography.minimum_pt)
    if size_pt <= 0:
        raise MeasurementError("Ukuran font pengukuran harus positif.")
    effective_line_height = theme.code.line_height if line_height is None else line_height
    if effective_line_height <= 0:
        raise MeasurementError("Line-height pengukuran harus positif.")

    font_size_emu = size_pt * _EMU_PER_POINT
    line_height_emu = max(1, _round_emu(font_size_emu * effective_line_height))
    character_width_emu = font_size_emu * _CODE_ADVANCE_EM
    capacity = max(1, int(available_width_emu // character_width_emu))

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    line_count = 0
    max_width_emu = 0
    for raw_line in normalized.split("\n"):
        line = raw_line.expandtabs(_CODE_TAB_WIDTH)
        chunks = _code_chunks(line, capacity)
        line_count += len(chunks)
        for chunk in chunks:
            width = _round_emu(len(chunk) * character_width_emu)
            max_width_emu = max(max_width_emu, width)
    return TextMeasurement(
        width_emu=max_width_emu,
        height_emu=max(1, line_count) * line_height_emu,
        line_count=max(1, line_count),
        overflow_width_emu=max(0, max_width_emu - available_width_emu),
    )


def code_line_count(code: str) -> int:
    """Hitung baris logis code; baris kosong tetap mendapat nomor.

    Nilai ini sama dengan jumlah nomor baris yang digambar renderer PPTX.
    """
    normalized = code.replace("\r\n", "\n").replace("\r", "\n")
    return max(1, len(normalized.split("\n")))


def line_number_gutter_width(
    line_count: int,
    *,
    theme: Theme,
    available_width_emu: int,
) -> int:
    """Lebar gutter nomor baris dari teks nomor terlebar.

    Kontrak dengan renderer PPTX: gutter memakai advance monospace yang sama
    dengan :func:`measure_code_text`, dan lebarnya adalah hasil pengukuran
    string nomor terlebar, bukan konstanta tetap. Renderer menambahkan
    ``theme.spacing.sm_emu`` sebagai jarak setelah gutter.
    """
    widest = str(max(1, line_count))
    measurement = measure_code_text(
        widest,
        available_width_emu=max(1, available_width_emu),
        theme=theme,
    )
    return max(1, measurement.width_emu)


def code_text_width(
    code: str,
    *,
    inner_width_emu: int,
    theme: Theme,
    line_numbers: bool,
) -> int:
    """Lebar teks code setelah gutter nomor baris dan jarak gutter.

    ``inner_width_emu`` adalah lebar slot setelah padding kartu. Bila nomor
    baris aktif, lebar dikurangi gutter dan ``theme.spacing.sm_emu`` persis
    seperti kotak code pada renderer PPTX. Default renderer untuk
    ``line_numbers`` adalah ``True``.
    """
    if not line_numbers:
        return max(1, inner_width_emu)
    gutter_width = line_number_gutter_width(
        code_line_count(code),
        theme=theme,
        available_width_emu=inner_width_emu,
    )
    return max(1, inner_width_emu - gutter_width - theme.spacing.sm_emu)


def measure_block(
    block: BlockIR,
    *,
    width_emu: int,
    theme: Theme,
    max_height_emu: int | None = None,
) -> BlockMeasurement:
    """Ukur tinggi satu block pada lebar slot yang diberikan.

    ``max_height_emu`` hanya dipakai media (``image``, ``chart``, ``diagram``):
    media memakai mode contain dan tinggi yang tersedia, bukan tinggi natural
    tetap. Block non-media mengabaikan batas ini dan tetap dilaporkan lewat
    overflow bila tidak muat.
    """
    if width_emu <= 0:
        raise MeasurementError(f"Lebar slot block '{block.block_id}' harus positif.")
    block_type = block.block_type
    if block_type == "text":
        return _measure_text_block(block, width_emu=width_emu, theme=theme)
    if block_type == "bullets":
        return _measure_bullets_block(block, width_emu=width_emu, theme=theme)
    if block_type == "quote":
        return _measure_quote_block(block, width_emu=width_emu, theme=theme)
    if block_type == "metric":
        return _measure_metric_block(block, width_emu=width_emu, theme=theme)
    if block_type == "code":
        return _measure_code_block(block, width_emu=width_emu, theme=theme)
    if block_type == "table":
        return _measure_table_block(block, width_emu=width_emu, theme=theme)
    if block_type in {"image", "diagram", "chart"}:
        return _measure_media_block(
            block,
            width_emu=width_emu,
            theme=theme,
            max_height_emu=max_height_emu,
        )
    if block_type == "divider":
        return BlockMeasurement(
            width_emu=width_emu,
            height_emu=theme.spacing.divider_emu,
            line_count=0,
            overflow_width_emu=0,
        )
    if block_type == "spacer":
        size = _as_text(block.fields.get("size")) or "md"
        height = {
            "sm": theme.spacing.sm_emu,
            "md": theme.spacing.md_emu,
            "lg": theme.spacing.lg_emu,
        }.get(size, theme.spacing.md_emu)
        return BlockMeasurement(
            width_emu=width_emu,
            height_emu=height,
            line_count=0,
            overflow_width_emu=0,
        )
    size_pt, weight = _body_style(theme)
    parts = [
        _TextPart(
            "label",
            measure_text(
                _as_text(block.fields.get("text"))
                or _as_text(block.fields.get("label"))
                or _as_text(block.fields.get("value")),
                available_width_emu=_inner_width(width_emu, theme),
                theme=theme,
                font_size_pt=size_pt,
                weight=weight,
            ),
        )
    ]
    return _measure_parts(parts, theme=theme)


def minimum_block_height(
    block: BlockIR,
    *,
    width_emu: int,
    theme: Theme,
) -> int:
    """Tinggi minimum block untuk reservasi row berikutnya.

    Untuk media, batas tinggi nol memilih tinggi minimum contain, bukan tinggi
    natural 16:9. Teks dan tabel tetap memakai tinggi naturalnya karena tidak
    boleh di-shrink.
    """
    return measure_block(block, width_emu=width_emu, theme=theme, max_height_emu=0).height_emu


def _measure_text_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, theme)
    parts: list[_TextPart] = []
    heading = _as_text(block.fields.get("heading"))
    if heading:
        heading_size_pt, heading_weight = _body_style(theme, weight=600)
        parts.append(
            _TextPart(
                "heading",
                measure_text(
                    heading,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=heading_size_pt,
                    weight=heading_weight,
                ),
            )
        )
    size_pt, weight = _role_style(theme, block.role)
    parts.append(
        _TextPart(
            "text",
            measure_text(
                _as_text(block.fields.get("text")),
                available_width_emu=inner,
                theme=theme,
                font_size_pt=size_pt,
                weight=weight,
            ),
        )
    )
    return _measure_parts(parts, theme=theme)


def _measure_bullets_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, theme)
    item_width = max(1, inner - theme.spacing.md_emu)
    size_pt, weight = _body_style(theme)
    items = _as_text_tuple(block.fields.get("items"))
    parts = [
        _TextPart(
            f"item{index}.text",
            measure_text(
                item,
                available_width_emu=item_width,
                theme=theme,
                font_size_pt=size_pt,
                weight=weight,
            ),
        )
        for index, item in enumerate(items, start=1)
    ]
    if not parts:
        parts.append(
            _TextPart(
                "item1.text",
                measure_text(
                    "",
                    available_width_emu=item_width,
                    theme=theme,
                    font_size_pt=size_pt,
                    weight=weight,
                ),
            )
        )
    return _measure_parts(parts, theme=theme)


def _measure_quote_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, theme)
    size_pt, weight = _body_style(theme)
    parts = [
        _TextPart(
            "text",
            measure_text(
                _as_text(block.fields.get("text")),
                available_width_emu=inner,
                theme=theme,
                font_size_pt=size_pt,
                weight=weight,
            ),
        )
    ]
    attribution = _as_text(block.fields.get("attribution"))
    if attribution:
        attribution_size_pt, attribution_weight = _body_style(theme, weight=600)
        parts.append(
            _TextPart(
                "attribution",
                measure_text(
                    attribution,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=attribution_size_pt,
                    weight=attribution_weight,
                ),
            )
        )
    return _measure_parts(parts, theme=theme)


def _measure_metric_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, theme)
    parts: list[_TextPart] = []
    value = _as_text(block.fields.get("value"))
    if value:
        parts.append(
            _TextPart(
                "value",
                measure_text(
                    value,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=max(theme.typography.title_pt, theme.typography.minimum_pt),
                    weight=800,
                ),
            )
        )
    label = _as_text(block.fields.get("label"))
    if label:
        label_size_pt, label_weight = _body_style(theme, weight=600)
        parts.append(
            _TextPart(
                "label",
                measure_text(
                    label,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=label_size_pt,
                    weight=label_weight,
                ),
            )
        )
    caption = _as_text(block.fields.get("caption"))
    if caption:
        caption_size_pt, caption_weight = _body_style(theme)
        parts.append(
            _TextPart(
                "caption",
                measure_text(
                    caption,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=caption_size_pt,
                    weight=caption_weight,
                ),
            )
        )
    if not parts:
        size_pt, weight = _body_style(theme)
        value_part = _TextPart(
            "value",
            measure_text(
                "",
                available_width_emu=inner,
                theme=theme,
                font_size_pt=size_pt,
                weight=weight,
            ),
        )
        return _with_padding(_combine_parts([value_part]), theme)
    return _measure_parts(parts, theme=theme)


def _measure_code_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, theme)
    code = _as_text(block.fields.get("code"))
    # Renderer memakai default ``True`` saat field line_numbers tidak ada.
    code_width = code_text_width(
        code,
        inner_width_emu=inner,
        theme=theme,
        line_numbers=bool(block.fields.get("line_numbers", True)),
    )
    parts = [
        _TextPart(
            "code",
            measure_code_text(
                code,
                available_width_emu=code_width,
                theme=theme,
            ),
        )
    ]
    filename = _as_text(block.fields.get("filename"))
    filename_gap = 0
    if filename:
        filename_size_pt, filename_weight = _body_style(theme, weight=600)
        parts.insert(
            0,
            _TextPart(
                "filename",
                measure_text(
                    filename,
                    available_width_emu=inner,
                    theme=theme,
                    font_size_pt=filename_size_pt,
                    weight=filename_weight,
                ),
            ),
        )
        filename_gap = theme.spacing.sm_emu
    combined = _combine_parts(parts)
    if filename_gap:
        combined = TextMeasurement(
            width_emu=combined.width_emu,
            height_emu=combined.height_emu + filename_gap,
            line_count=combined.line_count,
            overflow_width_emu=combined.overflow_width_emu,
        )
    return _with_padding(
        combined,
        theme,
        width_leaf=_overflow_width_leaf(parts),
        height_leaf=_height_leaf(parts),
    )


def _measure_table_block(block: BlockIR, *, width_emu: int, theme: Theme) -> BlockMeasurement:
    inner = _inner_width(width_emu, theme)
    columns = _as_text_tuple(block.fields.get("columns"))
    rows = _as_text_rows(block.fields.get("rows"))
    caption = _as_text(block.fields.get("caption"))

    caption_part: _TextPart | None = None
    if caption:
        caption_size_pt, caption_weight = _body_style(theme)
        caption_part = _TextPart(
            "caption",
            measure_text(
                caption,
                available_width_emu=inner,
                theme=theme,
                font_size_pt=caption_size_pt,
                weight=caption_weight,
            ),
        )

    cell_parts: list[_TextPart] = []
    table_height = 0
    table_width = 0
    table_lines = 0
    table_overflow = 0
    table_margin = 2 * theme.spacing.sm_emu
    row_column_count = max((len(row) for row in rows), default=0)
    column_count = max(len(columns), row_column_count)
    if column_count > 0:
        column_width = max(1, inner // column_count)
        cell_width = max(1, column_width - 2 * theme.spacing.sm_emu)
        emphasis_column = _emphasis_column(block.fields, column_count=column_count)
        header_size_pt, header_weight = _body_style(theme, weight=600)
        if columns:
            header_parts = [
                _TextPart(
                    f"h{column_index}",
                    measure_text(
                        cell,
                        available_width_emu=cell_width,
                        theme=theme,
                        font_size_pt=header_size_pt,
                        weight=700 if emphasis_column == column_index else header_weight,
                    ),
                )
                for column_index, cell in enumerate(columns, start=1)
            ]
            cell_parts.extend(header_parts)
            table_height += max(item.measurement.height_emu for item in header_parts) + table_margin
            table_width = max(table_width, max(item.measurement.width_emu for item in header_parts))
            table_lines += sum(item.measurement.line_count for item in header_parts)
            table_overflow = max(
                table_overflow,
                max(item.measurement.overflow_width_emu for item in header_parts),
            )
        body_size_pt, body_weight = _body_style(theme)
        for row_index, row in enumerate(rows, start=1):
            row_parts = [
                _TextPart(
                    f"r{row_index}.c{column_index}",
                    measure_text(
                        cell,
                        available_width_emu=cell_width,
                        theme=theme,
                        font_size_pt=body_size_pt,
                        weight=600 if emphasis_column == column_index else body_weight,
                    ),
                )
                for column_index, cell in enumerate(row, start=1)
            ]
            if not row_parts:
                continue
            cell_parts.extend(row_parts)
            table_height += max(item.measurement.height_emu for item in row_parts) + table_margin
            table_width = max(table_width, max(item.measurement.width_emu for item in row_parts))
            table_lines += sum(item.measurement.line_count for item in row_parts)
            table_overflow = max(
                table_overflow,
                max(item.measurement.overflow_width_emu for item in row_parts),
            )

    if caption_part is None and not cell_parts:
        return _with_padding(
            TextMeasurement(width_emu=0, height_emu=0, line_count=0, overflow_width_emu=0),
            theme,
        )

    caption_height = 0 if caption_part is None else caption_part.measurement.height_emu
    gap = theme.spacing.sm_emu if caption_part is not None and cell_parts else 0
    all_parts = tuple(part for part in (caption_part, *cell_parts) if part is not None)
    width = max((part.measurement.width_emu for part in all_parts), default=0)
    overflow_width = max(
        (part.measurement.overflow_width_emu for part in all_parts),
        default=0,
    )
    line_count = (0 if caption_part is None else caption_part.measurement.line_count) + table_lines
    return _with_padding(
        TextMeasurement(
            width_emu=width,
            height_emu=caption_height + gap + table_height,
            line_count=line_count,
            overflow_width_emu=overflow_width,
        ),
        theme,
        width_leaf=_overflow_width_leaf(all_parts),
        height_leaf=_height_leaf(cell_parts) or ("caption" if caption_part is not None else None),
    )


def _measure_media_block(
    block: BlockIR,
    *,
    width_emu: int,
    theme: Theme,
    max_height_emu: int | None = None,
) -> BlockMeasurement:
    natural_media_height = max(theme.spacing.md_emu, width_emu * 9 // 16)
    caption = _as_text(block.fields.get("caption"))
    caption_measurement: TextMeasurement | None = None
    if caption:
        caption_size_pt, caption_weight = _body_style(theme)
        caption_measurement = measure_text(
            caption,
            available_width_emu=width_emu,
            theme=theme,
            font_size_pt=caption_size_pt,
            weight=caption_weight,
        )
    caption_gap = theme.spacing.sm_emu if caption_measurement is not None else 0
    caption_height = 0 if caption_measurement is None else caption_measurement.height_emu

    media_height = natural_media_height
    overflow_height = 0
    if max_height_emu is not None:
        available_height = max(0, max_height_emu)
        media_budget = available_height - caption_gap - caption_height
        media_height = min(
            natural_media_height,
            max(theme.spacing.md_emu, media_budget),
        )
        overflow_height = max(
            0,
            media_height + caption_gap + caption_height - available_height,
        )

    height_emu = media_height + caption_gap + caption_height
    if caption_measurement is None:
        return BlockMeasurement(
            width_emu=width_emu,
            height_emu=height_emu,
            line_count=0,
            overflow_width_emu=0,
            overflow_height_emu=overflow_height,
            overflow_height_leaf=None,
            height_leaf=None,
        )
    return BlockMeasurement(
        width_emu=max(width_emu, caption_measurement.width_emu),
        height_emu=height_emu,
        line_count=caption_measurement.line_count,
        overflow_width_emu=caption_measurement.overflow_width_emu,
        overflow_height_emu=overflow_height,
        overflow_width_leaf="caption" if caption_measurement.overflow_width_emu > 0 else None,
        overflow_height_leaf="caption" if overflow_height > 0 else None,
        height_leaf="caption",
    )


def _measure_parts(parts: Sequence[_TextPart], *, theme: Theme) -> BlockMeasurement:
    return _with_padding(
        _combine_parts(parts),
        theme,
        width_leaf=_overflow_width_leaf(parts),
        height_leaf=_height_leaf(parts),
    )


def _combine_parts(parts: Sequence[_TextPart]) -> TextMeasurement:
    return _combine_text([part.measurement for part in parts])


def _overflow_width_leaf(parts: Sequence[_TextPart]) -> str | None:
    overflowing = [part for part in parts if part.measurement.overflow_width_emu > 0]
    if not overflowing:
        return None
    return max(overflowing, key=lambda part: part.measurement.overflow_width_emu).leaf


def _height_leaf(parts: Sequence[_TextPart]) -> str | None:
    if not parts:
        return None
    return max(parts, key=lambda part: part.measurement.height_emu).leaf


def _combine_text(measurements: Sequence[TextMeasurement]) -> TextMeasurement:
    if not measurements:
        return TextMeasurement(
            width_emu=0,
            height_emu=0,
            line_count=0,
            overflow_width_emu=0,
        )
    return TextMeasurement(
        width_emu=max(item.width_emu for item in measurements),
        height_emu=sum(item.height_emu for item in measurements),
        line_count=sum(item.line_count for item in measurements),
        overflow_width_emu=max(item.overflow_width_emu for item in measurements),
    )


def _with_padding(
    measurement: TextMeasurement,
    theme: Theme,
    *,
    width_leaf: str | None = None,
    height_leaf: str | None = None,
) -> BlockMeasurement:
    padding = theme.spacing.card_padding_emu
    return BlockMeasurement(
        width_emu=measurement.width_emu,
        height_emu=measurement.height_emu + 2 * padding,
        line_count=measurement.line_count,
        overflow_width_emu=measurement.overflow_width_emu,
        overflow_width_leaf=width_leaf,
        height_leaf=height_leaf,
    )


def _inner_width(width_emu: int, theme: Theme) -> int:
    return max(1, width_emu - 2 * theme.spacing.card_padding_emu)


def _emphasis_column(fields: Mapping[str, object], *, column_count: int) -> int | None:
    """Baca kolom emphasis 1-based bila valid untuk jumlah kolom tabel."""
    value = fields.get("emphasis_column")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 1 <= value <= column_count:
        return value
    return None


def _role_style(theme: Theme, role: str | None) -> tuple[float, int]:
    active_role = role if role in _ROLE_WEIGHTS else "body"
    if active_role in _TITLE_ROLES:
        size_pt = theme.typography.title_pt
    elif active_role in _SMALL_ROLES:
        size_pt = theme.typography.minimum_pt
    else:
        size_pt = theme.typography.body_pt
    return max(size_pt, theme.typography.minimum_pt), _ROLE_WEIGHTS[active_role]


def _body_style(theme: Theme, *, weight: int = 400) -> tuple[float, int]:
    return max(theme.typography.body_pt, theme.typography.minimum_pt), weight


def _code_chunks(line: str, capacity: int) -> tuple[str, ...]:
    if not line:
        return ("",)
    return tuple(line[index : index + capacity] for index in range(0, len(line), capacity))


def _round_emu(value: float) -> int:
    return round(value)


@lru_cache(maxsize=len(_FONT_BY_WEIGHT))
def _load_font(file_name: str) -> ImageFont.FreeTypeFont:
    path: Path = font_path(file_name)
    return ImageFont.truetype(str(path), _FONT_PIXEL_SIZE)


def _font_file_for_weight(weight: int) -> str:
    return min(_FONT_BY_WEIGHT, key=lambda item: (abs(item[0] - weight), item[0]))[1]


def _line_width_emu(
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    scale: float,
    tracking_emu: float,
) -> int:
    if not text:
        return 0
    advance = font.getlength(text) * scale
    tracking = max(0, len(text) - 1) * tracking_emu
    return max(0, _round_emu(advance + tracking))


def _wrap_text(
    text: str,
    *,
    width_emu: int,
    font: ImageFont.FreeTypeFont,
    scale: float,
    tracking_emu: float,
) -> tuple[tuple[str, ...], int]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    overflow = 0
    for paragraph in normalized.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            candidate_width = _line_width_emu(
                candidate,
                font=font,
                scale=scale,
                tracking_emu=tracking_emu,
            )
            if candidate_width <= width_emu:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            word_width = _line_width_emu(
                word,
                font=font,
                scale=scale,
                tracking_emu=tracking_emu,
            )
            if word_width > width_emu:
                lines.append(word)
                overflow = max(overflow, word_width - width_emu)
            else:
                current = word
        if current:
            lines.append(current)
    if not lines:
        lines.append("")
    widths = [
        _line_width_emu(
            line,
            font=font,
            scale=scale,
            tracking_emu=tracking_emu,
        )
        for line in lines
    ]
    overflow = max(overflow, max(widths, default=0) - width_emu)
    return tuple(lines), overflow


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        values = cast("list[object]", value)
        return tuple(_as_text(item) for item in values)
    if isinstance(value, tuple):
        tuple_values = cast("tuple[object, ...]", value)
        return tuple(_as_text(item) for item in tuple_values)
    return ()


def _as_text_rows(value: object) -> tuple[tuple[str, ...], ...]:
    if isinstance(value, list):
        values = cast("list[object]", value)
        return tuple(_as_text_tuple(row) for row in values)
    if isinstance(value, tuple):
        tuple_values = cast("tuple[object, ...]", value)
        return tuple(_as_text_tuple(row) for row in tuple_values)
    return ()
