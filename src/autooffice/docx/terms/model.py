"""Model paragraf, penanda, style, dan pencocokan istilah.

Modul ini bergantung pada :mod:`docgen.docx.terms.glossary` dan helper DOCX
kanonis. Modul ini tidak boleh mengimpor ``apply`` atau ``verify`` agar arah
dependensi tetap satu arah.

Referensi: https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing?view=openxml-3.0.1
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from lxml import etree

from ..package import DOCUMENT_PART, paragraphs
from ..package.fields import FieldMarkerKind, field_marker_kind, iter_field_markers
from ..package.names import (
    STYLE_BIBLIOGRAPHY,
    STYLE_ISTILAH_ASING,
    STYLE_ISTILAH_REVIEW,
    W_BR,
    W_CR,
    W_HYPERLINK,
    W_INSTRTEXT,
    W_NO_BREAK_HYPHEN,
    W_R,
    W_RPR,
    W_RSTYLE,
    W_T,
    W_TAB,
    W_VAL,
    W,
)
from ..package.xml import is_on, iter_paragraphs, qn
from .glossary import Glossary, GlossaryEntry, TermsError

W_BASEDON = W + "basedOn"
W_I = W + "i"
W_LANG = W + "lang"
W_STYLE = W + "style"
W_STYLE_ID = W + "styleId"
W_SOFT_HYPHEN = qn("w:softHyphen")

ISTILAH_ASING = STYLE_ISTILAH_ASING
ISTILAH_REVIEW = STYLE_ISTILAH_REVIEW
BIBLIOGRAPHY_STYLE = STYLE_BIBLIOGRAPHY
BARRIER = "\ufffc"
MARKER_PREFIX = "{{?"
MARKER_SUFFIX = "?}}"
MARKER_RE = re.compile(r"\{\{\?((?:(?!\{\{|\}\}|\r|\n).)+?)\?\}\}")


class MarkerError(TermsError):
    """Penanda ``{{?…?}}`` kosong atau rusak."""

    default_code = "TERMS-MARKER"


@dataclass(frozen=True)
class TermMatch:
    start: int
    end: int
    entry: GlossaryEntry


def match_terms(text: str, glossary: Glossary) -> tuple[TermMatch, ...]:
    """Pilih match terpanjang yang tidak bertumpang tindih."""

    candidates: list[TermMatch] = []
    for entry in glossary.entries.values():
        for match in entry.pattern.finditer(text):
            candidates.append(TermMatch(match.start(), match.end(), entry))

    candidates.sort(
        key=lambda item: (
            -(item.end - item.start),
            item.start,
            item.entry.term.casefold(),
        )
    )

    occupied = bytearray(len(text))
    selected: list[TermMatch] = []
    for candidate in candidates:
        if any(occupied[candidate.start : candidate.end]):
            continue
        occupied[candidate.start : candidate.end] = b"\x01" * (candidate.end - candidate.start)
        selected.append(candidate)

    selected.sort(key=lambda item: item.start)
    return tuple(selected)


# ---------------------------------------------------------------------------
# Penanda
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Marker:
    start: int
    end: int
    content: str

    @property
    def content_start(self) -> int:
        return self.start + len(MARKER_PREFIX)

    @property
    def content_end(self) -> int:
        return self.end - len(MARKER_SUFFIX)

    @property
    def raw(self) -> str:
        return f"{MARKER_PREFIX}{self.content}{MARKER_SUFFIX}"


def iter_markers(text: str) -> Iterator[Marker]:
    """Satu-satunya parser penanda ``{{?…?}}``."""

    valid_matches = list(MARKER_RE.finditer(text))
    spans = [(match.start(), match.end()) for match in valid_matches]
    markers: list[Marker] = []

    for match in valid_matches:
        content = match.group(1)
        if not content.strip():
            raise MarkerError("Penanda {{?…?}} kosong tidak diperbolehkan.")
        markers.append(Marker(match.start(), match.end(), content))

    def inside_valid(position: int) -> bool:
        return any(start <= position < end for start, end in spans)

    position = 0
    while True:
        start = text.find(MARKER_PREFIX, position)
        if start == -1:
            break
        if not any(match.start() == start for match in valid_matches):
            if text.startswith("{{??}}", start):
                raise MarkerError("Penanda {{??}} kosong tidak diperbolehkan.")
            snippet = text[start : start + 40].splitlines()[0]
            raise MarkerError(
                f"Penanda tidak valid atau tidak ditutup: {snippet!r}. "
                "Gunakan {{?…?}}; isi marker tidak boleh memuat '{{', '}}', "
                "atau newline."
            )
        position = start + 1

    for match in re.finditer(r"\?\?", text):
        if not inside_valid(match.start()):
            raise MarkerError("Penanda '??' kosong tidak diperbolehkan. Gunakan {{?istilah?}}.")

    yield from markers


def unique_terms(terms: Sequence[str]) -> list[str]:
    """Deduplikasi casefold dengan urutan kemunculan pertama."""

    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        text = term.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def write_review_file(path: str | Path, terms: Sequence[str]) -> Path:
    """Tulis daftar review deterministik (UTF-8, LF, tanpa timestamp)."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    unique = unique_terms(terms)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        if unique:
            handle.write("\n".join(unique) + "\n")
    return output


def collect_markdown_terms(text: str) -> tuple[str, ...]:
    """Validasi penanda Markdown dan kembalikan istilahnya."""

    return tuple(unique_terms([marker.content for marker in iter_markers(text)]))


# ---------------------------------------------------------------------------
# Model paragraf
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextChar:
    run: etree._Element
    text_node: etree._Element
    offset: int


@dataclass
class ParagraphModel:
    element: etree._Element
    text: str
    chars: list[TextChar | None]
    ignored_texts: list[str] = field(default_factory=list)


def _relation_index(package: object) -> dict[str, object]:
    try:
        relationships = package.relationships(DOCUMENT_PART)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - package tanpa rels adalah boundary opsional
        return {}
    return {relationship.rel_id: relationship for relationship in relationships}


def _is_external_hyperlink(
    element: etree._Element,
    relations: Mapping[str, object],
) -> bool:
    rel_id = element.get(qn("r:id"))
    if not rel_id:
        return False
    relation = relations.get(rel_id)
    if relation is None:
        return True
    return getattr(relation, "target_mode", None) == "External"


def _text_of_ignored(element: etree._Element) -> str:
    pieces: list[str] = []
    for node in element.iter():
        if node.tag == W_T or node.tag == W_INSTRTEXT:
            pieces.append(node.text or "")
        elif node.tag == W_TAB:
            pieces.append("\t")
        elif node.tag in (W_BR, W_CR):
            pieces.append("\n")
    return "".join(pieces)


def build_paragraph_model(
    paragraph: etree._Element,
    relations: Mapping[str, object],
) -> ParagraphModel:
    """Ambil teks paragraf beserta peta balik ke setiap ``w:t``."""

    parts: list[str] = []
    chars: list[TextChar | None] = []
    ignored_texts: list[str] = []
    field_text: list[str] = []
    field_depth = 0
    marker_elements = tuple(iter_field_markers(paragraph))
    markers = {id(marker): field_marker_kind(marker) for marker in marker_elements}
    marker_ids = set(markers)

    def append_barrier() -> None:
        parts.append(BARRIER)
        chars.append(None)

    def append_unmapped(text: str) -> None:
        parts.append(text)
        chars.extend([None] * len(text))

    def flush_field_text() -> None:
        if field_text:
            ignored_texts.append("".join(field_text))
            field_text.clear()

    def walk(element: etree._Element, current_run: etree._Element | None = None) -> None:
        """Telusuri paragraf dan isi ``parts``/``chars`` beserta peta baliknya.

        Teks field dan hyperlink eksternal dicatat terpisah sebagai barrier;
        karakter di dalam ``w:t`` memetakan ke run dan offset aslinya.
        """

        nonlocal field_depth

        for child in element:
            tag = child.tag
            if tag == W_RPR:
                continue

            if id(child) in marker_ids:
                marker_kind = markers[id(child)]
                if marker_kind is FieldMarkerKind.BEGIN:
                    if field_depth == 0:
                        append_barrier()
                    field_depth += 1
                elif marker_kind is FieldMarkerKind.END and field_depth > 0:
                    field_depth -= 1
                    if field_depth == 0:
                        flush_field_text()
                elif marker_kind is FieldMarkerKind.INSTRUCTION:
                    text = child.text or ""
                    if field_depth > 0:
                        field_text.append(text)
                    else:
                        ignored_texts.append(text)
                        append_barrier()
                elif marker_kind is FieldMarkerKind.SIMPLE:
                    text = _text_of_ignored(child)
                    if field_depth > 0:
                        field_text.append(text)
                    else:
                        ignored_texts.append(text)
                    append_barrier()
                continue

            if tag == W_HYPERLINK and _is_external_hyperlink(child, relations):
                text = _text_of_ignored(child)
                if field_depth > 0:
                    field_text.append(text)
                else:
                    ignored_texts.append(text)
                append_barrier()
                continue

            if tag == W_T:
                text = child.text or ""
                if field_depth > 0:
                    field_text.append(text)
                    append_barrier()
                    continue
                if current_run is None:
                    append_barrier()
                    continue
                for offset, character in enumerate(text):
                    parts.append(character)
                    chars.append(TextChar(current_run, child, offset))
                continue

            if tag == W_TAB:
                if field_depth > 0:
                    field_text.append("\t")
                append_unmapped("\t")
                continue
            if tag in (W_BR, W_CR):
                if field_depth > 0:
                    field_text.append("\n")
                append_unmapped("\n")
                continue
            if tag in (W_NO_BREAK_HYPHEN, W_SOFT_HYPHEN):
                append_barrier()
                continue

            walk(child, child if tag == W_R else current_run)

    walk(paragraph)
    flush_field_text()
    return ParagraphModel(
        element=paragraph,
        text="".join(parts),
        chars=chars,
        ignored_texts=ignored_texts,
    )


def iter_ignored_markers(model: ParagraphModel) -> Iterator[Marker]:
    for ignored_text in model.ignored_texts:
        yield from iter_markers(ignored_text)


def _iter_all_paragraphs(
    package: object,
) -> Iterator[tuple[etree._Element, dict[str, object], bool]]:
    root = package.xml(DOCUMENT_PART)  # type: ignore[attr-defined]
    relations = _relation_index(package)
    for paragraph in iter_paragraphs(root):
        skipped = paragraphs.paragraph_style_id(paragraph) == BIBLIOGRAPHY_STYLE
        yield paragraph, relations, skipped


def iter_document_paragraphs(
    package: object,
) -> Iterator[tuple[etree._Element, dict[str, object]]]:
    """Paragraf body yang dapat diproses; ``Bibliography`` dilewati."""

    for paragraph, relations, skipped in _iter_all_paragraphs(package):
        if skipped:
            continue
        yield paragraph, relations


# ---------------------------------------------------------------------------
# Resolver style terpadu (dipakai terms dan audit)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StyleResolution:
    """Nilai efektif satu style setelah rantai ``w:basedOn``."""

    italic: bool | None = None
    lang: str | None = None
    bold: bool | None = None
    style_id: str | None = None


class StyleResolver:
    """Resolve italic/lang efektif dari direct formatting dan style chain."""

    def __init__(self, package: object) -> None:
        root = package.xml("word/styles.xml")  # type: ignore[attr-defined]
        self.styles = {
            style.get(W_STYLE_ID): style for style in root.findall(W_STYLE) if style.get(W_STYLE_ID)
        }

    def _chain(self, style_id: str | None) -> Iterator[etree._Element]:
        seen: set[str] = set()
        current = style_id
        while current and current not in seen:
            seen.add(current)
            style = self.styles.get(current)
            if style is None:
                return
            yield style
            based_on = style.find(W_BASEDON)
            current = based_on.get(W_VAL) if based_on is not None else None

    def resolve(self, style_id: str | None) -> StyleResolution:
        italic: bool | None = None
        lang: str | None = None
        bold: bool | None = None
        for style in self._chain(style_id):
            rpr = style.find(W_RPR)
            if rpr is None:
                continue
            if italic is None:
                node = rpr.find(W_I)
                if node is not None:
                    italic = is_on(node)
            if lang is None:
                node = rpr.find(W_LANG)
                if node is not None and node.get(W_VAL):
                    lang = node.get(W_VAL)
            if bold is None:
                node = rpr.find(W + "b")
                if node is not None:
                    bold = is_on(node)
            if italic is not None and lang is not None and bold is not None:
                break
        if italic is None and style_id == ISTILAH_ASING:
            italic = True
        return StyleResolution(
            italic=italic,
            lang=lang,
            bold=bold,
            style_id=style_id,
        )

    @staticmethod
    def _direct_rpr(run: etree._Element) -> etree._Element | None:
        return run.find(W_RPR)

    def effective_italic(
        self,
        run: etree._Element,
        paragraph: etree._Element | None = None,
    ) -> bool:
        rpr = self._direct_rpr(run)
        if rpr is not None:
            italic = rpr.find(W_I)
            if italic is not None:
                return is_on(italic)
        resolution = self.resolve(direct_style_id(run))
        if resolution.italic is not None:
            return resolution.italic
        if paragraph is not None:
            styled = self.resolve(paragraphs.paragraph_style_id(paragraph))
            if styled.italic is not None:
                return styled.italic
        return False

    def effective_lang(
        self,
        run: etree._Element,
        paragraph: etree._Element | None = None,
    ) -> str | None:
        rpr = self._direct_rpr(run)
        if rpr is not None:
            lang = rpr.find(W_LANG)
            if lang is not None and lang.get(W_VAL):
                return cast("str | None", lang.get(W_VAL))
        resolution = self.resolve(direct_style_id(run))
        if resolution.lang is not None:
            return resolution.lang
        if paragraph is not None:
            return self.resolve(paragraphs.paragraph_style_id(paragraph)).lang
        return None

    def effective(
        self,
        run: etree._Element,
        paragraph: etree._Element | None = None,
    ) -> bool:
        """Kompatibilitas audit: italic efektif sebagai boolean."""

        return self.effective_italic(run, paragraph)


def resolve_style(package: object, style_id: str) -> StyleResolution:
    """API kontrak untuk audit dan tes."""

    return StyleResolver(package).resolve(style_id)


def direct_style_id(run: etree._Element) -> str | None:
    rpr = run.find(W_RPR)
    if rpr is None:
        return None
    rstyle = rpr.find(W_RSTYLE)
    if rstyle is None:
        return None
    return cast("str | None", rstyle.get(W_VAL))


def direct_italic(run: etree._Element) -> bool:
    rpr = run.find(W_RPR)
    if rpr is None:
        return False
    italic = rpr.find(W_I)
    return italic is not None and is_on(italic)


def direct_en_us(run: etree._Element) -> bool:
    rpr = run.find(W_RPR)
    if rpr is None:
        return False
    lang = rpr.find(W_LANG)
    if lang is None:
        return False
    value = lang.get(W_VAL)
    return bool(value and value.casefold() == "en-us")


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewItem:
    text: str
    paragraph: int


def styled_spans(model: ParagraphModel, style: str) -> list[str]:
    """Ambil teks berurutan per run yang memakai ``style`` langsung."""

    spans: list[str] = []
    index = 0
    while index < len(model.text):
        char = model.chars[index]
        if char is None or direct_style_id(char.run) != style:
            index += 1
            continue
        end = index + 1
        while end < len(model.text):
            next_char = model.chars[end]
            if next_char is None or direct_style_id(next_char.run) != style:
                break
            end += 1
        value = model.text[index:end].strip()
        if value:
            spans.append(value)
        index = end
    return spans


def list_review_items(package: object) -> tuple[ReviewItem, ...]:
    """Daftar istilah review yang belum diputuskan."""

    items: list[ReviewItem] = []
    for number, (paragraph, relations) in enumerate(
        iter_document_paragraphs(package),
        start=1,
    ):
        model = build_paragraph_model(paragraph, relations)
        if not model.text and not model.ignored_texts:
            continue
        for span in styled_spans(model, ISTILAH_REVIEW):
            items.append(ReviewItem(span, number))
        for marker in iter_markers(model.text):
            items.append(ReviewItem(marker.content.strip(), number))
        for marker in iter_ignored_markers(model):
            items.append(ReviewItem(marker.content.strip(), number))
    return tuple(items)


# ---------------------------------------------------------------------------
# Loader package
# ---------------------------------------------------------------------------


def open_docx(path: str | Path) -> object:
    """Muat DOCX sebagai :class:`DocumentPackage`."""

    from ..package import DocumentPackage

    return DocumentPackage.load(Path(path))
