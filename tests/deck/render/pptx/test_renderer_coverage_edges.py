"""Tes cabang edge coverage: slide mismatch, key lintas slide, dan alt hilang."""

import pytest
from _edge_helpers import binding, single_slide_deck
from pptx import Presentation
from pptx.util import Emu

from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyManifest, SlideIR
from autooffice.deck.render.pptx.coverage import (
    CoverageError,
    collect_coverage,
    raise_if_incomplete,
)
from autooffice.deck.render.pptx.shapes import (
    KEY_MARKER,
    PptxRenderError,
    set_keyed_shape,
    set_non_visual_properties,
)
from autooffice.deck.render.protocol import CoverageReport


def _presentation_with_slides(count: int) -> Presentation:
    presentation = Presentation()
    for _ in range(count):
        presentation.slides.add_slide(presentation.slide_layouts[6])
    return presentation


def _keyed_textbox(slide, key: str) -> None:
    shape = slide.shapes.add_textbox(Emu(0), Emu(0), Emu(100000), Emu(100000))
    shape.text_frame.text = "Judul"
    set_keyed_shape(shape, key, description="Judul")


def test_collect_coverage_rejects_slide_count_mismatch() -> None:
    presentation = Presentation()
    deck = single_slide_deck()

    with pytest.raises(PptxRenderError, match="Jumlah slide PPTX 0"):
        collect_coverage(presentation, deck)


def test_collect_coverage_marks_key_rendered_on_wrong_slide() -> None:
    presentation = _presentation_with_slides(2)
    for slide in presentation.slides:
        _keyed_textbox(slide, "s01.title.text")
    block = BlockIR("title", "text", None, "title", {"text": "Judul"})
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Cross Slide", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(
            SlideIR("s01", "content", 0, (block,), None, None),
            SlideIR("s02", "content", 1, (), None, None),
        ),
        keys=KeyManifest((binding("s01.title.text"),)),
    )

    report = collect_coverage(presentation, deck)

    assert "s02:s01.title.text" in report.unkeyed_visible


def test_collect_coverage_reads_key_marker_on_picture(workspace, hero_image) -> None:
    presentation = _presentation_with_slides(1)
    picture = presentation.slides[0].shapes.add_picture(
        str(workspace / hero_image),
        Emu(0),
        Emu(0),
        Emu(100_000),
        Emu(100_000),
    )
    set_keyed_shape(picture, "s01.orphan", description="Ilustrasi")
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Orphan Key", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (), None, None),),
        keys=KeyManifest((binding("s01.orphan", block_id="orphan", leaf="text"),)),
    )

    report = collect_coverage(presentation, deck)

    assert report.missing_keys == ()
    assert report.ok is True


def test_collect_coverage_ignores_empty_key_marker(workspace, hero_image) -> None:
    presentation = _presentation_with_slides(1)
    picture = presentation.slides[0].shapes.add_picture(
        str(workspace / hero_image),
        Emu(0),
        Emu(0),
        Emu(100_000),
        Emu(100_000),
    )
    set_non_visual_properties(picture, name=KEY_MARKER)
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Empty Key Marker", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (), None, None),),
        keys=KeyManifest(()),
    )

    report = collect_coverage(presentation, deck)

    assert report.unkeyed_visible == ()
    assert report.ok is True


def test_collect_coverage_marks_unkeyed_table_cell() -> None:
    presentation = _presentation_with_slides(1)
    slide = presentation.slides[0]
    frame = slide.shapes.add_table(1, 2, Emu(0), Emu(0), Emu(1_000_000), Emu(1_000_000))
    frame.table.cell(0, 0).text = "Tanpa key"
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Raw Table", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (), None, None),),
        keys=KeyManifest(()),
    )

    report = collect_coverage(presentation, deck)

    assert "s01:table.r1.c1" in report.unkeyed_visible


def test_collect_coverage_ignores_empty_notes_text() -> None:
    presentation = _presentation_with_slides(1)
    presentation.slides[0].notes_slide.notes_text_frame.text = ""
    deck = single_slide_deck()

    report = collect_coverage(presentation, deck)

    assert report.ok is True


def test_collect_coverage_marks_missing_alt_shape() -> None:
    presentation = _presentation_with_slides(1)
    block = BlockIR(
        "image1",
        "image",
        None,
        None,
        {"path": "assets/hero.png", "alt": "Deskripsi valid"},
    )
    deck = single_slide_deck((block,))

    report = collect_coverage(presentation, deck)

    assert report.missing_alt == ("s01.image1",)


def test_coverage_error_message_lists_duplicates() -> None:
    report = CoverageReport(
        missing_keys=(),
        duplicate_keys=("s01.title.text",),
        unkeyed_visible=(),
        missing_alt=(),
    )

    with pytest.raises(CoverageError, match="duplicate=") as error:
        raise_if_incomplete(report)

    assert "s01.title.text" in str(error.value)
