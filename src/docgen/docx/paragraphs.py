"""Helper kanonis paragraf DOCX: body, style, level, teks, atribut, dan kosong.

Modul ini adalah sumber tunggal pembacaan ``w:body`` beserta child langsungnya,
style dan level heading paragraf, ekstraksi teks paragraf, penghapusan child
langsung, pembacaan atribut bilangan bulat, serta pembuatan paragraf kosong
kanonis. Modul DOCX lain dan stage memakai helper ini, bukan menduplikasi
traversal paragraf.

Semua fungsi bekerja pada elemen ``lxml`` hidup dan tidak melakukan I/O
package. ``xml.py`` tetap menjadi primitif parse/serialisasi dan tidak boleh
mengimpor modul ini.

Referensi: https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing?view=openxml-3.0.1
"""

import re

from lxml import etree

from . import DocxError
from .names import (
    W_BODY,
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
    W_PSTYLE,
    W_PTAB,
    W_RPR,
    W_T,
    W_TAB,
    W_TXBXCONTENT,
    W_VAL,
    normalize_style_id,
)
from .package import DOCUMENT_PART, DocumentPackage
from .xml import qn

_HEADING_LEVEL_RE = re.compile(r"^heading([1-9])$")

# Format kanonis paragraf kosong: satu sumber untuk stage ``blank_lines`` dan
# gap setelah judul TOC.
EMPTY_PARAGRAPH_FONT = "Times New Roman"
EMPTY_PARAGRAPH_HALF_POINTS = 24
EMPTY_PARAGRAPH_LINE_TWIPS = 360

# Tag yang tidak ditelusuri saat mengekstrak teks paragraf: properti, field,
# objek/gambar, text box, paragraf bersarang, dan teks yang dihapus.
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


class ParagraphError(DocxError):
    """Package DOCX tidak dapat dibaca atau tidak memiliki ``w:body``."""

    default_code = "PARAGRAPH"


def document_body(package: DocumentPackage) -> etree._Element:
    """Ambil ``w:body`` dari ``DocumentPackage``.

    Melempar ``ParagraphError`` bila argumen bukan package, part
    ``word/document.xml`` tidak ditemukan, atau root tidak memiliki ``w:body``.
    """

    if not isinstance(package, DocumentPackage):
        raise ParagraphError("document_body membutuhkan DocumentPackage")
    if not package.has_part(DOCUMENT_PART):
        raise ParagraphError(
            f"part {DOCUMENT_PART} tidak ditemukan",
            path=DOCUMENT_PART,
        )
    body = package.xml(DOCUMENT_PART).find(W_BODY)
    if body is None:
        raise ParagraphError(
            f"{DOCUMENT_PART} tidak memiliki elemen w:body",
            path=DOCUMENT_PART,
        )
    return body


def body_children(body: etree._Element) -> list[etree._Element]:
    """Child langsung ``w:body`` yang berupa elemen, tanpa komentar/PI.

    Elemen non-paragraf seperti ``w:tbl`` dan ``w:sectPr`` tetap disertakan
    karena keduanya bagian struktur body.
    """

    return [child for child in body if isinstance(child.tag, str)]


def paragraph_style_id(paragraph: etree._Element) -> str | None:
    """Nilai ``w:pStyle/@w:val`` langsung paragraf, atau ``None``."""

    style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
    if style is None:
        return None
    return style.get(W_VAL)


def heading_level(paragraph: etree._Element) -> int | None:
    """Level heading 1-9 dari style paragraf, atau ``None`` bila bukan heading.

    Style dinormalisasi lebih dulu sehingga ``Heading1``, ``Heading 1``, dan
    ``heading_1`` dianggap sama.
    """

    style_id = paragraph_style_id(paragraph)
    if style_id is None:
        return None
    match = _HEADING_LEVEL_RE.fullmatch(normalize_style_id(style_id))
    return int(match.group(1)) if match is not None else None


def paragraph_text(paragraph: etree._Element) -> str:
    """Teks paragraf dalam urutan dokumen.

    Menyertakan teks di hyperlink dan run bersarang, tab, line break, dan
    ``w:noBreakHyphen``. Teks di gambar, text box, paragraf bersarang, serta
    teks yang dihapus tidak disertakan. ``w:instrText`` selalu diabaikan.
    """

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
            elif tag == W_INSTRTEXT or tag in _TEXT_SKIP_DESCEND:
                continue
            else:
                walk(child)

    walk(paragraph)
    return "".join(parts)


def make_empty_paragraph(
    *,
    font: str = EMPTY_PARAGRAPH_FONT,
    half_points: int = EMPTY_PARAGRAPH_HALF_POINTS,
    line_twips: int = EMPTY_PARAGRAPH_LINE_TWIPS,
) -> etree._Element:
    """Buat paragraf kosong kanonis dengan spacing dan font eksplisit.

    Paragraf memakai ``w:spacing`` before/after 0 dan line ``line_twips``
    (``lineRule`` auto), lalu ``w:rPr`` berisi ``w:rFonts`` untuk
    ascii/hAnsi/cs/eastAsia serta ``w:sz``/``w:szCs``. Dipakai stage
    ``blank_lines`` untuk paragraf kosong fisik dan ``fields`` untuk gap
    setelah judul TOC.
    """

    paragraph = etree.Element(W_P)
    properties = etree.SubElement(paragraph, W_PPR)

    spacing = etree.SubElement(properties, qn("w:spacing"))
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), str(line_twips))
    spacing.set(qn("w:lineRule"), "auto")

    run_properties = etree.SubElement(properties, W_RPR)
    fonts = etree.SubElement(run_properties, qn("w:rFonts"))
    for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attribute), font)

    for tag in ("w:sz", "w:szCs"):
        size = etree.SubElement(run_properties, qn(tag))
        size.set(W_VAL, str(half_points))

    return paragraph


def remove_direct_children(parent: etree._Element, tag: str) -> int:
    """Hapus semua child langsung ``parent`` bertag ``tag``; kembalikan jumlah.

    ``tag`` memakai Clark notation (``qn("w:keepNext")``). Elemen bertag sama
    yang lebih dalam tidak disentuh.
    """

    removed = 0
    for child in parent.findall(tag):
        parent.remove(child)
        removed += 1
    return removed


def int_attribute(element: etree._Element, name: str) -> int | None:
    """Nilai atribut ``name`` sebagai ``int``, atau ``None``.

    ``None`` dikembalikan bila atribut tidak ada atau nilainya bukan bilangan
    bulat.
    """

    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


__all__ = [
    "EMPTY_PARAGRAPH_FONT",
    "EMPTY_PARAGRAPH_HALF_POINTS",
    "EMPTY_PARAGRAPH_LINE_TWIPS",
    "ParagraphError",
    "body_children",
    "document_body",
    "heading_level",
    "int_attribute",
    "make_empty_paragraph",
    "paragraph_style_id",
    "paragraph_text",
    "remove_direct_children",
]
