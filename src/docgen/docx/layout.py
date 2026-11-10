"""Helper layout paragraf untuk stage ``normalize`` dan stage DOCX lain.

Modul ini adalah satu tempat untuk:

* urutan child ``w:pPr``/``w:rPr`` dan helper ``get_or_add``;
* traversal paragraf/run yang aman terhadap text box dan tracked changes;
* parser field kompleks/sederhana;
* penghapusan bold langsung dengan pengecualian run field;
* pembacaan/penulisan ``word/document.xml`` melalui ``DocumentPackage``;
* deteksi ``ChapterTitle``/Heading1 sebagai paragraf bab.

Tidak ada I/O ZIP di modul ini. Semua mutasi part dilakukan lewat
``DocumentPackage`` agar aturan satu load/satu save tetap berlaku.
"""

import copy
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from lxml import etree

from . import DocxError, paragraphs, runs
from .names import (
    W_DEL,
    W_FLDCHAR,
    W_FLDCHARTYPE,
    W_FLDSIMPLE,
    W_INSTR,
    W_INSTRTEXT,
    W_MOVE_TO,
    W_MOVEFROM,
    W_P,
    W_PPR,
    W_RPR,
    W_SDT,
    W_SECTPR,
    W_TBL,
    W_TXBXCONTENT,
    W_VAL,
    normalize_style_id,
)
from .package import DOCUMENT_PART
from .xml import (
    PPR_ORDER,
    RPR_ORDER,
    ensure_ppr,
    ensure_rpr,
    get_or_add,
    insert_ordered,
    is_on,
    iter_paragraphs,
    iter_runs,
    qn,
    sha256_c14n,
)

W_B = qn("w:b")
W_BCS = qn("w:bCs")

__all__ = [
    "PPR_ORDER",
    "RPR_ORDER",
    "BodyUnit",
    "LayoutError",
    "LayoutReport",
    "LayoutSpec",
    "content_width",
    "document_root",
    "ensure_ppr",
    "ensure_rpr",
    "field_name",
    "get_or_add",
    "has_bold_field",
    "has_deleted_ancestor",
    "has_exempt_field",
    "has_field",
    "insert_ordered",
    "is_bold_run",
    "is_chapter_heading",
    "is_exempt",
    "is_exempt_style",
    "is_field_run",
    "is_on",
    "iter_body_units",
    "iter_field_instructions",
    "iter_field_markers",
    "iter_field_runs",
    "iter_paragraph_runs",
    "iter_paragraphs",
    "iter_runs",
    "new_element",
    "normalize_layout",
    "normalize_paragraph",
    "preserve_tabs",
    "read_part",
    "set_document_root",
    "strip_bold_from_run",
    "strip_paragraph_bold",
    "write_part",
]


class LayoutError(DocxError):
    """Kesalahan layout paragraf atau part ``word/document.xml``."""

    default_code = "LAYOUT"


# ---------------------------------------------------------------------------
# Spesifikasi dan laporan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    """Nilai layout yang diterapkan ke paragraf non-pengecualian.

    ``line_spacing`` (pengali) boleh diberikan bila caller belum mengonversi
    ke twip. Bila ``None``, ``line_spacing_twips`` dipakai langsung.
    """

    line_spacing_twips: int = 360
    space_before: int = 0
    space_after: int = 0
    alignment: str = "both"
    preserve_right_alignment: bool = True
    strip_bold: bool = True
    exempt_fields: frozenset[str] = frozenset({"TOC", "PAGEREF", "SEQ"})
    line_spacing: float | None = None

    def __post_init__(self) -> None:
        if self.line_spacing_twips < 0:
            raise LayoutError("line spacing tidak boleh negatif")
        if self.line_spacing is not None and self.line_spacing <= 0:
            raise LayoutError("line spacing pengali harus lebih dari 0")
        if self.space_before < 0 or self.space_after < 0:
            raise LayoutError("spacing before/after tidak boleh negatif")
        if self.alignment not in {"left", "right", "center", "both", "justify"}:
            raise LayoutError(f"alignment tidak dikenal: {self.alignment!r}")

    @property
    def effective_line_spacing_twips(self) -> int:
        if self.line_spacing is not None:
            return round(float(self.line_spacing) * 240)
        return self.line_spacing_twips

    @classmethod
    def from_format(cls, format_obj: object) -> LayoutSpec:
        """Bangun spec dari ``Format`` (``format.font.body``) secara defensif."""

        font = getattr(format_obj, "font", None)
        body = getattr(font, "body", None)
        line = getattr(body, "line_spacing", None)
        alignment = str(getattr(body, "alignment", "both") or "both")
        if alignment == "justify":
            alignment = "both"
        kwargs: dict[str, object] = {
            "space_before": int(getattr(body, "space_before", 0) or 0),
            "space_after": int(getattr(body, "space_after", 0) or 0),
            "alignment": alignment,
        }
        if line is not None:
            kwargs["line_spacing"] = float(line)
        return cls(**kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class LayoutReport:
    """Ringkasan normalisasi layout."""

    checked: int = 0
    normalized: int = 0
    skipped: int = 0
    fields_preserved: int = 0
    unchanged: int = 0
    bold_paragraphs: int = 0
    bold_runs_removed: int = 0


# ---------------------------------------------------------------------------
# Konstanta gaya dan field
# ---------------------------------------------------------------------------

CODE_STYLES = frozenset({"sourcecode", "verbatimchar", "htmlcode", "htmlpreformatted"})
CAPTION_STYLES = frozenset({"caption", "imagecaption", "tablecaption"})
FIGURE_STYLES = frozenset({"figure", "captionedfigure", "figurecaption"})
CUSTOM_HEADING_STYLES = frozenset({"chaptertitle"})
CHAPTER_HEADING_STYLES = frozenset({"heading1", "chaptertitle"})
TOC_STYLE_RE = re.compile(r"^toc[1-9]$|^tocheading$")
HEADING_STYLE_RE = re.compile(r"^heading([1-9])$")
COVER_PREFIX = "cover"
COVER_TITLE_STYLE = "covertitle"
TITLE_STYLE = "title"
EXEMPT_FIELDS = frozenset({"TOC", "PAGEREF", "SEQ"})

FIELD_NAME_RE = re.compile(r"\s*([A-Za-z]+)")

DEFAULT_CONTENT_WIDTH_TWIPS = 9072

TRACKED_INSERT_TAGS = frozenset({qn("w:ins"), W_MOVE_TO})
TRACKED_DELETE_TAGS = frozenset({W_DEL, W_MOVEFROM})
TRACKED_TAGS = TRACKED_INSERT_TAGS | TRACKED_DELETE_TAGS
BODY_BLOCK_TAGS = frozenset({W_P, W_TBL, W_SDT, W_SECTPR})


# ---------------------------------------------------------------------------
# Referensi silang ke helper XML agar stage cukup mengimpor satu modul
# ---------------------------------------------------------------------------


def new_element(tag: str) -> etree._Element:
    """Buat elemen baru dari nama OOXML (``w:tab``, ``w:r``, dst.)."""

    return etree.Element(qn(tag))


def iter_paragraph_runs(paragraph: etree._Element) -> Iterator[etree._Element]:
    """Iterasi run paragraf tanpa run di text box/paragraf bersarang."""

    yield from iter_runs(paragraph)


# ---------------------------------------------------------------------------
# Parser field
# ---------------------------------------------------------------------------


def iter_field_markers(
    paragraph: etree._Element,
) -> Iterator[etree._Element]:
    """Iterasi ``w:fldChar``/``w:instrText``/``w:fldSimple`` berurutan.

    Paragraf bersarang dan text box tidak dianggap bagian field paragraf ini.
    """

    def walk(element: etree._Element) -> Iterator[etree._Element]:
        for child in element:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag in (W_P, W_TXBXCONTENT):
                continue
            if tag in (W_FLDCHAR, W_INSTRTEXT, W_FLDSIMPLE):
                yield child
            yield from walk(child)

    yield from walk(paragraph)


def iter_field_instructions(paragraph: etree._Element) -> Iterator[str]:
    """Hasilkan instruksi field lengkap, termasuk yang terpecah antar-run."""

    stack: list[list[str]] = []
    for marker in iter_field_markers(paragraph):
        if marker.tag == W_FLDCHAR:
            field_type = marker.get(W_FLDCHARTYPE)
            if field_type == "begin":
                stack.append([])
            elif field_type == "end" and stack:
                yield "".join(stack.pop())
        elif marker.tag == W_INSTRTEXT:
            if stack:
                stack[-1].append(marker.text or "")
        elif marker.tag == W_FLDSIMPLE:
            yield marker.get(W_INSTR) or ""

    # Field yang tidak ditutup tetap dianggap milik paragraf ini.
    for parts in stack:
        yield "".join(parts)


def field_name(instruction: str) -> str | None:
    """Nama field dari kata pertama instruksi (huruf besar)."""

    match = FIELD_NAME_RE.match(instruction)
    return match.group(1).upper() if match else None


def has_field(paragraph: etree._Element) -> bool:
    """True bila paragraf memuat field kompleks atau sederhana."""

    return any(element.tag in (W_FLDCHAR, W_INSTRTEXT, W_FLDSIMPLE) for element in paragraph.iter())


def has_exempt_field(
    paragraph: etree._Element,
    exempt: Iterable[str] = EXEMPT_FIELDS,
) -> bool:
    """True bila paragraf memuat field yang membuat layout dikecualikan."""

    names = {name.upper() for name in exempt}
    return any(
        field_name(instruction) in names for instruction in iter_field_instructions(paragraph)
    )


def _ancestor(element: etree._Element, tag: str) -> bool:
    parent = element.getparent()
    while parent is not None:
        if parent.tag == tag:
            return True
        if parent.tag == W_P:
            return False
        parent = parent.getparent()
    return False


def _paragraph_of(element: etree._Element) -> etree._Element | None:
    parent = element.getparent()
    while parent is not None:
        if parent.tag == W_P:
            return parent
        parent = parent.getparent()
    return None


def has_deleted_ancestor(element: etree._Element) -> bool:
    """True bila elemen berada di dalam ``w:del``/``w:moveFrom``."""

    parent = element.getparent()
    while parent is not None:
        if parent.tag in TRACKED_DELETE_TAGS:
            return True
        parent = parent.getparent()
    return False


def iter_field_runs(paragraph: etree._Element) -> Iterator[etree._Element]:
    """Iterasi run yang menjadi bagian field (begin sampai end).

    Run hasil field ikut dianggap run field. Ini penting agar
    ``w:fldSimple`` dan field kompleks tidak kehilangan bold langsung.
    """

    depth = 0
    simple_runs: set[int] = set()
    for run in iter_paragraph_runs(paragraph):
        if _ancestor(run, W_FLDSIMPLE):
            simple_runs.add(id(run))

    for run in iter_paragraph_runs(paragraph):
        markers = list(run.iter(W_FLDCHAR))
        instr = run.find(f".//{W_INSTRTEXT}")
        if depth > 0 or id(run) in simple_runs or markers or instr is not None:
            yield run
        for marker in markers:
            field_type = marker.get(W_FLDCHARTYPE)
            if field_type == "begin":
                depth += 1
            elif field_type == "end" and depth > 0:
                depth -= 1


def is_field_run(
    run: etree._Element,
    paragraph: etree._Element | None = None,
) -> bool:
    """True bila ``run`` adalah bagian field pada paragrafnya."""

    if paragraph is None:
        paragraph = _paragraph_of(run)
    if paragraph is None:
        return bool(
            run.find(f".//{W_FLDCHAR}") is not None
            or run.find(f".//{W_INSTRTEXT}") is not None
            or _ancestor(run, W_FLDSIMPLE)
        )
    return any(candidate is run for candidate in iter_field_runs(paragraph))


# ---------------------------------------------------------------------------
# Bold
# ---------------------------------------------------------------------------


def is_bold_run(run: etree._Element) -> bool:
    """True bila run memiliki ``w:b``/``w:bCs`` yang efektif aktif."""

    properties = run.find(W_RPR)
    if properties is None:
        return False
    for tag in (W_B, W_BCS):
        element = properties.find(tag)
        if element is not None and is_on(element):
            return True
    return False


def has_bold_field(paragraph: etree._Element) -> bool:
    """True bila ada run field yang masih bold (bold exempt)."""

    return any(is_bold_run(run) for run in iter_field_runs(paragraph))


def strip_bold_from_run(run: etree._Element) -> int:
    """Hapus bold langsung dari satu run."""

    properties = run.find(W_RPR)
    if properties is None:
        return 0
    return runs.strip_bold_from_rpr(properties)


def strip_paragraph_bold(
    paragraph: etree._Element,
    *,
    preserve_fields: bool = True,
) -> int:
    """Hapus bold langsung dari run paragraf, kecuali run field.

    Pengecualian field diperiksa **sebelum** penghapusan, bukan sesudahnya.
    """

    removed = 0
    field_elements = tuple(iter_field_runs(paragraph)) if preserve_fields else ()
    field_runs = {id(run) for run in field_elements}
    for run in iter_paragraph_runs(paragraph):
        if has_deleted_ancestor(run):
            continue
        if id(run) in field_runs:
            continue
        removed += strip_bold_from_run(run)
    return removed


# ---------------------------------------------------------------------------
# Pengecualian gaya/field
# ---------------------------------------------------------------------------


def is_exempt_style(style_id: str | None) -> bool:
    """True untuk style yang tidak boleh dinormalisasi."""

    normalized = normalize_style_id(style_id)
    if not normalized:
        return False
    if normalized in CODE_STYLES or normalized in CAPTION_STYLES:
        return True
    if normalized in FIGURE_STYLES or normalized in CUSTOM_HEADING_STYLES:
        return True
    if normalized == TITLE_STYLE or normalized.startswith(COVER_PREFIX):
        return True
    if HEADING_STYLE_RE.fullmatch(normalized) is not None:
        return True
    return TOC_STYLE_RE.fullmatch(normalized) is not None


def is_exempt(paragraph: etree._Element) -> bool:
    """True bila paragraf dikecualikan dari normalisasi layout."""

    return is_exempt_style(paragraphs.paragraph_style_id(paragraph)) or has_exempt_field(paragraph)


def _cover_bold_to_strip(style_id: str | None) -> bool:
    normalized = normalize_style_id(style_id)
    return normalized.startswith(COVER_PREFIX) and normalized != COVER_TITLE_STYLE


def is_chapter_heading(value: str | etree._Element | None) -> bool:
    """True untuk Heading1 atau ``ChapterTitle``.

    Menerima style ID maupun elemen paragraf agar helper aman dipakai stage.
    """

    style_id = paragraphs.paragraph_style_id(value) if isinstance(value, etree._Element) else value
    return normalize_style_id(style_id) in CHAPTER_HEADING_STYLES


# ---------------------------------------------------------------------------
# Traversal body dan tracked changes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BodyUnit:
    """Satu unit visual level body.

    ``host`` adalah child langsung ``w:body``. Untuk paragraf yang dibungkus
    ``w:ins``/``w:del``, ``element`` adalah paragraf di dalamnya dan ``host``
    adalah pembungkus tracked change tersebut.
    """

    element: etree._Element
    host: etree._Element
    deleted: bool = False


def iter_body_units(body: etree._Element) -> Iterator[BodyUnit]:
    """Iterasi unit body dengan ``w:ins``/``w:del`` sebagai transparan.

    Paragraf di dalam ``w:del``/``w:moveFrom`` ditandai ``deleted=True`` agar
    stage blank line tidak menghitungnya sebagai isi dan tidak menyisipkan
    paragraf ke dalam konten yang dihapus.
    """

    for child in body:
        tag = child.tag
        if not isinstance(tag, str):
            continue
        if tag in TRACKED_TAGS:
            deleted = tag in TRACKED_DELETE_TAGS
            inner = [
                grandchild
                for grandchild in child
                if isinstance(grandchild.tag, str) and grandchild.tag in BODY_BLOCK_TAGS
            ]
            if inner:
                for element in inner:
                    yield BodyUnit(element=element, host=child, deleted=deleted)
            else:
                yield BodyUnit(element=child, host=child, deleted=deleted)
            continue
        yield BodyUnit(element=child, host=child, deleted=False)


# ---------------------------------------------------------------------------
# Part IO
# ---------------------------------------------------------------------------


def document_root(package: object) -> etree._Element:
    """Ambil dan parse ``word/document.xml`` dari package hidup."""

    has_part = getattr(package, "has_part", None)
    xml = getattr(package, "xml", None)
    if not callable(has_part) or not callable(xml):
        raise LayoutError("package DOCX tidak memiliki has_part/xml")
    if not has_part(DOCUMENT_PART):
        raise LayoutError(
            f"part {DOCUMENT_PART} tidak ditemukan",
            path=DOCUMENT_PART,
        )
    try:
        return xml(DOCUMENT_PART)
    except DocxError:
        raise
    except Exception as exc:  # pragma: no cover - pengaman kontrak
        raise LayoutError(
            f"{DOCUMENT_PART} tidak dapat dibaca: {exc}",
            path=DOCUMENT_PART,
        ) from exc


def set_document_root(package: object, root: etree._Element) -> None:
    """Tandai ``word/document.xml`` berubah pada package hidup."""

    setter = getattr(package, "set_xml", None)
    if not callable(setter):
        raise LayoutError("package DOCX tidak memiliki set_xml")
    setter(DOCUMENT_PART, root)


def read_part(package: object, name: str) -> bytes:
    """Baca payload part melalui ``DocumentPackage.part``."""

    reader = getattr(package, "part", None)
    if not callable(reader):
        raise LayoutError("package DOCX tidak memiliki part")
    try:
        return reader(name)
    except DocxError:
        raise
    except Exception as exc:  # pragma: no cover - pengaman kontrak
        raise LayoutError(
            f"part {name} tidak dapat dibaca: {exc}",
            path=name,
        ) from exc


def write_part(package: object, name: str, data: bytes) -> None:
    """Tulis payload part melalui ``DocumentPackage.set_part``."""

    writer = getattr(package, "set_part", None)
    if not callable(writer):
        raise LayoutError("package DOCX tidak memiliki set_part")
    try:
        writer(name, data)
    except DocxError:
        raise
    except Exception as exc:  # pragma: no cover - pengaman kontrak
        raise LayoutError(
            f"part {name} tidak dapat ditulis: {exc}",
            path=name,
        ) from exc


# ---------------------------------------------------------------------------
# Normalisasi layout
# ---------------------------------------------------------------------------


def preserve_tabs(
    paragraph: etree._Element,
    old_ppr: etree._Element | None,
) -> None:
    """Pulihkan tab stop kustom dari ``old_ppr`` setelah pPr dimutasi.

    Normalisasi tidak pernah menghapus tab stop, tetapi helper ini membuat
    jaminan tersebut eksplisit dan aman bila pemanggil mengganti ``w:pPr``.
    """

    if old_ppr is None:
        return
    old_tabs = old_ppr.find(qn("w:tabs"))
    if old_tabs is None:
        return
    ppr = ensure_ppr(paragraph)
    current = ppr.find(qn("w:tabs"))
    if current is not None and etree.tostring(current) == etree.tostring(old_tabs):
        return
    if current is not None:
        ppr.remove(current)
    tabs = copy.deepcopy(old_tabs)
    insert_ordered(ppr, tabs, PPR_ORDER)


def normalize_paragraph(
    paragraph: etree._Element,
    spec: LayoutSpec | None = None,
) -> bool:
    """Terapkan spacing/alignment dari ``spec``; kembalikan True bila berubah."""

    spec = spec or LayoutSpec()
    old_ppr = paragraph.find(W_PPR)
    before = etree.tostring(old_ppr) if old_ppr is not None else None

    ppr = ensure_ppr(paragraph)
    spacing = get_or_add(ppr, "w:spacing", PPR_ORDER)
    line = spec.effective_line_spacing_twips
    spacing.set(qn("w:before"), str(spec.space_before))
    spacing.set(qn("w:after"), str(spec.space_after))
    spacing.set(qn("w:line"), str(line))
    spacing.set(qn("w:lineRule"), "auto")
    for attribute in (
        qn("w:beforeLines"),
        qn("w:afterLines"),
        qn("w:beforeAutospacing"),
        qn("w:afterAutospacing"),
    ):
        spacing.attrib.pop(attribute, None)

    justification = get_or_add(ppr, "w:jc", PPR_ORDER)
    current = (justification.get(W_VAL) or "").strip().lower()
    if not (spec.preserve_right_alignment and current == "right"):
        justification.set(W_VAL, spec.alignment)

    preserve_tabs(paragraph, old_ppr)
    after = etree.tostring(ppr)
    return before != after


def normalize_layout(
    package: object,
    *,
    spec: LayoutSpec | None = None,
) -> LayoutReport:
    """Normalisasi semua paragraf body/tabel pada package hidup."""

    spec = spec or LayoutSpec()
    root = document_root(package)
    before_hash = sha256_c14n(root)

    checked = 0
    normalized = 0
    unchanged = 0
    skipped = 0
    fields_preserved = 0
    bold_paragraphs = 0
    bold_runs_removed = 0

    for paragraph in iter_paragraphs(root):
        checked += 1
        if has_deleted_ancestor(paragraph):
            skipped += 1
            continue
        style_id = paragraphs.paragraph_style_id(paragraph)

        if is_exempt_style(style_id):
            if _cover_bold_to_strip(style_id) and spec.strip_bold:
                removed = strip_paragraph_bold(paragraph)
                if removed:
                    bold_paragraphs += 1
                    bold_runs_removed += removed
            skipped += 1
            continue

        # PENTING: cek field exempt sebelum bold dihapus. Run field
        # TOC/PAGEREF/SEQ/PAGE tidak boleh kehilangan bold, tetapi run body
        # lain pada paragraf yang sama tetap boleh dibersihkan.
        exempt_field = has_exempt_field(paragraph, spec.exempt_fields)
        if exempt_field:
            fields_preserved += 1

        if spec.strip_bold:
            removed = strip_paragraph_bold(paragraph)
            if removed:
                bold_paragraphs += 1
                bold_runs_removed += removed

        if exempt_field:
            skipped += 1
            continue

        if normalize_paragraph(paragraph, spec):
            normalized += 1
        else:
            unchanged += 1

    changed = sha256_c14n(root) != before_hash
    if changed:
        set_document_root(package, root)

    return LayoutReport(
        checked=checked,
        normalized=normalized,
        skipped=skipped,
        fields_preserved=fields_preserved,
        unchanged=unchanged,
        bold_paragraphs=bold_paragraphs,
        bold_runs_removed=bold_runs_removed,
    )


# ---------------------------------------------------------------------------
# Helper tambahan untuk stage lain
# ---------------------------------------------------------------------------


def content_width(
    body: etree._Element,
    *,
    fallback: int = DEFAULT_CONTENT_WIDTH_TWIPS,
) -> int:
    """Lebar area teks dari ``sectPr`` terakhir, fallback 9072 twip."""

    section = body.find(W_SECTPR)
    if section is None:
        sections = body.findall(f".//{W_SECTPR}")
        section = sections[-1] if sections else None
    if section is None:
        return fallback

    page_size = section.find(qn("w:pgSz"))
    page_margin = section.find(qn("w:pgMar"))
    if page_size is None or page_margin is None:
        return fallback

    width = paragraphs.int_attribute(page_size, qn("w:w"))
    left = paragraphs.int_attribute(page_margin, qn("w:left"))
    right = paragraphs.int_attribute(page_margin, qn("w:right"))
    if width is None or left is None or right is None:
        return fallback
    gutter = paragraphs.int_attribute(page_margin, qn("w:gutter")) or 0
    result = width - left - right - gutter
    return result if result > 0 else fallback
