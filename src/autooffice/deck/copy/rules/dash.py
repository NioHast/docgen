"""Rule ``dash``: menolak em dash U+2014 dan en dash U+2013."""

from ..diagnostics import RuleViolation

_DASH_NAMES = {
    "\u2014": "em dash (U+2014)",
    "\u2013": "en dash (U+2013)",
}
_HINT = "Gunakan tanda hubung biasa, koma, titik dua, atau tanda kurung."


def check_dash(text: str) -> tuple[RuleViolation, ...]:
    """Cari setiap em dash atau en dash pada teks."""
    violations: list[RuleViolation] = []
    for offset, character in enumerate(text):
        name = _DASH_NAMES.get(character)
        if name is None:
            continue
        violations.append(
            RuleViolation(
                message=f"Teks memakai {name}.",
                hint=_HINT,
                offset=offset,
            )
        )
    return tuple(violations)
