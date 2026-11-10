"""Stage ``numbering``: seragamkan indentasi daftar berurut DOCX.

Stage ini **tidak** mengubah ``w:numFmt`` atau ``w:lvlText`` yang sudah
dipilih Pandoc/Markdown. Yang dirapikan hanya indentasi, hanging, tab stop,
dan ``w:suff`` level numbering, serta bold langsung pada paragraf list dan
``w:rPr`` level.

Part yang dimutasi: ``word/document.xml`` dan, bila ada perubahan,
``word/numbering.xml``. Part lain tidak disentuh.
"""

import time
from dataclasses import dataclass, field

from lxml import etree

from ..docx.layout import (
    PPR_ORDER,
    document_root,
    has_deleted_ancestor,
    is_field_run,
    iter_paragraph_runs,
    new_element,
    set_document_root,
)
from ..docx.names import (
    W_PPR,
    W_RPR,
    W_VAL,
)
from ..docx.package import DocumentPackage
from ..docx.paragraphs import int_attribute
from ..docx.runs import strip_bold_from_rpr
from ..docx.xml import ensure_ppr, get_or_add, iter_paragraphs, qn, sha256_c14n
from ..errors import DocgenError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

W_ILVL = qn("w:ilvl")
W_LEFT = qn("w:left")
W_NUMID = qn("w:numId")

DOCUMENT_PART = "word/document.xml"
NUMBERING_PART = "word/numbering.xml"

INDENT_STEP_TWIPS = 720
HANGING_TWIPS = 720
MAX_LEVEL = 8
ORDERED_FORMATS = frozenset({"decimal", "lowerLetter"})

W_P = qn("w:p")
W_NUMPR = qn("w:numPr")
W_HANGING = qn("w:hanging")
W_FIRST_LINE = qn("w:firstLine")
W_FIRST_LINE_CHARS = qn("w:firstLineChars")
W_HANGING_CHARS = qn("w:hangingChars")
W_LEFT_CHARS = qn("w:leftChars")
W_START = qn("w:start")
W_START_CHARS = qn("w:startChars")
W_POS = qn("w:pos")
W_TABS = qn("w:tabs")
W_TAB = qn("w:tab")
W_SUFF = qn("w:suff")
W_NUM_FMT = qn("w:numFmt")
W_LVL_TEXT = qn("w:lvlText")
W_ABSTRACT_NUM = qn("w:abstractNum")
W_ABSTRACT_NUM_ID = qn("w:abstractNumId")
W_NUM = qn("w:num")
W_LVL = qn("w:lvl")

LVL_ORDER = tuple(
    qn(tag)
    for tag in (
        "w:start",
        "w:numFmt",
        "w:lvlRestart",
        "w:pStyle",
        "w:isLgl",
        "w:suff",
        "w:lvlText",
        "w:lvlPicBulletId",
        "w:legacy",
        "w:lvlJc",
        "w:pPr",
        "w:rPr",
    )
)


class NumberingError(DocgenError):
    """Kesalahan normalisasi numbering."""

    default_code = "NUMBERING"


@dataclass(frozen=True, slots=True)
class NumberingSpec:
    """Nilai indentasi daftar yang diterapkan."""

    indent_step_twips: int = INDENT_STEP_TWIPS
    hanging_twips: int = HANGING_TWIPS
    max_level: int = MAX_LEVEL
    ordered_formats: frozenset[str] = ORDERED_FORMATS
    strip_bold: bool = True

    def __post_init__(self) -> None:
        if self.indent_step_twips <= 0 or self.hanging_twips < 0:
            raise NumberingError("indentasi/hanging numbering tidak valid")
        if self.max_level < 0 or self.max_level > 8:
            raise NumberingError("max level numbering harus 0-8")


@dataclass
class NumberingReport:
    """Ringkasan pekerjaan stage numbering."""

    list_paragraphs: int = 0
    paragraphs_changed: int = 0
    paragraphs_unchanged: int = 0
    numbering_levels: int = 0
    numbering_levels_changed: int = 0
    bold_removed: int = 0
    skipped_bullet: int = 0
    unresolved: int = 0
    format_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "list_paragraphs": self.list_paragraphs,
            "paragraphs_changed": self.paragraphs_changed,
            "paragraphs_unchanged": self.paragraphs_unchanged,
            "numbering_levels": self.numbering_levels,
            "numbering_levels_changed": self.numbering_levels_changed,
            "bold_removed": self.bold_removed,
            "skipped_bullet": self.skipped_bullet,
            "unresolved": self.unresolved,
            "format_counts": dict(self.format_counts),
        }


# ---------------------------------------------------------------------------
# Utilitas XML
# ---------------------------------------------------------------------------


def _int_or(
    element: etree._Element,
    attribute: str,
    default: int | None,
) -> int | None:
    value = int_attribute(element, attribute)
    return default if value is None else value


def _int_child(
    parent: etree._Element,
    tag: str,
    default: int | None = None,
) -> int | None:
    element = parent.find(tag)
    if element is None:
        return default
    return _int_or(element, W_VAL, default)


def _strip_paragraph_bold(paragraph: etree._Element) -> int:
    removed = 0
    ppr = paragraph.find(W_PPR)
    if ppr is not None:
        rpr = ppr.find(W_RPR)
        if rpr is not None:
            removed += strip_bold_from_rpr(rpr)

    for run in iter_paragraph_runs(paragraph):
        if has_deleted_ancestor(run) or is_field_run(run, paragraph):
            continue
        rpr = run.find(W_RPR)
        if rpr is not None:
            removed += strip_bold_from_rpr(rpr)
    return removed


def _set_indentation(ppr: etree._Element, left: int, spec: NumberingSpec) -> bool:
    ind = get_or_add(ppr, "w:ind", PPR_ORDER)
    before = etree.tostring(ind)

    for attribute in (
        W_FIRST_LINE,
        W_FIRST_LINE_CHARS,
        W_HANGING_CHARS,
        W_LEFT_CHARS,
        W_START,
        W_START_CHARS,
    ):
        ind.attrib.pop(attribute, None)

    ind.set(W_LEFT, str(left))
    ind.set(W_HANGING, str(spec.hanging_twips))
    return etree.tostring(ind) != before


def _set_tab_stop(ppr: etree._Element, position: int) -> bool:
    """Pastikan tepat satu tab stop kiri pada posisi teks daftar."""

    tabs = get_or_add(ppr, "w:tabs", PPR_ORDER)
    before = etree.tostring(tabs)

    for child in list(tabs):
        tabs.remove(child)

    tab = new_element("w:tab")
    tab.set(W_VAL, "left")
    tab.set(W_POS, str(position))
    tabs.append(tab)
    return etree.tostring(tabs) != before


def _set_suff_tab(level: etree._Element) -> bool:
    suff = get_or_add(level, "w:suff", LVL_ORDER)
    before = etree.tostring(suff)
    suff.set(W_VAL, "tab")
    return etree.tostring(suff) != before


# ---------------------------------------------------------------------------
# Deteksi daftar
# ---------------------------------------------------------------------------


def _paragraph_reference(
    paragraph: etree._Element,
    max_level: int = MAX_LEVEL,
) -> tuple[int, int] | None:
    ppr = paragraph.find(W_PPR)
    if ppr is None:
        return None
    numpr = ppr.find(W_NUMPR)
    if numpr is None:
        return None

    num_id = _int_child(numpr, W_NUMID)
    if num_id is None or num_id <= 0:
        return None

    ilvl = _int_child(numpr, W_ILVL, 0) or 0
    if ilvl < 0 or ilvl > max_level:
        ilvl = 0
    return num_id, ilvl


def _level_format(level: etree._Element) -> tuple[str, str]:
    fmt_element = level.find(W_NUM_FMT)
    fmt = (fmt_element.get(W_VAL) or "").strip() if fmt_element is not None else ""
    if not fmt:
        fmt = "decimal"

    text_element = level.find(W_LVL_TEXT)
    text = text_element.get(W_VAL) or "" if text_element is not None else ""
    return fmt, text


def _format_label(fmt: str, lvl_text: str) -> str:
    if fmt == "decimal" and lvl_text.endswith("."):
        return "1."
    if fmt == "lowerLetter" and lvl_text.endswith("."):
        return "a."
    if fmt == "lowerLetter" and lvl_text.endswith(")"):
        return "a)"
    return fmt


def _build_numbering_index(
    root: etree._Element,
) -> dict[tuple[int, int], etree._Element]:
    abstracts: dict[int, etree._Element] = {}
    for abstract in root.findall(W_ABSTRACT_NUM):
        abstract_id = _int_or(abstract, W_ABSTRACT_NUM_ID, None)
        if abstract_id is not None:
            abstracts[abstract_id] = abstract

    num_to_abstract: dict[int, int] = {}
    for num in root.findall(W_NUM):
        num_id = _int_or(num, W_NUMID, None)
        abstract_id = _int_child(num, W_ABSTRACT_NUM_ID)
        if num_id is not None and abstract_id is not None:
            num_to_abstract[num_id] = abstract_id

    index: dict[tuple[int, int], etree._Element] = {}
    for num_id, abstract_id in num_to_abstract.items():
        abstract = abstracts.get(abstract_id)
        if abstract is None:
            continue
        for level in abstract.findall(W_LVL):
            ilvl = _int_or(level, W_ILVL, 0) or 0
            index[(num_id, ilvl)] = level
    return index


def _normalize_level(
    level: etree._Element,
    spec: NumberingSpec,
) -> tuple[bool, int]:
    ilvl = _int_or(level, W_ILVL, 0) or 0
    if ilvl < 0 or ilvl > spec.max_level:
        ilvl = 0

    ppr = get_or_add(level, "w:pPr", LVL_ORDER)
    left = spec.indent_step_twips * (ilvl + 1)

    changed = _set_indentation(ppr, left, spec)
    changed = _set_tab_stop(ppr, left) or changed
    changed = _set_suff_tab(level) or changed

    removed = 0
    if spec.strip_bold:
        rpr = level.find(W_RPR)
        if rpr is not None:
            removed = strip_bold_from_rpr(rpr)

    return changed or removed > 0, removed


# ---------------------------------------------------------------------------
# API utama
# ---------------------------------------------------------------------------


def format_numbering(
    package: DocumentPackage,
    *,
    spec: NumberingSpec | None = None,
) -> NumberingReport:
    """Rapikan numbering daftar berurut pada ``DocumentPackage`` hidup."""

    spec = spec or NumberingSpec()
    root = document_root(package)
    numbering_root: etree._Element | None = None
    if getattr(package, "has_part", None) and package.has_part(NUMBERING_PART):
        numbering_root = package.xml(NUMBERING_PART)

    doc_before = sha256_c14n(root)
    numbering_before = sha256_c14n(numbering_root) if numbering_root is not None else None

    numbering_index = _build_numbering_index(numbering_root) if numbering_root is not None else {}

    report = NumberingReport()
    document_changed = False
    numbering_changed = False
    referenced_levels: set[int] = set()

    for paragraph in iter_paragraphs(root):
        if has_deleted_ancestor(paragraph):
            continue
        reference = _paragraph_reference(paragraph, spec.max_level)
        if reference is None:
            continue

        _num_id, ilvl = reference
        level = numbering_index.get(reference)

        if level is None:
            report.unresolved += 1
            report.list_paragraphs += 1
            report.format_counts["tidak diketahui"] = (
                report.format_counts.get("tidak diketahui", 0) + 1
            )
        else:
            fmt, lvl_text = _level_format(level)
            if fmt not in spec.ordered_formats:
                report.skipped_bullet += 1
                continue
            report.list_paragraphs += 1
            label = _format_label(fmt, lvl_text)
            report.format_counts[label] = report.format_counts.get(label, 0) + 1

        ppr = ensure_ppr(paragraph)
        left = spec.indent_step_twips * (ilvl + 1)
        if _set_indentation(ppr, left, spec):
            report.paragraphs_changed += 1
            document_changed = True
        else:
            report.paragraphs_unchanged += 1
        if _set_tab_stop(ppr, left):
            document_changed = True

        if spec.strip_bold:
            removed = _strip_paragraph_bold(paragraph)
            if removed:
                report.bold_removed += removed
                document_changed = True

        if level is not None:
            referenced_levels.add(id(level))

    processed_levels: set[int] = set()
    for level in numbering_index.values():
        level_id = id(level)
        if level_id not in referenced_levels or level_id in processed_levels:
            continue
        processed_levels.add(level_id)
        report.numbering_levels += 1
        changed, removed = _normalize_level(level, spec)
        if changed:
            report.numbering_levels_changed += 1
            numbering_changed = True
        report.bold_removed += removed

    document_changed = document_changed or sha256_c14n(root) != doc_before
    if numbering_root is not None:
        numbering_changed = numbering_changed or sha256_c14n(numbering_root) != numbering_before

    if document_changed:
        set_document_root(package, root)
    if numbering_changed and numbering_root is not None:
        package.set_xml(NUMBERING_PART, numbering_root)
    return report


class NumberingStage(BaseStage):
    """Stage normalisasi indentasi/tab/bold daftar berurut."""

    name = StageName.NUMBERING
    order = 100
    requires = canonical_prefix(StageName.NUMBERING)
    mutates = frozenset({"word/document.xml", "word/numbering.xml"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        package = getattr(ctx, "package", None)
        if package is None:
            raise NumberingError("stage numbering membutuhkan DocumentPackage dari stage pandoc")

        try:
            before_document = sha256_c14n(document_root(package))
            has_numbering = bool(
                getattr(package, "has_part", None) and package.has_part(NUMBERING_PART)
            )
            before_numbering = sha256_c14n(package.xml(NUMBERING_PART)) if has_numbering else None
            report = format_numbering(package, spec=NumberingSpec())
            changed = sha256_c14n(document_root(package)) != before_document
            if not changed and before_numbering is not None:
                changed = sha256_c14n(package.xml(NUMBERING_PART)) != before_numbering
        except NumberingError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise NumberingError(
                f"stage numbering gagal: {exc}",
                code="NUMBERING-STAGE",
            ) from exc

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "list_paragraphs": report.list_paragraphs,
                "paragraphs_changed": report.paragraphs_changed,
                "numbering_levels": report.numbering_levels,
                "numbering_levels_changed": report.numbering_levels_changed,
                "bold_removed": report.bold_removed,
                "unresolved": report.unresolved,
            },
        )


__all__ = [
    "DOCUMENT_PART",
    "HANGING_TWIPS",
    "INDENT_STEP_TWIPS",
    "LVL_ORDER",
    "MAX_LEVEL",
    "NUMBERING_PART",
    "ORDERED_FORMATS",
    "PPR_ORDER",
    "NumberingError",
    "NumberingReport",
    "NumberingSpec",
    "NumberingStage",
    "format_numbering",
]
