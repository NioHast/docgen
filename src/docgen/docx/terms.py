"""Glosarium, transformasi, dan verifikasi istilah asing DOCX.

Modul ini menggabungkan resolver ``tools/terms.py`` dan ``audit_terms.py``
menjadi satu API. Semua mutasi terjadi pada :class:`DocumentPackage` di
memori; penyimpanan tetap milik pipeline.

Pemisahan internal:

- glosarium: :func:`load_glossary`, :func:`merge_glossaries`;
- model paragraf: :func:`build_paragraph_model`, :func:`iter_document_paragraphs`;
- transformasi: :func:`apply_terms`, :func:`transform_runs`;
- verifikasi: :func:`verify_terms`, :func:`resolve_style`.
"""

import copy
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from . import DocxError, paragraphs
from .names import (
    STYLE_BIBLIOGRAPHY,
    STYLE_ISTILAH_ASING,
    STYLE_ISTILAH_REVIEW,
    W_BR,
    W_CR,
    W_FLDCHAR,
    W_FLDSIMPLE,
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
from .runs import copy_rpr, make_run
from .styles import StyleError, ensure_character_style
from .xml import is_on, iter_paragraphs, qn

W_BASEDON = W + "basedOn"
W_HIGHLIGHT = W + "highlight"
W_I = W + "i"
W_LANG = W + "lang"
W_NAME = W + "name"
W_STYLE = W + "style"
W_STYLE_ID = W + "styleId"
W_TYPE = W + "type"
W_SOFT_HYPHEN = qn("w:softHyphen")
W_DOCUMENT_PART = "word/document.xml"

ISTILAH_ASING = STYLE_ISTILAH_ASING
ISTILAH_REVIEW = STYLE_ISTILAH_REVIEW
BIBLIOGRAPHY_STYLE = STYLE_BIBLIOGRAPHY
DEFAULT_PARAGRAPH_FONT = "DefaultParagraphFont"
BARRIER = "\ufffc"
MARKER_PREFIX = "{{?"
MARKER_SUFFIX = "?}}"
MARKER_RE = re.compile(r"\{\{\?((?:(?!\{\{|\}\}|\r|\n).)+?)\?\}\}")

_GLOSSARY_HEADER = ("term", "italic")
_TRUE = "yes"
_FALSE = "no"


class TermsError(DocxError):
    """Pelanggaran penerapan atau verifikasi istilah."""

    default_code = "TERMS"


class GlossaryError(TermsError):
    """Isi ``istilah.tsv`` tidak valid."""

    default_code = "GLOSSARY"


class MarkerError(TermsError):
    """Penanda ``{{?…?}}`` kosong atau rusak."""

    default_code = "TERMS-MARKER"


# ---------------------------------------------------------------------------
# Glosarium
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GlossaryEntry:
    """Satu istilah; hanya keputusan italic yang masih dipakai."""

    term: str
    italic: bool
    pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pattern",
            re.compile(
                rf"(?<!\w){re.escape(self.term)}(?!\w)",
                re.IGNORECASE,
            ),
        )


@dataclass(frozen=True)
class Glossary:
    """Glosarium dengan kunci casefold dan asal berkas."""

    entries: Mapping[str, GlossaryEntry]
    source: Path

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[GlossaryEntry]:
        return iter(self.entries.values())


@dataclass(frozen=True)
class TermMatch:
    start: int
    end: int
    entry: GlossaryEntry


def load_glossary(path: str | Path) -> Glossary:
    """Baca TSV dengan header wajib ``term<TAB>italic``.

    Setiap baris harus memiliki tepat dua kolom. Header lama dengan kolom
    ``gloss_first``/``status`` ditolak agar format glosarium seragam.
    """

    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise GlossaryError(
            f"Glosarium tidak ditemukan: {source}",
            code="GLOSSARY-MISSING",
            path=source,
        ) from exc
    except UnicodeDecodeError as exc:
        raise GlossaryError(
            f"Glosarium bukan UTF-8 yang valid: {source}",
            code="GLOSSARY-ENCODING",
            path=source,
        ) from exc
    except OSError as exc:
        raise GlossaryError(
            f"Glosarium tidak dapat dibaca: {source}: {exc}",
            code="GLOSSARY-IO",
            path=source,
        ) from exc

    entries: dict[str, GlossaryEntry] = {}
    seen: dict[str, int] = {}
    errors: list[str] = []
    header_seen = False
    expected_columns = 2

    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        columns = [column.strip() for column in line.split("\t")]
        if not header_seen:
            if tuple(columns) != _GLOSSARY_HEADER:
                raise GlossaryError(
                    f"Baris {line_number}: header harus 'term<TAB>italic'.",
                    code="GLOSSARY-HEADER",
                    path=source,
                )
            header_seen = True
            continue

        if len(columns) < expected_columns:
            errors.append(
                f"Baris {line_number}: kolom kurang ({len(columns)} dari {expected_columns})."
            )
            continue
        if len(columns) > expected_columns:
            errors.append(
                f"Baris {line_number}: kolom terlalu banyak "
                f"({len(columns)} dari {expected_columns})."
            )
            continue

        term, italic = columns[0], columns[1]
        if not term:
            errors.append(f"Baris {line_number}: term kosong.")
            continue
        if italic not in {_TRUE, _FALSE}:
            errors.append(f"Baris {line_number}: italic harus 'yes' atau 'no', bukan {italic!r}.")
            continue

        key = term.casefold()
        if key in seen:
            errors.append(
                f"Baris {line_number}: term duplikat {term!r} (sudah ada di baris {seen[key]})."
            )
            continue
        seen[key] = line_number
        entries[key] = GlossaryEntry(term=term, italic=italic == _TRUE)

    if not header_seen:
        errors.append("Header glosarium tidak ditemukan.")
    if errors:
        raise GlossaryError(
            "Glosarium tidak valid:\n" + "\n".join(errors),
            code="GLOSSARY-INVALID",
            path=source,
        )
    return Glossary(entries=entries, source=source)


def merge_glossaries(base: Glossary, override: Glossary) -> Glossary:
    """Gabungkan glosarium; entri override menang per frasa (casefold)."""

    entries = dict(base.entries)
    entries.update(override.entries)
    return Glossary(entries=entries, source=override.source)


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
        relationships = package.relationships(W_DOCUMENT_PART)  # type: ignore[attr-defined]
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
        nonlocal field_depth

        for child in element:
            tag = child.tag
            if tag == W_RPR:
                continue

            if tag == W_FLDCHAR:
                field_type = child.get(qn("w:fldCharType"))
                if field_type == "begin":
                    if field_depth == 0:
                        append_barrier()
                    field_depth += 1
                elif field_type == "end" and field_depth > 0:
                    field_depth -= 1
                    if field_depth == 0:
                        flush_field_text()
                continue

            if tag == W_INSTRTEXT:
                text = child.text or ""
                if field_depth > 0:
                    field_text.append(text)
                else:
                    ignored_texts.append(text)
                    append_barrier()
                continue

            if tag == W_FLDSIMPLE:
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
    root = package.xml(W_DOCUMENT_PART)  # type: ignore[attr-defined]
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
                return lang.get(W_VAL)
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
    return rstyle.get(W_VAL)


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


def _run_text(run: etree._Element) -> str:
    return "".join(node.text or "" for node in run.findall(W_T))


# ---------------------------------------------------------------------------
# Style istilah
# ---------------------------------------------------------------------------


def ensure_styles(package: object) -> bool:
    """Pastikan IstilahAsing/IstilahReview ada dan invariant-nya benar."""

    try:
        added_asing = ensure_character_style(
            package,
            ISTILAH_ASING,
            "Istilah Asing",
            rpr_xml='<w:i/><w:lang w:val="en-US"/>',
        )
        added_review = ensure_character_style(
            package,
            ISTILAH_REVIEW,
            "Istilah Review",
            rpr_xml='<w:highlight w:val="yellow"/>',
        )
    except StyleError as exc:
        raise TermsError(
            exc.message,
            code=exc.code,
            path=exc.path,
            key=exc.key,
        ) from exc
    return bool(added_asing or added_review)


# ---------------------------------------------------------------------------
# Transformasi run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharAction:
    delete: bool = False
    style: str | None = None


DEFAULT_ACTION = CharAction()


def _ranges_overlap(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> bool:
    return first_start < second_end and second_start < first_end


def _range_already_handled(model: ParagraphModel, start: int, end: int) -> bool:
    for char in model.chars[start:end]:
        if char is None:
            return False
        if direct_style_id(char.run) in {ISTILAH_ASING, ISTILAH_REVIEW}:
            continue
        if direct_italic(char.run):
            continue
        return False
    return True


def _run_properties(
    rpr_template: etree._Element | None,
    style: str | None,
) -> etree._Element | None:
    """Susun ``w:rPr`` lokal dari templat dan gaya istilah yang diminta."""

    if rpr_template is None and style is None:
        return None
    properties = copy_rpr(rpr_template) if rpr_template is not None else etree.Element(W_RPR)
    if style is None:
        return properties

    for old_style in properties.findall(W_RSTYLE):
        properties.remove(old_style)
    rstyle = etree.Element(W_RSTYLE)
    rstyle.set(W_VAL, style)
    properties.insert(0, rstyle)
    if style == ISTILAH_ASING:
        for old in properties.findall(W_I):
            properties.remove(old)
        properties.append(etree.Element(W_I))
        for old in properties.findall(W_LANG):
            properties.remove(old)
        lang = etree.Element(W_LANG)
        lang.set(W_VAL, "en-US")
        properties.append(lang)
    return properties


def _detached_run(
    run_element: etree._Element,
    *,
    text: str | None = None,
    rpr: etree._Element | None = None,
) -> etree._Element:
    """Buat run lewat :func:`make_run`, salin atribut, lalu lepaskan dari parent sementara."""

    holder = etree.Element(W_R)
    new_run = make_run(holder, text=text, rpr=rpr)
    for key, value in run_element.attrib.items():
        new_run.set(key, value)
    holder.remove(new_run)
    return new_run


def _copy_non_text_child(
    run_element: etree._Element,
    rpr_template: etree._Element | None,
    child: etree._Element,
) -> etree._Element:
    new_run = _detached_run(run_element, rpr=rpr_template)
    new_run.append(copy.deepcopy(child))
    return new_run


def transform_runs(model: ParagraphModel, actions: list[CharAction]) -> bool:
    """Terapkan aksi per karakter; run hanya dipecah bila perlu."""

    node_actions: dict[int, tuple[etree._Element, list[CharAction]]] = {}
    for position, char in enumerate(model.chars):
        if char is None:
            continue
        action = actions[position]
        if action is DEFAULT_ACTION:
            continue
        key = id(char.text_node)
        if key not in node_actions:
            node_actions[key] = (
                char.text_node,
                [DEFAULT_ACTION] * len(char.text_node.text or ""),
            )
        node_actions[key][1][char.offset] = action

    if not node_actions:
        return False

    touched_runs: dict[int, etree._Element] = {}
    for char in model.chars:
        if char is None:
            continue
        if id(char.text_node) in node_actions:
            touched_runs[id(char.run)] = char.run

    for run in touched_runs.values():
        rpr_template = run.find(W_RPR)
        output: list[etree._Element] = []
        for child in list(run):
            if child.tag == W_RPR:
                continue
            if child.tag == W_T:
                text = child.text or ""
                node = node_actions.get(id(child))
                char_actions = node[1] if node is not None else [DEFAULT_ACTION] * len(text)
                index = 0
                while index < len(text):
                    action = char_actions[index]
                    end = index + 1
                    while end < len(text) and char_actions[end] == action:
                        end += 1
                    if not action.delete:
                        output.append(
                            _detached_run(
                                run,
                                text=text[index:end],
                                rpr=_run_properties(rpr_template, action.style),
                            )
                        )
                    index = end
            else:
                output.append(_copy_non_text_child(run, rpr_template, child))

        parent = run.getparent()
        if parent is None:
            continue
        index = parent.index(run)
        parent.remove(run)
        for offset, new_run in enumerate(output):
            parent.insert(index + offset, new_run)
    return True


def _styled_spans(model: ParagraphModel, style: str) -> list[str]:
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


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TermsReport:
    applied: int
    skipped_bibliography: int
    warnings: tuple[str, ...] = ()
    reviews: tuple[str, ...] = ()
    review_path: Path | None = None
    changed: bool = False


def apply_terms(
    package: object,
    glossary: Glossary,
    *,
    review_path: Path | None = None,
) -> TermsReport:
    """Terapkan ``IstilahAsing``/``IstilahReview`` ke package target."""

    styles_changed = ensure_styles(package)
    review_terms: list[str] = []
    warnings: list[str] = []
    applied = 0
    skipped_bibliography = 0
    document_changed = False

    for number, (paragraph, relations, skipped) in enumerate(
        _iter_all_paragraphs(package),
        start=1,
    ):
        if skipped:
            skipped_bibliography += 1
            continue
        model = build_paragraph_model(paragraph, relations)
        if not model.text and not model.ignored_texts:
            continue

        review_terms.extend(_styled_spans(model, ISTILAH_REVIEW))

        for marker in iter_ignored_markers(model):
            review_terms.append(marker.content)
            warnings.append(
                f"Paragraf {number}: penanda {marker.raw} berada di "
                "field/hyperlink eksternal dan tidak diubah."
            )

        delete_ranges: list[tuple[int, int]] = []
        review_ranges: list[tuple[int, int]] = []
        for marker in iter_markers(model.text):
            delete_ranges.append((marker.start, marker.content_start))
            delete_ranges.append((marker.content_end, marker.end))
            review_ranges.append((marker.content_start, marker.content_end))
            review_terms.append(marker.content)

        actions = [DEFAULT_ACTION] * len(model.text)

        for start, end in review_ranges:
            for position in range(start, end):
                actions[position] = CharAction(style=ISTILAH_REVIEW)

        for start, end in delete_ranges:
            for position in range(start, end):
                actions[position] = CharAction(delete=True)

        for match in match_terms(model.text, glossary):
            if not match.entry.italic:
                continue
            if any(
                _ranges_overlap(match.start, match.end, start, end)
                for start, end in review_ranges + delete_ranges
            ):
                continue
            if any(
                char is not None and direct_style_id(char.run) == ISTILAH_REVIEW
                for char in model.chars[match.start : match.end]
            ):
                continue
            if _range_already_handled(model, match.start, match.end):
                continue
            for position in range(match.start, match.end):
                actions[position] = CharAction(style=ISTILAH_ASING)
            applied += 1

        if transform_runs(model, actions):
            document_changed = True

    if document_changed:
        root = package.xml(W_DOCUMENT_PART)  # type: ignore[attr-defined]
        package.set_xml(W_DOCUMENT_PART, root)  # type: ignore[attr-defined]

    written: Path | None = None
    reviews = tuple(unique_terms(review_terms))
    if review_path is not None:
        written = write_review_file(review_path, reviews)

    return TermsReport(
        applied=applied,
        skipped_bibliography=skipped_bibliography,
        warnings=tuple(warnings),
        reviews=reviews,
        review_path=written,
        changed=bool(styles_changed or document_changed),
    )


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TermsVerifyReport:
    violations: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def _unique_runs(chars: Sequence[TextChar | None]) -> list[etree._Element]:
    runs: list[etree._Element] = []
    seen: set[int] = set()
    for char in chars:
        if char is None or id(char.run) in seen:
            continue
        seen.add(id(char.run))
        runs.append(char.run)
    return runs


def _term_status(
    model: ParagraphModel,
    match: TermMatch,
    resolver: StyleResolver,
) -> str:
    chars = model.chars[match.start : match.end]
    if not chars or any(char is None for char in chars):
        return "plain"
    styles = [direct_style_id(char.run) for char in chars]  # type: ignore[union-attr]
    if all(style == ISTILAH_ASING for style in styles):
        return "styled"
    if all(style in {ISTILAH_ASING, ISTILAH_REVIEW} for style in styles):
        return "review"
    if all(
        style == ISTILAH_ASING or resolver.effective_italic(char.run)  # type: ignore[union-attr]
        for style, char in zip(styles, chars, strict=True)
    ):
        return "direct"
    return "plain"


def verify_terms(package: object, glossary: Glossary) -> TermsVerifyReport:
    """Periksa seluruh invariant istilah pada package."""

    resolver = StyleResolver(package)
    violations: list[str] = []
    warnings: list[str] = []
    known_terms = {entry.term.casefold() for entry in glossary.entries.values()}
    language_failures: set[int] = set()

    for number, (paragraph, relations) in enumerate(
        iter_document_paragraphs(package),
        start=1,
    ):
        model = build_paragraph_model(paragraph, relations)
        if not model.text and not model.ignored_texts:
            continue

        try:
            markers = list(iter_markers(model.text))
        except MarkerError as exc:
            violations.append(f"Paragraf {number}: {exc}")
            markers = []
        for marker in markers:
            violations.append(
                f"Paragraf {number}: masih ada penanda {marker.raw} "
                "(belum di-apply atau belum diputuskan)."
            )

        try:
            ignored_markers = list(iter_ignored_markers(model))
        except MarkerError as exc:
            violations.append(f"Paragraf {number}: {exc}")
            ignored_markers = []
        for marker in ignored_markers:
            violations.append(
                f"Paragraf {number}: penanda {marker.raw} berada di "
                "field/hyperlink eksternal dan tidak diubah."
            )

        for match in match_terms(model.text, glossary):
            chars = model.chars[match.start : match.end]
            if not match.entry.italic:
                runs = _unique_runs(chars)
                uses_asing = any(direct_style_id(run) == ISTILAH_ASING for run in runs)
                uses_italic = any(resolver.effective_italic(run, paragraph) for run in runs)
                if uses_asing or uses_italic:
                    violations.append(
                        f"Paragraf {number}: istilah italic=no "
                        f"{match.entry.term!r} muncul dengan italic/"
                        "IstilahAsing; seharusnya tegak."
                    )
                continue

            status = _term_status(model, match, resolver)
            if status == "plain":
                violations.append(
                    f"Paragraf {number}: istilah {match.entry.term!r} muncul "
                    "sebagai teks biasa tanpa style IstilahAsing."
                )
            elif status == "direct":
                warnings.append(
                    f"direct formatting: istilah {match.entry.term!r} "
                    f"(paragraf {number}) memakai italic manual tanpa style "
                    "IstilahAsing."
                )

            for run in _unique_runs(chars):
                if id(run) in language_failures:
                    continue
                if direct_style_id(run) in {ISTILAH_ASING, ISTILAH_REVIEW}:
                    continue
                if direct_en_us(run):
                    language_failures.add(id(run))
                    text = _run_text(run).strip()
                    violations.append(
                        f"Paragraf {number}: run {text!r} memuat istilah "
                        f"italic=yes {match.entry.term!r} dan memakai direct "
                        "w:lang en-US tanpa style IstilahAsing."
                    )

        for span in _styled_spans(model, ISTILAH_ASING):
            if span.casefold() not in known_terms:
                violations.append(
                    f"Paragraf {number}: run IstilahAsing berisi {span!r}, "
                    "bukan istilah di glosarium."
                )

        seen_asing_runs: set[int] = set()
        for char in model.chars:
            if char is None or id(char.run) in seen_asing_runs:
                continue
            if direct_style_id(char.run) != ISTILAH_ASING:
                continue
            seen_asing_runs.add(id(char.run))
            text = _run_text(char.run).strip()
            if not resolver.effective_italic(char.run, paragraph):
                violations.append(
                    f"Paragraf {number}: run IstilahAsing {text!r} tidak "
                    "efektif italic (w:i dimatikan atau style tidak punya w:i)."
                )
            lang = resolver.effective_lang(char.run, paragraph)
            if not lang or lang.casefold() != "en-us":
                violations.append(
                    f"Paragraf {number}: run IstilahAsing {text!r} memakai "
                    f"w:lang {lang!r}, bukan en-US."
                )

    return TermsVerifyReport(
        violations=tuple(violations),
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class ReviewItem:
    text: str
    paragraph: int


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
        for span in _styled_spans(model, ISTILAH_REVIEW):
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

    from .package import DocumentPackage

    return DocumentPackage.load(Path(path))


__all__ = [
    "BARRIER",
    "BIBLIOGRAPHY_STYLE",
    "DEFAULT_ACTION",
    "ISTILAH_ASING",
    "ISTILAH_REVIEW",
    "MARKER_PREFIX",
    "MARKER_RE",
    "MARKER_SUFFIX",
    "CharAction",
    "Glossary",
    "GlossaryEntry",
    "GlossaryError",
    "Marker",
    "MarkerError",
    "ParagraphModel",
    "ReviewItem",
    "StyleResolution",
    "StyleResolver",
    "TermMatch",
    "TermsError",
    "TermsReport",
    "TermsVerifyReport",
    "TextChar",
    "apply_terms",
    "build_paragraph_model",
    "collect_markdown_terms",
    "direct_en_us",
    "direct_italic",
    "direct_style_id",
    "ensure_styles",
    "iter_document_paragraphs",
    "iter_ignored_markers",
    "iter_markers",
    "list_review_items",
    "load_glossary",
    "match_terms",
    "merge_glossaries",
    "open_docx",
    "resolve_style",
    "transform_runs",
    "unique_terms",
    "verify_terms",
    "write_review_file",
]
