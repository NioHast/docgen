"""Rule deterministik copy checker AutoOffice v1."""

from .banned_phrases import DEFAULT_BANNED_PHRASES, check_banned_phrases
from .dash import check_dash
from .patterns import (
    ONE_LINE_CLOSER_MAX_WORDS,
    PAIRED_CLAUSE_MAX_WORDS,
    CloserGroup,
    check_contrast_pattern,
    check_forced_triad,
    check_negative_parallelism,
    check_paired_clause_label,
    is_one_line_closer,
    paired_clause_fragments,
    parse_closer_key,
)
from .sentence_length import check_sentence_length
from .title_case import (
    LOWERCASE_WORDS,
    LOWERCASE_WORDS_EN,
    LOWERCASE_WORDS_ID,
    check_title_case,
)

__all__ = [
    "DEFAULT_BANNED_PHRASES",
    "LOWERCASE_WORDS",
    "LOWERCASE_WORDS_EN",
    "LOWERCASE_WORDS_ID",
    "ONE_LINE_CLOSER_MAX_WORDS",
    "PAIRED_CLAUSE_MAX_WORDS",
    "CloserGroup",
    "check_banned_phrases",
    "check_contrast_pattern",
    "check_dash",
    "check_forced_triad",
    "check_negative_parallelism",
    "check_paired_clause_label",
    "check_sentence_length",
    "check_title_case",
    "is_one_line_closer",
    "paired_clause_fragments",
    "parse_closer_key",
]
