"""Tes matriks target, deteksi input, dan target doctor."""

from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.targets import (
    DOCTOR_TARGETS,
    InputKind,
    canonical_targets,
    default_check_targets,
    detect_input_kind,
    parse_doctor_targets,
    parse_targets,
)


@pytest.mark.parametrize(
    ("raw", "suffix", "expected"),
    [
        ("docx", ".md", ("docx",)),
        ("pdf", ".md", ("pdf",)),
        ("pdf, docx", ".md", ("docx", "pdf")),
        ("docx,docx", ".md", ("docx",)),
        ("all", ".md", ("docx", "pdf")),
        ("pptx", ".yaml", ("pptx",)),
        ("slides", ".yaml", ("slides",)),
        ("pdf,slides", ".yaml", ("pdf", "slides")),
        ("slides, pptx, pdf", ".yaml", ("pptx", "pdf", "slides")),
        ("all", ".yaml", ("pptx", "pdf", "slides")),
    ],
)
def test_parse_targets_matrix(raw: str, suffix: str, expected: tuple[str, ...]) -> None:
    kind = detect_input_kind(Path(f"input{suffix}"))
    assert parse_targets(raw, kind) == expected


@pytest.mark.parametrize(
    ("raw", "suffix", "match"),
    [
        ("all,docx", ".md", "all"),
        ("ppt", ".md", "target tidak valid"),
        ("pptx", ".md", "target tidak valid"),
        ("docx", ".yaml", "target tidak valid"),
        ("", ".md", "tidak valid"),
        ("docx,,pdf", ".md", "tidak valid"),
    ],
)
def test_parse_targets_rejects_invalid(raw: str, suffix: str, match: str) -> None:
    kind = detect_input_kind(Path(f"input{suffix}"))
    with pytest.raises(CliError, match=match):
        parse_targets(raw, kind)


def test_parse_targets_requires_target_for_build() -> None:
    with pytest.raises(CliError, match="wajib"):
        parse_targets(None, InputKind.MARKDOWN)


def test_parse_targets_optional_for_check() -> None:
    assert parse_targets(None, InputKind.DECK, required=False) == canonical_targets(InputKind.DECK)


def test_default_check_targets_cover_all_valid_targets() -> None:
    assert default_check_targets(InputKind.MARKDOWN) == ("docx", "pdf")
    assert default_check_targets(InputKind.DECK) == ("pptx", "pdf", "slides")


@pytest.mark.parametrize("name", ["document.txt", "document.yml", "document"])
def test_detect_input_kind_rejects_unknown_suffix(name: str) -> None:
    with pytest.raises(CliError, match=r"\.md atau \.yaml"):
        detect_input_kind(Path(name))


def test_parse_doctor_targets_none() -> None:
    assert parse_doctor_targets(None) is None


def test_parse_doctor_targets_canonical_order() -> None:
    assert parse_doctor_targets("pptx, docx") == ("docx", "pptx")


def test_parse_doctor_targets_all() -> None:
    assert parse_doctor_targets("all") == DOCTOR_TARGETS


def test_parse_doctor_targets_rejects_mixed_all() -> None:
    with pytest.raises(CliError, match="all"):
        parse_doctor_targets("all,docx")
