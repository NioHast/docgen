"""Verifikasi invariant istilah pada DOCX.

Modul ini memuat :func:`verify_terms` beserta helper status istilah. Modul
hanya bergantung pada :mod:`docgen.docx.terms.model` dan helper DOCX kanonis;
tidak ada impor balik ke ``apply`` atau package induk ``terms``.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from lxml import etree

from ..package.paragraphs import paragraph_text
from .glossary import Glossary
from .model import (
    ISTILAH_ASING,
    ISTILAH_REVIEW,
    MarkerError,
    ParagraphModel,
    StyleResolver,
    TermMatch,
    TextChar,
    build_paragraph_model,
    direct_en_us,
    direct_style_id,
    iter_document_paragraphs,
    iter_ignored_markers,
    iter_markers,
    match_terms,
    styled_spans,
)


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
                    text = paragraph_text(run).strip()
                    violations.append(
                        f"Paragraf {number}: run {text!r} memuat istilah "
                        f"italic=yes {match.entry.term!r} dan memakai direct "
                        "w:lang en-US tanpa style IstilahAsing."
                    )

        for span in styled_spans(model, ISTILAH_ASING):
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
            text = paragraph_text(char.run).strip()
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


__all__ = [
    "TermsVerifyReport",
    "verify_terms",
]
