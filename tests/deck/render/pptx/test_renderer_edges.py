"""Tes cabang edge renderer: validasi request, block asing, dan chart tanpa cNvPr."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from _edge_helpers import new_slide, single_slide_deck, single_slide_layout
from lxml import etree
from pptx.oxml.ns import qn

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx import renderer
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def _title_block(text: str = "Judul") -> BlockIR:
    return BlockIR("title", "text", None, "title", {"text": text})


def test_validate_request_rejects_empty_deck(theme, workspace) -> None:
    deck = replace(single_slide_deck(), slides=())
    render_request = RenderRequest(
        deck=deck,
        layout=LayoutPlan(()),
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )

    with pytest.raises(PptxRenderError, match="tidak memiliki slide"):
        renderer._validate_request(render_request)


def test_validate_request_rejects_slide_count_mismatch(theme, workspace) -> None:
    deck = single_slide_deck((_title_block(),))
    render_request = RenderRequest(
        deck=deck,
        layout=LayoutPlan(()),
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )

    with pytest.raises(PptxRenderError, match="LayoutPlan memiliki 0 slide"):
        renderer._validate_request(render_request)


def test_validate_request_rejects_slide_order_mismatch(theme, workspace) -> None:
    deck = single_slide_deck((_title_block(),))
    render_request = RenderRequest(
        deck=deck,
        layout=single_slide_layout(slide_id="s02"),
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )

    with pytest.raises(PptxRenderError, match="Urutan slide tidak cocok"):
        renderer._validate_request(render_request)


def test_validate_request_rejects_overflow(theme, workspace) -> None:
    deck = single_slide_deck((_title_block(),))
    render_request = RenderRequest(
        deck=deck,
        layout=single_slide_layout(overflow_keys=("s01.title.text",)),
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )

    with pytest.raises(PptxRenderError, match="masih memiliki overflow"):
        renderer._validate_request(render_request)


def test_validate_request_rejects_duplicate_placements(theme, workspace) -> None:
    deck = single_slide_deck((_title_block(),))
    placed = PlacedBlock("title", 914400, 609600, 1_000_000, 1_000_000)
    render_request = RenderRequest(
        deck=deck,
        layout=single_slide_layout((placed, placed)),
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )

    with pytest.raises(PptxRenderError, match="menempatkan block lebih dari sekali"):
        renderer._validate_request(render_request)


def test_validate_request_rejects_missing_placement(theme, workspace) -> None:
    deck = single_slide_deck((_title_block(),))
    render_request = RenderRequest(
        deck=deck,
        layout=single_slide_layout(),
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )

    with pytest.raises(PptxRenderError, match="tidak memiliki kotak layout untuk block"):
        renderer._validate_request(render_request)


def test_validate_request_rejects_unknown_placement(theme, workspace) -> None:
    deck = single_slide_deck()
    placed = PlacedBlock("ghost", 914400, 609600, 1_000_000, 1_000_000)
    render_request = RenderRequest(
        deck=deck,
        layout=single_slide_layout((placed,)),
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )

    with pytest.raises(PptxRenderError, match="kotak layout untuk block asing"):
        renderer._validate_request(render_request)


def test_render_block_rejects_unknown_block_type(theme, workspace) -> None:
    block = BlockIR("b1", "video", None, None, {})
    slide_ir = single_slide_deck((block,)).slides[0]
    placed = PlacedBlock("b1", 914400, 609600, 1_000_000, 1_000_000)

    with pytest.raises(PptxRenderError, match="tidak didukung renderer PPTX"):
        renderer._render_block(
            new_slide(),
            slide_ir,
            block,
            placed,
            theme,
            target=OutputTarget.PPTX,
            workspace=workspace,
        )


def test_render_chart_skips_extension_keys_without_cnv_pr(
    chart_case,
    theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slide_ir = chart_case.deck.slides[0]
    block = slide_ir.blocks[0]
    fake_shape = SimpleNamespace(_element=etree.Element(qn("p:sp")))

    monkeypatch.setattr(
        renderer.chart_renderer,
        "render_chart",
        lambda *args, **kwargs: fake_shape,
    )

    renderer._render_chart(
        new_slide(),
        slide_ir,
        block,
        Box(left=0, top=0, width=1_000_000, height=1_000_000),
        theme,
        target=OutputTarget.PPTX,
    )

    assert next(fake_shape._element.iter("{urn:autooffice:key}key"), None) is None
