"""Tes cabang check deck: theme, layout, transcript, copy, dan coverage."""

from dataclasses import replace
from pathlib import Path

import pytest

from autooffice.cli.check import Finding, check_deck
from autooffice.deck.layout.spec import LayoutError
from autooffice.deck.model import CoveragePlan, compile_deck_file
from autooffice.design import DesignTokenError
from autooffice.errors import AutoOfficeError


def test_finding_format_includes_line_key_and_hint() -> None:
    finding = Finding(
        severity="error",
        message="kalimat terlalu panjang",
        rule="copy",
        key="s01.title.text",
        file="deck.yaml",
        line=7,
        hint="Pendekkan kalimat.",
    )

    assert finding.format() == (
        "deck.yaml:7: error: kalimat terlalu panjang [copy] [s01.title.text] "
        "Hint: Pendekkan kalimat."
    )


def test_check_deck_reports_missing_theme_name(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = compile_deck_file(deck_path)
    monkeypatch.setattr(
        "autooffice.deck.model.compile_deck_file",
        lambda _path: replace(compiled, theme_name=""),
    )

    result = check_deck(deck_path, ("pptx",))

    theme_findings = [finding for finding in result.findings if finding.rule == "theme"]
    assert len(theme_findings) == 1
    assert "theme_name" in theme_findings[0].message
    assert result.ok is False


def test_check_deck_reports_missing_meta_title(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = compile_deck_file(deck_path)
    monkeypatch.setattr(
        "autooffice.deck.model.compile_deck_file",
        lambda _path: replace(compiled, meta={"author": "Tim AutoOffice"}),
    )

    result = check_deck(deck_path, ("pptx",))

    finding = next(item for item in result.findings if item.rule == "meta")
    assert "meta.title" in finding.message
    assert result.ok is False


def test_check_deck_reports_theme_autooffice_error(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_theme(_name: str) -> object:
        raise DesignTokenError("token rusak")

    monkeypatch.setattr("autooffice.design.resolve_theme", fail_theme)

    result = check_deck(deck_path, ("pptx",))

    finding = next(item for item in result.findings if item.rule == "theme")
    assert "theme 'indigo' gagal di-resolve" in finding.message
    assert "token rusak" in finding.message


def test_check_deck_reports_layout_failure(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_plan(_deck: object, _theme: object, *, fail_on_overflow: bool = False) -> object:
        raise LayoutError("grid tidak muat")

    monkeypatch.setattr("autooffice.deck.layout.overflow.plan_deck", fail_plan)

    result = check_deck(deck_path, ("pptx",))

    finding = next(item for item in result.findings if item.rule == "layout")
    assert "layout gagal" in finding.message
    assert "grid tidak muat" in finding.message


def test_check_deck_reports_missing_alt_and_duplicate_keys(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coverage = CoveragePlan(
        deck_id="deck",
        declared_keys=(),
        visible_keys=(),
        sync_keys=(),
        data_keys=(),
        unkeyed_visible=(),
        missing_alt=("s03.chart1",),
        duplicate_keys=("s01.title",),
        charts=(),
    )
    monkeypatch.setattr("autooffice.deck.model.build_coverage_plan", lambda _deck: coverage)

    result = check_deck(deck_path, ("pptx",))

    messages = [finding.message for finding in result.findings if finding.rule == "coverage"]
    assert "objek tanpa alt text: s03.chart1" in messages
    assert "key duplikat: s01.title" in messages


def test_check_deck_without_transcript_skips_parse(deck_path: Path) -> None:
    (deck_path.parent / "transcripts.md").unlink()

    result = check_deck(deck_path, ("pptx",))

    assert result.ok is True
    assert not any(finding.rule == "transcript" for finding in result.findings)


@pytest.mark.parametrize("error_type", [AutoOfficeError, OSError])
def test_check_deck_reports_copy_checker_error(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    def fail_check_copy(*_args: object, **_kwargs: object) -> None:
        raise error_type("diagnostik rusak")

    monkeypatch.setattr("autooffice.deck.copy.check_copy", fail_check_copy)

    result = check_deck(deck_path, ("pptx",))

    finding = next(item for item in result.findings if item.rule == "copy")
    assert "diagnostik rusak" in finding.message
    assert result.ok is False
