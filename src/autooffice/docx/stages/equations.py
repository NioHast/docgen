"""Stage ``equations``: beri nomor persamaan display OMML per bab.

Persamaan display dikenali dari ``m:oMathPara`` anak langsung ``w:p`` atau
``m:oMath`` langsung yang paragrafnya tidak memuat prosa selain nomor
``(bab.n)``. Nomor ditulis sebagai run biasa di luar OMML, sehingga isi
persamaan tidak berubah.

Nomor bab berasal dari Heading1 atau ``ChapterTitle`` berformat
``BAB <romawi/arab>``. Counter direset setiap bab baru dan bertambah untuk
setiap paragraf persamaan, termasuk persamaan ber-field yang dilewati.
"""

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from lxml import etree

from ..errors import DocgenError
from ..package.fields import has_field
from ..package.layout import (
    PPR_ORDER,
    document_root,
    has_deleted_ancestor,
    is_chapter_heading,
    iter_paragraphs,
    new_element,
    set_document_root,
)
from ..package.names import (
    W_R,
    W_RPR,
    W_T,
    W_TAB,
    W_VAL,
    normalize_style_id,
)
from ..package.numbering import chapter_number
from ..package.package import DocumentPackage
from ..package.page import content_width
from ..package.paragraphs import document_body, paragraph_style_id, paragraph_text
from ..package.xml import ensure_ppr, get_or_add, qn, sha256_c14n
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

W_LEFT = qn("w:left")
W_FIRST_LINE = qn("w:firstLine")

M_O_MATH_PARA = qn("m:oMathPara")
M_O_MATH = qn("m:oMath")

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_SECT_PR = qn("w:sectPr")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_SPACING = qn("w:spacing")
W_IND = qn("w:ind")
W_TABS = qn("w:tabs")
W_JC = qn("w:jc")

EQUATION_NUMBER_RE = re.compile(r"\(\d+\.\d+\)")
DEFAULT_LEFT_INDENT_TWIPS = 1440
DEFAULT_SPACING_TWIPS = 0
DEFAULT_JUSTIFICATION = "left"
HEADING1_STYLES = frozenset({"heading1", "chaptertitle"})


class EquationError(DocgenError):
    """Kesalahan penomoran persamaan."""

    default_code = "EQUATION"


@dataclass(frozen=True, slots=True)
class EquationSpec:
    """Nilai format paragraf persamaan."""

    left_indent_twips: int = DEFAULT_LEFT_INDENT_TWIPS
    spacing_twips: int = DEFAULT_SPACING_TWIPS
    justification: str = DEFAULT_JUSTIFICATION
    chapter_styles: frozenset[str] = HEADING1_STYLES

    def __post_init__(self) -> None:
        if self.left_indent_twips < 0:
            raise EquationError("indentasi kiri persamaan tidak boleh negatif")
        if self.spacing_twips < 0:
            raise EquationError("spacing persamaan tidak boleh negatif")
        if self.justification not in {"left", "right", "center", "both", "justify"}:
            raise EquationError(f"justification persamaan tidak dikenal: {self.justification!r}")


@dataclass
class EquationReport:
    """Ringkasan pekerjaan penomoran persamaan."""

    heading1_count: int = 0
    chapter_headings: int = 0
    equation_paragraphs: int = 0
    numbered: int = 0
    skipped_no_chapter: int = 0
    skipped_field: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "heading1_count": self.heading1_count,
            "bab_headings": self.chapter_headings,
            "equation_paragraphs": self.equation_paragraphs,
            "numbered": self.numbered,
            "skipped_no_chapter": self.skipped_no_chapter,
            "skipped_field": self.skipped_field,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Deteksi persamaan dan nomor
# ---------------------------------------------------------------------------


def is_chapter_paragraph(paragraph: etree._Element) -> bool:
    """True untuk Heading1/``ChapterTitle`` yang membuka bab."""

    return is_chapter_heading(paragraph_style_id(paragraph))


def display_equation(paragraph: etree._Element) -> etree._Element | None:
    """Kembalikan elemen persamaan display anak langsung ``w:p``."""

    equations = paragraph.findall(M_O_MATH_PARA)
    if equations:
        return equations[-1]

    equations = paragraph.findall(M_O_MATH)
    if not equations:
        return None
    text = paragraph_text(paragraph).strip()
    if text and EQUATION_NUMBER_RE.fullmatch(text) is None:
        return None
    return equations[-1]


def run_number_text(run: etree._Element) -> str | None:
    """Teks nomor pada run, atau ``None`` bila bukan run nomor persamaan."""

    parts: list[str] = []
    for child in run:
        if child.tag == W_T:
            parts.append(child.text or "")
        elif child.tag in (W_RPR, W_TAB):
            continue
        else:
            return None
    text = "".join(parts).strip()
    return text if EQUATION_NUMBER_RE.fullmatch(text) else None


def iter_equation_paragraphs(body: etree._Element) -> Sequence[etree._Element]:
    """Paragraf persamaan display body dan sel tabel (tanpa text box)."""

    result: list[etree._Element] = []
    for paragraph in iter_paragraphs(body):
        if has_deleted_ancestor(paragraph):
            continue
        if display_equation(paragraph) is not None:
            result.append(paragraph)
    return result


# ---------------------------------------------------------------------------
# Format paragraf
# ---------------------------------------------------------------------------


def _set_right_tab(ppr: etree._Element, position: int) -> None:
    tabs = get_or_add(ppr, "w:tabs", PPR_ORDER)
    for tab in list(tabs.findall(W_TAB)):
        if tab.get(qn("w:pos")) == str(position):
            tabs.remove(tab)

    tab = new_element("w:tab")
    tab.set(W_VAL, "right")
    tab.set(qn("w:pos"), str(position))
    tabs.append(tab)


def _set_spacing(ppr: etree._Element, spacing_twips: int) -> None:
    spacing = get_or_add(ppr, "w:spacing", PPR_ORDER)
    spacing.set(qn("w:before"), str(spacing_twips))
    spacing.set(qn("w:after"), str(spacing_twips))
    for attribute in (
        qn("w:beforeLines"),
        qn("w:afterLines"),
        qn("w:beforeAutospacing"),
        qn("w:afterAutospacing"),
    ):
        spacing.attrib.pop(attribute, None)


def _set_indent(ppr: etree._Element, left_twips: int) -> None:
    indent = get_or_add(ppr, "w:ind", PPR_ORDER)
    indent.set(W_LEFT, str(left_twips))
    # Normal style memakai first-line indent; persamaan harus mulai tepat dua
    # tab dari margin.
    indent.set(W_FIRST_LINE, "0")
    for attribute in (
        qn("w:leftChars"),
        qn("w:firstLineChars"),
        qn("w:hanging"),
        qn("w:hangingChars"),
    ):
        indent.attrib.pop(attribute, None)


def _set_justification(ppr: etree._Element, value: str) -> None:
    justification = get_or_add(ppr, "w:jc", PPR_ORDER)
    justification.set(W_VAL, value)


def _rebuild_number_run(run: etree._Element, number: str) -> None:
    properties = run.find(W_RPR)
    for child in list(run):
        if child is not properties:
            run.remove(child)

    run.append(new_element("w:tab"))
    text_node = new_element("w:t")
    text_node.text = number
    run.append(text_node)


def _set_number_run(
    paragraph: etree._Element,
    equation: etree._Element,
    number: str,
) -> None:
    """Tambahkan/ganti run nomor setelah persamaan tanpa menyentuh OMML."""

    start = paragraph.index(equation) + 1
    siblings = list(paragraph)
    existing = [
        child
        for child in siblings[start:]
        if child.tag == W_R and run_number_text(child) is not None
    ]

    if existing:
        primary = existing[0]
        _rebuild_number_run(primary, number)
        for duplicate in existing[1:]:
            paragraph.remove(duplicate)
        return

    run = new_element("w:r")
    run.append(new_element("w:tab"))
    text_node = new_element("w:t")
    text_node.text = number
    run.append(text_node)
    equation.addnext(run)


def format_equation_paragraph(
    paragraph: etree._Element,
    equation: etree._Element,
    number: str,
    *,
    content_width_twips: int,
    spec: EquationSpec,
) -> None:
    """Terapkan format final dan nomor pada satu paragraf persamaan."""

    ppr = ensure_ppr(paragraph)
    _set_right_tab(ppr, content_width_twips)
    _set_spacing(ppr, spec.spacing_twips)
    _set_indent(ppr, spec.left_indent_twips)
    _set_justification(ppr, spec.justification)
    _set_number_run(paragraph, equation, number)


# ---------------------------------------------------------------------------
# API utama
# ---------------------------------------------------------------------------


def _apply_numbers(body: etree._Element, report: EquationReport, spec: EquationSpec) -> None:
    """Beri nomor persamaan per bab dan perbarui ``report``.

    Paragraf terhapus dilewati; persamaan sebelum heading bab atau yang sudah
    memuat field dicatat sebagai skipped. Lebar konten dihitung sekali saat
    persamaan pertama ditemukan. Tidak mengembalikan nilai.
    """

    width: int | None = None
    current_chapter: int | None = None
    counter = 0

    for paragraph in iter_paragraphs(body):
        if has_deleted_ancestor(paragraph):
            continue

        style_id = paragraph_style_id(paragraph)

        if is_chapter_heading(style_id) or normalize_style_id(style_id) in spec.chapter_styles:
            report.heading1_count += 1
            chapter = chapter_number(paragraph_text(paragraph))
            if chapter is not None:
                report.chapter_headings += 1
                current_chapter = chapter
                counter = 0
            continue

        equation = display_equation(paragraph)
        if equation is None:
            continue

        report.equation_paragraphs += 1
        if current_chapter is None:
            report.skipped_no_chapter += 1
            continue

        counter += 1
        if has_field(paragraph):
            report.skipped_field += 1
            continue

        if width is None:
            # Hindari membaca geometri section untuk dokumen tanpa persamaan:
            # stage ini tidak boleh gagal hanya karena sectPr tidak ada.
            width = content_width(body)
        number = f"({current_chapter}.{counter})"
        format_equation_paragraph(
            paragraph,
            equation,
            number,
            content_width_twips=width,
            spec=spec,
        )
        report.numbered += 1


def _add_warnings(report: EquationReport) -> None:
    if report.chapter_headings == 0:
        if report.heading1_count == 0:
            report.warnings.append(
                "Tidak ada paragraf Heading1/ChapterTitle; penomoran persamaan dilewati."
            )
        else:
            report.warnings.append(
                "Tidak ada Heading1/ChapterTitle berformat 'BAB <romawi/arab>'; "
                "penomoran persamaan dilewati."
            )
    elif report.skipped_no_chapter:
        report.warnings.append(
            f"{report.skipped_no_chapter} persamaan sebelum bab pertama "
            "dilewati (belum ada nomor bab)."
        )

    if report.skipped_field:
        report.warnings.append(
            f"{report.skipped_field} persamaan dilewati karena paragrafnya "
            "memuat field; field dibiarkan utuh."
        )


def format_equations(
    package: DocumentPackage,
    *,
    spec: EquationSpec | None = None,
) -> EquationReport:
    """Beri nomor persamaan display pada ``DocumentPackage`` hidup."""

    spec = spec or EquationSpec()
    root = document_root(package)
    body = document_body(package)
    before_hash = sha256_c14n(root)

    report = EquationReport()
    _apply_numbers(body, report, spec)
    _add_warnings(report)

    if sha256_c14n(root) != before_hash:
        set_document_root(package, root)
    return report


class EquationsStage(BaseStage):
    """Stage penomoran persamaan display per bab."""

    name = StageName.EQUATIONS
    order = 90
    requires = canonical_prefix(StageName.EQUATIONS)
    mutates = frozenset({"word/document.xml"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        package = getattr(ctx, "package", None)
        if package is None:
            raise EquationError("stage equations membutuhkan DocumentPackage dari stage pandoc")

        try:
            before = sha256_c14n(document_root(package))
            report = format_equations(package, spec=_spec_from_context(ctx))
            changed = sha256_c14n(document_root(package)) != before
        except EquationError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise EquationError(
                f"stage equations gagal: {exc}",
                code="EQUATION-STAGE",
            ) from exc

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "heading1_count": report.heading1_count,
                "bab_headings": report.chapter_headings,
                "equation_paragraphs": report.equation_paragraphs,
                "numbered": report.numbered,
                "skipped_no_chapter": report.skipped_no_chapter,
                "skipped_field": report.skipped_field,
            },
            warnings=tuple(report.warnings),
        )


def _spec_from_context(ctx: object) -> EquationSpec:
    """Nilai persamaan berasal dari aturan layout, bukan spacing body."""

    del ctx  # kontrak equations memakai nilai tetap, bukan spacing body
    return EquationSpec()


__all__ = [
    "DEFAULT_LEFT_INDENT_TWIPS",
    "DEFAULT_SPACING_TWIPS",
    "EQUATION_NUMBER_RE",
    "HEADING1_STYLES",
    "M_O_MATH",
    "M_O_MATH_PARA",
    "EquationError",
    "EquationReport",
    "EquationSpec",
    "EquationsStage",
    "display_equation",
    "format_equation_paragraph",
    "format_equations",
    "is_chapter_paragraph",
    "iter_equation_paragraphs",
    "run_number_text",
]
