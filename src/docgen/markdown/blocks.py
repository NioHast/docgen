"""Parser Markdown bersama untuk fitur non-Pandoc.

Parser ini menghasilkan blok non-kosong dengan ``heading_path`` yang sudah
dinormalisasi. Dipakai oleh Adeu untuk dua kebutuhan sekaligus:

- injeksi ID paragraf mencari blok sumber Markdown;
- rekonsiliasi membandingkan teks DOCX dengan blok sumber.

Tidak ada parser Markdown kedua di fitur Adeu. Format yang didukung sengaja
terbatas pada blok yang relevan untuk pencocokan paragraf: heading, paragraf,
list, blockquote, tabel, dan blok kode berpagar.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import DocgenError

HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LIST_RE = re.compile(r"^ {0,3}(?:[-*+]|\d+[.)])[ \t]+")
TABLE_RE = re.compile(r"^ {0,3}\|")
QUOTE_RE = re.compile(r"^ {0,3}>")
HORIZONTAL_RULE_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
FOOTNOTE_DEFINITION_RE = re.compile(r"^ {0,3}\[\^[^\]]+\]:")
LINK_DEFINITION_RE = re.compile(r"^ {0,3}\[[^\]]+\]:[ \t]*\S+")
YAML_DELIMITER_RE = re.compile(r"^(---|\.\.\.)\s*$")
CHECKBOX_RE = re.compile(r"^\[[ xX]\][ \t]+")

_INLINE_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REFERENCE_LINK_RE = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")
_FOOTNOTE_REF_RE = re.compile(r"\[\^[^\]]+\]")
_CITATION_RE = re.compile(r"\[@[^\]]*\]")
_CODE_SPAN_RE = re.compile(r"`([^`]*)`")
_STRONG_STAR_RE = re.compile(r"\*\*(.+?)\*\*")
_STRONG_UNDERSCORE_RE = re.compile(r"__(.+?)__")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_EM_STAR_RE = re.compile(r"(?<!\w)\*(\S(?:.*?\S)?)\*(?!\w)")
_EM_UNDERSCORE_RE = re.compile(r"(?<!\w)_(\S(?:.*?\S)?)_(?!\w)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")
_HEADING_NUMBER_RE = re.compile(
    r"(?i)^(?:bab|bagian|chapter)\s+[ivxlcdm0-9]+\b[\s.:\-\u2013\u2014]*"
)
_DOTTED_NUMBER_RE = re.compile(r"^(?:\d+(?:\.\d+)+|\d+)[.)]?\s+")
_ROMAN_NUMBER_RE = re.compile(r"(?i)^[ivxlcdm]+\.\s+")
_HEADING_TRIM = " \t.:;,\u2013\u2014-"
_TABLE_SEPARATOR_CELL_RE = re.compile(r":?-{3,}:?")


class MarkdownError(DocgenError):
    """Markdown tidak dapat dibaca atau bukan berkas yang didukung."""

    default_code = "MARKDOWN"


@dataclass(frozen=True)
class MarkdownBlock:
    """Satu blok Markdown non-kosong dalam urutan dokumen."""

    path: Path
    index: int
    heading_path: tuple[str, ...]
    text: str
    line: int
    kind: str = "paragraph"
    heading_level: int | None = None
    cells: tuple[str, ...] = field(default_factory=tuple)


def clean_text(text: str) -> str:
    """Normalisasi aman untuk teks DOCX dan Markdown."""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2011", "-")
    return text.strip()


def normalize_inline(text: str) -> str:
    """Buang markup inline agar teks Markdown sebanding dengan teks DOCX."""

    text = clean_text(text)
    text = _INLINE_IMAGE_RE.sub(r"\1", text)
    text = _INLINE_LINK_RE.sub(r"\1", text)
    text = _REFERENCE_LINK_RE.sub(r"\1", text)
    text = _FOOTNOTE_REF_RE.sub("", text)
    text = _CITATION_RE.sub("", text)
    text = _CODE_SPAN_RE.sub(r"\1", text)
    text = _STRONG_STAR_RE.sub(r"\1", text)
    text = _STRONG_UNDERSCORE_RE.sub(r"\1", text)
    text = _STRIKE_RE.sub(r"\1", text)
    text = _EM_STAR_RE.sub(r"\1", text)
    text = _EM_UNDERSCORE_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _ESCAPE_RE.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Nama lama dipertahankan agar pemanggil lama tidak perlu menulis ulang.
plain_inline = normalize_inline


def normalize_heading(text: str) -> str:
    """Normalisasi heading untuk pencocokan lintas nomor bab/subbab."""

    value = normalize_inline(text)
    value = _HEADING_NUMBER_RE.sub("", value).strip()
    value = _DOTTED_NUMBER_RE.sub("", value).strip()
    value = _ROMAN_NUMBER_RE.sub("", value).strip()
    value = value.strip(_HEADING_TRIM).strip()
    return value.casefold()


def normalize_path(path: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Normalisasi seluruh komponen ``heading_path`` dan buang yang kosong."""

    return tuple(
        normalized for normalized in (normalize_heading(item) for item in path) if normalized
    )


def normalize_for_match(text: str) -> str:
    """Normalisasi akhir untuk perbandingan teks DOCX vs blok Markdown."""

    text = clean_text(text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold().strip()


def split_table_cells(line: str) -> list[str]:
    """Pecah satu baris tabel Markdown, menghormati pipe yang di-escape."""

    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
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


def is_table_separator(line: str) -> bool:
    """True bila baris adalah baris pemisah header tabel Markdown."""

    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = split_table_cells(line)
    return bool(cells) and all(
        _TABLE_SEPARATOR_CELL_RE.fullmatch(cell) is not None for cell in cells
    )


def _plain_list_item(lines: list[str]) -> str:
    first = LIST_RE.sub("", lines[0], count=1)
    rest = [line.strip() for line in lines[1:]]
    text = " ".join([first, *rest])
    text = CHECKBOX_RE.sub("", text)
    return normalize_inline(text)


def _append(
    blocks: list[MarkdownBlock],
    *,
    path: Path,
    heading_path: tuple[str, ...],
    text: str,
    line: int,
    kind: str,
    heading_level: int | None = None,
    cells: tuple[str, ...] = (),
) -> None:
    if not text.strip():
        return
    blocks.append(
        MarkdownBlock(
            path=path,
            index=len(blocks) + 1,
            heading_path=heading_path,
            text=text,
            line=line,
            kind=kind,
            heading_level=heading_level,
            cells=cells,
        )
    )


def _front_matter_end(lines: list[str]) -> int:
    if not lines:
        return 0
    first = lines[0].lstrip("\ufeff").strip()
    if first != "---":
        return 0
    for index in range(1, len(lines)):
        if YAML_DELIMITER_RE.fullmatch(lines[index].strip()):
            return index + 1
    return 0


def parse_markdown_blocks(text: str, path: str | Path) -> list[MarkdownBlock]:
    """Pecah Markdown menjadi blok non-kosong dengan ``heading_path``."""

    source = Path(path)
    lines = text.splitlines()
    blocks: list[MarkdownBlock] = []
    heading_stack: list[tuple[int, str]] = []
    index = _front_matter_end(lines)

    def current_path() -> tuple[str, ...]:
        return tuple(raw for _, raw in heading_stack)

    while index < len(lines):
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        if HORIZONTAL_RULE_RE.fullmatch(line):
            index += 1
            continue

        if FOOTNOTE_DEFINITION_RE.match(line) or LINK_DEFINITION_RE.match(line):
            index += 1
            while index < len(lines) and lines[index].startswith((" ", "\t")):
                index += 1
            continue

        heading = HEADING_RE.match(line)
        if heading is not None:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_stack = [entry for entry in heading_stack if entry[0] < level]
            heading_stack.append((level, title))
            _append(
                blocks,
                path=source,
                heading_path=normalize_path(current_path()),
                text=normalize_inline(title),
                line=index + 1,
                kind="heading",
                heading_level=level,
            )
            index += 1
            continue

        fence = FENCE_RE.match(line)
        if fence is not None:
            marker = fence.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            start_line = index + 1
            index += 1
            content: list[str] = []
            while index < len(lines):
                closing = re.match(
                    rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*$",
                    lines[index],
                )
                if closing is not None:
                    index += 1
                    break
                content.append(lines[index])
                index += 1
            _append(
                blocks,
                path=source,
                heading_path=normalize_path(current_path()),
                text=clean_text("\n".join(content)),
                line=start_line,
                kind="code",
            )
            continue

        if TABLE_RE.match(line):
            start_line = index + 1
            rows: list[str] = []
            while index < len(lines) and TABLE_RE.match(lines[index]):
                rows.append(lines[index])
                index += 1
            text_rows: list[str] = []
            all_cells: list[str] = []
            for row in rows:
                if is_table_separator(row):
                    continue
                cells = split_table_cells(row)
                plain_cells = [normalize_inline(cell) for cell in cells]
                plain_cells = [cell for cell in plain_cells if cell]
                all_cells.extend(plain_cells)
                if plain_cells:
                    text_rows.append(" ".join(plain_cells))
            _append(
                blocks,
                path=source,
                heading_path=normalize_path(current_path()),
                text="\n".join(text_rows),
                line=start_line,
                kind="table",
                cells=tuple(all_cells),
            )
            continue

        if QUOTE_RE.match(line):
            start_line = index + 1
            quoted: list[str] = []
            while index < len(lines) and QUOTE_RE.match(lines[index]):
                quoted.append(re.sub(r"^ {0,3}>\s?", "", lines[index]))
                index += 1
            _append(
                blocks,
                path=source,
                heading_path=normalize_path(current_path()),
                text=normalize_inline(" ".join(quoted)),
                line=start_line,
                kind="quote",
            )
            continue

        if LIST_RE.match(line):
            start_line = index + 1
            item_lines = [lines[index]]
            index += 1
            while index < len(lines):
                candidate = lines[index]
                if not candidate.strip():
                    break
                if (
                    HEADING_RE.match(candidate)
                    or FENCE_RE.match(candidate)
                    or LIST_RE.match(candidate)
                    or TABLE_RE.match(candidate)
                    or QUOTE_RE.match(candidate)
                    or HORIZONTAL_RULE_RE.fullmatch(candidate)
                    or FOOTNOTE_DEFINITION_RE.match(candidate)
                    or LINK_DEFINITION_RE.match(candidate)
                ):
                    break
                item_lines.append(candidate)
                index += 1
            _append(
                blocks,
                path=source,
                heading_path=normalize_path(current_path()),
                text=_plain_list_item(item_lines),
                line=start_line,
                kind="list",
            )
            continue

        start_line = index + 1
        paragraph_lines: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip():
                break
            if (
                HEADING_RE.match(candidate)
                or FENCE_RE.match(candidate)
                or LIST_RE.match(candidate)
                or TABLE_RE.match(candidate)
                or QUOTE_RE.match(candidate)
                or HORIZONTAL_RULE_RE.fullmatch(candidate)
                or FOOTNOTE_DEFINITION_RE.match(candidate)
                or LINK_DEFINITION_RE.match(candidate)
            ):
                break
            paragraph_lines.append(candidate.strip())
            index += 1
        _append(
            blocks,
            path=source,
            heading_path=normalize_path(current_path()),
            text=normalize_inline(" ".join(paragraph_lines)),
            line=start_line,
            kind="paragraph",
        )

    return blocks


def load_markdown_blocks(path: str | Path) -> list[MarkdownBlock]:
    """Baca satu berkas Markdown lalu parse menjadi blok."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise MarkdownError(
            f"berkas Markdown tidak ditemukan: {source}",
            code="MARKDOWN-MISSING",
            path=source,
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise MarkdownError(
            f"berkas Markdown tidak dapat dibaca: {exc}",
            code="MARKDOWN-IO",
            path=source,
        ) from exc
    return parse_markdown_blocks(text, source)


def load_markdown_directory(
    directory: str | Path,
    *,
    pattern: str = "*.md",
) -> list[MarkdownBlock]:
    """Baca semua Markdown dalam direktori secara deterministik."""

    root = Path(directory)
    if not root.is_dir():
        raise MarkdownError(
            f"direktori Markdown tidak ditemukan: {root}",
            code="MARKDOWN-DIR",
            path=root,
        )
    blocks: list[MarkdownBlock] = []
    try:
        paths = sorted(
            (path for path in root.rglob(pattern) if path.is_file()),
            key=lambda item: item.as_posix().casefold(),
        )
    except OSError as exc:
        raise MarkdownError(
            f"direktori Markdown tidak dapat dibaca: {exc}",
            code="MARKDOWN-DIR",
            path=root,
        ) from exc

    for path in paths:
        blocks.extend(load_markdown_blocks(path))
    return blocks


def iter_candidate_texts(block: MarkdownBlock) -> tuple[str, ...]:
    """Teks yang bisa dipakai untuk mencocokkan satu paragraf DOCX.

    Sel tabel dipakai satu per satu karena DOCX menyimpan setiap sel sebagai
    paragraf sendiri. Blok lain memakai teks utuh.
    """

    if block.kind == "table" and block.cells:
        return block.cells
    return (block.text,)


__all__ = [
    "FENCE_RE",
    "FOOTNOTE_DEFINITION_RE",
    "HEADING_RE",
    "HORIZONTAL_RULE_RE",
    "LINK_DEFINITION_RE",
    "LIST_RE",
    "QUOTE_RE",
    "TABLE_RE",
    "MarkdownBlock",
    "MarkdownError",
    "clean_text",
    "is_table_separator",
    "iter_candidate_texts",
    "load_markdown_blocks",
    "load_markdown_directory",
    "normalize_for_match",
    "normalize_heading",
    "normalize_inline",
    "normalize_path",
    "parse_markdown_blocks",
    "plain_inline",
    "split_table_cells",
]
