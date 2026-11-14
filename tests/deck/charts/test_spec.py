"""Test ekstraksi dan validasi ``ChartSpec`` dari block chart."""

from collections.abc import Callable, Mapping

import pytest

from autooffice.deck.charts import ChartSpec, ChartSpecError, build_chart_spec, make_chart_id
from autooffice.deck.charts.spec import ChartOrientation
from autooffice.deck.model import BlockIR, ChartSeries


def _raw_chart_block(**overrides: object) -> BlockIR:
    fields: dict[str, object] = {
        "kind": "bar",
        "title": "Judul chart",
        "alt": "Alt chart untuk pembaca layar",
        "categories": ("Q1", "Q2"),
        "series": (ChartSeries(name="Seri 1", values=(10, 20)),),
    }
    fields.update(overrides)
    return BlockIR(
        block_id="chart1",
        block_type="chart",
        span=12,
        role=None,
        fields=fields,
    )


def test_bar_spec_extracts_block_fields(chart_specs: Mapping[str, ChartSpec]) -> None:
    spec = chart_specs["s01.chart1"]

    assert spec.chart_id == "s01.chart1"
    assert spec.kind == "bar"
    assert spec.categories == ("Q1", "Q2", "Q3", "Q4")
    assert tuple(series.name for series in spec.series) == ("2023", "2024", "2025", "2026")
    assert spec.series[0].values == (10, 12, 14, 16)
    assert spec.orientation == "vertical"
    assert spec.title == "Pendapatan per kuartal"
    assert spec.unit is None
    assert spec.alt == "Diagram batang pendapatan empat seri naik dari Q1 ke Q4"


def test_horizontal_bar_keeps_orientation(chart_specs: Mapping[str, ChartSpec]) -> None:
    spec = chart_specs["s02.chart1"]

    assert spec.kind == "bar"
    assert spec.orientation == "horizontal"
    assert len(spec.series) == 1


def test_line_spec_keeps_unit_and_has_no_orientation(
    chart_specs: Mapping[str, ChartSpec],
) -> None:
    spec = chart_specs["s03.chart1"]

    assert spec.kind == "line"
    assert spec.orientation is None
    assert spec.unit == "persen"
    assert tuple(series.name for series in spec.series) == ("2025", "2026")


def test_donut_spec_has_one_series_and_four_categories(
    chart_specs: Mapping[str, ChartSpec],
) -> None:
    spec = chart_specs["s04.chart1"]

    assert spec.kind == "donut"
    assert spec.orientation is None
    assert len(spec.series) == 1
    assert len(spec.categories) == 4


def test_spec_without_slide_id_uses_block_id(chart_deck) -> None:
    block = chart_deck.slides[0].blocks[0]

    spec = build_chart_spec(block)

    assert spec.chart_id == block.block_id


def test_spec_is_deterministic(chart_deck) -> None:
    block = chart_deck.slides[0].blocks[0]

    assert build_chart_spec(block, slide_id="s01") == build_chart_spec(block, slide_id="s01")


def test_build_spec_rejects_non_chart_block() -> None:
    block = BlockIR(
        block_id="title",
        block_type="text",
        span=12,
        role="title",
        fields={"text": "Bukan chart"},
    )

    with pytest.raises(ChartSpecError, match="bukan chart"):
        build_chart_spec(block, slide_id="s01")


def test_five_series_are_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    series = tuple(
        ChartSeries(name=f"Seri {index}", values=(index, index + 1)) for index in range(1, 6)
    )
    block = chart_block_factory(series=series)

    with pytest.raises(ChartSpecError, match="maksimal 4 seri"):
        build_chart_spec(block)


def test_four_series_are_accepted(chart_block_factory: Callable[..., BlockIR]) -> None:
    series = tuple(
        ChartSeries(name=f"Seri {index}", values=(index, index + 1)) for index in range(1, 5)
    )
    block = chart_block_factory(series=series)

    spec = build_chart_spec(block)

    assert len(spec.series) == 4


def test_empty_series_are_rejected(chart_block_factory: Callable[..., BlockIR]) -> None:
    block = chart_block_factory(series=())

    with pytest.raises(ChartSpecError, match="minimal 1 seri"):
        build_chart_spec(block)


def test_donut_with_two_series_is_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    series = (
        ChartSeries(name="A", values=(10, 20)),
        ChartSeries(name="B", values=(30, 40)),
    )
    block = chart_block_factory(kind="donut", series=series)

    with pytest.raises(ChartSpecError, match="tepat satu seri"):
        build_chart_spec(block)


def test_donut_with_five_categories_is_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(
        kind="donut",
        categories=("A", "B", "C", "D", "E"),
        series=(ChartSeries(name="Nilai", values=(1, 2, 3, 4, 5)),),
    )

    with pytest.raises(ChartSpecError, match="2 sampai 4 kategori"):
        build_chart_spec(block)


def test_donut_with_one_category_is_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(
        kind="donut",
        categories=("A",),
        series=(ChartSeries(name="Nilai", values=(1,)),),
    )

    with pytest.raises(ChartSpecError, match="2 sampai 4 kategori"):
        build_chart_spec(block)


def test_donut_with_four_categories_is_accepted(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(
        kind="donut",
        categories=("A", "B", "C", "D"),
        series=(ChartSeries(name="Nilai", values=(1, 2, 3, 4)),),
    )

    spec = build_chart_spec(block)

    assert len(spec.categories) == 4
    assert len(spec.series) == 1


def test_values_length_must_match_categories(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(series=(ChartSeries(name="Seri 1", values=(1, 2, 3)),))

    with pytest.raises(ChartSpecError, match="jumlah kategori"):
        build_chart_spec(block)


@pytest.mark.parametrize(
    "value",
    ["teks", True, float("inf")],
    ids=["text", "bool", "infinite"],
)
def test_non_numeric_values_are_rejected(
    chart_block_factory: Callable[..., BlockIR],
    value: object,
) -> None:
    block = chart_block_factory(series=(ChartSeries(name="Seri 1", values=(value, 2)),))

    with pytest.raises(ChartSpecError, match="angka"):
        build_chart_spec(block)


def test_orientation_is_only_valid_for_bar(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(kind="line", orientation="horizontal")

    with pytest.raises(ChartSpecError, match="hanya valid untuk chart bar"):
        build_chart_spec(block)


def test_invalid_bar_orientation_is_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(orientation="diagonal")

    with pytest.raises(ChartSpecError, match="orientation chart"):
        build_chart_spec(block)


def test_empty_alt_is_rejected(chart_block_factory: Callable[..., BlockIR]) -> None:
    block = chart_block_factory(alt="   ")

    with pytest.raises(ChartSpecError, match="alt"):
        build_chart_spec(block)


def test_raw_series_mapping_is_accepted(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(
        series=({"name": "Seri 1", "values": [1, 2]},),
    )

    spec = build_chart_spec(block)

    assert spec.series == (ChartSeries(name="Seri 1", values=(1, 2)),)


def test_unknown_series_field_is_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(
        series=({"name": "Seri 1", "values": [1, 2], "warna": "#FFFFFF"},),
    )

    with pytest.raises(ChartSpecError, match="field tidak dikenal"):
        build_chart_spec(block)


def test_make_chart_id_uses_slide_and_block() -> None:
    assert make_chart_id("s04", "chart1") == "s04.chart1"


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_bar_orientation_literal_values_are_accepted(
    chart_block_factory: Callable[..., BlockIR],
    orientation: ChartOrientation,
) -> None:
    block = chart_block_factory(orientation=orientation)

    assert build_chart_spec(block).orientation == orientation


def test_unknown_block_kind_is_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(kind="pie")

    with pytest.raises(ChartSpecError, match="pilih bar, line, donut"):
        build_chart_spec(block)


@pytest.mark.parametrize(
    "chart_id",
    ["s01:chart1", "s01 chart1"],
    ids=["colon", "whitespace"],
)
def test_explicit_chart_id_must_be_marker_safe(chart_id: str) -> None:
    with pytest.raises(ChartSpecError, match="chart_id"):
        build_chart_spec(_raw_chart_block(), chart_id=chart_id)


def test_chart_spec_rejects_invalid_kind_directly() -> None:
    with pytest.raises(ChartSpecError, match="kind chart harus"):
        ChartSpec(
            chart_id="s01.chart1",
            kind="pie",
            categories=("Q1", "Q2"),
            series=(ChartSeries(name="Seri 1", values=(1, 2)),),
            orientation=None,
            title="Judul",
            alt="Alt",
        )


def test_chart_spec_rejects_non_list_categories_directly() -> None:
    with pytest.raises(ChartSpecError, match="categories chart"):
        ChartSpec(
            chart_id="s01.chart1",
            kind="bar",
            categories="Q1,Q2",
            series=(ChartSeries(name="Seri 1", values=(1, 2)),),
            orientation="vertical",
            title="Judul",
            alt="Alt",
        )


def test_chart_spec_rejects_non_list_series_directly() -> None:
    with pytest.raises(ChartSpecError, match="series chart"):
        ChartSpec(
            chart_id="s01.chart1",
            kind="bar",
            categories=("Q1", "Q2"),
            series=ChartSeries(name="Seri 1", values=(1, 2)),
            orientation="vertical",
            title="Judul",
            alt="Alt",
        )


def test_chart_spec_rejects_non_chart_series_item_directly() -> None:
    with pytest.raises(ChartSpecError, match="wajib berupa ChartSeries"):
        ChartSpec(
            chart_id="s01.chart1",
            kind="bar",
            categories=("Q1", "Q2"),
            series=(object(),),
            orientation="vertical",
            title="Judul",
            alt="Alt",
        )


def test_chart_spec_rejects_non_text_title_directly() -> None:
    with pytest.raises(ChartSpecError, match="title"):
        ChartSpec(
            chart_id="s01.chart1",
            kind="bar",
            categories=("Q1", "Q2"),
            series=(ChartSeries(name="Seri 1", values=(1, 2)),),
            orientation="vertical",
            title=1,
            alt="Alt",
        )


def test_bar_with_one_category_is_rejected(
    chart_block_factory: Callable[..., BlockIR],
) -> None:
    block = chart_block_factory(
        categories=("Solo",),
        series=(ChartSeries(name="Seri 1", values=(1,)),),
    )

    with pytest.raises(ChartSpecError, match="minimal dua kategori"):
        build_chart_spec(block)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"categories": "Q1,Q2"}, "categories"),
        ({"series": "bukan-daftar"}, "series"),
        ({"series": (object(),)}, "wajib berupa mapping atau ChartSeries"),
        ({"series": ({"name": "Seri 1"},)}, "name dan values"),
        ({"series": ({"name": "Seri 1", "values": "12"},)}, "values"),
        ({"title": 123}, "title"),
    ],
    ids=["categories", "series", "series-item", "missing-values", "values", "title"],
)
def test_raw_block_field_shape_is_rejected(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ChartSpecError, match=match):
        build_chart_spec(_raw_chart_block(**overrides))


def test_direct_series_values_must_be_list() -> None:
    with pytest.raises(ChartSpecError, match="daftar angka"):
        ChartSpec(
            chart_id="s01.chart1",
            kind="bar",
            categories=("Q1", "Q2"),
            series=(ChartSeries(name="Seri 1", values="12"),),
            orientation="vertical",
            title="Judul",
            alt="Alt",
        )
