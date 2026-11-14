"""Tes coverage nyata dari shape, table cell, notes, dan alt text."""

import pytest
from pptx import Presentation
from pptx.util import Emu

from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.coverage import CoverageError, collect_coverage
from autooffice.deck.render.pptx.shapes import set_keyed_shape
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def _deck(*, keys: tuple[KeyBinding, ...]) -> DeckIR:
    block = BlockIR("title", "text", None, "title", {"text": "Judul"})
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Coverage Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (block,), None, None),),
        keys=KeyManifest(keys),
    )


def _key(key: str) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id="s01",
        block_id="title",
        leaf="text",
        kind="text",
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, "text"),
        value="nilai",
        plain_text="nilai",
    )


def _blank_presentation() -> Presentation:
    presentation = Presentation()
    presentation.slides.add_slide(presentation.slide_layouts[6])
    return presentation


def _render(case, theme):
    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=case.workspace,
        )
    )


def test_missing_declared_key_is_reported() -> None:
    report = collect_coverage(_blank_presentation(), _deck(keys=(_key("s01.title.text"),)))

    assert report.ok is False
    assert report.missing_keys == ("s01.title.text",)


def test_duplicate_rendered_key_is_reported() -> None:
    presentation = _blank_presentation()
    slide = presentation.slides[0]
    for text in ("Pertama", "Kedua"):
        shape = slide.shapes.add_textbox(Emu(0), Emu(0), Emu(100000), Emu(100000))
        shape.text_frame.text = text
        set_keyed_shape(shape, "s01.title.text", description=text)

    report = collect_coverage(presentation, _deck(keys=(_key("s01.title.text"),)))

    assert report.duplicate_keys == ("s01.title.text",)
    assert report.ok is False


def test_visible_shape_without_key_is_reported() -> None:
    presentation = _blank_presentation()
    shape = presentation.slides[0].shapes.add_textbox(Emu(0), Emu(0), Emu(100000), Emu(100000))
    shape.text_frame.text = "Teks tanpa key"

    report = collect_coverage(presentation, _deck(keys=()))

    assert report.unkeyed_visible[0].startswith("s01:")
    assert report.ok is False


def test_missing_manifest_render_fails_without_final_artifact(
    missing_manifest_case,
    theme,
) -> None:
    with pytest.raises(CoverageError) as error:
        _render(missing_manifest_case, theme)

    assert "s01.title.text" in error.value.report.unkeyed_visible
    assert not (missing_manifest_case.workspace / "missing-manifest.pptx").exists()


def test_missing_image_alt_fails_render(
    missing_alt_case,
    theme,
) -> None:
    with pytest.raises(CoverageError) as error:
        _render(missing_alt_case, theme)

    assert error.value.report.missing_alt == ("s01.image1",)
    assert not (missing_alt_case.workspace / "missing-alt.pptx").exists()


def test_notes_text_is_counted_as_key() -> None:
    presentation = _blank_presentation()
    presentation.slides[0].notes_slide.notes_text_frame.text = "Catatan"
    notes_key = KeyBinding(
        key="s01.notes",
        slide_id="s01",
        block_id=None,
        leaf="notes",
        kind="notes",
        sync=True,
        yaml_path=("slides", 0, "notes"),
        value="Catatan",
        plain_text="Catatan",
    )
    block = BlockIR("title", "text", None, "title", {"text": "Judul"})
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Notes Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (block,), "Catatan", None),),
        keys=KeyManifest((notes_key, _key("s01.title.text"))),
    )
    shape = presentation.slides[0].shapes.add_textbox(Emu(0), Emu(0), Emu(100), Emu(100))
    shape.text_frame.text = "Judul"
    set_keyed_shape(shape, "s01.title.text", description="Judul")

    report = collect_coverage(presentation, deck)

    assert report.missing_keys == ()
    assert report.ok is True
