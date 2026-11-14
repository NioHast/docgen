"""Stage pipeline ``autooffice.docx``.

Setiap modul stage hanya menyediakan API transformasi; orkestrasi dan urutan
stage dimiliki ``autooffice.docx.pipeline``. Modul ini mendaftarkan kelas stage kanonik
dalam satu tempat agar ``Pipeline`` tidak perlu mengetahui detail impor.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from ..pipeline import BaseStage


def default_stages() -> tuple[type[BaseStage], ...]:
    """Kembalikan kelas stage sesuai urutan kanonik ``StageName``."""

    from .blank_lines import BlankLinesStage
    from .captions import CaptionsStage
    from .code import CodeStage
    from .equations import EquationsStage
    from .front_matter import FrontMatterStage
    from .lists import ListsStage
    from .mermaid import MermaidStage
    from .normalize import NormalizeStage
    from .numbering import NumberingStage
    from .office import OfficeStage
    from .page_numbers import PageNumbersStage
    from .pandoc import PandocStage
    from .pdf import PdfStage
    from .sections import SectionsStage
    from .style_reference import StyleReferenceStage
    from .terms import TermsStage
    from .toc import TocStage
    from .validate import ValidateStage

    return (
        ValidateStage,
        MermaidStage,
        StyleReferenceStage,
        FrontMatterStage,
        PandocStage,
        SectionsStage,
        CodeStage,
        CaptionsStage,
        NormalizeStage,
        EquationsStage,
        NumberingStage,
        BlankLinesStage,
        TermsStage,
        TocStage,
        PageNumbersStage,
        ListsStage,
        OfficeStage,
        PdfStage,
    )


__all__ = ["default_stages"]
