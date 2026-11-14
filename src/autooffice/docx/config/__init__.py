"""Pembacaan dan validasi ``format.yml`` serta ``structure.yml``.

API masuk adalah :func:`load_format`, :func:`load_structure`,
:func:`format_override_warning`, :func:`load_yaml_mapping`, dan
:func:`parse_yaml_mapping`. ``load_format`` dan ``load_structure``
mengembalikan model immutable; ``format_override_warning`` mengembalikan
``str | None``; ``load_yaml_mapping`` dan ``parse_yaml_mapping``
mengembalikan ``dict`` biasa yang dapat dimutasi pemanggil. Semua melempar
``ConfigError`` dengan kode stabil saat input tidak valid. Submodul internal
dipisah berdasarkan tanggung jawab: ``models`` untuk nilai immutable,
``validation`` untuk pemeriksaan tipe dan nilai, ``common`` untuk helper
nilai generik dan pembacaan YAML, serta ``format`` dan ``structure`` untuk
pembentukan model.

Package ini tidak menyentuh DOCX, tidak menjalankan stage, dan tidak menulis
berkas. Kontrak data ada di ``docs/dev/formats.md``.
"""

from .common import load_yaml_mapping, parse_yaml_mapping
from .format import format_override_warning, load_format
from .models import (
    AbstractStyle,
    AssetsFormat,
    BackMatterItem,
    BibliographyStyle,
    BodyChapter,
    BodyFont,
    CaptionFont,
    CaptionsFormat,
    CaptionStyle,
    CitationFormat,
    CodeBorder,
    CodeFont,
    CodeFormat,
    CodeTable,
    CoverOverrides,
    FigureStyle,
    FontFormat,
    Format,
    FrontMatterItem,
    HeadingStyle,
    ListSettings,
    Margins,
    MonoFont,
    Numbering,
    PageFormat,
    Structure,
    TocHeadingStyle,
)
from .structure import load_structure

__all__ = [
    "AbstractStyle",
    "AssetsFormat",
    "BackMatterItem",
    "BibliographyStyle",
    "BodyChapter",
    "BodyFont",
    "CaptionFont",
    "CaptionStyle",
    "CaptionsFormat",
    "CitationFormat",
    "CodeBorder",
    "CodeFont",
    "CodeFormat",
    "CodeTable",
    "CoverOverrides",
    "FigureStyle",
    "FontFormat",
    "Format",
    "FrontMatterItem",
    "HeadingStyle",
    "ListSettings",
    "Margins",
    "MonoFont",
    "Numbering",
    "PageFormat",
    "Structure",
    "TocHeadingStyle",
    "format_override_warning",
    "load_format",
    "load_structure",
    "load_yaml_mapping",
    "parse_yaml_mapping",
]
