"""Tes cabang check deck: theme, layout, transcript, copy, dan coverage."""

from pathlib import Path

import pytest

from autooffice.cli import CliError, require_module
from autooffice.cli.check import Finding, check_deck
from autooffice.deck.layout.spec import LayoutError
from autooffice.deck.model import CoveragePlan
from autooffice.design import DesignTokenError
from autooffice.errors import AutoOfficeError


def _failing_require(
    monkeypatch: pytest.MonkeyPatch,
    *,
    names: tuple[str, ...] = (),
    prefixes: tuple[str, ...] = (),
) -> None:
    def fake_require(name: str, lane: str) -> object:
        if name in names or any(name.startswith(prefix) for prefix in prefixes):
            raise CliError(
                f"modul '{name}' untuk lane {lane} belum tersedia",
                code=f"CLI-LANE-{lane}",
                exit_code=1,
            )
        return require_module(name, lane)

    monkeypatch.setattr("autooffice.cli.check.require_module", fake_require)


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


def test_check_deck_reports_missing_design_lane_as_theme_finding(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _failing_require(monkeypatch, names=("autooffice.design",))

    result = check_deck(deck_path, ("pptx",))

    theme_findings = [finding for finding in result.findings if finding.rule == "theme"]
    assert len(theme_findings) == 1
    assert "F1-DESIGN" in theme_findings[0].message
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


def test_check_deck_notes_missing_layout_lane(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _failing_require(monkeypatch, prefixes=("autooffice.deck.layout",))

    result = check_deck(deck_path, ("pptx",))

    layout_finding = next(item for item in result.findings if item.rule == "layout")
    assert "F1-LAYOUT" in layout_finding.message
    assert any("F1-LAYOUT" in note for note in result.notes)


def test_check_deck_reports_layout_failure(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_plan(_deck: object, _theme: object, *, fail_on_overflow: bool = False) -> object:
        raise LayoutError("grid tidak muat")

    monkeypatch.setattr("autooffice.deck.layout.overflow.plan_deck", fail_plan)

    result = check_deck(deck_path, ("pptx",))

    finding = next(item for item in result.findings if item.rule == "layout")
    assert "layout gagal (lane F1-LAYOUT)" in finding.message
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


def test_check_deck_notes_missing_transcript_lane(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _failing_require(monkeypatch, names=("autooffice.deck.transcript",))

    result = check_deck(deck_path, ("pptx",))

    assert any("transcript validation dilewati" in note for note in result.notes)
    assert not any(finding.rule == "transcript" for finding in result.findings)


def test_check_deck_notes_missing_copy_lane(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _failing_require(monkeypatch, names=("autooffice.deck.copy",))

    result = check_deck(deck_path, ("pptx",))

    assert any("copy checker dilewati" in note for note in result.notes)
    assert result.ok is True


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
