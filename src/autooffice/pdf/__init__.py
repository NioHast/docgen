"""Domain PDF AutoOffice.

Adapter COM untuk finalisasi field DOCX, ekspor PDF DOCX lewat Word, dan
ekspor PDF PPTX lewat PowerPoint. Import paket ini tidak memuat pywin32; guard
platform dan import lazy berada di :mod:`autooffice.pdf.com`.
"""

from pathlib import Path

from . import powerpoint as _powerpoint
from .com import (
    PdfUnavailableError,
    ProcessSnapshotError,
    WordBusyError,
    WordCleanupError,
    WordComError,
    WordTimeoutError,
)
from .powerpoint import export_pdf as export_pptx_pdf
from .word import export_pdf, update_fields


def embed_pptx_fonts(pptx: Path, *, timeout_s: float = 120.0) -> Path:
    """Tanam font TrueType ke PPTX lewat adapter PowerPoint COM."""

    return _powerpoint.embed_fonts(pptx, timeout_s=timeout_s)


__all__ = [
    "PdfUnavailableError",
    "ProcessSnapshotError",
    "WordBusyError",
    "WordCleanupError",
    "WordComError",
    "WordTimeoutError",
    "embed_pptx_fonts",
    "export_pdf",
    "export_pptx_pdf",
    "update_fields",
]
