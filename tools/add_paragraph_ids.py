"""Injeksi bookmark ID paragraf untuk integrasi Adeu.

Alat ini menambahkan bookmark stabil ``p0001``, ``p0002``, ... ke setiap
paragraf body DOCX. Bookmark dibungkus di dalam isi paragraf (setelah
``w:pPr``) agar tidak mengubah properti paragraf, lalu dideskripsikan dalam
manifest JSON yang bentuknya dipakai Adeu sebagai proyeksi ``{#nama}``.

Perubahan hanya dilakukan pada ``word/document.xml``. Semua part lain
(header, footer, styles, numbering, media, dan relasi) disalin byte-per-byte
dari arsip asli, sehingga dokumen tetap dapat dibuka Word dan teks/format
tidak berubah.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
from lxml.etree import _Element

DOCUMENT_PART = "word/document.xml"
MANIFEST_VERSION = 1

W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_TBL = qn("w:tbl")
W_VAL = qn("w:val")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_PTAB = qn("w:ptab")
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_NO_BREAK_HYPHEN = qn("w:noBreakHyphen")
W_BOOKMARK_START = qn("w:bookmarkStart")
W_BOOKMARK_END = qn("w:bookmarkEnd")
W_ID = qn("w:id")
W_NAME = qn("w:name")
W_INSTRTEXT = qn("w:instrText")
W_FLDCHAR = qn("w:fldChar")
W_FLDCHARTYPE = qn("w:fldCharType")
W_FLDSIMPLE = qn("w:fldSimple")
W_INSTR = qn("w:instr")
W_DRAWING = qn("w:drawing")
W_PICT = qn("w:pict")
W_OBJECT = qn("w:object")
W_TXBXCONTENT = qn("w:txbxContent")
W_DEL = qn("w:del")
W_MOVEFROM = qn("w:moveFrom")
W_DELTEXT = qn("w:delText")
W_SECTPR = qn("w:sectPr")

PARAGRAPH_ID_RE = re.compile(r"^p\d{4,}$")
HEADING_STYLE_RE = re.compile(r"^Heading([1-9])$")
CAPTION_STYLES = frozenset({"ImageCaption", "TableCaption", "Caption"})
BIBLIOGRAPHY_STYLE = "Bibliography"
TOC_FIELD = "TOC"

# Elemen yang tidak boleh dianggap teks paragraf: kode field, teks terhapus,
# isi gambar/text box (paragraf di dalamnya diproses terpisah), dan properti.
TEXT_SKIP_TAGS = frozenset(
    {
        W_PPR,
        W_INSTRTEXT,
        W_FLDCHAR,
        W_DEL,
        W_MOVEFROM,
        W_DELTEXT,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_TXBXCONTENT,
        W_P,
    }
)

MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
MARKDOWN_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
MARKDOWN_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
MARKDOWN_TABLE_RE = re.compile(r"^\s*\|")
MARKDOWN_HR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
HEADING_NUMBER_RE = re.compile(
    r"^(?:(?:BAB|BAGIAN|CHAPTER)\s+"
    r"(?:XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I|\d+)"
    r"\s*[.:-]?\s*"
    r"|\d+(?:\.\d+)*\.?\s+"
    r"|[IVXLCDM]+\.\s+)",
    re.IGNORECASE,
)


class ParagraphIdError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass
class ParagraphRecord:
    index: int
    id: str
    kind: str
    heading_path: list[str]
    text: str
    protected: bool
    protected_reason: str | None
    source_file: str | None = None
    source_line: int | None = None

    def as_manifest_entry(self, include_source: bool) -> dict[str, object]:
        entry: dict[str, object] = {
            "id": self.id,
            "index": self.index,
            "kind": self.kind,
            "heading_path": list(self.heading_path),
            "text": self.text,
            "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
            "protected": self.protected,
            "protected_reason": self.protected_reason,
        }
        if include_source:
            entry["source_file"] = self.source_file
            entry["source_line"] = self.source_line
        return entry


@dataclass
class _FieldFrame:
    start_index: int
    instruction_parts: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pembacaan dan penulisan DOCX


def _read_document_xml(docx_path: Path) -> bytes:
    try:
        with zipfile.ZipFile(docx_path, "r") as archive:
            try:
                return archive.read(DOCUMENT_PART)
            except KeyError as exc:
                raise ParagraphIdError(
                    f"{docx_path} bukan DOCX valid: part {DOCUMENT_PART} tidak ada."
                ) from exc
    except FileNotFoundError as exc:
        raise ParagraphIdError(f"File input tidak ditemukan: {docx_path}") from exc
    except zipfile.BadZipFile as exc:
        raise ParagraphIdError(f"{docx_path} bukan arsip DOCX/ZIP yang valid.") from exc
    except OSError as exc:
        raise ParagraphIdError(f"Tidak dapat membaca {docx_path}: {exc}") from exc


def _parse_document(document_xml: bytes) -> tuple[_Element, _Element]:
    parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
    try:
        root = etree.fromstring(document_xml, parser)
    except etree.XMLSyntaxError as exc:
        raise ParagraphIdError(f"XML {DOCUMENT_PART} tidak valid: {exc}") from exc
    body = root.find(W_BODY)
    if body is None:
        raise ParagraphIdError(f"{DOCUMENT_PART} tidak memiliki elemen w:body.")
    return root, body


def _write_docx(input_path: Path, output_path: Path, document_xml: bytes) -> None:
    """Tulis DOCX baru dengan mengganti document.xml saja.

    Semua part lain disalin dari ZIP asli tanpa parsing ulang agar header,
    footer, style, numbering, media, dan relasi tetap identik byte-per-byte.
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
# Traversal paragraf dan teks


def _paragraphs(body: _Element) -> list[_Element]:
    """Semua paragraf body dalam urutan dokumen, termasuk di dalam tabel.

    Header, footer, dan footnote tidak berada di ``word/document.xml``
    sehingga otomatis tidak ikut. Paragraf di dalam text box tetap dihitung
    sebagai bagian body.
    """

    return list(body.iter(W_P))


def _paragraph_style(paragraph: _Element) -> str | None:
    style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
    if style is None:
        return None
    return style.get(W_VAL)


def _heading_level(style: str | None) -> int | None:
    if style is None:
        return None
    match = HEADING_STYLE_RE.fullmatch(style)
    return int(match.group(1)) if match else None


def _in_table(paragraph: _Element) -> bool:
    return any(ancestor.tag == W_TBL for ancestor in paragraph.iterancestors())


def _paragraph_text(paragraph: _Element) -> str:
    """Teks paragraf yang terlihat, tanpa kode field dan properti.

    Tab dan line break dipetakan ke ``\\t`` dan ``\\n`` seperti python-docx.
    Teks di dalam gambar/text box dan paragraf bersarang tidak diikutkan
    karena paragraf tersebut diproses sebagai record sendiri.
    """

    return _element_text(paragraph)


def _element_text(element: _Element) -> str:
    parts: list[str] = []
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
            parts.append(_element_text(child))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Deteksi field dan proteksi


def _field_name(instruction: str) -> str | None:
    match = re.match(r"\s*([A-Za-z]+)", instruction)
    return match.group(1).upper() if match else None


def _iter_field_markers(paragraph: _Element) -> Iterator[_Element]:
    """Iterasi fldChar/instrText/fldSimple secara berurutan.

    Paragraf bersarang (text box) dilewati karena akan dipindai sendiri.
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


def _scan_fields(
    paragraphs: Sequence[_Element],
) -> tuple[set[int], list[set[str]]]:
    """Kembalikan indeks paragraf di dalam field TOC dan nama field per paragraf."""

    if not paragraphs:
        return set(), []

    stack: list[_FieldFrame] = []
    spans: list[tuple[str, int, int]] = []
    direct_names: list[set[str]] = [set() for _ in paragraphs]

    for index, paragraph in enumerate(paragraphs):
        for marker in _iter_field_markers(paragraph):
            if marker.tag == W_FLDCHAR:
                field_type = marker.get(W_FLDCHARTYPE)
                if field_type == "begin":
                    stack.append(_FieldFrame(start_index=index))
                elif field_type == "end" and stack:
                    frame = stack.pop()
                    name = _field_name("".join(frame.instruction_parts))
                    if name is not None:
                        spans.append((name, frame.start_index, index))
            elif marker.tag == W_INSTRTEXT:
                text = marker.text or ""
                if stack:
                    stack[-1].instruction_parts.append(text)
                name = _field_name(text)
                if name is not None:
                    direct_names[index].add(name)
            elif marker.tag == W_FLDSIMPLE:
                name = _field_name(marker.get(W_INSTR) or "")
                if name is not None:
                    spans.append((name, index, index))
                    direct_names[index].add(name)

    # Field yang tidak ditutup tetap dianggap mencakup sisa dokumen.
    for frame in stack:
        name = _field_name("".join(frame.instruction_parts))
        if name is not None:
            spans.append((name, frame.start_index, len(paragraphs) - 1))

    field_names: list[set[str]] = [set() for _ in paragraphs]
    toc_indices: set[int] = set()
    for name, start, end in spans:
        for index in range(max(start, 0), min(end, len(paragraphs) - 1) + 1):
            field_names[index].add(name)
            if name == TOC_FIELD:
                toc_indices.add(index)
    for index, names in enumerate(direct_names):
        field_names[index].update(names)
        if TOC_FIELD in names:
            toc_indices.add(index)
    return toc_indices, field_names


def _classify_kind(style: str | None, in_table: bool, in_toc: bool) -> str:
    if _heading_level(style) is not None:
        return "heading"
    if style in CAPTION_STYLES:
        return "caption"
    if style == BIBLIOGRAPHY_STYLE:
        return "bibliography"
    if style == "Title" or (style is not None and style.startswith("Cover")):
        return "cover"
    if style is not None and style.startswith("TOC"):
        return "toc"
    if in_toc:
        return "toc"
    if in_table:
        return "table"
    return "body"


def _has_sectpr(paragraph: _Element) -> bool:
    return (
        paragraph.find(f"{W_PPR}/{W_SECTPR}") is not None
        or paragraph.find(W_SECTPR) is not None
    )


def _protected_reason(
    kind: str,
    field_names: set[str],
    in_toc: bool,
    contains_sectpr: bool,
) -> str | None:
    if in_toc or TOC_FIELD in field_names:
        return "toc_field"
    if contains_sectpr:
        return "sectpr"
    if "SEQ" in field_names:
        return "seq_field"
    if "PAGEREF" in field_names:
        return "pageref_field"
    if "PAGE" in field_names:
        return "page_field"
    if kind == "caption":
        return "caption_style"
    if kind == "toc":
        return "toc_style"
    if kind == "bibliography":
        return "bibliography"
    if kind == "cover":
        return "cover_style"
    return None


# ---------------------------------------------------------------------------
# Bookmark


def _remove_existing_ids(body: _Element) -> None:
    """Hapus bookmark pNNNN lama agar injeksi idempoten."""

    old_starts = [
        bookmark
        for bookmark in body.iter(W_BOOKMARK_START)
        if PARAGRAPH_ID_RE.fullmatch(bookmark.get(W_NAME) or "")
    ]
    old_ids = {
        bookmark.get(W_ID)
        for bookmark in old_starts
        if bookmark.get(W_ID) is not None
    }
    for bookmark in old_starts:
        parent = bookmark.getparent()
        if parent is not None:
            parent.remove(bookmark)
    if not old_ids:
        return
    old_ends = [
        bookmark
        for bookmark in body.iter(W_BOOKMARK_END)
        if bookmark.get(W_ID) in old_ids
    ]
    for bookmark in old_ends:
        parent = bookmark.getparent()
        if parent is not None:
            parent.remove(bookmark)


def _used_bookmark_ids(body: _Element) -> set[int]:
    used: set[int] = set()
    for tag in (W_BOOKMARK_START, W_BOOKMARK_END):
        for bookmark in body.iter(tag):
            value = bookmark.get(W_ID)
            if value is None:
                continue
            try:
                used.add(int(value))
            except ValueError:
                continue
    return used


def _insert_bookmark(paragraph: _Element, bookmark_id: int, name: str) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(W_ID, str(bookmark_id))
    start.set(W_NAME, name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(W_ID, str(bookmark_id))

    ppr = paragraph.find(W_PPR)
    if ppr is None:
        paragraph.insert(0, start)
    else:
        paragraph.insert(paragraph.index(ppr) + 1, start)
    paragraph.append(end)


# ---------------------------------------------------------------------------
# Pencocokan sumber Markdown


def _normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u2011", "-")
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"`+([^`]*)`+", r"\1", text)
    text = re.sub(r"\*\*|__|\*|_", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\\([\\`*{}\[\]()#+\-.!_>])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_heading(text: str) -> str:
    normalized = _normalize_text(text)
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = HEADING_NUMBER_RE.sub("", normalized, count=1).strip()
    return normalized


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = stripped.strip("|").split("|")
    return bool(cells) and all(
        re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in cells
    )


def _split_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == "|":
            cells.append("".join(current))
            current = []
        else:
            current.append(character)
    cells.append("".join(current))
    return [cell.strip() for cell in cells if cell.strip()]


def _markdown_candidates(
    text: str, source_file: str
) -> Iterator[tuple[str, int, tuple[str, ...], str]]:
    """Hasilkan (source_file, baris, heading_path, teks) dari satu Markdown."""

    lines = text.splitlines()
    start_index = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in {"---", "..."}:
                start_index = index + 1
                break

    heading_state: dict[int, str] = {}
    block: list[tuple[int, str]] = []
    block_type = "paragraph"

    def current_path() -> tuple[str, ...]:
        return tuple(heading_state[level] for level in sorted(heading_state))

    def flush() -> Iterator[tuple[str, int, tuple[str, ...], str]]:
        nonlocal block, block_type
        if not block:
            block_type = "paragraph"
            return
        first_line = block[0][0]
        if block_type == "list":
            first_line_text = re.sub(MARKDOWN_LIST_RE, "", block[0][1], count=1)
            raw = " ".join([first_line_text, *(line for _, line in block[1:])])
        elif block_type == "quote":
            raw = " ".join(
                re.sub(r"^\s*>\s?", "", line) for _, line in block
            )
        else:
            raw = " ".join(line for _, line in block)
        normalized = _normalize_text(raw)
        if normalized:
            yield source_file, first_line, current_path(), normalized
        block = []
        block_type = "paragraph"

    index = start_index
    while index < len(lines):
        line = lines[index]
        line_number = index + 1
        stripped = line.strip()

        fence = MARKDOWN_FENCE_RE.match(line)
        if fence:
            yield from flush()
            fence_marker = fence.group(1)
            fence_char = fence_marker[0]
            fence_length = len(fence_marker)
            code_lines: list[tuple[int, str]] = []
            index += 1
            while index < len(lines):
                candidate = lines[index]
                closing = re.match(
                    rf"^\s{{0,3}}{re.escape(fence_char)}{{{fence_length},}}\s*$",
                    candidate,
                )
                if closing:
                    break
                code_lines.append((index + 1, candidate))
                index += 1
            if code_lines:
                code_text = "\n".join(code for _, code in code_lines)
                normalized = _normalize_text(code_text)
                if normalized:
                    yield (
                        source_file,
                        code_lines[0][0],
                        current_path(),
                        normalized,
                    )
            index += 1
            continue

        heading = MARKDOWN_HEADING_RE.match(line)
        if heading:
            yield from flush()
            level = len(heading.group(1))
            heading_text = _normalize_heading(heading.group(2))
            for existing in list(heading_state):
                if existing >= level:
                    del heading_state[existing]
            heading_state[level] = heading_text
            if heading_text:
                yield source_file, line_number, current_path(), heading_text
            index += 1
            continue

        if not stripped:
            yield from flush()
            index += 1
            continue

        if MARKDOWN_HR_RE.match(line):
            yield from flush()
            index += 1
            continue

        if MARKDOWN_TABLE_RE.match(line):
            yield from flush()
            if not _is_table_separator(line):
                for cell in _split_table_cells(line):
                    normalized = _normalize_text(cell)
                    if normalized:
                        yield source_file, line_number, current_path(), normalized
            index += 1
            continue

        list_match = MARKDOWN_LIST_RE.match(line)
        if list_match:
            yield from flush()
            block_type = "list"
            block.append((line_number, line.strip()))
            index += 1
            continue

        if re.match(r"^\s*>", line):
            if block_type != "quote":
                yield from flush()
                block_type = "quote"
            block.append((line_number, line.strip()))
            index += 1
            continue

        if block_type == "list" and block:
            block.append((line_number, line.strip()))
            index += 1
            continue

        if block_type == "quote" and block:
            block.append((line_number, line.strip()))
            index += 1
            continue

        if not block:
            block_type = "paragraph"
        block.append((line_number, line.strip()))
        index += 1

    yield from flush()


def _load_source_candidates(
    source_dir: Path,
) -> dict[tuple[tuple[str, ...], str], list[tuple[str, int]]]:
    if not source_dir.exists() or not source_dir.is_dir():
        raise ParagraphIdError(f"--source-dir bukan direktori: {source_dir}")

    candidates: dict[
        tuple[tuple[str, ...], str], list[tuple[str, int]]
    ] = {}
    for path in sorted(source_dir.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise ParagraphIdError(f"Tidak dapat membaca {path}: {exc}") from exc
        source_name = path.relative_to(source_dir).as_posix()
        for source_file, line, heading_path, paragraph_text in _markdown_candidates(
            text, source_name
        ):
            key = (heading_path, paragraph_text)
            candidates.setdefault(key, []).append((source_file, line))
    return candidates


def _attach_sources(
    records: Sequence[ParagraphRecord], source_dir: Path
) -> int:
    candidates = _load_source_candidates(source_dir)
    matched = 0
    for record in records:
        if record.kind == "heading":
            paragraph_text = _normalize_heading(record.text)
        else:
            paragraph_text = _normalize_text(record.text)
        heading_path = tuple(_normalize_heading(item) for item in record.heading_path)
        if not paragraph_text:
            continue
        matches = candidates.get((heading_path, paragraph_text), [])
        if len(matches) != 1:
            continue
        record.source_file = matches[0][0]
        record.source_line = matches[0][1]
        matched += 1
    return matched


# ---------------------------------------------------------------------------
# Analisis dan injeksi


def _analyze_paragraphs(body: _Element) -> list[ParagraphRecord]:
    paragraphs = _paragraphs(body)
    toc_indices, field_names = _scan_fields(paragraphs)

    records: list[ParagraphRecord] = []
    heading_state: dict[int, str] = {}
    for index, paragraph in enumerate(paragraphs):
        style = _paragraph_style(paragraph)
        text = _paragraph_text(paragraph)
        kind = _classify_kind(style, _in_table(paragraph), index in toc_indices)

        if kind == "heading":
            level = _heading_level(style)
            assert level is not None
            for existing in list(heading_state):
                if existing >= level:
                    del heading_state[existing]
            heading_state[level] = text
        heading_path = [
            heading_state[level] for level in sorted(heading_state)
        ]

        reason = _protected_reason(
            kind,
            field_names[index],
            index in toc_indices,
            _has_sectpr(paragraph),
        )
        records.append(
            ParagraphRecord(
                index=index,
                id=f"p{index + 1:04d}",
                kind=kind,
                heading_path=heading_path,
                text=text,
                protected=reason is not None,
                protected_reason=reason,
            )
        )
    return records


def add_paragraph_ids(
    docx_path: str | Path,
    out_docx: str | Path,
    manifest_path: str | Path,
    source_dir: str | Path | None = None,
    docx_name: str | None = None,
) -> dict[str, object]:
    """Injeksi bookmark pNNNN dan tulis manifest Adeu.

    ``docx_path`` tidak pernah ditimpa kecuali ``out_docx`` menunjuk path yang
    sama (ditangani lewat file sementara dan ``os.replace``).

    ``docx_name`` adalah nama yang dicatat di manifest; bila ``None``, dipakai
    nama ``out_docx``. Build memakai ini karena DOCX dialirkan lewat file
    sementara ``Laporan-ids.docx`` sebelum dipindahkan ke ``Laporan.docx``.
    """

    input_path = Path(docx_path)
    output_path = Path(out_docx)
    manifest_file = Path(manifest_path)
    source_path = Path(source_dir) if source_dir is not None else None

    root, body = _parse_document(_read_document_xml(input_path))
    _remove_existing_ids(body)
    records = _analyze_paragraphs(body)

    next_bookmark_id = max(_used_bookmark_ids(body), default=-1) + 1
    paragraphs = _paragraphs(body)
    if len(paragraphs) != len(records):
        raise ParagraphIdError(
            "Jumlah paragraf berubah saat analisis; dokumen tidak disentuh."
        )
    for offset, (paragraph, record) in enumerate(zip(paragraphs, records)):
        _insert_bookmark(
            paragraph, next_bookmark_id + offset, record.id
        )

    if source_path is not None:
        _attach_sources(records, source_path)

    document_xml = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    _write_docx(input_path, output_path, document_xml)

    manifest: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "docx": docx_name if docx_name is not None else output_path.name,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "paragraphs": [
            record.as_manifest_entry(include_source=source_path is not None)
            for record in records
        ],
    }
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    with manifest_file.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def _summary(manifest: dict[str, object]) -> str:
    paragraphs = manifest["paragraphs"]
    assert isinstance(paragraphs, list)
    kinds = Counter(
        str(entry["kind"]) for entry in paragraphs if isinstance(entry, dict)
    )
    protected = sum(
        1
        for entry in paragraphs
        if isinstance(entry, dict) and entry["protected"]
    )
    ids = [
        str(entry["id"])
        for entry in paragraphs
        if isinstance(entry, dict) and entry.get("id")
    ]
    id_range = f"{ids[0]}..{ids[-1]}" if ids else "-"
    kind_text = ", ".join(f"{name}={count}" for name, count in sorted(kinds.items()))
    return (
        f"Paragraf body: {len(paragraphs)} ({kind_text})\n"
        f"Protected: {protected}\n"
        f"Bookmark: {id_range}"
    )


# ---------------------------------------------------------------------------
# CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Injeksi bookmark pNNNN ke setiap paragraf body DOCX dan tulis "
            "manifest JSON untuk integrasi Adeu."
        )
    )
    parser.add_argument("docx", type=Path, help="file DOCX input")
    parser.add_argument(
        "--out-docx",
        type=Path,
        required=True,
        help="lokasi DOCX hasil (tidak menimpa input secara langsung)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="lokasi manifest JSON hasil",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help=(
            "opsional; direktori Markdown untuk mengisi source_file/source_line "
            "bila heading_path dan teks cocok secara unik"
        ),
    )
    parser.add_argument(
        "--docx-name",
        help=(
            "opsional; nama DOCX yang dicatat di manifest "
            "(default: nama --out-docx)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        manifest = add_paragraph_ids(
            args.docx,
            args.out_docx,
            args.manifest,
            args.source_dir,
            args.docx_name,
        )
    except (ParagraphIdError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_summary(manifest))
    print(f"DOCX: {args.out_docx}")
    print(f"Manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
