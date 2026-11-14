"""Placeholder chart deterministik untuk staging Google Slides."""

from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.shapes.autoshape import Shape
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.design.theme import Theme

from .colors import rgb_from_hex
from .spec import ChartSpec, ChartSpecError

CHART_MARKER_PREFIX = "autooffice:chart:"


def chart_marker(chart_id: str) -> str:
    """Bentuk marker nama dan alt placeholder untuk satu ``chart_id``."""
    if not isinstance(chart_id, str) or not chart_id.strip():
        raise ChartSpecError("chart_id placeholder wajib berupa teks non-kosong.")
    if ":" in chart_id or any(character.isspace() for character in chart_id):
        raise ChartSpecError(f"chart_id placeholder tidak valid: {chart_id!r}.")
    return f"{CHART_MARKER_PREFIX}{chart_id}"


def parse_chart_marker(value: str) -> str | None:
    """Kembalikan ``chart_id`` bila ``value`` adalah marker placeholder persis."""
    if not value.startswith(CHART_MARKER_PREFIX):
        return None
    chart_id = value[len(CHART_MARKER_PREFIX) :]
    if not chart_id or ":" in chart_id or any(character.isspace() for character in chart_id):
        return None
    return chart_id


def create_chart_placeholder(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
) -> Shape:
    """Buat shape placeholder pada box chart tanpa chart object native.

    Nama shape dan ``title`` berisi marker deterministik; ``descr`` berisi alt
    manusia agar Google Slides dapat mencari berdasarkan nama dan alt title
    tanpa kehilangan deskripsi aksesibilitas.
    """
    marker = chart_marker(spec.chart_id)
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Emu(left),
        Emu(top),
        Emu(width),
        Emu(height),
    )
    shape.name = marker
    shape.fill.background()
    shape.line.color.rgb = rgb_from_hex(theme.colors.border)
    shape.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    c_nv_pr = shape._element.nvSpPr.cNvPr
    c_nv_pr.set("title", marker)
    c_nv_pr.set("descr", spec.alt)
    return shape


def chart_placeholder_id(shape: Shape) -> str | None:
    """Kembalikan ``chart_id`` bila shape adalah placeholder chart yang valid."""
    name_id = parse_chart_marker(shape.name)
    if name_id is None:
        return None
    title = shape._element.nvSpPr.cNvPr.get("title")
    if title is None or parse_chart_marker(title) != name_id:
        return None
    return name_id


def find_chart_placeholders(slide: Slide) -> tuple[Shape, ...]:
    """Kumpulkan seluruh placeholder chart pada slide sesuai urutan shape."""
    placeholders: list[Shape] = []
    for shape in slide.shapes:
        if isinstance(shape, Shape) and chart_placeholder_id(shape) is not None:
            placeholders.append(shape)
    return tuple(placeholders)


__all__ = [
    "CHART_MARKER_PREFIX",
    "chart_marker",
    "chart_placeholder_id",
    "create_chart_placeholder",
    "find_chart_placeholders",
    "parse_chart_marker",
]
