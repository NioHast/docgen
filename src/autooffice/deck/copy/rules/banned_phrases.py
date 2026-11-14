"""Rule ``banned_phrases``: frasa literal Indonesia dan Inggris.

Daftar default Indonesia diadaptasi dari ``scripts/check-copy.js`` deck-studio.
Daftar Inggris memuat kata dan frasa stok yang paling sering muncul pada naskah
mesin. ``copy.yaml`` hanya boleh menambah frasa literal; regex tidak diterima.
"""

import re
from collections.abc import Mapping
from types import MappingProxyType

from ..config import Language
from ..diagnostics import RuleViolation

DEFAULT_BANNED_PHRASES: Mapping[Language, tuple[str, ...]] = MappingProxyType(
    {
        "id": (
            "bukan hanya",
            "tidak hanya",
            "lebih dari sekadar",
            "di era",
            "lanskap",
            "krusial",
            "hiruk pikuk",
            "tidak dapat dipungkiri",
            "sebagai bentuk",
            "memberikan gambaran komprehensif",
            "memainkan peran penting",
            "solusi terbaik",
            "berbagai macam",
        ),
        "en": (
            "align with",
            "aligns with",
            "aligned with",
            "aligning with",
            "at the end of the day",
            "bolster",
            "bolstered",
            "bolsters",
            "bolstering",
            "crucial",
            "cutting-edge",
            "deep dive",
            "delve",
            "delved",
            "delves",
            "delving",
            "enduring",
            "enhance",
            "enhanced",
            "enhances",
            "enhancing",
            "game-changer",
            "garner",
            "garnered",
            "garners",
            "garnering",
            "groundbreaking",
            "in today's",
            "interplay",
            "intricate",
            "it is worth noting",
            "it's worth noting",
            "landscape",
            "leverage",
            "leveraged",
            "leverages",
            "leveraging",
            "meticulous",
            "meticulously",
            "pivotal",
            "robust",
            "seamless",
            "showcase",
            "showcased",
            "showcases",
            "showcasing",
            "stands as a testament",
            "tapestry",
            "testament",
            "underscore",
            "underscored",
            "underscores",
            "underscoring",
            "unlock",
            "unlocked",
            "unlocks",
            "unlocking",
            "valuable",
            "vibrant",
        ),
    }
)

_HINT = "Tulis pernyataan langsung dan konkret; lihat docs/learn/humanizer.md."
_APOSTROPHES = str.maketrans({"\u2018": "'", "\u2019": "'"})


def check_banned_phrases(
    text: str,
    *,
    language: Language = "id",
    extra: Mapping[Language, tuple[str, ...]] | None = None,
) -> tuple[RuleViolation, ...]:
    """Cari frasa terlarang sesuai rule pack bahasa."""
    phrases = _phrases_for(language, extra)
    normalized = text.translate(_APOSTROPHES)
    violations: list[RuleViolation] = []
    for phrase in phrases:
        literal = phrase.translate(_APOSTROPHES)
        pattern = re.compile(rf"(?<!\w){re.escape(literal)}(?!\w)", re.IGNORECASE)
        match = pattern.search(normalized)
        if match is None:
            continue
        violations.append(
            RuleViolation(
                message=f"Teks memakai frasa terlarang: '{phrase}'.",
                hint=_HINT,
                offset=match.start(),
            )
        )
    return tuple(violations)


def _phrases_for(
    language: Language,
    extra: Mapping[Language, tuple[str, ...]] | None,
) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for phrase in (*DEFAULT_BANNED_PHRASES[language], *(extra or {}).get(language, ())):
        folded = phrase.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        merged.append(phrase)
    return tuple(merged)
