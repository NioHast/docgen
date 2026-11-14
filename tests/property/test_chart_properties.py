"""Properti batas chart bar, line, dan donut."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from autooffice.deck.charts import ChartSpecError, build_chart_spec
from autooffice.deck.model import (
    BlockIR,
    ChartSeries,
    DeckSchemaError,
    compile_deck,
    validate_deck,
)

_WORD = st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True)


def _categories(count: int):
    return st.lists(_WORD, min_size=count, max_size=count).map(tuple)


def _series_for(categories: tuple[str, ...], count: int):
    return st.tuples(
        *(
            st.lists(
                st.integers(-999, 999),
                min_size=len(categories),
                max_size=len(categories),
            ).map(tuple)
            for _ in range(count)
        )
    ).map(
        lambda values: tuple(
            {"name": f"seri{index + 1}", "values": value} for index, value in enumerate(values)
        )
    )


def _chart_deck(
    kind: str,
    categories: tuple[str, ...],
    series: tuple[dict[str, object], ...],
) -> dict[str, object]:
    return {
        "schema": "autooffice.deck/v1",
        "meta": {"title": "Chart", "author": "Tim"},
        "slides": [
            {
                "id": "s01",
                "layout": "content",
                "blocks": [
                    {
                        "id": "chart1",
                        "type": "chart",
                        "kind": kind,
                        "title": "Judul grafik",
                        "alt": "Alt grafik",
                        "categories": list(categories),
                        "series": [
                            {
                                "name": item["name"],
                                "values": list(item["values"]),
                            }
                            for item in series
                        ],
                    }
                ],
            }
        ],
    }


def _raw_block(
    kind: str,
    categories: tuple[str, ...],
    series: tuple[dict[str, object], ...],
) -> BlockIR:
    return BlockIR(
        block_id="chart1",
        block_type="chart",
        span=12,
        role=None,
        fields={
            "kind": kind,
            "title": "Judul grafik",
            "alt": "Alt grafik",
            "categories": categories,
            "series": tuple(
                ChartSeries(name=item["name"], values=tuple(item["values"])) for item in series
            ),
        },
    )


def _assert_accepted(
    kind: str,
    categories: tuple[str, ...],
    series: tuple[dict[str, object], ...],
):
    block = compile_deck(validate_deck(_chart_deck(kind, categories, series))).slides[0].blocks[0]

    spec = build_chart_spec(block, slide_id="s01")

    assert spec.kind == kind
    assert spec.categories == categories
    assert tuple((item.name, item.values) for item in spec.series) == tuple(
        (item["name"], tuple(item["values"])) for item in series
    )
    return spec


def _assert_rejected(
    kind: str,
    categories: tuple[str, ...],
    series: tuple[dict[str, object], ...],
    match: str,
) -> None:
    with pytest.raises(DeckSchemaError, match=match):
        validate_deck(_chart_deck(kind, categories, series))

    with pytest.raises(ChartSpecError, match=match):
        build_chart_spec(_raw_block(kind, categories, series), slide_id="s01")


@st.composite
def _bar_line_chart(draw, series_count=None):
    kind = draw(st.sampled_from(("bar", "line")))
    category_count = draw(st.integers(2, 5))
    categories = draw(_categories(category_count))
    count = draw(st.integers(1, 4)) if series_count is None else series_count
    series = draw(_series_for(categories, count))
    return kind, categories, series


@st.composite
def _donut_chart(draw):
    category_count = draw(st.integers(2, 4))
    categories = draw(_categories(category_count))
    series = draw(_series_for(categories, 1))
    return "donut", categories, series


@st.composite
def _donut_wrong_series_count(draw):
    category_count = draw(st.integers(2, 4))
    categories = draw(_categories(category_count))
    count = draw(st.one_of(st.just(0), st.integers(2, 5)))
    series = draw(_series_for(categories, count))
    return "donut", categories, series


@st.composite
def _donut_wrong_category_count(draw):
    category_count = draw(st.one_of(st.integers(0, 1), st.integers(5, 6)))
    categories = draw(_categories(category_count))
    series = draw(_series_for(categories, 1))
    return "donut", categories, series


@st.composite
def _mismatched_chart(draw):
    kind = draw(st.sampled_from(("bar", "line", "donut")))
    if kind == "donut":
        category_count = draw(st.integers(2, 4))
        series_count = 1
    else:
        category_count = draw(st.integers(2, 5))
        series_count = draw(st.integers(1, 4))
    categories = draw(_categories(category_count))
    delta = draw(st.sampled_from((-2, -1, 1, 2)))
    value_count = max(0, category_count + delta)
    series = []
    for index in range(series_count):
        values = tuple(draw(st.integers(-999, 999)) for _ in range(value_count))
        series.append({"name": f"seri{index + 1}", "values": values})
    return kind, categories, tuple(series)


@settings(max_examples=60, deadline=None)
@given(chart=_bar_line_chart())
def test_bar_and_line_accept_one_to_four_series(chart) -> None:
    kind, categories, series = chart

    spec = _assert_accepted(kind, categories, series)

    assert 1 <= len(spec.series) <= 4
    assert spec.orientation == ("vertical" if kind == "bar" else None)


@settings(max_examples=40, deadline=None)
@given(chart=_bar_line_chart(series_count=5))
def test_bar_and_line_reject_five_series(chart) -> None:
    kind, categories, series = chart

    assert len(series) == 5
    _assert_rejected(kind, categories, series, "seri")


@settings(max_examples=30, deadline=None)
@given(chart=_donut_chart())
def test_donut_accepts_one_series_and_two_to_four_categories(chart) -> None:
    kind, categories, series = chart

    spec = _assert_accepted(kind, categories, series)

    assert len(spec.series) == 1
    assert 2 <= len(spec.categories) <= 4
    assert spec.orientation is None


@settings(max_examples=40, deadline=None)
@given(chart=_donut_wrong_series_count())
def test_donut_rejects_other_series_counts(chart) -> None:
    kind, categories, series = chart

    assert len(series) != 1
    _assert_rejected(kind, categories, series, "seri")


@settings(max_examples=40, deadline=None)
@given(chart=_donut_wrong_category_count())
def test_donut_rejects_other_category_counts(chart) -> None:
    kind, categories, series = chart

    assert not 2 <= len(categories) <= 4
    _assert_rejected(kind, categories, series, "kategori")


@settings(max_examples=50, deadline=None)
@given(chart=_mismatched_chart())
def test_chart_values_must_match_categories(chart) -> None:
    kind, categories, series = chart

    assert any(len(item["values"]) != len(categories) for item in series)
    _assert_rejected(kind, categories, series, "jumlah kategori")
