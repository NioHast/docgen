"""Test perilaku checker untuk cabang rule, target, dan formatting diagnostic."""

from collections.abc import Callable, Sequence

import pytest

from autooffice.deck.copy import (
    Diagnostic,
    check_copy,
    has_errors,
    loads_copy_config,
)
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyBinding, KeyManifest, SlideIR
from autooffice.deck.transcript import TranscriptError, TranscriptIR

VALID_TITLE = "Peta Tiga Bagian"

ALL_RULES_DISABLED = """
schema: 1
rules:
  banned_phrases:
    severity: off
  title_case:
    enabled: false
  dash:
    severity: off
  sentence_length:
    enabled: false
  negative_parallelism:
    severity: off
  contrast_pattern:
    enabled: false
  forced_triad:
    severity: off
  one_line_closer:
    enabled: false
  paired_clause_label:
    severity: off
"""


def _text_block(block_id: str, text: object, *, role: str | None = None) -> BlockIR:
    return BlockIR(
        block_id=block_id,
        block_type="text",
        span=None,
        role=role,
        fields={"text": text},
    )


def _code_block(block_id: str) -> BlockIR:
    return BlockIR(block_id=block_id, block_type="code", span=None, role=None, fields={})


def _text_binding(
    key: str,
    block_id: str,
    *,
    plain_text: str = "Teks aman.",
) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id="s01",
        block_id=block_id,
        leaf="text",
        kind="text",  # type: ignore[arg-type]
        sync=True,
        yaml_path=("slides", "s01", block_id, "text"),
        value=plain_text,
        plain_text=plain_text,
    )


def _deck(
    blocks: Sequence[BlockIR] = (),
    bindings: Sequence[KeyBinding] = (),
    *,
    notes: str | None = None,
) -> DeckIR:
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Lokal", "author": "Test", "language": "id"},
        theme_name="indigo",
        slides=(
            SlideIR(
                slide_id="s01",
                layout="custom",
                order=0,
                blocks=tuple(blocks),
                notes=notes,
                source=None,
            ),
        ),
        keys=KeyManifest(bindings=tuple(bindings)),
    )


def test_has_errors_only_flags_error_severity(make_deck: Callable[..., DeckIR]) -> None:
    warning_deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": " ".join(["kata"] * 26) + ".",
            }
        ]
    )
    error_deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE, "notes": "Ini krusial."}])

    warnings = check_copy(warning_deck)
    errors = check_copy(error_deck)

    assert warnings
    assert not has_errors(warnings)
    assert has_errors(errors)


@pytest.mark.parametrize(
    ("title", "valid"),
    [
        ("Untuk Peta", True),
        ("Peta Untuk", True),
        ("Peta untuk Bagian", True),
        ("Peta Untuk Bagian", False),
        ("2026 Roadmap", True),
        ("peta Tiga Bagian", False),
        ("Peta Tiga bagian", False),
    ],
)
def test_title_case_first_last_and_function_word_boundaries(
    make_deck: Callable[..., DeckIR],
    title: str,
    valid: bool,
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": title}])

    diagnostics = check_copy(deck)
    has_violation = "title_case" in {item.rule for item in diagnostics}

    assert has_violation is not valid


def test_sentence_length_uses_configured_boundary(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  sentence_length:
    max_words: 5
"""
    )
    within_limit = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "Satu dua tiga empat lima.",
            }
        ]
    )
    over_limit = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "Satu dua tiga empat lima enam.",
            }
        ]
    )

    assert "sentence_length" not in {item.rule for item in check_copy(within_limit, config=config)}
    diagnostic = next(
        item for item in check_copy(over_limit, config=config) if item.rule == "sentence_length"
    )
    assert diagnostic.severity == "warning"
    assert "6 kata" in diagnostic.message


def test_configured_triad_severity_is_applied(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  forced_triad:
    severity: error
"""
    )
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "Cepat, tepat, dan terpercaya.",
            }
        ]
    )

    diagnostic = next(
        item for item in check_copy(deck, config=config) if item.rule == "forced_triad"
    )

    assert diagnostic.severity == "error"
    assert "triad" in diagnostic.message.lower()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tiga Kelompok Besar, Satu Alur Baca Utama Jelas", True),
        ("Tiga Kelompok Besar, Satu Alur Baca Utama Jelas Kini", False),
    ],
)
def test_paired_clause_respects_word_boundary(
    make_deck: Callable[..., DeckIR],
    text: str,
    expected: bool,
) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "labels",
                        "type": "bullets",
                        "items": (text,),
                    }
                ],
            }
        ]
    )

    diagnostics = check_copy(deck)

    assert ("paired_clause_label" in {item.rule for item in diagnostics}) is expected


def test_one_line_closer_allowlist_suppresses_last_item(
    make_deck: Callable[..., DeckIR],
) -> None:
    config = loads_copy_config(
        """
schema: 1
allow:
  - key: s01.points.item3.text
    rules: [one_line_closer]
    reason: kutipan sumber
"""
    )
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "points",
                        "type": "bullets",
                        "items": (
                            "Satu dua tiga empat lima enam",
                            "Satu dua tiga empat lima enam",
                            "Siap melangkah.",
                        ),
                    }
                ],
            }
        ]
    )

    diagnostics = check_copy(deck, config=config)

    assert all(item.rule != "one_line_closer" for item in diagnostics)


def test_non_text_block_is_not_used_as_title(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "blocks": [
                    {
                        "id": "chart",
                        "type": "chart",
                        "title": VALID_TITLE,
                    }
                ],
            }
        ]
    )

    diagnostics = check_copy(deck)

    assert all(item.rule != "title_case" for item in diagnostics)


def test_slide_without_title_block_has_no_title_entry(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "blocks": [{"id": "body", "type": "text", "text": "Teks aman."}],
            }
        ]
    )

    assert check_copy(deck) == ()


def test_title_block_requires_string_text() -> None:
    deck = _deck(blocks=(_text_block("title", 42, role="title"),))

    assert check_copy(deck) == ()


def test_title_fallback_uses_block_id_title() -> None:
    deck = _deck(
        blocks=(_text_block("title", "Peta tiga bagian"),),
        bindings=(_text_binding("s01.title.text", "title", plain_text="Peta tiga bagian"),),
    )

    diagnostics = check_copy(deck)

    assert any(item.key == "s01.title" and item.rule == "title_case" for item in diagnostics)


def test_bindings_without_usable_text_are_ignored() -> None:
    deck = _deck(
        blocks=(
            _text_block("body", "Teks aman."),
            _code_block("snippet"),
        ),
        bindings=(
            _text_binding("s01.ghost.text", "ghost"),
            _text_binding("s01.body.text", "body", plain_text="   "),
            _text_binding("s01.snippet.text", "snippet", plain_text="print(1)"),
        ),
    )

    assert check_copy(deck) == ()


def test_check_copy_rejects_transcript_missing_slide(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(
        slides=[
            {"id": "s01", "title": VALID_TITLE},
            {"id": "s02", "title": VALID_TITLE},
        ]
    )
    transcript = make_transcript([{"slide_id": "s01", "title": "Pembuka", "id": "Selamat pagi."}])

    with pytest.raises(TranscriptError, match="tidak memuat bagian"):
        check_copy(deck, transcript)


def test_severity_off_suppresses_only_selected_rule(
    make_deck: Callable[..., DeckIR],
) -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  dash:
    severity: off
"""
    )
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "Bagian A\u2014bagian B. Ini krusial.",
            }
        ]
    )

    diagnostics = check_copy(deck, config=config)

    assert all(item.rule != "dash" for item in diagnostics)
    assert any(item.rule == "banned_phrases" for item in diagnostics)


def test_enabled_false_suppresses_only_selected_rule(
    make_deck: Callable[..., DeckIR],
) -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  banned_phrases:
    enabled: false
"""
    )
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE, "notes": "Ini krusial."}])

    assert check_copy(deck, config=config) == ()


def test_all_disabled_rules_produce_no_diagnostics(
    make_deck: Callable[..., DeckIR],
) -> None:
    config = loads_copy_config(ALL_RULES_DISABLED)
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": "peta tiga bagian, bukan hanya satu \u2014 dan dua, dan tiga",
                "notes": "Ini krusial. " + " ".join(["kata"] * 30) + ".",
            }
        ]
    )

    assert check_copy(deck, config=config) == ()


@pytest.mark.parametrize(
    ("file", "line", "location"),
    [
        ("deck.yaml", 3, "deck.yaml:3"),
        ("deck.yaml", None, "deck.yaml"),
        (None, None, "<deck>"),
    ],
)
def test_diagnostic_format_includes_location_and_line(
    file: str | None,
    line: int | None,
    location: str,
) -> None:
    diagnostic = Diagnostic(
        rule="dash",
        severity="error",
        key="s01.notes",
        message="Ada tanda pisah.",
        hint="Hapus tanda pisah.",
        file=file,
        line=line,
    )

    assert diagnostic.format() == (
        f"{location}: error: s01.notes [dash] Ada tanda pisah. Hint: Hapus tanda pisah."
    )
