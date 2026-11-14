"""Rule pola naskah: negasi berpasangan, kontras, triad, closer, paired label.

Semua regex dan heuristik di modul ini dibekukan oleh
``docs/contracts/copy.md`` bagian "Detail heuristik". Tidak ada regex yang
dibaca dari konfigurasi pengguna.
"""

import re
from dataclasses import dataclass

from ..config import Language
from ..diagnostics import RuleViolation

_NEGATIVE_PARALLELISM: dict[Language, tuple[re.Pattern[str], ...]] = {
    "id": (
        re.compile(
            r"\b(?:bukan|tidak)\s+hanya\b[^.!?]{0,200}?\b(?:tetapi|tapi|melainkan)\s+juga\b",
            re.IGNORECASE,
        ),
    ),
    "en": (
        re.compile(
            r"\bnot\s+(?:only|just|merely)\b[^.!?]{0,200}?\bbut\s+(?:also|rather)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bnot\s+(?:only|just|merely)\b[^.!?]{0,200}?\bbut\b[^.!?]{0,40}?"
            r"\b(?:also|too|as\s+well)\b",
            re.IGNORECASE,
        ),
    ),
}
_CONTRAST_PATTERN = re.compile(r",\s*bukan\s+", re.IGNORECASE)
_FORCED_TRIAD = re.compile(
    r"[^\s,.;:!?][^,.;:!?]*,\s*[^,.;:!?]+,\s*dan\s+[^,.;:!?]+",
    re.IGNORECASE,
)
_ONE_LINE_CLOSER_KEY = re.compile(
    r"^(?P<prefix>.*)\.(?P<index>(?:[A-Za-z]+)?\d+)\.(?P<leaf>body|text)$"
)
_KNOWN_VERBS = frozenset(
    {
        "ada",
        "adalah",
        "akan",
        "bisa",
        "buat",
        "dapat",
        "dipakai",
        "guna",
        "ialah",
        "jadi",
        "memakai",
        "menjadi",
        "pakai",
        "punya",
        "sudah",
        "telah",
    }
)
_VERB_PREFIX = re.compile(r"^(?:me|men|mem|meng|meny|menge|di|ber|ter)[a-z]{2,}$")
_LONG_WORD = re.compile(r"[^\W\d_]{3,}")
_WORD_SEPARATOR = re.compile(r"[^\w]+")

ONE_LINE_CLOSER_MAX_WORDS = 6
PAIRED_CLAUSE_MAX_WORDS = 8


@dataclass(frozen=True, slots=True)
class CloserGroup:
    """Komponen key yang membentuk satu grup ``body`` atau ``text``."""

    prefix: str
    index: str
    leaf: str
    number: int


def check_negative_parallelism(
    text: str,
    *,
    language: Language = "id",
) -> tuple[RuleViolation, ...]:
    """Cari pola ``bukan hanya ... tetapi juga`` dan padanan Inggrisnya."""
    violations: list[RuleViolation] = []
    for pattern in _NEGATIVE_PARALLELISM[language]:
        for match in pattern.finditer(text):
            violations.append(
                RuleViolation(
                    message=f"Teks memakai negasi berpasangan: '{_excerpt(match.group(0))}'.",
                    hint="Pecah menjadi dua pernyataan atau pilih satu fokus utama.",
                    offset=match.start(),
                )
            )
    return tuple(violations)


def check_contrast_pattern(text: str) -> tuple[RuleViolation, ...]:
    """Cari pola koma diikuti ``bukan``."""
    return tuple(
        RuleViolation(
            message=f"Teks memakai pola kontras: '{_excerpt(match.group(0))}'.",
            hint="Tulis pernyataan langsung tanpa kontras retoris.",
            offset=match.start(),
        )
        for match in _CONTRAST_PATTERN.finditer(text)
    )


def check_forced_triad(text: str) -> tuple[RuleViolation, ...]:
    """Cari pola tiga frasa ``A, B, dan C`` dalam satu kalimat."""
    return tuple(
        RuleViolation(
            message=f"Teks memakai triad paksa: '{_excerpt(match.group(0))}'.",
            hint="Pakai jumlah item sesuai isi; hapus triad yang hanya demi irama.",
            offset=match.start(),
        )
        for match in _FORCED_TRIAD.finditer(text)
    )


def check_paired_clause_label(text: str) -> tuple[RuleViolation, ...]:
    """Periksa label dua fragmen tanpa verba dan maksimal delapan kata."""
    fragments = paired_clause_fragments(text)
    if fragments is None:
        return ()
    left, right = fragments
    return (
        RuleViolation(
            message=f"Label dua fragmen tanpa verba: '{left}, {right}'.",
            hint=(
                "Ganti dengan satu frasa benda yang memakai pewatas, misalnya 'Peta Tiga Bagian'."
            ),
        ),
    )


def paired_clause_fragments(text: str) -> tuple[str, str] | None:
    """Kembalikan dua fragmen bila teks memenuhi kontrak paired clause."""
    if re.search(r"[\r\n]\s*$", text):
        return None
    value = text.strip()
    if not value:
        return None
    if value.endswith(("\n", ".", "!", "?", ":", ";")):
        return None
    if value.count(",") != 1:
        return None
    left, right = (part.strip() for part in value.split(",", 1))
    if not left or not right:
        return None
    if len(value.split()) > PAIRED_CLAUSE_MAX_WORDS:
        return None
    if not _LONG_WORD.search(left) or not _LONG_WORD.search(right):
        return None
    if _fragment_has_verb(left) or _fragment_has_verb(right):
        return None
    return left, right


def parse_closer_key(key: str) -> CloserGroup | None:
    """Parse key ``...<index>.body|text`` untuk aturan one-line closer."""
    match = _ONE_LINE_CLOSER_KEY.fullmatch(key)
    if match is None:
        return None
    prefix = match.group("prefix")
    index = match.group("index")
    if not prefix:
        return None
    numeric = re.search(r"\d+", index)
    if numeric is None:  # pragma: no cover - regex menjamin index memuat digit
        return None
    return CloserGroup(
        prefix=prefix,
        index=index,
        leaf=match.group("leaf"),
        number=int(numeric.group(0)),
    )


def is_one_line_closer(text: str) -> bool:
    """True bila teks closer memiliki kurang dari enam kata."""
    return len(text.split()) < ONE_LINE_CLOSER_MAX_WORDS


def _fragment_has_verb(fragment: str) -> bool:
    words = [word for word in _WORD_SEPARATOR.split(fragment.lower()) if word]
    return any(word in _KNOWN_VERBS or _VERB_PREFIX.fullmatch(word) for word in words)


def _excerpt(value: str) -> str:
    compact = " ".join(value.split())
    if len(compact) <= 80:
        return compact
    return f"{compact[:77]}..."
