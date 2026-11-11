"""Model data immutable untuk format dan struktur dokumen.

Semua model di sini adalah nilai hasil parsing dengan field yang sudah
dikonversi ke satuan internal (twip dan setengah poin). ``Format`` dan
``Structure`` menyimpan data mentah sebagai mapping read-only di samping field
hasil konversi; konstruksi dan validasinya adalah tanggung jawab loader
``format`` dan ``structure``.

Modul ini tidak membaca YAML, tidak menyentuh filesystem, dan tidak melempar
error domain sendiri.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Margins:
    top: int
    bottom: int
    left: int
    right: int


@dataclass(frozen=True)
class PageFormat:
    size: str
    orientation: str
    margins: Margins
    header_distance: int
    footer_distance: int
    gutter: int


@dataclass(frozen=True)
class BodyFont:
    family: str
    size_half_points: int
    color: str
    line_spacing: float
    space_before: int
    space_after: int
    alignment: str
    first_line_indent: int


@dataclass(frozen=True)
class MonoFont:
    family: str
    size_half_points: int


@dataclass(frozen=True)
class FontFormat:
    body: BodyFont
    monospace: MonoFont


@dataclass(frozen=True)
class AbstractStyle:
    font_family: str
    font_size_half_points: int
    line_spacing: float
    space_before: int
    space_after: int
    alignment: str


@dataclass(frozen=True)
class HeadingStyle:
    font_family: str
    font_size_half_points: int
    bold: bool
    color: str
    alignment: str
    space_before: int
    space_after: int
    line_spacing: float
    keep_next: bool
    keep_lines: bool
    outline_level: int
    first_line_indent: int
    indent_left: int
    indent_hanging: int


@dataclass(frozen=True)
class TocHeadingStyle:
    heading_style: str
    font_family: str
    font_size_half_points: int
    bold: bool
    color: str
    alignment: str
    space_before: int
    space_after: int
    line_spacing: float
    first_line_indent: int


@dataclass(frozen=True)
class CaptionFont:
    family: str
    size_half_points: int
    bold: bool
    italic: bool
    color: str
    alignment: str
    space_before: int
    space_after: int
    line_spacing: float


@dataclass(frozen=True)
class CaptionStyle:
    label: str
    separator: str
    font: CaptionFont
    keep_next: bool = False


@dataclass(frozen=True)
class CaptionsFormat:
    figure: CaptionStyle
    table: CaptionStyle


@dataclass(frozen=True)
class FigureStyle:
    caption_alignment: str
    image_alignment: str
    numbering: str
    space_before: int
    space_after: int
    first_line_indent: int


@dataclass(frozen=True)
class CodeFont:
    family: str
    size_half_points: int
    color: str


@dataclass(frozen=True)
class CodeBorder:
    style: str
    width: int
    color: str


@dataclass(frozen=True)
class CodeTable:
    width_percent: int
    cell_margin: int


@dataclass(frozen=True)
class CodeFormat:
    style: str
    font: CodeFont
    line_spacing: float
    space_before: int
    space_after: int
    alignment: str
    shading: str
    border: CodeBorder
    table: CodeTable
    detect_styles: tuple[str, ...]


@dataclass(frozen=True)
class BibliographyStyle:
    heading: str
    font_family: str
    font_size_half_points: int
    line_spacing: float
    space_before: int
    space_after: int
    indent_left: int
    indent_hanging: int


@dataclass(frozen=True)
class CitationFormat:
    csl: Path
    bibliography: str
    locale: str


@dataclass(frozen=True)
class AssetsFormat:
    logo: Path
    reference_docx: Path


@dataclass(frozen=True)
class Format:
    id: str
    name: str
    description: str
    path: Path
    data: Mapping[str, Any]
    page: PageFormat
    font: FontFormat
    abstract: AbstractStyle
    headings: Mapping[str, HeadingStyle]
    toc_heading: TocHeadingStyle
    captions: CaptionsFormat
    figures: FigureStyle
    code: CodeFormat
    bibliography_style: BibliographyStyle
    citation: CitationFormat
    assets: AssetsFormat


@dataclass(frozen=True)
class FrontMatterItem:
    id: str
    source: str
    template: str | None = None


@dataclass(frozen=True)
class BodyChapter:
    id: str
    title: str


@dataclass(frozen=True)
class BackMatterItem:
    id: str
    source: str


@dataclass(frozen=True)
class Numbering:
    body: str
    sub_dot: bool
    subsub_dot: bool


@dataclass(frozen=True)
class ListSettings:
    figures: bool
    tables: bool


@dataclass(frozen=True)
class CoverOverrides:
    show_lecturer: bool = True
    logo_width: int = 2767  # 4.88 cm
    title_split: bool = True


@dataclass(frozen=True)
class Structure:
    id: str
    format_id: str
    path: Path
    data: Mapping[str, Any]
    front_matter: tuple[FrontMatterItem, ...]
    body: tuple[BodyChapter, ...]
    back_matter: tuple[BackMatterItem, ...]
    toc: bool
    numbering: Numbering
    lists: ListSettings
    cover: CoverOverrides = field(default_factory=CoverOverrides)

    @property
    def template_dir(self) -> Path:
        return self.path / "templates"
