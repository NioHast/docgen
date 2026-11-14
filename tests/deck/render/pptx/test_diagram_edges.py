"""Tes cabang edge kotak media diagram."""

import pytest

from autooffice.deck.render.pptx.diagram import _media_boxes
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError


def test_media_boxes_rejects_caption_without_diagram_room(theme) -> None:
    box = Box(left=0, top=0, width=1_000_000, height=1000)

    with pytest.raises(PptxRenderError, match="tidak menyisakan ruang media"):
        _media_boxes(box, "Caption yang panjang sekali", theme)
