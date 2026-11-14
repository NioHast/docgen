"""Test preflight placeholder chart dan table native sebelum mutasi."""

from collections.abc import Callable
from dataclasses import replace
from types import SimpleNamespace

import pytest

from autooffice.deck.model import DeckIR
from autooffice.google import ChartPlaceholderError, TablePreflightError
from autooffice.google.slides import (
    PresentationSnapshot,
    find_chart_placeholders,
    preflight_native_tables,
    table_namespace,
    table_requirements,
)


def _options(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "include_chart_placeholders": True,
        "include_tables": True,
        "table_kind": "table",
        "table_rows": None,
        "table_columns": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_placeholder_preflight_returns_exactly_one_per_chart(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()

    placeholders = find_chart_placeholders(snapshot, ("s02.chart1",))

    assert placeholders["s02.chart1"].title == "autooffice:chart:s02.chart1"
    assert placeholders["s02.chart1"].kind == "shape"


def test_placeholder_preflight_fails_when_missing(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot(options=_options(include_chart_placeholders=False))

    with pytest.raises(ChartPlaceholderError, match=r"s02\.chart1"):
        find_chart_placeholders(snapshot, ("s02.chart1",))


def test_placeholder_preflight_fails_when_duplicate(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    slide = snapshot.slides[1]
    chart = next(
        element for element in slide.page_elements if element.title == "autooffice:chart:s02.chart1"
    )
    duplicate = replace(chart, object_id="chart-duplicate")
    slides = list(snapshot.slides)
    slides[1] = replace(slide, page_elements=(*slide.page_elements, duplicate))
    duplicated = replace(snapshot, slides=tuple(slides))

    with pytest.raises(ChartPlaceholderError, match="ditemukan 2 kali"):
        find_chart_placeholders(duplicated, ("s02.chart1",))


def test_table_preflight_accepts_native_table(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    requirements = table_requirements(google_deck)
    snapshot = make_snapshot()

    preflight_native_tables(google_deck, snapshot)

    assert requirements[0].row_count == 3
    assert requirements[0].column_count == 2


def test_table_preflight_accepts_autooffice_marker_prefix(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    slide = snapshot.slides[0]
    table = next(element for element in slide.page_elements if element.kind == "table")
    marked = replace(table, title="autooffice:table:s01.table1")
    snapshot = replace(
        snapshot,
        slides=(
            replace(
                slide,
                page_elements=tuple(
                    marked if element.object_id == table.object_id else element
                    for element in slide.page_elements
                ),
            ),
            *snapshot.slides[1:],
        ),
    )

    preflight_native_tables(google_deck, snapshot)

    requirement = table_requirements(google_deck)[0]
    marked_table = next(
        element
        for element in snapshot.slides[0].page_elements
        if element.object_id == table.object_id
    )
    assert marked_table.title == "autooffice:table:s01.table1"
    assert table_namespace(marked_table.title) == requirement.namespace
    assert (marked_table.row_count, marked_table.column_count) == (
        requirement.row_count,
        requirement.column_count,
    )


def test_table_preflight_rejects_table_moved_to_another_slide(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    first, second = snapshot.slides[0], snapshot.slides[1]
    table = next(element for element in first.page_elements if element.kind == "table")
    snapshot = replace(
        snapshot,
        slides=(
            replace(
                first,
                page_elements=tuple(
                    element
                    for element in first.page_elements
                    if element.object_id != table.object_id
                ),
            ),
            replace(second, page_elements=(*second.page_elements, table)),
        ),
    )

    with pytest.raises(TablePreflightError, match=r"slide index 2.*slide index 1"):
        preflight_native_tables(google_deck, snapshot)


def test_table_preflight_rejects_off_slide_duplicate_even_with_valid_table(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    first, second = snapshot.slides[0], snapshot.slides[1]
    table = next(element for element in first.page_elements if element.kind == "table")
    duplicate = replace(table, object_id="table-offslide")
    snapshot = replace(
        snapshot,
        slides=(
            first,
            replace(second, page_elements=(*second.page_elements, duplicate)),
        ),
    )

    with pytest.raises(TablePreflightError, match=r"slide index 1, 2"):
        preflight_native_tables(google_deck, snapshot)


def test_table_preflight_fails_when_table_missing(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot(options=_options(include_tables=False))

    with pytest.raises(
        TablePreflightError,
        match=r"slide 's01' block 'table1'.*tidak ditemukan",
    ):
        preflight_native_tables(google_deck, snapshot)


def test_table_preflight_fails_for_image_instead_of_native_table(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot(options=_options(table_kind="image"))

    with pytest.raises(
        TablePreflightError,
        match=r"slide 's01' block 'table1'.*image",
    ):
        preflight_native_tables(google_deck, snapshot)


def test_table_preflight_fails_for_wrong_row_and_column_count(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot(options=_options(table_rows=9, table_columns=7))

    with pytest.raises(
        TablePreflightError,
        match=r"slide 's01' block 'table1'.*9x7.*3x2",
    ):
        preflight_native_tables(google_deck, snapshot)


def test_table_preflight_fails_for_shape_group(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot(options=_options(table_kind="group"))

    with pytest.raises(
        TablePreflightError,
        match=r"slide 's01' block 'table1'.*group",
    ):
        preflight_native_tables(google_deck, snapshot)
