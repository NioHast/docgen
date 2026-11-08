"""Normalisasi numbering daftar berurut pada DOCX hasil Pandoc.

Pandoc 3.13 sudah memetakan sintaks Markdown ke format numbering yang benar:

- ``1.``  -> ``w:numFmt`` ``decimal`` + ``w:lvlText`` ``%1.``
- ``a.``  -> ``w:numFmt`` ``lowerLetter`` + ``w:lvlText`` ``%1.``
- ``a)``  -> ``w:numFmt`` ``lowerLetter`` + ``w:lvlText`` ``%1)``

Yang belum sesuai adalah indentasi: Pandoc menulis ``w:ind left="720"
hanging="360"`` tanpa tab stop eksplisit. Alat ini hanya merapikan hal
tersebut, tanpa mengubah format numbering yang sudah dipilih dari Markdown:

1. Mendeteksi paragraf yang memiliki ``w:numPr`` dan level numbering
   berformat ``decimal`` atau ``lowerLetter``.
2. Menetapkan ``w:ind`` langsung pada paragraf: ``left = 720 x (ilvl + 1)``
   dan ``hanging = 720``. Untuk level teratas hasilnya 720/720.
3. Menambahkan satu tab stop kiri pada posisi ``left`` yang sama sehingga
   jarak nomor ke teks selalu satu tab.
4. Menetapkan ``w:suff`` level numbering ke ``tab`` agar pemisah nomor dan
   teks eksplisit.
5. Menghapus bold dari run paragraf list dan dari ``w:rPr`` level numbering.

Paragraf non-list, daftar bullet, dan format numbering lain tidak diubah.
``word/document.xml`` dan (bila perlu) ``word/numbering.xml`` ditulis ulang;
part lain disalin byte-per-byte dari DOCX asli. Penulisan memakai file
sementara lalu ``os.replace`` sehingga input tidak rusak bila proses gagal.

Jalankan:

    python tools/format_numbering.py --docx input.docx --out output.docx
"""

from __future__ import annotations

import argparse
import os
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
NUMBERING_PART = "word/numbering.xml"

INDENT_STEP_TWIPS = 720
HANGING_TWIPS = 720
MAX_LEVEL = 8

ORDERED_FORMATS = frozenset({"decimal", "lowerLetter"})

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_R = qn("w:r")
W_RPR = qn("w:rPr")
W_B = qn("w:b")
W_BCS = qn("w:bCs")
W_NUMPR = qn("w:numPr")
W_NUMID = qn("w:numId")
W_ILVL = qn("w:ilvl")
W_VAL = qn("w:val")
W_LEFT = qn("w:left")
W_HANGING = qn("w:hanging")
W_FIRST_LINE = qn("w:firstLine")
W_FIRST_LINE_CHARS = qn("w:firstLineChars")
W_HANGING_CHARS = qn("w:hangingChars")
W_LEFT_CHARS = qn("w:leftChars")
W_START = qn("w:start")
W_START_CHARS = qn("w:startChars")
W_POS = qn("w:pos")
W_TXBX_CONTENT = qn("w:txbxContent")

W_ABSTRACT_NUM = qn("w:abstractNum")
W_ABSTRACT_NUM_ID = qn("w:abstractNumId")
W_NUM = qn("w:num")
W_LVL = qn("w:lvl")
W_NUM_FMT = qn("w:numFmt")
W_LVL_TEXT = qn("w:lvlText")

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

LVL_ORDER = tuple(
    qn(tag)
    for tag in (
        "w:start",
        "w:numFmt",
        "w:lvlRestart",
        "w:pStyle",
        "w:isLgl",
        "w:suff",
        "w:lvlText",
        "w:lvlPicBulletId",
        "w:legacy",
        "w:lvlJc",
        "w:pPr",
        "w:rPr",
    )
)


class FormatNumberingError(Exception):
    """Kesalahan input yang dapat dilaporkan ke pengguna."""


@dataclass
class NumberingReport:
    """Ringkasan pekerjaan yang dilakukan alat."""

    list_paragraphs: int = 0
    paragraphs_changed: int = 0
    paragraphs_unchanged: int = 0
    numbering_levels: int = 0
    numbering_levels_changed: int = 0
    bold_removed: int = 0
    skipped_bullet: int = 0
    unresolved: int = 0
    format_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Utilitas XML


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


def _get_or_add_ppr(parent: _Element, order: Sequence[str]) -> _Element:
    ppr = parent.find(W_PPR)
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        _insert_ordered(parent, ppr, order)
    return ppr


def _int_attribute(
    element: _Element, attribute: str, default: int | None = None
) -> int | None:
    value = element.get(attribute)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_child(parent: _Element, tag: str, default: int | None = None) -> int | None:
    element = parent.find(tag)
    if element is None:
        return default
    return _int_attribute(element, W_VAL, default)


def _is_on(element: _Element) -> bool:
    value = (element.get(W_VAL) or "").strip().lower()
    return value not in {"0", "false", "off"}


def _strip_bold_from_rpr(rpr: _Element) -> int:
    removed = 0
    for tag in (W_B, W_BCS):
        for element in list(rpr.findall(tag)):
            if _is_on(element):
                rpr.remove(element)
                removed += 1
    return removed


def _iter_own_runs(paragraph: _Element) -> Iterator[_Element]:
    """Iterasi run milik paragraf ini, bukan run di dalam text box."""

    for run in paragraph.iter(W_R):
        parent = run.getparent()
        inside_textbox = False
        while parent is not None and parent is not paragraph:
            if parent.tag == W_TXBX_CONTENT:
                inside_textbox = True
                break
            parent = parent.getparent()
        if not inside_textbox:
            yield run


def _strip_paragraph_bold(paragraph: _Element) -> int:
    removed = 0
    ppr = paragraph.find(W_PPR)
    if ppr is not None:
        rpr = ppr.find(W_RPR)
        if rpr is not None:
            removed += _strip_bold_from_rpr(rpr)

    for run in _iter_own_runs(paragraph):
        rpr = run.find(W_RPR)
        if rpr is not None:
            removed += _strip_bold_from_rpr(rpr)
    return removed


def _set_indentation(ppr: _Element, left: int) -> bool:
    """Set ``w:ind left``/``hanging`` dan buang atribut yang menimpanya."""

    ind = _get_or_add_child(ppr, "w:ind", PPR_ORDER)
    before = etree.tostring(ind)

    for attribute in (
        W_FIRST_LINE,
        W_FIRST_LINE_CHARS,
        W_HANGING_CHARS,
        W_LEFT_CHARS,
        W_START,
        W_START_CHARS,
    ):
        ind.attrib.pop(attribute, None)

    ind.set(W_LEFT, str(left))
    ind.set(W_HANGING, str(HANGING_TWIPS))
    return etree.tostring(ind) != before


def _set_tab_stop(ppr: _Element, position: int) -> bool:
    """Pastikan ada tepat satu tab stop kiri pada posisi teks."""

    tabs = _get_or_add_child(ppr, "w:tabs", PPR_ORDER)
    before = etree.tostring(tabs)

    for child in list(tabs):
        tabs.remove(child)

    tab = OxmlElement("w:tab")
    tab.set(W_VAL, "left")
    tab.set(W_POS, str(position))
    tabs.append(tab)

    return etree.tostring(tabs) != before


def _set_suff_tab(level: _Element) -> bool:
    suff = _get_or_add_child(level, "w:suff", LVL_ORDER)
    before = etree.tostring(suff)
    suff.set(W_VAL, "tab")
    return etree.tostring(suff) != before


# ---------------------------------------------------------------------------
# Deteksi daftar


def _iter_target_paragraphs(body: _Element) -> Iterator[_Element]:
    """Iterasi paragraf body dan sel tabel, tanpa isi text box."""

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


def _paragraph_reference(paragraph: _Element) -> tuple[int, int] | None:
    """Kembalikan ``(numId, ilvl)`` bila paragraf adalah item list."""

    ppr = paragraph.find(W_PPR)
    if ppr is None:
        return None
    numpr = ppr.find(W_NUMPR)
    if numpr is None:
        return None

    num_id = _int_child(numpr, W_NUMID)
    if num_id is None or num_id <= 0:
        # numId 0 berarti numbering dimatikan untuk paragraf ini.
        return None

    ilvl = _int_child(numpr, W_ILVL, 0) or 0
    if ilvl < 0 or ilvl > MAX_LEVEL:
        ilvl = 0
    return num_id, ilvl


def _level_format(level: _Element) -> tuple[str, str]:
    fmt_element = level.find(W_NUM_FMT)
    fmt = (fmt_element.get(W_VAL) or "").strip() if fmt_element is not None else ""
    if not fmt:
        # numFmt opsional; default OOXML untuk ordered list adalah decimal.
        fmt = "decimal"

    text_element = level.find(W_LVL_TEXT)
    text = text_element.get(W_VAL) or "" if text_element is not None else ""
    return fmt, text


def _format_label(fmt: str, lvl_text: str) -> str:
    if fmt == "decimal" and lvl_text.endswith("."):
        return "1."
    if fmt == "lowerLetter" and lvl_text.endswith("."):
        return "a."
    if fmt == "lowerLetter" and lvl_text.endswith(")"):
        return "a)"
    return fmt


# ---------------------------------------------------------------------------
# Numbering.xml


def _build_numbering_index(
    root: _Element,
) -> dict[tuple[int, int], _Element]:
    abstracts: dict[int, _Element] = {}
    for abstract in root.findall(W_ABSTRACT_NUM):
        abstract_id = _int_attribute(abstract, W_ABSTRACT_NUM_ID)
        if abstract_id is not None:
            abstracts[abstract_id] = abstract

    num_to_abstract: dict[int, int] = {}
    for num in root.findall(W_NUM):
        num_id = _int_attribute(num, W_NUMID)
        abstract_id = _int_child(num, W_ABSTRACT_NUM_ID)
        if num_id is not None and abstract_id is not None:
            num_to_abstract[num_id] = abstract_id

    index: dict[tuple[int, int], _Element] = {}
    for num_id, abstract_id in num_to_abstract.items():
        abstract = abstracts.get(abstract_id)
        if abstract is None:
            continue
        for level in abstract.findall(W_LVL):
            ilvl = _int_attribute(level, W_ILVL, 0) or 0
            index[(num_id, ilvl)] = level
    return index


def _normalize_level(level: _Element) -> tuple[bool, int]:
    ilvl = _int_attribute(level, W_ILVL, 0) or 0
    if ilvl < 0 or ilvl > MAX_LEVEL:
        ilvl = 0

    ppr = _get_or_add_ppr(level, LVL_ORDER)
    left = INDENT_STEP_TWIPS * (ilvl + 1)

    changed = _set_indentation(ppr, left)
    changed = _set_tab_stop(ppr, left) or changed
    changed = _set_suff_tab(level) or changed

    removed = 0
    rpr = level.find(W_RPR)
    if rpr is not None:
        removed = _strip_bold_from_rpr(rpr)

    return changed or removed > 0, removed


# ---------------------------------------------------------------------------
# Baca/tulis DOCX


def _read_part(docx_path: Path, part: str, required: bool) -> bytes | None:
    try:
        with zipfile.ZipFile(docx_path, "r") as archive:
            try:
                return archive.read(part)
            except KeyError as exc:
                if not required:
                    return None
                raise FormatNumberingError(
                    f"{docx_path} bukan DOCX valid: part {part} tidak ada."
                ) from exc
    except FileNotFoundError as exc:
        raise FormatNumberingError(
            f"File input tidak ditemukan: {docx_path}"
        ) from exc
    except zipfile.BadZipFile as exc:
        raise FormatNumberingError(
            f"{docx_path} bukan arsip DOCX/ZIP yang valid."
        ) from exc
    except OSError as exc:
        raise FormatNumberingError(f"Tidak dapat membaca {docx_path}: {exc}") from exc


def _parse_xml(data: bytes, part: str) -> _Element:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    try:
        return etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise FormatNumberingError(f"XML {part} tidak valid: {exc}") from exc


def _write_docx(
    input_path: Path, output_path: Path, replacements: dict[str, bytes]
) -> None:
    """Tulis DOCX baru dengan mengganti part yang berubah saja."""

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
                data = replacements.get(info.filename)
                if data is None:
                    data = source.read(info.filename)

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
# API utama


def format_numbering(
    docx_path: str | Path, out_docx: str | Path
) -> NumberingReport:
    """Rapikan numbering daftar berurut dari ``docx_path`` ke ``out_docx``."""

    input_path = Path(docx_path)
    output_path = Path(out_docx)

    document_xml = _read_part(input_path, DOCUMENT_PART, required=True)
    if document_xml is None:
        raise FormatNumberingError(
            f"{DOCUMENT_PART} tidak ditemukan di {input_path}."
        )
    document_root = _parse_xml(document_xml, DOCUMENT_PART)
    body = document_root.find(W_BODY)
    if body is None:
        raise FormatNumberingError(
            f"{DOCUMENT_PART} tidak memiliki elemen w:body."
        )

    numbering_xml = _read_part(input_path, NUMBERING_PART, required=False)
    numbering_root = (
        _parse_xml(numbering_xml, NUMBERING_PART) if numbering_xml is not None else None
    )
    numbering_index = (
        _build_numbering_index(numbering_root) if numbering_root is not None else {}
    )

    report = NumberingReport()
    document_changed = False
    numbering_changed = False
    referenced_levels: set[int] = set()

    for paragraph in _iter_target_paragraphs(body):
        reference = _paragraph_reference(paragraph)
        if reference is None:
            continue

        num_id, ilvl = reference
        level = numbering_index.get(reference)

        if level is None:
            # DOCX tanpa numbering.xml atau referensi yang tidak lengkap:
            # paragraf tetap jelas list, jadi indentasinya masih bisa
            # dirapikan tanpa mengubah format numbering.
            report.unresolved += 1
            report.list_paragraphs += 1
            report.format_counts["tidak diketahui"] = (
                report.format_counts.get("tidak diketahui", 0) + 1
            )
        else:
            fmt, lvl_text = _level_format(level)
            if fmt not in ORDERED_FORMATS:
                report.skipped_bullet += 1
                continue
            report.list_paragraphs += 1
            label = _format_label(fmt, lvl_text)
            report.format_counts[label] = report.format_counts.get(label, 0) + 1

        ppr = _get_or_add_ppr(paragraph, PPR_ORDER)
        left = INDENT_STEP_TWIPS * (ilvl + 1)
        if _set_indentation(ppr, left):
            report.paragraphs_changed += 1
            document_changed = True
        else:
            report.paragraphs_unchanged += 1
        if _set_tab_stop(ppr, left):
            document_changed = True

        removed = _strip_paragraph_bold(paragraph)
        if removed:
            report.bold_removed += removed
            document_changed = True

        if level is not None:
            referenced_levels.add(id(level))

    processed_levels: set[int] = set()
    for level in numbering_index.values():
        level_id = id(level)
        if level_id not in referenced_levels or level_id in processed_levels:
            continue
        processed_levels.add(level_id)
        report.numbering_levels += 1
        changed, removed = _normalize_level(level)
        if changed:
            report.numbering_levels_changed += 1
            numbering_changed = True
        report.bold_removed += removed

    replacements: dict[str, bytes] = {}
    if document_changed:
        replacements[DOCUMENT_PART] = etree.tostring(
            document_root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
    if numbering_changed and numbering_root is not None:
        replacements[NUMBERING_PART] = etree.tostring(
            numbering_root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )

    _write_docx(input_path, output_path, replacements)
    return report


# ---------------------------------------------------------------------------
# CLI


def _summary(report: NumberingReport) -> str:
    formats = ", ".join(
        f"{label}={count}" for label, count in sorted(report.format_counts.items())
    )
    lines = [
        f"Paragraf list diperiksa: {report.list_paragraphs}",
        f"Indent/tab dirapikan: {report.paragraphs_changed} "
        f"(sudah sesuai: {report.paragraphs_unchanged})",
        f"Level numbering dirapikan: {report.numbering_levels_changed} "
        f"dari {report.numbering_levels}",
        f"Elemen bold dihapus: {report.bold_removed}",
    ]
    if formats:
        lines.append(f"Format: {formats}")
    if report.skipped_bullet:
        lines.append(f"Item bullet dilewati: {report.skipped_bullet}")
    if report.unresolved:
        lines.append(
            f"List tanpa definisi numbering lengkap: {report.unresolved}"
        )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rapikan numbering daftar DOCX: indent 720 twip, hanging 720, "
            "tab stop 720, dan tanpa bold."
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
        report = format_numbering(args.docx, args.out)
    except (FormatNumberingError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_summary(report))
    print(f"DOCX: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
