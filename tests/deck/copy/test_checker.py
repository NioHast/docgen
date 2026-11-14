"""Test diagnostic, target, allowlist, dan perilaku offline copy checker."""

from collections.abc import Callable
from pathlib import Path

import pytest

from autooffice.deck.copy import (
    CopyConfigError,
    check_copy,
    loads_copy_config,
)
from autooffice.deck.model.deck_ir import DeckIR
from autooffice.deck.transcript import TranscriptError, TranscriptIR

VALID_TITLE = "Peta Tiga Bagian"


def test_diagnostic_contains_required_fields(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE, "notes": "Ini krusial."}])

    diagnostics = check_copy(deck, deck_file="deck.yaml")
    diagnostic = next(item for item in diagnostics if item.rule == "banned_phrases")

    assert diagnostic.severity == "error"
    assert diagnostic.key == "s01.notes"
    assert diagnostic.file == "deck.yaml"
    assert diagnostic.line is None
    assert diagnostic.message
    assert diagnostic.hint
    assert set(diagnostic.to_dict()) == {
        "rule",
        "severity",
        "key",
        "file",
        "line",
        "message",
        "hint",
    }


def test_error_and_warning_have_different_severity(make_deck: Callable[..., DeckIR]) -> None:
    notes = "Ini krusial. " + " ".join(["kata"] * 26) + "."
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE, "notes": notes}])

    diagnostics = check_copy(deck)

    assert {item.severity for item in diagnostics} == {"error", "warning"}


def test_targets_disable_notes(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config("schema: 1\ntargets:\n  notes: false\n")
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE, "notes": "Ini krusial."}])

    assert check_copy(deck, config=config) == ()


def test_targets_disable_slides(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config("schema: 1\ntargets:\n  slides: false\n")
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": "Peta tiga bagian",
                "notes": "Ini krusial.",
                "blocks": [{"id": "body", "type": "text", "text": "Ini krusial."}],
            }
        ]
    )

    diagnostics = check_copy(deck, config=config)

    assert {item.key for item in diagnostics} == {"s01.notes"}


def test_targets_disable_transcript(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    config = loads_copy_config("schema: 1\ntargets:\n  transcript: false\n")
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript([{"slide_id": "s01", "title": "Pembuka", "id": "Ini krusial."}])

    assert check_copy(deck, transcript, config=config) == ()


def test_transcript_is_checked_by_default(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript([{"slide_id": "s01", "title": "Pembuka", "id": "Ini krusial."}])

    diagnostics = check_copy(deck, transcript)

    assert any(item.key == "s01.transcript.id" for item in diagnostics)


def test_transcript_diagnostic_uses_file_and_line(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Pembuka",
                "id": "Baris aman.\nIni krusial.",
                "line": 7,
            }
        ]
    )

    diagnostics = check_copy(deck, transcript)
    diagnostic = next(item for item in diagnostics if item.key == "s01.transcript.id")

    assert diagnostic.file == "transcripts.md"
    assert diagnostic.line == 8


def test_english_transcript_uses_english_pack(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(language="en", slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Opening",
                "id": "Selamat pagi.",
                "en": "We delve into the data.",
            }
        ]
    )

    diagnostics = check_copy(deck, transcript)

    assert any(
        item.key == "s01.transcript.en" and item.rule == "banned_phrases" for item in diagnostics
    )


def test_allowlist_suppresses_matching_diagnostic(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
allow:
  - key: s01.notes
    rules: [banned_phrases]
    reason: kutipan sumber
"""
    )
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE, "notes": "Ini krusial."}])

    assert check_copy(deck, config=config) == ()


def test_allowlist_does_not_suppress_other_key(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
allow:
  - key: s02.notes
    rules: [banned_phrases]
    reason: kutipan sumber
"""
    )
    deck = make_deck(
        slides=[
            {"id": "s01", "title": VALID_TITLE, "notes": "Ini krusial."},
            {"id": "s02", "title": VALID_TITLE, "notes": "Aman."},
        ]
    )

    diagnostics = check_copy(deck, config=config)

    assert any(item.key == "s01.notes" for item in diagnostics)


def test_allowlist_unknown_key_is_rejected(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
allow:
  - key: s99.notes
    rules: [banned_phrases]
    reason: kutipan sumber
"""
    )
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])

    with pytest.raises(CopyConfigError, match="tidak ditemukan"):
        check_copy(deck, config=config)


def test_allowlist_accepts_title_block_key_alias(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
allow:
  - key: s01.title.text
    rules: [title_case]
    reason: nama produk
"""
    )
    deck = make_deck(slides=[{"id": "s01", "title": "Peta tiga bagian"}])

    diagnostics = check_copy(deck, config=config)

    assert all(item.rule != "title_case" for item in diagnostics)


def test_copy_path_loads_config(
    make_deck: Callable[..., DeckIR],
    tmp_path: Path,
) -> None:
    copy_path = tmp_path / "copy.yaml"
    copy_path.write_text(
        """
schema: 1
rules:
  banned_phrases:
    extra:
      id: ["frasa khusus"]
""",
        encoding="utf-8",
        newline="\n",
    )
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "Ini frasa khusus.",
            }
        ]
    )

    diagnostics = check_copy(deck, copy_path=copy_path)

    assert any(item.rule == "banned_phrases" for item in diagnostics)


def test_missing_copy_path_raises(make_deck: Callable[..., DeckIR], tmp_path: Path) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])

    with pytest.raises(CopyConfigError, match="tidak ditemukan"):
        check_copy(deck, copy_path=tmp_path / "copy.yaml")


def test_copy_path_and_config_conflict(
    make_deck: Callable[..., DeckIR],
    tmp_path: Path,
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])

    with pytest.raises(CopyConfigError, match="bersamaan"):
        check_copy(deck, copy_path=tmp_path / "copy.yaml", config=loads_copy_config("schema: 1\n"))


def test_transcript_mapping_mismatch_is_rejected(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript([{"slide_id": "s02", "title": "Lain", "id": "Selamat pagi."}])

    with pytest.raises(TranscriptError, match="tidak dikenal"):
        check_copy(deck, transcript)


def test_transcript_optional_when_target_enabled(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])

    assert check_copy(deck, None) == ()


def test_checker_is_deterministic(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": "Peta tiga bagian",
                "notes": "Ini krusial.",
                "blocks": [
                    {
                        "id": "labels",
                        "type": "bullets",
                        "items": ("Tiga Kelompok, Satu Alur Baca",),
                    }
                ],
            }
        ]
    )

    first = check_copy(deck)
    second = check_copy(deck)

    assert first == second
    assert first


def test_checker_does_not_open_network_sockets(
    make_deck: Callable[..., DeckIR],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("copy checker tidak boleh membuka socket")

    monkeypatch.setattr("socket.socket", forbidden)
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE, "notes": "Teks aman."}])

    assert check_copy(deck) == ()
