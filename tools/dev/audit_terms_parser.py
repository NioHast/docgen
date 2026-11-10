"""Ekstraksi paragraf DOCX dan pengumpulan kemunculan istilah asing.

Parser hanya membaca DOCX hasil build. Klasifikasi kata memakai heuristik di
``audit_terms_rules`` dan model hasil di ``audit_terms_model``; modul ini tidak
menulis laporan dan tidak menjalankan CLI.
"""

import re
from pathlib import Path

from audit_terms_model import (
    CATEGORY_GLOSSARY_ITALIC,
    CATEGORY_GLOSSARY_PLAIN,
    CATEGORY_ITALIC_MISSING,
    CATEGORY_MIXED_CASE_NAME,
    CATEGORY_PLAIN_BUT_ITALIC,
    CATEGORY_UNKNOWN,
    AuditResult,
    Group,
    Occurrence,
)
from audit_terms_rules import (
    CONTEXT_WORD_RE,
    NON_PROSE_RE,
    TOKEN_RE,
    is_abbreviation,
    is_english_stopword,
    is_mixed_case_name,
    looks_indonesian,
    normalize_key,
)

from docgen.docx.paragraphs import paragraph_style_id
from docgen.docx.terms import (
    BIBLIOGRAPHY_STYLE,
    Glossary,
    StyleResolver,
    build_paragraph_model,
    match_terms,
    open_docx,
)
from docgen.docx.xml import iter_paragraphs

DOCUMENT_PART = "word/document.xml"
HEADER_FOOTER_RE = re.compile(r"^word/(?:header|footer)\d*\.xml$")


def iter_audit_paragraphs(
    package: object,
) -> list[tuple[object, dict[str, object]]]:
    """Paragraf body, tabel, header, dan footer beserta relasinya.

    Resolver style dan istilah ada di ``docgen.docx``; alat dev ini hanya
    membaca data dari package DOCX, bukan menjalankan kode dari folder input.
    """

    names = [DOCUMENT_PART]
    names.extend(
        name
        for name in package.part_names()  # type: ignore[attr-defined]
        if HEADER_FOOTER_RE.match(name)
    )
    paragraphs: list[tuple[object, dict[str, object]]] = []
    for name in names:
        root = package.xml(name)  # type: ignore[attr-defined]
        relations = {
            rel.rel_id: rel
            for rel in package.relationships(name)  # type: ignore[attr-defined]
        }
        for paragraph in iter_paragraphs(root):
            if paragraph_style_id(paragraph) == BIBLIOGRAPHY_STYLE:
                continue
            paragraphs.append((paragraph, relations))
    return paragraphs


def _letter_count(text: str) -> int:
    return sum(character.isalpha() for character in text)


def make_context(text: str, start: int, end: int, window: int = 8) -> str:
    """Ambil 8 kata sebelum/sesudah dengan target ditebalkan."""

    words = list(CONTEXT_WORD_RE.finditer(text))
    before = [word for word in words if word.end() <= start]
    after = [word for word in words if word.start() >= end]
    selected_before = before[-window:]
    selected_after = after[:window]

    target = text[start:end]
    parts = [word.group(0) for word in selected_before]
    parts.append(f"**{target}**")
    parts.extend(word.group(0) for word in selected_after)

    context = " ".join(parts)
    if len(before) > window:
        context = "… " + context
    if len(after) > window:
        context = context + " …"
    context = context.replace("\ufffc", "…")
    context = re.sub(r"\s+", " ", context).strip()
    context = re.sub(r"…+", "…", context)
    return context or "—"


def _ranges(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in pattern.finditer(text)]


def _overlaps_any(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < range_end and range_start < end for range_start, range_end in ranges)


def collect_occurrences(docx_path: Path, glossary: Glossary) -> AuditResult:
    """Baca DOCX dan kumpulkan semua kemunculan yang relevan."""

    docx_path = Path(docx_path)
    package = open_docx(docx_path)
    resolver = StyleResolver(package)
    occurrences: list[Occurrence] = []
    paragraph_count = 0
    abbreviation_count = 0
    abbreviation_terms: set[str] = set()
    noise_count = 0

    for paragraph_no, (paragraph, relations) in enumerate(iter_audit_paragraphs(package), start=1):
        model = build_paragraph_model(paragraph, relations)
        text = model.text
        if not text.strip():
            continue
        paragraph_count += 1

        non_prose_ranges = _ranges(text, NON_PROSE_RE)
        occupied = bytearray(len(text))

        # 1. Istilah/frasa dari glosarium. Frasa terpanjang menang, sehingga
        #    "training data" tidak dipecah menjadi "training" + "data".
        for match in match_terms(text, glossary):
            start, end = match.start, match.end
            if _overlaps_any(start, end, non_prose_ranges):
                continue
            if any(occupied[start:end]):
                continue
            chars = model.chars[start:end]
            if not chars or any(char is None for char in chars):
                continue

            # Spasi/tanda baca di antara kata tidak menentukan status italic;
            # yang dinilai adalah huruf-hurufnya. Ini penting saat istilah
            # terpotong beberapa run dan spasi berada di run tegak.
            span = text[start:end]
            flags = [
                resolver.effective(char.run, paragraph)  # type: ignore[union-attr]
                for char, character in zip(chars, span, strict=True)
                if char is not None and character.isalpha()
            ]
            if not flags:
                flags = [
                    resolver.effective(char.run, paragraph)  # type: ignore[union-attr]
                    for char in chars
                    if char is not None
                ]
            any_italic = any(flags)
            all_italic = all(flags)

            if match.entry.italic:
                category = CATEGORY_GLOSSARY_ITALIC if all_italic else CATEGORY_ITALIC_MISSING
            else:
                category = CATEGORY_PLAIN_BUT_ITALIC if any_italic else CATEGORY_GLOSSARY_PLAIN

            display = text[start:end]
            occurrences.append(
                Occurrence(
                    key=normalize_key(match.entry.term),
                    display=display,
                    category=category,
                    paragraph=paragraph_no,
                    start=start,
                    end=end,
                    context=make_context(text, start, end),
                    italic=all_italic,
                )
            )
            occupied[start:end] = b"\x01" * (end - start)

        # 2. Kata Latin lain yang belum tercakup glosarium.
        for match in TOKEN_RE.finditer(text):
            start, end = match.start(), match.end()
            while end > start and text[end - 1] in {"'", "\u2019", "-"}:
                end -= 1
            token = text[start:end]

            if _letter_count(token) < 3:
                continue
            if any(occupied[start:end]):
                continue
            if _overlaps_any(start, end, non_prose_ranges):
                continue

            chars = model.chars[start:end]
            if not chars or any(char is None for char in chars):
                continue

            if is_abbreviation(token):
                abbreviation_count += 1
                abbreviation_terms.add(normalize_key(token))
                continue

            if is_mixed_case_name(token):
                category = CATEGORY_MIXED_CASE_NAME
                is_name = True
            elif looks_indonesian(token) or is_english_stopword(token):
                noise_count += 1
                continue
            else:
                category = CATEGORY_UNKNOWN
                is_name = False

            letter_flags = [
                resolver.effective(char.run, paragraph)  # type: ignore[union-attr]
                for char, character in zip(chars, token, strict=True)
                if char is not None and character.isalpha()
            ]
            occurrences.append(
                Occurrence(
                    key=normalize_key(token),
                    display=token,
                    category=category,
                    paragraph=paragraph_no,
                    start=start,
                    end=end,
                    context=make_context(text, start, end),
                    is_name=is_name,
                    italic=bool(letter_flags) and all(letter_flags),
                )
            )

    occurrences.sort(key=lambda occurrence: (occurrence.paragraph, occurrence.start))
    groups = _group_occurrences(occurrences)
    groups.sort(key=lambda group: (-group.count, group.key, group.category))
    return AuditResult(
        occurrences=occurrences,
        groups=groups,
        paragraph_count=paragraph_count,
        abbreviation_count=abbreviation_count,
        abbreviation_terms=abbreviation_terms,
        noise_count=noise_count,
    )


def _group_occurrences(occurrences: list[Occurrence]) -> list[Group]:
    groups: dict[tuple[str, str, bool], Group] = {}
    for occurrence in occurrences:
        group_key = (occurrence.category, occurrence.key, occurrence.is_name)
        group = groups.get(group_key)
        if group is None:
            group = Group(
                key=occurrence.key,
                display=occurrence.display,
                category=occurrence.category,
                is_name=occurrence.is_name,
            )
            groups[group_key] = group
        group.occurrences.append(occurrence)
    return list(groups.values())


def audit_docx(docx_path: Path, glossary: Glossary) -> AuditResult:
    """API utama untuk tes dan pemakaian internal."""

    return collect_occurrences(docx_path, glossary)
