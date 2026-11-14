"""Render block diagram Mermaid sebagai picture native di slide PPTX."""

from pathlib import Path

from pptx.shapes.base import BaseShape
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.layout.measure import measure_text
from autooffice.deck.media.mermaid import (
    MermaidError,
    render_mermaid,
    resolve_mermaid_source,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

from .image import contain_geometry, image_size
from .shapes import (
    DIAGRAM_MARKER,
    Box,
    PptxRenderError,
    field_optional_text,
    field_text,
    set_namespace_marker,
)
from .textbox import add_caption

CACHE_DIR = Path("cache") / "mermaid"


def render_diagram_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
    workspace: Path,
) -> tuple[BaseShape, ...]:
    """Render satu block diagram dan kembalikan picture serta caption-nya.

    Diagram selalu menjadi gambar PNG hasil ``mmdc``; tidak ada fallback teks
    atau shape. Bila render gagal, error dari lane media diteruskan sebagai
    ``PptxRenderError`` dengan konteks slide dan block.
    """
    relative_source = field_text(block.fields, "source", block_id=block.block_id)
    alt = field_optional_text(block.fields, "alt")
    caption = field_optional_text(block.fields, "caption")
    media_box, caption_box = _media_boxes(box, caption, theme)
    cache_dir = workspace / CACHE_DIR
    output = cache_dir / f"{slide_id}.{block.block_id}.png"
    try:
        source = resolve_mermaid_source(workspace, relative_source)
        png = render_mermaid(source, output, theme=theme, cache_dir=cache_dir)
    except MermaidError as error:
        raise PptxRenderError(
            f"Slide '{slide_id}', block '{block.block_id}' gagal merender diagram: {error}"
        ) from error

    image_width, image_height = image_size(png)
    left, top, width, height = contain_geometry(image_width, image_height, media_box)
    picture = slide.shapes.add_picture(
        str(png),
        left=Emu(left),
        top=Emu(top),
        width=Emu(width),
        height=Emu(height),
    )
    set_namespace_marker(
        picture,
        DIAGRAM_MARKER,
        f"{slide_id}.{block.block_id}",
        description=alt,
    )
    shapes: list[BaseShape] = [picture]
    if caption and caption_box is not None:
        shapes.append(
            add_caption(
                slide,
                caption_box,
                key=f"{slide_id}.{block.block_id}.caption",
                text=caption,
                theme=theme,
            )
        )
    return tuple(shapes)


def _media_boxes(box: Box, caption: str, theme: Theme) -> tuple[Box, Box | None]:
    if not caption:
        return box, None
    caption_height = measure_text(
        caption,
        available_width_emu=box.width,
        theme=theme,
        font_size_pt=theme.typography.body_pt,
        weight=400,
    ).height_emu
    gap = theme.spacing.sm_emu
    media_height = box.height - caption_height - gap
    if media_height <= 0:
        raise PptxRenderError("Kotak diagram tidak menyisakan ruang media setelah caption.")
    media = Box(left=box.left, top=box.top, width=box.width, height=media_height)
    caption_box = Box(
        left=box.left,
        top=box.top + media_height + gap,
        width=box.width,
        height=caption_height,
    )
    return media, caption_box


__all__ = ["CACHE_DIR", "render_diagram_block"]
