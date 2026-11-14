"""Presentasi 16:9 dan theme OOXML yang dihasilkan dari token desain."""

from datetime import datetime

from lxml import etree
from pptx import Presentation as PresentationFactory
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.presentation import Presentation
from pptx.slide import Slide, SlideLayout
from pptx.util import Emu

from autooffice.design.theme import Theme

from .shapes import PptxRenderError, primary_typeface, rgb

FIXED_DOCUMENT_TIME = datetime(2000, 1, 1)
_BLANK_LAYOUT_NAME = "Blank"
_COLOR_SCHEME_ORDER = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)


def new_presentation(theme: Theme, *, deck_title: str, author: str) -> Presentation:
    """Buat presentasi kosong dengan ukuran dan theme OOXML dari token."""
    presentation = PresentationFactory()
    presentation.slide_width = Emu(theme.grid.slide_width_emu)
    presentation.slide_height = Emu(theme.grid.slide_height_emu)
    _apply_theme_xml(presentation, theme)
    _set_core_properties(presentation, deck_title=deck_title, author=author)
    return presentation


def blank_layout(presentation: Presentation) -> SlideLayout:
    """Kembalikan layout blank library tanpa placeholder yang dipakai."""
    for layout in presentation.slide_layouts:
        if layout.name == _BLANK_LAYOUT_NAME:
            return layout
    for layout in presentation.slide_layouts:
        if len(layout.placeholders) == 0:
            return layout
    raise PptxRenderError("Template library python-pptx tidak memiliki layout blank.")


def apply_slide_background(slide: Slide, theme: Theme) -> None:
    """Isi background slide dari token warna theme."""
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(theme.colors.background)


def _apply_theme_xml(presentation: Presentation, theme: Theme) -> None:
    part = presentation.slide_masters[0].part.part_related_by(RT.THEME)
    try:
        root = parse_xml(part.blob)
    except etree.XMLSyntaxError as error:
        raise PptxRenderError("Theme part PPTX bukan XML valid.") from error
    root.set("name", f"AutoOffice {theme.name}")
    _apply_color_scheme(root, theme)
    _apply_font_scheme(root, theme)
    part.blob = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


def _apply_color_scheme(root: etree._Element, theme: Theme) -> None:
    scheme = root.find(".//" + qn("a:clrScheme"))
    if scheme is None:
        raise PptxRenderError("Theme OOXML tidak memiliki a:clrScheme.")
    for name, color in zip(_COLOR_SCHEME_ORDER, _scheme_colors(theme), strict=True):
        element = scheme.find(qn(f"a:{name}"))
        if element is None:
            element = etree.SubElement(scheme, qn(f"a:{name}"))
        for child in list(element):
            element.remove(child)
        color_element = etree.SubElement(element, qn("a:srgbClr"))
        color_element.set("val", color[1:].upper())


def _scheme_colors(theme: Theme) -> tuple[str, ...]:
    colors = theme.colors
    series = theme.chart.series
    return (
        colors.ink,
        colors.background,
        colors.ink_secondary,
        colors.surface,
        colors.accent,
        series[1],
        series[2],
        series[3],
        colors.accent_deep,
        colors.muted,
        colors.accent,
        colors.muted,
    )


def _apply_font_scheme(root: etree._Element, theme: Theme) -> None:
    scheme = root.find(".//" + qn("a:fontScheme"))
    if scheme is None:
        raise PptxRenderError("Theme OOXML tidak memiliki a:fontScheme.")
    family = primary_typeface(theme.typography.family)
    scheme.set("name", f"AutoOffice {theme.name}")
    for kind in ("majorFont", "minorFont"):
        font = scheme.find(qn(f"a:{kind}"))
        if font is None:
            raise PptxRenderError(f"Theme OOXML tidak memiliki a:{kind}.")
        for tag in ("a:latin", "a:ea", "a:cs"):
            element = font.find(qn(tag))
            if element is None:
                element = etree.SubElement(font, qn(tag))
            element.set("typeface", family)
            for attribute in ("panose", "pitchFamily", "charset"):
                element.attrib.pop(attribute, None)


def _set_core_properties(presentation: Presentation, *, deck_title: str, author: str) -> None:
    properties = presentation.core_properties
    properties.title = deck_title
    properties.author = author
    properties.last_modified_by = author
    properties.category = "AutoOffice"
    properties.comments = ""
    properties.revision = 1
    properties.created = FIXED_DOCUMENT_TIME
    properties.modified = FIXED_DOCUMENT_TIME
