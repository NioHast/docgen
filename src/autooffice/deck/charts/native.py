"""Pembentuk chart native python-pptx dari ``ChartSpec`` dan ``Theme``."""

from pptx.chart.chart import Chart
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.text.text import Font
from pptx.util import Pt

from autooffice.design.theme import Theme

from .colors import chart_category_colors, chart_element_color, chart_series_colors
from .spec import ChartSpec, ChartSpecError

_LINE_MARKER_SIZE = 6


def build_category_chart_data(spec: ChartSpec) -> CategoryChartData:
    """Bangun data kategori native yang akan ditanam sebagai workbook PPTX."""
    data = CategoryChartData()  # type: ignore[no-untyped-call]
    data.categories = list(spec.categories)
    for series in spec.series:
        data.add_series(series.name, list(series.values))  # type: ignore[no-untyped-call]
    return data


def native_chart_type(spec: ChartSpec) -> XL_CHART_TYPE:
    """Pilih tipe chart native sesuai kind dan orientation."""
    if spec.kind == "bar":
        if spec.orientation == "horizontal":
            return XL_CHART_TYPE.BAR_CLUSTERED
        return XL_CHART_TYPE.COLUMN_CLUSTERED
    if spec.kind == "line":
        return XL_CHART_TYPE.LINE_MARKERS
    return XL_CHART_TYPE.DOUGHNUT


def format_native_chart(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    """Terapkan title, legend, axis, gridline, font, dan warna token."""
    chart.font.name = theme.typography.family
    chart.font.size = Pt(theme.typography.minimum_pt)
    chart.font.color.rgb = chart_element_color(theme, "axis")
    _format_title(chart, spec, theme)
    _format_legend(chart, spec, theme)
    if spec.kind == "donut":
        _format_donut_series(chart, spec, theme)
        return
    _format_axes(chart, spec, theme)
    _format_category_series(chart, spec, theme)


def validate_native_chart(chart: Chart, spec: ChartSpec) -> None:
    """Pastikan chart native memuat tipe, data, dan title sesuai spec."""
    expected_type = native_chart_type(spec)
    if chart.chart_type != expected_type:
        raise ChartSpecError(
            f"Chart '{spec.chart_id}' bertipe {chart.chart_type}, seharusnya {expected_type}."
        )
    actual_categories = tuple(str(category) for category in chart.plots[0].categories)
    if actual_categories != spec.categories:
        raise ChartSpecError(
            f"Kategori chart '{spec.chart_id}' tidak cocok: "
            f"{actual_categories!r} != {spec.categories!r}."
        )
    actual_series = tuple(chart.series)
    if len(actual_series) != len(spec.series):
        raise ChartSpecError(
            f"Chart '{spec.chart_id}' memiliki {len(actual_series)} seri, "
            f"seharusnya {len(spec.series)}."
        )
    for index, (actual, expected) in enumerate(zip(actual_series, spec.series, strict=True)):
        if str(actual.name) != expected.name:
            raise ChartSpecError(
                f"Seri {index} chart '{spec.chart_id}' bernama '{actual.name}', "
                f"seharusnya '{expected.name}'."
            )
        actual_values = tuple(float(value) for value in actual.values)
        expected_values = tuple(float(value) for value in expected.values)
        if actual_values != expected_values:
            raise ChartSpecError(
                f"Nilai seri '{expected.name}' chart '{spec.chart_id}' tidak cocok."
            )
    if not chart.has_title or chart.chart_title.text_frame.text != spec.title:
        raise ChartSpecError(f"Title chart '{spec.chart_id}' tidak cocok dengan spec.")


def _format_title(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    chart.has_title = True
    text_frame = chart.chart_title.text_frame
    text_frame.text = spec.title
    _apply_font(
        text_frame.paragraphs[0].font,
        theme=theme,
        size_pt=theme.typography.body_pt,
        color=chart_element_color(theme, "title"),
    )


def _format_legend(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    visible = spec.kind == "donut" or len(spec.series) > 1
    chart.has_legend = visible
    if not visible:
        return
    legend = chart.legend
    legend.position = XL_LEGEND_POSITION.RIGHT
    legend.include_in_layout = False
    _apply_font(
        legend.font,
        theme=theme,
        size_pt=theme.typography.minimum_pt,
        color=chart_element_color(theme, "legend"),
    )


def _format_axes(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    category_axis = chart.category_axis
    value_axis = chart.value_axis
    for axis in (category_axis, value_axis):
        axis.format.line.color.rgb = chart_element_color(theme, "axis")
        _apply_font(
            axis.tick_labels.font,
            theme=theme,
            size_pt=theme.typography.minimum_pt,
            color=chart_element_color(theme, "axis"),
        )
    category_axis.has_major_gridlines = False
    value_axis.has_major_gridlines = True
    value_axis.major_gridlines.format.line.color.rgb = chart_element_color(theme, "grid")
    if spec.unit is not None:
        value_axis.has_title = True
        value_axis.axis_title.text_frame.text = spec.unit
        _apply_font(
            value_axis.axis_title.text_frame.paragraphs[0].font,
            theme=theme,
            size_pt=theme.typography.minimum_pt,
            color=chart_element_color(theme, "axis"),
        )


def _format_category_series(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    colors = chart_series_colors(theme, len(spec.series))
    for series, color in zip(chart.series, colors, strict=True):
        if spec.kind == "line":
            series.format.line.color.rgb = color
            series.smooth = False
            series.marker.style = XL_MARKER_STYLE.CIRCLE
            series.marker.size = _LINE_MARKER_SIZE
            series.marker.format.fill.solid()
            series.marker.format.fill.fore_color.rgb = color
            series.marker.format.line.color.rgb = color
            continue
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
        series.format.line.color.rgb = color


def _format_donut_series(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    colors = chart_category_colors(theme, len(spec.categories))
    series = chart.series[0]
    for index, color in enumerate(colors):
        point = series.points[index]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = color


def _apply_font(font: Font, *, theme: Theme, size_pt: float, color: RGBColor) -> None:
    font.name = theme.typography.family
    font.size = Pt(size_pt)
    font.color.rgb = color


__all__ = [
    "build_category_chart_data",
    "format_native_chart",
    "native_chart_type",
    "validate_native_chart",
]
