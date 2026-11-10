"""Stage ``captions/figures``: caption wajib, nomor bab, gambar, dan tabel.

Orkestrasi memakai helper domain ``docgen.docx.captions`` dan
``docgen.docx.tables``. Stage hanya memutasi ``word/document.xml`` pada
``DocumentPackage`` yang diberikan pipeline.
"""

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..docx.captions import (
    CaptionError,
    CaptionFontSpec,
    CaptionKind,
    CaptionReport,
    CaptionSpec,
    CaptionSpecs,
    FigureLayoutSpec,
    ensure_caption,
    find_caption,
    format_images,
    image_alt_text,
    iter_image_paragraphs,
    renumber_captions,
    table_caption_text,
)
from ..docx.package import DOCUMENT_PART
from ..docx.tables import (
    CodeSpec,
    TableError,
    format_tables,
    iter_tables,
)
from ..docx.xml import sha256_c14n
from ..errors import DocgenError, StageError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix
from .code import code_spec_from_format

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from ..docx.package import DocumentPackage


def _caption_font(font: object | None, *, alignment: str) -> CaptionFontSpec:
    if font is None:
        return CaptionFontSpec()
    return CaptionFontSpec(
        family=str(getattr(font, "family", "Times New Roman")),
        size_half_points=int(getattr(font, "size_half_points", 20)),
        bold=bool(getattr(font, "bold", False)),
        italic=bool(getattr(font, "italic", False)),
        color=str(getattr(font, "color", "000000")),
        space_before=int(getattr(font, "space_before", 0)),
        space_after=int(getattr(font, "space_after", 0)),
        line_spacing=float(getattr(font, "line_spacing", 1.0)),
    )


def _caption_specs_from_format(
    format_value: object | None,
) -> tuple[CaptionSpecs, FigureLayoutSpec]:
    """Terjemahkan ``format.captions``/``format.figures`` ke spec DOCX."""

    captions = getattr(format_value, "captions", None)
    figures = getattr(format_value, "figures", None)

    figure_style = getattr(captions, "figure", None)
    table_style = getattr(captions, "table", None)
    figure_font = getattr(figure_style, "font", None)
    table_font = getattr(table_style, "font", None)

    figure_alignment = str(getattr(figures, "caption_alignment", "center") or "center")
    table_alignment = str(getattr(table_font, "alignment", "left") or "left")

    figure = CaptionSpec(
        label=str(getattr(figure_style, "label", "Gambar") or "Gambar"),
        separator=str(getattr(figure_style, "separator", " ")) or " ",
        alignment=figure_alignment,
        keep_next=bool(getattr(figure_style, "keep_next", False)),
        font=_caption_font(figure_font, alignment=figure_alignment),
    )
    table = CaptionSpec(
        label=str(getattr(table_style, "label", "Tabel") or "Tabel"),
        separator=str(getattr(table_style, "separator", " ")) or " ",
        alignment=table_alignment,
        keep_next=bool(getattr(table_style, "keep_next", True)),
        font=_caption_font(table_font, alignment=table_alignment),
    )

    layout = FigureLayoutSpec(
        caption_alignment=str(getattr(figures, "caption_alignment", "center") or "center"),
        image_alignment=str(getattr(figures, "image_alignment", "center") or "center"),
        numbering=str(getattr(figures, "numbering", "chapter") or "chapter"),
        space_before=int(getattr(figures, "space_before", 0)),
        space_after=int(getattr(figures, "space_after", 0)),
        first_line_indent=int(getattr(figures, "first_line_indent", 0)),
    )
    return CaptionSpecs(figure=figure, table=table), layout


def _missing_table(index: int) -> str:
    return f"Tabel #{index}: tidak memiliki caption; tambahkan ': Judul tabel' pada Markdown."


def _missing_image(index: int) -> str:
    return (
        f"Gambar #{index}: tidak memiliki alt text/caption; tambahkan "
        "![deskripsi gambar](path) pada Markdown."
    )


def _ensure_table_captions(
    package: DocumentPackage,
    report: CaptionReport,
    code_spec: CodeSpec | None = None,
) -> None:
    index = 0
    detect_styles = (code_spec or CodeSpec()).detect_styles
    for info in iter_tables(package, detect_styles=detect_styles):
        if info.is_code:
            continue
        index += 1
        element = info.element
        source = table_caption_text(element)
        existing = find_caption(package, kind=CaptionKind.TABLE, anchor=element)

        if existing is not None and existing.text.strip():
            ensure_caption(
                package,
                kind=CaptionKind.TABLE,
                anchor=element,
                text=source,
            )
            continue
        if not source:
            report.missing_captions.append(_missing_table(index))
            continue

        try:
            ensure_caption(
                package,
                kind=CaptionKind.TABLE,
                anchor=element,
                text=source,
            )
        except CaptionError:
            report.missing_captions.append(_missing_table(index))
            continue
        report.created_table_captions += 1


def _ensure_image_captions(
    package: DocumentPackage,
    report: CaptionReport,
) -> None:
    index = 0
    for paragraph in iter_image_paragraphs(package):
        index += 1
        alt_text = image_alt_text(paragraph)
        existing = find_caption(package, kind=CaptionKind.FIGURE, anchor=paragraph)

        if existing is not None and existing.text.strip():
            ensure_caption(
                package,
                kind=CaptionKind.FIGURE,
                anchor=paragraph,
                text=alt_text,
            )
            continue
        if not alt_text:
            report.missing_captions.append(_missing_image(index))
            continue

        try:
            ensure_caption(
                package,
                kind=CaptionKind.FIGURE,
                anchor=paragraph,
                text=alt_text,
            )
        except CaptionError:
            report.missing_captions.append(_missing_image(index))
            continue
        report.created_image_captions += 1


def _ensure_captions(
    package: DocumentPackage,
    report: CaptionReport,
    code_spec: CodeSpec | None = None,
) -> None:
    """Buat caption dari sumber Pandoc dan catat objek tanpa caption."""

    _ensure_table_captions(package, report, code_spec)
    _ensure_image_captions(package, report)


def _merge_renumber(report: CaptionReport, numbered: CaptionReport) -> None:
    report.heading1_count = numbered.heading1_count
    report.bab_headings = numbered.bab_headings
    report.image_captions = numbered.image_captions
    report.table_captions = numbered.table_captions
    report.skipped_no_chapter = numbered.skipped_no_chapter
    report.skipped_field = numbered.skipped_field


def _add_warnings(report: CaptionReport, scope: str) -> None:
    if scope == "chapter":
        if report.bab_headings == 0:
            if report.heading1_count == 0:
                report.warnings.append("Tidak ada paragraf Heading1; penomoran caption dilewati.")
            else:
                report.warnings.append(
                    "Tidak ada Heading1 berformat 'BAB <romawi/arab>' atau "
                    "'<nomor arab>. <judul>'; penomoran caption dilewati."
                )
        elif report.skipped_no_chapter:
            report.warnings.append(
                f"{report.skipped_no_chapter} caption sebelum bab pertama "
                "dilewati (belum ada nomor bab)."
            )

    if report.skipped_field:
        report.warnings.append(
            f"{report.skipped_field} caption dilewati karena prefix nomornya "
            "memuat field; field dibiarkan utuh."
        )


def _missing_message(report: CaptionReport) -> str:
    lines = "\n".join(f"  - {item}" for item in report.missing_captions)
    return (
        "tabel/gambar berikut tidak memiliki caption:\n"
        f"{lines}\n"
        "Tambahkan ': Judul tabel' pada tabel dan alt text pada gambar di "
        "Markdown, lalu build ulang."
    )


def apply_captions(
    package: DocumentPackage,
    *,
    scope: str = "chapter",
    caption_specs: CaptionSpecs | None = None,
    figure_spec: FigureLayoutSpec | None = None,
    code_spec: CodeSpec | None = None,
    require_captions: bool = True,
    path: str | Path | None = None,
) -> CaptionReport:
    """Format tabel/gambar, pastikan caption, lalu beri nomor per bab."""

    root = package.xml(DOCUMENT_PART)
    before = sha256_c14n(root)

    specs = caption_specs or CaptionSpecs()
    layout = figure_spec or FigureLayoutSpec()
    report = CaptionReport()

    report.tables = format_tables(package, code_spec=code_spec)
    report.image_paragraphs, report.images_clamped = format_images(package, spec=layout)

    _ensure_captions(package, report, code_spec)
    _merge_renumber(
        report,
        renumber_captions(package, scope=scope, spec=specs),
    )
    _add_warnings(report, scope)

    report.changed = sha256_c14n(root) != before
    if report.changed:
        package.set_xml(DOCUMENT_PART, root)

    if require_captions and report.missing_captions:
        raise CaptionError(
            _missing_message(report),
            code="CAPTION-MISSING",
            missing=report.missing_captions,
            path=path,
        )
    return report


def _document_path(ctx: object) -> Path | None:
    document = getattr(ctx, "document", None)
    path = getattr(document, "path", None)
    return Path(path) if path is not None else None


def _apply_from_context(
    package: DocumentPackage,
    ctx: object,
) -> CaptionReport:
    caption_specs, figure_spec = _caption_specs_from_format(getattr(ctx, "format", None))
    code_spec = code_spec_from_format(getattr(ctx, "format", None))
    try:
        return apply_captions(
            package,
            scope=figure_spec.numbering,
            caption_specs=caption_specs,
            figure_spec=figure_spec,
            code_spec=code_spec,
            path=_document_path(ctx),
        )
    except DocgenError:
        raise
    except Exception as exc:  # pragma: no cover - pengaman kontrak
        raise StageError(
            "captions/figures",
            f"stage caption gagal: {exc}",
            cause=exc,
            path=_document_path(ctx),
            code="CAPTION-STAGE",
        ) from exc


def _stage_metrics(report: CaptionReport) -> dict[str, int]:
    return {
        "image_captions": report.image_captions,
        "table_captions": report.table_captions,
        "created_image_captions": report.created_image_captions,
        "created_table_captions": report.created_table_captions,
        "images_clamped": report.images_clamped,
        "tables": report.tables,
        "missing_captions": len(report.missing_captions),
    }


class CaptionsStage(BaseStage):
    """Stage publik ``captions/figures``."""

    name = StageName.CAPTIONS
    order = 70
    requires = canonical_prefix(StageName.CAPTIONS)
    mutates = frozenset({"word/document.xml"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        package = getattr(ctx, "package", None)
        if package is None:
            raise TableError(
                "stage captions/figures membutuhkan package DOCX dari stage pandoc",
                code="TABLE-NO-PACKAGE",
                path=_document_path(ctx),
            )

        report = _apply_from_context(package, ctx)
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=report.changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics=_stage_metrics(report),
            warnings=tuple(report.warnings),
        )


__all__ = [
    "CaptionStage",
    "CaptionsStage",
    "apply_captions",
    "format_figures",
]

CaptionStage = CaptionsStage
format_figures = apply_captions
