"""Test batas pengukuran teks, varian field block, dan contain media."""

from collections.abc import Callable

import pytest

from autooffice.deck.layout.measure import (
    BlockMeasurement,
    MeasurementError,
    TextMeasurement,
    measure_block,
    measure_text,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

WIDTH = 2_000_000


def _inner_width(theme: Theme) -> int:
    return WIDTH - 2 * theme.spacing.card_padding_emu


def _bullet_width(theme: Theme) -> int:
    return max(1, _inner_width(theme) - theme.spacing.md_emu)


def _line_height(theme: Theme, size_pt: float | None = None) -> int:
    size = theme.typography.body_pt if size_pt is None else size_pt
    return round(round(size * 12_700) * theme.typography.line_height)


def test_empty_text_measures_one_blank_line(theme: Theme) -> None:
    measurement = measure_text("", available_width_emu=WIDTH, theme=theme)

    assert measurement == TextMeasurement(
        width_emu=0,
        height_emu=_line_height(theme),
        line_count=1,
        overflow_width_emu=0,
    )


def test_blank_paragraph_between_lines_is_measured(theme: Theme) -> None:
    measurement = measure_text("satu\n\ndua", available_width_emu=WIDTH, theme=theme)

    assert measurement.line_count == 3
    assert measurement.height_emu == 3 * _line_height(theme)


def test_line_that_exactly_fits_has_no_overflow(theme: Theme) -> None:
    reference = measure_text("kata", available_width_emu=WIDTH, theme=theme)

    exact = measure_text("kata", available_width_emu=reference.width_emu, theme=theme)
    narrower = measure_text("kata", available_width_emu=reference.width_emu - 1, theme=theme)

    assert exact.line_count == 1
    assert exact.overflow_width_emu == 0
    assert narrower.line_count == 1
    assert narrower.overflow_width_emu == 1


def test_positive_tracking_widens_text(theme: Theme) -> None:
    normal = measure_text("Tracking test", available_width_emu=WIDTH, theme=theme, tracking_em=0.0)
    loose = measure_text("Tracking test", available_width_emu=WIDTH, theme=theme, tracking_em=0.05)

    assert loose.width_emu > normal.width_emu


def test_zero_font_size_is_rejected(theme: Theme) -> None:
    with pytest.raises(MeasurementError, match="Ukuran font"):
        measure_text("Halo", available_width_emu=WIDTH, theme=theme, font_size_pt=0)


def test_zero_line_height_is_rejected(theme: Theme) -> None:
    with pytest.raises(MeasurementError, match="Line-height"):
        measure_text("Halo", available_width_emu=WIDTH, theme=theme, line_height=0)


def test_zero_block_width_is_rejected(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    block = block_factory("body", "text", fields={"text": "Halo"}, role="body")

    with pytest.raises(MeasurementError, match="harus positif"):
        measure_block(block, width_emu=0, theme=theme)


def test_non_string_text_is_measured_as_text(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("body", "text", fields={"text": 1234}, role="body")

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    expected = measure_text("1234", available_width_emu=_inner_width(theme), theme=theme)

    assert measurement.line_count == 1
    assert measurement.height_emu == expected.height_emu + 2 * theme.spacing.card_padding_emu


def test_bullets_accept_list_items(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    block = block_factory("points", "bullets", fields={"items": ["satu", "dua"]})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    item = measure_text("satu", available_width_emu=_bullet_width(theme), theme=theme)

    assert measurement.line_count == 2
    assert measurement.height_emu == 2 * item.height_emu + 2 * theme.spacing.card_padding_emu


def test_bullets_without_usable_items_measure_one_blank_line(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("points", "bullets", fields={"items": "bukan daftar"})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    blank = measure_text("", available_width_emu=_bullet_width(theme), theme=theme)

    assert measurement.line_count == 1
    assert measurement.width_emu == 0
    assert measurement.height_emu == blank.height_emu + 2 * theme.spacing.card_padding_emu


def test_quote_without_attribution_measures_text_only(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("quote1", "quote", fields={"text": "Kutipan singkat"})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    text = measure_text("Kutipan singkat", available_width_emu=_inner_width(theme), theme=theme)

    assert measurement.line_count == text.line_count
    assert measurement.height_emu == text.height_emu + 2 * theme.spacing.card_padding_emu


def test_metric_without_value_measures_label_and_caption(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory(
        "metric1",
        "metric",
        fields={"label": "Pendapatan", "caption": "2025"},
    )

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    label = measure_text(
        "Pendapatan",
        available_width_emu=_inner_width(theme),
        theme=theme,
        weight=600,
    )
    caption = measure_text("2025", available_width_emu=_inner_width(theme), theme=theme)

    assert measurement.line_count == 2
    assert measurement.height_emu == (
        label.height_emu + caption.height_emu + 2 * theme.spacing.card_padding_emu
    )


def test_metric_with_only_value_measures_one_line(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("metric1", "metric", fields={"value": "42%"})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    value = measure_text(
        "42%",
        available_width_emu=_inner_width(theme),
        theme=theme,
        font_size_pt=theme.typography.title_pt,
        weight=800,
    )

    assert measurement.line_count == 1
    assert measurement.width_emu == value.width_emu
    assert measurement.height_emu == value.height_emu + 2 * theme.spacing.card_padding_emu


def test_metric_without_fields_measures_blank_line(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("metric1", "metric", fields={})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    blank = measure_text("", available_width_emu=_inner_width(theme), theme=theme)

    assert measurement == BlockMeasurement(
        width_emu=0,
        height_emu=blank.height_emu + 2 * theme.spacing.card_padding_emu,
        line_count=1,
        overflow_width_emu=0,
    )


def test_table_without_cells_only_has_padding(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("table1", "table", fields={})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)

    assert measurement == BlockMeasurement(
        width_emu=0,
        height_emu=2 * theme.spacing.card_padding_emu,
        line_count=0,
        overflow_width_emu=0,
    )


def test_table_caption_is_measured_without_cells(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("table1", "table", fields={"caption": "Tabel kosong"})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    caption = measure_text("Tabel kosong", available_width_emu=_inner_width(theme), theme=theme)

    assert measurement.line_count == caption.line_count
    assert measurement.width_emu == caption.width_emu
    assert measurement.height_emu == caption.height_emu + 2 * theme.spacing.card_padding_emu


def test_table_rows_without_header_are_measured(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("table1", "table", fields={"rows": [["1", "2"]]})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)

    assert measurement.line_count == 2
    assert measurement.width_emu > 0
    assert measurement.overflow_width_emu == 0


def test_table_empty_row_is_skipped(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    block = block_factory(
        "table1",
        "table",
        fields={"columns": ("A",), "rows": ((), ("1",))},
    )

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)

    assert measurement.line_count == 2


def test_table_non_sequence_rows_are_ignored(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("table1", "table", fields={"columns": ("A",), "rows": "bukan baris"})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)

    assert measurement.line_count == 1
    assert measurement.width_emu > 0


def test_unknown_block_type_falls_back_to_label(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("stat", "stat", fields={"label": "Ringkasan"})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    label = measure_text("Ringkasan", available_width_emu=_inner_width(theme), theme=theme)

    assert measurement.line_count == 1
    assert measurement.height_emu == label.height_emu + 2 * theme.spacing.card_padding_emu


def test_media_caption_overflow_width_is_reported(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    caption = "W" * 800
    block = block_factory(
        "image1",
        "image",
        fields={"path": "assets/hero.png", "caption": caption},
    )

    measurement = measure_block(block, width_emu=400_000, theme=theme)
    measured_caption = measure_text(caption, available_width_emu=400_000, theme=theme)

    assert measurement.width_emu == measured_caption.width_emu
    assert measurement.overflow_width_emu == measured_caption.overflow_width_emu
    assert measurement.overflow_width_emu > 0


def test_media_zero_available_height_reports_minimum_overflow(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("image1", "image", fields={"path": "assets/hero.png"})

    measurement = measure_block(block, width_emu=WIDTH, theme=theme, max_height_emu=0)

    assert measurement.height_emu == theme.spacing.md_emu
    assert measurement.overflow_height_emu == theme.spacing.md_emu
