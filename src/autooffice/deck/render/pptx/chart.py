"""Integrasi chart native dan placeholder untuk renderer PPTX AutoOffice."""

from typing import cast

from pptx.chart.data import ChartData
from pptx.shapes.autoshape import Shape
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.charts.native import (
    build_category_chart_data,
    format_native_chart,
    native_chart_type,
    validate_native_chart,
)
from autooffice.deck.charts.placeholder import (
    CHART_MARKER_PREFIX,
    chart_marker,
    chart_placeholder_id,
    create_chart_placeholder,
    find_chart_placeholders,
    parse_chart_marker,
)
from autooffice.deck.charts.spec import ChartSpec
from autooffice.deck.layout.measure import measure_text
from autooffice.design.theme import Theme

from .shapes import Box, PptxRenderError
from .textbox import add_caption

__all__ = [
    "CHART_MARKER_PREFIX",
    "add_chart_placeholder",
    "add_native_chart",
    "chart_id_from_shape",
    "chart_marker",
    "find_chart_placeholders",
    "render_chart",
]


def add_native_chart(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    caption: str = "",
) -> GraphicFrame:
    """Tambahkan satu chart native pada box block dan kembalikan frame-nya."""
    chart_height, caption_box = _caption_layout(
        spec,
        theme,
        left=left,
        top=top,
        width=width,
        height=height,
        caption=caption,
    )
    data = build_category_chart_data(spec)
    result = slide.shapes.add_chart(
        native_chart_type(spec),
        Emu(left),
        Emu(top),
        Emu(width),
        Emu(chart_height),
        cast(ChartData, data),
    )
    frame = cast(GraphicFrame, result)
    frame.name = chart_marker(spec.chart_id)
    c_nv_pr = frame._element.nvGraphicFramePr.cNvPr
    c_nv_pr.set("title", spec.chart_id)
    c_nv_pr.set("descr", spec.alt)
    format_native_chart(frame.chart, spec, theme)
    validate_native_chart(frame.chart, spec)
    _add_chart_caption(slide, spec, theme, caption=caption, caption_box=caption_box)
    return frame


def add_chart_placeholder(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    caption: str = "",
) -> Shape:
    """Tambahkan placeholder chart pada box block untuk staging Slides."""
    chart_height, caption_box = _caption_layout(
        spec,
        theme,
        left=left,
        top=top,
        width=width,
        height=height,
        caption=caption,
    )
    shape = create_chart_placeholder(
        slide,
        spec,
        theme,
        left=left,
        top=top,
        width=width,
        height=chart_height,
    )
    _add_chart_caption(slide, spec, theme, caption=caption, caption_box=caption_box)
    return shape


def render_chart(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    placeholder: bool = False,
    caption: str = "",
) -> GraphicFrame | Shape:
    """Render chart dan caption opsional di bawahnya.

    Caption memakai text box berkey sendiri, sehingga chart frame harus
    dipendekkan sebesar tinggi caption ditambah jarak ``sm``.
    """
    if placeholder:
        return add_chart_placeholder(
            slide,
            spec,
            theme,
            left=left,
            top=top,
            width=width,
            height=height,
            caption=caption,
        )
    return add_native_chart(
        slide,
        spec,
        theme,
        left=left,
        top=top,
        width=width,
        height=height,
        caption=caption,
    )


def _caption_layout(
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    caption: str,
) -> tuple[int, Box | None]:
    """Hitung tinggi chart dan kotak caption opsional di bawahnya."""
    if not caption.strip():
        return height, None
    caption_height = measure_text(
        caption,
        available_width_emu=width,
        theme=theme,
        font_size_pt=theme.typography.body_pt,
        weight=400,
    ).height_emu
    gap = theme.spacing.sm_emu
    chart_height = height - caption_height - gap
    if chart_height <= 0:
        raise PptxRenderError(
            f"Kotak chart '{spec.chart_id}' tidak menyisakan ruang chart setelah caption."
        )
    caption_box = Box(
        left=left,
        top=top + chart_height + gap,
        width=width,
        height=caption_height,
    )
    return chart_height, caption_box


def _add_chart_caption(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    caption: str,
    caption_box: Box | None,
) -> None:
    """Render caption chart sebagai text box berkey bila kotaknya tersedia."""
    if caption_box is None:
        return
    add_caption(
        slide,
        caption_box,
        key=f"{spec.chart_id}.caption",
        text=caption,
        theme=theme,
    )


def chart_id_from_shape(shape: BaseShape) -> str | None:
    """Baca ``chart_id`` dari chart native atau placeholder, bila ada."""
    if isinstance(shape, GraphicFrame) and shape.has_chart:
        return parse_chart_marker(shape.name)
    if isinstance(shape, Shape):
        return chart_placeholder_id(shape)
    return None
