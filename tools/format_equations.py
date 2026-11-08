"""Beri nomor persamaan display DOCX (OMML) per bab.

Alat ini mencari paragraf persamaan display OMML (``m:oMathPara``, atau
``m:oMath`` yang berdiri sendiri tanpa prosa selain nomor). Untuk setiap
paragraf tersebut, alat menambahkan tab stop kanan pada tepi kanan area teks,
run teks ``(bab.n)`` setelah persamaan, indentasi kiri 1440 twip (dua tab
default), dan spasi sebelum/sesudah 0 twip. Jarak vertikal di sekitar
persamaan dibuat memakai paragraf kosong oleh ``tools/insert_blank_lines.py``,
sesuai aturan tanpa spacing before/after.

Nomor bab diambil dari Heading1 terakhir yang berformat ``BAB <romawi/arab>``.
Counter persamaan dimulai dari 1 pada setiap bab dan direset ketika Heading1
``BAB ...`` baru ditemukan. Isi OMML tidak diubah; nomor ditulis sebagai run
``w:r`` terpisah di luar ``m:oMathPara``.

Hanya ``word/document.xml`` yang ditulis ulang. Part lain (header, footer,
style, numbering, media, relasi, dan section) disalin byte-per-byte dari DOCX
asli. Field, bookmark, dan section properties tidak dihapus atau diubah.

Jalankan:

    python tools/format_equations.py --docx input.docx --out output.docx

Posisi pipeline: jalankan **setelah** ``tools/normalize_layout.py`` (dan
``tools/format_code.py``). Urutan ini penting agar ``normalize_layout.py``
tidak menimpa spacing 0 twip dan ``w:jc="left"`` yang disetel alat ini.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
from lxml.etree import _Element

DOCUMENT_PART = "word/document.xml"

M_O_MATH_PARA = qn("m:oMathPara")
M_O_MATH = qn("m:oMath")

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_R = qn("w:r")
W_RPR = qn("w:rPr")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_PTAB = qn("w:ptab")
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_NO_BREAK_HYPHEN = qn("w:noBreakHyphen")
W_SPACING = qn("w:spacing")
W_IND = qn("w:ind")
W_JC = qn("w:jc")
W_VAL = qn("w:val")
W_POS = qn("w:pos")
W_W = qn("w:w")
W_LEFT = qn("w:left")
W_RIGHT = qn("w:right")
W_GUTTER = qn("w:gutter")
W_FIRST_LINE = qn("w:firstLine")
W_HANGING = qn("w:hanging")
W_LEFT_CHARS = qn("w:leftChars")
W_FIRST_LINE_CHARS = qn("w:firstLineChars")
W_HANGING_CHARS = qn("w:hangingChars")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_BEFORE_LINES = qn("w:beforeLines")
W_AFTER_LINES = qn("w:afterLines")
W_BEFORE_AUTO = qn("w:beforeAutospacing")
W_AFTER_AUTO = qn("w:afterAutospacing")
W_PG_SZ = qn("w:pgSz")
W_PG_MAR = qn("w:pgMar")
W_SECT_PR = qn("w:sectPr")
W_FLD_CHAR = qn("w:fldChar")
W_FLD_SIMPLE = qn("w:fldSimple")
W_INSTR_TEXT = qn("w:instrText")
W_DEL_TEXT = qn("w:delText")
W_DEL = qn("w:del")
W_MOVE_FROM = qn("w:moveFrom")
W_DRAWING = qn("w:drawing")
W_PICT = qn("w:pict")
W_OBJECT = qn("w:object")
W_TXBX_CONTENT = qn("w:txbxContent")

# Urutan anak w:pPr menurut schema OOXML. Elemen baru disisipkan pada posisi
# yang benar supaya Word tidak menganggap dokumen rusak.
PPR_ORDER = tuple(
    qn(tag)
    for tag in (
        "w:pStyle",
        "w:keepNext",
        "w:keepLines",
        "w:pageBreakBefore",
        "w:framePr",
        "w:widowControl",
        "w:numPr",
        "w:suppressLineNumbers",
        "w:pBdr",
        "w:shd",
        "w:tabs",
        "w:suppressAutoHyphens",
        "w:kinsoku",
        "w:wordWrap",
        "w:overflowPunct",
        "w:topLinePunct",
        "w:autoSpaceDE",
        "w:autoSpaceDN",
        "w:bidi",
        "w:adjustRightInd",
        "w:snapToGrid",
        "w:spacing",
        "w:ind",
        "w:contextualSpacing",
        "w:mirrorIndents",
        "w:suppressOverlap",
        "w:jc",
        "w:textDirection",
        "w:textAlignment",
        "w:textboxTightWrap",
        "w:outlineLvl",
        "w:divId",
        "w:cnfStyle",
        "w:rPr",
        "w:sectPr",
        "w:pPrChange",
    )
)

HEADING1_STYLES = frozenset({"heading1"})
BAB_RE = re.compile(
    r"^\s*BAB\s+(?P<number>[IVXLCDM]+|\d+)(?=\s|[.:;,\-–—]|$)",
    re.IGNORECASE,
)
EQUATION_NUMBER_RE = re.compile(r"\(\d+\.\d+\)")

ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

# Dua tab default = 2 x 720 twip. Nilai ini dipakai untuk indentasi kiri
# persamaan sesuai panduan ("menjorok ke kanan 2 tabulasi").
EQUATION_LEFT_INDENT_TWIPS = 1440

# Spasi sebelum/sesudah. Aturan dokumen: tidak ada spacing before/after.
# Jarak antarbagian dibuat memakai paragraf kosong fisik (insert_blank_lines).
EQUATION_SPACING_TWIPS = 0

# Rata kiri (bukan justify) agar tab kanan dan nomor (bab.n) tetap pada
# posisinya; w:jc=both akan membuat Word ikut meregangkan baris persamaan.
EQUATION_JUSTIFICATION = "left"

# Fallback bila geometri section tidak terbaca: 9072 twip = 16,0 cm.
# Nilai sebenarnya dihitung dari lebar halaman dikurangi margin kiri/kanan
# dan gutter pada sectPr terakhir.
DEFAULT_RIGHT_TAB_TWIPS = 9072

TEXT_SKIP_TAGS = frozenset(
    {
        W_PPR,
        W_P,
        W_TXBX_CONTENT,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_INSTR_TEXT,
        W_FLD_CHAR,
        W_FLD_SIMPLE,
        W_DEL,
        W_MOVE_FROM,
        W_DEL_TEXT,
    }
)

FIELD_TAGS = frozenset({W_FLD_CHAR, W_FLD_SIMPLE, W_INSTR_TEXT})


class FormatEquationsError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass
class FormatEquationsReport:
    """Ringkasan pekerjaan yang dilakukan beserta peringatan yang muncul."""

    heading1_count: int = 0
    bab_headings: int = 0
    equation_paragraphs: int = 0
    numbered: int = 0
    skipped_no_chapter: int = 0
    skipped_field: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "heading1_count": self.heading1_count,
            "bab_headings": self.bab_headings,
            "equation_paragraphs": self.equation_paragraphs,
            "numbered": self.numbered,
            "skipped_no_chapter": self.skipped_no_chapter,
            "skipped_field": self.skipped_field,
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Pembacaan dan penulisan DOCX


def _read_document_xml(docx_path: Path) -> bytes:
    try:
        with zipfile.ZipFile(docx_path, "r") as archive:
            try:
                return archive.read(DOCUMENT_PART)
            except KeyError as exc:
                raise FormatEquationsError(
                    f"{docx_path} bukan DOCX valid: part {DOCUMENT_PART} tidak ada."
                ) from exc
    except FileNotFoundError as exc:
        raise FormatEquationsError(f"File input tidak ditemukan: {docx_path}") from exc
    except zipfile.BadZipFile as exc:
        raise FormatEquationsError(
            f"{docx_path} bukan arsip DOCX/ZIP yang valid."
        ) from exc
    except OSError as exc:
        raise FormatEquationsError(f"Tidak dapat membaca {docx_path}: {exc}") from exc


def _parse_document(document_xml: bytes) -> tuple[_Element, _Element]:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    try:
        root = etree.fromstring(document_xml, parser)
    except etree.XMLSyntaxError as exc:
        raise FormatEquationsError(
            f"XML {DOCUMENT_PART} tidak valid: {exc}"
        ) from exc

    body = root.find(W_BODY)
    if body is None:
        raise FormatEquationsError(f"{DOCUMENT_PART} tidak memiliki elemen w:body.")
    return root, body


def _write_docx(input_path: Path, output_path: Path, document_xml: bytes) -> None:
    """Tulis DOCX baru dengan mengganti document.xml saja.

    Semua part lain disalin dari ZIP asli tanpa parsing ulang agar header,
    footer, style, numbering, media, dan relasi tetap identik.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    temp_path = Path(temp_name)

    try:
        with zipfile.ZipFile(input_path, "r") as source, zipfile.ZipFile(
            temp_path, "w"
        ) as target:
            target.comment = source.comment
            for info in source.infolist():
                data = (
                    document_xml
                    if info.filename == DOCUMENT_PART
                    else source.read(info.filename)
                )
                new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.comment = info.comment
                new_info.extra = info.extra
                new_info.internal_attr = info.internal_attr
                new_info.external_attr = info.external_attr
                new_info.create_system = info.create_system
                target.writestr(new_info, data)
        os.replace(temp_path, output_path)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Utilitas XML dan teks


def _normalize_style_id(style_id: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (style_id or "").lower())


def _paragraph_style_id(paragraph: _Element) -> str | None:
    style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
    if style is None:
        return None
    return style.get(W_VAL)


def _get_or_add_ppr(paragraph: _Element) -> _Element:
    ppr = paragraph.find(W_PPR)
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        paragraph.insert(0, ppr)
    return ppr


def _insert_ordered(
    parent: _Element, element: _Element, order: Sequence[str]
) -> None:
    try:
        target_index = order.index(element.tag)
    except ValueError:
        parent.append(element)
        return

    for index, child in enumerate(parent):
        try:
            child_index = order.index(child.tag)
        except ValueError:
            continue
        if child_index > target_index:
            parent.insert(index, element)
            return
    parent.append(element)


def _get_or_add_child(
    parent: _Element, nsptag: str, order: Sequence[str]
) -> _Element:
    tag = qn(nsptag)
    existing = parent.find(tag)
    if existing is not None:
        return existing
    element = OxmlElement(nsptag)
    _insert_ordered(parent, element, order)
    return element


def _paragraph_text(paragraph: _Element) -> str:
    """Teks paragraf untuk deteksi Heading1, tanpa isi OMML/text box."""

    parts: list[str] = []

    def walk(element: _Element) -> None:
        for child in element:
            tag = child.tag
            if tag == W_T:
                parts.append(child.text or "")
            elif tag in (W_TAB, W_PTAB):
                parts.append("\t")
            elif tag in (W_BR, W_CR):
                parts.append("\n")
            elif tag == W_NO_BREAK_HYPHEN:
                parts.append("\u2011")
            elif tag in TEXT_SKIP_TAGS:
                continue
            else:
                walk(child)

    walk(paragraph)
    return "".join(parts)


def _iter_paragraphs(body: _Element) -> Iterator[_Element]:
    """Iterasi paragraf body dan sel tabel, kecuali isi text box."""

    for paragraph in body.iter(W_P):
        parent = paragraph.getparent()
        inside_textbox = False
        while parent is not None and parent is not body:
            if parent.tag == W_TXBX_CONTENT:
                inside_textbox = True
                break
            parent = parent.getparent()
        if not inside_textbox:
            yield paragraph


# ---------------------------------------------------------------------------
# Deteksi bab dan persamaan


def _roman_to_int(token: str) -> int | None:
    total = 0
    previous = 0
    for character in reversed(token.upper()):
        value = ROMAN_VALUES.get(character)
        if value is None:
            return None
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total or None


def _chapter_number(text: str) -> int | None:
    match = BAB_RE.match(text)
    if match is None:
        return None
    token = match.group("number")
    if token.isdigit():
        return int(token)
    return _roman_to_int(token)


def _display_equation(paragraph: _Element) -> _Element | None:
    """Kembalikan elemen persamaan display anak langsung ``w:p``.

    Pandoc menulis persamaan display sebagai ``m:oMathPara``. Setelah Word
    menyimpan ulang dokumen (mis. saat finalisasi field), persamaan yang
    paragrafnya juga memuat tab dan nomor dapat dinormalkan menjadi
    ``m:oMath`` biasa. Paragraf seperti itu tetap dianggap persamaan display
    bila teks non-matematikanya kosong atau hanya berupa nomor ``(bab.n)``;
    persamaan inline di tengah prosa tidak ikut diproses.
    """

    equations = paragraph.findall(M_O_MATH_PARA)
    if equations:
        return equations[-1]

    equations = paragraph.findall(M_O_MATH)
    if not equations:
        return None
    text = _paragraph_text(paragraph).strip()
    if text and EQUATION_NUMBER_RE.fullmatch(text) is None:
        return None
    return equations[-1]


def _has_field(paragraph: _Element) -> bool:
    """True bila paragraf memuat field; paragraf seperti ini dilewati."""

    for element in paragraph.iter():
        if element.tag in FIELD_TAGS:
            return True
    return False


def _int_attribute(element: _Element, name: str) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _content_width(body: _Element) -> int:
    """Lebar area teks dari sectPr terakhir, fallback 9072 twip."""

    section = body.find(W_SECT_PR)
    if section is None:
        sections = body.findall(f".//{W_SECT_PR}")
        section = sections[-1] if sections else None
    if section is None:
        return DEFAULT_RIGHT_TAB_TWIPS

    page_size = section.find(W_PG_SZ)
    page_margin = section.find(W_PG_MAR)
    if page_size is None or page_margin is None:
        return DEFAULT_RIGHT_TAB_TWIPS

    width = _int_attribute(page_size, W_W)
    left = _int_attribute(page_margin, W_LEFT)
    right = _int_attribute(page_margin, W_RIGHT)
    if width is None or left is None or right is None:
        return DEFAULT_RIGHT_TAB_TWIPS
    gutter = _int_attribute(page_margin, W_GUTTER) or 0

    content_width = width - left - right - gutter
    return content_width if content_width > 0 else DEFAULT_RIGHT_TAB_TWIPS


# ---------------------------------------------------------------------------
# Format paragraf persamaan


def _set_right_tab(ppr: _Element, position: int) -> None:
    tabs = _get_or_add_child(ppr, "w:tabs", PPR_ORDER)
    for tab in list(tabs.findall(W_TAB)):
        if tab.get(W_POS) == str(position):
            tabs.remove(tab)

    tab = OxmlElement("w:tab")
    tab.set(W_VAL, "right")
    tab.set(W_POS, str(position))
    tabs.append(tab)


def _set_spacing(ppr: _Element) -> None:
    spacing = _get_or_add_child(ppr, "w:spacing", PPR_ORDER)
    spacing.set(W_BEFORE, str(EQUATION_SPACING_TWIPS))
    spacing.set(W_AFTER, str(EQUATION_SPACING_TWIPS))
    for attribute in (W_BEFORE_LINES, W_AFTER_LINES, W_BEFORE_AUTO, W_AFTER_AUTO):
        spacing.attrib.pop(attribute, None)


def _set_indent(ppr: _Element) -> None:
    indent = _get_or_add_child(ppr, "w:ind", PPR_ORDER)
    indent.set(W_LEFT, str(EQUATION_LEFT_INDENT_TWIPS))
    # Normal style memakai first-line indent 1,25 cm. Untuk persamaan,
    # indentasi itu harus dinolkan agar persamaan benar-benar mulai dua tab
    # dari margin, bukan dua tab ditambah indentasi baris pertama.
    indent.set(W_FIRST_LINE, "0")
    for attribute in (W_LEFT_CHARS, W_FIRST_LINE_CHARS, W_HANGING, W_HANGING_CHARS):
        indent.attrib.pop(attribute, None)


def _set_justification(ppr: _Element) -> None:
    justification = _get_or_add_child(ppr, "w:jc", PPR_ORDER)
    justification.set(W_VAL, EQUATION_JUSTIFICATION)


def _run_number_text(run: _Element) -> str | None:
    """Teks nomor pada run, atau None bila run bukan run nomor persamaan."""

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


def _rebuild_number_run(run: _Element, number: str) -> None:
    properties = run.find(W_RPR)
    for child in list(run):
        if child is not properties:
            run.remove(child)

    run.append(OxmlElement("w:tab"))
    text_node = OxmlElement("w:t")
    text_node.text = number
    run.append(text_node)


def _set_number_run(
    paragraph: _Element, equation: _Element, number: str
) -> None:
    """Tambahkan/ganti run nomor setelah persamaan tanpa menyentuh OMML."""

    start = paragraph.index(equation) + 1
    siblings = list(paragraph)
    existing = [
        child
        for child in siblings[start:]
        if child.tag == W_R and _run_number_text(child) is not None
    ]

    if existing:
        primary = existing[0]
        _rebuild_number_run(primary, number)
        for duplicate in existing[1:]:
            paragraph.remove(duplicate)
        return

    run = OxmlElement("w:r")
    run.append(OxmlElement("w:tab"))
    text_node = OxmlElement("w:t")
    text_node.text = number
    run.append(text_node)
    equation.addnext(run)


def _format_equation_paragraph(
    paragraph: _Element,
    equation: _Element,
    number: str,
    content_width: int,
) -> None:
    ppr = _get_or_add_ppr(paragraph)
    _set_right_tab(ppr, content_width)
    _set_spacing(ppr)
    _set_indent(ppr)
    _set_justification(ppr)
    _set_number_run(paragraph, equation, number)


# ---------------------------------------------------------------------------
# API dan CLI


def _apply_numbers(body: _Element, report: FormatEquationsReport) -> None:
    content_width = _content_width(body)
    current_chapter: int | None = None
    counter = 0

    for paragraph in _iter_paragraphs(body):
        style_id = _paragraph_style_id(paragraph)

        if _normalize_style_id(style_id) in HEADING1_STYLES:
            report.heading1_count += 1
            chapter = _chapter_number(_paragraph_text(paragraph))
            if chapter is not None:
                report.bab_headings += 1
                current_chapter = chapter
                counter = 0
            continue

        equation = _display_equation(paragraph)
        if equation is None:
            continue

        report.equation_paragraphs += 1
        if current_chapter is None:
            report.skipped_no_chapter += 1
            continue

        # Counter tetap maju untuk paragraf equation yang dilewati karena
        # field, supaya nomor persamaan berikutnya sesuai urutan dokumen.
        counter += 1

        if _has_field(paragraph):
            report.skipped_field += 1
            continue

        number = f"({current_chapter}.{counter})"
        _format_equation_paragraph(paragraph, equation, number, content_width)
        report.numbered += 1


def _add_warnings(report: FormatEquationsReport) -> None:
    if report.bab_headings == 0:
        if report.heading1_count == 0:
            report.warnings.append(
                "Tidak ada paragraf Heading1; penomoran persamaan dilewati."
            )
        else:
            report.warnings.append(
                "Tidak ada Heading1 berformat 'BAB <romawi/arab>'; "
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
    docx_path: str | Path, out_docx: str | Path
) -> FormatEquationsReport:
    """Beri nomor persamaan display dari ``docx_path`` ke ``out_docx``."""

    input_path = Path(docx_path)
    output_path = Path(out_docx)

    document_xml = _read_document_xml(input_path)
    root, body = _parse_document(document_xml)

    report = FormatEquationsReport()
    _apply_numbers(body, report)
    _add_warnings(report)

    revised_xml = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    _write_docx(input_path, output_path, revised_xml)
    return report


def _summary(report: FormatEquationsReport) -> str:
    lines = [
        f"Persamaan display ditemukan: {report.equation_paragraphs}",
        f"Persamaan diberi nomor: {report.numbered}",
        f"Bab terdeteksi: {report.bab_headings}",
    ]
    if report.skipped_no_chapter:
        lines.append(f"Persamaan tanpa bab: {report.skipped_no_chapter}")
    if report.skipped_field:
        lines.append(f"Persamaan dengan field: {report.skipped_field}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Beri nomor persamaan display OMML DOCX per bab: (bab.n) di tepi "
            "kanan, indentasi dua tab, dan spasi before/after 0 twip."
        )
    )
    parser.add_argument("--docx", type=Path, required=True, help="file DOCX input")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="lokasi DOCX hasil (boleh sama dengan input)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        report = format_equations(args.docx, args.out)
    except (FormatEquationsError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_summary(report))
    for warning in report.warnings:
        print(f"PERINGATAN: {warning}", file=sys.stderr)
    print(f"DOCX: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
