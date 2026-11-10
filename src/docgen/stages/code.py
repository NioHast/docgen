"""Stage ``code``: blok kode DOCX menjadi tabel 1x1 berkotak penuh.

Deteksi memakai style paragraf yang sudah dinormalisasi (``Source Code``,
``Verbatim Char``, ``HTML Code``, ``HTML Preformatted``, atau daftar
``code.detect_styles`` dari format). Paragraf kode berurutan digabung menjadi
satu tabel 1x1; tabel kode lama dinormalisasi lebih dulu agar run pertama
untuk tabel baru melaporkan ``normalized_tables == 0`` dan run kedua juga 0.

Hanya ``word/document.xml`` yang dimutasi. Stage tidak memanggil
``load``/``save`` package; pipeline yang melakukannya.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

from ..docx import names
from ..docx.package import DOCUMENT_PART
from ..docx.tables import (
    NEUTRAL_BODY_TAGS,
    CodeSpec,
    TableError,
    collect_unsafe_children,
    document_body,
    is_code_paragraph,
    make_code_table,
    normalize_code_tables,
)
from ..docx.xml import sha256_c14n
from ..errors import DocgenError, StageError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from ..docx.package import DocumentPackage


@dataclass
class CodeReport:
    """Ringkasan pekerjaan stage kode."""

    tables: int = 0
    paragraphs: int = 0
    lines: int = 0
    normalized_tables: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    changed: bool = False


def _collect_code_blocks(
    body: etree._Element,
    report: CodeReport,
    detect_styles: Sequence[str] | None,
) -> list[list[etree._Element]]:
    """Kumpulkan deretan paragraf kode berurutan di level body."""

    blocks: list[list[etree._Element]] = []
    current: list[etree._Element] = []

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append(current)
            current = []

    for child in body:
        if child.tag == names.W_P:
            if is_code_paragraph(child, detect_styles):
                if collect_unsafe_children(child):
                    report.skipped += 1
                    flush()
                else:
                    current.append(child)
            else:
                flush()
        elif child.tag in NEUTRAL_BODY_TAGS:
            # Penanda bookmark/comment tidak memutus blok kode.
            continue
        else:
            flush()

    flush()
    return blocks


def _paragraph_line_count(paragraphs: Sequence[etree._Element]) -> int:
    """Hitung baris kode efektif: satu paragraf minimal satu baris."""

    lines = max(1, len(paragraphs))
    for paragraph in paragraphs:
        for element in paragraph.iter():
            if element is paragraph:
                continue
            if element.tag in (names.W_BR, names.W_CR):
                lines += 1
    return lines


def _apply_code_blocks(
    package: DocumentPackage,
    body: etree._Element,
    report: CodeReport,
    spec: CodeSpec,
) -> None:
    """Ganti setiap blok paragraf kode dengan satu tabel kode."""

    for block in _collect_code_blocks(body, report, spec.detect_styles):
        table = make_code_table(package, block, spec)
        block[0].addprevious(table)
        for paragraph in block:
            body.remove(paragraph)

        report.tables += 1
        report.paragraphs += len(block)
        report.lines += _paragraph_line_count(block)


def apply_code(
    package: DocumentPackage,
    *,
    spec: CodeSpec | None = None,
) -> CodeReport:
    """Format seluruh blok kode package dan normalisasi tabel kode lama."""

    code_spec = spec or CodeSpec()
    root = package.xml(DOCUMENT_PART)
    body = document_body(package)
    before = sha256_c14n(root)

    report = CodeReport()
    # Normalisasi tabel lama lebih dulu agar tabel baru tidak ikut dihitung
    # sebagai "normalized_tables" pada run pertama.
    report.normalized_tables = normalize_code_tables(package, spec=code_spec)
    _apply_code_blocks(package, body, report, code_spec)

    if report.skipped:
        report.warnings.append(
            f"{report.skipped} paragraf kode dilewati karena memuat field, "
            "section break, objek, atau perubahan terlacak; paragraf itu "
            "dibiarkan utuh."
        )

    report.changed = sha256_c14n(root) != before
    if report.changed:
        package.set_xml(DOCUMENT_PART, root)
    return report


def _get[T](value: object, name: str, default: T) -> T:
    return getattr(value, name, default)


def code_spec_from_format(format_value: object | None) -> CodeSpec:
    """Bangun ``CodeSpec`` dari ``format.code`` yang sudah divalidasi."""

    code = _get(format_value, "code", None) if format_value is not None else None
    if code is None:
        return CodeSpec()

    font = _get(code, "font", None)
    border = _get(code, "border", None)
    table = _get(code, "table", None)

    border_width = int(_get(border, "width", 20) or 20)
    border_size = max(1, round(border_width * 8 / 20))
    detect_styles = tuple(_get(code, "detect_styles", CodeSpec.detect_styles) or ())

    return CodeSpec(
        style_id=str(_get(code, "style", CodeSpec.style_id)),
        detect_styles=detect_styles or CodeSpec.detect_styles,
        font_family=str(_get(font, "family", CodeSpec.font_family)),
        font_size_half_points=int(_get(font, "size_half_points", CodeSpec.font_size_half_points)),
        color=str(_get(font, "color", CodeSpec.color)),
        alignment=str(_get(code, "alignment", CodeSpec.alignment)),
        line_spacing=float(_get(code, "line_spacing", CodeSpec.line_spacing)),
        space_before=int(_get(code, "space_before", CodeSpec.space_before)),
        space_after=int(_get(code, "space_after", CodeSpec.space_after)),
        border_style=str(_get(border, "style", CodeSpec.border_style)),
        border_size_eighth_points=border_size,
        border_color=str(_get(border, "color", CodeSpec.border_color)),
        cell_margin=int(_get(table, "cell_margin", CodeSpec.cell_margin)),
        width_percent=int(_get(table, "width_percent", CodeSpec.width_percent)),
    )


def _document_path(ctx: object) -> Path | None:
    document = getattr(ctx, "document", None)
    path = getattr(document, "path", None)
    return Path(path) if path is not None else None


class CodeStage(BaseStage):
    """Gabungkan paragraf kode menjadi tabel 1x1 dan normalisasi tabel lama."""

    name = StageName.CODE
    order = 60
    requires = canonical_prefix(StageName.CODE)
    mutates = frozenset({"word/document.xml"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        package = getattr(ctx, "package", None)
        if package is None:
            raise TableError(
                "stage code membutuhkan package DOCX dari stage pandoc",
                code="TABLE-NO-PACKAGE",
                path=_document_path(ctx),
            )

        spec = code_spec_from_format(getattr(ctx, "format", None))
        try:
            report = apply_code(package, spec=spec)
        except DocgenError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise StageError(
                self.name.value,
                f"stage code gagal: {exc}",
                cause=exc,
                path=_document_path(ctx),
                code="CODE-STAGE",
            ) from exc

        metrics = {
            "tables": report.tables,
            "paragraphs": report.paragraphs,
            "lines": report.lines,
            "normalized_tables": report.normalized_tables,
            "skipped": report.skipped,
        }
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=report.changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics=metrics,
            warnings=tuple(report.warnings),
        )


__all__ = [
    "CodeReport",
    "CodeStage",
    "apply_code",
    "code_spec_from_format",
]
