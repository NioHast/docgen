"""Notes slide native hanya untuk slide yang memiliki catatan pembicara."""

from pptx.enum.text import MSO_AUTO_SIZE
from pptx.slide import Slide
from pptx.util import Emu, Pt

from autooffice.design.theme import Theme

from .shapes import (
    PptxRenderError,
    apply_paragraph_style,
    key_from_shape,
    primary_typeface,
    rgb,
    set_keyed_shape,
)


def set_notes(slide: Slide, notes: str, *, slide_id: str, theme: Theme) -> bool:
    """Buat notes slide native bila catatan tidak kosong."""
    if not notes.strip():
        return False
    notes_slide = slide.notes_slide
    text_frame = notes_slide.notes_text_frame
    if text_frame is None:
        raise PptxRenderError(f"Notes slide '{slide_id}' tidak memiliki text frame.")
    text_frame.word_wrap = True
    text_frame.auto_size = MSO_AUTO_SIZE.NONE
    text_frame.margin_left = Emu(0)
    text_frame.margin_right = Emu(0)
    text_frame.margin_top = Emu(0)
    text_frame.margin_bottom = Emu(0)
    text_frame.text = notes
    font_size_pt = max(theme.typography.body_pt, theme.typography.minimum_pt)
    for paragraph in text_frame.paragraphs:
        apply_paragraph_style(
            paragraph,
            line_height=theme.typography.line_height,
            font_size_pt=font_size_pt,
        )
        for run in paragraph.runs:
            run.font.name = primary_typeface(theme.typography.family)
            run.font.size = Pt(font_size_pt)
            run.font.bold = False
            run.font.italic = False
            run.font.color.rgb = rgb(theme.colors.ink)
    placeholder = notes_slide.notes_placeholder
    if placeholder is not None:
        set_keyed_shape(placeholder, f"{slide_id}.notes", description="Catatan pembicara")
    return True


def notes_text(slide: Slide) -> str | None:
    """Kembalikan teks notes native atau ``None`` bila notes slide tidak ada."""
    if not slide.has_notes_slide:
        return None
    text_frame = slide.notes_slide.notes_text_frame
    return None if text_frame is None else text_frame.text


def notes_key(slide: Slide, *, slide_id: str) -> str | None:
    """Kembalikan key notes dari metadata placeholder bila ada."""
    if not slide.has_notes_slide:
        return None
    placeholder = slide.notes_slide.notes_placeholder
    if placeholder is None:
        return None
    key = key_from_shape(placeholder)
    return key if key is not None else f"{slide_id}.notes"
