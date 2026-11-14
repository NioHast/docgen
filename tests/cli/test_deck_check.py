"""Tes check deck YAML: aset, transkrip, coverage, warning, dan exit code."""

from pathlib import Path

import pytest

from autooffice.cli.check import check_deck
from autooffice.cli.main import main
from autooffice.deck.copy.diagnostics import Diagnostic
from autooffice.deck.model import CoveragePlan


def test_check_deck_all_types_is_clean_and_reports_coverage(
    all_types_deck_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = check_deck(all_types_deck_path, ("pptx", "pdf", "slides"))

    assert result.ok is True
    assert result.error_count == 0
    assert any(note.startswith("coverage:") for note in result.notes)
    assert main(["check", str(all_types_deck_path)]) == 0
    captured = capsys.readouterr()
    assert "bersih" in captured.out
    assert "coverage:" in captured.err


def test_check_deck_missing_image_names_slide_block_and_paths(
    missing_asset_deck_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = check_deck(missing_asset_deck_path, ("pptx",))
    findings = [finding for finding in result.findings if finding.rule == "asset"]

    assert len(findings) == 1
    assert findings[0].key == "s04.image1"
    assert "slide 's04'" in findings[0].message
    assert "block 'image1'" in findings[0].message
    assert "assets/missing.png" in findings[0].message
    assert str(missing_asset_deck_path.parent / "assets" / "missing.png") in findings[0].message
    assert main(["check", str(missing_asset_deck_path)]) == 1
    assert "[ERROR]" in capsys.readouterr().err


def test_check_deck_missing_diagram_is_reported_as_asset_error(
    missing_diagram_deck_path: Path,
) -> None:
    result = check_deck(missing_diagram_deck_path, ("pptx",))
    findings = [finding for finding in result.findings if finding.rule == "asset"]

    assert len(findings) == 1
    assert findings[0].key == "s05.diagram1"
    assert "diagrams/missing.mmd" in findings[0].message


def test_check_deck_incomplete_transcript_is_an_error(
    incomplete_transcript_deck_path: Path,
) -> None:
    result = check_deck(incomplete_transcript_deck_path, ("pptx",))
    findings = [finding for finding in result.findings if finding.rule == "transcript"]

    assert len(findings) == 1
    assert "s02" in findings[0].message
    assert result.error_count >= 1


def test_check_deck_reports_coverage_error(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_coverage(_deck: object) -> CoveragePlan:
        return CoveragePlan(
            deck_id="deck",
            declared_keys=(),
            visible_keys=(),
            sync_keys=(),
            data_keys=(),
            unkeyed_visible=("s01.points",),
            missing_alt=(),
            duplicate_keys=(),
            charts=(),
        )

    monkeypatch.setattr("autooffice.deck.model.build_coverage_plan", fake_coverage)
    result = check_deck(deck_path, ("pptx",))

    assert result.ok is False
    assert any(
        finding.rule == "coverage" and finding.key == "s01.points" for finding in result.findings
    )


def test_check_deck_warning_only_exits_zero(
    deck_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_check_copy(*_args: object, **_kwargs: object) -> tuple[Diagnostic, ...]:
        return (
            Diagnostic(
                rule="sentence_length",
                severity="warning",
                key="s01.title.text",
                message="Kalimat melewati batas kata.",
                hint="Pendekkan kalimat.",
            ),
        )

    monkeypatch.setattr("autooffice.deck.copy.check_copy", fake_check_copy)
    assert main(["check", str(deck_path)]) == 0
    captured = capsys.readouterr()

    assert "[PERINGATAN]" in captured.err
    assert "bersih" in captured.out
