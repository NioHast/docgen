"""Helper XML untuk DOCX.

Semua parsing dan serialisasi XML untuk package melewati modul ini. Fungsi
container memutasi elemen yang diberikan; fungsi teks dan canonical murni.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Iterator, Sequence
from typing import Literal

from lxml import etree

from . import XmlError
from .names import (
    A_NS,
    NSMAP,
    R_NS,
    W,
    W_BR,
    W_CR,
    W_DEL,
    W_DELTEXT,
    W_DRAWING,
    W_FLDCHAR,
    W_INSTRTEXT,
    W_MOVEFROM,
    W_NO_BREAK_HYPHEN,
    W_OBJECT,
    W_P,
    W_PICT,
    W_PPR,
    W_PTAB,
    W_R,
    W_RPR,
    W_T,
    W_TAB,
    W_TBL,
    W_TBLPR,
    W_TC,
    W_TCPR,
    W_TXBXCONTENT,
    W_PROOFERR,
    W_LAST_RENDERED_PAGE_BREAK,
    W_NS,
    WP_NS,
    local_name,
)

Profile = Literal["c14n", "docx"]

# Urutan anak rPr/pPr sesuai skema OOXML agar Word tidak menganggap XML rusak.
RPR_ORDER: tuple[str, ...] = (
    "rStyle",
    "rFonts",
    "b",
    "bCs",
    "i",
    "iCs",
    "caps",
    "smallCaps",
    "strike",
    "dstrike",
    "outline",
    "shadow",
    "emboss",
    "imprint",
    "noProof",
    "snapToGrid",
    "vanish",
    "webHidden",
    "color",
    "spacing",
    "w",
    "kern",
    "position",
    "sz",
    "szCs",
    "highlight",
    "u",
    "effect",
    "bdr",
    "shd",
    "fitText",
    "vertAlign",
    "rtl",
    "cs",
    "em",
    "lang",
    "eastAsianLayout",
    "specVanish",
    "oMath",
)

PPR_ORDER: tuple[str, ...] = (
    "pStyle",
    "keepNext",
    "keepLines",
    "pageBreakBefore",
    "framePr",
    "widowControl",
    "numPr",
    "suppressLineNumbers",
    "pBdr",
    "shd",
    "tabs",
    "suppressAutoHyphens",
    "kinsoku",
    "wordWrap",
    "overflowPunct",
    "topLinePunct",
    "autoSpaceDE",
    "autoSpaceDN",
    "bidi",
    "adjustRightInd",
    "snapToGrid",
    "spacing",
    "ind",
    "contextualSpacing",
    "mirrorIndents",
    "suppressOverlap",
    "jc",
    "textDirection",
    "textAlignment",
    "textboxTightWrap",
    "outlineLvl",
    "divId",
    "cnfStyle",
    "rPr",
    "sectPr",
    "pPrChange",
)

SECTPR_ORDER: tuple[str, ...] = (
    "headerReference",
    "footerReference",
    "footnotePr",
    "endnotePr",
    "type",
    "pgSz",
    "pgMar",
    "paperSrc",
    "pgBorders",
    "lnNumType",
    "pgNumType",
    "cols",
    "formProt",
    "vAlign",
    "noEndnote",
    "titlePg",
    "textDirection",
    "bidi",
    "rtlGutter",
    "docGrid",
    "printerSettings",
    "sectPrChange",
)

TBLPR_ORDER: tuple[str, ...] = (
    "tblStyle",
    "tblpPr",
    "tblOverlap",
    "bidiVisual",
    "tblStyleRowBandSize",
    "tblStyleColBandSize",
    "tblW",
    "jc",
    "tblCellSpacing",
    "tblInd",
    "tblBorders",
    "shd",
    "tblLayout",
    "tblCellMar",
    "tblLook",
    "tblCaption",
    "tblDescription",
    "tblPrChange",
)

TCPR_ORDER: tuple[str, ...] = (
    "cnfStyle",
    "tcW",
    "gridSpan",
    "hMerge",
    "vMerge",
    "tcBorders",
    "shd",
    "noWrap",
    "tcMar",
    "textDirection",
    "tcFitText",
    "vAlign",
    "hideMark",
    "headers",
    "cellIns",
    "cellDel",
    "cellMerge",
    "tcPrChange",
)

_TEXT_SKIP_DESCEND = frozenset(
    {
        W_PPR,
        W_RPR,
        W_FLDCHAR,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_TXBXCONTENT,
        W_P,
        W_DEL,
        W_MOVEFROM,
        W_DELTEXT,
    }
)


def qn(tag: str) -> str:
    """Ubah ``prefix:local`` menjadi Clark notation.

    Clark notation yang sudah jadi dikembalikan apa adanya. Prefix yang tidak
    dikenal dianggap kesalahan pemanggil.
    """

    if not isinstance(tag, str) or not tag:
        raise ValueError("Nama tag XML tidak boleh kosong")
    if tag.startswith("{"):
        return tag
    prefix, separator, local = tag.partition(":")
    if not separator or not prefix or not local:
        raise ValueError(f"Tag XML harus memakai prefix: {tag!r}")
    namespace = NSMAP.get(prefix)
    if namespace is None:
        raise ValueError(f"Prefix namespace tidak dikenal: {prefix!r}")
    return f"{{{namespace}}}{local}"


def _make_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        remove_blank_text=False,
        remove_comments=False,
        remove_pis=False,
        recover=False,
        huge_tree=False,
    )


def parse_xml(data: bytes | bytearray | memoryview | str) -> etree._Element:
    """Parse XML dengan parser aman tanpa mengubah whitespace/komentar/PI."""

    if isinstance(data, str):
        data = data.encode("utf-8")
    elif isinstance(data, (bytearray, memoryview)):
        data = bytes(data)

    try:
        root = etree.fromstring(data, parser=_make_parser())
    except (etree.LxmlError, ValueError, TypeError) as exc:
        raise XmlError(f"XML tidak valid: {exc}") from exc

    if root is None:
        raise XmlError("XML tidak menghasilkan elemen root")

    tree = root.getroottree()
    if tree.docinfo.doctype or tree.docinfo.internalDTD is not None:
        raise XmlError("DOCTYPE/entity tidak didukung")

    for node in root.iter():
        if isinstance(node, etree._Entity):
            raise XmlError("Entity XML tidak didukung")

    return root


def serialize_xml(
    root: etree._Element | etree._ElementTree,
    *,
    xml_declaration: bool = True,
) -> bytes:
    """Serialisasi XML sebagai UTF-8 tanpa pretty-print."""

    if isinstance(root, etree._ElementTree):
        element = root.getroot()
    elif isinstance(root, etree._Element):
        element = root
    else:
        raise XmlError("serialize_xml membutuhkan element atau element tree")

    try:
        body = etree.tostring(
            element,
            encoding="UTF-8",
            xml_declaration=False,
            pretty_print=False,
            with_comments=True,
            with_tail=False,
        )
    except (etree.LxmlError, ValueError, TypeError) as exc:
        raise XmlError(f"XML gagal diserialisasi: {exc}") from exc

    if not xml_declaration:
        return body
    return (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body
    )


def _remove_with_tail(element: etree._Element) -> None:
    """Hapus elemen tanpa membuang text tail miliknya."""

    parent = element.getparent()
    if parent is None:
        return
    tail = element.tail
    if tail:
        previous = element.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(element)


def _strip_docx_noise(root: etree._Element) -> None:
    """Hapus artefak Word yang tidak semantik pada salinan canonical."""

    for element in list(root.iter()):
        if not isinstance(element.tag, str):
            continue
        if element.tag in (W_PROOFERR, W_LAST_RENDERED_PAGE_BREAK):
            _remove_with_tail(element)

    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        for attribute in list(element.attrib):
            if not attribute.startswith(W):
                continue
            if local_name(attribute).lower().startswith("rsid"):
                del element.attrib[attribute]


def canonicalize_xml(
    data: bytes | etree._Element | etree._ElementTree,
    *,
    profile: Profile = "docx",
) -> bytes:
    """Canonical XML (C14N 1.0 tanpa komentar) dengan profil opsional."""

    if profile not in ("c14n", "docx"):
        raise ValueError(f"Profil canonical tidak dikenal: {profile!r}")

    if isinstance(data, etree._ElementTree):
        source = data.getroot()
    elif isinstance(data, etree._Element):
        source = data
    else:
        source = parse_xml(data)

    work = copy.deepcopy(source)
    if profile == "docx":
        _strip_docx_noise(work)

    try:
        return etree.tostring(
            work,
            method="c14n",
            exclusive=False,
            with_comments=False,
            with_tail=False,
        )
    except (etree.LxmlError, ValueError, TypeError) as exc:
        raise XmlError(f"XML gagal dikanonikalisasi: {exc}") from exc


def sha256_c14n(
    data: bytes | etree._Element | etree._ElementTree,
    *,
    profile: Profile = "docx",
) -> str:
    """SHA-256 heksadesimal huruf kecil dari canonical XML."""

    return hashlib.sha256(canonicalize_xml(data, profile=profile)).hexdigest()


def iter_paragraphs(
    root: etree._Element | etree._ElementTree,
    *,
    include_tables: bool = True,
) -> Iterator[etree._Element]:
    """Iterasi paragraf dalam urutan dokumen.

    Paragraf di dalam ``w:txbxContent`` tidak dianggap paragraf body.
    """

    if isinstance(root, etree._ElementTree):
        root = root.getroot()

    if isinstance(root.tag, str) and root.tag == W_P:
        yield root
        return
    if not include_tables and isinstance(root.tag, str) and root.tag == W_TBL:
        return

    def walk(element: etree._Element) -> Iterator[etree._Element]:
        for child in element:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag == W_P:
                yield child
                continue
            if tag == W_TXBXCONTENT:
                continue
            if tag == W_TBL and not include_tables:
                continue
            yield from walk(child)

    yield from walk(root)


def iter_runs(paragraph: etree._Element) -> Iterator[etree._Element]:
    """Iterasi run dalam paragraf, termasuk run di hyperlink dan sdt."""

    if not isinstance(paragraph.tag, str):
        return
    if paragraph.tag == W_R:
        yield paragraph
        return

    def walk(element: etree._Element) -> Iterator[etree._Element]:
        for child in element:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag == W_R:
                yield child
                continue
            if tag in (W_TXBXCONTENT, W_P):
                continue
            yield from walk(child)

    yield from walk(paragraph)


def _text_content(element: etree._Element, *, include_fields: bool) -> str:
    parts: list[str] = []

    def walk(node: etree._Element) -> None:
        for child in node:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag == W_T:
                parts.append(child.text or "")
            elif tag in (W_TAB, W_PTAB):
                parts.append("\t")
            elif tag in (W_BR, W_CR):
                parts.append("\n")
            elif tag == W_NO_BREAK_HYPHEN:
                parts.append("\u2011")
            elif tag == W_INSTRTEXT:
                if include_fields:
                    parts.append(child.text or "")
            elif tag in _TEXT_SKIP_DESCEND:
                continue
            else:
                walk(child)

    walk(element)
    return "".join(parts)


def run_text(run: etree._Element) -> str:
    """Teks satu run: ``w:t``, tab, dan line break; field tidak disertakan."""

    return _text_content(run, include_fields=False)


def paragraph_text(
    paragraph: etree._Element,
    *,
    include_fields: bool = False,
) -> str:
    """Teks paragraf dalam urutan dokumen.

    ``w:instrText`` hanya disertakan bila ``include_fields=True``. Teks di
    dalam gambar, text box, dan paragraf bersarang tidak disertakan.
    """

    return _text_content(paragraph, include_fields=include_fields)


def _ensure_first_child(
    element: etree._Element,
    tag: str,
    *,
    expected_parent: str,
    label: str,
) -> etree._Element:
    if not isinstance(element.tag, str) or element.tag != expected_parent:
        raise XmlError(f"{label} harus berupa elemen {expected_parent}")
    existing = element.find(tag)
    if existing is not None:
        if element.index(existing) != 0:
            element.remove(existing)
            element.insert(0, existing)
        return existing
    child = etree.Element(tag)
    element.insert(0, child)
    return child


def ensure_ppr(paragraph: etree._Element) -> etree._Element:
    """Pastikan ``w:pPr`` ada dan menjadi child pertama paragraf."""

    return _ensure_first_child(
        paragraph, W_PPR, expected_parent=W_P, label="Paragraf"
    )


def ensure_rpr(run: etree._Element) -> etree._Element:
    """Pastikan ``w:rPr`` ada dan menjadi child pertama run."""

    return _ensure_first_child(run, W_RPR, expected_parent=W_R, label="Run")


def ensure_tblpr(table: etree._Element) -> etree._Element:
    """Pastikan ``w:tblPr`` ada dan menjadi child pertama tabel."""

    return _ensure_first_child(
        table, W_TBLPR, expected_parent=W_TBL, label="Tabel"
    )


def ensure_tcpr(cell: etree._Element) -> etree._Element:
    """Pastikan ``w:tcPr`` ada dan menjadi child pertama sel."""

    return _ensure_first_child(
        cell, W_TCPR, expected_parent=W_TC, label="Sel tabel"
    )


def _order_index(order: Sequence[str]) -> dict[str, int]:
    return {local_name(tag): index for index, tag in enumerate(order)}


def insert_ordered(
    parent: etree._Element,
    child: etree._Element,
    order: Sequence[str],
) -> None:
    """Sisipkan ``child`` pada urutan skema OOXML yang benar."""

    if not isinstance(child.tag, str):
        raise XmlError("Child yang disisipkan harus berupa elemen XML")
    index = _order_index(order).get(local_name(child.tag))
    if index is None:
        parent.append(child)
        return

    order_map = _order_index(order)
    for existing in parent:
        tag = existing.tag
        if not isinstance(tag, str):
            continue
        existing_index = order_map.get(local_name(tag))
        if existing_index is not None and existing_index > index:
            parent.insert(parent.index(existing), child)
            return
    parent.append(child)


def get_or_add(
    parent: etree._Element,
    tag: str,
    order: Sequence[str],
) -> etree._Element:
    """Ambil child langsung ``tag`` atau buat lalu sisipkan sesuai urutan."""

    qualified = qn(tag)
    existing = parent.find(qualified)
    if existing is not None:
        return existing
    child = etree.Element(qualified)
    insert_ordered(parent, child, order)
    return child


def is_on(element: etree._Element | None) -> bool:
    """Nilai boolean toggle OOXML (``w:b``, ``w:i``, dan sejenisnya)."""

    if element is None:
        return False
    value = element.get(f"{{{W_NS}}}val")
    if value is None:
        return True
    return value.strip().casefold() not in {"0", "false", "off", "no"}


__all__ = [
    "A_NS",
    "PPR_ORDER",
    "Profile",
    "RPR_ORDER",
    "R_NS",
    "SECTPR_ORDER",
    "TBLPR_ORDER",
    "TCPR_ORDER",
    "W_NS",
    "WP_NS",
    "canonicalize_xml",
    "ensure_ppr",
    "ensure_rpr",
    "ensure_tblpr",
    "ensure_tcpr",
    "get_or_add",
    "insert_ordered",
    "is_on",
    "iter_paragraphs",
    "iter_runs",
    "paragraph_text",
    "parse_xml",
    "qn",
    "run_text",
    "serialize_xml",
    "sha256_c14n",
]
