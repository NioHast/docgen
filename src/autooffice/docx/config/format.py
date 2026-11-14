"""Parser ``format.yml`` dan validasi aset format.

Modul ini memuat :func:`load_format` dan :func:`format_override_warning`.
Parser membangun model immutable dari blok ``page``, ``font``, ``abstract``,
``headings``, ``captions``, ``figures``, ``code``, ``bibliography_style``,
``citation``, dan ``assets``; validasi aset (logo, ``reference.docx``, CSL) khusus format dan
tidak dipakai struktur.

Semua kegagalan input dilempar sebagai ``ConfigError`` dengan kode stabil;
modul ini tidak menulis berkas dan tidak menyediakan fallback format.
Kontrak data ada di ``docs/dev/formats.md``.
"""

import zipfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any
from xml.etree import ElementTree

from .. import paths as path_mod
from ..errors import ConfigError
from .common import (
    _alignment,
    _boolean,
    _color,
    _dimension,
    _enum,
    _font_size,
    _number,
    _text,
    _text_list,
    load_yaml_mapping,
)
from .models import (
    AbstractStyle,
    AssetsFormat,
    BibliographyStyle,
    BodyFont,
    CaptionFont,
    CaptionsFormat,
    CaptionStyle,
    CitationFormat,
    CodeBorder,
    CodeFont,
    CodeFormat,
    CodeTable,
    FigureStyle,
    FontFormat,
    Format,
    HeadingStyle,
    Margins,
    MonoFont,
    PageFormat,
    Structure,
    TocHeadingStyle,
)
from .validation import _check_unknown, _err, _expect_mapping, _required

_FORMAT_KEYS = frozenset(
    {
        "format",
        "name",
        "description",
        "page",
        "font",
        "abstract",
        "headings",
        "toc_heading",
        "captions",
        "figures",
        "code",
        "bibliography_style",
        "citation",
        "assets",
    }
)
_PAGE_KEYS = frozenset(
    {"size", "orientation", "margins", "header_distance", "footer_distance", "gutter"}
)
_MARGIN_KEYS = frozenset({"top", "bottom", "left", "right"})
_FONT_KEYS = frozenset({"body", "monospace"})
_BODY_FONT_KEYS = frozenset(
    {
        "family",
        "size",
        "color",
        "line_spacing",
        "space_before",
        "space_after",
        "alignment",
        "first_line_indent",
    }
)
_MONO_FONT_KEYS = frozenset({"family", "size"})
_ABSTRACT_KEYS = frozenset(
    {"font", "size", "line_spacing", "space_before", "space_after", "alignment"}
)
_HEADINGS_KEYS = frozenset({"styles"})
_HEADING_STYLE_KEYS = frozenset(
    {
        "font_family",
        "font_size",
        "bold",
        "color",
        "alignment",
        "space_before",
        "space_after",
        "line_spacing",
        "keep_next",
        "keep_lines",
        "outline_level",
        "first_line_indent",
        "indent_left",
        "indent_hanging",
    }
)
_TOC_HEADING_KEYS = frozenset(
    {
        "heading_style",
        "font",
        "size",
        "bold",
        "color",
        "alignment",
        "space_before",
        "space_after",
        "line_spacing",
        "first_line_indent",
    }
)
_CAPTIONS_KEYS = frozenset({"figure", "table"})
_CAPTION_KEYS = frozenset({"label", "separator", "keep_next", "font"})
_CAPTION_FONT_KEYS = frozenset(
    {
        "family",
        "size",
        "bold",
        "italic",
        "color",
        "space_before",
        "space_after",
        "line_spacing",
    }
)
_TABLE_CAPTION_FONT_KEYS = _CAPTION_FONT_KEYS | {"alignment"}
_FIGURE_KEYS = frozenset(
    {
        "caption_alignment",
        "image_alignment",
        "numbering",
        "space_before",
        "space_after",
        "first_line_indent",
    }
)
_CODE_KEYS = frozenset(
    {
        "style",
        "font",
        "line_spacing",
        "space_before",
        "space_after",
        "alignment",
        "shading",
        "border",
        "table",
        "detect_styles",
    }
)
_CODE_FONT_KEYS = frozenset({"family", "size", "color"})
_CODE_BORDER_KEYS = frozenset({"style", "width", "color"})
_CODE_TABLE_KEYS = frozenset({"width", "cell_margin"})
_BIBLIOGRAPHY_STYLE_KEYS = frozenset(
    {
        "heading",
        "font",
        "size",
        "line_spacing",
        "space_before",
        "space_after",
        "indent_left",
        "indent_hanging",
    }
)
_CITATION_KEYS = frozenset({"csl", "bibliography", "locale"})
_ASSETS_KEYS = frozenset({"logo", "reference_docx"})
_DEFAULT_DETECT_STYLES = (
    "Source Code",
    "Verbatim Char",
    "HTML Code",
    "HTML Preformatted",
)


def _parse_page(data: Mapping[str, Any], *, path: Path) -> PageFormat:
    """Bangun ``PageFormat`` dari blok ``page`` dengan default kontrak.

    Ukuran, orientasi, margin, jarak header/footer, dan gutter divalidasi;
    error tipe atau nilai dilempar sebagai ``ConfigError``.
    """

    _check_unknown(data, _PAGE_KEYS, path=path, key="page")
    margins = _expect_mapping(
        _required(data, "margins", path=path, key="page"),
        path=path,
        key="page.margins",
    )
    _check_unknown(margins, _MARGIN_KEYS, path=path, key="page.margins")
    return PageFormat(
        size=_enum(
            data.get("size"),
            path=path,
            key="page.size",
            choices=("A4", "Letter"),
            default="A4",
        ),
        orientation=_enum(
            data.get("orientation"),
            path=path,
            key="page.orientation",
            choices=("portrait", "landscape"),
            default="portrait",
        ),
        margins=Margins(
            top=_dimension(
                _required(margins, "top", path=path, key="page.margins"),
                path=path,
                key="page.margins.top",
                positive=True,
            ),
            bottom=_dimension(
                _required(margins, "bottom", path=path, key="page.margins"),
                path=path,
                key="page.margins.bottom",
                positive=True,
            ),
            left=_dimension(
                _required(margins, "left", path=path, key="page.margins"),
                path=path,
                key="page.margins.left",
                positive=True,
            ),
            right=_dimension(
                _required(margins, "right", path=path, key="page.margins"),
                path=path,
                key="page.margins.right",
                positive=True,
            ),
        ),
        header_distance=_dimension(
            data.get("header_distance"),
            path=path,
            key="page.header_distance",
            default="1.27cm",
        ),
        footer_distance=_dimension(
            data.get("footer_distance"),
            path=path,
            key="page.footer_distance",
            default="1.27cm",
        ),
        gutter=_dimension(
            data.get("gutter"),
            path=path,
            key="page.gutter",
            default="0cm",
        ),
    )


def _parse_body_font(data: Mapping[str, Any], *, path: Path) -> BodyFont:
    """Bangun ``BodyFont`` dari ``font.body`` dengan default spasi dan indent."""

    _check_unknown(data, _BODY_FONT_KEYS, path=path, key="font.body")
    return BodyFont(
        family=_text(
            _required(data, "family", path=path, key="font.body"),
            path=path,
            key="font.body.family",
        ),
        size_half_points=_font_size(
            _required(data, "size", path=path, key="font.body"),
            path=path,
            key="font.body.size",
        ),
        color=_color(data.get("color"), path=path, key="font.body.color"),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key="font.body.line_spacing",
            default=1.5,
            minimum=0.5,
            maximum=3.0,
        ),
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key="font.body.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key="font.body.space_after",
            default="0pt",
        ),
        alignment=_alignment(data.get("alignment"), path=path, key="font.body.alignment"),
        first_line_indent=_dimension(
            data.get("first_line_indent"),
            path=path,
            key="font.body.first_line_indent",
            default="1.25cm",
        ),
    )


def _parse_mono_font(data: Mapping[str, Any], *, path: Path) -> MonoFont:
    _check_unknown(data, _MONO_FONT_KEYS, path=path, key="font.monospace")
    return MonoFont(
        family=_text(
            data.get("family"),
            path=path,
            key="font.monospace.family",
            default="Courier New",
        ),
        size_half_points=_font_size(
            data.get("size"),
            path=path,
            key="font.monospace.size",
            default="10pt",
        ),
    )


def _parse_abstract(
    data: Mapping[str, Any] | None,
    *,
    body: BodyFont,
    path: Path,
) -> AbstractStyle:
    """Bangun ``AbstractStyle`` dari ``abstract``; default mewarisi ``font.body``."""

    raw = data or {}
    _check_unknown(raw, _ABSTRACT_KEYS, path=path, key="abstract")
    font_value = raw.get("font")
    if font_value is not None and not isinstance(font_value, str):
        raise _err(
            "'abstract.font' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key="abstract.font",
        )
    return AbstractStyle(
        font_family=_text(
            font_value,
            path=path,
            key="abstract.font",
            default=body.family,
        ),
        font_size_half_points=_font_size(
            raw.get("size"),
            path=path,
            key="abstract.size",
            default=f"{body.size_half_points / 2:g}pt",
        ),
        line_spacing=_number(
            raw.get("line_spacing"),
            path=path,
            key="abstract.line_spacing",
            default=body.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
        space_before=_dimension(
            raw.get("space_before"),
            path=path,
            key="abstract.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            raw.get("space_after"),
            path=path,
            key="abstract.space_after",
            default="0pt",
        ),
        alignment=_alignment(
            raw.get("alignment"),
            path=path,
            key="abstract.alignment",
            default=body.alignment,
        ),
    )


def _parse_heading_style(
    data: Mapping[str, Any],
    *,
    level: int,
    body: BodyFont,
    path: Path,
) -> HeadingStyle:
    """Bangun ``HeadingStyle`` untuk ``heading{level}``.

    Field yang tidak diisi mewarisi ``body`` dan default per level. Ukuran,
    warna, perataan, spasi, indent, dan outline divalidasi sebagai
    ``ConfigError``.
    """

    key = f"headings.styles.heading{level}"
    _check_unknown(data, _HEADING_STYLE_KEYS, path=path, key=key)
    default_alignment = "center" if level == 1 else "justify"
    default_indent = "0cm" if level == 1 else "1.25cm"
    return HeadingStyle(
        font_family=_text(
            data.get("font_family"),
            path=path,
            key=f"{key}.font_family",
            default=body.family,
        ),
        font_size_half_points=_font_size(
            data.get("font_size"),
            path=path,
            key=f"{key}.font_size",
            default=f"{body.size_half_points / 2:g}pt",
        ),
        bold=_boolean(data.get("bold"), path=path, key=f"{key}.bold", default=True),
        color=_color(data.get("color"), path=path, key=f"{key}.color"),
        alignment=_alignment(
            data.get("alignment"),
            path=path,
            key=f"{key}.alignment",
            default=default_alignment,
        ),
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key=f"{key}.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key=f"{key}.space_after",
            default="0pt",
        ),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key=f"{key}.line_spacing",
            default=body.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
        keep_next=_boolean(data.get("keep_next"), path=path, key=f"{key}.keep_next", default=True),
        keep_lines=_boolean(
            data.get("keep_lines"), path=path, key=f"{key}.keep_lines", default=True
        ),
        outline_level=int(
            _number(
                data.get("outline_level"),
                path=path,
                key=f"{key}.outline_level",
                default=float(level - 1),
                minimum=0,
                maximum=8,
            )
        ),
        first_line_indent=_dimension(
            data.get("first_line_indent"),
            path=path,
            key=f"{key}.first_line_indent",
            default="0cm",
        ),
        indent_left=_dimension(
            data.get("indent_left"),
            path=path,
            key=f"{key}.indent_left",
            default=default_indent,
        ),
        indent_hanging=_dimension(
            data.get("indent_hanging"),
            path=path,
            key=f"{key}.indent_hanging",
            default=default_indent,
        ),
    )


def _parse_toc_heading(
    data: Mapping[str, Any] | None,
    *,
    heading1: HeadingStyle,
    path: Path,
) -> TocHeadingStyle:
    """Bangun ``TocHeadingStyle``; ``None`` mewarisi nilai dari heading 1."""

    if data is None:
        return TocHeadingStyle(
            heading_style="TOCHeading",
            font_family=heading1.font_family,
            font_size_half_points=heading1.font_size_half_points,
            bold=heading1.bold,
            color=heading1.color,
            alignment=heading1.alignment,
            space_before=heading1.space_before,
            space_after=heading1.space_after,
            line_spacing=heading1.line_spacing,
            first_line_indent=heading1.first_line_indent,
        )

    _check_unknown(data, _TOC_HEADING_KEYS, path=path, key="toc_heading")
    font_raw = data.get("font")
    if font_raw is not None and not isinstance(font_raw, str):
        raise _err(
            "'toc_heading.font' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key="toc_heading.font",
        )
    return TocHeadingStyle(
        heading_style=_text(
            data.get("heading_style"),
            path=path,
            key="toc_heading.heading_style",
            default="TOCHeading",
        ),
        font_family=_text(
            font_raw,
            path=path,
            key="toc_heading.font",
            default=heading1.font_family,
        ),
        font_size_half_points=_font_size(
            data.get("size"),
            path=path,
            key="toc_heading.size",
            default=f"{heading1.font_size_half_points / 2:g}pt",
        ),
        bold=_boolean(
            data.get("bold"),
            path=path,
            key="toc_heading.bold",
            default=heading1.bold,
        ),
        color=_color(
            data.get("color"),
            path=path,
            key="toc_heading.color",
            default=heading1.color,
        ),
        alignment=_alignment(
            data.get("alignment"),
            path=path,
            key="toc_heading.alignment",
            default=heading1.alignment,
        ),
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key="toc_heading.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key="toc_heading.space_after",
            default="0pt",
        ),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key="toc_heading.line_spacing",
            default=heading1.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
        first_line_indent=_dimension(
            data.get("first_line_indent"),
            path=path,
            key="toc_heading.first_line_indent",
            default="0cm",
        ),
    )


def _parse_caption_font(
    data: Mapping[str, Any],
    *,
    key: str,
    path: Path,
    defaults: CaptionFont,
    allow_alignment: bool,
) -> CaptionFont:
    """Bangun ``CaptionFont`` dari mapping font caption di atas ``defaults``."""

    _check_unknown(
        data,
        _TABLE_CAPTION_FONT_KEYS if allow_alignment else _CAPTION_FONT_KEYS,
        path=path,
        key=key,
    )
    alignment = defaults.alignment
    if allow_alignment:
        alignment = _alignment(
            data.get("alignment"),
            path=path,
            key=f"{key}.alignment",
            default=defaults.alignment,
        )
    return CaptionFont(
        family=_text(
            data.get("family"),
            path=path,
            key=f"{key}.family",
            default=defaults.family,
        ),
        size_half_points=_font_size(
            data.get("size"),
            path=path,
            key=f"{key}.size",
            default=f"{defaults.size_half_points / 2:g}pt",
        ),
        bold=_boolean(data.get("bold"), path=path, key=f"{key}.bold", default=defaults.bold),
        italic=_boolean(
            data.get("italic"), path=path, key=f"{key}.italic", default=defaults.italic
        ),
        color=_color(data.get("color"), path=path, key=f"{key}.color", default=defaults.color),
        alignment=alignment,
        space_before=_dimension(
            data.get("space_before"),
            path=path,
            key=f"{key}.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            data.get("space_after"),
            path=path,
            key=f"{key}.space_after",
            default="0pt",
        ),
        line_spacing=_number(
            data.get("line_spacing"),
            path=path,
            key=f"{key}.line_spacing",
            default=defaults.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
    )


def _parse_captions(
    data: Mapping[str, Any] | None,
    *,
    body: BodyFont,
    path: Path,
) -> CaptionsFormat:
    """Bangun ``CaptionsFormat`` gambar dan tabel.

    ``None`` memakai label serta font default. ``keep_next`` tabel wajib
    ``true`` dan separator tidak boleh memuat baris baru; pelanggaran melempar
    ``ConfigError``.
    """

    default_figure_font = CaptionFont(
        family=body.family,
        size_half_points=20,
        bold=False,
        italic=False,
        color="000000",
        alignment="center",
        space_before=0,
        space_after=0,
        line_spacing=1.0,
    )
    default_table_font = replace(default_figure_font, alignment="left")
    if data is None:
        return CaptionsFormat(
            figure=CaptionStyle("Gambar", " ", default_figure_font),
            table=CaptionStyle("Tabel", " ", default_table_font, keep_next=True),
        )

    _check_unknown(data, _CAPTIONS_KEYS, path=path, key="captions")

    figure_raw = _expect_mapping(data.get("figure", {}), path=path, key="captions.figure")
    _check_unknown(figure_raw, _CAPTION_KEYS, path=path, key="captions.figure")
    figure_font_raw = _expect_mapping(
        figure_raw.get("font", {}), path=path, key="captions.figure.font"
    )
    figure_font = _parse_caption_font(
        figure_font_raw,
        key="captions.figure.font",
        path=path,
        defaults=default_figure_font,
        allow_alignment=False,
    )

    table_raw = _expect_mapping(data.get("table", {}), path=path, key="captions.table")
    _check_unknown(table_raw, _CAPTION_KEYS, path=path, key="captions.table")
    table_font_raw = _expect_mapping(
        table_raw.get("font", {}), path=path, key="captions.table.font"
    )
    table_font = _parse_caption_font(
        table_font_raw,
        key="captions.table.font",
        path=path,
        defaults=default_table_font,
        allow_alignment=True,
    )
    table_keep_next = _boolean(
        table_raw.get("keep_next"),
        path=path,
        key="captions.table.keep_next",
        default=True,
    )
    if not table_keep_next:
        raise _err(
            "captions.table.keep_next harus true",
            code="CFG-TYPE",
            path=path,
            key="captions.table.keep_next",
        )

    figure = CaptionStyle(
        label=_text(
            figure_raw.get("label"),
            path=path,
            key="captions.figure.label",
            default="Gambar",
        ),
        separator=_text(
            figure_raw.get("separator", " "),
            path=path,
            key="captions.figure.separator",
            allow_empty=True,
        ),
        font=figure_font,
    )
    table = CaptionStyle(
        label=_text(
            table_raw.get("label"),
            path=path,
            key="captions.table.label",
            default="Tabel",
        ),
        separator=_text(
            table_raw.get("separator", " "),
            path=path,
            key="captions.table.separator",
            allow_empty=True,
        ),
        font=table_font,
        keep_next=table_keep_next,
    )
    for separator_key, separator in (
        ("captions.figure.separator", figure.separator),
        ("captions.table.separator", table.separator),
    ):
        if "\n" in separator or "\r" in separator:
            raise _err(
                f"{separator_key} tidak boleh memuat baris baru",
                code="CFG-TYPE",
                path=path,
                key=separator_key,
            )
    return CaptionsFormat(figure=figure, table=table)


def _parse_figures(
    data: Mapping[str, Any] | None,
    *,
    path: Path,
) -> FigureStyle:
    """Bangun ``FigureStyle`` dari ``figures`` dengan default kontrak."""

    raw = data or {}
    _check_unknown(raw, _FIGURE_KEYS, path=path, key="figures")
    return FigureStyle(
        caption_alignment=_alignment(
            raw.get("caption_alignment"),
            path=path,
            key="figures.caption_alignment",
            default="center",
        ),
        image_alignment=_alignment(
            raw.get("image_alignment"),
            path=path,
            key="figures.image_alignment",
            default="center",
        ),
        numbering=_enum(
            raw.get("numbering"),
            path=path,
            key="figures.numbering",
            choices=("chapter", "document"),
            default="chapter",
        ),
        space_before=_dimension(
            raw.get("space_before"),
            path=path,
            key="figures.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            raw.get("space_after"),
            path=path,
            key="figures.space_after",
            default="0pt",
        ),
        first_line_indent=_dimension(
            raw.get("first_line_indent"),
            path=path,
            key="figures.first_line_indent",
            default="0cm",
        ),
    )


def _parse_code(
    data: Mapping[str, Any] | None,
    *,
    mono: MonoFont,
    path: Path,
) -> CodeFormat:
    """Bangun ``CodeFormat`` dari ``code``.

    Hanya ``table.width=100%``, ``shading=none``, dan border ``single`` yang
    didukung; font mewarisi monospace bila tidak diisi. Pelanggaran melempar
    ``ConfigError``.
    """

    raw = data or {}
    _check_unknown(raw, _CODE_KEYS, path=path, key="code")
    font_raw = _expect_mapping(raw.get("font", {}), path=path, key="code.font")
    _check_unknown(font_raw, _CODE_FONT_KEYS, path=path, key="code.font")
    border_raw = _expect_mapping(raw.get("border", {}), path=path, key="code.border")
    _check_unknown(border_raw, _CODE_BORDER_KEYS, path=path, key="code.border")
    table_raw = _expect_mapping(raw.get("table", {}), path=path, key="code.table")
    _check_unknown(table_raw, _CODE_TABLE_KEYS, path=path, key="code.table")
    width = raw.get("table", {}).get("width", "100%")
    if width != "100%":
        raise _err(
            "code.table.width harus 100%",
            code="CFG-TYPE",
            path=path,
            key="code.table.width",
        )
    shading = raw.get("shading", "none")
    if shading != "none":
        raise _err(
            "code.shading hanya mendukung 'none'",
            code="CFG-TYPE",
            path=path,
            key="code.shading",
        )
    border_style = border_raw.get("style", "single")
    if border_style != "single":
        raise _err(
            "code.border.style harus 'single'",
            code="CFG-TYPE",
            path=path,
            key="code.border.style",
        )
    return CodeFormat(
        style=_text(
            raw.get("style"),
            path=path,
            key="code.style",
            default="SourceCode",
        ),
        font=CodeFont(
            family=_text(
                font_raw.get("family"),
                path=path,
                key="code.font.family",
                default=mono.family,
            ),
            size_half_points=_font_size(
                font_raw.get("size"),
                path=path,
                key="code.font.size",
                default=f"{mono.size_half_points / 2:g}pt",
            ),
            color=_color(font_raw.get("color"), path=path, key="code.font.color"),
        ),
        line_spacing=_number(
            raw.get("line_spacing"),
            path=path,
            key="code.line_spacing",
            default=1.0,
            minimum=0.5,
            maximum=3.0,
        ),
        space_before=_dimension(
            raw.get("space_before"),
            path=path,
            key="code.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            raw.get("space_after"),
            path=path,
            key="code.space_after",
            default="0pt",
        ),
        alignment=_alignment(
            raw.get("alignment"),
            path=path,
            key="code.alignment",
            default="left",
        ),
        shading=shading,
        border=CodeBorder(
            style=border_style,
            width=_dimension(
                border_raw.get("width"),
                path=path,
                key="code.border.width",
                default="1pt",
                positive=True,
            ),
            color=_color(border_raw.get("color"), path=path, key="code.border.color"),
        ),
        table=CodeTable(
            width_percent=100,
            cell_margin=_dimension(
                table_raw.get("cell_margin"),
                path=path,
                key="code.table.cell_margin",
                default="108twip",
            ),
        ),
        detect_styles=_text_list(
            raw.get("detect_styles"),
            path=path,
            key="code.detect_styles",
            default=_DEFAULT_DETECT_STYLES,
        ),
    )


def _parse_bibliography_style(
    data: Mapping[str, Any] | None,
    *,
    body: BodyFont,
    path: Path,
) -> BibliographyStyle:
    """Bangun ``BibliographyStyle`` dari ``bibliography_style``."""

    raw = data or {}
    _check_unknown(raw, _BIBLIOGRAPHY_STYLE_KEYS, path=path, key="bibliography_style")
    font_value = raw.get("font")
    if font_value is not None and not isinstance(font_value, str):
        raise _err(
            "'bibliography_style.font' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key="bibliography_style.font",
        )
    return BibliographyStyle(
        heading=_text(
            raw.get("heading"),
            path=path,
            key="bibliography_style.heading",
            default="DAFTAR PUSTAKA",
        ),
        font_family=_text(
            font_value,
            path=path,
            key="bibliography_style.font",
            default=body.family,
        ),
        font_size_half_points=_font_size(
            raw.get("size"),
            path=path,
            key="bibliography_style.size",
            default=f"{body.size_half_points / 2:g}pt",
        ),
        line_spacing=_number(
            raw.get("line_spacing"),
            path=path,
            key="bibliography_style.line_spacing",
            default=body.line_spacing,
            minimum=0.5,
            maximum=3.0,
        ),
        space_before=_dimension(
            raw.get("space_before"),
            path=path,
            key="bibliography_style.space_before",
            default="0pt",
        ),
        space_after=_dimension(
            raw.get("space_after"),
            path=path,
            key="bibliography_style.space_after",
            default="0pt",
        ),
        indent_left=_dimension(
            raw.get("indent_left"),
            path=path,
            key="bibliography_style.indent_left",
            default="1.27cm",
        ),
        indent_hanging=_dimension(
            raw.get("indent_hanging"),
            path=path,
            key="bibliography_style.indent_hanging",
            default="1.27cm",
        ),
    )


def _validate_image(path: Path) -> None:
    try:
        data = path.read_bytes()[:16]
    except OSError as exc:
        raise _err(
            f"logo tidak dapat dibaca: {exc}",
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.logo",
        ) from exc
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        valid = data.startswith(b"\xff\xd8\xff")
    elif suffix == ".png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n")
    else:
        valid = False
    if not valid:
        raise _err(
            "logo harus berupa JPEG/PNG yang valid",
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.logo",
        )


def _validate_reference_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise _err(
                    f"reference.docx rusak pada part {bad}",
                    code="CFG-ASSET-INVALID",
                    path=path,
                    key="assets.reference_docx",
                )
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise _err(
            "reference.docx bukan ZIP yang valid",
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.reference_docx",
        ) from exc
    except OSError as exc:
        raise _err(
            f"reference.docx tidak dapat dibaca: {exc}",
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.reference_docx",
        ) from exc
    required = {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}
    missing = sorted(required - names)
    if missing:
        raise _err(
            "reference.docx tidak memuat part wajib: " + ", ".join(missing),
            code="CFG-ASSET-INVALID",
            path=path,
            key="assets.reference_docx",
        )


def _validate_csl(path: Path) -> None:
    try:
        ElementTree.parse(path)
    except (ElementTree.ParseError, OSError) as exc:
        raise _err(
            f"citation.csl bukan XML yang valid: {exc}",
            code="CFG-ASSET-INVALID",
            path=path,
            key="citation.csl",
        ) from exc


def _parse_citation(data: Mapping[str, Any], *, format_dir: Path, path: Path) -> CitationFormat:
    """Validasi ``citation`` dan resolve path asetnya terhadap ``format_dir``.

    File CSL wajib ada, ber-ekstensi ``.csl``, dan XML valid; bibliography
    wajib ``.bib`` serta path relatif aman. Error aset memakai ``ConfigError``.
    """

    _check_unknown(data, _CITATION_KEYS, path=path, key="citation")
    csl = path_mod.safe_relative_path(
        _required(data, "csl", path=path, key="citation"),
        base=format_dir,
        label="citation.csl",
        code="CFG-ASSET-MISSING",
        must_exist=True,
        expect_file=True,
    )
    if csl.suffix.lower() != ".csl":
        raise _err(
            "citation.csl harus berekstensi .csl",
            code="CFG-TYPE",
            path=path,
            key="citation.csl",
        )
    _validate_csl(csl)
    bibliography = _text(
        data.get("bibliography"),
        path=path,
        key="citation.bibliography",
        default="references.bib",
    )
    path_mod.safe_relative_path(
        bibliography,
        base=format_dir,
        label="citation.bibliography",
        code="CFG-PATH-ESCAPE",
    )
    if not bibliography.lower().endswith(".bib"):
        raise _err(
            "citation.bibliography harus berekstensi .bib",
            code="CFG-TYPE",
            path=path,
            key="citation.bibliography",
        )
    locale = _text(
        data.get("locale"),
        path=path,
        key="citation.locale",
        default="id-ID",
    )
    return CitationFormat(
        csl=csl,
        bibliography=bibliography,
        locale=locale,
    )


def _parse_assets(data: Mapping[str, Any] | None, *, format_dir: Path, path: Path) -> AssetsFormat:
    raw = data or {}
    _check_unknown(raw, _ASSETS_KEYS, path=path, key="assets")
    logo_value = raw.get("logo")
    if logo_value is None:
        logo_value = "logo.jpg"
    logo = path_mod.safe_relative_path(
        logo_value,
        base=format_dir,
        label="assets.logo",
        code="CFG-ASSET-MISSING",
        must_exist=True,
        expect_file=True,
    )
    if logo.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise _err(
            "assets.logo harus .jpg, .jpeg, atau .png",
            code="CFG-TYPE",
            path=path,
            key="assets.logo",
        )
    _validate_image(logo)
    reference_value = raw.get("reference_docx")
    if reference_value is None:
        reference_value = "reference.docx"
    reference = path_mod.safe_relative_path(
        reference_value,
        base=format_dir,
        label="assets.reference_docx",
        code="CFG-ASSET-MISSING",
        must_exist=True,
        expect_file=True,
    )
    _validate_reference_docx(reference)
    return AssetsFormat(
        logo=logo,
        reference_docx=reference,
    )


def load_format(format_id: str, *, root: Path | None = None) -> Format:
    """Muat dan validasi ``formats/<format_id>/format.yml``.

    Mengembalikan ``Format`` immutable dengan path aset yang sudah di-resolve
    dan data YAML read-only. ``root`` opsional mengganti direktori data paket.
    Semua kegagalan I/O, skema, tipe, nilai, dan aset dilempar sebagai
    ``ConfigError``; tidak ada fallback ke format lain.
    """

    path_mod.validate_id(format_id, kind="format")
    directory = path_mod.format_dir(format_id, root=root)
    path = directory / "format.yml"
    if not path.is_file():
        raise ConfigError(
            f"format '{format_id}': format.yml tidak ditemukan",
            code="CFG-FORMAT-MISSING",
            path=path,
        )
    data = load_yaml_mapping(path, label="format.yml")
    _check_unknown(
        data,
        _FORMAT_KEYS,
        path=path,
        key="format",
    )
    declared = _text(
        _required(data, "format", path=path, key="format"),
        path=path,
        key="format.format",
    )
    if declared != format_id:
        raise _err(
            f"key 'format' bernilai '{declared}', tetapi direktori bernama '{format_id}'",
            code="CFG-TYPE",
            path=path,
            key="format.format",
        )

    page = _parse_page(
        _expect_mapping(_required(data, "page", path=path, key="format"), path=path, key="page"),
        path=path,
    )
    font_raw = _expect_mapping(
        _required(data, "font", path=path, key="format"), path=path, key="font"
    )
    _check_unknown(font_raw, _FONT_KEYS, path=path, key="font")
    body = _parse_body_font(
        _expect_mapping(
            _required(font_raw, "body", path=path, key="font"), path=path, key="font.body"
        ),
        path=path,
    )
    mono = _parse_mono_font(
        _expect_mapping(font_raw.get("monospace", {}), path=path, key="font.monospace"),
        path=path,
    )
    font = FontFormat(body=body, monospace=mono)

    abstract = _parse_abstract(
        _expect_mapping(data["abstract"], path=path, key="abstract")
        if data.get("abstract") is not None
        else None,
        body=body,
        path=path,
    )

    headings_raw = _expect_mapping(
        _required(data, "headings", path=path, key="format"),
        path=path,
        key="headings",
    )
    _check_unknown(headings_raw, _HEADINGS_KEYS, path=path, key="headings")
    styles_raw = _expect_mapping(
        _required(headings_raw, "styles", path=path, key="headings"),
        path=path,
        key="headings.styles",
    )
    expected_levels = {f"heading{level}" for level in (1, 2, 3)}
    _check_unknown(styles_raw, expected_levels, path=path, key="headings.styles")
    headings: dict[str, HeadingStyle] = {}
    for level in (1, 2, 3):
        style_key = f"heading{level}"
        style_raw = _expect_mapping(
            _required(styles_raw, style_key, path=path, key="headings.styles"),
            path=path,
            key=f"headings.styles.{style_key}",
        )
        headings[style_key] = _parse_heading_style(style_raw, level=level, body=body, path=path)

    toc_heading = _parse_toc_heading(
        _expect_mapping(data["toc_heading"], path=path, key="toc_heading")
        if data.get("toc_heading") is not None
        else None,
        heading1=headings["heading1"],
        path=path,
    )

    captions = _parse_captions(
        _expect_mapping(data["captions"], path=path, key="captions")
        if data.get("captions") is not None
        else None,
        body=body,
        path=path,
    )
    figures = _parse_figures(
        _expect_mapping(data["figures"], path=path, key="figures")
        if data.get("figures") is not None
        else None,
        path=path,
    )
    # Perataan caption gambar adalah milik figures.caption_alignment, bukan
    # captions.figure.font.alignment.
    captions = replace(
        captions,
        figure=replace(
            captions.figure,
            font=replace(captions.figure.font, alignment=figures.caption_alignment),
        ),
    )

    code = _parse_code(
        _expect_mapping(data["code"], path=path, key="code")
        if data.get("code") is not None
        else None,
        mono=mono,
        path=path,
    )
    bibliography_style = _parse_bibliography_style(
        _expect_mapping(data["bibliography_style"], path=path, key="bibliography_style")
        if data.get("bibliography_style") is not None
        else None,
        body=body,
        path=path,
    )
    citation = _parse_citation(
        _expect_mapping(
            _required(data, "citation", path=path, key="format"),
            path=path,
            key="citation",
        ),
        format_dir=directory,
        path=path,
    )
    assets = _parse_assets(
        _expect_mapping(data["assets"], path=path, key="assets")
        if data.get("assets") is not None
        else None,
        format_dir=directory,
        path=path,
    )
    path_mod.check_case_collisions(directory, label="format")

    return Format(
        id=format_id,
        name=_text(
            data.get("name"),
            path=path,
            key="name",
            default=format_id,
        ),
        description=_text(
            data.get("description", ""),
            path=path,
            key="description",
            default="",
            allow_empty=True,
        ),
        path=directory,
        data=MappingProxyType(dict(data)),
        page=page,
        font=font,
        abstract=abstract,
        headings=MappingProxyType(headings),
        toc_heading=toc_heading,
        captions=captions,
        figures=figures,
        code=code,
        bibliography_style=bibliography_style,
        citation=citation,
        assets=assets,
    )


def format_override_warning(document_format: str, structure: Structure) -> str | None:
    """Kembalikan peringatan bila format dokumen mengalahkan format struktur."""

    if document_format == structure.format_id:
        return None
    return (
        f"document.format '{document_format}' mengalahkan structure.format "
        f"'{structure.format_id}' (CFG-FORMAT-OVERRIDE)"
    )
