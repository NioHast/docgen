"""Test entry point renderer PPTX untuk dispatch chart native dan placeholder."""

from collections.abc import Mapping

from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.shapes.autoshape import Shape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.charts import ChartSpec
from autooffice.deck.render.pptx.chart import chart_id_from_shape, render_chart
from autooffice.design.theme import Theme


def test_render_chart_dispatches_native_by_default(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s03.chart1"]

    shape = render_chart(slide, spec, theme, **chart_box)

    assert isinstance(shape, GraphicFrame)
    assert shape.has_chart is True
    assert chart_id_from_shape(shape) == spec.chart_id


def test_render_chart_dispatches_placeholder_for_slides(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s04.chart1"]

    shape = render_chart(slide, spec, theme, placeholder=True, **chart_box)

    assert isinstance(shape, Shape)
    assert shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
    assert chart_id_from_shape(shape) == spec.chart_id


def test_chart_id_from_shape_ignores_unrelated_shape(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    textbox = slide.shapes.add_textbox(Emu(0), Emu(0), Emu(100), Emu(100))
    textbox.name = "bukan-chart"

    assert chart_id_from_shape(textbox) is None


def test_chart_id_from_shape_ignores_graphic_frame_without_chart(
    slide: Slide,
) -> None:
    table = slide.shapes.add_table(1, 1, Emu(0), Emu(0), Emu(100), Emu(100))

    assert chart_id_from_shape(table) is None
