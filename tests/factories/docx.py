"""Factory DOCX minimal berbasis python-docx."""

from __future__ import annotations

from pathlib import Path

from docx import Document


def build_docx(paragraphs: list[str], path: Path) -> Path:
    """Buat DOCX berisi satu paragraf per string, lalu kembalikan path-nya."""
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))
    return path
