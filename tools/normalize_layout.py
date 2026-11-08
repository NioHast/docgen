"""Normalisasi layout paragraf DOCX: spasi 1,5 baris dan rata kanan-kiri.

Alat ini menetapkan properti paragraf langsung (direct formatting) untuk semua
paragraf body dan sel tabel:

- ``w:spacing/@w:before = 0`` dan ``@w:after = 0``;
- ``w:spacing/@w:line = 360`` dengan ``@w:lineRule = auto`` (1,5 baris);
- ``w:jc/@w:val = both`` (justify);
- menghapus bold langsung (``w:b``/``w:bCs``) dari run body, daftar, semua sel
  tabel (termasuk baris header), dan seluruh style cover kecuali
  ``CoverTitle``. Paragraf ber-style heading dan judul sampul ``CoverTitle``
  dipertahankan bold;
- mempertahankan perataan kanan langsung (``w:jc="right"``) saat spacing
  paragraf dinolkan, alih-alih memaksanya menjadi justify.

Paragraf dengan style blok kode, caption, heading (``Heading1``–``Heading9``
dan style heading kustom seperti ``ChapterTitle``), daftar isi, cover selain
field cover yang disebut di atas, ``Title``, atau yang memuat field
TOC/PAGEREF/SEQ tidak disentuh sama sekali.
Teks, run, style, section, field, dan bookmark tidak diubah; hanya
``word/document.xml`` yang ditulis ulang, sedangkan part lain disalin
byte-per-byte dari DOCX asli.

Jalankan:

    python tools/normalize_layout.py --docx input.docx --out output.docx
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

LINE_SPACING_TWIPS = 360  # 1,5 baris (1,5 x 240 twip)
JUSTIFICATION = "both"

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_R = qn("w:r")
W_RPR = qn("w:rPr")
W_B = qn("w:b")
W_BCS = qn("w:bCs")
W_PSTYLE = qn("w:pStyle")
W_SPACING = qn("w:spacing")
W_JC = qn("w:jc")
W_VAL = qn("w:val")
W_BEFORE = qn("w:before")
W_AFTER = qn("w:after")
W_LINE = qn("w:line")
W_LINE_RULE = qn("w:lineRule")
W_BEFORE_LINES = qn("w:beforeLines")
W_AFTER_LINES = qn("w:afterLines")
W_BEFORE_AUTO = qn("w:beforeAutospacing")
W_AFTER_AUTO = qn("w:afterAutospacing")
W_FLDCHAR = qn("w:fldChar")
W_FLDCHARTYPE = qn("w:fldCharType")
W_INSTRTEXT = qn("w:instrText")
W_FLDSIMPLE = qn("w:fldSimple")
W_INSTR = qn("w:instr")
W_TXBXCONTENT = qn("w:txbxContent")

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

# Style yang tidak boleh disentuh. Perbandingan memakai styleId yang
# dinormalisasi: huruf kecil, tanpa spasi/tanda hubung/garis bawah.
CODE_STYLES = frozenset(
    {
        "sourcecode",
        "verbatimchar",
        "htmlcode",
        "htmlpreformatted",
    }
)
CAPTION_STYLES = frozenset({"imagecaption", "tablecaption"})
FIGURE_STYLES = frozenset({"figure", "captionedfigure", "figurecaption"})
TOC_STYLE_RE = re.compile(r"^toc[1-9]$|^tocheading$")
HEADING_STYLE_RE = re.compile(r"^heading[1-9]$")
CUSTOM_HEADING_STYLES = frozenset({"chaptertitle"})
COVER_PREFIX = "cover"
TITLE_STYLE = "title"

# Seluruh paragraf cover tetap dikecualikan dari spacing/justify, tetapi bold
# langsungnya dihapus kecuali pada judul sampul CoverTitle.
COVER_TITLE_STYLE = "covertitle"

# Field yang membuat paragrafnya dikecualikan dari normalisasi.
EXEMPT_FIELDS = frozenset({"TOC", "PAGEREF", "SEQ"})

STYLE_ID_RE = re.compile(r"[^a-z0-9]+")
FIELD_NAME_RE = re.compile(r"\s*([A-Za-z]+)")


class NormalizeLayoutError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass
class LayoutReport:
    """Ringkasan hasil normalisasi."""

    paragraphs: int = 0
    normalized: int = 0
    unchanged: int = 0
    skipped_style: int = 0
    skipped_field: int = 0
    bold_paragraphs: int = 0
    bold_runs_removed: int = 0


# ---------------------------------------------------------------------------
# Pembacaan dan penulisan DOCX


def _read_document_xml(docx_path: Path) -> bytes:
    try:
        with zipfile.ZipFile(docx_path, "r") as archive:
            try:
                return archive.read(DOCUMENT_PART)
            except KeyError as exc:
                raise NormalizeLayoutError(
                    f"{docx_path} bukan DOCX valid: part {DOCUMENT_PART} tidak ada."
                ) from exc
    except FileNotFoundError as exc:
        raise NormalizeLayoutError(f"File input tidak ditemukan: {docx_path}") from exc
    except zipfile.BadZipFile as exc:
        raise NormalizeLayoutError(
            f"{docx_path} bukan arsip DOCX/ZIP yang valid."
        ) from exc
    except OSError as exc:
        raise NormalizeLayoutError(f"Tidak dapat membaca {docx_path}: {exc}") from exc


def _parse_document(document_xml: bytes) -> tuple[_Element, _Element]:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    try:
        root = etree.fromstring(document_xml, parser)
    except etree.XMLSyntaxError as exc:
        raise NormalizeLayoutError(
            f"XML {DOCUMENT_PART} tidak valid: {exc}"
        ) from exc

    body = root.find(W_BODY)
    if body is None:
        raise NormalizeLayoutError(f"{DOCUMENT_PART} tidak memiliki elemen w:body.")
    return root, body


def _write_docx(input_path: Path, output_path: Path, document_xml: bytes) -> None:
    """Tulis DOCX baru dengan mengganti document.xml saja.

    Part lain disalin dari ZIP asli tanpa parsing ulang agar header, footer,
    style, numbering, media, dan relasi tetap identik.
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
# Utilitas XML


def _normalize_style_id(style_id: str | None) -> str:
    return STYLE_ID_RE.sub("", (style_id or "").lower())


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


# ---------------------------------------------------------------------------
# Deteksi pengecualian


def _has_exempt_style(style_id: str | None) -> bool:
    normalized = _normalize_style_id(style_id)
    if not normalized:
        return False
    if normalized in CODE_STYLES or normalized in CAPTION_STYLES:
        return True
    if normalized in FIGURE_STYLES:
        return True
    if normalized in CUSTOM_HEADING_STYLES:
        return True
    if normalized == TITLE_STYLE or normalized.startswith(COVER_PREFIX):
        return True
    if HEADING_STYLE_RE.fullmatch(normalized) is not None:
        return True
    return TOC_STYLE_RE.fullmatch(normalized) is not None


def _has_cover_bold_to_strip(style_id: str | None) -> bool:
    """True untuk paragraf cover yang bold langsungnya harus dihapus.

    Semua style ``Cover*`` kehilangan bold langsung kecuali ``CoverTitle``.
    """

    normalized = _normalize_style_id(style_id)
    return normalized.startswith(COVER_PREFIX) and normalized != COVER_TITLE_STYLE


def _iter_field_markers(paragraph: _Element) -> Iterator[_Element]:
    """Iterasi fldChar/instrText/fldSimple secara berurutan.

    Paragraf bersarang (text box) dilewati karena bukan bagian dari field
    paragraf ini.
    """

    def walk(element: _Element) -> Iterator[_Element]:
        for child in element:
            tag = child.tag
            if tag in (W_P, W_TXBXCONTENT):
                continue
            if tag in (W_FLDCHAR, W_INSTRTEXT, W_FLDSIMPLE):
                yield child
            yield from walk(child)

    yield from walk(paragraph)


def _iter_field_instructions(paragraph: _Element) -> Iterator[str]:
    """Hasilkan instruksi field lengkap, termasuk field yang terpecah run."""

    stack: list[list[str]] = []
    for marker in _iter_field_markers(paragraph):
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


def _field_name(instruction: str) -> str | None:
    match = FIELD_NAME_RE.match(instruction)
    return match.group(1).upper() if match else None


def _has_exempt_field(paragraph: _Element) -> bool:
    for instruction in _iter_field_instructions(paragraph):
        if _field_name(instruction) in EXEMPT_FIELDS:
            return True
    return False


def _iter_target_paragraphs(body: _Element) -> Iterator[_Element]:
    """Iterasi paragraf body dan sel tabel, tanpa isi text box."""

    for paragraph in body.iter(W_P):
        parent = paragraph.getparent()
        inside_textbox = False
        while parent is not None and parent is not body:
            if parent.tag == W_TXBXCONTENT:
                inside_textbox = True
                break
            parent = parent.getparent()
        if not inside_textbox:
            yield paragraph


def _iter_paragraph_runs(paragraph: _Element) -> Iterator[_Element]:
    """Iterasi run milik paragraf ini, tanpa menembus text box/nested paragraph."""

    def walk(element: _Element) -> Iterator[_Element]:
        for child in element:
            if child.tag in (W_P, W_TXBXCONTENT):
                continue
            if child.tag == W_R:
                yield child
                continue
            yield from walk(child)

    yield from walk(paragraph)


def _toggle_is_on(element: _Element) -> bool:
    """Nilai efektif elemen on/off OOXML; absennya ``w:val`` berarti aktif."""

    value = element.get(W_VAL)
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "off", "none"}


def _strip_run_bold(run: _Element) -> int:
    """Hapus properti bold langsung dari satu run. Kembalikan jumlah elemen."""

    properties = run.find(W_RPR)
    if properties is None:
        return 0

    removed = 0
    for tag in (W_B, W_BCS):
        for marker in list(properties.findall(tag)):
            if not _toggle_is_on(marker):
                continue
            properties.remove(marker)
            removed += 1
    return removed


def _strip_paragraph_bold(paragraph: _Element) -> int:
    removed = 0
    for run in _iter_paragraph_runs(paragraph):
        removed += _strip_run_bold(run)
    return removed


# ---------------------------------------------------------------------------
# Normalisasi


def _normalize_paragraph(paragraph: _Element) -> bool:
    """Terapkan spacing 1,5 baris dan justify. Kembalikan True bila berubah."""

    ppr = _get_or_add_ppr(paragraph)
    before = etree.tostring(ppr)

    spacing = _get_or_add_child(ppr, "w:spacing", PPR_ORDER)
    spacing.set(W_BEFORE, "0")
    spacing.set(W_AFTER, "0")
    spacing.set(W_LINE, str(LINE_SPACING_TWIPS))
    spacing.set(W_LINE_RULE, "auto")

    # Atribut ini menimpa before/after sehingga harus dibuang bila ada.
    for attribute in (W_BEFORE_LINES, W_AFTER_LINES, W_BEFORE_AUTO, W_AFTER_AUTO):
        spacing.attrib.pop(attribute, None)

    justification = _get_or_add_child(ppr, "w:jc", PPR_ORDER)
    # Perataan kanan langsung (mis. blok tanda tangan sampul) dipertahankan;
    # hanya paragraf lain yang dipaksa justify.
    if (justification.get(W_VAL) or "").strip().lower() != "right":
        justification.set(W_VAL, JUSTIFICATION)

    return etree.tostring(ppr) != before


def normalize_layout(
    docx_path: str | Path, out_docx: str | Path
) -> LayoutReport:
    """Normalisasi layout paragraf dari ``docx_path`` ke ``out_docx``."""

    input_path = Path(docx_path)
    output_path = Path(out_docx)

    document_xml = _read_document_xml(input_path)
    root, body = _parse_document(document_xml)

    report = LayoutReport()
    for paragraph in _iter_target_paragraphs(body):
        report.paragraphs += 1

        style_id = _paragraph_style_id(paragraph)
        if _has_exempt_style(style_id):
            # Heading, caption, kode, TOC, cover, dan figure dipertahankan;
            # bold langsung field cover tetap dibersihkan.
            if _has_cover_bold_to_strip(style_id):
                removed = _strip_paragraph_bold(paragraph)
                if removed:
                    report.bold_paragraphs += 1
                    report.bold_runs_removed += removed
            report.skipped_style += 1
            continue

        # Bold langsung dibersihkan dari body, daftar, dan semua sel tabel
        # (termasuk header). Paragraf ber-style heading/CoverTitle sudah
        # dilewati di atas sehingga bold-nya tetap dipertahankan.
        removed = _strip_paragraph_bold(paragraph)
        if removed:
            report.bold_paragraphs += 1
            report.bold_runs_removed += removed

        if _has_exempt_field(paragraph):
            report.skipped_field += 1
            continue

        if _normalize_paragraph(paragraph):
            report.normalized += 1
        else:
            report.unchanged += 1

    revised_xml = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    _write_docx(input_path, output_path, revised_xml)
    return report


def _summary(report: LayoutReport) -> str:
    return "\n".join(
        (
            f"Paragraf diperiksa: {report.paragraphs}",
            f"Paragraf dinormalisasi: {report.normalized}",
            f"Paragraf sudah sesuai: {report.unchanged}",
            f"Dilewati karena style: {report.skipped_style}",
            f"Dilewati karena field: {report.skipped_field}",
            f"Paragraf bold dibersihkan: {report.bold_paragraphs}",
            f"Properti bold dihapus: {report.bold_runs_removed}",
        )
    )


# ---------------------------------------------------------------------------
# CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Normalisasi layout paragraf DOCX: spacing before/after 0, "
            "spasi 1,5 baris, dan rata kanan-kiri (justify)."
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
        report = normalize_layout(args.docx, args.out)
    except (NormalizeLayoutError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_summary(report))
    print(f"DOCX: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
