"""Builder dan parser field WordprocessingML (``w:fldChar``/``w:fldSimple``).

Field dipakai untuk TOC native, ``PAGEREF``, ``SEQ``, dan nomor halaman.
Modul ini hanya memutasi ``word/document.xml``; stage TOC memakai
:func:`insert_toc` dan stage halaman memakai field ``PAGE`` di part
header/footer.

Field kompleks selalu ditulis lengkap: ``begin`` -> ``instrText`` ->
``separate`` -> hasil -> ``end``. Word/LibreOffice yang mengisi hasil;
pipeline tidak menulis cache nomor halaman palsu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from enum import Enum

from lxml import etree

from ..errors import DocgenError
from .names import (
    W,
    W_BODY,
    W_DOCUMENT,
    W_FLDCHAR,
    W_FLDCHARTYPE,
    W_FLDSIMPLE,
    W_INSTR,
    W_INSTRTEXT,
    W_P,
    W_PPR,
    W_R,
    W_SDT,
    W_SDT_CONTENT,
    W_SECTPR,
    W_T,
    W_TAB,
    W_TBL,
)
from .package import DOCUMENT_PART
from .xml import paragraph_text, qn

SETTINGS_PART = "word/settings.xml"

_TOC_GALLERY = "Table of Contents"
_TOC_INSTRUCTION_RE = re.compile(r"^\s*TOC\b", re.IGNORECASE)
_FIELD_KIND_RE = re.compile(r"^\s*([A-Za-z]+)")

_PAGE_BREAK_TYPE = qn("w:br")


class FieldError(DocgenError):
    """Field tidak lengkap, instruksi tidak valid, atau konflik field."""

    default_code = "FIELD"


class FieldKind(Enum):
    """Jenis field yang dikenal pipeline."""

    TOC = "TOC"
    PAGEREF = "PAGEREF"
    SEQ = "SEQ"
    PAGE = "PAGE"
    NUMPAGES = "NUMPAGES"
    OTHER = "OTHER"


@dataclass(frozen=True)
class Field:
    """Satu field kompleks atau ``w:fldSimple``."""

    kind: FieldKind
    instruction: str
    paragraph: etree._Element
    begin: etree._Element
    separate: etree._Element | None
    end: etree._Element
    nested: tuple["Field", ...] = ()


@dataclass
class _Builder:
    begin: etree._Element
    paragraph: etree._Element
    instruction: list[str] = dataclass_field(default_factory=list)
    separate: etree._Element | None = None
    nested: list[Field] = dataclass_field(default_factory=list)


def _nearest_paragraph(element: etree._Element) -> etree._Element:
    node: etree._Element | None = element
    while node is not None:
        if node.tag == W_P:
            return node
        node = node.getparent()
    raise FieldError("Field tidak berada di dalam w:p")


def _nearest_sdt(element: etree._Element) -> etree._Element | None:
    node: etree._Element | None = element
    while node is not None:
        if node.tag == W_SDT:
            return node
        node = node.getparent()
    return None


def field_kind(instruction: str) -> FieldKind:
    """Klasifikasi instruksi field berdasarkan token pertama."""

    match = _FIELD_KIND_RE.match(instruction or "")
    if match is None:
        return FieldKind.OTHER
    token = match.group(1).upper()
    for kind in FieldKind:
        if kind is not FieldKind.OTHER and kind.value == token:
            return kind
    return FieldKind.OTHER


def field_instruction(field: Field) -> str:
    """Instruksi field tanpa spasi pinggir berlebih."""

    return " ".join((field.instruction or "").split())


def _element_order(root: etree._Element) -> dict[int, int]:
    return {id(element): index for index, element in enumerate(root.iter())}


def _parse_complex_fields(root: etree._Element) -> list[Field]:
    stack: list[_Builder] = []
    completed: list[Field] = []
    for element in root.iter():
        tag = element.tag
        if not isinstance(tag, str):
            continue
        if tag == W_INSTRTEXT:
            if stack:
                stack[-1].instruction.append(element.text or "")
            continue
        if tag != W_FLDCHAR:
            continue
        field_type = (element.get(W_FLDCHARTYPE) or "").casefold()
        if field_type == "begin":
            stack.append(
                _Builder(
                    begin=element,
                    paragraph=_nearest_paragraph(element),
                )
            )
        elif field_type == "separate":
            if not stack:
                raise FieldError("w:fldChar separate tanpa field begin")
            if stack[-1].separate is not None:
                raise FieldError("Field memiliki lebih dari satu separate")
            stack[-1].separate = element
        elif field_type == "end":
            if not stack:
                raise FieldError("w:fldChar end tanpa field begin")
            builder = stack.pop()
            if builder.separate is None:
                raise FieldError("Field kompleks tidak memiliki separate")
            instruction = "".join(builder.instruction)
            parsed = Field(
                kind=field_kind(instruction),
                instruction=instruction,
                paragraph=builder.paragraph,
                begin=builder.begin,
                separate=builder.separate,
                end=element,
                nested=tuple(builder.nested),
            )
            if stack:
                stack[-1].nested.append(parsed)
            else:
                completed.append(parsed)
    if stack:
        raise FieldError("Field kompleks tidak memiliki w:fldChar end")
    return completed


def _parse_simple_fields(root: etree._Element) -> list[Field]:
    parsed: list[Field] = []
    for simple in root.iter(W_FLDSIMPLE):
        instruction = simple.get(W_INSTR) or ""
        parsed.append(
            Field(
                kind=field_kind(instruction),
                instruction=instruction,
                paragraph=_nearest_paragraph(simple),
                begin=simple,
                separate=simple,
                end=simple,
                nested=(),
            )
        )
    return parsed


def iter_fields_in_root(root: etree._Element) -> tuple[Field, ...]:
    """Iterasi field di satu root XML dalam urutan dokumen."""

    fields = _parse_complex_fields(root) + _parse_simple_fields(root)
    order = _element_order(root)
    fields.sort(key=lambda item: order.get(id(item.begin), 0))
    return tuple(fields)


def iter_fields_in_part(package: object, part_name: str) -> tuple[Field, ...]:
    """Iterasi field di part XML tertentu (mis. header/footer)."""

    return iter_fields_in_root(package.xml(part_name))  # type: ignore[attr-defined]


def iter_fields(package: object) -> tuple[Field, ...]:
    """Iterasi field di ``word/document.xml``."""

    return iter_fields_in_root(package.xml(DOCUMENT_PART))  # type: ignore[attr-defined]


def iter_fields_in_paragraph(paragraph: etree._Element) -> tuple[Field, ...]:
    """Field yang berada di satu paragraf, termasuk field bersarang."""

    return tuple(
        field
        for field in iter_fields_in_root(paragraph)
        if field.paragraph is paragraph
    )


def field_result_text(field: Field) -> str:
    """Teks cache hasil field (antara ``separate`` dan ``end``)."""

    if field.begin.tag == W_FLDSIMPLE:
        return "".join(
            node.text or "" for node in field.begin.iter(W_T) if node.text
        )
    if field.separate is None:
        return ""
    root = field.begin.getroottree().getroot()
    if root is None:
        return ""
    parts: list[str] = []
    active = False
    for element in root.iter():
        if element is field.separate:
            active = True
            continue
        if not active:
            continue
        if element is field.end:
            break
        if element.tag == W_T:
            parts.append(element.text or "")
        elif element.tag == W_TAB:
            parts.append("\t")
    return "".join(parts)


def field_has_result(field: Field) -> bool:
    """True bila field punya teks cache hasil."""

    return bool(field_result_text(field))


def _append_run(
    paragraph: etree._Element,
    *,
    text: str | None = None,
    instr: str | None = None,
    fld_char: str | None = None,
    dirty: bool = False,
    rpr: etree._Element | None = None,
) -> etree._Element:
    run = etree.SubElement(paragraph, W_R)
    if rpr is not None:
        run.append(rpr)
    if fld_char is not None:
        element = etree.SubElement(run, W_FLDCHAR)
        element.set(W + "fldCharType", fld_char)
        if dirty:
            element.set(W + "dirty", "true")
    if instr is not None:
        element = etree.SubElement(run, W_INSTRTEXT)
        element.set(qn("xml:space"), "preserve")
        element.text = instr
    if text is not None:
        element = etree.SubElement(run, W_T)
        element.text = text
    return run


def _field_runs(
    paragraph: etree._Element,
    instruction: str,
    *,
    result: str = "",
    dirty: bool = True,
    end_field: bool = True,
) -> tuple[etree._Element, etree._Element, etree._Element | None]:
    begin = _append_run(paragraph, fld_char="begin", dirty=dirty)
    _append_run(paragraph, instr=instruction)
    separate = _append_run(paragraph, fld_char="separate")
    if result:
        _append_run(paragraph, text=result)
    end = _append_run(paragraph, fld_char="end") if end_field else None
    return begin, separate, end


def _new_paragraph(style: str | None = None) -> etree._Element:
    paragraph = etree.Element(W_P)
    if style:
        ppr = etree.SubElement(paragraph, qn("w:pPr"))
        pstyle = etree.SubElement(ppr, qn("w:pStyle"))
        pstyle.set(W + "val", style)
    return paragraph


def _body(package: object) -> etree._Element:
    root = package.xml(DOCUMENT_PART)  # type: ignore[attr-defined]
    if not isinstance(root.tag, str) or root.tag != W_DOCUMENT:
        raise FieldError("Root document.xml bukan w:document")
    body = root.find(W_BODY)
    if body is None:
        raise FieldError("w:body tidak ditemukan")
    return body


def _normalized_text(paragraph: etree._Element) -> str:
    return " ".join(paragraph_text(paragraph).split())


def _paragraph_style(paragraph: etree._Element) -> str | None:
    ppr = paragraph.find(W + "pPr")
    if ppr is None:
        return None
    style = ppr.find(W + "pStyle")
    return style.get(W + "val") if style is not None else None


def _is_body_chapter(paragraph: etree._Element) -> bool:
    if paragraph.tag != W_P:
        return False
    if _paragraph_style(paragraph) != "Heading1":
        return False
    text = _normalized_text(paragraph)
    return (
        re.match(
            r"^(?:BAB\s+(?:[IVXLCDM]+|\d+)(?=\b|\s)|\d+\.(?=\s|$))",
            text,
            re.IGNORECASE,
        )
        is not None
    )


def _remove_element(element: etree._Element) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _remove_toc_sdts(root: etree._Element) -> int:
    removed = 0
    for sdt in list(root.iter(W_SDT)):
        pr = sdt.find(W + "sdtPr")
        gallery = (
            pr.find(".//" + qn("w:docPartGallery"))
            if pr is not None
            else None
        )
        if gallery is None or gallery.get(W + "val") != _TOC_GALLERY:
            continue
        _remove_element(sdt)
        removed += 1
    return removed


def _remove_field(field: Field) -> None:
    if field.begin.tag == W_FLDSIMPLE:
        _remove_element(field.begin)
        return
    root = field.begin.getroottree().getroot()
    if root is None:
        return
    result_runs: list[etree._Element] = []
    if field.separate is not None:
        active = False
        for element in root.iter():
            if element is field.separate:
                active = True
                continue
            if element is field.end:
                break
            if not active:
                continue
            run = element
            while run is not None and run.tag != W_R:
                run = run.getparent()
            if run is not None and run not in result_runs:
                result_runs.append(run)
    for run in result_runs:
        _remove_element(run)
    # Hapus run pemilik elemen field; begin/separate/end biasanya berada di
    # run terpisah. Bila satu run memuat beberapa elemen, run tetap dihapus.
    for element in (field.begin, field.separate, field.end):
        if element is None:
            continue
        run = element
        while run is not None and run.tag != W_R:
            run = run.getparent()
        if run is not None:
            _remove_element(run)
    # Hasil field (teks/cache) di antara separate dan end.
    if field.separate is not None:
        active = False
        for element in list(root.iter()):
            if element is field.separate:
                active = True
                continue
            if element is field.end:
                break
            if not active:
                continue
            run = element
            while run is not None and run.tag != W_R:
                run = run.getparent()
            if run is not None:
                _remove_element(run)


def _remove_toc_fields(root: etree._Element) -> int:
    removed = 0
    for field in iter_fields_in_root(root):
        if field.kind is not FieldKind.TOC:
            continue
        _remove_field(field)
        removed += 1
    return removed


def _remove_existing_toc(root: etree._Element, title: str) -> None:
    _remove_toc_sdts(root)
    _remove_toc_fields(root)
    for paragraph in list(root.iter(W_P)):
        if _normalized_text(paragraph) != title:
            continue
        if _paragraph_style(paragraph) not in ("TOCHeading", "Heading1"):
            continue
        if _nearest_sdt(paragraph) is not None:
            continue
        _remove_element(paragraph)


def _sdt_toc(
    title: str,
    instruction: str,
) -> tuple[etree._Element, etree._Element, etree._Element, etree._Element]:
    sdt = etree.Element(W_SDT)
    sdt_pr = etree.SubElement(sdt, qn("w:sdtPr"))
    rpr = etree.SubElement(sdt_pr, qn("w:rPr"))
    bold = etree.SubElement(rpr, qn("w:b"))
    bold.set(W + "val", "0")
    bold_cs = etree.SubElement(rpr, qn("w:bCs"))
    bold_cs.set(W + "val", "0")
    identifier = etree.SubElement(sdt_pr, qn("w:id"))
    identifier.set(W + "val", "1180696141")
    doc_part = etree.SubElement(sdt_pr, qn("w:docPartObj"))
    gallery = etree.SubElement(doc_part, qn("w:docPartGallery"))
    gallery.set(W + "val", _TOC_GALLERY)
    etree.SubElement(doc_part, qn("w:docPartUnique"))

    end_pr = etree.SubElement(sdt, qn("w:sdtEndPr"))
    end_rpr = etree.SubElement(end_pr, qn("w:rPr"))
    etree.SubElement(end_rpr, qn("w:noProof"))

    content = etree.SubElement(sdt, W_SDT_CONTENT)

    title_paragraph = _new_paragraph("TOCHeading")
    title_ppr = title_paragraph.find(W + "pPr")
    assert title_ppr is not None
    jc = etree.SubElement(title_ppr, qn("w:jc"))
    jc.set(W + "val", "center")
    outline = etree.SubElement(title_ppr, qn("w:outlineLvl"))
    outline.set(W + "val", "9")
    title_run = etree.SubElement(title_paragraph, W_R)
    title_rpr = etree.SubElement(title_run, qn("w:rPr"))
    etree.SubElement(title_rpr, qn("w:b"))
    sz = etree.SubElement(title_rpr, qn("w:sz"))
    sz.set(W + "val", "24")
    sz_cs = etree.SubElement(title_rpr, qn("w:szCs"))
    sz_cs.set(W + "val", "24")
    title_text = etree.SubElement(title_run, W_T)
    title_text.text = title
    content.append(title_paragraph)

    begin_paragraph = _new_paragraph("TOC1")
    begin, separate, _unused_end = _field_runs(
        begin_paragraph,
        instruction,
        result="",
        end_field=False,
    )
    end_paragraph = _new_paragraph("TOC1")
    end = _append_run(end_paragraph, fld_char="end")
    content.append(begin_paragraph)
    content.append(end_paragraph)
    return sdt, begin, separate, end


def _insert_before(body: etree._Element, before: etree._Element, sdt: etree._Element) -> None:
    if before.getparent() is not body:
        raise FieldError("Target penyisipan TOC bukan child langsung w:body")
    body.insert(body.index(before), sdt)


def _first_body_chapter(body: etree._Element) -> etree._Element | None:
    for child in body:
        if child.tag == W_P and _is_body_chapter(child):
            return child
    return None


def _section_break_before(
    paragraph: etree._Element,
) -> etree._Element:
    """Paragraf ber-``sectPr`` tepat sebelum bab pertama, bila ada.

    TOC dan daftar tabel/gambar adalah front matter. Bila sections sudah
    menaruh section break sebelum Heading1 bab pertama, field harus
    disisipkan sebelum break itu agar nomor halaman Romawi TOC tetap
    terpisah dari nomor Arab body.
    """

    previous = paragraph.getprevious()
    while previous is not None and previous.tag not in (W_P, W_SDT, W_TBL):
        previous = previous.getprevious()
    if previous is not None and previous.tag == W_P:
        ppr = previous.find(W_PPR)
        if ppr is not None and ppr.find(W_SECTPR) is not None:
            return previous
    return paragraph


def _paragraph_has_page_break(paragraph: etree._Element) -> bool:
    for br in paragraph.iter(W + "br"):
        if (br.get(W + "type") or "").casefold() == "page":
            return True
    ppr = paragraph.find(W + "pPr")
    if ppr is not None and ppr.find(W + "pageBreakBefore") is not None:
        return True
    return False


def _remove_blank_breaks_after(body: etree._Element, sdt: etree._Element) -> int:
    """Hapus paragraf page-break kosong setelah TOC agar tidak ada blank page."""

    removed = 0
    index = body.index(sdt) + 1
    while index < len(body):
        child = body[index]
        if child.tag != W_P:
            break
        ppr = child.find(W + "pPr")
        has_sect_pr = ppr is not None and ppr.find(W + "sectPr") is not None
        text = "".join(node.text or "" for node in child.iter(W_T)).strip()
        if has_sect_pr or text:
            break
        if _paragraph_has_page_break(child):
            body.remove(child)
            removed += 1
            continue
        index += 1
    return removed


def insert_toc(
    package: object,
    *,
    title: str,
    levels: tuple[int, int] = (1, 3),
    caption: str | None = None,
    before: etree._Element | None = None,
) -> Field:
    """Tulis field TOC native di dalam ``w:sdt``.

    Field TOC lama diganti, bukan ditambah. ``caption`` mengubah instruksi
    menjadi ``TOC \\c "..."`` untuk daftar gambar/tabel. Bila ``before``
    tidak diberikan, TOC diletakkan sebelum Heading1 ``BAB ...`` pertama,
    atau di akhir body sebelum ``w:sectPr``.
    """

    if not isinstance(title, str) or not title.strip():
        raise FieldError("Judul TOC tidak boleh kosong")
    low, high = levels
    if not (1 <= low <= high <= 9):
        raise FieldError("levels TOC harus 1 <= low <= high <= 9")
    if caption is not None and not caption.strip():
        raise FieldError("Caption TOC tidak boleh kosong")

    body = _body(package)
    _remove_existing_toc(body, title.strip())

    if caption is None:
        instruction = f' TOC \\o "{low}-{high}" \\h \\z \\u '
    else:
        escaped = caption.replace('"', '\\"')
        instruction = f' TOC \\c "{escaped}" \\h \\z '

    sdt, begin, separate, end = _sdt_toc(title.strip(), instruction)

    if before is not None:
        _insert_before(body, before, sdt)
    else:
        target = _first_body_chapter(body)
        if target is not None:
            anchor = _section_break_before(target)
            _insert_before(body, anchor, sdt)
        else:
            final_sect = body.find(W + "sectPr")
            if final_sect is not None:
                body.insert(body.index(final_sect), sdt)
            else:
                body.append(sdt)

    _remove_blank_breaks_after(body, sdt)
    paragraph = begin.getparent()
    assert paragraph is not None
    return Field(
        kind=FieldKind.TOC,
        instruction=instruction,
        paragraph=paragraph,
        begin=begin,
        separate=separate,
        end=end,
        nested=(),
    )


def insert_seq(
    package: object,
    *,
    paragraph: etree._Element,
    label: str,
) -> Field:
    """Tambahkan field ``SEQ <label>`` pada akhir paragraf."""

    if not isinstance(label, str) or not label.strip():
        raise FieldError("Label SEQ tidak boleh kosong")
    if paragraph.tag != W_P:
        raise FieldError("SEQ hanya boleh disisipkan ke paragraf")
    instruction = f" SEQ {label.strip()} "
    begin, separate, end = _field_runs(paragraph, instruction, result="1")
    return Field(
        kind=FieldKind.SEQ,
        instruction=instruction,
        paragraph=paragraph,
        begin=begin,
        separate=separate,
        end=end,
        nested=(),
    )


def insert_pageref(
    package: object,
    *,
    paragraph: etree._Element,
    bookmark: str,
) -> Field:
    """Tambahkan field ``PAGEREF <bookmark> \\h`` pada akhir paragraf."""

    if not isinstance(bookmark, str) or not bookmark.strip():
        raise FieldError("Nama bookmark PAGEREF tidak boleh kosong")
    if paragraph.tag != W_P:
        raise FieldError("PAGEREF hanya boleh disisipkan ke paragraf")
    instruction = f" PAGEREF {bookmark.strip()} \\h "
    begin, separate, end = _field_runs(paragraph, instruction, result="0")
    return Field(
        kind=FieldKind.PAGEREF,
        instruction=instruction,
        paragraph=paragraph,
        begin=begin,
        separate=separate,
        end=end,
        nested=(),
    )


def is_bold_exempt(field: Field) -> bool:
    """Field yang run-nya tidak boleh kehilangan bold saat normalisasi."""

    return field.kind in {
        FieldKind.TOC,
        FieldKind.PAGEREF,
        FieldKind.SEQ,
        FieldKind.PAGE,
        FieldKind.NUMPAGES,
    }


def _settings_root(package: object) -> etree._Element | None:
    if not package.has_part(SETTINGS_PART):  # type: ignore[attr-defined]
        return None
    return package.xml(SETTINGS_PART)  # type: ignore[attr-defined]


def update_fields_enabled(package: object) -> bool:
    """True bila ``w:updateFields`` aktif di ``word/settings.xml``."""

    root = _settings_root(package)
    if root is None:
        return False
    element = root.find(W + "updateFields")
    if element is None:
        return False
    value = element.get(W + "val")
    if value is None:
        return True
    return value.strip().casefold() not in {"0", "false", "off", "no"}


def strip_update_fields(package: object) -> bool:
    """Hapus ``w:updateFields`` dari settings; field tidak diubah."""

    root = _settings_root(package)
    if root is None:
        return False
    removed = False
    for element in list(root.findall(W + "updateFields")):
        root.remove(element)
        removed = True
    return removed


def ensure_no_blank_page_after_toc(package: object) -> int:
    """Bersihkan page-break kosong setelah setiap TOC ``w:sdt``."""

    body = _body(package)
    removed = 0
    for child in list(body):
        if child.tag != W_SDT:
            continue
        pr = child.find(W + "sdtPr")
        gallery = (
            pr.find(".//" + qn("w:docPartGallery")) if pr is not None else None
        )
        if gallery is None or gallery.get(W + "val") != _TOC_GALLERY:
            continue
        removed += _remove_blank_breaks_after(body, child)
    return removed


__all__ = [
    "Field",
    "FieldError",
    "FieldKind",
    "SETTINGS_PART",
    "ensure_no_blank_page_after_toc",
    "field_has_result",
    "field_instruction",
    "field_kind",
    "field_result_text",
    "insert_pageref",
    "insert_seq",
    "insert_toc",
    "is_bold_exempt",
    "iter_fields",
    "iter_fields_in_paragraph",
    "iter_fields_in_part",
    "iter_fields_in_root",
    "strip_update_fields",
    "update_fields_enabled",
]
