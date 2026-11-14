"""Gambar native, crop proporsional, dan alt text untuk PPTX."""

import io
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from PIL import Image as PILImage
from pptx.shapes.base import BaseShape
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.layout.measure import measure_text
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

from .shapes import (
    IMAGE_MARKER,
    Box,
    PptxRenderError,
    field_optional_text,
    field_text,
    set_namespace_marker,
)
from .textbox import add_keyed_text, body_style

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


def _asset_context(*, slide_id: str | None, block_id: str | None) -> str:
    """Bangun prefix konteks slide dan block untuk error aset."""
    if slide_id and block_id:
        return f"Slide '{slide_id}', block '{block_id}': "
    if slide_id:
        return f"Slide '{slide_id}': "
    if block_id:
        return f"Block '{block_id}': "
    return ""


def resolve_asset_path(
    workspace: Path,
    relative_path: str,
    *,
    slide_id: str | None = None,
    block_id: str | None = None,
) -> Path:
    """Resolve path aset relatif terhadap workspace build."""
    context = _asset_context(slide_id=slide_id, block_id=block_id)
    if not relative_path:
        raise PptxRenderError(f"{context}Path gambar tidak boleh kosong.")
    if "\\" in relative_path:
        raise PptxRenderError(f"{context}Path gambar harus memakai '/': {relative_path!r}.")
    parsed = urlsplit(relative_path)
    if parsed.scheme or relative_path.startswith("/"):
        raise PptxRenderError(f"{context}Path gambar harus relatif: {relative_path!r}.")
    pure = Path(relative_path)
    if pure.is_absolute() or ".." in pure.parts:
        raise PptxRenderError(f"{context}Path gambar keluar dari workspace: {relative_path!r}.")
    if pure.suffix.lower() not in _IMAGE_SUFFIXES:
        raise PptxRenderError(
            f"{context}Gambar '{relative_path}' harus berekstensi png, jpg, jpeg, atau webp."
        )
    try:
        root = workspace.resolve()
        resolved = (root / relative_path).resolve()
    except (OSError, RuntimeError) as error:
        raise PptxRenderError(
            f"{context}Gambar '{relative_path}' tidak dapat di-resolve terhadap workspace "
            f"'{workspace}'; periksa symlink loop atau izin: {error}"
        ) from error
    if not resolved.is_relative_to(root):
        raise PptxRenderError(f"{context}Path gambar keluar dari workspace: {relative_path!r}.")
    if not resolved.is_file():
        raise PptxRenderError(f"{context}Gambar tidak ditemukan: {relative_path!r}.")
    return resolved


def image_size(
    path: Path,
    *,
    slide_id: str | None = None,
    block_id: str | None = None,
) -> tuple[int, int]:
    """Baca dimensi pixel gambar tanpa jaringan."""
    context = _asset_context(slide_id=slide_id, block_id=block_id)
    try:
        with PILImage.open(path) as image:
            width, height = image.size
    except (OSError, RuntimeError) as error:
        raise PptxRenderError(f"{context}Gambar tidak dapat dibaca: {path}: {error}") from error
    if width <= 0 or height <= 0:
        raise PptxRenderError(f"{context}Gambar memiliki dimensi tidak valid: {path}.")
    return width, height


def cover_crop(
    image_width: int,
    image_height: int,
    box_width: int,
    box_height: int,
) -> tuple[float, float, float, float]:
    """Hitung crop native ``(left, top, right, bottom)`` untuk mode cover."""
    if min(image_width, image_height, box_width, box_height) <= 0:
        raise PptxRenderError("Dimensi gambar dan kotak crop harus positif.")
    image_ratio = image_width / image_height
    box_ratio = box_width / box_height
    if image_ratio > box_ratio:
        total = 1.0 - (box_ratio / image_ratio)
        side = total / 2.0
        return side, 0.0, side, 0.0
    if image_ratio < box_ratio:
        total = 1.0 - (image_ratio / box_ratio)
        side = total / 2.0
        return 0.0, side, 0.0, side
    return 0.0, 0.0, 0.0, 0.0


def contain_geometry(
    image_width: int,
    image_height: int,
    box: Box,
) -> tuple[int, int, int, int]:
    """Hitung posisi dan ukuran proporsional untuk mode contain."""
    if min(image_width, image_height) <= 0:
        raise PptxRenderError("Dimensi gambar harus positif.")
    image_ratio = image_width / image_height
    box_ratio = box.width / box.height
    if image_ratio > box_ratio:
        width = box.width
        height = max(1, round(width / image_ratio))
    else:
        height = box.height
        width = max(1, round(height * image_ratio))
    left = box.left + (box.width - width) // 2
    top = box.top + (box.height - height) // 2
    return left, top, width, height


def render_image_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
    workspace: Path,
) -> tuple[BaseShape, ...]:
    """Render block image sebagai picture native dengan crop dan alt text."""
    relative_path = field_text(block.fields, "path", block_id=block.block_id)
    path = resolve_asset_path(
        workspace,
        relative_path,
        slide_id=slide_id,
        block_id=block.block_id,
    )
    alt = field_optional_text(block.fields, "alt")
    fit = field_optional_text(block.fields, "fit") or "contain"
    if fit not in {"contain", "cover"}:
        raise PptxRenderError(f"Block image '{block.block_id}' memiliki fit tidak dikenal: {fit}.")
    caption = field_optional_text(block.fields, "caption")
    media_box, caption_box = _media_boxes(box, caption, theme)
    image_width, image_height = image_size(path, slide_id=slide_id, block_id=block.block_id)
    source = _picture_source(path)
    if fit == "cover":
        picture = slide.shapes.add_picture(
            source,
            left=Emu(media_box.left),
            top=Emu(media_box.top),
            width=Emu(media_box.width),
            height=Emu(media_box.height),
        )
        left, top, right, bottom = cover_crop(
            image_width,
            image_height,
            media_box.width,
            media_box.height,
        )
        picture.crop_left = left
        picture.crop_top = top
        picture.crop_right = right
        picture.crop_bottom = bottom
    else:
        left, top, width, height = contain_geometry(image_width, image_height, media_box)
        picture = slide.shapes.add_picture(
            source,
            left=Emu(left),
            top=Emu(top),
            width=Emu(width),
            height=Emu(height),
        )
    set_namespace_marker(
        picture,
        IMAGE_MARKER,
        f"{slide_id}.{block.block_id}",
        description=alt,
    )
    shapes: list[BaseShape] = [picture]
    if caption and caption_box is not None:
        shapes.append(
            add_keyed_text(
                slide,
                caption_box,
                key=f"{slide_id}.{block.block_id}.caption",
                text=caption,
                style=body_style(theme, weight=400, color=theme.colors.muted),
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
        raise PptxRenderError("Kotak gambar tidak menyisakan ruang media setelah caption.")
    media = Box(left=box.left, top=box.top, width=box.width, height=media_height)
    caption_box = Box(
        left=box.left,
        top=box.top + media_height + gap,
        width=box.width,
        height=caption_height,
    )
    return media, caption_box


def _picture_source(path: Path) -> str | BinaryIO:
    """Kembalikan sumber picture; WebP dinormalisasi ke PNG di memori."""
    if path.suffix.lower() != ".webp":
        return str(path)
    buffer = io.BytesIO()
    try:
        with PILImage.open(path) as image:
            image.convert("RGBA").save(buffer, format="PNG")
    except OSError as error:
        raise PptxRenderError(
            f"WebP tidak dapat dikonversi ke PNG: {path.name}: {error}"
        ) from error
    buffer.seek(0)
    return buffer
