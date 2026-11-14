"""Parsing input, target matrix, dan validasi kombinasi target CLI."""

from enum import StrEnum
from pathlib import Path

from . import CliError


class InputKind(StrEnum):
    """Jenis input yang didukung permukaan CLI AutoOffice v1."""

    MARKDOWN = "markdown"
    DECK = "deck"


MD_TARGETS: tuple[str, ...] = ("docx", "pdf")
DECK_TARGETS: tuple[str, ...] = ("pptx", "pdf", "slides")
DOCTOR_TARGETS: tuple[str, ...] = ("docx", "pptx", "pdf", "slides")

_KIND_TARGETS: dict[InputKind, tuple[str, ...]] = {
    InputKind.MARKDOWN: MD_TARGETS,
    InputKind.DECK: DECK_TARGETS,
}

_KIND_SUFFIX: dict[InputKind, str] = {
    InputKind.MARKDOWN: ".md",
    InputKind.DECK: ".yaml",
}

_SUFFIX_KIND: dict[str, InputKind] = {
    ".md": InputKind.MARKDOWN,
    ".yaml": InputKind.DECK,
}


def detect_input_kind(path: Path) -> InputKind:
    """Tentukan jenis input dari ekstensi ``.md`` atau ``.yaml``.

    Ekstensi lain ditolak dengan exit code 2 sebelum modul domain dimuat.
    """
    kind = _SUFFIX_KIND.get(path.suffix.lower())
    if kind is None:
        raise CliError(
            f"input harus berberkas .md atau .yaml, bukan '{path.name}'",
            code="CLI-INPUT-TYPE",
            exit_code=2,
            path=str(path),
        )
    return kind


def canonical_targets(kind: InputKind) -> tuple[str, ...]:
    """Kembalikan urutan target kanonik untuk satu jenis input."""
    return _KIND_TARGETS[kind]


def default_check_targets(kind: InputKind) -> tuple[str, ...]:
    """Target bawaan ``check``: semua target valid untuk input tersebut."""
    return canonical_targets(kind)


def parse_targets(
    raw: str | None,
    kind: InputKind,
    *,
    required: bool = True,
) -> tuple[str, ...]:
    """Parse target dipisah koma dan kembalikan urutan kanonik tanpa duplikat.

    Aturan kontrak: spasi setelah koma boleh, duplikat dihapus, ``all`` tidak
    boleh digabung dengan target lain, dan target yang tidak valid untuk jenis
    input ditolak dengan exit code 2.
    """
    if raw is None:
        if required:
            raise CliError(
                "--target wajib untuk build",
                code="CLI-TARGET-MISSING",
                exit_code=2,
            )
        return canonical_targets(kind)

    tokens = [token.strip() for token in raw.split(",")]
    if not tokens or any(not token for token in tokens):
        raise CliError(
            f"daftar target tidak valid: {raw!r}",
            code="CLI-TARGET-EMPTY",
            exit_code=2,
        )

    allowed = set(canonical_targets(kind))
    seen = set(tokens)
    unknown = sorted(seen - allowed - {"all"})
    if unknown:
        raise CliError(
            f"target tidak valid untuk input {_KIND_SUFFIX[kind]}: {', '.join(unknown)}; "
            f"pilihan: {', '.join(canonical_targets(kind))}, all",
            code="CLI-TARGET-INVALID",
            exit_code=2,
        )
    if "all" in seen:
        if len(seen) > 1:
            raise CliError(
                "target 'all' tidak boleh digabung dengan target lain",
                code="CLI-TARGET-ALL-MIXED",
                exit_code=2,
            )
        return canonical_targets(kind)

    return tuple(target for target in canonical_targets(kind) if target in seen)


def parse_doctor_targets(raw: str | None) -> tuple[str, ...] | None:
    """Parse target opsional ``doctor`` dari gabungan permukaan document/deck."""
    if raw is None:
        return None
    tokens = [token.strip() for token in raw.split(",")]
    if not tokens or any(not token for token in tokens):
        raise CliError(
            f"daftar target doctor tidak valid: {raw!r}",
            code="CLI-TARGET-EMPTY",
            exit_code=2,
        )
    allowed = set(DOCTOR_TARGETS)
    seen = set(tokens)
    unknown = sorted(seen - allowed - {"all"})
    if unknown:
        raise CliError(
            f"target doctor tidak valid: {', '.join(unknown)}; "
            f"pilihan: {', '.join(DOCTOR_TARGETS)}, all",
            code="CLI-TARGET-INVALID",
            exit_code=2,
        )
    if "all" in seen:
        if len(seen) > 1:
            raise CliError(
                "target 'all' tidak boleh digabung dengan target lain",
                code="CLI-TARGET-ALL-MIXED",
                exit_code=2,
            )
        return DOCTOR_TARGETS
    return tuple(target for target in DOCTOR_TARGETS if target in seen)


__all__ = [
    "DECK_TARGETS",
    "DOCTOR_TARGETS",
    "MD_TARGETS",
    "InputKind",
    "canonical_targets",
    "default_check_targets",
    "detect_input_kind",
    "parse_doctor_targets",
    "parse_targets",
]
