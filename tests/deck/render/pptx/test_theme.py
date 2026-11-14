"""Tes ukuran 16:9, theme OOXML, background slide, dan core properties."""

from datetime import datetime

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn

from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.theme import FIXED_DOCUMENT_TIME, blank_layout
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def _render_minimal(case, theme):
    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=case.workspace,
        )
    )


def test_presentation_uses_theme_16_9_dimensions(minimal_case, theme) -> None:
    result = _render_minimal(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))

    assert presentation.slide_width == theme.grid.slide_width_emu
    assert presentation.slide_height == theme.grid.slide_height_emu
    assert presentation.slide_width / presentation.slide_height == 16 / 9
    assert blank_layout(presentation).name == "Blank"
    assert all(not shape.is_placeholder for shape in presentation.slides[0].shapes)


def test_theme_xml_contains_token_colors_and_font(minimal_case, theme) -> None:
    result = _render_minimal(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))
    part = presentation.slide_masters[0].part.part_related_by(RT.THEME)
    root = parse_xml(part.blob)
    scheme = root.find(".//" + qn("a:clrScheme"))
    font_scheme = root.find(".//" + qn("a:fontScheme"))

    assert root.get("name") == f"AutoOffice {theme.name}"
    assert scheme is not None
    assert _scheme_color(scheme, "accent1") == theme.colors.accent[1:].upper()
    assert _scheme_color(scheme, "lt1") == theme.colors.background[1:].upper()
    assert _scheme_color(scheme, "dk1") == theme.colors.ink[1:].upper()
    assert font_scheme is not None
    latin = font_scheme.find(".//" + qn("a:latin"))
    assert latin is not None
    assert latin.get("typeface") == theme.typography.family


def test_slide_background_and_core_properties_follow_tokens(minimal_case, theme) -> None:
    result = _render_minimal(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))
    first = presentation.slides[0]

    assert first.background.fill.fore_color.rgb == _rgb(theme.colors.background)
    assert presentation.core_properties.title == "Minimal Deck"
    assert presentation.core_properties.author == "AutoOffice"
    assert presentation.core_properties.created == FIXED_DOCUMENT_TIME
    assert presentation.core_properties.modified == FIXED_DOCUMENT_TIME


def test_fixed_document_time_is_deterministic() -> None:
    assert datetime(2000, 1, 1) == FIXED_DOCUMENT_TIME


def _scheme_color(scheme: etree._Element, name: str) -> str:
    element = scheme.find(qn(f"a:{name}"))
    assert element is not None
    color = element.find(qn("a:srgbClr"))
    assert color is not None
    return color.get("val", "")


def _rgb(color: str) -> object:
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(color[1:])
