#!/usr/bin/env python3
"""Rekonsiliasi edit manual DOCX terhadap manifest dan sumber Markdown.

Alat ini membaca DOCX hasil build yang sudah diberi bookmark ``pNNNN``,
membandingkan teks setiap paragraf dengan ``manifest.json``, lalu menulis
laporan tinjauan ke Markdown. Alat ini tidak pernah menulis ke
``chapters/*.md`` maupun ke DOCX.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Sequence

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from lxml.etree import XMLSyntaxError

MANIFEST_VERSION = 1
BOOKMARK_RE = re.compile(r"^p\d{4,}$")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
LIST_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
FOOTNOTE_DEFINITION_RE = re.compile(r"^\s*\[\^[^\]]+\]:")
LINK_DEFINITION_RE = re.compile(r"^\s*\[[^\]]+\]:\s*\S+")
HORIZONTAL_RULE_RE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
YAML_DELIMITER_RE = re.compile(r"^(---|\.\.\.)\s*$")

KIND_VALUES = {
    "heading",
    "body",
    "table",
    "caption",
    "toc",
    "bibliography",
    "cover",
}

# Kemiripan minimum agar sebuah blok Markdown dianggap sumber. Nilai ini
# sengaja rendah karena teks DOCX sudah kehilangan markup, sitasi, dan
# penomoran otomatis; yang penting blok berasal dari heading_path yang sama.
SIMILARITY_THRESHOLD = 0.35

W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_PTAB = qn("w:ptab")
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_NO_BREAK_HYPHEN = qn("w:noBreakHyphen")
W_SOFT_HYPHEN = qn("w:softHyphen")
W_INSTR_TEXT = qn("w:instrText")
W_DEL = qn("w:del")
W_MOVE_FROM = qn("w:moveFrom")
W_DRAWING = qn("w:drawing")
W_PICT = qn("w:pict")
W_OBJECT = qn("w:object")
W_TXBX_CONTENT = qn("w:txbxContent")
W_BOOKMARK_START = qn("w:bookmarkStart")
W_BOOKMARK_END = qn("w:bookmarkEnd")
W_ID = qn("w:id")
W_NAME = qn("w:name")


class ReconcileError(Exception):
    """Kesalahan input yang aman ditampilkan ke pengguna CLI."""


@dataclass(frozen=True)
class ManifestParagraph:
    id: str
    index: int
    kind: str
    heading_path: tuple[str, ...]
    text: str
    protected: bool
    protected_reason: str | None


@dataclass(frozen=True)
class DocxSnapshot:
    """Teks paragraf ber-bookmark, urutan bookmark, dan paragraf tanpa ID."""

    bookmarks: dict[str, str]
    order: tuple[str, ...]
    unbookmarked: tuple[str, ...]


@dataclass(frozen=True)
class MarkdownBlock:
    path: Path
    index: int
    heading_path: tuple[str, ...]
    text: str
    line: int


@dataclass(frozen=True)
class SourceMatch:
    block: MarkdownBlock
    similarity: float
    display_path: str


@dataclass(frozen=True)
class ReconcileResult:
    report: str
    exit_code: int
    checked: int
    changed: int
    violations: int


@dataclass
class _OpenBookmark:
    name: str
    chunks: list[str]


# ---------------------------------------------------------------------------
# Manifest


def load_manifest(path: Path) -> list[ManifestParagraph]:
    """Baca dan validasi manifest versi 1."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ReconcileError(f"manifest tidak ditemukan: {path}") from exc
    except OSError as exc:
        raise ReconcileError(f"manifest tidak dapat dibaca: {path}: {exc}") from exc
    except UnicodeError as exc:
        raise ReconcileError(f"manifest bukan UTF-8 valid: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReconcileError(
            f"manifest bukan JSON valid: {path} (baris {exc.lineno}: {exc.msg})"
        ) from exc

    if not isinstance(raw, dict):
        raise ReconcileError("manifest harus berupa objek JSON.")
    if raw.get("version") != MANIFEST_VERSION:
        raise ReconcileError(
            f"versi manifest tidak didukung: {raw.get('version')!r} "
            f"(diharapkan {MANIFEST_VERSION})."
        )

    items = raw.get("paragraphs")
    if not isinstance(items, list):
        raise ReconcileError("manifest.paragraphs harus berupa array.")

    paragraphs: list[ManifestParagraph] = []
    seen_ids: set[str] = set()
    seen_indexes: set[int] = set()

    for position, item in enumerate(items):
        where = f"paragraphs[{position}]"
        if not isinstance(item, dict):
            raise ReconcileError(f"{where} harus berupa objek.")

        paragraph_id = item.get("id")
        if not isinstance(paragraph_id, str) or not BOOKMARK_RE.fullmatch(paragraph_id):
            raise ReconcileError(
                f"{where}.id harus berformat pNNNN, ditemukan {paragraph_id!r}."
            )
        if paragraph_id in seen_ids:
            raise ReconcileError(f"id manifest duplikat: {paragraph_id}.")
        seen_ids.add(paragraph_id)

        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ReconcileError(f"{where}.index harus bilangan bulat >= 0.")
        if index in seen_indexes:
            raise ReconcileError(f"index manifest duplikat: {index}.")
        seen_indexes.add(index)

        kind = item.get("kind")
        if kind not in KIND_VALUES:
            raise ReconcileError(
                f"{where}.kind tidak dikenal: {kind!r}; "
                f"pilihan: {', '.join(sorted(KIND_VALUES))}."
            )

        heading_path = item.get("heading_path", [])
        if not isinstance(heading_path, list) or any(
            not isinstance(part, str) for part in heading_path
        ):
            raise ReconcileError(f"{where}.heading_path harus array string.")
        cleaned_path = tuple(part for part in heading_path if part.strip())

        text = item.get("text")
        if not isinstance(text, str):
            raise ReconcileError(f"{where}.text harus string.")

        protected = item.get("protected", False)
        if not isinstance(protected, bool):
            raise ReconcileError(f"{where}.protected harus boolean.")

        protected_reason = item.get("protected_reason")
        if protected_reason is not None and not isinstance(protected_reason, str):
            raise ReconcileError(f"{where}.protected_reason harus string atau null.")

        paragraphs.append(
            ManifestParagraph(
                id=paragraph_id,
                index=index,
                kind=kind,
                heading_path=cleaned_path,
                text=text,
                protected=protected,
                protected_reason=protected_reason,
            )
        )

    paragraphs.sort(key=lambda paragraph: (paragraph.index, paragraph.id))
    return paragraphs


# ---------------------------------------------------------------------------
# Ekstraksi DOCX


def _clean_text(text: str) -> str:
    """Normalisasi aman untuk perbandingan dan tampilan laporan."""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    return text.strip()


def _visible_text(element) -> str:
    """Teks yang terlihat pada state 'accepted' Track Changes."""

    tag = element.tag
    if tag in (
        W_P,
        W_PPR,
        W_DEL,
        W_MOVE_FROM,
        W_INSTR_TEXT,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_TXBX_CONTENT,
    ):
        return ""
    if tag == W_T:
        return element.text or ""
    if tag in (W_TAB, W_PTAB):
        return "\t"
    if tag in (W_BR, W_CR):
        return "\n"
    if tag == W_NO_BREAK_HYPHEN:
        return "\u2011"
    if tag == W_SOFT_HYPHEN:
        return ""
    return "".join(_visible_text(child) for child in element)


def _outer_paragraphs(container) -> list:
    """Paragraf di dalam container, tanpa paragraf yang bersarang di paragraf lain."""

    result = []
    for paragraph in container.iter(W_P):
        parent = paragraph.getparent()
        nested = False
        while parent is not None and parent is not container:
            if parent.tag == W_P:
                nested = True
                break
            parent = parent.getparent()
        if not nested:
            result.append(paragraph)
    return result


def _walk_nested_paragraphs(container, closed, unbookmarked, started) -> None:
    """Proses paragraf di gambar/text box tanpa mencemari bookmark paragraf induk.

    ``add_paragraph_ids.py`` tidak memasukkan isi ``w:txbxContent`` ke teks
    paragraf induk, tetapi tetap memberi bookmark pada paragraf di dalamnya.
    """

    for paragraph in _outer_paragraphs(container):
        _walk_xml(paragraph, {}, closed, unbookmarked, started)


def _paragraph_visible_text(paragraph) -> str:
    """Teks satu paragraf tanpa properti dan tanpa isi gambar/text box."""

    parts: list[str] = []
    for child in paragraph:
        if child.tag in (
            W_P,
            W_PPR,
            W_DRAWING,
            W_PICT,
            W_OBJECT,
            W_TXBX_CONTENT,
        ):
            continue
        parts.append(_visible_text(child))
    return "".join(parts)


def _has_bookmark_start(element) -> bool:
    for candidate in element.iter(W_BOOKMARK_START):
        name = candidate.get(W_NAME)
        if name and BOOKMARK_RE.fullmatch(name):
            return True
    return False


def _walk_xml(
    element,
    active: dict[str, _OpenBookmark],
    closed: list[tuple[str, str]],
    unbookmarked: list[str],
    started: list[str],
) -> None:
    tag = element.tag

    if tag in (W_DEL, W_MOVE_FROM):
        return

    if tag == W_BOOKMARK_START:
        name = element.get(W_NAME)
        if name and BOOKMARK_RE.fullmatch(name):
            bookmark_id = element.get(W_ID)
            if bookmark_id is None:
                raise ReconcileError(f"bookmark {name} tidak memiliki w:id.")
            if bookmark_id in active:
                raise ReconcileError(f"bookmark id ganda di DOCX: {bookmark_id}.")
            active[bookmark_id] = _OpenBookmark(name=name, chunks=[])
            started.append(name)
        return

    if tag == W_BOOKMARK_END:
        bookmark_id = element.get(W_ID)
        if bookmark_id in active:
            bookmark = active.pop(bookmark_id)
            closed.append((bookmark.name, "".join(bookmark.chunks)))
        return

    if tag == W_P:
        covered = bool(active) or _has_bookmark_start(element)

        for child in element:
            _walk_xml(child, active, closed, unbookmarked, started)

        # Paragraf yang dilintasi bookmark mendapat pemisah baris. Bookmark
        # yang hanya membungkus isi satu paragraf tidak menambah newline.
        if active:
            for bookmark in active.values():
                bookmark.chunks.append("\n")

        if not covered:
            text = _clean_text(_paragraph_visible_text(element))
            if text:
                unbookmarked.append(text)
        return

    if tag == W_T:
        text = element.text or ""
        if text:
            for bookmark in active.values():
                bookmark.chunks.append(text)
        return

    if tag in (W_TAB, W_PTAB):
        for bookmark in active.values():
            bookmark.chunks.append("\t")
        return

    if tag in (W_BR, W_CR):
        for bookmark in active.values():
            bookmark.chunks.append("\n")
        return

    if tag == W_NO_BREAK_HYPHEN:
        for bookmark in active.values():
            bookmark.chunks.append("\u2011")
        return

    if tag == W_SOFT_HYPHEN:
        return

    if tag in (W_DRAWING, W_PICT, W_OBJECT, W_TXBX_CONTENT):
        _walk_nested_paragraphs(element, closed, unbookmarked, started)
        return

    for child in element:
        _walk_xml(child, active, closed, unbookmarked, started)


def extract_bookmarks(docx_path: Path) -> DocxSnapshot:
    """Ekstrak teks untuk setiap bookmark ``pNNNN`` dari body DOCX."""

    try:
        document = Document(docx_path)
    except FileNotFoundError as exc:
        raise ReconcileError(f"DOCX tidak ditemukan: {docx_path}") from exc
    except (
        PackageNotFoundError,
        zipfile.BadZipFile,
        KeyError,
        OSError,
        XMLSyntaxError,
    ) as exc:
        raise ReconcileError(f"DOCX tidak dapat dibaca: {docx_path}: {exc}") from exc
    except Exception as exc:  # paket rusak dapat melempar error lxml/python-docx lain
        raise ReconcileError(f"DOCX tidak dapat dibaca: {docx_path}: {exc}") from exc

    active: dict[str, _OpenBookmark] = {}
    closed: list[tuple[str, str]] = []
    unbookmarked: list[str] = []
    started: list[str] = []

    _walk_xml(document.element.body, active, closed, unbookmarked, started)

    if active:
        names = ", ".join(sorted(bookmark.name for bookmark in active.values()))
        raise ReconcileError(f"bookmark tidak ditutup di DOCX: {names}.")

    closed_text: dict[str, str] = {}
    for name, text in closed:
        if name in closed_text:
            raise ReconcileError(f"bookmark duplikat di DOCX: {name}.")
        closed_text[name] = _clean_text(text)

    bookmarks: dict[str, str] = {}
    order: list[str] = []
    for name in started:
        if name in bookmarks:
            raise ReconcileError(f"bookmark duplikat di DOCX: {name}.")
        if name not in closed_text:
            raise ReconcileError(f"bookmark tidak ditutup di DOCX: {name}.")
        bookmarks[name] = closed_text[name]
        order.append(name)

    return DocxSnapshot(
        bookmarks=bookmarks,
        order=tuple(order),
        unbookmarked=tuple(unbookmarked),
    )


# ---------------------------------------------------------------------------
# Parser Markdown


def _plain_inline(text: str) -> str:
    """Buang markup inline agar bisa dibandingkan dengan teks DOCX."""

    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"\[\^[^\]]+\]", "", text)
    text = re.sub(r"\[@[^\]]*\]", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"(?<!\w)\*(\S(?:.*?\S)?)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(\S(?:.*?\S)?)_(?!\w)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_heading(text: str) -> str:
    """Normalisasi heading agar 'BAB II TINJAUAN PUSTAKA' cocok dengan 'TINJAUAN PUSTAKA'."""

    value = _plain_inline(text)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(
        r"(?i)^(?:bab|bagian|chapter)\s+[ivxlcdm0-9]+\b[\s.:\-–—]*", "", value
    ).strip()
    value = re.sub(r"^(?:\d+(?:\.\d+)+|\d+)[.)]?\s+", "", value).strip()
    value = re.sub(r"(?i)^[ivxlcdm]+\.\s+", "", value).strip()
    value = value.strip(" \t.:;,–—-")
    return value.casefold()


def _normalize_path(path: Sequence[str]) -> tuple[str, ...]:
    return tuple(part for part in (_normalize_heading(item) for item in path) if part)


def _normalize_for_match(text: str) -> str:
    text = _clean_text(text).replace("\u2011", "-")
    text = re.sub(r"\s+", " ", text)
    return text.casefold().strip()


def _plain_table(rows: list[str]) -> str:
    lines: list[str] = []
    for row in rows:
        if TABLE_SEPARATOR_RE.fullmatch(row):
            continue
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        lines.append(" ".join(_plain_inline(cell) for cell in cells if cell.strip()))
    return "\n".join(line for line in lines if line)


def _plain_list_item(lines: list[str]) -> str:
    first = LIST_RE.sub("", lines[0], count=1)
    rest = [line.strip() for line in lines[1:]]
    text = " ".join([first, *rest])
    text = re.sub(r"^\[[ xX]\][ \t]+", "", text)
    return _plain_inline(text)


def parse_markdown_blocks(text: str, path: Path) -> list[MarkdownBlock]:
    """Pecah Markdown menjadi blok non-kosong dengan heading_path-nya."""

    lines = text.splitlines()
    blocks: list[MarkdownBlock] = []
    heading_stack: list[tuple[int, str]] = []
    block_index = 0
    i = 0

    # Front matter YAML di awal file bukan blok isi.
    if lines and YAML_DELIMITER_RE.fullmatch(lines[0].strip()):
        for candidate in range(1, len(lines)):
            if YAML_DELIMITER_RE.fullmatch(lines[candidate].strip()):
                i = candidate + 1
                break

    def current_path() -> tuple[str, ...]:
        return tuple(raw for _, raw in heading_stack)

    def append_block(raw_text: str, line: int) -> None:
        nonlocal block_index
        plain = _plain_inline(raw_text)
        if not plain:
            return
        block_index += 1
        blocks.append(
            MarkdownBlock(
                path=path,
                index=block_index,
                heading_path=_normalize_path(current_path()),
                text=plain,
                line=line,
            )
        )

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if HORIZONTAL_RULE_RE.fullmatch(line):
            i += 1
            continue

        if FOOTNOTE_DEFINITION_RE.match(line) or LINK_DEFINITION_RE.match(line):
            i += 1
            while i < len(lines) and lines[i].startswith((" ", "\t")):
                i += 1
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_stack = [entry for entry in heading_stack if entry[0] < level]
            heading_stack.append((level, title))
            append_block(title, i + 1)
            i += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            start_line = i + 1
            i += 1
            content: list[str] = []
            while i < len(lines):
                closing = re.match(
                    rf"^[ \t]*{re.escape(fence_char)}{{{fence_length},}}[ \t]*$",
                    lines[i],
                )
                if closing:
                    i += 1
                    break
                content.append(lines[i])
                i += 1
            plain = "\n".join(content).strip()
            if plain:
                block_index += 1
                blocks.append(
                    MarkdownBlock(
                        path=path,
                        index=block_index,
                        heading_path=_normalize_path(current_path()),
                        text=plain,
                        line=start_line,
                    )
                )
            continue

        if line.lstrip().startswith("|"):
            start_line = i + 1
            rows: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            plain = _plain_table(rows)
            if plain:
                block_index += 1
                blocks.append(
                    MarkdownBlock(
                        path=path,
                        index=block_index,
                        heading_path=_normalize_path(current_path()),
                        text=plain,
                        line=start_line,
                    )
                )
            continue

        if line.lstrip().startswith(">"):
            start_line = i + 1
            quoted: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            plain = _plain_inline(" ".join(quoted))
            if plain:
                block_index += 1
                blocks.append(
                    MarkdownBlock(
                        path=path,
                        index=block_index,
                        heading_path=_normalize_path(current_path()),
                        text=plain,
                        line=start_line,
                    )
                )
            continue

        if LIST_RE.match(line):
            start_line = i + 1
            item_lines = [lines[i]]
            i += 1
            while i < len(lines):
                candidate = lines[i]
                if not candidate.strip():
                    break
                if (
                    HEADING_RE.match(candidate)
                    or FENCE_RE.match(candidate)
                    or LIST_RE.match(candidate)
                    or candidate.lstrip().startswith(("|", ">"))
                    or HORIZONTAL_RULE_RE.fullmatch(candidate)
                ):
                    break
                item_lines.append(candidate)
                i += 1
            plain = _plain_list_item(item_lines)
            if plain:
                block_index += 1
                blocks.append(
                    MarkdownBlock(
                        path=path,
                        index=block_index,
                        heading_path=_normalize_path(current_path()),
                        text=plain,
                        line=start_line,
                    )
                )
            continue

        start_line = i + 1
        paragraph_lines: list[str] = []
        while i < len(lines):
            candidate = lines[i]
            if not candidate.strip():
                break
            if (
                HEADING_RE.match(candidate)
                or FENCE_RE.match(candidate)
                or LIST_RE.match(candidate)
                or candidate.lstrip().startswith(("|", ">"))
                or HORIZONTAL_RULE_RE.fullmatch(candidate)
                or FOOTNOTE_DEFINITION_RE.match(candidate)
                or LINK_DEFINITION_RE.match(candidate)
            ):
                break
            paragraph_lines.append(candidate.strip())
            i += 1
        plain = _plain_inline(" ".join(paragraph_lines))
        if plain:
            block_index += 1
            blocks.append(
                MarkdownBlock(
                    path=path,
                    index=block_index,
                    heading_path=_normalize_path(current_path()),
                    text=plain,
                    line=start_line,
                )
            )

    return blocks


def load_chapter_blocks(chapters_dir: Path) -> list[MarkdownBlock]:
    """Baca semua ``chapters/*.md`` dalam urutan nama yang deterministik."""

    if not chapters_dir.is_dir():
        raise ReconcileError(f"direktori chapters tidak ditemukan: {chapters_dir}")

    blocks: list[MarkdownBlock] = []
    try:
        files = sorted(chapters_dir.glob("*.md"), key=lambda item: item.name.casefold())
    except OSError as exc:
        raise ReconcileError(f"tidak dapat membaca {chapters_dir}: {exc}") from exc

    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise ReconcileError(f"tidak dapat membaca {path}: {exc}") from exc
        blocks.extend(parse_markdown_blocks(text, path))

    return blocks


# ---------------------------------------------------------------------------
# Pencocokan sumber


def find_source(
    paragraph: ManifestParagraph,
    blocks: Sequence[MarkdownBlock],
    chapters_dir: Path,
) -> SourceMatch | None:
    """Cari blok Markdown sumber berdasarkan heading_path lalu difflib."""

    wanted_path = _normalize_path(paragraph.heading_path)
    if not wanted_path:
        return None

    candidates = [block for block in blocks if block.heading_path == wanted_path]

    if not candidates:
        # Manifest kadang hanya memuat sebagian jalur heading (misalnya tanpa
        # judul bab), atau sebaliknya. Cocokkan sebagai suffix yang utuh.
        candidates = [
            block
            for block in blocks
            if len(block.heading_path) >= len(wanted_path)
            and block.heading_path[-len(wanted_path) :] == wanted_path
        ]
    if not candidates:
        candidates = [
            block
            for block in blocks
            if len(wanted_path) >= len(block.heading_path)
            and wanted_path[-len(block.heading_path) :] == block.heading_path
        ]
    if not candidates:
        return None

    target = _normalize_for_match(paragraph.text)
    scored: list[tuple[float, MarkdownBlock]] = []
    for block in candidates:
        ratio = SequenceMatcher(
            None, target, _normalize_for_match(block.text), autojunk=False
        ).ratio()
        scored.append((ratio, block))

    best_ratio, best_block = max(scored, key=lambda item: (item[0], -item[1].index))
    if best_ratio < SIMILARITY_THRESHOLD:
        return None

    try:
        relative = best_block.path.resolve().relative_to(chapters_dir.resolve().parent)
        display_path = relative.as_posix()
    except (OSError, ValueError):
        display_path = best_block.path.as_posix()

    return SourceMatch(
        block=best_block,
        similarity=best_ratio,
        display_path=display_path,
    )


# ---------------------------------------------------------------------------
# Laporan


def _quote(text: str) -> str:
    value = _clean_text(text)
    if not value:
        return ">"
    return "\n".join(f"> {line}" if line else ">" for line in value.split("\n"))


def _heading_label(paragraph: ManifestParagraph) -> str:
    if not paragraph.heading_path:
        return paragraph.kind
    parts = (re.sub(r"\s+", " ", part).strip() for part in paragraph.heading_path)
    return " / ".join(part for part in parts if part) or paragraph.kind


def _protected_label(paragraph: ManifestParagraph) -> str:
    if paragraph.protected_reason:
        return f"{paragraph.kind} (protected: {paragraph.protected_reason})"
    return f"{paragraph.kind} (protected)"


def _change_section(
    paragraph: ManifestParagraph,
    before: str,
    after: str,
    source: SourceMatch | None,
) -> list[str]:
    if paragraph.protected:
        lines = [
            f"## PELANGGARAN {paragraph.id} — {_protected_label(paragraph)}",
            "",
            "**Sebelum**",
            _quote(before),
            "",
            "**Sesudah**",
            _quote(after),
            "",
            "> Blok ini tidak boleh diedit manual. Kembalikan dari build.",
        ]
        return lines

    lines = [f"## {paragraph.id} — {_heading_label(paragraph)}", ""]
    if source is not None:
        lines.append(
            f"Sumber: {source.display_path} "
            f"(blok {source.block.index}, kemiripan {source.similarity:.2f})"
        )
    else:
        lines.append(
            "**SUMBER TIDAK DITEMUKAN** — tidak ada blok Markdown yang cocok "
            "dengan heading_path dan teks lama."
        )
    lines.extend(
        [
            "",
            "**Sebelum**",
            _quote(before),
            "",
            "**Sesudah**",
            _quote(after),
            "",
            "**Saran:** terapkan ke Markdown lalu build ulang.",
        ]
    )
    return lines


def _new_bookmark_section(paragraph_id: str, text: str) -> list[str]:
    return [
        f"## PARAGRAF BARU {paragraph_id}",
        "",
        "ID ini ada di DOCX tetapi tidak ada di manifest.",
        "",
        "**Sesudah**",
        _quote(text),
    ]


def _new_unbookmarked_section(text: str) -> list[str]:
    return [
        "## PARAGRAF BARU — tanpa ID",
        "",
        "Paragraf ini tidak berada di dalam bookmark pNNNN mana pun.",
        "",
        "**Sesudah**",
        _quote(text),
    ]


def _missing_section(paragraph: ManifestParagraph) -> list[str]:
    label = _heading_label(paragraph)
    if paragraph.protected:
        return [
            f"## PELANGGARAN {paragraph.id} — {_protected_label(paragraph)}",
            "",
            "**PARAGRAF HILANG** — ID ini ada di manifest tetapi tidak ditemukan di DOCX.",
            "",
            "**Sebelum**",
            _quote(paragraph.text),
            "",
            "> Blok terlindungi ini hilang dari DOCX. Kembalikan dari build.",
        ]
    return [
        f"## PARAGRAF HILANG {paragraph.id} — {label}",
        "",
        "ID ini ada di manifest tetapi tidak ditemukan di DOCX.",
        "",
        "**Sebelum**",
        _quote(paragraph.text),
    ]


def build_report(
    snapshot: DocxSnapshot,
    paragraphs: Sequence[ManifestParagraph],
    blocks: Sequence[MarkdownBlock],
    chapters_dir: Path,
) -> ReconcileResult:
    """Susun laporan dan tentukan exit code."""

    manifest_by_id = {paragraph.id: paragraph for paragraph in paragraphs}
    docx_ids = set(snapshot.bookmarks)

    changed_paragraphs: list[tuple[ManifestParagraph, str, str]] = []
    for paragraph in paragraphs:
        if paragraph.id not in snapshot.bookmarks:
            continue
        current = snapshot.bookmarks[paragraph.id]
        if _clean_text(paragraph.text) != _clean_text(current):
            changed_paragraphs.append((paragraph, paragraph.text, current))

    protected_changes = [
        item for item in changed_paragraphs if item[0].protected
    ]
    missing_paragraphs = [
        paragraph for paragraph in paragraphs if paragraph.id not in docx_ids
    ]
    protected_missing = [paragraph for paragraph in missing_paragraphs if paragraph.protected]
    new_ids = [
        bookmark_id
        for bookmark_id in snapshot.order
        if bookmark_id not in manifest_by_id
    ]

    sections: list[list[str]] = []

    for paragraph, before, after in changed_paragraphs:
        source = None
        if not paragraph.protected:
            source = find_source(paragraph, blocks, chapters_dir)
        sections.append(_change_section(paragraph, before, after, source))

    for bookmark_id in new_ids:
        sections.append(_new_bookmark_section(bookmark_id, snapshot.bookmarks[bookmark_id]))

    for text in snapshot.unbookmarked:
        sections.append(_new_unbookmarked_section(text))

    for paragraph in missing_paragraphs:
        sections.append(_missing_section(paragraph))

    violations = len(protected_changes) + len(protected_missing)
    changed_count = len(changed_paragraphs)

    lines = [
        "# Edit Manual",
        "",
        "## Ringkasan",
        f"- Diperiksa: {len(paragraphs)} paragraf",
        f"- Berubah: {changed_count}",
        f"- Dilindungi & dilanggar: {violations}",
    ]

    for position, section in enumerate(sections):
        lines.append("")
        if position:
            lines.append("---")
            lines.append("")
        lines.extend(section)

    report = "\n".join(lines).rstrip("\n") + "\n"

    if violations:
        exit_code = 3
    elif changed_count or new_ids or snapshot.unbookmarked or missing_paragraphs:
        exit_code = 2
    else:
        exit_code = 0

    return ReconcileResult(
        report=report,
        exit_code=exit_code,
        checked=len(paragraphs),
        changed=changed_count,
        violations=violations,
    )


def write_report(path: Path, report: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(report.encode("utf-8"))
    except OSError as exc:
        raise ReconcileError(f"laporan tidak dapat ditulis ke {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# CLI


class _Parser(argparse.ArgumentParser):
    """Argparse yang tidak memakai exit code 2 (2 berarti ada perubahan)."""

    def error(self, message: str) -> None:  # pragma: no cover - dipanggil argparse
        raise ReconcileError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="reconcile.py",
        description=(
            "Rekonsiliasi edit manual DOCX dengan manifest paragraf dan "
            "sumber Markdown. Hanya menulis laporan, tidak mengubah sumber."
        ),
    )
    parser.add_argument("--docx", required=True, type=Path, help="DOCX hasil edit.")
    parser.add_argument(
        "--manifest", required=True, type=Path, help="manifest.json hasil build."
    )
    parser.add_argument(
        "--chapters",
        required=True,
        type=Path,
        help="Direktori berisi chapters/*.md.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Lokasi laporan Markdown, misalnya review/manual-edits.md.",
    )
    return parser


def run(
    docx_path: Path,
    manifest_path: Path,
    chapters_dir: Path,
    out_path: Path,
) -> ReconcileResult:
    """Jalankan rekonsiliasi lengkap dan tulis laporan."""

    paragraphs = load_manifest(manifest_path)
    if not chapters_dir.is_dir():
        raise ReconcileError(f"direktori chapters tidak ditemukan: {chapters_dir}")

    # Alat ini tidak boleh menulis apa pun ke sumber Markdown dan tidak boleh
    # menimpa DOCX atau manifest yang menjadi input.
    try:
        out_resolved = out_path.resolve()
        docx_resolved = docx_path.resolve()
        manifest_resolved = manifest_path.resolve()
        chapters_resolved = chapters_dir.resolve()
    except OSError as exc:
        raise ReconcileError(f"path tidak dapat diselesaikan: {exc}") from exc
    if out_resolved in (docx_resolved, manifest_resolved):
        raise ReconcileError(
            "--out tidak boleh menimpa --docx atau --manifest; "
            "gunakan review/manual-edits.md."
        )
    if out_path.suffix.lower() != ".md":
        raise ReconcileError(
            "--out harus berekstensi .md; gunakan review/manual-edits.md."
        )
    if out_resolved == chapters_resolved or chapters_resolved in out_resolved.parents:
        raise ReconcileError(
            "--out tidak boleh berada di dalam direktori chapters; "
            "gunakan review/manual-edits.md."
        )

    snapshot = extract_bookmarks(docx_path)
    blocks = load_chapter_blocks(chapters_dir)
    result = build_report(snapshot, paragraphs, blocks, chapters_dir)
    write_report(out_path, result.report)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help
        return int(exc.code or 0)
    except ReconcileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        result = run(args.docx, args.manifest, args.chapters, args.out)
    except ReconcileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Diperiksa {result.checked} paragraf; berubah {result.changed}; "
        f"pelanggaran {result.violations}. Laporan: {args.out}"
    )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
