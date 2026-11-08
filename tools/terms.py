"""Penanda dan pemeriksa istilah asing pada dokumen DOCX.

Modul ini sengaja memakai python-docx + lxml saja. Semua perubahan XML
dilakukan pada salinan dokumen yang sudah dibuka, lalu disimpan kembali.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml.etree import _Element

W_R = qn("w:r")
W_RPR = qn("w:rPr")
W_RSTYLE = qn("w:rStyle")
W_T = qn("w:t")
W_TAB = qn("w:tab")
W_BR = qn("w:br")
W_CR = qn("w:cr")
W_NO_BREAK_HYPHEN = qn("w:noBreakHyphen")
W_SOFT_HYPHEN = qn("w:softHyphen")
W_FLDCHAR = qn("w:fldChar")
W_FLDSIMPLE = qn("w:fldSimple")
W_INSTRTEXT = qn("w:instrText")
W_HYPERLINK = qn("w:hyperlink")
W_P = qn("w:p")
W_PSTYLE = qn("w:pStyle")
W_STYLE = qn("w:style")
W_STYLEID = qn("w:styleId")
W_TYPE = qn("w:type")
W_NAME = qn("w:name")
W_BASEDON = qn("w:basedOn")
W_VAL = qn("w:val")
W_I = qn("w:i")
W_LANG = qn("w:lang")
W_HIGHLIGHT = qn("w:highlight")
W_HDR = qn("w:hdr")
W_FTR = qn("w:ftr")
R_ID = qn("r:id")

ISTILAH_ASING = "IstilahAsing"
ISTILAH_REVIEW = "IstilahReview"
DEFAULT_PARAGRAPH_FONT = "DefaultParagraphFont"
BIBLIOGRAPHY_STYLE = "Bibliography"
BARRIER = "\ufffc"
MARKER_PREFIX = "{{?"
MARKER_SUFFIX = "?}}"
MARKER_RE = re.compile(
    r"\{\{\?((?:(?!\{\{|\}\}|\r|\n).)+?)\?\}\}"
)

HEADER = ("term", "italic", "gloss_first", "status")
TRUE_FALSE = {"yes", "no"}


class IstilahError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


class GlossaryError(IstilahError):
    """Isi istilah.tsv tidak valid."""


class MarkerError(IstilahError):
    """Penanda {{?…?}} kosong atau tidak valid."""


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
    """Satu-satunya parser penanda {{?…?}}.

    Isi marker tidak boleh kosong, mengandung ``{{``/``}}``, atau newline.
    ``??`` di luar marker dan ``{{??}}`` dianggap error, bukan diabaikan.
    """

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

    # Marker dengan delimiter rusak/terbuka tidak boleh lolos diam-diam.
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

    # Sintaks lama untuk marker kosong tetap harus terdeteksi sebagai error.
    for match in re.finditer(r"\?\?", text):
        if not inside_valid(match.start()):
            raise MarkerError(
                "Penanda '??' kosong tidak diperbolehkan. "
                "Gunakan {{?istilah?}}."
            )

    yield from markers


@dataclass
class GlossaryEntry:
    term: str
    italic: bool
    gloss_first: bool
    status: str
    line_no: int
    pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Batas \w dipakai agar "data" tidak cocok di dalam "datang" atau
        # "metadata". Spasi dibiarkan literal supaya spasi ganda tidak lolos.
        body = re.escape(self.term)
        self.pattern = re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


@dataclass
class Glossary:
    entries: list[GlossaryEntry]


def load_glossary(path: Path) -> Glossary:
    """Baca dan validasi file glosarium TSV."""

    if not path.exists():
        raise GlossaryError(f"Glosarium tidak ditemukan: {path}")

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GlossaryError(f"Glosarium bukan UTF-8 yang valid: {path}") from exc

    entries: list[GlossaryEntry] = []
    seen: dict[str, int] = {}
    header_seen = False
    errors: list[str] = []

    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if not header_seen:
            columns = [column.strip() for column in line.split("\t")]
            if tuple(columns) != HEADER:
                raise GlossaryError(
                    f"Baris {line_no}: header harus "
                    "'term<TAB>italic<TAB>gloss_first<TAB>status'."
                )
            header_seen = True
            continue

        columns = line.split("\t")
        if len(columns) < len(HEADER):
            errors.append(
                f"Baris {line_no}: kolom kurang ({len(columns)} dari 4)."
            )
            continue
        if len(columns) > len(HEADER):
            errors.append(
                f"Baris {line_no}: kolom terlalu banyak ({len(columns)} dari 4)."
            )
            continue

        term, italic, gloss_first, status = (column.strip() for column in columns)
        if not term:
            errors.append(f"Baris {line_no}: term kosong.")
            continue
        if italic not in TRUE_FALSE:
            errors.append(
                f"Baris {line_no}: italic harus 'yes' atau 'no', bukan {italic!r}."
            )
            continue
        if gloss_first not in TRUE_FALSE:
            errors.append(
                f"Baris {line_no}: gloss_first harus 'yes' atau 'no', "
                f"bukan {gloss_first!r}."
            )
            continue
        if status not in {"confirmed", "review"}:
            errors.append(
                f"Baris {line_no}: status harus 'confirmed' atau 'review', "
                f"bukan {status!r}."
            )
            continue

        key = term.casefold()
        if key in seen:
            errors.append(
                f"Baris {line_no}: term duplikat {term!r} "
                f"(sudah ada di baris {seen[key]})."
            )
            continue

        seen[key] = line_no
        entries.append(
            GlossaryEntry(
                term=term,
                italic=italic == "yes",
                gloss_first=gloss_first == "yes",
                status=status,
                line_no=line_no,
            )
        )

    if not header_seen:
        errors.append("Header glosarium tidak ditemukan.")
    if errors:
        raise GlossaryError("Glosarium tidak valid:\n" + "\n".join(errors))
    return Glossary(entries=entries)


@dataclass(frozen=True)
class TermMatch:
    entry: GlossaryEntry
    start: int
    end: int


def find_term_matches(text: str, glossary: Glossary) -> list[TermMatch]:
    """Pilih match terpanjang yang tidak bertumpang tindih.

    Istilah italic=no tetap ikut dipertimbangkan sebagai penghalang, sehingga
    "big data" (yes) dapat mengalahkan "data" (no) di dalamnya.
    """

    candidates: list[TermMatch] = []
    for entry in glossary.entries:
        for match in entry.pattern.finditer(text):
            candidates.append(TermMatch(entry, match.start(), match.end()))

    candidates.sort(
        key=lambda match: (
            -(match.end - match.start),
            match.start,
            match.entry.term.casefold(),
        )
    )

    occupied = bytearray(len(text))
    selected: list[TermMatch] = []
    for match in candidates:
        if any(occupied[match.start : match.end]):
            continue
        occupied[match.start : match.end] = b"\x01" * (match.end - match.start)
        selected.append(match)

    selected.sort(key=lambda match: match.start)
    return selected


@dataclass(frozen=True)
class TextChar:
    run: _Element
    text_node: _Element
    offset: int


@dataclass
class ParagraphModel:
    element: _Element
    text: str
    chars: list[TextChar | None]
    ignored_texts: list[str] = field(default_factory=list)


def _is_external_hyperlink(element: _Element, rels: object) -> bool:
    rel_id = element.get(R_ID)
    if not rel_id:
        return False
    relation = rels.get(rel_id)  # type: ignore[attr-defined]
    if relation is None:
        # Relasi rusak: jangan mengubah isi hyperlink yang tidak bisa dipastikan.
        return True
    return bool(getattr(relation, "is_external", False))


def _text_of_ignored(element: _Element) -> str:
    """Teks mentah untuk mendeteksi penanda di area yang tidak diproses."""

    pieces: list[str] = []
    for node in element.iter():
        if node.tag in (W_T, W_INSTRTEXT):
            pieces.append(node.text or "")
        elif node.tag == W_TAB:
            pieces.append("\t")
        elif node.tag in (W_BR, W_CR):
            pieces.append("\n")
    return "".join(pieces)


def build_paragraph_model(paragraph: _Element, rels: object) -> ParagraphModel:
    """Ambil teks paragraf + peta balik ke w:t.

    Isi field, external hyperlink, dan w:instrText tidak dipetakan. Barrier
    dipasang agar istilah tidak pernah dicocokkan menembus objek tersebut.
    Teks mentah dari area yang dilewati disimpan untuk pelaporan penanda.
    """

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

    def walk(element: _Element, current_run: _Element | None = None) -> None:
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
                elif field_type == "end":
                    if field_depth > 0:
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
                # Hasil field sederhana tidak diproses.
                continue

            if tag == W_HYPERLINK and _is_external_hyperlink(child, rels):
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


def paragraph_style_id(paragraph: _Element) -> str | None:
    ppr = paragraph.find(qn("w:pPr"))
    if ppr is None:
        return None
    pstyle = ppr.find(W_PSTYLE)
    if pstyle is None:
        return None
    return pstyle.get(W_VAL)


def iter_document_paragraphs(doc: object) -> Iterator[tuple[_Element, object]]:
    """Semua paragraf body, tabel, header, dan footer yang bisa dibaca.

    Paragraf ber-style ``Bibliography`` dilewati: italic di sana berasal dari
    CSL untuk judul/jurnal, bukan keputusan istilah pada naskah.
    """

    document_part = doc.part  # type: ignore[attr-defined]
    for paragraph in doc.element.body.iter(W_P):  # type: ignore[attr-defined]
        if paragraph_style_id(paragraph) == BIBLIOGRAPHY_STYLE:
            continue
        yield paragraph, document_part

    seen_parts: set[int] = set()
    for part in document_part.package.iter_parts():
        if id(part) in seen_parts:
            continue
        element = getattr(part, "element", None)
        if element is None or element.tag not in (W_HDR, W_FTR):
            continue
        seen_parts.add(id(part))
        for paragraph in element.iter(W_P):
            if paragraph_style_id(paragraph) == BIBLIOGRAPHY_STYLE:
                continue
            yield paragraph, part


def open_docx(path: Path) -> object:
    if not path.exists():
        raise IstilahError(f"File DOCX tidak ditemukan: {path}")
    try:
        return Document(str(path))
    except PackageNotFoundError as exc:
        raise IstilahError(f"File bukan DOCX yang valid: {path}") from exc


def direct_style_id(run: _Element) -> str | None:
    rpr = run.find(W_RPR)
    if rpr is None:
        return None
    rstyle = rpr.find(W_RSTYLE)
    if rstyle is None:
        return None
    return rstyle.get(W_VAL)


def _on_off_enabled(element: _Element) -> bool:
    value = element.get(W_VAL)
    return value is None or value.casefold() not in {"0", "false", "off", "none"}


def direct_italic(run: _Element) -> bool:
    rpr = run.find(W_RPR)
    if rpr is None:
        return False
    italic = rpr.find(W_I)
    return italic is not None and _on_off_enabled(italic)


def direct_en_us(run: _Element) -> bool:
    rpr = run.find(W_RPR)
    if rpr is None:
        return False
    lang = rpr.find(W_LANG)
    if lang is None:
        return False
    value = lang.get(W_VAL)
    return bool(value and value.casefold() == "en-us")


class StyleResolver:
    """Resolve italic/lang efektif dari direct formatting + character style."""

    def __init__(self, doc: object) -> None:
        self.styles = {
            style.get(W_STYLEID): style
            for style in doc.styles.element.findall(W_STYLE)  # type: ignore[attr-defined]
            if style.get(W_STYLEID)
        }

    def _style_property(self, style_id: str | None, tag: str) -> _Element | None:
        seen: set[str] = set()
        current = style_id
        while current and current not in seen:
            seen.add(current)
            style = self.styles.get(current)
            if style is None:
                return None
            rpr = style.find(W_RPR)
            if rpr is not None:
                prop = rpr.find(tag)
                if prop is not None:
                    return prop
            based_on = style.find(W_BASEDON)
            current = based_on.get(W_VAL) if based_on is not None else None
        return None

    def effective_italic(self, run: _Element) -> bool:
        rpr = run.find(W_RPR)
        if rpr is not None:
            italic = rpr.find(W_I)
            if italic is not None:
                return _on_off_enabled(italic)
        style_id = direct_style_id(run)
        styled = self._style_property(style_id, W_I)
        return styled is not None and _on_off_enabled(styled)

    def effective_lang(self, run: _Element) -> str | None:
        rpr = run.find(W_RPR)
        if rpr is not None:
            lang = rpr.find(W_LANG)
            if lang is not None:
                value = lang.get(W_VAL)
                if value:
                    return value
        style_id = direct_style_id(run)
        styled = self._style_property(style_id, W_LANG)
        if styled is None:
            return None
        return styled.get(W_VAL)


def _run_text(run: _Element) -> str:
    return "".join(node.text or "" for node in run.findall(W_T))


def _make_style(style_id: str, name: str) -> _Element:
    style = OxmlElement("w:style")
    style.set(W_TYPE, "character")
    style.set(W_STYLEID, style_id)

    style_name = OxmlElement("w:name")
    style_name.set(W_VAL, name)
    style.append(style_name)

    based_on = OxmlElement("w:basedOn")
    based_on.set(W_VAL, DEFAULT_PARAGRAPH_FONT)
    style.append(based_on)

    style.append(OxmlElement("w:rPr"))
    return style


def _ensure_based_on(style: _Element) -> None:
    based_on = style.find(W_BASEDON)
    if based_on is None:
        based_on = OxmlElement("w:basedOn")
        name = style.find(W_NAME)
        if name is not None:
            style.insert(style.index(name) + 1, based_on)
        else:
            style.append(based_on)
    based_on.set(W_VAL, DEFAULT_PARAGRAPH_FONT)


def _ensure_rpr(style: _Element) -> _Element:
    rpr = style.find(W_RPR)
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        style.append(rpr)
    return rpr


def _set_italic_on(rpr: _Element) -> None:
    for old in rpr.findall(W_I):
        rpr.remove(old)
    getter = getattr(rpr, "get_or_add_i", None)
    if getter is not None:
        italic = getter()
        italic.val = True
    else:
        rpr.append(OxmlElement("w:i"))


def _set_lang_en_us(rpr: _Element) -> None:
    for old in rpr.findall(W_LANG):
        rpr.remove(old)
    lang = OxmlElement("w:lang")
    lang.set(W_VAL, "en-US")
    rpr.append(lang)


def _set_highlight_yellow(rpr: _Element) -> None:
    for old in rpr.findall(W_HIGHLIGHT):
        rpr.remove(old)
    highlight = OxmlElement("w:highlight")
    highlight.set(W_VAL, "yellow")
    rpr.append(highlight)


def ensure_styles(doc: object) -> None:
    """Pastikan style ada dan invariant IstilahAsing selalu benar."""

    styles = doc.styles.element  # type: ignore[attr-defined]
    existing = {
        style.get(W_STYLEID): style
        for style in styles.findall(W_STYLE)
        if style.get(W_STYLEID)
    }

    asing = existing.get(ISTILAH_ASING)
    if asing is None:
        asing = _make_style(ISTILAH_ASING, "Istilah Asing")
        styles.append(asing)
    elif asing.get(W_TYPE) != "character":
        raise IstilahError(
            f"Style {ISTILAH_ASING} sudah ada tetapi bukan character style."
        )
    _ensure_based_on(asing)
    _set_italic_on(_ensure_rpr(asing))
    _set_lang_en_us(_ensure_rpr(asing))

    review = existing.get(ISTILAH_REVIEW)
    if review is None:
        review = _make_style(ISTILAH_REVIEW, "Istilah Review")
        styles.append(review)
    elif review.get(W_TYPE) != "character":
        raise IstilahError(
            f"Style {ISTILAH_REVIEW} sudah ada tetapi bukan character style."
        )
    _ensure_based_on(review)
    _set_highlight_yellow(_ensure_rpr(review))


@dataclass(frozen=True)
class CharAction:
    delete: bool = False
    style: str | None = None


DEFAULT_ACTION = CharAction()


def _ranges_overlap(
    first_start: int, first_end: int, second_start: int, second_end: int
) -> bool:
    return first_start < second_end and second_start < first_end


def _range_already_handled(model: ParagraphModel, start: int, end: int) -> bool:
    """True jika istilah sudah styled, review, atau italic manual."""

    for char in model.chars[start:end]:
        if char is None:
            return False
        if direct_style_id(char.run) in {ISTILAH_ASING, ISTILAH_REVIEW}:
            continue
        if direct_italic(char.run):
            continue
        return False
    return True


def _make_run(
    run_element: _Element,
    rpr_template: _Element | None,
    text: str,
    style: str | None,
) -> _Element:
    new_run = OxmlElement("w:r")
    for key, value in run_element.attrib.items():
        new_run.set(key, value)

    if rpr_template is not None:
        new_run.append(copy.deepcopy(rpr_template))

    if style is not None:
        rpr = new_run.find(W_RPR)
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            new_run.insert(0, rpr)
        for old_style in rpr.findall(W_RSTYLE):
            rpr.remove(old_style)
        rstyle = OxmlElement("w:rStyle")
        rstyle.set(W_VAL, style)
        rpr.insert(0, rstyle)

        if style == ISTILAH_ASING:
            # Direct formatting lama tidak boleh mengalahkan invariant style.
            _set_italic_on(rpr)
            _set_lang_en_us(rpr)

    text_node = OxmlElement("w:t")
    text_node.text = text
    if text[:1].isspace() or text[-1:].isspace():
        text_node.set(qn("xml:space"), "preserve")
    new_run.append(text_node)
    return new_run


def _copy_non_text_child(
    run_element: _Element, rpr_template: _Element | None, child: _Element
) -> _Element:
    new_run = OxmlElement("w:r")
    for key, value in run_element.attrib.items():
        new_run.set(key, value)
    if rpr_template is not None:
        new_run.append(copy.deepcopy(rpr_template))
    new_run.append(copy.deepcopy(child))
    return new_run


def transform_runs(
    model: ParagraphModel, actions: list[CharAction]
) -> None:
    """Terapkan aksi per karakter, memecah run hanya saat perlu.

    Run yang tidak tersentuh tidak dipindahkan. Run yang tersentuh dipecah
    dengan salinan w:rPr aslinya, sehingga bold/format langsung lain tetap.
    """

    node_actions: dict[int, tuple[_Element, list[CharAction]]] = {}
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
        return

    touched_runs: dict[int, _Element] = {}
    for char in model.chars:
        if char is None:
            continue
        if id(char.text_node) in node_actions:
            touched_runs[id(char.run)] = char.run

    for run in touched_runs.values():
        rpr_template = run.find(W_RPR)
        output: list[_Element] = []

        for child in list(run):
            if child.tag == W_RPR:
                continue

            if child.tag == W_T:
                text = child.text or ""
                node = node_actions.get(id(child))
                char_actions = (
                    node[1] if node is not None else [DEFAULT_ACTION] * len(text)
                )
                index = 0
                while index < len(text):
                    action = char_actions[index]
                    end = index + 1
                    while end < len(text) and char_actions[end] == action:
                        end += 1
                    if not action.delete:
                        output.append(
                            _make_run(
                                run, rpr_template, text[index:end], action.style
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


def _unique_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not term:
            continue
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            result.append(term)
    return result


def review_file_for(path: Path) -> Path:
    return path.parent / "review" / "istilah-baru.txt"


def write_review_file(
    path: Path, terms: list[str], output: Path | None = None
) -> Path:
    if output is None:
        output = review_file_for(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    unique = _unique_terms(terms)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        if unique:
            handle.write("\n".join(unique) + "\n")
    return output


@dataclass
class ApplyResult:
    term_count: int
    review_count: int
    paragraph_count: int
    review_path: Path
    warnings: list[str]


def apply_to_docx(
    path: Path, glossary: Glossary, review_path: Path | None = None
) -> ApplyResult:
    """Terapkan style istilah asing + penanda review ke DOCX."""

    doc = open_docx(path)
    ensure_styles(doc)

    review_terms: list[str] = []
    warnings: list[str] = []
    term_count = 0
    review_count = 0
    paragraph_count = 0

    for number, (paragraph, part) in enumerate(
        iter_document_paragraphs(doc), start=1
    ):
        model = build_paragraph_model(paragraph, part.rels)
        if not model.text and not model.ignored_texts:
            continue
        paragraph_count += 1

        # Pertahankan item review dari apply sebelumnya agar file daftar tidak
        # kosong ketika apply dijalankan ulang pada DOCX yang sama.
        review_terms.extend(_styled_spans(model, ISTILAH_REVIEW))

        for marker in iter_ignored_markers(model):
            review_terms.append(marker.content.strip())
            review_count += 1
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
            review_terms.append(marker.content.strip())
            review_count += 1

        actions = [DEFAULT_ACTION] * len(model.text)

        for start, end in review_ranges:
            for position in range(start, end):
                actions[position] = CharAction(style=ISTILAH_REVIEW)

        for start, end in delete_ranges:
            for position in range(start, end):
                actions[position] = CharAction(delete=True)

        for match in find_term_matches(model.text, glossary):
            if not match.entry.italic:
                continue
            if any(
                _ranges_overlap(match.start, match.end, start, end)
                for start, end in review_ranges + delete_ranges
            ):
                continue
            if any(
                char is not None
                and direct_style_id(char.run) == ISTILAH_REVIEW
                for char in model.chars[match.start : match.end]
            ):
                continue
            if _range_already_handled(model, match.start, match.end):
                continue

            for position in range(match.start, match.end):
                actions[position] = CharAction(style=ISTILAH_ASING)
            term_count += 1

        transform_runs(model, actions)

    doc.save(str(path))
    written_review_path = write_review_file(path, review_terms, review_path)
    return ApplyResult(
        term_count=term_count,
        review_count=review_count,
        paragraph_count=paragraph_count,
        review_path=written_review_path,
        warnings=warnings,
    )


@dataclass
class VerifyResult:
    failures: list[str]
    direct_formatting: list[str]


def _term_status(
    model: ParagraphModel, match: TermMatch, resolver: StyleResolver
) -> str:
    """Kembalikan styled / review / direct / plain untuk satu istilah."""

    chars = model.chars[match.start : match.end]
    if not chars or any(char is None for char in chars):
        return "plain"

    styles = [direct_style_id(char.run) for char in chars]
    if all(style == ISTILAH_ASING for style in styles):
        return "styled"

    # Istilah yang masih ditandai IstilahReview sengaja belum diputuskan.
    # Keberadaannya dilaporkan oleh perintah review, bukan dianggap teks biasa.
    if all(style in {ISTILAH_ASING, ISTILAH_REVIEW} for style in styles):
        return "review"

    if all(
        style == ISTILAH_ASING or resolver.effective_italic(char.run)
        for style, char in zip(styles, chars)
    ):
        return "direct"
    return "plain"


def _unique_runs(chars: list[TextChar | None]) -> list[_Element]:
    runs: list[_Element] = []
    seen: set[int] = set()
    for char in chars:
        if char is None or id(char.run) in seen:
            continue
        seen.add(id(char.run))
        runs.append(char.run)
    return runs


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


def verify_docx(path: Path, glossary: Glossary) -> VerifyResult:
    doc = open_docx(path)
    resolver = StyleResolver(doc)
    failures: list[str] = []
    direct_formatting: list[str] = []
    known_terms = {entry.term.casefold() for entry in glossary.entries}
    language_failures: set[int] = set()

    for number, (paragraph, part) in enumerate(
        iter_document_paragraphs(doc), start=1
    ):
        model = build_paragraph_model(paragraph, part.rels)
        if not model.text and not model.ignored_texts:
            continue

        try:
            markers = list(iter_markers(model.text))
        except MarkerError as exc:
            failures.append(f"Paragraf {number}: {exc}")
            markers = []
        for marker in markers:
            failures.append(
                f"Paragraf {number}: masih ada penanda {marker.raw} "
                "(belum di-apply atau belum diputuskan)."
            )

        try:
            ignored_markers = list(iter_ignored_markers(model))
        except MarkerError as exc:
            failures.append(f"Paragraf {number}: {exc}")
            ignored_markers = []
        for marker in ignored_markers:
            failures.append(
                f"Paragraf {number}: penanda {marker.raw} berada di "
                "field/hyperlink eksternal dan tidak diubah."
            )

        matches = find_term_matches(model.text, glossary)
        for match in matches:
            chars = model.chars[match.start : match.end]
            if not match.entry.italic:
                direct_runs = _unique_runs(chars)
                uses_asing = any(
                    direct_style_id(run) == ISTILAH_ASING for run in direct_runs
                )
                uses_italic = any(
                    resolver.effective_italic(run) for run in direct_runs
                )
                if uses_asing or uses_italic:
                    failures.append(
                        f"Paragraf {number}: istilah italic=no "
                        f"{match.entry.term!r} muncul dengan italic/"
                        "IstilahAsing; seharusnya tegak."
                    )
                continue

            status = _term_status(model, match, resolver)
            if status == "plain":
                failures.append(
                    f"Paragraf {number}: istilah {match.entry.term!r} muncul "
                    "sebagai teks biasa tanpa style IstilahAsing."
                )
            elif status == "direct":
                direct_formatting.append(
                    f"direct formatting: istilah {match.entry.term!r} "
                    f"(paragraf {number}) memakai italic manual tanpa style "
                    "IstilahAsing."
                )

            # Pemeriksaan bahasa hanya untuk run yang memuat istilah italic=yes
            # tetapi tidak ber-style IstilahAsing/Review.
            for run in _unique_runs(chars):
                if id(run) in language_failures:
                    continue
                if direct_style_id(run) in {ISTILAH_ASING, ISTILAH_REVIEW}:
                    continue
                if direct_en_us(run):
                    language_failures.add(id(run))
                    text = _run_text(run).strip()
                    failures.append(
                        f"Paragraf {number}: run {text!r} memuat istilah "
                        f"italic=yes {match.entry.term!r} dan memakai direct "
                        "w:lang en-US tanpa style IstilahAsing."
                    )

        for span in _styled_spans(model, ISTILAH_ASING):
            if span.casefold() not in known_terms:
                failures.append(
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
            if not resolver.effective_italic(char.run):
                failures.append(
                    f"Paragraf {number}: run IstilahAsing {text!r} tidak "
                    "efektif italic (w:i dimatikan atau style tidak punya w:i)."
                )
            lang = resolver.effective_lang(char.run)
            if not lang or lang.casefold() != "en-us":
                failures.append(
                    f"Paragraf {number}: run IstilahAsing {text!r} memakai "
                    f"w:lang {lang!r}, bukan en-US."
                )

    return VerifyResult(failures=failures, direct_formatting=direct_formatting)


@dataclass
class ReviewItem:
    text: str
    paragraph: int


def list_review_items(path: Path) -> list[ReviewItem]:
    doc = open_docx(path)
    items: list[ReviewItem] = []
    for number, (paragraph, part) in enumerate(
        iter_document_paragraphs(doc), start=1
    ):
        model = build_paragraph_model(paragraph, part.rels)
        if not model.text and not model.ignored_texts:
            continue
        for span in _styled_spans(model, ISTILAH_REVIEW):
            items.append(ReviewItem(span, number))
        for marker in iter_markers(model.text):
            items.append(ReviewItem(marker.content.strip(), number))
        for marker in iter_ignored_markers(model):
            items.append(ReviewItem(marker.content.strip(), number))
    return items


def check_markdown(
    path: Path,
    glossary_path: Path | None,
    review_path: Path | None = None,
) -> tuple[list[str], Path]:
    if not path.exists():
        raise IstilahError(f"File Markdown tidak ditemukan: {path}")

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IstilahError(f"File Markdown bukan UTF-8 yang valid: {path}") from exc

    if glossary_path is None:
        for candidate in (path.parent / "istilah.tsv", Path.cwd() / "istilah.tsv"):
            if candidate.exists():
                glossary_path = candidate
                break
    if glossary_path is not None:
        load_glossary(glossary_path)

    terms = _unique_terms(
        [marker.content.strip() for marker in iter_markers(text)]
    )
    output = write_review_file(path, terms, review_path)
    return terms, output


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kelola style istilah asing pada dokumen DOCX."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "check", help="cari penanda {{?istilah?}} pada file Markdown"
    )
    check.add_argument("markdown", type=Path)
    check.add_argument(
        "--glossary",
        type=Path,
        help="opsional; divalidasi bila diberikan atau ditemukan otomatis",
    )
    check.add_argument(
        "--review-file",
        type=Path,
        help="opsional; lokasi daftar review (default: review/ di samping file)",
    )

    apply_parser = subparsers.add_parser(
        "apply", help="terapkan IstilahAsing dan IstilahReview ke DOCX"
    )
    apply_parser.add_argument("docx", type=Path)
    apply_parser.add_argument("--glossary", type=Path, required=True)
    apply_parser.add_argument(
        "--review-file",
        type=Path,
        help="opsional; lokasi daftar review (default: review/ di samping DOCX)",
    )

    verify = subparsers.add_parser("verify", help="periksa hasil apply DOCX")
    verify.add_argument("docx", type=Path)
    verify.add_argument("--glossary", type=Path, required=True)

    review = subparsers.add_parser(
        "review", help="cetak istilah yang belum diputuskan di DOCX"
    )
    review.add_argument("docx", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "check":
            terms, output = check_markdown(
                args.markdown, args.glossary, args.review_file
            )
            if terms:
                print(f"Ditemukan {len(terms)} istilah baru:")
                for term in terms:
                    print(f"- {term}")
                print(f"Ditulis ke: {output}")
                return 2
            print("Tidak ada penanda {{?istilah?}} pada Markdown.")
            print(f"Daftar kosong ditulis ke: {output}")
            return 0

        if args.command == "apply":
            glossary = load_glossary(args.glossary)
            result = apply_to_docx(args.docx, glossary, args.review_file)
            for warning in result.warnings:
                print(f"PERINGATAN: {warning}")
            print(
                f"DOCX diperbarui: {result.term_count} istilah asing, "
                f"{result.review_count} penanda review."
            )
            print(f"Daftar review: {result.review_path}")
            return 0

        if args.command == "verify":
            glossary = load_glossary(args.glossary)
            result = verify_docx(args.docx, glossary)
            for warning in result.direct_formatting:
                print(f"[direct formatting] {warning.removeprefix('direct formatting: ')}")
            if result.failures:
                print(f"VERIFY GAGAL ({len(result.failures)} masalah):")
                for failure in result.failures:
                    print(f"- {failure}")
                return 1
            print("VERIFY OK: tidak ada pelanggaran.")
            return 0

        if args.command == "review":
            items = list_review_items(args.docx)
            if not items:
                print("Tidak ada istilah yang belum diputuskan.")
                return 0
            print(f"{len(items)} istilah belum diputuskan:")
            for item in items:
                print(f"- {item.text} (paragraf {item.paragraph})")
            return 0

        parser.error(f"Perintah tidak dikenal: {args.command}")
        return 2
    except (IstilahError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
