"""Ubah teks Markdown menjadi teks tampil untuk copy checker.

Copy checker memeriksa teks yang benar-benar terlihat pembaca. Link inline
dipertahankan sebagai label, sedangkan tujuan link, autolink, URL telanjang,
penanda daftar, penanda emphasis, dan backtick kode dibuang. Setiap karakter
pada hasil membawa indeks karakter asal agar pemetaan baris tetap masuk akal.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

_AUTOLINK = re.compile(r"<https?://[^>\s]+>", re.IGNORECASE)
# Karakter URL aman tanpa penanda Markdown: kutip, kurung, `*`, `_`, backtick,
# `]`, dan `}` tidak ikut ditelan. Karakter akhir membuang tanda baca kalimat.
_BARE_URL = re.compile(
    r"(?i)\b(?:https?://|www\.)"
    r"[A-Za-z0-9\-.:/?#@!$&+,;=%]*"
    r"[A-Za-z0-9\-:/?#@$&+=%]"
)
_LIST_MARKER = re.compile(r"(?m)^[ \t]*(?:[-*+]|\d+[.)])(?:[ \t]+|$)")
_EMPHASIS_OR_CODE = re.compile(r"(?<!\w)[*_~`]+|[*_~`]+(?!\w)")

_Replacement = Callable[[re.Match[str], str, list[int]], tuple[str, list[int]]]


@dataclass(frozen=True, slots=True)
class VisibleText:
    """Teks tampil beserta peta offset ke teks asal."""

    text: str
    offsets: tuple[int, ...]

    def original_offset(self, offset: int) -> int:
        """Kembalikan indeks pada teks asal untuk satu offset teks tampil."""
        if 0 <= offset < len(self.offsets):
            return self.offsets[offset]
        if offset == len(self.offsets) and self.offsets:
            return self.offsets[-1] + 1
        return offset


def render_visible_text(text: str) -> VisibleText:
    """Hasilkan teks tampil yang bebas penanda Markdown umum."""
    rendered, offsets = _replace_inline_links(text, list(range(len(text))))
    for pattern, replace in (
        (_AUTOLINK, _remove),
        (_BARE_URL, _remove),
        (_LIST_MARKER, _remove),
        (_EMPHASIS_OR_CODE, _remove),
    ):
        rendered, offsets = _replace(rendered, offsets, pattern, replace)
    return VisibleText(text=rendered, offsets=tuple(offsets))


def _replace_inline_links(
    text: str,
    offsets: list[int],
) -> tuple[str, list[int]]:
    """Ganti setiap inline link dengan labelnya memakai pemindai berimbang."""
    pieces: list[str] = []
    mapped: list[int] = []
    cursor = 0
    index = 0
    while index < len(text):
        scanned = _scan_inline_link(text, index)
        if scanned is None:
            index += 1
            continue
        bracket, label_end, end = scanned
        pieces.append(text[cursor:index])
        mapped.extend(offsets[cursor:index])
        pieces.append(text[bracket + 1 : label_end])
        mapped.extend(offsets[bracket + 1 : label_end])
        cursor = end
        index = end
    pieces.append(text[cursor:])
    mapped.extend(offsets[cursor:])
    return "".join(pieces), mapped


def _scan_inline_link(text: str, index: int) -> tuple[int, int, int] | None:
    """Kembalikan posisi bracket, akhir label, dan akhir link bila valid."""
    if text[index] == "!":
        if index + 1 >= len(text) or text[index + 1] != "[":
            return None
        bracket = index + 1
    elif text[index] == "[":
        bracket = index
    else:
        return None
    label_end = _find_unescaped(text, "]", bracket + 1)
    if label_end < 0 or label_end + 1 >= len(text) or text[label_end + 1] != "(":
        return None
    target_end = _scan_link_target_end(text, label_end + 2)
    if target_end < 0:
        return None
    return bracket, label_end, target_end


def _find_unescaped(text: str, needle: str, start: int) -> int:
    """Cari ``needle`` yang tidak didahului backslash ganjil."""
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


def _scan_link_target_end(text: str, start: int) -> int:
    """Pindai tujuan link dengan kurung berimbang; -1 bila tidak ditutup."""
    depth = 0
    index = start
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return index + 1
            depth -= 1
        index += 1
    return -1


def _replace(
    text: str,
    offsets: list[int],
    pattern: re.Pattern[str],
    replace: _Replacement,
) -> tuple[str, list[int]]:
    pieces: list[str] = []
    mapped: list[int] = []
    cursor = 0
    for match in pattern.finditer(text):
        pieces.append(text[cursor : match.start()])
        mapped.extend(offsets[cursor : match.start()])
        value, value_offsets = replace(match, text, offsets)
        pieces.append(value)
        mapped.extend(value_offsets)
        cursor = match.end()
    pieces.append(text[cursor:])
    mapped.extend(offsets[cursor:])
    return "".join(pieces), mapped


def _remove(
    match: re.Match[str],
    text: str,
    offsets: list[int],
) -> tuple[str, list[int]]:
    return "", []


__all__ = ["VisibleText", "render_visible_text"]
