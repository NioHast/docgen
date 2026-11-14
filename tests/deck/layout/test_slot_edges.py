"""Test tambahan kontrak slot: layout tidak cocok dan block ID duplikat."""

from collections.abc import Callable

import pytest

from autooffice.deck.layout.slot import SlotValidationError, validate_slide
from autooffice.deck.layout.spec import LayoutSpec
from autooffice.deck.model.deck_ir import BlockIR, SlideIR


def test_slide_layout_must_match_spec_layout_id(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    slide = slide_factory(
        (
            block_factory("title", "text", fields={"text": "Judul"}, role="title"),
            block_factory("body", "text", fields={"text": "Isi"}, role="body"),
        ),
        layout="other",
    )

    with pytest.raises(SlotValidationError, match="memakai layout 'other', bukan 'demo'"):
        validate_slide(slide, demo_spec)


def test_duplicate_block_ids_are_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    demo_spec: LayoutSpec,
) -> None:
    title = block_factory("title", "text", fields={"text": "Judul"}, role="title")
    slide = slide_factory(
        (
            title,
            title,
            block_factory("body", "text", fields={"text": "Isi"}, role="body"),
        )
    )

    with pytest.raises(SlotValidationError, match="Block ID 'title' duplikat"):
        validate_slide(slide, demo_spec)
