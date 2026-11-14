"""Test state JSON atomik, lokasi, dan larangan token OAuth."""

import json
from pathlib import Path

import pytest

from autooffice.google import GoogleStateError
from autooffice.google.state import (
    STATE_SCHEMA,
    ChartState,
    GoogleState,
    deck_sha256,
    load_state,
    save_state,
    state_path,
)

_DIGEST = "a" * 64
_CHART = ChartState(
    tab_name="s02.chart1",
    sheet_id=11,
    embedded_chart_id=22,
    last_data_sha256="b" * 64,
)


def _state(deck: Path) -> GoogleState:
    return GoogleState(
        deck_path=deck.name,
        deck_sha256=deck_sha256(deck),
        presentation_id="presentation-1",
        presentation_url="https://docs.google.com/presentation/d/presentation-1/edit",
        spreadsheet_id="spreadsheet-1",
        spreadsheet_url="https://docs.google.com/spreadsheets/d/spreadsheet-1/edit",
        charts={"s02.chart1": _CHART},
    )


def test_state_path_is_next_to_yaml(tmp_path: Path) -> None:
    deck = tmp_path / "deck.yaml"
    deck.write_text("schema: 1\n", encoding="utf-8")

    assert state_path(deck) == tmp_path / ".autooffice" / "state" / "deck.json"


def test_state_roundtrip_has_no_oauth_token(tmp_path: Path) -> None:
    deck = tmp_path / "deck.yaml"
    deck.write_text("schema: 1\n", encoding="utf-8")
    state_file = state_path(deck)

    save_state(_state(deck), state_file)
    loaded = load_state(state_file)
    payload = json.loads(state_file.read_text(encoding="utf-8"))

    assert loaded.schema == STATE_SCHEMA
    assert loaded.charts["s02.chart1"] == _CHART
    assert "token" not in payload
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_state_roundtrip_accepts_chart_id_with_token_words(tmp_path: Path) -> None:
    deck = tmp_path / "deck.yaml"
    deck.write_text("schema: 1\n", encoding="utf-8")
    state_file = state_path(deck)
    chart = ChartState(
        tab_name="s02.token_usage",
        sheet_id=0,
        embedded_chart_id=23,
        last_data_sha256="c" * 64,
    )
    state = GoogleState(
        deck_path=deck.name,
        deck_sha256=_DIGEST,
        charts={
            "s02.token_usage": chart,
            "s03.client_id": chart,
        },
    )

    save_state(state, state_file)
    loaded = load_state(state_file)

    assert loaded.charts["s02.token_usage"] == chart
    assert loaded.charts["s03.client_id"] == chart


def test_state_allows_default_sheet_id_zero(tmp_path: Path) -> None:
    deck = tmp_path / "deck.yaml"
    deck.write_text("schema: 1\n", encoding="utf-8")
    state = GoogleState(
        deck_path=deck.name,
        deck_sha256=_DIGEST,
        charts={
            "s02.chart1": ChartState(
                tab_name="s02.chart1",
                sheet_id=0,
                embedded_chart_id=22,
                last_data_sha256="b" * 64,
            )
        },
    )
    state_file = state_path(deck)

    save_state(state, state_file)

    assert load_state(state_file).charts["s02.chart1"].sheet_id == 0


def test_state_rejects_secret_fields(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "schema": STATE_SCHEMA,
                "deck_path": "deck.yaml",
                "deck_sha256": _DIGEST,
                "access_token": "secret",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(GoogleStateError, match="rahasia/OAuth"):
        load_state(state_file)


def test_state_write_is_atomic_and_keeps_old_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck = tmp_path / "deck.yaml"
    deck.write_text("schema: 1\n", encoding="utf-8")
    state_file = state_path(deck)
    old = _state(deck)
    save_state(old, state_file)
    old_bytes = state_file.read_bytes()

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr("autooffice.google.state.os.replace", fail_replace)
    new = GoogleState(
        deck_path=deck.name,
        deck_sha256=_DIGEST,
        presentation_id="presentation-2",
    )

    with pytest.raises(GoogleStateError, match="tidak dapat ditulis"):
        save_state(new, state_file)

    assert state_file.read_bytes() == old_bytes
    assert not list(state_file.parent.glob("*.tmp"))


def test_autooffice_directory_is_gitignored() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    lines = {
        line.strip()
        for line in (repository_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    }

    assert ".autooffice/" in lines
