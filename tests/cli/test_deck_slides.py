"""Tes target Slides memakai fake Google tanpa jaringan."""

from pathlib import Path

import pytest

import autooffice.pdf
from autooffice.cli import CliError
from autooffice.cli.build import build_deck
from autooffice.design import resolve_theme
from autooffice.google import load_state
from autooffice.google.fake import FakeGoogleServices


def _state_file(deck_path: Path) -> Path:
    return deck_path.parent / ".autooffice" / "state" / f"{deck_path.stem}.json"


def _rgb(value: str) -> dict[str, float]:
    return {
        "red": int(value[1:3], 16) / 255,
        "green": int(value[3:5], 16) / 255,
        "blue": int(value[5:7], 16) / 255,
    }


def test_build_slides_push_uploads_preflights_and_syncs_text(
    deck_path: Path,
    tmp_path: Path,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "out"
    outcome = build_deck(deck_path, ("slides",), out, google_services=fake_google)

    state = load_state(_state_file(deck_path))
    assert state.presentation_id is not None
    assert (out / "deck.transcript.md").is_file()
    assert not (out / "deck.slides-upload.pptx").exists()
    assert len(fake_google.drive.uploads) == 1
    assert fake_google.drive.uploads[0].name == "Deck Uji Build"
    assert _state_file(deck_path) in outcome.files

    snapshot = fake_google.slides.get_presentation(state.presentation_id)
    assert sum(1 for element in snapshot.elements() if element.kind == "table") == 1
    assert sum(1 for element in snapshot.elements() if element.kind == "sheets_chart") == 1
    assert not any(
        element.marker == "autooffice:chart:s03.chart1" for element in snapshot.elements()
    )
    assert any(
        element.marker == "s01.title.text" and element.text == "Ringkasan Build"
        for element in snapshot.elements()
    )


def test_build_slides_forwards_theme_to_google_chart_colors(
    deck_path: Path,
    tmp_path: Path,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "out"

    build_deck(
        deck_path,
        ("slides",),
        out,
        theme="hitam",
        google_services=fake_google,
    )

    state = load_state(_state_file(deck_path))
    assert state.spreadsheet_id is not None
    chart_state = state.charts["s03.chart1"]
    chart = fake_google.sheets.get_chart(state.spreadsheet_id, chart_state.sheet_id)
    assert chart is not None
    basic = chart.spec["basicChart"]
    assert isinstance(basic, dict)
    series = basic["series"]
    assert isinstance(series, list)
    assert series[0]["color"] == _rgb(resolve_theme("hitam").chart.series[0])


def test_build_slides_does_not_embed_ppt_fonts(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "out"
    calls: list[Path] = []

    def fake_embed(path: Path) -> Path:
        calls.append(Path(path))
        return Path(path)

    monkeypatch.setattr(autooffice.pdf, "embed_pptx_fonts", fake_embed)
    build_deck(deck_path, ("slides",), out, google_services=fake_google)

    assert calls == []


def test_build_slides_keep_intermediate_keeps_staging(
    deck_path: Path,
    tmp_path: Path,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "out"
    outcome = build_deck(
        deck_path,
        ("slides",),
        out,
        keep_intermediate=True,
        google_services=fake_google,
    )

    staging = out / "deck.slides-upload.pptx"
    assert staging.is_file()
    assert staging in outcome.files


def test_build_slides_sync_modes_write_review_without_changing_source(
    deck_path: Path,
    tmp_path: Path,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "push-out"
    build_deck(deck_path, ("slides",), out, google_services=fake_google)
    original = deck_path.read_bytes()
    review_dir = deck_path.parent / ".autooffice" / "review"
    state = _state_file(deck_path)

    expectations = {
        "diff": review_dir / "deck.diff.json",
        "pull": review_dir / "deck.pulled.yaml",
        "apply": review_dir / "deck.applied.yaml",
    }
    for mode, expected in expectations.items():
        sync_out = tmp_path / f"sync-{mode}"
        outcome = build_deck(
            deck_path,
            ("slides",),
            sync_out,
            sync=mode,
            google_services=fake_google,
        )
        assert expected.is_file()
        assert outcome.files == (expected, state)
        assert not sync_out.exists()
        assert not (sync_out / "deck.transcript.md").exists()
        assert deck_path.read_bytes() == original


def test_build_slides_sync_modes_preserve_existing_build_directory(
    deck_path: Path,
    tmp_path: Path,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "push-out"
    build_deck(deck_path, ("slides",), out, google_services=fake_google)
    build_dir = deck_path.parent / ".autooffice-build" / deck_path.stem
    sentinel = build_dir / "sentinel.txt"
    build_dir.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("pertahankan", encoding="utf-8")

    for mode in ("diff", "pull", "apply"):
        build_deck(
            deck_path,
            ("slides",),
            tmp_path / f"sync-{mode}",
            sync=mode,
            google_services=fake_google,
        )

        assert sentinel.read_text(encoding="utf-8") == "pertahankan"
        assert build_dir.is_dir()


def test_build_slides_sync_dry_run_plan_has_no_final_artifacts(
    deck_path: Path,
    tmp_path: Path,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "push-out"
    build_deck(deck_path, ("slides",), out, google_services=fake_google)
    review = deck_path.parent / ".autooffice" / "review" / "deck.diff.json"

    outcome = build_deck(
        deck_path,
        ("slides",),
        tmp_path / "sync-out",
        sync="diff",
        dry_run=True,
        google_services=fake_google,
    )

    assert outcome.files == (review, _state_file(deck_path))
    assert not (tmp_path / "sync-out").exists()


def test_build_slides_sync_requires_state(
    deck_path: Path,
    tmp_path: Path,
    fake_google: FakeGoogleServices,
) -> None:
    out = tmp_path / "out"
    with pytest.raises(CliError, match=r"state|presentation_id") as error:
        build_deck(
            deck_path,
            ("slides",),
            out,
            sync="diff",
            google_services=fake_google,
        )

    assert error.value.exit_code == 1
    assert not out.exists()
    assert not (deck_path.parent / ".autooffice" / "review").exists()


def test_build_slides_dry_run_requires_google_credentials(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("AUTOOFFICE_GOOGLE_TOKEN", str(tmp_path / "missing-token.json"))
    out = tmp_path / "out"

    with pytest.raises(CliError, match="kredensial Google") as error:
        build_deck(deck_path, ("slides",), out, dry_run=True)

    assert error.value.code == "CLI-GOOGLE-CREDENTIALS"
    assert error.value.exit_code == 1
    assert not out.exists()
