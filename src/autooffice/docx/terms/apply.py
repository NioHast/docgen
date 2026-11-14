"""Penerapan glosarium ke DOCX.

Modul ini memuat pembuatan style istilah, transformasi run, dan
:func:`apply_terms`. Modul bergantung pada :mod:`docgen.docx.terms.model`
serta helper DOCX kanonis; modul tidak boleh mengimpor ``verify`` atau
package induk ``terms`` agar arah dependensi tetap satu arah.
"""

import copy
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from ..package import DOCUMENT_PART
from ..package.names import W_RPR, W_RSTYLE, W_T, W_VAL, W
from ..package.runs import build_run, copy_rpr
from ..package.styles import StyleError, ensure_character_style
from .glossary import Glossary, TermsError
from .model import (
    ISTILAH_ASING,
    ISTILAH_REVIEW,
    ParagraphModel,
    _iter_all_paragraphs,
    build_paragraph_model,
    direct_italic,
    direct_style_id,
    iter_ignored_markers,
    iter_markers,
    match_terms,
    styled_spans,
    unique_terms,
    write_review_file,
)

W_I = W + "i"
W_LANG = W + "lang"


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
    """Buat run lewat :func:`build_run`, lalu salin atribut run sumber."""

    new_run = build_run(text=text, rpr=rpr)
    for key, value in run_element.attrib.items():
        new_run.set(key, value)
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

        review_terms.extend(styled_spans(model, ISTILAH_REVIEW))

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
        root = package.xml(DOCUMENT_PART)  # type: ignore[attr-defined]
        package.set_xml(DOCUMENT_PART, root)  # type: ignore[attr-defined]

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


__all__ = [
    "DEFAULT_ACTION",
    "CharAction",
    "TermsReport",
    "apply_terms",
    "ensure_styles",
    "transform_runs",
]
