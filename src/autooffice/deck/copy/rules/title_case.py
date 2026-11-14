"""Rule ``title_case``: Title Case per bahasa untuk judul slide.

Tokenisasi per whitespace dan tanda baca di tepi token diabaikan saat memeriksa
huruf. Token tanda baca murni tidak dihitung sebagai kata pertama atau terakhir.
Kata pertama dan terakhir selalu kapital; kata fungsi di tengah lowercase.
Akronim yang seluruhnya kapital dipertahankan. Judul tidak boleh memuat koma
atau diakhiri titik.
"""

import re

from ..config import Language
from ..diagnostics import RuleViolation

LOWERCASE_WORDS_ID: frozenset[str] = frozenset(
    {
        "agar",
        "antara",
        "atas",
        "bagi",
        "dalam",
        "dan",
        "dari",
        "demi",
        "dengan",
        "di",
        "hingga",
        "jika",
        "kalau",
        "ke",
        "maupun",
        "oleh",
        "pada",
        "per",
        "sampai",
        "sebagai",
        "serta",
        "supaya",
        "tentang",
        "terhadap",
        "untuk",
        "yang",
    }
)
LOWERCASE_WORDS_EN: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "from",
        "in",
        "nor",
        "of",
        "on",
        "or",
        "per",
        "the",
        "to",
        "via",
        "vs",
    }
)
LOWERCASE_WORDS: dict[Language, frozenset[str]] = {
    "id": LOWERCASE_WORDS_ID,
    "en": LOWERCASE_WORDS_EN,
}
_EDGE_PUNCTUATION = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)
_HINT = "Gunakan Title Case; kata fungsi di tengah tetap huruf kecil."


def check_title_case(text: str, *, language: Language = "id") -> tuple[RuleViolation, ...]:
    """Periksa satu judul slide terhadap aturan Title Case bahasa."""
    violations: list[RuleViolation] = []
    stripped = text.strip()
    if not stripped:
        return (
            RuleViolation(
                message="Judul slide tidak boleh kosong.",
                hint="Isi judul dengan frasa benda yang konkret.",
            ),
        )

    tokens = [
        (index, match.group(0), match.start(), _strip_word(match.group(0)))
        for index, match in enumerate(re.finditer(r"\S+", text))
    ]
    words = [token for token in tokens if token[3]]
    if not words:
        return (
            RuleViolation(
                message="Judul slide tidak boleh kosong.",
                hint="Isi judul dengan frasa benda yang konkret.",
            ),
        )
    first_index = words[0][0]
    last_index = words[-1][0]

    # Token tanda baca murni seperti "..." bukan akhir kalimat.
    if words[-1][1].endswith("."):
        violations.append(
            RuleViolation(
                message="Judul slide tidak boleh diakhiri titik.",
                hint="Hapus titik akhir pada judul.",
                offset=len(text.rstrip()) - 1,
            )
        )
    if "," in text:
        violations.append(
            RuleViolation(
                message="Judul slide tidak boleh memuat koma.",
                hint="Pisahkan daftar menjadi kalimat atau frasa tanpa koma.",
                offset=text.index(","),
            )
        )

    for index, _, position, word in words:
        lower = word.lower()
        first = index == first_index
        last = index == last_index
        is_function_word = lower in LOWERCASE_WORDS[language]
        if is_function_word and not first and not last:
            if word != lower:
                violations.append(
                    RuleViolation(
                        message=f"Kata fungsi '{word}' di tengah judul harus huruf kecil.",
                        hint=_HINT,
                        offset=position,
                    )
                )
            continue
        if not _starts_uppercase(word):
            violations.append(
                RuleViolation(
                    message=f"Kata '{word}' pada judul harus diawali huruf kapital.",
                    hint=_HINT,
                    offset=position,
                )
            )
    return tuple(violations)


def _strip_word(raw: str) -> str:
    return _EDGE_PUNCTUATION.sub("", raw)


def _starts_uppercase(word: str) -> bool:
    first = word[0]
    if first.isdigit():
        return True
    if first.isupper():
        return True
    # Skrip tanpa huruf besar/kecil (CJK, Arab, Ibrani, Thai) tidak punya
    # konsep Title Case; jangan paksa kapitalisasi.
    return first.isalpha() and not first.islower()
