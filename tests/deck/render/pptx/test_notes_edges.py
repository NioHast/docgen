"""Tes cabang edge notes slide: kosong, tanpa text frame, dan metadata key."""

from types import SimpleNamespace

import pytest
from _edge_helpers import (
    has_percentage_line_spacing,
    line_spacing_points,
    new_slide,
    shape_with_metadata,
)
from pptx import Presentation

from autooffice.deck.render.pptx.notes import notes_key, notes_text, set_notes
from autooffice.deck.render.pptx.shapes import PptxRenderError


def test_set_notes_ignores_blank_text(theme) -> None:
    slide = new_slide()

    assert set_notes(slide, "   \n", slide_id="s01", theme=theme) is False
    assert slide.has_notes_slide is False


def test_set_notes_requires_notes_text_frame(theme) -> None:
    fake_slide = SimpleNamespace(
        notes_slide=SimpleNamespace(notes_text_frame=None),
    )

    with pytest.raises(PptxRenderError, match="tidak memiliki text frame"):
        set_notes(fake_slide, "Catatan", slide_id="s01", theme=theme)


def test_set_notes_allows_notes_slide_without_placeholder(theme) -> None:
    text_frame = new_slide().notes_slide.notes_text_frame
    fake_slide = SimpleNamespace(
        notes_slide=SimpleNamespace(
            notes_text_frame=text_frame,
            notes_placeholder=None,
        ),
    )

    assert set_notes(fake_slide, "Catatan", slide_id="s01", theme=theme) is True
    assert text_frame is not None
    assert text_frame.text == "Catatan"


def test_notes_text_returns_none_without_notes_slide() -> None:
    assert notes_text(new_slide()) is None


def test_notes_key_returns_none_without_notes_slide() -> None:
    assert notes_key(new_slide(), slide_id="s01") is None


def test_notes_key_returns_none_without_placeholder() -> None:
    fake_slide = SimpleNamespace(
        has_notes_slide=True,
        notes_slide=SimpleNamespace(notes_placeholder=None),
    )

    assert notes_key(fake_slide, slide_id="s01") is None


def test_notes_key_falls_back_to_slide_namespace() -> None:
    fake_slide = SimpleNamespace(
        has_notes_slide=True,
        notes_slide=SimpleNamespace(
            notes_placeholder=shape_with_metadata("Notes Placeholder 1"),
        ),
    )

    assert notes_key(fake_slide, slide_id="s01") == "s01.notes"


def test_notes_key_reads_keyed_placeholder(theme) -> None:
    slide = new_slide()
    set_notes(slide, "Catatan", slide_id="s01", theme=theme)

    assert notes_key(slide, slide_id="s01") == "s01.notes"


def test_notes_key_prefers_existing_shape_key() -> None:
    fake_slide = SimpleNamespace(
        has_notes_slide=True,
        notes_slide=SimpleNamespace(
            notes_placeholder=shape_with_metadata("autooffice:key:custom.notes"),
        ),
    )

    assert notes_key(fake_slide, slide_id="s01") == "custom.notes"


def test_notes_text_reads_created_notes(theme) -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    set_notes(slide, "Isi catatan", slide_id="s01", theme=theme)

    assert notes_text(slide) == "Isi catatan"


def test_set_notes_uses_exact_point_line_spacing(theme) -> None:
    slide = new_slide()
    set_notes(slide, "Baris satu\nBaris dua", slide_id="s01", theme=theme)
    text_frame = slide.notes_slide.notes_text_frame
    assert text_frame is not None
    font_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)
    expected_points = round(font_size_pt * theme.typography.line_height * 100)

    assert len(text_frame.paragraphs) == 2
    for paragraph in text_frame.paragraphs:
        assert has_percentage_line_spacing(paragraph) is False
        assert line_spacing_points(paragraph) == expected_points
