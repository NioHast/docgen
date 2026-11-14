"""Test rumus grid, span, dan primitive row."""

import pytest

from autooffice.deck.layout.grid import (
    LAYOUT_COLUMNS,
    Grid,
    GridError,
    RowError,
    RowItem,
    SpanError,
    place_row,
    span_width,
    validate_row_spans,
    validate_span,
)
from autooffice.deck.layout.spec import PlacedBlock
from autooffice.design.theme import Theme


def _grid(**overrides: int) -> Grid:
    values = {
        "columns": LAYOUT_COLUMNS,
        "gutter_emu": 0,
        "margin_left_emu": 0,
        "margin_right_emu": 0,
        "margin_top_emu": 0,
        "margin_bottom_emu": 0,
        "row_gap_emu": 0,
        "slide_width_emu": 1000,
        "slide_height_emu": 1000,
    }
    values.update(overrides)
    return Grid(**values)


def test_content_and_column_width_follow_theme_tokens(grid: Grid) -> None:
    expected_content = grid.slide_width_emu - grid.margin_left_emu - grid.margin_right_emu
    assert grid.content_width_emu == expected_content
    assert (
        grid.column_width_emu
        == (grid.content_width_emu - (LAYOUT_COLUMNS - 1) * grid.gutter_emu) // LAYOUT_COLUMNS
    )
    assert grid.column_width_emu == 779_780


def test_span_width_matches_contract_formula(grid: Grid) -> None:
    for span in (1, 2, 6, 7, 12):
        expected = span * grid.column_width_emu + (span - 1) * grid.gutter_emu
        assert grid.span_width(span) == expected
    assert grid.span_width(12) == grid.content_width_emu


def test_module_span_width_uses_theme(grid: Grid, theme: Theme) -> None:
    assert span_width(theme, 6) == grid.span_width(6)


def test_twelve_spans_fill_content_when_division_is_not_exact() -> None:
    grid = Grid(
        columns=12,
        gutter_emu=0,
        margin_left_emu=0,
        margin_right_emu=0,
        margin_top_emu=0,
        margin_bottom_emu=0,
        row_gap_emu=0,
        slide_width_emu=1001,
        slide_height_emu=1000,
    )

    assert grid.span_width(12) == 1001


def test_colum_left_places_spans_left_to_right(grid: Grid) -> None:
    first = grid.column_left(0)
    second = grid.column_left(6)
    assert first == grid.margin_left_emu
    assert first + grid.span_width(6) + grid.gutter_emu == second
    assert second + grid.span_width(6) == grid.content_right_emu


@pytest.mark.parametrize("span", [0, 13, -1])
def test_span_outside_one_to_twelve_is_rejected(span: int) -> None:
    with pytest.raises(SpanError, match="Span harus 1 sampai 12"):
        validate_span(span)


def test_span_width_rejects_invalid_span(grid: Grid) -> None:
    with pytest.raises(SpanError):
        grid.span_width(0)
    with pytest.raises(SpanError):
        grid.span_width(13)


def test_row_sum_over_twelve_is_rejected() -> None:
    with pytest.raises(SpanError, match="maksimal 12"):
        validate_row_spans((7, 6))


def test_row_sum_exactly_twelve_is_accepted() -> None:
    assert validate_row_spans((7, 5)) == 12


def test_empty_row_is_rejected() -> None:
    with pytest.raises(RowError, match="minimal"):
        validate_row_spans(())


def test_place_row_uses_tallest_content_and_row_gap(grid: Grid) -> None:
    placement = place_row(
        grid,
        (
            RowItem(block_id="left", span=7, height_emu=100),
            RowItem(block_id="right", span=5, height_emu=400),
        ),
        top_emu=grid.content_top_emu,
    )

    assert [box.block_id for box in placement.boxes] == ["left", "right"]
    assert all(isinstance(box, PlacedBlock) for box in placement.boxes)
    assert placement.height_emu == 400
    assert placement.bottom_emu == grid.content_top_emu + 400
    left, right = placement.boxes
    assert left.left_emu == grid.column_left(0)
    assert left.width_emu == grid.span_width(7)
    assert right.left_emu == grid.column_left(7)
    assert right.width_emu == grid.span_width(5)
    assert all(box.height_emu == 400 for box in placement.boxes)
    assert all(box.top_emu == grid.content_top_emu for box in placement.boxes)


def test_place_row_can_keep_natural_heights(grid: Grid) -> None:
    placement = place_row(
        grid,
        (
            RowItem(block_id="left", span=6, height_emu=100),
            RowItem(block_id="right", span=6, height_emu=400),
        ),
        top_emu=grid.content_top_emu,
        stretch=False,
    )

    assert tuple(box.height_emu for box in placement.boxes) == (100, 400)


def test_place_row_rejects_duplicate_block_ids(grid: Grid) -> None:
    with pytest.raises(RowError, match="duplikat"):
        place_row(
            grid,
            (
                RowItem(block_id="same", span=6, height_emu=10),
                RowItem(block_id="same", span=6, height_emu=10),
            ),
            top_emu=0,
        )


def test_grid_requires_twelve_columns() -> None:
    with pytest.raises(GridError, match="12 kolom"):
        Grid(
            columns=10,
            gutter_emu=1,
            margin_left_emu=0,
            margin_right_emu=0,
            margin_top_emu=0,
            margin_bottom_emu=0,
            row_gap_emu=0,
            slide_width_emu=1000,
            slide_height_emu=1000,
        )


@pytest.mark.parametrize("span", [3.0, "6", None])
def test_validate_span_rejects_non_integer(span: object) -> None:
    with pytest.raises(SpanError, match="bilangan bulat"):
        validate_span(span)  # type: ignore[arg-type]


def test_span_boundaries_cover_one_column_and_full_content(grid: Grid) -> None:
    assert validate_span(1) == 1
    assert validate_span(LAYOUT_COLUMNS) == LAYOUT_COLUMNS
    assert grid.span_width(1) == grid.column_width_emu
    assert grid.span_width(LAYOUT_COLUMNS) == grid.content_width_emu


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"gutter_emu": -1}, "Gutter grid"),
        ({"margin_left_emu": -1}, "Margin horizontal"),
        ({"margin_right_emu": -1}, "Margin horizontal"),
        ({"margin_top_emu": -1}, "Margin vertikal"),
        ({"margin_bottom_emu": -1}, "Margin vertikal"),
        ({"slide_width_emu": 0}, "Lebar konten slide"),
        ({"slide_height_emu": 0}, "Tinggi konten slide"),
        ({"slide_width_emu": 10, "gutter_emu": 5}, "Lebar kolom"),
        ({"row_gap_emu": -1}, "Row gap"),
    ],
)
def test_grid_rejects_invalid_token_geometry(
    overrides: dict[str, int],
    match: str,
) -> None:
    with pytest.raises(GridError, match=match):
        _grid(**overrides)


def test_column_left_returns_content_right_at_end_column(grid: Grid) -> None:
    assert grid.column_left(grid.columns) == grid.content_right_emu


@pytest.mark.parametrize(
    ("start_column", "match"),
    [
        (4.0, "bilangan bulat"),
        (-1, "0 sampai 12"),
        (LAYOUT_COLUMNS + 1, "0 sampai 12"),
    ],
)
def test_column_left_rejects_invalid_start_column(
    grid: Grid,
    start_column: object,
    match: str,
) -> None:
    with pytest.raises(GridError, match=match):
        grid.column_left(start_column)  # type: ignore[arg-type]


def test_row_width_matches_span_and_gutter_sum(grid: Grid) -> None:
    assert grid.row_width((6, 6)) == 2 * grid.span_width(6) + grid.gutter_emu
    assert grid.row_width((LAYOUT_COLUMNS,)) == grid.content_width_emu


def test_full_row_ends_at_content_right(grid: Grid) -> None:
    placement = place_row(
        grid,
        (RowItem(block_id="full", span=LAYOUT_COLUMNS, height_emu=100),),
        top_emu=grid.content_top_emu,
    )
    box = placement.boxes[0]

    assert box.left_emu == grid.content_left_emu
    assert box.left_emu + box.width_emu == grid.content_right_emu


@pytest.mark.parametrize(
    ("block_id", "height_emu", "match"),
    [
        ("", 10, "tidak boleh kosong"),
        ("body", -1, "tidak boleh negatif"),
    ],
)
def test_row_item_rejects_invalid_content(
    block_id: str,
    height_emu: int,
    match: str,
) -> None:
    with pytest.raises(RowError, match=match):
        RowItem(block_id=block_id, span=LAYOUT_COLUMNS, height_emu=height_emu)


def test_place_row_rejects_negative_top(grid: Grid) -> None:
    with pytest.raises(RowError, match="Posisi atas"):
        place_row(
            grid,
            (RowItem(block_id="body", span=LAYOUT_COLUMNS, height_emu=10),),
            top_emu=-1,
        )


def test_place_row_rejects_empty_items(grid: Grid) -> None:
    with pytest.raises(RowError, match="memiliki satu block"):
        place_row(grid, (), top_emu=0)
