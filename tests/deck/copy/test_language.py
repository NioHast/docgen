"""Test normalisasi bahasa dan pemilihan rule pack bilingual."""

from collections.abc import Callable

import pytest

from autooffice.deck.copy import CopyConfigError, check_copy, normalize_language
from autooffice.deck.model.deck_ir import DeckIR
from autooffice.deck.transcript import TranscriptIR

VALID_TITLE = "Peta Tiga Bagian"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("id", "id"),
        ("id-ID", "id"),
        ("ID-id", "id"),
        ("en", "en"),
        ("en-US", "en"),
        ("EN-gb", "en"),
    ],
)
def test_normalize_language_primary_subtag(raw: str, expected: str) -> None:
    assert normalize_language(raw) == expected


@pytest.mark.parametrize("raw", ["fr-FR", "de", "", "id_ID", "english"])
def test_normalize_language_rejects_unsupported(raw: str) -> None:
    with pytest.raises(CopyConfigError):
        normalize_language(raw)


def test_deck_language_id_variant_uses_indonesian_pack(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        language="id-ID",
        slides=[{"id": "s01", "title": VALID_TITLE, "notes": "Ini krusial."}],
    )

    diagnostics = check_copy(deck)

    assert any(item.rule == "banned_phrases" for item in diagnostics)


def test_deck_language_en_variant_uses_english_pack(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        language="en-US",
        slides=[{"id": "s01", "title": VALID_TITLE, "notes": "We delve into the data."}],
    )

    diagnostics = check_copy(deck)

    assert any(item.rule == "banned_phrases" for item in diagnostics)


def test_bilingual_transcript_uses_separate_packs(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Pembuka",
                "id": "Ini krusial.",
                "en": "We delve into the data.",
            }
        ]
    )

    diagnostics = check_copy(deck, transcript)

    banned_keys = {item.key for item in diagnostics if item.rule == "banned_phrases"}
    assert banned_keys == {"s01.transcript.id", "s01.transcript.en"}


def test_transcript_language_pack_is_not_cross_applied(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Pembuka",
                "id": "We delve into the data.",
                "en": "Ini krusial.",
            }
        ]
    )

    diagnostics = check_copy(deck, transcript)

    assert all(item.rule != "banned_phrases" for item in diagnostics)


def test_id_transcript_gets_indonesian_only_rules(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Pembuka",
                "id": "Cepat, tepat, dan terpercaya.",
                "en": "Fast, precise, and trusted.",
            }
        ]
    )

    diagnostics = check_copy(deck, transcript)

    assert any(
        item.rule == "forced_triad" and item.key == "s01.transcript.id" for item in diagnostics
    )
    assert all(item.key != "s01.transcript.en" for item in diagnostics)


def test_english_title_still_uses_title_case(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(language="en", slides=[{"id": "s01", "title": "The Road To Results"}])

    diagnostics = check_copy(deck)

    assert any(item.rule == "title_case" for item in diagnostics)


def test_english_notes_skip_title_case(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        language="en",
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "the road to results",
            }
        ],
    )

    diagnostics = check_copy(deck)

    assert all(item.rule != "title_case" for item in diagnostics)
