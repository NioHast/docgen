"""Tes cabang edge theme OOXML: layout fallback dan elemen skema hilang."""

from types import SimpleNamespace

import pytest
from lxml import etree
from pptx.oxml.ns import qn

from autooffice.deck.render.pptx.shapes import PptxRenderError, primary_typeface
from autooffice.deck.render.pptx.theme import (
    _apply_color_scheme,
    _apply_font_scheme,
    _apply_theme_xml,
    blank_layout,
)


def test_blank_layout_falls_back_to_layout_without_placeholders() -> None:
    filled = SimpleNamespace(name="Isi", placeholders=[object()])
    empty = SimpleNamespace(name="Kosong", placeholders=[])
    presentation = SimpleNamespace(slide_layouts=[filled, empty])

    assert blank_layout(presentation) is empty


def test_blank_layout_raises_when_no_blank_layout_exists() -> None:
    presentation = SimpleNamespace(
        slide_layouts=[SimpleNamespace(name="Isi", placeholders=[object()])],
    )

    with pytest.raises(PptxRenderError, match="tidak memiliki layout blank"):
        blank_layout(presentation)


def test_apply_theme_xml_wraps_invalid_xml(theme) -> None:
    class FakePart:
        blob = b"<bukan xml"

    class FakeMaster:
        part = SimpleNamespace(part_related_by=lambda relationship: FakePart())

    presentation = SimpleNamespace(slide_masters=[FakeMaster()])

    with pytest.raises(PptxRenderError, match="bukan XML valid"):
        _apply_theme_xml(presentation, theme)


def test_apply_color_scheme_requires_scheme(theme) -> None:
    root = etree.Element(qn("a:theme"))

    with pytest.raises(PptxRenderError, match="tidak memiliki a:clrScheme"):
        _apply_color_scheme(root, theme)


def test_apply_color_scheme_creates_missing_entries(theme) -> None:
    root = etree.Element(qn("a:theme"))
    scheme = etree.SubElement(root, qn("a:clrScheme"))

    _apply_color_scheme(root, theme)

    for name in ("dk1", "lt1", "dk2", "lt2", "accent1", "accent6", "hlink", "folHlink"):
        element = scheme.find(qn(f"a:{name}"))
        assert element is not None
        color = element.find(qn("a:srgbClr"))
        assert color is not None
        value = color.get("val", "")
        assert len(value) == 6
        assert value == value.upper()
    accent1 = scheme.find(qn("a:accent1"))
    assert accent1 is not None
    accent_color = accent1.find(qn("a:srgbClr"))
    assert accent_color is not None
    assert accent_color.get("val") == theme.colors.accent[1:].upper()


def test_apply_font_scheme_requires_scheme(theme) -> None:
    root = etree.Element(qn("a:theme"))

    with pytest.raises(PptxRenderError, match="tidak memiliki a:fontScheme"):
        _apply_font_scheme(root, theme)


def test_apply_font_scheme_requires_major_and_minor_fonts(theme) -> None:
    root = etree.Element(qn("a:theme"))
    etree.SubElement(root, qn("a:fontScheme"))

    with pytest.raises(PptxRenderError, match="tidak memiliki a:majorFont"):
        _apply_font_scheme(root, theme)


def test_apply_font_scheme_creates_missing_font_children_and_clears_attributes(theme) -> None:
    root = etree.Element(qn("a:theme"))
    scheme = etree.SubElement(root, qn("a:fontScheme"))
    major = etree.SubElement(scheme, qn("a:majorFont"))
    etree.SubElement(scheme, qn("a:minorFont"))
    latin = etree.SubElement(major, qn("a:latin"))
    latin.set("panose", "0000000000000000000000000000000000000000")
    latin.set("pitchFamily", "34")
    latin.set("charset", "0")

    _apply_font_scheme(root, theme)

    family = primary_typeface(theme.typography.family)
    for kind in ("majorFont", "minorFont"):
        font = scheme.find(qn(f"a:{kind}"))
        assert font is not None
        for tag in ("a:latin", "a:ea", "a:cs"):
            element = font.find(qn(tag))
            assert element is not None
            assert element.get("typeface") == family
            assert element.get("panose") is None
            assert element.get("pitchFamily") is None
            assert element.get("charset") is None
