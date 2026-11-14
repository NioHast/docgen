"""Tes cabang edge text box, block teks, dan bullet numbering."""

from types import SimpleNamespace

import pytest
from _edge_helpers import line_spacing_points, new_slide
from pptx.oxml.ns import qn

from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError, key_from_shape
from autooffice.deck.render.pptx.textbox import (
    add_keyed_text,
    render_bullets_block,
    render_code_block,
    render_metric_block,
    render_quote_block,
    render_source_text,
    render_text_block,
    role_style,
)


def _padding(theme) -> int:
    return theme.spacing.card_padding_emu


def _tight_box(theme) -> Box:
    """Kotak yang menyisakan tinggi 1 EMU setelah padding."""
    padding = _padding(theme)
    return Box(left=0, top=0, width=padding * 4, height=padding * 2 + 1)


def test_add_keyed_text_requires_text_frame(theme) -> None:
    class FakeShapes:
        def add_textbox(self, *args: object) -> SimpleNamespace:
            return SimpleNamespace(has_text_frame=False)

    fake_slide = SimpleNamespace(shapes=FakeShapes())

    with pytest.raises(PptxRenderError, match="tidak memiliki text frame"):
        add_keyed_text(
            fake_slide,
            Box(left=0, top=0, width=1000, height=1000),
            key="s01.title.text",
            text="Judul",
            style=role_style(theme, "body"),
            theme=theme,
        )


def test_render_text_block_rejects_no_body_space_after_heading(theme) -> None:
    block = BlockIR("b1", "text", None, "body", {"heading": "Judul", "text": "Isi"})

    with pytest.raises(PptxRenderError, match="tidak menyisakan ruang untuk teks"):
        render_text_block(new_slide(), block, _tight_box(theme), theme, slide_id="s01")


def test_render_bullets_block_rejects_zero_available_width(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu",)})
    padding = _padding(theme)
    box = Box(
        left=0,
        top=0,
        width=padding * 2 + theme.spacing.md_emu,
        height=padding * 4,
    )

    with pytest.raises(PptxRenderError, match="tidak memiliki lebar untuk bullets"):
        render_bullets_block(new_slide(), block, box, theme, slide_id="s01")


def test_render_bullets_block_rejects_empty_items(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ()})
    box = Box(left=0, top=0, width=1_000_000, height=1_000_000)

    with pytest.raises(PptxRenderError, match="tidak memiliki item"):
        render_bullets_block(new_slide(), block, box, theme, slide_id="s01")


def test_render_bullets_block_rejects_overflow_without_shrinking(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("x" * 200, "y" * 200)})
    padding = _padding(theme)
    box = Box(
        left=0,
        top=0,
        width=padding * 2 + theme.spacing.md_emu + 1,
        height=padding * 2 + 2,
    )

    with pytest.raises(PptxRenderError, match="melebihi kotak"):
        render_bullets_block(new_slide(), block, box, theme, slide_id="s01")


def test_render_bullets_block_keeps_all_shapes_inside_box(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu", "Dua")})
    box = Box(left=100, top=200, width=4_000_000, height=3_000_000)

    shapes = render_bullets_block(new_slide(), block, box, theme, slide_id="s01")
    inner = box.inset(_padding(theme))

    assert len(shapes) == 2
    for shape in shapes:
        assert shape.left >= inner.left
        assert shape.top >= inner.top
        assert shape.left + shape.width <= inner.right
        assert shape.top + shape.height <= inner.bottom


def test_render_bullets_block_writes_ordered_numbering(theme) -> None:
    block = BlockIR("b1", "bullets", None, None, {"items": ("Satu", "Dua"), "ordered": True})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_bullets_block(new_slide(), block, box, theme, slide_id="s01")

    starts = []
    for shape in shapes:
        paragraph = shape.text_frame.paragraphs[0]
        numbering = paragraph._p.find(".//" + qn("a:buAutoNum"))
        assert numbering is not None
        assert numbering.get("type") == "arabicPeriod"
        starts.append(numbering.get("startAt"))
    assert starts == ["1", "2"]


def test_render_quote_block_without_attribution_returns_one_shape(theme) -> None:
    block = BlockIR("q1", "quote", None, None, {"text": "Kutipan"})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_quote_block(new_slide(), block, box, theme, slide_id="s01")

    assert len(shapes) == 1
    assert shapes[0].text_frame.text == "Kutipan"


def test_render_quote_block_rejects_attribution_without_space(theme) -> None:
    block = BlockIR(
        "q1",
        "quote",
        None,
        None,
        {"text": "Kutipan yang panjang", "attribution": "Tim"},
    )

    with pytest.raises(PptxRenderError, match="tidak menyisakan ruang untuk attribution"):
        render_quote_block(new_slide(), block, _tight_box(theme), theme, slide_id="s01")


def test_render_metric_block_without_caption_returns_two_shapes(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    assert len(shapes) == 2
    assert [shape.text_frame.text for shape in shapes] == ["95%", "Coverage"]


def test_render_metric_block_rejects_overflow_without_shrinking(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})

    with pytest.raises(PptxRenderError, match="melebihi kotak"):
        render_metric_block(new_slide(), block, _tight_box(theme), theme, slide_id="s01")


def test_render_metric_block_keeps_measured_heights_when_exact(theme) -> None:
    block = BlockIR("m1", "metric", None, None, {"label": "Coverage", "value": "95%"})
    padding = _padding(theme)
    roomy = Box(left=0, top=0, width=4_000_000, height=3_000_000)
    natural = render_metric_block(new_slide(), block, roomy, theme, slide_id="s01")
    natural_heights = [shape.height for shape in natural]

    exact = Box(
        left=0,
        top=0,
        width=4_000_000,
        height=padding * 2 + sum(natural_heights),
    )
    shapes = render_metric_block(new_slide(), block, exact, theme, slide_id="s01")
    inner = exact.inset(padding)

    assert [shape.height for shape in shapes] == natural_heights
    assert sum(shape.height for shape in shapes) == inner.height
    assert shapes[-1].top + shapes[-1].height == inner.bottom


@pytest.mark.parametrize("status", ["success", "warning", "danger", "neutral"])
def test_render_metric_block_applies_status_color(theme, status: str) -> None:
    block = BlockIR(
        "m1",
        "metric",
        None,
        None,
        {"label": "Coverage", "value": "95%", "status": status},
    )
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_metric_block(new_slide(), block, box, theme, slide_id="s01")

    value_run = shapes[0].text_frame.paragraphs[0].runs[0]
    assert value_run.font.color.rgb == _rgb(theme.colors.status[status])


def test_render_code_block_without_filename_returns_one_shape_without_line_numbers(theme) -> None:
    block = BlockIR("c1", "code", None, None, {"code": "print(1)", "line_numbers": False})
    box = Box(left=0, top=0, width=4_000_000, height=3_000_000)

    shapes = render_code_block(new_slide(), block, box, theme, slide_id="s01")

    assert len(shapes) == 1
    assert shapes[0].text_frame.text == "print(1)"


def test_render_code_block_renders_line_numbers_as_chrome(theme) -> None:
    block = BlockIR("c1", "code", None, None, {"code": "print(1)\nprint(2)"})
    box = Box(left=100, top=200, width=4_000_000, height=3_000_000)

    shapes = render_code_block(new_slide(), block, box, theme, slide_id="s01")
    inner = box.inset(_padding(theme))
    names = {shape.name: shape for shape in shapes}

    numbers = names["chrome:code-lines:s01.c1"]
    code = names["autooffice:key:s01.c1.code"]
    assert key_from_shape(numbers) is None
    assert numbers.text_frame.text == "1\n2"
    assert code.text_frame.text == "print(1)\nprint(2)"
    assert numbers.left == inner.left
    assert numbers.left + numbers.width <= code.left
    assert code.left + code.width <= inner.right
    for paragraph in numbers.text_frame.paragraphs:
        assert line_spacing_points(paragraph) == round(
            theme.code.size_pt * theme.code.line_height * 100
        )


def test_render_code_block_rejects_no_room_after_filename(theme) -> None:
    block = BlockIR("c1", "code", None, None, {"code": "print(1)", "filename": "kode.py"})

    with pytest.raises(PptxRenderError, match="tidak memiliki ruang teks"):
        render_code_block(new_slide(), block, _tight_box(theme), theme, slide_id="s01")


def test_render_source_text_requires_text(theme) -> None:
    with pytest.raises(PptxRenderError, match="source tanpa teks"):
        render_source_text(new_slide(), "s01", {}, theme)


@pytest.mark.parametrize(
    ("role", "expected"),
    [("label", "ink_secondary"), ("kicker", "accent")],
)
def test_role_style_maps_secondary_and_accent_roles(theme, role: str, expected: str) -> None:
    assert role_style(theme, role).color == getattr(theme.colors, expected)


def _rgb(color: str) -> object:
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(color[1:])
