"""Model dan mutator section DOCX.

Modul ini adalah satu-satunya pintu untuk membaca dan mengubah section,
ukuran halaman, margin, format nomor halaman, serta part header/footer.
Stage tidak memakai ``zipfile`` atau regex terhadap ``document.xml``;
semua perubahan melewati helper di sini. Penomoran heading body berada di
:mod:`docgen.docx.heading_numbering`, bukan di modul ini.

Section pada OOXML diakhiri oleh ``w:sectPr``. Section terakhir memakai
``w:sectPr`` di akhir ``w:body``; section lain memakai ``w:sectPr`` di dalam
``w:pPr`` paragraf pemutus. Model :class:`Section` memakai indeks child
langsung ``w:body`` agar stabil untuk pembacaan dan penyisipan.
"""

import copy
import posixpath
import re
from dataclasses import dataclass
from typing import Literal

from lxml import etree

from ..errors import DocgenError
from . import paragraphs
from .names import R_ID, W_P, W_PPR, W_SECTPR, W, local_name
from .package import (
    DOCUMENT_PART,
    REL_TYPE_FOOTER,
    REL_TYPE_HEADER,
    DocumentPackage,
    Relationship,
)
from .xml import SECTPR_ORDER, get_or_add, insert_ordered, serialize_xml

SectionKind = Literal["cover", "front_matter", "body", "back_matter"]
SectionType = Literal["nextPage", "continuous", "evenPage", "oddPage"]
PageNumberFormat = Literal["decimal", "lowerRoman", "upperRoman", "lowerLetter", "upperLetter"]
HeaderFooterKind = Literal["header", "footer"]
HeaderFooterReferenceType = Literal["default", "first", "even"]

HEADER_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
FOOTER_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"

_PAGE_NUMBER_FORMATS = frozenset(
    {"decimal", "lowerRoman", "upperRoman", "lowerLetter", "upperLetter"}
)
_SECTION_TYPES = frozenset({"nextPage", "continuous", "evenPage", "oddPage"})
_HEADER_FOOTER_TYPES = frozenset({"default", "first", "even"})

_CHAPTER_RE = re.compile(
    r"^(?:BAB\s+(?:[IVXLCDM]+|\d+)(?=\b|\s)|\d+\.(?=\s|$))",
    re.IGNORECASE,
)
_BACK_MATTER_RE = re.compile(
    r"^(?:DAFTAR\s+PUSTAKA|DAFTAR\s+RUJUKAN|LAMPIRAN|BIBLIOGRAFI)\b",
    re.IGNORECASE,
)
_PAGE_BREAK_TYPES = frozenset({"page"})


class SectionError(DocgenError):
    """Struktur section tidak valid atau format nomor halaman tidak dikenal."""

    default_code = "SECTION"


class HeaderFooterError(SectionError):
    """Part atau relationship header/footer tidak valid."""

    default_code = "HEADER-FOOTER"


@dataclass(frozen=True)
class Section:
    """Satu section logis di dalam ``w:body``.

    ``start`` dan ``end`` adalah indeks child langsung ``w:body`` (setengah
    terbuka). ``end`` mencakup paragraf pemutus yang membawa ``sect_pr``.
    """

    index: int
    start: int
    end: int
    sect_pr: etree._Element
    kind: SectionKind


@dataclass(frozen=True)
class HeaderFooterRefs:
    """Relationship ID header/footer efektif untuk satu section."""

    header: str | None
    footer: str | None
    first_page_header: str | None
    first_page_footer: str | None


# ---------------------------------------------------------------------------
# Pembacaan section
# ---------------------------------------------------------------------------


def _body(package: DocumentPackage) -> etree._Element:
    try:
        return paragraphs.document_body(package)
    except paragraphs.ParagraphError as exc:
        raise SectionError(str(exc)) from exc


def _paragraph_sect_pr(paragraph: etree._Element) -> etree._Element | None:
    if paragraph.tag != W_P:
        return None
    ppr = paragraph.find(W_PPR)
    if ppr is None:
        return None
    matches = ppr.findall(W_SECTPR)
    if len(matches) > 1:
        raise SectionError("Satu paragraf memiliki lebih dari satu w:sectPr")
    return matches[0] if matches else None


def _text(paragraph: etree._Element) -> str:
    return " ".join(paragraphs.paragraph_text(paragraph).split())


def _has_visible_content(child: etree._Element) -> bool:
    if child.tag != W_P:
        return True
    if _text(child):
        return True
    if child.find(".//" + W + "drawing") is not None:
        return True
    if child.find(".//" + W + "pict") is not None:
        return True
    if child.find(".//" + W + "object") is not None:
        return True
    if child.find(".//" + W + "txbxContent") is not None:
        return True
    if child.find(".//" + W + "instrText") is not None:
        return True
    for br in child.iter(W + "br"):
        if (br.get(W + "type") or "").casefold() in _PAGE_BREAK_TYPES:
            return True
    return False


def _section_kind(
    children: list[etree._Element],
    index: int,
    start: int,
    end: int,
    body_start: int | None,
    back_start: int | None,
) -> SectionKind:
    section_paragraphs = [
        child for child in children[start:end] if isinstance(child.tag, str) and child.tag == W_P
    ]
    styles = {
        style
        for paragraph in section_paragraphs
        if (style := paragraphs.paragraph_style_id(paragraph)) is not None
    }
    has_cover_style = any(style.casefold().startswith("cover") for style in styles)
    if index == 0 and has_cover_style:
        return "cover"
    if body_start is not None and start >= body_start:
        if back_start is not None and start >= back_start:
            return "back_matter"
        return "body"
    if not section_paragraphs:
        return "cover" if index == 0 else "front_matter"
    return "front_matter"


def iter_sections(package: DocumentPackage) -> tuple[Section, ...]:
    """Kembalikan seluruh section di ``word/document.xml``."""

    body = _body(package)
    children = paragraphs.body_children(body)
    final_sect = body.find(W_SECTPR)
    if final_sect is None:
        raise SectionError("w:sectPr terakhir tidak ditemukan di w:body")

    boundaries: list[tuple[int, etree._Element, int]] = []
    start = 0
    for index, child in enumerate(children):
        sect = _paragraph_sect_pr(child) if child.tag == W_P else None
        if sect is not None:
            boundaries.append((start, sect, index + 1))
            start = index + 1
    boundaries.append((start, final_sect, len(children)))

    body_start: int | None = None
    back_start: int | None = None
    for index, child in enumerate(children):
        if child.tag != W_P:
            continue
        if body_start is None and paragraphs.heading_level(child) == 1:
            text = _text(child)
            if _CHAPTER_RE.match(text):
                body_start = index
        if body_start is not None and index >= body_start and paragraphs.heading_level(child) == 1:
            text = _text(child)
            if _BACK_MATTER_RE.match(text):
                back_start = index
                break

    sections: list[Section] = []
    for section_index, (section_start, sect_pr, section_end) in enumerate(boundaries):
        sections.append(
            Section(
                index=section_index,
                start=section_start,
                end=section_end,
                sect_pr=sect_pr,
                kind=_section_kind(
                    children,
                    section_index,
                    section_start,
                    section_end,
                    body_start,
                    back_start,
                ),
            )
        )
    return tuple(sections)


def section_at(package: DocumentPackage, paragraph_index: int) -> Section:
    """Section yang memuat child ``w:body`` pada ``paragraph_index``."""

    if not isinstance(paragraph_index, int) or paragraph_index < 0:
        raise SectionError("Indeks paragraf section harus bilangan bulat >= 0")
    children = paragraphs.body_children(_body(package))
    if paragraph_index >= len(children):
        raise SectionError(
            f"Indeks paragraf {paragraph_index} di luar batas body ({len(children)} child)"
        )
    for section in iter_sections(package):
        if section.start <= paragraph_index < section.end:
            return section
    raise SectionError(f"Section untuk paragraf {paragraph_index} tidak ditemukan")


# ---------------------------------------------------------------------------
# Mutator w:sectPr
# ---------------------------------------------------------------------------


def _require_sect_pr(section: Section) -> etree._Element:
    sect_pr = section.sect_pr
    if not isinstance(sect_pr, etree._Element) or sect_pr.tag != W_SECTPR:
        raise SectionError(f"Section {section.index} tidak memiliki w:sectPr")
    return sect_pr


def _check_non_negative(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SectionError(f"{label} harus bilangan bulat >= 0")
    return value


def set_page_size(
    section: Section,
    *,
    width: int,
    height: int,
    orientation: Literal["portrait", "landscape"],
) -> None:
    """Set ``w:pgSz`` pada section."""

    _check_non_negative(width, "Lebar halaman")
    _check_non_negative(height, "Tinggi halaman")
    if width == 0 or height == 0:
        raise SectionError("Lebar dan tinggi halaman harus > 0")
    if orientation not in ("portrait", "landscape"):
        raise SectionError(f"Orientasi halaman tidak dikenal: {orientation!r}")
    pg_sz = get_or_add(_require_sect_pr(section), "w:pgSz", SECTPR_ORDER)
    pg_sz.set(W + "w", str(width))
    pg_sz.set(W + "h", str(height))
    pg_sz.set(W + "orient", orientation)


def set_margins(
    section: Section,
    *,
    top: int,
    right: int,
    bottom: int,
    left: int,
    header: int,
    footer: int,
    gutter: int,
) -> None:
    """Set ``w:pgMar`` pada section; seluruh nilai dalam twip."""

    values = {
        "top": _check_non_negative(top, "Margin atas"),
        "right": _check_non_negative(right, "Margin kanan"),
        "bottom": _check_non_negative(bottom, "Margin bawah"),
        "left": _check_non_negative(left, "Margin kiri"),
        "header": _check_non_negative(header, "Jarak header"),
        "footer": _check_non_negative(footer, "Jarak footer"),
        "gutter": _check_non_negative(gutter, "Gutter"),
    }
    pg_mar = get_or_add(_require_sect_pr(section), "w:pgMar", SECTPR_ORDER)
    for name, value in values.items():
        pg_mar.set(W + name, str(value))


def set_page_number_format(
    section: Section,
    *,
    fmt: PageNumberFormat,
    start: int | None = None,
) -> None:
    """Set ``w:pgNumType``; ``start=None`` menghapus atribut ``w:start``."""

    if fmt not in _PAGE_NUMBER_FORMATS:
        raise SectionError(f"Format nomor halaman tidak dikenal: {fmt!r}")
    if start is not None:
        _check_non_negative(start, "Nomor awal halaman")
        if start == 0:
            raise SectionError("Nomor awal halaman harus >= 1")
    pg_num = get_or_add(_require_sect_pr(section), "w:pgNumType", SECTPR_ORDER)
    pg_num.set(W + "fmt", fmt)
    if start is None:
        pg_num.attrib.pop(W + "start", None)
    else:
        pg_num.set(W + "start", str(start))


def set_title_page(section: Section, value: bool) -> None:
    """Aktifkan atau matikan header/footer halaman pertama berbeda."""

    sect_pr = _require_sect_pr(section)
    existing = sect_pr.find(W + "titlePg")
    if value:
        if existing is None:
            insert_ordered(sect_pr, etree.Element(W + "titlePg"), SECTPR_ORDER)
        return
    if existing is not None:
        sect_pr.remove(existing)


def set_section_type(
    section: Section,
    value: Literal["nextPage", "continuous", "evenPage", "oddPage"],
) -> None:
    """Set ``w:type`` pada section."""

    if value not in _SECTION_TYPES:
        raise SectionError(f"Tipe section tidak dikenal: {value!r}")
    sect_pr = _require_sect_pr(section)
    existing = sect_pr.find(W + "type")
    if existing is None:
        existing = etree.Element(W + "type")
        insert_ordered(sect_pr, existing, SECTPR_ORDER)
    existing.set(W + "val", value)


def _section_is_empty(
    children: list[etree._Element],
    section: Section,
) -> bool:
    break_index = section.end - 1
    if break_index < section.start:
        return True
    for index in range(section.start, break_index):
        child = children[index]
        if _has_visible_content(child):
            return False
    break_child = children[break_index]
    # Paragraf pemutus itu sendiri kosong; paragraf berisi page break adalah
    # konten yang sah dan tidak boleh dihapus.
    return not (break_child.tag == W_P and _has_visible_content(break_child))


def remove_empty_sections(package: DocumentPackage) -> int:
    """Hapus section kosong yang tidak membawa konten.

    Paragraf pemutus yang hanya berisi ``w:sectPr`` dihapus bila section
    sebelum pemutus tidak punya teks, gambar, tabel, field, atau page break.
    Section terakhir tidak dihapus. Mengembalikan jumlah section dihapus.
    """

    removed = 0
    while True:
        body = _body(package)
        children = paragraphs.body_children(body)
        sections = iter_sections(package)
        candidate: Section | None = None
        for section in sections[:-1]:
            if _section_is_empty(children, section):
                candidate = section
                break
        if candidate is None:
            return removed
        break_index = candidate.end - 1
        break_child = children[break_index]
        sect = _paragraph_sect_pr(break_child) if break_child.tag == W_P else None
        if sect is None or break_child.getparent() is not body:
            return removed
        body.remove(break_child)
        removed += 1


def _section_start_child(
    package: DocumentPackage, before: etree._Element
) -> tuple[etree._Element, int]:
    body = _body(package)
    if before.getparent() is not body:
        raise SectionError("Paragraf target section break bukan child langsung w:body")
    children = paragraphs.body_children(body)
    try:
        index = children.index(before)
    except ValueError as exc:
        raise SectionError("Paragraf target section break tidak ditemukan") from exc
    return body, index


def add_section_break(
    package: DocumentPackage,
    *,
    before: etree._Element,
    kind: Literal["nextPage", "continuous"],
) -> Section:
    """Sisipkan section break tepat sebelum ``before``.

    Paragraf pemutus membawa salinan ``w:sectPr`` section yang berakhir.
    Operasi idempoten: bila ``before`` sudah menjadi awal section, section
    yang ada dikembalikan tanpa menambah paragraf baru.
    """

    if kind not in ("nextPage", "continuous"):
        raise SectionError(f"Tipe section break tidak dikenal: {kind!r}")
    body, index = _section_start_child(package, before)
    current = section_at(package, index)
    if current.start == index:
        return current

    sect_pr = copy.deepcopy(current.sect_pr)
    for tag in ("headerReference", "footerReference"):
        for reference in list(sect_pr.findall(W + tag)):
            sect_pr.remove(reference)
    for tag in ("pgNumType", "titlePg"):
        for element in list(sect_pr.findall(W + tag)):
            sect_pr.remove(element)
    type_element = sect_pr.find(W + "type")
    if type_element is None:
        type_element = etree.Element(W + "type")
        insert_ordered(sect_pr, type_element, SECTPR_ORDER)
    type_element.set(W + "val", kind)

    paragraph = etree.Element(W_P)
    ppr = etree.SubElement(paragraph, W_PPR)
    ppr.append(sect_pr)
    body.insert(index, paragraph)

    new_index = index + 1
    for section in iter_sections(package):
        if section.start <= new_index < section.end:
            return section
    raise SectionError("Section baru tidak ditemukan setelah penyisipan break")


# ---------------------------------------------------------------------------
# Header/footer reference dan part
# ---------------------------------------------------------------------------


def section_header_footer(section: Section) -> HeaderFooterRefs:
    """Baca reference header/footer efektif dari ``w:sectPr``."""

    sect_pr = _require_sect_pr(section)
    values: dict[str, str | None] = {
        "header": None,
        "footer": None,
        "first_header": None,
        "first_footer": None,
    }
    for reference in sect_pr:
        if not isinstance(reference.tag, str):
            continue
        name = local_name(reference.tag)
        if name not in ("headerReference", "footerReference"):
            continue
        ref_type = reference.get(W + "type") or "default"
        rel_id = reference.get(R_ID)
        if ref_type not in _HEADER_FOOTER_TYPES or not rel_id:
            continue
        prefix = "header" if name == "headerReference" else "footer"
        key = f"first_{prefix}" if ref_type == "first" else prefix
        if ref_type == "default" or ref_type == "first":
            values[key] = rel_id
    return HeaderFooterRefs(
        header=values["header"],
        footer=values["footer"],
        first_page_header=values["first_header"],
        first_page_footer=values["first_footer"],
    )


def set_header_footer_reference(
    section: Section,
    *,
    kind: HeaderFooterKind,
    reference_type: HeaderFooterReferenceType,
    rel_id: str | None,
) -> None:
    """Ganti satu reference header/footer pada section.

    ``rel_id=None`` menghapus reference dengan tipe yang sama. Reference
    lain tidak disentuh sehingga gambar/header khusus pengguna tetap aman.
    """

    if kind not in ("header", "footer"):
        raise SectionError(f"Jenis header/footer tidak dikenal: {kind!r}")
    if reference_type not in _HEADER_FOOTER_TYPES:
        raise SectionError(f"Tipe reference header/footer tidak dikenal: {reference_type!r}")
    if rel_id is not None and not isinstance(rel_id, str):
        raise SectionError("Relationship ID header/footer harus string")

    sect_pr = _require_sect_pr(section)
    tag = W + ("headerReference" if kind == "header" else "footerReference")
    for reference in list(sect_pr.findall(tag)):
        if (reference.get(W + "type") or "default") == reference_type:
            sect_pr.remove(reference)
    if rel_id is None:
        return

    reference = etree.Element(tag)
    reference.set(W + "type", reference_type)
    reference.set(R_ID, rel_id)

    if kind == "header":
        header_positions = [
            index
            for index, child in enumerate(sect_pr)
            if isinstance(child.tag, str) and local_name(child.tag) == "headerReference"
        ]
        insert_at = (header_positions[-1] + 1) if header_positions else 0
        sect_pr.insert(insert_at, reference)
        return

    footer_positions = [
        index
        for index, child in enumerate(sect_pr)
        if isinstance(child.tag, str)
        and local_name(child.tag) in ("headerReference", "footerReference")
    ]
    insert_at = (footer_positions[-1] + 1) if footer_positions else 0
    sect_pr.insert(insert_at, reference)


def clear_header_footer_references(section: Section) -> None:
    """Hapus semua reference header/footer pada section."""

    sect_pr = _require_sect_pr(section)
    for tag in ("headerReference", "footerReference"):
        for reference in list(sect_pr.findall(W + tag)):
            sect_pr.remove(reference)


def _next_relationship_id(package: object) -> str:
    relationships = package.relationships(DOCUMENT_PART)  # type: ignore[attr-defined]
    used = {rel.rel_id for rel in relationships}
    numbers = [
        int(match.group(1)) for rel_id in used if (match := re.fullmatch(r"rId(\d+)", rel_id))
    ]
    number = max(numbers, default=0) + 1
    while f"rId{number}" in used:
        number += 1
    return f"rId{number}"


def _next_part_name(package: object, kind: HeaderFooterKind) -> str:
    names = package.part_names()  # type: ignore[attr-defined]
    pattern = re.compile(rf"word/{kind}(\d+)\.xml$")
    numbers = [int(match.group(1)) for name in names if (match := pattern.fullmatch(name))]
    number = max(numbers, default=0) + 1
    while f"word/{kind}{number}.xml" in names:
        number += 1
    return f"word/{kind}{number}.xml"


def create_header_footer_part(
    package: object,
    *,
    kind: HeaderFooterKind,
    content: etree._Element | bytes,
) -> str:
    """Buat part header/footer baru, content type, dan relationship.

    Mengembalikan relationship ID yang siap ditulis ke ``w:sectPr``.
    """

    if kind not in ("header", "footer"):
        raise HeaderFooterError(f"Jenis part tidak dikenal: {kind!r}")
    if isinstance(content, etree._Element):
        payload = serialize_xml(content)
        root = content
    else:
        payload = bytes(content)
        root = None
    expected = W + ("hdr" if kind == "header" else "ftr")
    if root is not None and root.tag != expected:
        raise HeaderFooterError(f"Root part {kind} harus {expected}, bukan {root.tag}")
    part_name = _next_part_name(package, kind)
    content_type = HEADER_CONTENT_TYPE if kind == "header" else FOOTER_CONTENT_TYPE
    package.set_part(part_name, payload, content_type=content_type)  # type: ignore[attr-defined]
    rel_id = _next_relationship_id(package)
    package.add_relationship(  # type: ignore[attr-defined]
        DOCUMENT_PART,
        Relationship(
            rel_id=rel_id,
            rel_type=REL_TYPE_HEADER if kind == "header" else REL_TYPE_FOOTER,
            target=posixpath.basename(part_name),
        ),
    )
    return rel_id


def header_footer_part(
    package: object,
    rel_id: str,
) -> tuple[str, etree._Element]:
    """Kembalikan ``(nama_part, root)`` untuk relationship header/footer."""

    for relationship in package.relationships(DOCUMENT_PART):  # type: ignore[attr-defined]
        if relationship.rel_id != rel_id:
            continue
        if relationship.rel_type not in (REL_TYPE_HEADER, REL_TYPE_FOOTER):
            raise HeaderFooterError(
                f"Relationship {rel_id} bukan header/footer: {relationship.rel_type}"
            )
        target = relationship.target
        if target.startswith("/"):
            part_name = target.lstrip("/")
        else:
            part_name = posixpath.normpath(posixpath.join(posixpath.dirname(DOCUMENT_PART), target))
        if not package.has_part(part_name):  # type: ignore[attr-defined]
            raise HeaderFooterError(f"Part header/footer tidak ditemukan: {part_name}")
        return part_name, package.xml(part_name)  # type: ignore[attr-defined]
    raise HeaderFooterError(f"Relationship header/footer tidak ditemukan: {rel_id}")


def set_part_xml(package: object, part_name: str, root: etree._Element) -> None:
    """Ganti payload root part yang sudah ada."""

    if not package.has_part(part_name):  # type: ignore[attr-defined]
        raise HeaderFooterError(f"Part tidak ditemukan: {part_name}")
    package.set_xml(part_name, root)  # type: ignore[attr-defined]


def _referenced_header_footer_parts(package: DocumentPackage) -> set[str]:
    referenced: set[str] = set()
    relationships = {
        relationship.rel_id: relationship for relationship in package.relationships(DOCUMENT_PART)
    }
    for section in iter_sections(package):
        for reference in section.sect_pr:
            if not isinstance(reference.tag, str):
                continue
            name = local_name(reference.tag)
            if name not in ("headerReference", "footerReference"):
                continue
            rel_id = reference.get(R_ID)
            if not rel_id or rel_id not in relationships:
                continue
            relationship = relationships[rel_id]
            target = relationship.target
            if target.startswith("/"):
                part_name = target.lstrip("/")
            else:
                part_name = posixpath.normpath(
                    posixpath.join(posixpath.dirname(DOCUMENT_PART), target)
                )
            if package.has_part(part_name):
                referenced.add(part_name)
    return referenced


def remove_unused_header_footer_parts(package: DocumentPackage) -> int:
    """Hapus part header/footer yang tidak dirujuk section mana pun."""

    referenced = _referenced_header_footer_parts(package)
    removed = 0
    for name in list(package.part_names()):
        if not re.fullmatch(r"word/(?:header|footer)\d+\.xml", name):
            continue
        if name in referenced:
            continue
        package.remove_part(name)
        removed += 1
    return removed


__all__ = [
    "FOOTER_CONTENT_TYPE",
    "HEADER_CONTENT_TYPE",
    "HeaderFooterError",
    "HeaderFooterRefs",
    "Section",
    "SectionError",
    "add_section_break",
    "clear_header_footer_references",
    "create_header_footer_part",
    "header_footer_part",
    "iter_sections",
    "remove_empty_sections",
    "remove_unused_header_footer_parts",
    "section_at",
    "section_header_footer",
    "set_header_footer_reference",
    "set_margins",
    "set_page_number_format",
    "set_page_size",
    "set_part_xml",
    "set_section_type",
    "set_title_page",
]
