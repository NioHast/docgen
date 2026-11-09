"""Model dan mutator ``w:sectPr`` untuk DOCX.

Modul ini adalah satu-satunya pintu untuk membaca dan mengubah section,
ukuran halaman, margin, format nomor halaman, serta part header/footer.
Stage tidak memakai ``zipfile`` atau regex terhadap ``document.xml``;
semua perubahan melewati helper di sini.

Section pada OOXML diakhiri oleh ``w:sectPr``. Section terakhir memakai
``w:sectPr`` di akhir ``w:body``; section lain memakai ``w:sectPr`` di dalam
``w:pPr`` paragraf pemutus. Model :class:`Section` memakai indeks child
langsung ``w:body`` agar stabil untuk pembacaan dan penyisipan.
"""

from __future__ import annotations

import copy
import posixpath
import re
from dataclasses import dataclass
from typing import Literal

from lxml import etree

from ..errors import DocgenError
from .names import (
    R_ID,
    W,
    W_BODY,
    W_BR,
    W_CR,
    W_DOCUMENT,
    W_P,
    W_PPR,
    W_R,
    W_SECTPR,
    W_T,
    W_TAB,
    local_name,
)
from .package import (
    DOCUMENT_PART,
    REL_TYPE_FOOTER,
    REL_TYPE_HEADER,
    Relationship,
)
from .xml import (
    SECTPR_ORDER,
    get_or_add,
    insert_ordered,
    iter_paragraphs,
    iter_runs,
    paragraph_text,
    qn,
    run_text,
    serialize_xml,
    sha256_c14n,
)

SectionKind = Literal["cover", "front_matter", "body", "back_matter"]
SectionType = Literal["nextPage", "continuous", "evenPage", "oddPage"]
PageNumberFormat = Literal[
    "decimal", "lowerRoman", "upperRoman", "lowerLetter", "upperLetter"
]
HeaderFooterKind = Literal["header", "footer"]
HeaderFooterReferenceType = Literal["default", "first", "even"]

HEADER_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
)
FOOTER_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
)

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


def _body(package: object) -> etree._Element:
    root = package.xml(DOCUMENT_PART)  # type: ignore[attr-defined]
    if not isinstance(root.tag, str) or root.tag != W_DOCUMENT:
        raise SectionError("Root document.xml bukan w:document")
    body = root.find(W_BODY)
    if body is None:
        raise SectionError("w:body tidak ditemukan")
    return body


def _body_children(body: etree._Element) -> list[etree._Element]:
    return [child for child in body if isinstance(child.tag, str)]


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


def _paragraph_style(paragraph: etree._Element) -> str | None:
    ppr = paragraph.find(W_PPR)
    if ppr is None:
        return None
    style = ppr.find(W + "pStyle")
    if style is None:
        return None
    return style.get(W + "val")


def _heading_level(paragraph: etree._Element) -> int | None:
    style = _paragraph_style(paragraph)
    if style is None:
        return None
    match = re.fullmatch(r"Heading([1-9])", style)
    return int(match.group(1)) if match else None


def _text(paragraph: etree._Element) -> str:
    return " ".join(paragraph_text(paragraph).split())


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
    paragraphs = [
        child
        for child in children[start:end]
        if isinstance(child.tag, str) and child.tag == W_P
    ]
    styles = {
        style
        for paragraph in paragraphs
        if (style := _paragraph_style(paragraph)) is not None
    }
    has_cover_style = any(
        style.casefold().startswith("cover") for style in styles
    )
    if index == 0 and has_cover_style:
        return "cover"
    if body_start is not None and start >= body_start:
        if back_start is not None and start >= back_start:
            return "back_matter"
        return "body"
    if not paragraphs:
        return "cover" if index == 0 else "front_matter"
    return "front_matter"


def iter_sections(package: object) -> tuple[Section, ...]:
    """Kembalikan seluruh section di ``word/document.xml``."""

    body = _body(package)
    children = _body_children(body)
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
        if body_start is None and _heading_level(child) == 1:
            text = _text(child)
            if _CHAPTER_RE.match(text):
                body_start = index
        if body_start is not None and index >= body_start and _heading_level(child) == 1:
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


def section_at(package: object, paragraph_index: int) -> Section:
    """Section yang memuat child ``w:body`` pada ``paragraph_index``."""

    if not isinstance(paragraph_index, int) or paragraph_index < 0:
        raise SectionError("Indeks paragraf section harus bilangan bulat >= 0")
    children = _body_children(_body(package))
    if paragraph_index >= len(children):
        raise SectionError(
            f"Indeks paragraf {paragraph_index} di luar batas body "
            f"({len(children)} child)"
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
    if break_child.tag == W_P and _has_visible_content(break_child):
        return False
    return True


def remove_empty_sections(package: object) -> int:
    """Hapus section kosong yang tidak membawa konten.

    Paragraf pemutus yang hanya berisi ``w:sectPr`` dihapus bila section
    sebelum pemutus tidak punya teks, gambar, tabel, field, atau page break.
    Section terakhir tidak dihapus. Mengembalikan jumlah section dihapus.
    """

    removed = 0
    while True:
        body = _body(package)
        children = _body_children(body)
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


def _section_start_child(package: object, before: etree._Element) -> tuple[etree._Element, int]:
    body = _body(package)
    if before.getparent() is not body:
        raise SectionError("Paragraf target section break bukan child langsung w:body")
    children = _body_children(body)
    try:
        index = children.index(before)
    except ValueError as exc:
        raise SectionError("Paragraf target section break tidak ditemukan") from exc
    return body, index


def add_section_break(
    package: object,
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
        if ref_type == "default":
            values[key] = rel_id
        elif ref_type == "first":
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
        raise SectionError(
            f"Tipe reference header/footer tidak dikenal: {reference_type!r}"
        )
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
            if isinstance(child.tag, str)
            and local_name(child.tag) == "headerReference"
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
        int(match.group(1))
        for rel_id in used
        if (match := re.fullmatch(r"rId(\d+)", rel_id))
    ]
    number = max(numbers, default=0) + 1
    while f"rId{number}" in used:
        number += 1
    return f"rId{number}"


def _next_part_name(package: object, kind: HeaderFooterKind) -> str:
    names = package.part_names()  # type: ignore[attr-defined]
    pattern = re.compile(rf"word/{kind}(\d+)\.xml$")
    numbers = [
        int(match.group(1))
        for name in names
        if (match := pattern.fullmatch(name))
    ]
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
        raise HeaderFooterError(
            f"Root part {kind} harus {expected}, bukan {root.tag}"
        )
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
                f"Relationship {rel_id} bukan header/footer: "
                f"{relationship.rel_type}"
            )
        target = relationship.target
        if target.startswith("/"):
            part_name = target.lstrip("/")
        else:
            part_name = posixpath.normpath(
                posixpath.join(posixpath.dirname(DOCUMENT_PART), target)
            )
        if not package.has_part(part_name):  # type: ignore[attr-defined]
            raise HeaderFooterError(
                f"Part header/footer tidak ditemukan: {part_name}"
            )
        return part_name, package.xml(part_name)  # type: ignore[attr-defined]
    raise HeaderFooterError(
        f"Relationship header/footer tidak ditemukan: {rel_id}"
    )


def set_part_xml(package: object, part_name: str, root: etree._Element) -> None:
    """Ganti payload root part yang sudah ada."""

    if not package.has_part(part_name):  # type: ignore[attr-defined]
        raise HeaderFooterError(f"Part tidak ditemukan: {part_name}")
    package.set_xml(part_name, root)  # type: ignore[attr-defined]


def _referenced_header_footer_parts(package: object) -> set[str]:
    referenced: set[str] = set()
    relationships = {
        relationship.rel_id: relationship
        for relationship in package.relationships(DOCUMENT_PART)  # type: ignore[attr-defined]
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
            if package.has_part(part_name):  # type: ignore[attr-defined]
                referenced.add(part_name)
    return referenced


def remove_unused_header_footer_parts(package: object) -> int:
    """Hapus part header/footer yang tidak dirujuk section mana pun."""

    referenced = _referenced_header_footer_parts(package)
    removed = 0
    for name in list(package.part_names()):  # type: ignore[attr-defined]
        if not re.fullmatch(r"word/(?:header|footer)\d+\.xml", name):
            continue
        if name in referenced:
            continue
        package.remove_part(name)  # type: ignore[attr-defined]
        removed += 1
    return removed


# ---------------------------------------------------------------------------
# Heading numbering
# ---------------------------------------------------------------------------


class HeadingError(DocgenError):
    """Heading tidak valid atau level tidak didukung."""

    default_code = "HEADING"


@dataclass(frozen=True)
class Heading:
    """Satu heading body beserta nomor hasil pembacaan."""

    level: int
    paragraph: etree._Element
    text: str
    number: str | None
    unnumbered: bool


@dataclass(frozen=True)
class NumberingSpec:
    """Konfigurasi penomoran heading dari ``structure.numbering``."""

    body: Literal["BAB_ROMAN", "ARABIC_DOTTED"]
    sub_dot: bool = True
    subsub_dot: bool = True


@dataclass(frozen=True)
class HeadingReport:
    """Ringkasan hasil :func:`apply_heading_numbering`."""

    changed: bool
    numbered: int
    unnumbered: int
    skipped_without_chapter: int
    headings: tuple[Heading, ...]


_FRONT_MATTER_NAMES = frozenset(
    {
        "KATA PENGANTAR",
        "PRAKATA",
        "UCAPAN TERIMA KASIH",
        "ABSTRAK",
        "ABSTRACT",
        "DAFTAR ISI",
        "DAFTAR TABEL",
        "DAFTAR GAMBAR",
        "DAFTAR LAMPIRAN",
        "DAFTAR SINGKATAN",
        "DAFTAR SIMBOL",
        "DAFTAR PUSTAKA",
        "DAFTAR RUJUKAN",
        "BIBLIOGRAFI",
        "MOTTO",
        "PERSEMBAHAN",
    }
)
_UNNUMBERED_PREFIXES = (
    "LEMBAR PENGESAHAN",
    "HALAMAN PENGESAHAN",
    "LEMBAR PERSETUJUAN",
    "HALAMAN PERSETUJUAN",
    "LEMBAR PERNYATAAN",
    "HALAMAN PERNYATAAN",
    "PERNYATAAN ",
    "LAMPIRAN",
)
_HEADING_NUMBER_RE = re.compile(
    r"^\s*(?P<number>BAB\s+(?:[IVXLCDM]+|\d+)|\d+(?:\.\d+)*\.?)",
    re.IGNORECASE,
)
_H1_NUMBER_RE = re.compile(
    r"^\s*(?:BAB\s+(?P<bab>[IVXLCDM]+|\d+)\s*|(?P<arabic>\d+\.)\s*)",
    re.IGNORECASE,
)
_H2_H3_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)+(?:\.)?\s*")
_EXPLICIT_UNNUMBERED_RE = re.compile(r"^\s*\{-\}\s*")


def _as_roman(number: int) -> str:
    if number <= 0 or number >= 4000:
        raise HeadingError(f"Nomor bab Romawi di luar rentang: {number}")
    values = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    result: list[str] = []
    remaining = number
    for value, numeral in values:
        while remaining >= value:
            result.append(numeral)
            remaining -= value
    return "".join(result)


def _normalized(text: str) -> str:
    return " ".join(text.split())


def heading_level(paragraph: etree._Element) -> int | None:
    """Level heading 1-9 dari ``w:pStyle``, atau ``None``."""

    return _heading_level(paragraph)


def _number_from_text(level: int, text: str) -> str | None:
    if level == 1:
        match = _H1_NUMBER_RE.match(text)
        if match is None:
            return None
        number = match.group("bab") or match.group("arabic")
        if number is None:
            return None
        if match.group("arabic") is not None:
            return number.strip()
        return f"BAB {' '.join(number.split())}"
    match = _HEADING_NUMBER_RE.match(text)
    if match is None:
        return None
    number = match.group("number")
    return " ".join(number.split())


def is_unnumbered(paragraph: etree._Element) -> bool:
    """True untuk heading yang tidak boleh mendapat nomor bab.

    Mendukung marker eksplisit ``{-}``, style yang mengandung
    ``unnumbered``, serta heading front/back matter yang lazim.
    """

    if _heading_level(paragraph) is None:
        return False
    style = _paragraph_style(paragraph) or ""
    if "unnumbered" in style.casefold():
        return True
    text = paragraph_text(paragraph).strip()
    if _EXPLICIT_UNNUMBERED_RE.match(text):
        return True
    normalized = _normalized(text).upper()
    if not normalized:
        return True
    if normalized in _FRONT_MATTER_NAMES:
        return True
    return any(
        normalized == prefix.rstrip() or normalized.startswith(prefix)
        for prefix in _UNNUMBERED_PREFIXES
    )


def heading_text(
    paragraph: etree._Element,
    *,
    include_number: bool = True,
) -> str:
    """Teks heading; ``include_number=False`` membuang prefix nomor lama."""

    full = paragraph_text(paragraph).strip()
    if include_number:
        return full
    level = _heading_level(paragraph) or 0
    if level == 1:
        stripped = _H1_NUMBER_RE.sub("", full)
    elif level in (2, 3):
        stripped = _H2_H3_NUMBER_RE.sub("", full)
    else:
        stripped = full
    return stripped.strip("\t \n")


def iter_headings(package: object) -> tuple[Heading, ...]:
    """Iterasi heading body dalam urutan dokumen."""

    root = package.xml(DOCUMENT_PART)  # type: ignore[attr-defined]
    headings: list[Heading] = []
    for paragraph in iter_paragraphs(root):
        level = _heading_level(paragraph)
        if level is None:
            continue
        text = paragraph_text(paragraph).strip()
        headings.append(
            Heading(
                level=level,
                paragraph=paragraph,
                text=text,
                number=_number_from_text(level, text),
                unnumbered=is_unnumbered(paragraph),
            )
        )
    return tuple(headings)


def _copy_run(run: etree._Element) -> etree._Element:
    return copy.deepcopy(run)


def _strip_prefix_from_runs(
    runs: list[etree._Element],
    prefix: str,
) -> list[etree._Element]:
    remaining = len(prefix)
    result: list[etree._Element] = []
    for run in runs:
        clone = _copy_run(run)
        for child in list(clone):
            if not isinstance(child.tag, str):
                continue
            if remaining <= 0:
                break
            if child.tag == W_T:
                text = child.text or ""
                take = min(len(text), remaining)
                child.text = text[take:]
                remaining -= take
                if not child.text:
                    clone.remove(child)
            elif child.tag in (W_TAB, W_BR, W_CR):
                clone.remove(child)
                remaining -= 1
        has_content = bool(run_text(clone)) or any(
            isinstance(child.tag, str)
            and child.tag
            in (W_TAB, W_BR, W_CR, W + "drawing", W + "pict", W + "object")
            for child in clone
        )
        if has_content:
            result.append(clone)
    # Buang tab/break kosong di awal.
    while result:
        text = run_text(result[0])
        has_break = (
            result[0].find(W_TAB) is not None
            or result[0].find(W_BR) is not None
            or result[0].find(W_CR) is not None
        )
        if text or not has_break:
            break
        result.pop(0)
    return result


def _uppercase_runs(runs: list[etree._Element]) -> None:
    for run in runs:
        for text in run.iter(W_T):
            if text.text:
                text.text = text.text.upper()


def _run_with_text(template: etree._Element | None, text: str) -> etree._Element:
    run = etree.Element(W_R)
    if template is not None:
        rpr = template.find(W + "rPr")
        if rpr is not None:
            run.append(copy.deepcopy(rpr))
    node = etree.SubElement(run, W_T)
    node.text = text
    return run


def _run_with_break(template: etree._Element | None, tag: str) -> etree._Element:
    run = etree.Element(W_R)
    if template is not None:
        rpr = template.find(W + "rPr")
        if rpr is not None:
            run.append(copy.deepcopy(rpr))
    etree.SubElement(run, tag)
    return run


def _replace_heading_content(
    paragraph: etree._Element,
    prefix_runs: list[etree._Element],
    title_runs: list[etree._Element],
) -> None:
    """Ganti run heading tanpa menghapus bookmark/proofErr."""

    ppr = paragraph.find(W_PPR)
    preserved = {
        "bookmarkStart",
        "bookmarkEnd",
        "proofErr",
        "permStart",
        "permEnd",
        "commentRangeStart",
        "commentRangeEnd",
    }
    for child in list(paragraph):
        if child is ppr:
            continue
        if local_name(child.tag) in preserved:
            continue
        paragraph.remove(child)
    insert_at = 1 if ppr is not None else 0
    while insert_at < len(paragraph) and local_name(paragraph[insert_at].tag) in (
        "bookmarkStart",
        "proofErr",
    ):
        insert_at += 1
    for run in prefix_runs + title_runs:
        paragraph.insert(insert_at, run)
        insert_at += 1


def _strip_leading_separators(
    runs: list[etree._Element],
) -> list[etree._Element]:
    """Buang tab/break/spasi di awal title runs setelah prefix nomor."""

    result: list[etree._Element] = []
    stripping = True
    for run in runs:
        clone = run
        if stripping:
            for child in list(clone):
                if not isinstance(child.tag, str):
                    continue
                if child.tag in (W_TAB, W_BR, W_CR):
                    clone.remove(child)
                    continue
                if child.tag == W_T:
                    text = child.text or ""
                    stripped = text.lstrip(" \t\r\n")
                    if stripped:
                        child.text = stripped
                        stripping = False
                    else:
                        clone.remove(child)
                    continue
                if child.tag == W + "rPr":
                    continue
                # Elemen lain (mis. drawing) adalah konten judul.
                stripping = False
                break
            if not run_text(clone) and clone.find(".//" + W_TAB) is None:
                has_visual = any(
                    isinstance(child.tag, str)
                    and child.tag
                    in (W_TAB, W_BR, W_CR, W + "drawing", W + "pict", W + "object")
                    for child in clone
                )
                if not has_visual:
                    continue
        result.append(clone)
    return result


def _heading_title_runs(
    paragraph: etree._Element,
    *,
    level: int,
    uppercase: bool,
) -> list[etree._Element]:
    text = paragraph_text(paragraph)
    if level == 1:
        match = _H1_NUMBER_RE.match(text)
    elif level in (2, 3):
        match = _H2_H3_NUMBER_RE.match(text)
    else:
        match = None
    prefix = match.group(0) if match is not None else ""
    # Prefix dari regex boleh memuat tab/line-break yang di DOCX tersimpan
    # sebagai elemen ``w:tab``/``w:br`` di luar run. Hanya karakter teks yang
    # boleh dihitung agar huruf pertama judul tidak ikut terpotong.
    prefix = prefix.rstrip(" \t\r\n")
    runs = list(iter_runs(paragraph))
    title_runs = _strip_prefix_from_runs(runs, prefix)
    title_runs = _strip_leading_separators(title_runs)
    if not any(run_text(run) for run in title_runs):
        fallback_text = heading_text(paragraph, include_number=False)
        if fallback_text:
            title_runs = [_run_with_text(runs[0] if runs else None, fallback_text)]
    if uppercase:
        _uppercase_runs(title_runs)
    return title_runs


def _numbered_runs(
    paragraph: etree._Element,
    number: str,
    *,
    level: int,
    kind: str,
) -> list[etree._Element]:
    runs = list(iter_runs(paragraph))
    template = runs[0] if runs else None
    prefix: list[etree._Element] = [_run_with_text(template, number)]
    if level == 1 and kind == "BAB_ROMAN":
        prefix.append(_run_with_break(template, W_BR))
    elif level == 1:
        prefix.append(_run_with_text(template, " "))
    else:
        prefix.append(_run_with_break(template, W_TAB))
    return prefix


def apply_heading_numbering(
    package: object,
    spec: NumberingSpec,
) -> HeadingReport:
    """Nomori H1/H2/H3 dan pertahankan format inline judul.

    H1 ``BAB_ROMAN`` menjadi ``BAB I`` + line break + judul kapital.
    H1 ``ARABIC_DOTTED`` menjadi ``1.`` + spasi + judul kapital. H2/H3
    memakai nomor bertingkat + tab. H4-H9 dan heading unnumbered tidak
    mengubah counter.
    """

    if spec.body not in ("BAB_ROMAN", "ARABIC_DOTTED"):
        raise HeadingError(f"Format penomoran body tidak dikenal: {spec.body!r}")

    before = sha256_c14n(package.xml(DOCUMENT_PART))  # type: ignore[attr-defined]
    chapter = 0
    sub = 0
    subsub = 0
    numbered = 0
    unnumbered = 0
    skipped = 0
    in_unnumbered_section = False

    for heading in iter_headings(package):
        paragraph = heading.paragraph
        level = heading.level
        if level not in (1, 2, 3):
            continue
        if heading.unnumbered:
            if level == 1:
                in_unnumbered_section = True
            unnumbered += 1
            continue
        if level == 1:
            in_unnumbered_section = False
            chapter += 1
            sub = 0
            subsub = 0
            if spec.body == "BAB_ROMAN":
                number = f"BAB {_as_roman(chapter)}"
            else:
                number = f"{chapter}."
            prefix = _numbered_runs(
                paragraph,
                number,
                level=1,
                kind=spec.body,
            )
            title_runs = _heading_title_runs(
                paragraph,
                level=1,
                uppercase=True,
            )
            _replace_heading_content(paragraph, prefix, title_runs)
            numbered += 1
            continue
        if in_unnumbered_section:
            unnumbered += 1
            continue
        if chapter == 0:
            skipped += 1
            continue
        if level == 2:
            sub += 1
            subsub = 0
            suffix = "." if spec.sub_dot else ""
            number = f"{chapter}.{sub}{suffix}"
        else:
            subsub += 1
            suffix = "." if spec.subsub_dot else ""
            number = f"{chapter}.{sub}.{subsub}{suffix}"
        prefix = _numbered_runs(
            paragraph,
            number,
            level=level,
            kind=spec.body,
        )
        title_runs = _heading_title_runs(paragraph, level=level, uppercase=False)
        _replace_heading_content(paragraph, prefix, title_runs)
        numbered += 1

    after = sha256_c14n(package.xml(DOCUMENT_PART))  # type: ignore[attr-defined]
    return HeadingReport(
        changed=before != after,
        numbered=numbered,
        unnumbered=unnumbered,
        skipped_without_chapter=skipped,
        headings=iter_headings(package),
    )


def heading_bookmark_name(heading: Heading) -> str:
    """Nama bookmark stabil untuk PAGEREF/TOC."""

    if heading.number:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", heading.number).strip("_")
        if safe:
            return f"_Toc{safe}"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", heading.text).strip("_")
    if safe:
        return f"_Toc{safe[:40]}"
    return f"_TocHeading{heading.level}"


__all__ = [
    "FOOTER_CONTENT_TYPE",
    "HEADER_CONTENT_TYPE",
    "HeaderFooterError",
    "HeaderFooterRefs",
    "Heading",
    "HeadingError",
    "HeadingReport",
    "NumberingSpec",
    "Section",
    "SectionError",
    "add_section_break",
    "apply_heading_numbering",
    "clear_header_footer_references",
    "create_header_footer_part",
    "heading_bookmark_name",
    "heading_level",
    "heading_text",
    "header_footer_part",
    "is_unnumbered",
    "iter_headings",
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
