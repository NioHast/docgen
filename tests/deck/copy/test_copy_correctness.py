"""Test regresi correctness copy checker dan transcript parser."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from autooffice.cli.check import check_deck
from autooffice.deck.copy import (
    CopyConfigError,
    Diagnostic,
    check_banned_phrases,
    check_copy,
    check_sentence_length,
    check_title_case,
    load_copy_config,
    loads_copy_config,
    paired_clause_fragments,
)
from autooffice.deck.copy.prose import render_visible_text
from autooffice.deck.model.deck_ir import (
    DeckIR,
    KeyBinding,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.transcript import TranscriptError, TranscriptIR, parse_transcript

VALID_TITLE = "Peta Tiga Bagian"


def _rules(diagnostics: Sequence[Diagnostic]) -> set[str]:
    return {diagnostic.rule for diagnostic in diagnostics}


def _deck_with_source(make_deck: Callable[..., DeckIR], source_text: str) -> DeckIR:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    slide = deck.slides[0]
    slide_with_source = SlideIR(
        slide_id=slide.slide_id,
        layout=slide.layout,
        order=slide.order,
        blocks=slide.blocks,
        notes=slide.notes,
        source={"text": source_text},
    )
    source_binding = KeyBinding(
        key="s01.source.text",
        slide_id="s01",
        block_id=None,
        leaf="source.text",
        kind="source",
        sync=True,
        yaml_path=("slides", 0, "source", "text"),
        value=source_text,
        plain_text=source_text,
    )
    return DeckIR(
        schema=deck.schema,
        meta=deck.meta,
        theme_name=deck.theme_name,
        slides=(slide_with_source,),
        keys=KeyManifest(bindings=(*deck.keys.bindings, source_binding)),
    )


def _write_copy_config(path: Path) -> None:
    path.write_text(
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


def test_markdown_link_in_title_is_checked_as_visible_label(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": "Peta [untuk](https://example.com) Tim",
            }
        ]
    )

    assert "title_case" not in _rules(check_copy(deck))


def test_render_visible_text_maps_offsets_to_source() -> None:
    source = "Peta [untuk](https://example.com) **Tim**"

    visible = render_visible_text(source)

    assert visible.text == "Peta untuk Tim"
    assert visible.original_offset(0) == 0
    assert visible.original_offset(5) == 6
    assert visible.original_offset(len(visible.text)) == visible.offsets[-1] + 1
    assert visible.original_offset(999) == 999


def test_markdown_emphasis_and_code_markers_are_stripped_from_title(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": "Peta **untuk** `Tim`"}])

    assert "title_case" not in _rules(check_copy(deck))


def test_markdown_link_label_is_still_linted(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "Lihat [krusial](https://example.com) sekarang.",
            }
        ]
    )

    diagnostics = check_copy(deck)

    assert "banned_phrases" in _rules(diagnostics)


def test_urls_and_autolinks_are_not_linted_in_prose(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": ("Lihat <https://example.com/krusial> dan https://example.com/krusial."),
            }
        ]
    )

    assert "banned_phrases" not in _rules(check_copy(deck))


def test_inline_link_target_keeps_balanced_parentheses() -> None:
    source = "[lihat](https://en.wikipedia.org/wiki/Foo_(bar)/krusial)"

    assert render_visible_text(source).text == "lihat"


def test_balanced_parentheses_link_target_is_not_linted_in_prose(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "[lihat](https://en.wikipedia.org/wiki/Foo_(bar)/krusial)",
            }
        ]
    )

    assert "banned_phrases" not in _rules(check_copy(deck))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('Lihat "https://example.com/krusial". Selesai.', 'Lihat "". Selesai.'),
        ('Lihat "https://example.com/data." Selesai.', 'Lihat "." Selesai.'),
        ("https://example.com/krusial**krusial**", "krusial"),
        ("https://example.com/krusial*krusial*", "krusial"),
        ("https://example.com/krusial_krusial_", "krusial"),
        ("https://example.com/krusial`krusial`", "krusial"),
        ("https://example.com/krusial~~krusial~~", "krusial"),
        ("https://example.com/krusial]krusial", "]krusial"),
        ("https://example.com/krusial}krusial", "}krusial"),
    ],
)
def test_bare_url_stops_at_quotes_and_markdown_markers(
    source: str,
    expected: str,
) -> None:
    assert render_visible_text(source).text == expected


def test_bare_url_does_not_swallow_closing_quote_before_sentence_boundary() -> None:
    visible = render_visible_text('Lihat "https://example.com/krusial". Selesai.')

    assert visible.text == 'Lihat "". Selesai.'
    assert visible.offsets[-1] == len('Lihat "https://example.com/krusial". Selesai.') - 1


def test_urls_in_transcript_are_not_linted(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Pembuka",
                "id": "Kunjungi https://example.com/krusial untuk detail.",
                "en": "Visit https://example.com/robust for details.",
            }
        ]
    )

    assert "banned_phrases" not in _rules(check_copy(deck, transcript))


def test_transcript_line_mapping_survives_markdown_stripping(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Pembuka",
                "id": "Baris aman.\nLihat https://example.com/krusial lalu ini krusial.",
                "line": 7,
            }
        ]
    )

    diagnostics = check_copy(deck, transcript)
    diagnostic = next(item for item in diagnostics if item.key == "s01.transcript.id")

    assert diagnostic.line == 8


def test_list_marker_is_not_counted_by_sentence_length(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript(
        [
            {
                "slide_id": "s01",
                "title": "Pembuka",
                "id": "- " + " ".join(["kata"] * 25) + ".",
            }
        ]
    )

    diagnostics = check_copy(deck, transcript)

    assert "sentence_length" not in _rules(diagnostics)


@pytest.mark.parametrize("marker", ["- ", "* ", "1. "])
def test_sentence_length_ignores_list_markers_directly(marker: str) -> None:
    assert check_sentence_length(marker + " ".join(["kata"] * 25) + ".") == ()


def test_sentence_length_splits_after_closing_quote() -> None:
    text = "\u201c" + " ".join(["kata"] * 25) + ".\u201d " + "Pendek."

    assert check_sentence_length(text) == ()


def test_duplicate_bindings_produce_one_diagnostic_per_rule_key_span(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [{"id": "body", "type": "text", "text": "Ini krusial."}],
            }
        ]
    )
    duplicated = DeckIR(
        schema=deck.schema,
        meta=deck.meta,
        theme_name=deck.theme_name,
        slides=deck.slides,
        keys=KeyManifest(bindings=(*deck.keys.bindings, deck.keys.bindings[-1])),
    )

    diagnostics = check_copy(duplicated)
    banned = [item for item in diagnostics if item.rule == "banned_phrases"]

    assert len(banned) == 1


def test_duplicate_bindings_do_not_create_false_one_line_closer(
    make_deck: Callable[..., DeckIR],
) -> None:
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
                            "Siap melangkah.",
                        ),
                    }
                ],
            }
        ]
    )
    duplicated = DeckIR(
        schema=deck.schema,
        meta=deck.meta,
        theme_name=deck.theme_name,
        slides=deck.slides,
        keys=KeyManifest(bindings=(*deck.keys.bindings, deck.keys.bindings[-1])),
    )

    diagnostics = check_copy(duplicated)

    assert all(item.rule != "one_line_closer" for item in diagnostics)


def test_title_case_reports_repeated_tokens_at_their_own_offsets() -> None:
    findings = [
        (violation.message, violation.offset) for violation in check_title_case("peta peta")
    ]

    assert findings == [
        ("Kata 'peta' pada judul harus diawali huruf kapital.", 0),
        ("Kata 'peta' pada judul harus diawali huruf kapital.", 5),
    ]


def test_title_case_rejects_blank_title() -> None:
    violations = check_title_case("   ")

    assert len(violations) == 1
    assert violations[0].message == "Judul slide tidak boleh kosong."


def test_title_case_boundaries_ignore_punctuation_only_tokens() -> None:
    assert check_title_case("Peta Untuk ...") == ()
    assert check_title_case("... Untuk Peta") == ()
    findings = [
        (violation.message, violation.offset) for violation in check_title_case("... untuk Peta")
    ]
    assert findings == [("Kata 'untuk' pada judul harus diawali huruf kapital.", 4)]


def test_title_case_reports_punctuation_only_title_as_empty() -> None:
    violations = check_title_case("---")

    assert len(violations) == 1
    assert violations[0].message == "Judul slide tidak boleh kosong."


@pytest.mark.parametrize(
    "text",
    [
        "It\u2019s worth noting.",
        "In today\u2019s report.",
        "We delved into it.",
        "It leverages data.",
        "It enhances flow.",
    ],
)
def test_banned_phrases_accept_curly_apostrophes_and_inflections(text: str) -> None:
    assert check_banned_phrases(text, language="en")


def test_copy_path_with_parent_segments_inside_deck_is_allowed(
    make_deck: Callable[..., DeckIR],
    tmp_path: Path,
) -> None:
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    _write_copy_config(deck_dir / "copy.yaml")
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "notes": "Ini frasa khusus.",
            }
        ]
    )
    source = tmp_path / "nested" / ".." / "deck" / "deck.yaml"
    copy_path = tmp_path / "nested" / ".." / "deck" / "copy.yaml"

    diagnostics = check_copy(deck, copy_path=copy_path, deck_file=source)

    assert any(item.rule == "banned_phrases" for item in diagnostics)


def test_load_copy_config_allows_parent_segments_inside_deck(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    _write_copy_config(deck_dir / "copy.yaml")

    config = load_copy_config(
        tmp_path / "nested" / ".." / "deck" / "copy.yaml",
        deck_dir=tmp_path / "nested" / ".." / "deck",
    )

    assert config.rule("banned_phrases").extra_for("id") == ("frasa khusus",)


def test_load_copy_config_resolves_parent_segments_without_deck_context(
    tmp_path: Path,
) -> None:
    _write_copy_config(tmp_path / "copy.yaml")

    config = load_copy_config(tmp_path / "nested" / ".." / "copy.yaml")

    assert config.rule("banned_phrases").extra_for("id") == ("frasa khusus",)


def test_absolute_copy_path_outside_deck_is_rejected(
    make_deck: Callable[..., DeckIR],
    tmp_path: Path,
) -> None:
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    outside = tmp_path / "copy.yaml"
    _write_copy_config(outside)
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])

    with pytest.raises(CopyConfigError, match="folder deck"):
        check_copy(deck, copy_path=outside, deck_file=deck_dir / "deck.yaml")


def test_relative_copy_path_escaping_deck_is_rejected(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    outside = tmp_path / "copy.yaml"
    _write_copy_config(outside)

    with pytest.raises(CopyConfigError, match="folder deck"):
        load_copy_config(
            deck_dir / ".." / "copy.yaml",
            deck_dir=deck_dir,
        )


def test_cli_check_resolves_sibling_copy_yaml_with_parent_segments(
    tmp_path: Path,
) -> None:
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "deck" / "minimal.yaml"
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    deck_text = fixture.read_text(encoding="utf-8").replace(
        "Catatan pembicara untuk slide pertama.",
        "Catatan pembicara untuk slide pertama. Ini frasa khusus.",
    )
    (deck_dir / "deck.yaml").write_text(deck_text, encoding="utf-8", newline="\n")
    _write_copy_config(deck_dir / "copy.yaml")
    source = tmp_path / "nested" / ".." / "deck" / "deck.yaml"

    result = check_deck(source, ("pptx",))

    assert any(
        finding.rule == "banned_phrases" and finding.key == "s01.notes"
        for finding in result.findings
    )
    assert all(finding.rule != "copy" for finding in result.findings)


def test_targets_transcript_false_skips_mapping_validation(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    config = loads_copy_config("schema: 1\ntargets:\n  transcript: false\n")
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript([{"slide_id": "s99", "title": "Lain", "id": "Ini krusial."}])

    assert check_copy(deck, transcript, config=config) == ()


def test_transcript_allow_entry_is_inert_without_transcript(
    make_deck: Callable[..., DeckIR],
) -> None:
    config = loads_copy_config(
        """
schema: 1
allow:
  - key: s01.transcript.id
    rules: [banned_phrases]
    reason: transkrip belum tersedia
"""
    )
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])

    assert check_copy(deck, config=config) == ()


def test_transcript_allow_entry_is_inert_when_target_disabled(
    make_deck: Callable[..., DeckIR],
    make_transcript: Callable[..., TranscriptIR],
) -> None:
    config = loads_copy_config(
        """
schema: 1
targets:
  transcript: false
allow:
  - key: s01.transcript.en
    rules: [banned_phrases]
    reason: target transkrip dimatikan
"""
    )
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])
    transcript = make_transcript([{"slide_id": "s99", "title": "Lain", "id": "Ini krusial."}])

    assert check_copy(deck, transcript, config=config) == ()


def test_source_text_is_checked_as_prose(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = _deck_with_source(make_deck, "Sumber: ini krusial")

    diagnostics = check_copy(deck)

    assert any(
        item.key == "s01.source.text" and item.rule == "banned_phrases" for item in diagnostics
    )


def test_source_text_is_not_treated_as_title(make_deck: Callable[..., DeckIR]) -> None:
    deck = _deck_with_source(make_deck, "peta tiga bagian")

    diagnostics = check_copy(deck)

    assert all(item.rule != "title_case" for item in diagnostics)


@pytest.mark.parametrize(
    "title",
    [
        "\u6771\u4eac\u306e\u5730\u56f3",
        "\u062e\u0631\u064a\u0637\u0629 \u0627\u0644\u0645\u0634\u0631\u0648\u0639",
        "\u05de\u05e4\u05ea \u05d4\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8",
        "\u0e41\u0e1c\u0e19\u0e17\u0e35\u0e48\u0e42\u0e04\u0e23\u0e07\u0e01\u0e32\u0e23",
    ],
)
def test_title_case_allows_scripts_without_letter_case(title: str) -> None:
    assert check_title_case(title) == ()


def test_paired_clause_fragments_rejects_trailing_newline_and_spaces() -> None:
    assert paired_clause_fragments("Tiga Kelompok, Satu Alur Baca\n   ") is None


@pytest.mark.parametrize("text", ["", "   \n", "# hanya komentar\n", "---\n"])
def test_empty_or_comment_only_copy_yaml_is_rejected(text: str) -> None:
    with pytest.raises(CopyConfigError, match="tidak boleh kosong"):
        loads_copy_config(text)


def test_empty_transcript_prose_reports_section_heading_line() -> None:
    text = "\n".join(
        [
            "## s05. Pembuka",
            "",
            "### Indonesia",
            "",
            "   ",
            "",
        ]
    )

    with pytest.raises(TranscriptError) as captured:
        parse_transcript(text, slide_ids=("s05",))

    assert captured.value.line == 1
    assert "baris 1" in str(captured.value)
