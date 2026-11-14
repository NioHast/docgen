"""Test marker dan shape placeholder chart untuk staging Slides."""

from collections.abc import Mapping

import pytest
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.charts import (
    ChartSpec,
    ChartSpecError,
    chart_marker,
    chart_placeholder_id,
    find_chart_placeholders,
    parse_chart_marker,
)
from autooffice.deck.render.pptx.chart import add_chart_placeholder
from autooffice.design.theme import Theme


def test_chart_marker_is_exact() -> None:
    assert chart_marker("s04.chart1") == "autooffice:chart:s04.chart1"


def test_parse_chart_marker_round_trips() -> None:
    assert parse_chart_marker("autooffice:chart:s04.chart1") == "s04.chart1"


@pytest.mark.parametrize(
    "value",
    [
        "s04.chart1",
        "autooffice:chart:",
        "autooffice:chart:s04 chart1",
        "autooffice:chart:s04:chart1",
    ],
    ids=["no-prefix", "empty-id", "space", "colon"],
)
def test_parse_chart_marker_rejects_non_marker(value: str) -> None:
    assert parse_chart_marker(value) is None


def test_chart_marker_rejects_invalid_chart_id() -> None:
    with pytest.raises(ChartSpecError, match="chart_id placeholder"):
        chart_marker("s04 chart1")


def test_chart_marker_rejects_non_string() -> None:
    with pytest.raises(ChartSpecError, match="teks non-kosong"):
        chart_marker(123)  # type: ignore[arg-type]


def test_placeholder_has_exact_marker_and_box(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    presentation,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s02.chart1"]
    marker = chart_marker(spec.chart_id)

    shape = add_chart_placeholder(slide, spec, theme, **chart_box)

    c_nv_pr = shape._element.nvSpPr.cNvPr
    assert shape.name == marker
    assert c_nv_pr.get("title") == marker
    assert c_nv_pr.get("descr") == spec.alt
    assert shape.left == Emu(chart_box["left"])
    assert shape.top == Emu(chart_box["top"])
    assert shape.width == Emu(chart_box["width"])
    assert shape.height == Emu(chart_box["height"])
    assert shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
    assert chart_placeholder_id(shape) == spec.chart_id

    part_names = {str(part.partname) for part in presentation.part.package.iter_parts()}
    assert not any(name.startswith("/ppt/charts/") for name in part_names)
    assert not any(name.startswith("/ppt/media/") for name in part_names)


def test_find_chart_placeholders_only_returns_markers(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    placeholder = add_chart_placeholder(slide, chart_specs["s01.chart1"], theme, **chart_box)
    textbox = slide.shapes.add_textbox(Emu(0), Emu(0), Emu(100), Emu(100))
    textbox.name = "bukan-placeholder"

    assert find_chart_placeholders(slide) == (placeholder,)


def test_placeholder_id_requires_matching_title(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    placeholder = add_chart_placeholder(slide, chart_specs["s01.chart1"], theme, **chart_box)
    placeholder._element.nvSpPr.cNvPr.set("title", "judul-lain")

    assert chart_placeholder_id(placeholder) is None
    assert find_chart_placeholders(slide) == ()
