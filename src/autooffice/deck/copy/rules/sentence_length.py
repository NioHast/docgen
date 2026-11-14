"""Rule ``sentence_length``: kalimat lebih dari batas kata.

Pemisahan kalimat memakai batas akhir kalimat ``.``, ``!``, atau ``?`` yang
diikuti whitespace. Teks tanpa tanda akhir dianggap satu kalimat.
"""

import re

from ..config import DEFAULT_MAX_WORDS
from ..diagnostics import RuleViolation

_SENTENCE_BOUNDARY = re.compile(r"(?:(?<=[.!?][\u201d\"\u2019'])|(?<=[.!?]))\s+")
_LIST_MARKER = re.compile(r"(?m)^[ \t]*(?:[-*+]|\d+[.)])(?:[ \t]+|$)")
_HINT = "Pecah kalimat menjadi pernyataan pendek atau pindahkan detail ke bullet."


def check_sentence_length(
    text: str,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
) -> tuple[RuleViolation, ...]:
    """Cari kalimat yang jumlah katanya melebihi ``max_words``."""
    violations: list[RuleViolation] = []
    for sentence, offset in _sentences(text):
        count = _word_count(sentence)
        if count <= max_words:
            continue
        violations.append(
            RuleViolation(
                message=f"Kalimat memuat {count} kata; batasnya {max_words} kata.",
                hint=_HINT,
                offset=offset,
            )
        )
    return tuple(violations)


def _word_count(sentence: str) -> int:
    without_markers = _LIST_MARKER.sub("", sentence)
    return len(without_markers.split())


def _sentences(text: str) -> tuple[tuple[str, int], ...]:
    sentences: list[tuple[str, int]] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        _append_sentence(sentences, text, start, match.start())
        start = match.end()
    _append_sentence(sentences, text, start, len(text))
    return tuple(sentences)


def _append_sentence(
    sentences: list[tuple[str, int]],
    text: str,
    start: int,
    end: int,
) -> None:
    raw = text[start:end]
    stripped = raw.strip()
    if not stripped:
        return
    leading = len(raw) - len(raw.lstrip())
    sentences.append((stripped, start + leading))
