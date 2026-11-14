"""Test pengukuran teks dan block memakai metrik font bundle."""

from collections.abc import Callable

import pytest

from autooffice.deck.layout.measure import (
    MeasurementError,
    TextMeasurement,
    measure_block,
    measure_code_text,
    measure_text,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

WIDTH = 2_000_000


def test_text_measurement_uses_theme_line_height(theme: Theme) -> None:
    measurement = measure_text("Halo", available_width_emu=WIDTH, theme=theme)
    expected_line_height = round(round(theme.typography.body_pt * 12_700) * 1.2)

    assert isinstance(measurement, TextMeasurement)
    assert measurement.line_count == 1
    assert measurement.height_emu == expected_line_height
    assert measurement.width_emu > 0
    assert measurement.overflow_width_emu == 0


def test_text_wraps_without_shrinking(theme: Theme) -> None:
    text = " ".join(["kata"] * 100)
    measurement = measure_text(text, available_width_emu=350_000, theme=theme)
    line_height = round(round(theme.typography.body_pt * 12_700) * 1.2)

    assert measurement.line_count > 1
    assert measurement.height_emu == measurement.line_count * line_height


def test_long_word_is_flagged_instead_of_ellipsized(theme: Theme) -> None:
    measurement = measure_text("W" * 40, available_width_emu=100_000, theme=theme)

    assert measurement.line_count == 1
    assert measurement.overflow_width_emu > 0
    assert measurement.width_emu > 100_000


def test_explicit_newlines_add_lines(theme: Theme) -> None:
    measurement = measure_text("satu\ndua\ntiga", available_width_emu=WIDTH, theme=theme)

    assert measurement.line_count == 3


def test_negative_tracking_is_applied(theme: Theme) -> None:
    normal = measure_text("Tracking test", available_width_emu=WIDTH, theme=theme, tracking_em=0.0)
    tight = measure_text("Tracking test", available_width_emu=WIDTH, theme=theme, tracking_em=-0.1)

    assert tight.width_emu < normal.width_emu


def test_text_block_height_includes_padding(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("body", "text", fields={"text": "Satu baris"}, role="body")
    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    text = measure_text(
        "Satu baris",
        available_width_emu=WIDTH - 2 * theme.spacing.card_padding_emu,
        theme=theme,
    )

    assert measurement.height_emu == text.height_emu + 2 * theme.spacing.card_padding_emu
    assert measurement.overflow_width_emu == 0


def test_code_height_grows_with_lines(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    short = block_factory("code1", "code", fields={"code": "x = 1"})
    long = block_factory("code2", "code", fields={"code": "\n".join(["x = 1"] * 20)})

    assert (
        measure_block(long, width_emu=WIDTH, theme=theme).height_emu
        > measure_block(short, width_emu=WIDTH, theme=theme).height_emu
    )


def test_table_height_grows_with_rows(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    short = block_factory(
        "table1",
        "table",
        fields={"columns": ("A", "B"), "rows": (("1", "2"),)},
    )
    long = block_factory(
        "table2",
        "table",
        fields={
            "columns": ("A", "B"),
            "rows": tuple((str(index), str(index + 1)) for index in range(8)),
        },
    )

    assert (
        measure_block(long, width_emu=WIDTH, theme=theme).height_emu
        > measure_block(short, width_emu=WIDTH, theme=theme).height_emu
    )


def test_table_and_code_wide_content_is_flagged(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    table = block_factory(
        "table1",
        "table",
        fields={"columns": ("A",), "rows": (("W" * 200,),)},
    )
    code = block_factory("code1", "code", fields={"code": "W" * 400})

    assert measure_block(table, width_emu=400_000, theme=theme).overflow_width_emu > 0
    assert measure_block(code, width_emu=400_000, theme=theme).overflow_width_emu > 0


def test_text_ignores_max_height(block_factory: Callable[..., BlockIR], theme: Theme) -> None:
    block = block_factory("body", "text", fields={"text": "Satu baris"}, role="body")
    natural = measure_block(block, width_emu=WIDTH, theme=theme)
    capped = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=theme.spacing.sm_emu,
    )

    assert capped == natural
    assert capped.overflow_height_emu == 0


def test_media_height_is_capped_to_max_height(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("image1", "image", fields={"path": "assets/hero.png"})
    natural = measure_block(block, width_emu=WIDTH, theme=theme)
    capped = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=900_000,
    )

    assert natural.height_emu == WIDTH * 9 // 16
    assert capped.height_emu == 900_000
    assert capped.overflow_height_emu == 0


def test_media_caption_shrinks_media_inside_max_height(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory(
        "image1",
        "image",
        fields={"path": "assets/hero.png", "caption": "Sumber foto"},
    )
    max_height = 1_000_000
    natural = measure_block(block, width_emu=WIDTH, theme=theme)
    measurement = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=max_height,
    )

    assert natural.height_emu > max_height
    assert measurement.height_emu == max_height
    assert measurement.line_count == 1
    assert measurement.overflow_height_emu == 0


def test_media_height_never_drops_below_minimum(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory("image1", "image", fields={"path": "assets/hero.png"})
    max_height = theme.spacing.md_emu // 2
    measurement = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=max_height,
    )

    assert measurement.height_emu == theme.spacing.md_emu
    assert measurement.overflow_height_emu == theme.spacing.md_emu - max_height


def test_media_caption_that_cannot_fit_reports_height_overflow(
    block_factory: Callable[..., BlockIR], theme: Theme
) -> None:
    block = block_factory(
        "image1",
        "image",
        fields={"path": "assets/hero.png", "caption": "Sumber foto"},
    )
    caption_height = measure_text(
        "Sumber foto",
        available_width_emu=WIDTH,
        theme=theme,
    ).height_emu
    max_height = theme.spacing.md_emu + theme.spacing.sm_emu
    measurement = measure_block(
        block,
        width_emu=WIDTH,
        theme=theme,
        max_height_emu=max_height,
    )

    assert measurement.height_emu == (theme.spacing.md_emu + theme.spacing.sm_emu + caption_height)
    assert measurement.overflow_height_emu == caption_height


def test_zero_measurement_width_is_rejected(theme: Theme) -> None:
    with pytest.raises(MeasurementError, match="positif"):
        measure_text("Halo", available_width_emu=0, theme=theme)


def _inner_width(theme: Theme, width: int = WIDTH) -> int:
    return width - 2 * theme.spacing.card_padding_emu


@pytest.mark.parametrize(
    ("role", "size_token", "weight"),
    [
        ("display", "title_pt", 800),
        ("title", "title_pt", 700),
        ("lead", "body_pt", 600),
        ("body", "body_pt", 400),
        ("caption", "minimum_pt", 400),
        ("label", "minimum_pt", 600),
        ("kicker", "minimum_pt", 700),
    ],
)
def test_text_role_matches_renderer_size_and_weight(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
    role: str,
    size_token: str,
    weight: int,
) -> None:
    block = block_factory("body", "text", fields={"text": "Halo dunia"}, role=role)
    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    expected = measure_text(
        "Halo dunia",
        available_width_emu=_inner_width(theme),
        theme=theme,
        font_size_pt=getattr(theme.typography, size_token),
        weight=weight,
    )

    assert measurement.height_emu == expected.height_emu + 2 * theme.spacing.card_padding_emu
    assert measurement.width_emu == expected.width_emu


@pytest.mark.parametrize(
    ("lighter_role", "heavier_role"),
    [
        ("body", "lead"),
        ("caption", "label"),
        ("label", "kicker"),
        ("title", "display"),
    ],
)
def test_role_weight_affects_measured_width(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
    lighter_role: str,
    heavier_role: str,
) -> None:
    lighter = block_factory(
        "lighter",
        "text",
        fields={"text": "Halo dunia"},
        role=lighter_role,
    )
    heavier = block_factory(
        "heavier",
        "text",
        fields={"text": "Halo dunia"},
        role=heavier_role,
    )

    lighter_measurement = measure_block(lighter, width_emu=WIDTH, theme=theme)
    heavier_measurement = measure_block(heavier, width_emu=WIDTH, theme=theme)

    assert heavier_measurement.width_emu > lighter_measurement.width_emu


def test_code_filename_height_includes_gap(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    code_text = "def key():\n    return 1"
    filename = "keys.py"
    block = block_factory(
        "code1",
        "code",
        fields={"code": code_text, "filename": filename},
    )
    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    code = measure_code_text(
        code_text,
        available_width_emu=_inner_width(theme),
        theme=theme,
    )
    filename_measurement = measure_text(
        filename,
        available_width_emu=_inner_width(theme),
        theme=theme,
        font_size_pt=max(theme.typography.body_pt, theme.typography.minimum_pt),
        weight=600,
    )

    assert measurement.height_emu == (
        code.height_emu
        + filename_measurement.height_emu
        + theme.spacing.sm_emu
        + 2 * theme.spacing.card_padding_emu
    )
    assert measurement.line_count == code.line_count + filename_measurement.line_count


def test_code_preserves_leading_and_repeated_spaces(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    plain = block_factory("plain", "code", fields={"code": "x = 1"})
    indented = block_factory("indented", "code", fields={"code": "    x = 1"})
    spaced = block_factory("spaced", "code", fields={"code": "x  =  1"})

    plain_measurement = measure_block(plain, width_emu=WIDTH, theme=theme)
    indented_measurement = measure_block(indented, width_emu=WIDTH, theme=theme)
    spaced_measurement = measure_block(spaced, width_emu=WIDTH, theme=theme)

    assert indented_measurement.width_emu > plain_measurement.width_emu
    assert spaced_measurement.width_emu > plain_measurement.width_emu
    assert indented_measurement.line_count == 1
    assert spaced_measurement.line_count == 1


def test_indented_code_near_slot_width_reports_wrapped_line_count(theme: Theme) -> None:
    inner = _inner_width(theme)
    character_width = measure_code_text(
        "x",
        available_width_emu=inner,
        theme=theme,
    ).width_emu
    capacity = inner // character_width
    unindented = "x" * capacity
    indented = "    " + unindented

    unindented_measurement = measure_code_text(
        unindented,
        available_width_emu=inner,
        theme=theme,
    )
    indented_measurement = measure_code_text(
        indented,
        available_width_emu=inner,
        theme=theme,
    )

    assert unindented_measurement.line_count == 1
    assert indented_measurement.line_count == 2
    assert indented_measurement.width_emu <= inner


def test_table_emphasis_column_uses_emphasized_weights(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    header = "review eksperimen delta tambahan hasil"
    body = "arsitektur column arsitektur kontrak measurement arsitektur"
    caption = "Status emphasis"
    width = 4_000_000
    block = block_factory(
        "table1",
        "table",
        fields={
            "columns": ("A", header),
            "rows": (("1", body), ("2", body)),
            "caption": caption,
            "emphasis_column": 2,
        },
    )
    inner = width - 2 * theme.spacing.card_padding_emu
    cell_width = inner // 2 - 2 * theme.spacing.sm_emu
    size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)

    def measure(text: str, weight: int) -> TextMeasurement:
        return measure_text(
            text,
            available_width_emu=cell_width,
            theme=theme,
            font_size_pt=size_pt,
            weight=weight,
        )

    header_emphasis = measure(header, 700)
    body_emphasis = measure(body, 600)
    assert header_emphasis.line_count > measure(header, 600).line_count
    assert body_emphasis.line_count > measure(body, 400).line_count
    caption_measurement = measure_text(
        caption,
        available_width_emu=inner,
        theme=theme,
        font_size_pt=size_pt,
        weight=400,
    )
    margin = 2 * theme.spacing.sm_emu

    measurement = measure_block(block, width_emu=width, theme=theme)

    expected_height = (
        2 * theme.spacing.card_padding_emu
        + caption_measurement.height_emu
        + theme.spacing.sm_emu
        + header_emphasis.height_emu
        + margin
        + 2 * (body_emphasis.height_emu + margin)
    )
    assert measurement.height_emu == expected_height


def test_table_height_includes_cell_margins_and_caption_gap(
    block_factory: Callable[..., BlockIR],
    theme: Theme,
) -> None:
    columns = ("A", "B")
    rows = (("1", "2"), ("3", "4"))
    caption = "Tabel angka"
    block = block_factory(
        "table1",
        "table",
        fields={"columns": columns, "rows": rows, "caption": caption},
    )

    measurement = measure_block(block, width_emu=WIDTH, theme=theme)
    inner = _inner_width(theme)
    cell_width = max(1, inner // len(columns) - 2 * theme.spacing.sm_emu)
    header = measure_text(
        "A",
        available_width_emu=cell_width,
        theme=theme,
        weight=600,
    )
    cell = measure_text("1", available_width_emu=cell_width, theme=theme)
    caption_measurement = measure_text(caption, available_width_emu=inner, theme=theme)

    expected_height = (
        caption_measurement.height_emu
        + theme.spacing.sm_emu
        + header.height_emu
        + 2 * theme.spacing.sm_emu
        + 2 * (cell.height_emu + 2 * theme.spacing.sm_emu)
        + 2 * theme.spacing.card_padding_emu
    )

    assert measurement.height_emu == expected_height
