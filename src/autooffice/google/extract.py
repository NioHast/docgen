"""Ekstraksi teks Slides menjadi key datar AutoOffice.

Modul ini murni dan tidak memanggil Google API sehingga bisa diuji dengan
snapshot fake. Identitas teks adalah title shape (key datar), placeholder tabel
(namespace block), dan notes page key.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from autooffice.deck.model import KeyGrammarError, parse_key

from . import GoogleSyncError
from .slides import (
    TABLE_MARKER_PREFIX,
    PageElement,
    PresentationSnapshot,
    SlideSnapshot,
    slide_id_for_index,
    table_namespace,
)

TextKind = Literal["text", "table_cell", "notes", "source"]
_PRESENTATION_PATTERNS = (
    re.compile(r"/presentation/d/e/([A-Za-z0-9_-]+)"),
    re.compile(r"/presentation/(?:u/\d+/)?d/([A-Za-z0-9_-]+)"),
    re.compile(r"/d/([A-Za-z0-9_-]+)"),
    re.compile(r"[?&]id=([A-Za-z0-9_-]+)"),
)


@dataclass(frozen=True, slots=True)
class TextEntry:
    """Satu nilai teks remote beserta key dan posisi slide aktualnya."""

    key: str
    slide_id: str
    text: str
    kind: TextKind
    slide_index: int = -1

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise GoogleSyncError("TextEntry key tidak boleh kosong.")
        if not self.slide_id.strip():
            raise GoogleSyncError(f"TextEntry '{self.key}' tidak memiliki slide_id.")
        if isinstance(self.slide_index, bool) or not isinstance(self.slide_index, int):
            raise GoogleSyncError(f"TextEntry '{self.key}' slide_index harus integer.")
        if self.slide_index < -1:
            raise GoogleSyncError(f"TextEntry '{self.key}' slide_index tidak valid.")


@dataclass(frozen=True, slots=True)
class PulledText:
    """Seluruh teks remote satu presentasi dalam urutan deterministik."""

    presentation_id: str
    revision_id: str | None
    entries: tuple[TextEntry, ...]
    unkeyed_text_elements: int = 0

    def by_key(self) -> Mapping[str, TextEntry]:
        """Map key ke entry; key duplikat gagal sebelum diff."""
        result: dict[str, TextEntry] = {}
        for entry in self.entries:
            existing = result.get(entry.key)
            if existing is not None:
                raise GoogleSyncError(
                    f"Key '{entry.key}' muncul lebih dari sekali di Google Slides "
                    f"(slide '{existing.slide_id}' dan '{entry.slide_id}')."
                )
            result[entry.key] = entry
        return MappingProxyType(result)


def extract_text(presentation: PresentationSnapshot) -> PulledText:
    """Ekstrak shape berkey, sel tabel native, notes, dan source."""
    entries: list[TextEntry] = []
    unkeyed = 0
    for slide in presentation.slides:
        actual_slide_id = slide_id_for_index(slide.index)
        for element in (*slide.page_elements, *slide.notes_page_elements):
            is_notes = element in slide.notes_page_elements
            table_entries, table_unkeyed = _table_entries(
                element,
                actual_slide_id=actual_slide_id,
                slide_index=slide.index,
            )
            if table_entries:
                entries.extend(table_entries)
                continue
            if table_unkeyed:
                unkeyed += 1
                continue
            if not element.text:
                continue
            marker = element.marker
            if marker is None or marker.startswith(("autooffice:", "chrome:")):
                if is_notes and marker is None:
                    entries.append(_notes_fallback(element, slide=slide))
                continue
            try:
                parsed = parse_key(marker)
            except KeyGrammarError:
                if is_notes:
                    entries.append(_notes_fallback(element, slide=slide))
                else:
                    unkeyed += 1
                continue
            if parsed.slide_id != actual_slide_id:
                raise GoogleSyncError(
                    f"Key '{marker}' berada di slide index {slide.index + 1} "
                    f"milik '{actual_slide_id}', bukan '{parsed.slide_id}'."
                )
            kind: TextKind = "notes" if is_notes else "text"
            if not is_notes and parsed.leaf == "source.text":
                kind = "source"
            elif not is_notes and parsed.leaf == "notes":
                kind = "notes"
            entries.append(
                TextEntry(
                    key=marker,
                    slide_id=parsed.slide_id,
                    text=normalize_text(marker, element.text),
                    kind=kind,
                    slide_index=slide.index,
                )
            )
    return PulledText(
        presentation_id=presentation.presentation_id,
        revision_id=presentation.revision_id,
        entries=tuple(entries),
        unkeyed_text_elements=unkeyed,
    )


def normalize_text(key: str, value: str) -> str:
    """Normalisasi pulled text sesuai kelas key: notes/code preserve newline."""
    if key.endswith(".notes") or key.endswith(".code"):
        return normalize_preserve_newlines(value)
    return " ".join(value.split())


def normalize_preserve_newlines(value: str) -> str:
    """Trim baris kosong awal/akhir dan pertahankan baris baru internal."""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def find_presentation_id_from_url(url: str) -> str | None:
    """Ambil presentation ID dari URL Slides/Drive atau ID mentah."""
    value = url.strip()
    if not value:
        return None
    for pattern in _PRESENTATION_PATTERNS:
        match = pattern.search(value)
        if match is not None:
            return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", value):
        return value
    return None


def _notes_fallback(element: PageElement, *, slide: SlideSnapshot) -> TextEntry:
    """Notes tanpa marker memakai urutan slide sebagai identitas cadangan."""
    key = f"{slide_id_for_index(slide.index)}.notes"
    return TextEntry(
        key=key,
        slide_id=key.split(".", 1)[0],
        text=normalize_text(key, element.text),
        kind="notes",
        slide_index=slide.index,
    )


def _table_entries(
    element: PageElement,
    *,
    actual_slide_id: str,
    slide_index: int,
) -> tuple[list[TextEntry], bool]:
    if element.kind != "table":
        if element.marker is not None and element.marker.startswith(TABLE_MARKER_PREFIX):
            return [], True
        return [], False
    marker = element.marker
    if not marker:
        return [], True
    namespace = table_namespace(marker)
    if not namespace or namespace.startswith(("autooffice:", "chrome:")):
        return [], True
    try:
        parsed = parse_key(f"{namespace}.h1")
    except KeyGrammarError:
        return [], True
    if parsed.slide_id != actual_slide_id:
        raise GoogleSyncError(
            f"Table '{marker}' berada di slide index {slide_index + 1} "
            f"milik '{actual_slide_id}', bukan '{parsed.slide_id}'."
        )
    cell_count = 0
    entries: list[TextEntry] = []
    namespace = namespace.split(".", 1)[1]
    for row_index, row in enumerate(element.cells, start=1):
        for column_index, text in enumerate(row, start=1):
            cell_count += 1
            leaf = f"h{column_index}" if row_index == 1 else f"r{row_index - 1}.c{column_index}"
            key = f"{parsed.slide_id}.{namespace}.{leaf}"
            entries.append(
                TextEntry(
                    key=key,
                    slide_id=parsed.slide_id,
                    text=" ".join(text.split()),
                    kind="table_cell",
                    slide_index=slide_index,
                )
            )
    return entries, cell_count == 0


__all__ = [
    "PulledText",
    "TextEntry",
    "TextKind",
    "extract_text",
    "find_presentation_id_from_url",
    "normalize_preserve_newlines",
    "normalize_text",
]
