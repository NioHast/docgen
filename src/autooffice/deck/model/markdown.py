"""Parser inline Markdown dan normalisasi teks deck AutoOffice v1.

Hanya sintaks yang dibekukan pada kontrak deck-schema yang diterima: bold,
inline code, link http/https/mailto, dan escape terbatas. Italic, heading,
list, tabel, blockquote, gambar, HTML, dan footnote ditolak dengan error
eksplisit, bukan diperlakukan sebagai teks biasa secara diam-diam.
"""

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from autooffice.errors import AutoOfficeError

_ESCAPE_TARGETS = frozenset("*_`[]")
_ALLOWED_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
_DASH_CHARACTERS = frozenset({"\u2013", "\u2014"})
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_HEADING_PATTERN = re.compile(r"^#{1,6}\s")
_LIST_PATTERN = re.compile(r"^(?:[-*+]|\d+[.)])\s")
_BLOCKQUOTE_PATTERN = re.compile(r"^>\s")
_HTML_PATTERN = re.compile(r"<!--|</?[A-Za-z][^>]*>")
_TABLE_SEPARATOR_PATTERN = re.compile(r"^\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{0,}:?\s*$")
_LINK_PATTERN = re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)")
_BOLD_PATTERN = re.compile(r"\*\*[^*\n]+\*\*")
_ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\*)[^*\n]+\*(?!\*)")


class MarkdownError(AutoOfficeError):
    """Nilai teks tidak memenuhi kontrak inline Markdown."""


@dataclass(frozen=True, slots=True)
class TextSegment:
    """Satu run teks hasil parsing inline Markdown."""

    text: str
    bold: bool = False
    code: bool = False
    link: str | None = None


@dataclass(frozen=True, slots=True)
class InlineMarkdown:
    """Hasil parsing satu nilai inline Markdown."""

    source: str
    plain_text: str
    segments: tuple[TextSegment, ...]


def parse_inline(value: str, *, field: str = "text", multiline: bool = True) -> InlineMarkdown:
    """Parse inline Markdown dan kembalikan nilai sumber, plain text, dan run."""
    if not isinstance(value, str):
        raise MarkdownError(f"{field} harus string.")
    source = _normalize_newlines(value)
    _reject_invisible_text(source, field)
    if not multiline and "\n" in source:
        raise MarkdownError(f"{field} harus satu baris.")
    _reject_block_syntax(source, field)
    segments = tuple(_parse_segments(source, field=field, bold=False))
    plain_text = _normalize_whitespace(
        "".join(segment.text for segment in segments),
        field=field,
        multiline=multiline,
    )
    _reject_invisible_text(plain_text, field)
    _reject_dashes(plain_text, field)
    return InlineMarkdown(source=source, plain_text=plain_text, segments=segments)


def normalize_inline(value: str, *, field: str = "text", multiline: bool = True) -> str:
    """Kembalikan plain text hasil parsing inline Markdown."""
    return parse_inline(value, field=field, multiline=multiline).plain_text


def validate_plain_text(value: str, *, field: str = "text", multiline: bool = False) -> str:
    """Validasi field plain text yang tidak boleh memuat sintaks Markdown."""
    if not isinstance(value, str):
        raise MarkdownError(f"{field} harus string.")
    text = _normalize_newlines(value)
    _reject_invisible_text(text, field)
    if not multiline and "\n" in text:
        raise MarkdownError(f"{field} harus satu baris.")
    _reject_block_syntax(text, field)
    _reject_plain_markup(text, field)
    plain_text = _normalize_whitespace(text, field=field, multiline=multiline)
    _reject_invisible_text(plain_text, field)
    _reject_dashes(plain_text, field)
    return plain_text


def normalize_preserve_newlines(
    value: str,
    *,
    field: str = "text",
    multiline: bool = True,
) -> str:
    """Normalisasi nilai preserve-newline untuk ``notes`` dan ``code``."""
    if not isinstance(value, str):
        raise MarkdownError(f"{field} harus string.")
    text = _normalize_newlines(value)
    _reject_invisible_text(text, field)
    lines = text.split("\n")
    if not multiline and len(lines) > 1:
        raise MarkdownError(f"{field} harus satu baris.")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise MarkdownError(f"{field} tidak boleh kosong.")
    return "\n".join(lines)


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _reject_invisible_text(text: str, field: str) -> None:
    if _CONTROL_PATTERN.search(text):
        raise MarkdownError(f"{field} tidak boleh memuat karakter kontrol.")
    visible = [character for character in text if not character.isspace()]
    if visible and all(unicodedata.category(character) == "Cf" for character in visible):
        raise MarkdownError(f"{field} tidak boleh hanya memuat karakter tak terlihat (zero-width).")


def _normalize_whitespace(text: str, *, field: str, multiline: bool) -> str:
    lines = [_collapse_horizontal_whitespace(line) for line in text.split("\n")]
    plain_text = "\n".join(lines).strip()
    if not multiline and "\n" in plain_text:
        raise MarkdownError(f"{field} harus satu baris.")
    if not plain_text:
        raise MarkdownError(f"{field} tidak boleh kosong.")
    return plain_text


def _collapse_horizontal_whitespace(line: str) -> str:
    return re.sub(r"[ \t\f\v]+", " ", line).strip()


def _reject_dashes(plain_text: str, field: str) -> None:
    for character in plain_text:
        if character in _DASH_CHARACTERS:
            raise MarkdownError(
                f"{field} tidak boleh memakai em dash atau en dash; pakai tanda hubung biasa."
            )


def _reject_block_syntax(text: str, field: str) -> None:
    for line in text.split("\n"):
        stripped = line.lstrip()
        if _HEADING_PATTERN.match(stripped):
            raise MarkdownError(f"{field} tidak boleh memakai heading Markdown.")
        if _LIST_PATTERN.match(stripped):
            raise MarkdownError(f"{field} tidak boleh memakai list Markdown; pakai block bullets.")
        if _BLOCKQUOTE_PATTERN.match(stripped):
            raise MarkdownError(f"{field} tidak boleh memakai blockquote Markdown.")
        if _looks_like_table(stripped):
            raise MarkdownError(f"{field} tidak boleh memakai table Markdown.")
        if _HTML_PATTERN.search(line):
            raise MarkdownError(f"{field} tidak boleh memakai HTML mentah.")


def _looks_like_table(stripped: str) -> bool:
    if stripped.count("|") >= 2 and (stripped.startswith("|") or stripped.endswith("|")):
        return True
    return _TABLE_SEPARATOR_PATTERN.match(stripped) is not None


def _reject_plain_markup(text: str, field: str) -> None:
    if re.search(r"\[\^[^\]\n]+\]", text):
        raise MarkdownError(f"{field} adalah plain text dan tidak boleh memakai footnote.")
    if "`" in text:
        raise MarkdownError(f"{field} adalah plain text dan tidak boleh memakai inline code.")
    if _BOLD_PATTERN.search(text) or "**" in text:
        raise MarkdownError(f"{field} adalah plain text dan tidak boleh memakai bold Markdown.")
    if _ITALIC_PATTERN.search(text):
        raise MarkdownError(f"{field} adalah plain text dan tidak boleh memakai italic Markdown.")
    if _LINK_PATTERN.search(text):
        raise MarkdownError(
            f"{field} adalah plain text dan tidak boleh memakai Markdown link/image."
        )


def _parse_segments(text: str, *, field: str, bold: bool) -> list[TextSegment]:
    segments: list[TextSegment] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            segments.append(TextSegment("".join(buffer), bold=bold))
            buffer.clear()

    index = 0
    while index < len(text):
        if text[index] == "\\":
            escaped, index = _parse_escape(text, index, field)
            buffer.append(escaped)
            continue
        if text.startswith("**", index):
            flush()
            closing = _find_unescaped(text, "**", index + 2)
            if closing < 0:
                raise MarkdownError(f"{field} memiliki bold Markdown yang tidak ditutup.")
            inner = text[index + 2 : closing]
            if not inner:
                raise MarkdownError(f"{field} memiliki bold Markdown kosong.")
            segments.extend(_parse_segments(inner, field=field, bold=True))
            index = closing + 2
            continue
        if text[index] == "*":
            if _has_single_star(text, index + 1):
                raise MarkdownError(
                    f"{field} tidak mendukung italic; hanya bold, inline code, dan link."
                )
            buffer.append("*")
            index += 1
            continue
        if text[index] == "`":
            flush()
            closing = text.find("`", index + 1)
            if closing < 0:
                raise MarkdownError(f"{field} memiliki inline code yang tidak ditutup.")
            content = text[index + 1 : closing]
            if not content:
                raise MarkdownError(f"{field} memiliki inline code kosong.")
            if "\n" in content:
                raise MarkdownError(f"{field} inline code harus satu baris.")
            segments.append(TextSegment(content, bold=bold, code=True))
            index = closing + 1
            continue
        if text.startswith("![", index):
            raise MarkdownError(f"{field} tidak boleh memakai gambar Markdown.")
        if text[index] == "[":
            flush()
            segment, index = _parse_link(text, index, field=field, bold=bold)
            segments.append(segment)
            continue
        if text[index] == "<" and _HTML_PATTERN.match(text, index) is not None:
            raise MarkdownError(f"{field} tidak boleh memakai HTML mentah.")
        buffer.append(text[index])
        index += 1
    flush()
    return segments


def _find_unescaped(text: str, needle: str, start: int) -> int:
    index = text.find(needle, start)
    while index >= 0:
        backslashes = 0
        position = index - 1
        while position >= 0 and text[position] == "\\":
            backslashes += 1
            position -= 1
        if backslashes % 2 == 0:
            return index
        index = text.find(needle, index + 1)
    return -1


def _parse_escape(text: str, index: int, field: str) -> tuple[str, int]:
    if index + 1 >= len(text):
        raise MarkdownError(f"{field} memiliki escape '\\' tanpa karakter tujuan.")
    escaped = text[index + 1]
    if escaped not in _ESCAPE_TARGETS:
        raise MarkdownError(f"{field} memiliki escape '\\{escaped}' yang tidak didukung.")
    return escaped, index + 2


def _has_single_star(text: str, start: int) -> bool:
    index = text.find("*", start)
    while index >= 0:
        is_double = (index > 0 and text[index - 1] == "*") or (
            index + 1 < len(text) and text[index + 1] == "*"
        )
        if not is_double:
            return True
        index = text.find("*", index + 1)
    return False


def _parse_link(text: str, index: int, *, field: str, bold: bool) -> tuple[TextSegment, int]:
    label_end = _find_unescaped(text, "]", index + 1)
    if label_end < 0:
        raise MarkdownError(f"{field} memiliki link yang tidak ditutup.")
    if label_end + 1 >= len(text) or text[label_end + 1] != "(":
        raise MarkdownError(f"{field} hanya mendukung inline link '[label](url)'.")
    label = text[index + 1 : label_end]
    if not label:
        raise MarkdownError(f"{field} memiliki label link kosong.")
    if "\n" in label:
        raise MarkdownError(f"{field} label link harus satu baris.")
    url, end = _scan_link_target(text, label_end + 2, field=field)
    url = url.strip()
    _validate_link_url(url, field)
    return TextSegment(_unescape_label(label, field), bold=bold, link=url), end


def _scan_link_target(text: str, start: int, *, field: str) -> tuple[str, int]:
    depth = 0
    index = start
    characters: list[str] = []
    while index < len(text):
        character = text[index]
        if character == "\\":
            if index + 1 >= len(text):
                raise MarkdownError(f"{field} memiliki escape '\\' tanpa karakter tujuan.")
            characters.append(text[index : index + 2])
            index += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return _unescape_link_target("".join(characters)), index + 1
            depth -= 1
        characters.append(character)
        index += 1
    raise MarkdownError(f"{field} memiliki URL link yang tidak ditutup.")


def _unescape_link_target(target: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(target):
        if target[index] == "\\" and index + 1 < len(target) and target[index + 1] in "()":
            result.append(target[index + 1])
            index += 2
            continue
        result.append(target[index])
        index += 1
    return "".join(result)


def _unescape_label(label: str, field: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(label):
        if label[index] == "\\":
            escaped, index = _parse_escape(label, index, field)
            result.append(escaped)
            continue
        if label[index] in "[*`":
            raise MarkdownError(f"{field} label link hanya boleh plain text dan escape.")
        result.append(label[index])
        index += 1
    return "".join(result)


def _validate_link_url(url: str, field: str) -> None:
    if not url or any(character.isspace() for character in url):
        raise MarkdownError(f"{field} memiliki URL link kosong atau memuat spasi.")
    scheme, separator, remainder = url.partition(":")
    if not separator or scheme.lower() not in _ALLOWED_LINK_SCHEMES:
        raise MarkdownError(f"{field} hanya menerima link http, https, atau mailto.")
    if not remainder:
        raise MarkdownError(f"{field} memiliki URL link tanpa tujuan.")
    if scheme.lower() in {"http", "https"}:
        if not remainder.startswith("//"):
            raise MarkdownError(f"{field} URL http/https harus memakai format https://.")
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
        except ValueError as error:
            raise MarkdownError(f"{field} memiliki URL link yang tidak valid: {error}.") from error
        if hostname is None:
            raise MarkdownError(f"{field} URL http/https harus memiliki host.")
