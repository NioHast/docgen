"""Tes integrasi build_deck: validasi API dan dry-run tanpa render."""

from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.build import build_deck
from autooffice.deck.layout.spec import LayoutPlan

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "deck" / "minimal.yaml"


def _patch_deck_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "autooffice.deck.layout.overflow.plan_deck",
        lambda _deck, _theme, *, fail_on_overflow=False: LayoutPlan(slides=()),
    )
    monkeypatch.setattr(
        "autooffice.deck.layout.overflow.plan_overflow_keys",
        lambda _plan: (),
    )
    monkeypatch.setattr("autooffice.deck.copy.check_copy", lambda *_args, **_kwargs: ())
    monkeypatch.setattr("autooffice.deck.copy.has_errors", lambda _diagnostics: False)


def test_build_deck_dry_run_does_not_create_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_deck_dependencies(monkeypatch)
    out = tmp_path / "out"
    outcome = build_deck(FIXTURE, ("pptx", "pdf"), out, dry_run=True)
    assert outcome.dry_run is True
    assert outcome.files == (
        out / "minimal.pptx",
        out / "minimal.pdf",
    )
    assert not out.exists()


def test_build_deck_rejects_invalid_target(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="target tidak valid"):
        build_deck(FIXTURE, ("docx",), tmp_path)


def test_build_deck_missing_renderer_reports_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_deck_dependencies(monkeypatch)
    for name in ("create_renderer", "renderer_factory", "render_deck", "PptxRenderer"):
        monkeypatch.setattr(f"autooffice.deck.render.pptx.{name}", None, raising=False)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="renderer PPTX") as error:
        build_deck(FIXTURE, ("pptx",), out)

    assert error.value.code == "CLI-RENDERER"
    assert not list(out.glob("*.pptx"))
