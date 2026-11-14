# mypy: disable-error-code="import-untyped"
"""Smoke visual PPTX: render nyata ke PNG lewat PowerPoint COM."""

from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock, SlideLayout
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyBinding, KeyManifest, SlideIR
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.protocol import OutputTarget, RenderRequest
from autooffice.design.theme import resolve_theme
from autooffice.pdf.com import PdfUnavailableError
from tools.visual.render_pptx import render_slides

pytestmark = [pytest.mark.integration, pytest.mark.slow]

PNG_WIDTH = 1280
PNG_HEIGHT = 720


def _build_two_slide_pptx(tmp_path: Path) -> Path:
    """Render deck dua slide lewat PptxRenderer sebagai input smoke."""

    theme = resolve_theme("indigo")
    slides = (
        SlideIR(
            "s01",
            "content",
            0,
            (
                BlockIR(
                    "title",
                    "text",
                    None,
                    "display",
                    {"text": "Smoke visual satu"},
                ),
            ),
            None,
            None,
        ),
        SlideIR(
            "s02",
            "content",
            1,
            (
                BlockIR(
                    "title",
                    "text",
                    None,
                    "display",
                    {"text": "Smoke visual dua"},
                ),
            ),
            None,
            None,
        ),
    )
    bindings = tuple(
        KeyBinding(
            key=f"{slide.slide_id}.title.text",
            slide_id=slide.slide_id,
            block_id="title",
            leaf="text",
            kind="text",
            sync=True,
            yaml_path=("slides", index, "blocks", 0, "text"),
            value="nilai",
            plain_text="nilai",
        )
        for index, slide in enumerate(slides)
    )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Visual Smoke", "author": "AutoOffice"},
        theme_name="indigo",
        slides=slides,
        keys=KeyManifest(bindings),
    )
    left = theme.grid.margin_left_emu
    top = theme.grid.margin_top_emu
    width = theme.grid.slide_width_emu - left - theme.grid.margin_right_emu
    layout = LayoutPlan(
        tuple(
            SlideLayout(
                slide.slide_id,
                (PlacedBlock("title", left, top, width, 2_000_000),),
                (),
            )
            for slide in slides
        )
    )
    request = RenderRequest(
        deck=deck,
        layout=layout,
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=tmp_path / "workspace",
    )
    rendered = PptxRenderer().render(request)
    return Path(rendered.artifact_path)


def test_render_slides_writes_one_non_uniform_png_per_slide(tmp_path: Path) -> None:
    pptx = _build_two_slide_pptx(tmp_path)
    out_dir = tmp_path / "png"
    try:
        rendered = render_slides(pptx, out_dir, width=PNG_WIDTH, height=PNG_HEIGHT)
    except PdfUnavailableError as exc:
        pytest.skip(f"PowerPoint COM tidak tersedia: {exc}")

    slide_count = len(Presentation(str(pptx)).slides)
    assert slide_count == 2
    assert len(rendered) == slide_count
    assert [path.name for path in rendered] == ["slide-001.png", "slide-002.png"]
    assert sorted(out_dir.glob("*.png")) == list(rendered)

    for path in rendered:
        assert path.stat().st_size > 0
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == (PNG_WIDTH, PNG_HEIGHT)
            colors = image.convert("RGB").getcolors(maxcolors=PNG_WIDTH * PNG_HEIGHT)
        assert colors is not None
        assert len(colors) > 1
