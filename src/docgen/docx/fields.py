"""Parser, scanner, dan builder field WordprocessingML.

Field dipakai untuk TOC native, ``PAGEREF``, ``SEQ``, dan nomor halaman.
Modul ini adalah satu-satunya parser ``w:fldChar``/``w:fldSimple`` dan satu-
satunya scanner marker field untuk modul DOCX serta stage. Stage TOC memakai
:func:`insert_toc`; stage halaman memakai :func:`insert_field` untuk field
``PAGE`` di part header/footer.

Field kompleks selalu ditulis lengkap: ``begin`` -> ``instrText`` ->
``separate`` -> hasil -> ``end``. Word/LibreOffice yang mengisi hasil;
pipeline tidak menulis cache nomor halaman palsu dan tidak menulis
``w:dirty``.

Referensi: https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing?view=openxml-3.0.1
"""

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum

from lxml import etree

from ..errors import DocgenError
from .names import (
    W_DEL,
    W_DELTEXT,
    W_DRAWING,
    W_FLDCHAR,
    W_FLDCHARTYPE,
    W_FLDSIMPLE,
    W_INSTR,
    W_INSTRTEXT,
    W_MOVEFROM,
    W_OBJECT,
    W_P,
    W_PICT,
    W_PPR,
    W_PSTYLE,
    W_R,
    W_SDT,
    W_SDT_CONTENT,
    W_SECTPR,
    W_T,
    W_TAB,
    W_TBL,
    W_TXBXCONTENT,
    W,
)
from .package import DOCUMENT_PART, DocumentPackage
from .paragraphs import (
    ParagraphError,
    document_body,
    make_empty_paragraph,
    paragraph_style_id,
    paragraph_text,
)
from .runs import build_run, make_run
from .xml import iter_runs, qn

SETTINGS_PART = "word/settings.xml"

_TOC_GALLERY = "Table of Contents"
_FIELD_KIND_RE = re.compile(r"^\s*([A-Za-z]+)")
FIELD_NAME_RE = re.compile(r"\s*([A-Za-z]+)")
EXEMPT_FIELDS = frozenset({"TOC", "PAGEREF", "SEQ"})

_RANGE_SKIP_TAGS = frozenset(
    {
        W_PPR,
        W_P,
        W_TXBXCONTENT,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_INSTRTEXT,
        W_FLDCHAR,
        W_DEL,
        W_MOVEFROM,
        W_DELTEXT,
    }
)


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


class FieldMarkerKind(Enum):
    """Jenis elemen yang membentuk field kompleks atau sederhana."""

    BEGIN = "begin"
    SEPARATE = "separate"
    END = "end"
    INSTRUCTION = "instrText"
    SIMPLE = "simple"


@dataclass(frozen=True)
class Field:
    """Satu field kompleks atau ``w:fldSimple``."""

    kind: FieldKind
    instruction: str
    paragraph: etree._Element
    begin: etree._Element
    separate: etree._Element | None
    end: etree._Element
    nested: tuple[Field, ...] = ()


@dataclass(frozen=True, slots=True)
class FieldPosition:
    """Posisi penulisan field kompleks.

    ``paragraph`` menerima run ``begin``, ``instrText``, ``separate``, dan
    hasil. ``before`` membatasi penyisipan run awal pada child langsung
    paragraf tersebut; ``None`` berarti run ditambahkan di akhir paragraf.
    ``end_paragraph`` memisahkan run ``end`` ke paragraf lain sehingga field
    dapat membentang dua paragraf seperti TOC. ``rpr`` disalin ke setiap run
    field.
    """

    paragraph: etree._Element
    before: etree._Element | None = None
    end_paragraph: etree._Element | None = None
    rpr: etree._Element | None = None


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


def field_marker_kind(element: etree._Element) -> FieldMarkerKind | None:
    """Klasifikasi satu elemen marker field, atau ``None`` bila bukan marker."""

    tag = element.tag
    if tag == W_FLDCHAR:
        field_type = (element.get(W_FLDCHARTYPE) or "").casefold()
        if field_type == "begin":
            return FieldMarkerKind.BEGIN
        if field_type == "separate":
            return FieldMarkerKind.SEPARATE
        if field_type == "end":
            return FieldMarkerKind.END
        return None
    if tag == W_INSTRTEXT:
        return FieldMarkerKind.INSTRUCTION
    if tag == W_FLDSIMPLE:
        return FieldMarkerKind.SIMPLE
    return None


def iter_field_markers(paragraph: etree._Element) -> Iterator[etree._Element]:
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
        kind = field_marker_kind(marker)
        if kind is FieldMarkerKind.BEGIN:
            stack.append([])
        elif kind is FieldMarkerKind.END and stack:
            yield "".join(stack.pop())
        elif kind is FieldMarkerKind.INSTRUCTION:
            if stack:
                stack[-1].append(marker.text or "")
        elif kind is FieldMarkerKind.SIMPLE:
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

    return any(field_marker_kind(element) is not None for element in paragraph.iter())


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


def iter_field_runs(paragraph: etree._Element) -> Iterator[etree._Element]:
    """Iterasi run yang menjadi bagian field (begin sampai end).

    Run hasil field ikut dianggap run field. Ini penting agar
    ``w:fldSimple`` dan field kompleks tidak kehilangan bold langsung.
    """

    depth = 0
    simple_runs: set[int] = set()
    for run in iter_runs(paragraph):
        if _ancestor(run, W_FLDSIMPLE):
            simple_runs.add(id(run))

    for run in iter_runs(paragraph):
        markers = list(run.iter(W_FLDCHAR))
        instr = run.find(f".//{W_INSTRTEXT}")
        if depth > 0 or id(run) in simple_runs or markers or instr is not None:
            yield run
        for marker in markers:
            kind = field_marker_kind(marker)
            if kind is FieldMarkerKind.BEGIN:
                depth += 1
            elif kind is FieldMarkerKind.END and depth > 0:
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


def field_text_ranges(paragraph: etree._Element) -> tuple[tuple[int, int], ...]:
    """Rentang offset teks yang ditempati field (``fldSimple``/``fldChar``)."""

    ranges: list[tuple[int, int]] = []
    stack: list[int] = []
    offset = 0
    marker_elements = tuple(iter_field_markers(paragraph))
    markers = {id(marker): field_marker_kind(marker) for marker in marker_elements}

    def walk(element: etree._Element) -> None:
        nonlocal offset
        for child in element:
            kind = markers.get(id(child))
            if kind is FieldMarkerKind.SIMPLE:
                start = offset
                stack.append(start)
                walk(child)
                start = stack.pop()
                if offset > start:
                    ranges.append((start, offset))
            elif kind is FieldMarkerKind.BEGIN:
                stack.append(offset)
            elif kind is FieldMarkerKind.END and stack:
                start = stack.pop()
                if offset > start:
                    ranges.append((start, offset))
            elif child.tag == W_T:
                offset += len(child.text or "")
            elif child.tag in _RANGE_SKIP_TAGS:
                continue
            else:
                walk(child)

    walk(paragraph)
    return tuple(ranges)


def _element_order(root: etree._Element) -> dict[int, int]:
    return {id(element): index for index, element in enumerate(root.iter())}


def _parse_complex_fields(root: etree._Element) -> list[Field]:
    """Parse field kompleks ``fldChar`` menjadi daftar ``Field`` berurutan.

    Field bersarang dilampirkan ke ``nested`` milik parent. ``FieldError``
    dilempar bila ada begin/separate/end yang tidak seimbang atau field tanpa
    separate.
    """

    stack: list[_Builder] = []
    completed: list[Field] = []
    for element in root.iter():
        marker_kind = field_marker_kind(element)
        if marker_kind is FieldMarkerKind.INSTRUCTION:
            if stack:
                stack[-1].instruction.append(element.text or "")
            continue
        if marker_kind is FieldMarkerKind.BEGIN:
            stack.append(
                _Builder(
                    begin=element,
                    paragraph=_nearest_paragraph(element),
                )
            )
        elif marker_kind is FieldMarkerKind.SEPARATE:
            if not stack:
                raise FieldError("w:fldChar separate tanpa field begin")
            if stack[-1].separate is not None:
                raise FieldError("Field memiliki lebih dari satu separate")
            stack[-1].separate = element
        elif marker_kind is FieldMarkerKind.END:
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

    return tuple(field for field in iter_fields_in_root(paragraph) if field.paragraph is paragraph)


def field_result_text(field: Field) -> str:
    """Teks cache hasil field (antara ``separate`` dan ``end``)."""

    if field.begin.tag == W_FLDSIMPLE:
        return "".join(node.text or "" for node in field.begin.iter(W_T) if node.text)
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


def _field_run(
    *,
    rpr: etree._Element | None = None,
    text: str | None = None,
    instr: str | None = None,
    fld_char: str | None = None,
) -> etree._Element:
    run = build_run(rpr=rpr)
    if fld_char is not None:
        element = etree.SubElement(run, W_FLDCHAR)
        element.set(W_FLDCHARTYPE, fld_char)
    if instr is not None:
        element = etree.SubElement(run, W_INSTRTEXT)
        element.set(qn("xml:space"), "preserve")
        element.text = instr
    if text is not None:
        element = etree.SubElement(run, W_T)
        element.text = text
    return run


def _instruction_text(switches: Sequence[str]) -> str:
    if isinstance(switches, str):
        raise FieldError("Switches field harus sequence token, bukan string tunggal")
    parts: list[str] = []
    for switch in switches:
        if not isinstance(switch, str):
            raise FieldError("Switch field harus berupa string")
        value = switch.strip()
        if value:
            parts.append(value)
    if not parts:
        raise FieldError("Instruksi field tidak boleh kosong")
    return f" {' '.join(parts)} "


def _insert_runs(
    paragraph: etree._Element,
    runs: Sequence[etree._Element],
    before: etree._Element | None,
) -> None:
    if before is None:
        paragraph.extend(runs)
        return
    index = paragraph.index(before)
    for offset, run in enumerate(runs):
        paragraph.insert(index + offset, run)


def insert_field(
    switches: Sequence[str],
    position: FieldPosition,
    result: str = "",
) -> Field:
    """Sisipkan field kompleks lengkap pada posisi paragraf yang eksplisit.

    ``switches`` adalah token instruksi tanpa spasi pinggir; fungsi menulis
    tepat satu spasi di awal dan akhir instruksi. ``position`` menentukan
    paragraf run awal, anchor ``before`` opsional, paragraf run ``end``
    opsional, dan template ``rPr``. Urutan XML selalu ``begin``,
    ``instrText``, ``separate``, hasil, lalu ``end``; ``w:dirty`` tidak
    pernah ditulis. ``FieldError`` dilempar untuk posisi atau switch yang
    tidak valid.
    """

    instruction = _instruction_text(switches)
    paragraph = position.paragraph
    if paragraph.tag != W_P:
        raise FieldError("Field hanya boleh disisipkan ke paragraf")
    end_paragraph = position.end_paragraph if position.end_paragraph is not None else paragraph
    if end_paragraph.tag != W_P:
        raise FieldError("Paragraf akhir field harus w:p")
    if position.before is not None and position.before.getparent() is not paragraph:
        raise FieldError("Anchor penyisipan field bukan child langsung paragraf")
    if not isinstance(result, str):
        raise FieldError("Hasil field harus berupa string")

    begin_run = _field_run(rpr=position.rpr, fld_char="begin")
    instruction_run = _field_run(rpr=position.rpr, instr=instruction)
    separate_run = _field_run(rpr=position.rpr, fld_char="separate")
    head: list[etree._Element] = [begin_run, instruction_run, separate_run]
    if result:
        head.append(_field_run(rpr=position.rpr, text=result))
    end_run = _field_run(rpr=position.rpr, fld_char="end")

    if end_paragraph is paragraph:
        _insert_runs(paragraph, [*head, end_run], position.before)
    else:
        _insert_runs(paragraph, head, position.before)
        end_paragraph.append(end_run)

    return Field(
        kind=field_kind(instruction),
        instruction=instruction,
        paragraph=paragraph,
        begin=begin_run,
        separate=separate_run,
        end=end_run,
        nested=(),
    )


def _new_paragraph(style: str | None = None) -> etree._Element:
    paragraph = etree.Element(W_P)
    if style:
        ppr = etree.SubElement(paragraph, qn("w:pPr"))
        pstyle = etree.SubElement(ppr, qn("w:pStyle"))
        pstyle.set(W + "val", style)
    return paragraph


def _body(package: DocumentPackage) -> etree._Element:
    try:
        return document_body(package)
    except ParagraphError as exc:
        raise FieldError(str(exc)) from exc


def _normalized_text(paragraph: etree._Element) -> str:
    return " ".join(paragraph_text(paragraph).split())


def _is_body_chapter(paragraph: etree._Element) -> bool:
    if paragraph.tag != W_P:
        return False
    if paragraph_style_id(paragraph) != "Heading1":
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
        gallery = pr.find(".//" + qn("w:docPartGallery")) if pr is not None else None
        if gallery is None or gallery.get(W + "val") != _TOC_GALLERY:
            continue
        _remove_element(sdt)
        removed += 1
    return removed


def _remove_field(field: Field) -> None:
    """Hapus elemen field beserta run hasil dan cache-nya dari tree."""

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
        if paragraph_style_id(paragraph) not in ("TOCHeading", "Heading1"):
            continue
        if _nearest_sdt(paragraph) is not None:
            continue
        _remove_element(paragraph)


def _sdt_toc(
    title: str,
    switches: Sequence[str],
    *,
    gap_after_title: bool,
    page_break_before: bool,
) -> tuple[etree._Element, Field]:
    """Bangun ``w:sdt`` TOC berisi paragraf judul dan field TOC.

    ``gap_after_title`` menyisipkan satu paragraf kosong kanonis di dalam
    ``w:sdtContent`` tepat setelah paragraf judul. ``page_break_before``
    menambahkan ``w:pageBreakBefore`` pada paragraf judul agar daftar dimulai
    di halaman baru. Mengembalikan elemen ``sdt`` dan ``Field`` yang disisipkan
    agar pemanggil dapat memberi ID atau memverifikasinya.
    """

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
    if page_break_before:
        # Urutan child w:pPr: pStyle, pageBreakBefore, ..., jc, outlineLvl.
        index = 1 if title_ppr.find(W_PSTYLE) is not None else 0
        title_ppr.insert(index, etree.Element(qn("w:pageBreakBefore")))
    jc = etree.SubElement(title_ppr, qn("w:jc"))
    jc.set(W + "val", "center")
    outline = etree.SubElement(title_ppr, qn("w:outlineLvl"))
    outline.set(W + "val", "9")
    title_rpr = etree.Element(qn("w:rPr"))
    etree.SubElement(title_rpr, qn("w:b"))
    sz = etree.SubElement(title_rpr, qn("w:sz"))
    sz.set(W + "val", "24")
    sz_cs = etree.SubElement(title_rpr, qn("w:szCs"))
    sz_cs.set(W + "val", "24")
    title_run = make_run(title_paragraph, rpr=title_rpr)
    title_text = etree.SubElement(title_run, W_T)
    title_text.text = title
    content.append(title_paragraph)
    if gap_after_title:
        # Satu paragraf kosong fisik agar jarak judul ke entri sama dengan
        # jarak setelah Heading1 bab.
        content.append(make_empty_paragraph())

    begin_paragraph = _new_paragraph("TOC1")
    end_paragraph = _new_paragraph("TOC1")
    field = insert_field(
        switches,
        FieldPosition(paragraph=begin_paragraph, end_paragraph=end_paragraph),
    )
    content.append(begin_paragraph)
    content.append(end_paragraph)
    return sdt, field


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
    return ppr is not None and ppr.find(W + "pageBreakBefore") is not None


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
    package: DocumentPackage,
    *,
    title: str,
    levels: tuple[int, int] = (1, 3),
    caption: str | None = None,
    before: etree._Element | None = None,
    keep_existing: bool = False,
    gap_after_title: bool = True,
    page_break_before: bool = False,
) -> Field:
    r"""Tulis field TOC native di dalam ``w:sdt``.

    Secara default field TOC lama diganti, bukan ditambah. Bila
    ``keep_existing`` benar, TOC lama dipertahankan dan field baru tetap
    disisipkan; pemanggil bertanggung jawab memilih posisi ``before`` agar
    tidak ada duplikat yang tidak disengaja. ``caption`` mengubah instruksi
    menjadi ``TOC \c "..."`` untuk daftar gambar/tabel. Bila ``before``
    tidak diberikan, TOC diletakkan sebelum Heading1 ``BAB ...`` pertama,
    atau di akhir body sebelum ``w:sectPr``.

    ``gap_after_title`` (default benar) menambahkan satu paragraf kosong
    kanonis TNR 12 pt line 360 di dalam ``w:sdtContent`` tepat setelah
    paragraf judul, sehingga jarak judul ke entri sama dengan jarak setelah
    Heading1 bab. ``page_break_before`` menambahkan ``w:pageBreakBefore`` pada
    paragraf judul agar daftar dimulai di halaman baru; tidak ada paragraf
    page-break tambahan setelah ``w:sdt``.
    """

    if not isinstance(title, str) or not title.strip():
        raise FieldError("Judul TOC tidak boleh kosong")
    low, high = levels
    if not (1 <= low <= high <= 9):
        raise FieldError("levels TOC harus 1 <= low <= high <= 9")
    if caption is not None and not caption.strip():
        raise FieldError("Caption TOC tidak boleh kosong")

    body = _body(package)
    if not keep_existing:
        _remove_existing_toc(body, title.strip())

    if caption is None:
        switches: tuple[str, ...] = ("TOC", f'\\o "{low}-{high}"', "\\h", "\\z", "\\u")
    else:
        escaped = caption.replace('"', '\\"')
        switches = ("TOC", f'\\c "{escaped}"', "\\h", "\\z")

    sdt, field = _sdt_toc(
        title.strip(),
        switches,
        gap_after_title=gap_after_title,
        page_break_before=page_break_before,
    )

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
    return field


def insert_seq(
    package: object,
    *,
    paragraph: etree._Element,
    label: str,
) -> Field:
    """Tambahkan field ``SEQ <label>`` pada akhir paragraf."""

    if not isinstance(label, str) or not label.strip():
        raise FieldError("Label SEQ tidak boleh kosong")
    return insert_field(["SEQ", label.strip()], FieldPosition(paragraph=paragraph), "1")


def insert_pageref(
    package: object,
    *,
    paragraph: etree._Element,
    bookmark: str,
) -> Field:
    r"""Tambahkan field ``PAGEREF <bookmark> \h`` pada akhir paragraf."""

    if not isinstance(bookmark, str) or not bookmark.strip():
        raise FieldError("Nama bookmark PAGEREF tidak boleh kosong")
    return insert_field(
        ["PAGEREF", bookmark.strip(), "\\h"],
        FieldPosition(paragraph=paragraph),
        "0",
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


def ensure_no_blank_page_after_toc(package: DocumentPackage) -> int:
    """Bersihkan page-break kosong setelah setiap TOC ``w:sdt``."""

    body = _body(package)
    removed = 0
    for child in list(body):
        if child.tag != W_SDT:
            continue
        pr = child.find(W + "sdtPr")
        gallery = pr.find(".//" + qn("w:docPartGallery")) if pr is not None else None
        if gallery is None or gallery.get(W + "val") != _TOC_GALLERY:
            continue
        removed += _remove_blank_breaks_after(body, child)
    return removed


__all__ = [
    "EXEMPT_FIELDS",
    "SETTINGS_PART",
    "Field",
    "FieldError",
    "FieldKind",
    "FieldMarkerKind",
    "FieldPosition",
    "ensure_no_blank_page_after_toc",
    "field_has_result",
    "field_instruction",
    "field_kind",
    "field_marker_kind",
    "field_name",
    "field_result_text",
    "field_text_ranges",
    "has_exempt_field",
    "has_field",
    "insert_field",
    "insert_pageref",
    "insert_seq",
    "insert_toc",
    "is_bold_exempt",
    "is_field_run",
    "iter_field_instructions",
    "iter_field_markers",
    "iter_field_runs",
    "iter_fields",
    "iter_fields_in_paragraph",
    "iter_fields_in_part",
    "iter_fields_in_root",
    "strip_update_fields",
    "update_fields_enabled",
]
