"""Tes cabang edge renderer: validasi request dan block type tanpa dukungan."""

from dataclasses import replace

import pytest
from _edge_helpers import single_slide_deck, single_slide_layout

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.shapes import PptxRenderError
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def _title_block(text: str = "Judul") -> BlockIR:
    return BlockIR("title", "text", None, "title", {"text": text})


def _request(deck, layout, theme, workspace) -> RenderRequest:
    return RenderRequest(
        deck=deck,
        layout=layout,
        theme=theme,
        target=OutputTarget.PPTX,
        workspace=workspace,
    )


def test_render_rejects_empty_deck(theme, workspace) -> None:
    request = _request(
        replace(single_slide_deck(), slides=()),
        LayoutPlan(()),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="tidak memiliki slide"):
        PptxRenderer().render(request)


def test_render_rejects_slide_count_mismatch(theme, workspace) -> None:
    request = _request(
        single_slide_deck((_title_block(),)),
        LayoutPlan(()),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="LayoutPlan memiliki 0 slide"):
        PptxRenderer().render(request)


def test_render_rejects_slide_order_mismatch(theme, workspace) -> None:
    request = _request(
        single_slide_deck((_title_block(),)),
        single_slide_layout(slide_id="s02"),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="Urutan slide tidak cocok"):
        PptxRenderer().render(request)


def test_render_rejects_overflow(theme, workspace) -> None:
    request = _request(
        single_slide_deck((_title_block(),)),
        single_slide_layout(overflow_keys=("s01.title.text",)),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="masih memiliki overflow"):
        PptxRenderer().render(request)


def test_render_rejects_duplicate_placements(theme, workspace) -> None:
    placed = PlacedBlock("title", 914400, 609600, 1_000_000, 1_000_000)
    request = _request(
        single_slide_deck((_title_block(),)),
        single_slide_layout((placed, placed)),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="menempatkan block lebih dari sekali"):
        PptxRenderer().render(request)


def test_render_rejects_missing_placement(theme, workspace) -> None:
    request = _request(
        single_slide_deck((_title_block(),)),
        single_slide_layout(),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="tidak memiliki kotak layout untuk block"):
        PptxRenderer().render(request)


def test_render_rejects_unknown_placement(theme, workspace) -> None:
    placed = PlacedBlock("ghost", 914400, 609600, 1_000_000, 1_000_000)
    request = _request(
        single_slide_deck(),
        single_slide_layout((placed,)),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="kotak layout untuk block asing"):
        PptxRenderer().render(request)


def test_render_rejects_unsupported_block_type(theme, workspace) -> None:
    block = BlockIR("b1", "video", None, None, {})
    placed = PlacedBlock("b1", 914400, 609600, 1_000_000, 1_000_000)
    request = _request(
        single_slide_deck((block,)),
        single_slide_layout((placed,)),
        theme,
        workspace,
    )

    with pytest.raises(PptxRenderError, match="tidak didukung renderer PPTX"):
        PptxRenderer().render(request)
