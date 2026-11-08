#!/usr/bin/env python3
"""Sisipkan paragraf kosong fisik pada DOCX sesuai aturan tata letak laporan.

Spacing before/after pada style dihilangkan (lihat ``build_style.py``), lalu
jarak antarbagian dibuat eksplisit memakai paragraf kosong nyata. Aturan
posisi yang diterapkan (Opsi A):

- satu paragraf kosong setelah Heading1 (judul bab);
- satu paragraf kosong sebelum Heading2/Heading3 hanya bila blok sebelumnya
  berupa isi, tabel, atau gambar;
- nol paragraf kosong antara Heading2 yang langsung diikuti Heading3 tanpa
  isi (begitu pula antarheading lain tanpa isi);
- satu paragraf kosong sebelum tabel/gambar ber-caption;
- satu paragraf kosong setelah tabel/gambar;
- satu paragraf kosong sebelum dan sesudah paragraf persamaan display.

Paragraf kosong yang disisipkan memakai Times New Roman 12 pt, line 360
(1,5 baris), dan before/after 0. Alat ini idempoten dan aditif: paragraf
kosong yang sudah ada tidak diduplikasi maupun dihapus, sehingga menjalankan
dua kali menghasilkan ``word/document.xml`` yang sama.

Yang tidak disentuh:

- header, footer, dan part XML lain (hanya ``word/document.xml`` ditulis);
- isi daftar isi (style ``TOC1``–``TOC9``/``TOCHeading`` serta field ``TOC``);
- isi tabel, teks, run, style, section, field, dan bookmark.

Jalankan:

    python tools/insert_blank_lines.py --docx input.docx --out output.docx
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
from lxml.etree import _Element

DOCUMENT_PART = "word/document.xml"

EMPTY_FONT = "Times New Roman"
EMPTY_HALF_POINTS = 24  # 12 pt
EMPTY_LINE_TWIPS = 360  # 1,5 baris

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_RPR = qn("w:rPr")
W_PSTYLE = qn("w:pStyle")
W_SECTPR = qn("w:sectPr")
W_TBL = qn("w:tbl")
W_SDT = qn("w:sdt")
W_VAL = qn("w:val")
W_FLDCHAR = qn("w:fldChar")
W_FLDCHARTYPE = qn("w:fldCharType")
W_INSTRTEXT = qn("w:instrText")
W_FLDSIMPLE = qn("w:fldSimple")
W_INSTR = qn("w:instr")
W_DRAWING = qn("w:drawing")
W_PICT = qn("w:pict")
W_OBJECT = qn("w:object")
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_TAB = qn("w:tab")
W_FOOTNOTE_REFERENCE = qn("w:footnoteReference")
W_ENDNOTE_REFERENCE = qn("w:endnoteReference")
M_O_MATH_PARA = qn("m:oMathPara")
M_O_MATH = qn("m:oMath")

STYLE_ID_RE = re.compile(r"[^a-z0-9]+")
HEADING_STYLE_RE = re.compile(r"^heading([1-9])$")
TOC_STYLE_RE = re.compile(r"^toc[1-9]$|^tocheading$")
FIELD_NAME_RE = re.compile(r"\s*([A-Za-z]+)")
CAPTION_LABEL_RE = re.compile(r"^\s*(tabel|table|gambar|figure)\b", re.I)
EQUATION_NUMBER_RE = re.compile(r"\(\d+\.\d+\)")

CUSTOM_HEADING_STYLES = frozenset({"chaptertitle"})
COVER_PREFIX = "cover"

IMAGE_CAPTION_STYLES = frozenset({"imagecaption", "figurecaption"})
TABLE_CAPTION_STYLES = frozenset({"tablecaption"})
GENERIC_CAPTION_STYLES = frozenset({"caption"})

# Elemen non-visual di level body: tidak memutus blok maupun dihitung sebagai
# isi saat menentukan jarak.
IGNORED_BODY_TAGS = frozenset(
    {
        qn("w:bookmarkStart"),
        qn("w:bookmarkEnd"),
        qn("w:proofErr"),
        qn("w:commentRangeStart"),
        qn("w:commentRangeEnd"),
        qn("w:permStart"),
        qn("w:permEnd"),
    }
)

EMPTY = "empty"
IGNORE = "ignore"
CONTENT = "content"
TABLE = "table"
IMAGE = "image"
EQUATION = "equation"
H1 = "h1"
H2 = "h2"
H3 = "h3"
TOC = "toc"
COVER = "cover"
SECTION = "section"
SECTPR = "sectpr"
OTHER = "other"
CAPTION_TABLE = "caption_table"
CAPTION_IMAGE = "caption_image"


class InsertBlankLinesError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass
class BlankLineReport:
    """Ringkasan hasil penyisipan paragraf kosong."""

    blocks: int = 0
    inserted: int = 0
    after_h1: int = 0
    before_heading: int = 0
    before_object: int = 0
    after_object: int = 0
    empty_paragraphs: int = 0
    skipped_toc: int = 0
    skipped_cover: int = 0


@dataclass
class _Block:
    """Satu blok visual pada level ``w:body``."""

    kind: str
    start: int
    end: int
    element: _Element


# ---------------------------------------------------------------------------
# Pembacaan dan penulisan DOCX


def _read_document_xml(docx_path: Path) -> bytes:
    try:
        with zipfile.ZipFile(docx_path, "r") as archive:
            try:
                return archive.read(DOCUMENT_PART)
            except KeyError as exc:
                raise InsertBlankLinesError(
                    f"{docx_path} bukan DOCX valid: part {DOCUMENT_PART} tidak ada."
                ) from exc
    except FileNotFoundError as exc:
        raise InsertBlankLinesError(
            f"File input tidak ditemukan: {docx_path}"
        ) from exc
    except zipfile.BadZipFile as exc:
        raise InsertBlankLinesError(
            f"{docx_path} bukan arsip DOCX/ZIP yang valid."
        ) from exc
    except OSError as exc:
        raise InsertBlankLinesError(
            f"Tidak dapat membaca {docx_path}: {exc}"
        ) from exc


def _parse_document(document_xml: bytes) -> tuple[_Element, _Element]:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    try:
        root = etree.fromstring(document_xml, parser)
    except etree.XMLSyntaxError as exc:
        raise InsertBlankLinesError(
            f"XML {DOCUMENT_PART} tidak valid: {exc}"
        ) from exc

    body = root.find(W_BODY)
    if body is None:
        raise InsertBlankLinesError(
            f"{DOCUMENT_PART} tidak memiliki elemen w:body."
        )
    return root, body


def _write_docx(input_path: Path, output_path: Path, document_xml: bytes) -> None:
    """Tulis DOCX baru dengan mengganti document.xml saja."""

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
# Utilitas XML


def _normalize_style_id(style_id: str | None) -> str:
    return STYLE_ID_RE.sub("", (style_id or "").lower())


def _paragraph_style_id(paragraph: _Element) -> str | None:
    style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
    if style is None:
        return None
    return style.get(W_VAL)


def _paragraph_text(paragraph: _Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))


def _iter_field_instructions(paragraph: _Element) -> Iterator[str]:
    """Hasilkan instruksi field kompleks/sederhana di dalam paragraf."""

    stack: list[list[str]] = []

    def walk(element: _Element) -> Iterator[str]:
        for child in element:
            if child.tag in (W_P, qn("w:txbxContent")):
                continue
            if child.tag == W_FLDCHAR:
                field_type = child.get(W_FLDCHARTYPE)
                if field_type == "begin":
                    stack.append([])
                elif field_type == "end" and stack:
                    yield "".join(stack.pop())
            elif child.tag == W_INSTRTEXT:
                if stack:
                    stack[-1].append(child.text or "")
            elif child.tag == W_FLDSIMPLE:
                yield child.get(W_INSTR) or ""
            yield from walk(child)

    yield from walk(paragraph)
    for parts in stack:
        yield "".join(parts)


def _field_name(instruction: str) -> str | None:
    match = FIELD_NAME_RE.match(instruction)
    return match.group(1).upper() if match else None


def _has_toc_field(paragraph: _Element) -> bool:
    for instruction in _iter_field_instructions(paragraph):
        if _field_name(instruction) == "TOC":
            return True
    return False


def _is_empty_paragraph(paragraph: _Element) -> bool:
    """True bila paragraf tidak menampilkan teks, gambar, atau pemisah baris."""

    if paragraph.find(f"{W_PPR}/{W_SECTPR}") is not None:
        return False
    if _paragraph_text(paragraph).strip():
        return False
    if paragraph.find(f".//{W_TAB}") is not None:
        return False
    for tag in (
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_BR,
        W_CR,
        W_FLDCHAR,
        W_FLDSIMPLE,
        W_INSTRTEXT,
        W_FOOTNOTE_REFERENCE,
        W_ENDNOTE_REFERENCE,
    ):
        if paragraph.find(f".//{tag}") is not None:
            return False
    return True


def _has_image(paragraph: _Element) -> bool:
    return any(
        paragraph.find(f".//{tag}") is not None
        for tag in (W_DRAWING, W_PICT, W_OBJECT)
    )


def _is_equation_paragraph(paragraph: _Element) -> bool:
    """True bila paragraf berisi persamaan display, bukan prosa + math inline.

    Pandoc menulis persamaan display sebagai ``m:oMathPara``. Word dapat
    menyimpannya ulang sebagai ``m:oMath`` langsung di paragraf setelah
    finalisasi. Paragraf seperti itu dianggap persamaan jika teks non-matematik
    kosong atau hanya nomor ``(bab.n)``.
    """

    if paragraph.find(M_O_MATH_PARA) is not None:
        return True
    if paragraph.find(M_O_MATH) is None:
        return False
    text = _paragraph_text(paragraph).strip()
    return not text or EQUATION_NUMBER_RE.fullmatch(text) is not None


def _caption_kind(paragraph: _Element, style_id: str) -> str | None:
    if style_id in IMAGE_CAPTION_STYLES:
        return "image"
    if style_id in TABLE_CAPTION_STYLES:
        return "table"
    if style_id in GENERIC_CAPTION_STYLES:
        match = CAPTION_LABEL_RE.match(_paragraph_text(paragraph))
        if match is not None:
            label = match.group(1).lower()
            return "image" if label in {"gambar", "figure"} else "table"
    return None


def _sdt_is_toc(element: _Element) -> bool:
    for paragraph in element.iter(W_P):
        style_id = _normalize_style_id(_paragraph_style_id(paragraph))
        if TOC_STYLE_RE.fullmatch(style_id) or _has_toc_field(paragraph):
            return True
    return False


def _heading_level(style_id: str) -> int | None:
    if style_id in CUSTOM_HEADING_STYLES:
        return 1
    match = HEADING_STYLE_RE.fullmatch(style_id)
    if match is None:
        return None
    return int(match.group(1))


def _classify(element: _Element) -> str:
    """Klasifikasikan satu anak ``w:body``."""

    if element.tag == W_P:
        if element.find(f"{W_PPR}/{W_SECTPR}") is not None:
            return SECTION

        style_id = _normalize_style_id(_paragraph_style_id(element))
        level = _heading_level(style_id)
        if level is not None:
            return f"h{level}"
        if TOC_STYLE_RE.fullmatch(style_id) or _has_toc_field(element):
            return TOC
        if style_id.startswith(COVER_PREFIX):
            return COVER
        if _has_image(element):
            return IMAGE
        if _is_equation_paragraph(element):
            return EQUATION
        if _is_empty_paragraph(element):
            return EMPTY
        caption = _caption_kind(element, style_id)
        if caption == "table":
            return CAPTION_TABLE
        if caption == "image":
            return CAPTION_IMAGE
        return CONTENT

    if element.tag == W_TBL:
        return TABLE
    if element.tag == W_SECTPR:
        return SECTPR
    if element.tag == W_SDT:
        return TOC if _sdt_is_toc(element) else OTHER
    if element.tag in IGNORED_BODY_TAGS:
        return IGNORE
    return OTHER


# ---------------------------------------------------------------------------
# Penyusunan blok


def _build_blocks(children: Sequence[_Element], kinds: Sequence[str]) -> list[_Block]:
    """Gabungkan caption dengan tabel/gambar agar jarak tidak jatuh di tengah."""

    blocks: list[_Block] = []
    index = 0
    total = len(children)

    while index < total:
        kind = kinds[index]

        if kind in (EMPTY, IGNORE):
            index += 1
            continue

        if kind == CAPTION_TABLE:
            if index + 1 < total and kinds[index + 1] == TABLE:
                blocks.append(_Block(TABLE, index, index + 1, children[index]))
                index += 2
                continue
            blocks.append(_Block(CONTENT, index, index, children[index]))
            index += 1
            continue

        if kind == TABLE:
            end = index
            cursor = index + 1
            # Dukung caption tabel di bawah tabel (gaya Inggris); gaya
            # Indonesia menaruh caption di atas dan ditangani cabang di atas.
            if cursor < total and kinds[cursor] == CAPTION_TABLE:
                end = cursor
            blocks.append(_Block(TABLE, index, end, children[index]))
            index = end + 1
            continue

        if kind == IMAGE:
            end = index
            cursor = index + 1
            while cursor < total and kinds[cursor] == CAPTION_IMAGE:
                end = cursor
                cursor += 1
            blocks.append(_Block(IMAGE, index, end, children[index]))
            index = end + 1
            continue

        if kind == CAPTION_IMAGE:
            # Caption gambar di atas gambar (jarang) tetap dianggap satu blok.
            if index + 1 < total and kinds[index + 1] == IMAGE:
                end = index + 1
                cursor = end + 1
                while cursor < total and kinds[cursor] == CAPTION_IMAGE:
                    end = cursor
                    cursor += 1
                blocks.append(_Block(IMAGE, index, end, children[index]))
                index = end + 1
                continue
            # Caption tanpa gambar di dekatnya diperlakukan sebagai isi.
            blocks.append(_Block(CONTENT, index, index, children[index]))
            index += 1
            continue

        blocks.append(_Block(kind, index, index, children[index]))
        index += 1

    return blocks


def _desired_gap(previous: _Block | None, current: _Block) -> int:
    """Jumlah paragraf kosong yang seharusnya ada sebelum ``current``."""

    if current.kind in (TOC, COVER, SECTION, SECTPR, OTHER):
        return 0

    if current.kind in (H2, H3):
        if previous is None:
            return 0
        if previous.kind in (CONTENT, TABLE, IMAGE, EQUATION):
            return 1
        if previous.kind == H1:
            return 1
        return 0

    if current.kind == H1:
        if previous is not None and previous.kind in (TABLE, IMAGE, EQUATION):
            return 1
        return 0

    if current.kind in (TABLE, IMAGE, EQUATION):
        if previous is None:
            return 0
        if previous.kind in (TOC, COVER, SECTION, SECTPR, OTHER):
            return 0
        return 1

    # Blok isi biasa.
    if previous is not None and previous.kind == H1:
        return 1
    if previous is not None and previous.kind in (TABLE, IMAGE, EQUATION):
        return 1
    return 0


def _gap_reason(previous: _Block | None, current: _Block) -> str:
    if (
        current.kind in (H2, H3)
        and previous is not None
        and previous.kind in (CONTENT, TABLE, IMAGE, EQUATION)
    ):
        return "before_heading"
    if previous is not None and previous.kind == H1:
        return "after_h1"
    if current.kind in (TABLE, IMAGE, EQUATION):
        return "before_object"
    if previous is not None and previous.kind in (TABLE, IMAGE, EQUATION):
        return "after_object"
    return "other"


def _make_empty_paragraph() -> _Element:
    """Buat paragraf kosong TNR 12 pt, line 360, before/after 0."""

    paragraph = OxmlElement("w:p")
    properties = OxmlElement("w:pPr")

    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), str(EMPTY_LINE_TWIPS))
    spacing.set(qn("w:lineRule"), "auto")
    properties.append(spacing)

    run_properties = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attribute), EMPTY_FONT)
    run_properties.append(fonts)

    for tag in ("w:sz", "w:szCs"):
        size = OxmlElement(tag)
        size.set(W_VAL, str(EMPTY_HALF_POINTS))
        run_properties.append(size)

    properties.append(run_properties)
    paragraph.append(properties)
    return paragraph


# ---------------------------------------------------------------------------
# API utama


def insert_blank_lines(
    docx_path: str | Path, out_docx: str | Path
) -> BlankLineReport:
    """Sisipkan paragraf kosong dari ``docx_path`` ke ``out_docx``."""

    input_path = Path(docx_path)
    output_path = Path(out_docx)

    document_xml = _read_document_xml(input_path)
    root, body = _parse_document(document_xml)

    children = list(body)
    kinds = [_classify(child) for child in children]
    blocks = _build_blocks(children, kinds)

    report = BlankLineReport(blocks=len(blocks))
    report.skipped_toc = sum(1 for kind in kinds if kind == TOC)
    report.skipped_cover = sum(1 for kind in kinds if kind == COVER)

    insertions: list[tuple[_Element, int, str]] = []
    previous: _Block | None = None
    for current in blocks:
        wanted = _desired_gap(previous, current)
        if wanted <= 0:
            previous = current
            continue

        actual = sum(
            1 for index in range(previous.end + 1, current.start)
            if kinds[index] == EMPTY
        ) if previous is not None else 0
        needed = wanted - actual
        if needed > 0:
            insertions.append(
                (current.element, needed, _gap_reason(previous, current))
            )
        previous = current

    for element, count, reason in insertions:
        for _ in range(count):
            element.addprevious(_make_empty_paragraph())
        report.inserted += count
        if reason == "after_h1":
            report.after_h1 += count
        elif reason == "before_heading":
            report.before_heading += count
        elif reason == "before_object":
            report.before_object += count
        elif reason == "after_object":
            report.after_object += count

    if insertions:
        revised_xml = etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
    else:
        # Tidak ada perubahan: tulis byte asli agar idempoten sempurna.
        revised_xml = document_xml

    report.empty_paragraphs = sum(
        1 for child in body if child.tag == W_P and _is_empty_paragraph(child)
    )

    _write_docx(input_path, output_path, revised_xml)
    return report


def _summary(report: BlankLineReport) -> str:
    return "\n".join(
        (
            f"Blok diperiksa: {report.blocks}",
            f"Paragraf kosong disisipkan: {report.inserted}",
            f"  setelah Heading1: {report.after_h1}",
            f"  sebelum Heading2/3: {report.before_heading}",
            f"  sebelum tabel/gambar/persamaan: {report.before_object}",
            f"  setelah tabel/gambar/persamaan: {report.after_object}",
            f"Paragraf kosong total: {report.empty_paragraphs}",
            f"Paragraf TOC diabaikan: {report.skipped_toc}",
            f"Paragraf cover diabaikan: {report.skipped_cover}",
        )
    )


# ---------------------------------------------------------------------------
# CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sisipkan paragraf kosong TNR 12 pt (line 360, before/after 0) "
            "setelah Heading1, sebelum Heading2/3 berisi konteks, serta di "
            "sekitar tabel/gambar/persamaan."
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
        report = insert_blank_lines(args.docx, args.out)
    except (InsertBlankLinesError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_summary(report))
    print(f"DOCX: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
