"""Test chart native PPTX: part, data, metadata, warna, dan format theme."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide

from autooffice.deck.charts import (
    ChartSpec,
    ChartSpecError,
    chart_marker,
    native_chart_type,
    validate_native_chart,
)
from autooffice.deck.model import ChartSeries
from autooffice.deck.render.pptx.chart import add_native_chart
from autooffice.design.theme import Theme

_CHART_IDS = ("s01.chart1", "s02.chart1", "s03.chart1", "s04.chart1")


def _rgb(value: object) -> str:
    return f"#{value}"


def _add(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    chart_box: Mapping[str, int],
) -> GraphicFrame:
    return add_native_chart(slide, spec, theme, **chart_box)


@pytest.mark.parametrize(
    ("chart_id", "expected"),
    [
        ("s01.chart1", XL_CHART_TYPE.COLUMN_CLUSTERED),
        ("s02.chart1", XL_CHART_TYPE.BAR_CLUSTERED),
        ("s03.chart1", XL_CHART_TYPE.LINE_MARKERS),
        ("s04.chart1", XL_CHART_TYPE.DOUGHNUT),
    ],
)
def test_native_chart_type(
    chart_id: str,
    expected: XL_CHART_TYPE,
    chart_specs: Mapping[str, ChartSpec],
) -> None:
    assert native_chart_type(chart_specs[chart_id]) == expected


@pytest.mark.parametrize("chart_id", _CHART_IDS)
def test_native_chart_parts_have_no_image(
    chart_id: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    presentation: Presentation,
    chart_box: Mapping[str, int],
    tmp_path: Path,
) -> None:
    frame = _add(slide, chart_specs[chart_id], theme, chart_box)
    output = tmp_path / "chart.pptx"
    presentation.save(output)

    assert frame.has_chart is True
    assert frame.shape_type == MSO_SHAPE_TYPE.CHART
    assert not any(
        shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in presentation.slides[0].shapes
    )

    loaded = Presentation(output)
    loaded_frame = loaded.slides[0].shapes[0]
    assert isinstance(loaded_frame, GraphicFrame)
    assert loaded_frame.has_chart is True
    part_names = {str(part.partname) for part in loaded.part.package.iter_parts()}
    assert any(name.startswith("/ppt/charts/chart") for name in part_names)
    assert any(name.startswith("/ppt/embeddings/") for name in part_names)
    assert not any(name.startswith("/ppt/media/") for name in part_names)


@pytest.mark.parametrize("chart_id", _CHART_IDS)
def test_categories_and_series_match_spec(
    chart_id: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs[chart_id]
    frame = _add(slide, spec, theme, chart_box)
    chart = frame.chart

    assert tuple(str(category) for category in chart.plots[0].categories) == spec.categories
    assert tuple(str(series.name) for series in chart.series) == tuple(
        series.name for series in spec.series
    )
    assert tuple(
        tuple(float(value) for value in series.values) for series in chart.series
    ) == tuple(tuple(float(value) for value in series.values) for series in spec.series)
    validate_native_chart(chart, spec)


def test_native_chart_metadata_is_deterministic(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    c_nv_pr = frame._element.nvGraphicFramePr.cNvPr

    assert frame.name == chart_marker(spec.chart_id)
    assert c_nv_pr.get("title") == spec.chart_id
    assert c_nv_pr.get("descr") == spec.alt
    assert frame.chart.has_title is True
    assert frame.chart.chart_title.text_frame.text == spec.title


@pytest.mark.parametrize("chart_id", ["s01.chart1", "s03.chart1"])
def test_bar_and_line_series_use_four_theme_colors(
    chart_id: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs[chart_id]
    frame = _add(slide, spec, theme, chart_box)
    chart = frame.chart

    if spec.kind == "bar":
        actual = tuple(_rgb(series.format.fill.fore_color.rgb) for series in chart.series)
    else:
        actual = tuple(_rgb(series.format.line.color.rgb) for series in chart.series)

    assert actual == theme.chart.series[: len(spec.series)]


def test_donut_categories_use_theme_series_colors(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s04.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    series = frame.chart.series[0]

    actual = tuple(_rgb(series.points[index].format.fill.fore_color.rgb) for index in range(4))

    assert actual == theme.chart.series


def test_chart_font_legend_gridlines_and_axis_come_from_theme(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s01.chart1"], theme, chart_box)
    chart = frame.chart

    assert chart.font.name == theme.typography.family
    assert chart.has_legend is True
    assert chart.legend.font.name == theme.typography.family
    assert _rgb(chart.legend.font.color.rgb) == theme.chart.legend
    assert chart.value_axis.has_major_gridlines is True
    assert _rgb(chart.value_axis.major_gridlines.format.line.color.rgb) == theme.chart.grid
    assert _rgb(chart.value_axis.format.line.color.rgb) == theme.chart.axis
    assert _rgb(chart.value_axis.tick_labels.font.color.rgb) == theme.chart.axis
    title_font = chart.chart_title.text_frame.paragraphs[0].font
    assert title_font.name == theme.typography.family
    assert _rgb(title_font.color.rgb) == theme.chart.title


def test_single_series_bar_and_donut_legend_rules(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    bar = _add(slide, chart_specs["s02.chart1"], theme, chart_box)
    donut = _add(slide, chart_specs["s04.chart1"], theme, chart_box)

    assert bar.chart.has_legend is False
    assert donut.chart.has_legend is True


def test_line_markers_and_unit_axis(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s03.chart1"], theme, chart_box)
    chart = frame.chart

    assert all(series.marker.style == XL_MARKER_STYLE.CIRCLE for series in chart.series)
    assert chart.value_axis.has_title is True
    assert chart.value_axis.axis_title.text_frame.text == "persen"


def test_validation_rejects_wrong_chart_spec(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s01.chart1"], theme, chart_box)

    with pytest.raises(ChartSpecError, match="seharusnya"):
        validate_native_chart(frame.chart, chart_specs["s03.chart1"])


def test_validation_rejects_category_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    wrong = replace(spec, categories=("X1", "X2", "X3", "X4"))

    with pytest.raises(ChartSpecError, match="Kategori"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_series_count_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    wrong = replace(spec, series=spec.series[:1])

    with pytest.raises(ChartSpecError, match="memiliki 4 seri"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_series_name_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    first = spec.series[0]
    wrong = replace(
        spec,
        series=(ChartSeries(name="Lain", values=first.values), *spec.series[1:]),
    )

    with pytest.raises(ChartSpecError, match="bernama"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_series_value_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    first = spec.series[0]
    wrong = replace(
        spec,
        series=(ChartSeries(name=first.name, values=(0, 0, 0, 0)), *spec.series[1:]),
    )

    with pytest.raises(ChartSpecError, match="Nilai seri"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_title_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    wrong = replace(spec, title="Judul lain")

    with pytest.raises(ChartSpecError, match="Title chart"):
        validate_native_chart(frame.chart, wrong)
