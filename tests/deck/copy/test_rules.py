"""Test positif dan negatif untuk seluruh rule copy checker."""

from collections.abc import Callable, Sequence

import pytest

from autooffice.deck.copy import (
    Diagnostic,
    check_copy,
    check_forced_triad,
    check_title_case,
    loads_copy_config,
    paired_clause_fragments,
    parse_closer_key,
)
from autooffice.deck.model.deck_ir import DeckIR

VALID_TITLE = "Peta Tiga Bagian"
VALID_TITLE_EN = "The Road to Results"


def rules(diagnostics: Sequence[Diagnostic]) -> set[str]:
    return {diagnostic.rule for diagnostic in diagnostics}


def rules_for(diagnostics: Sequence[Diagnostic], key: str) -> set[str]:
    return {diagnostic.rule for diagnostic in diagnostics if diagnostic.key == key}


def deck_with_notes(
    make_deck: Callable[..., DeckIR],
    notes: str,
    *,
    language: str = "id",
) -> DeckIR:
    return make_deck(
        language=language,
        slides=[{"id": "s01", "title": VALID_TITLE, "notes": notes}],
    )


def test_title_case_accepts_valid_title(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": VALID_TITLE}])

    assert check_copy(deck) == ()


def test_title_case_rejects_lowercase_word(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": "Peta tiga bagian"}])

    diagnostics = check_copy(deck)

    assert [(item.rule, item.key, item.message) for item in diagnostics] == [
        ("title_case", "s01.title", "Kata 'tiga' pada judul harus diawali huruf kapital."),
        ("title_case", "s01.title", "Kata 'bagian' pada judul harus diawali huruf kapital."),
    ]


def test_title_case_keeps_function_word_lowercase_in_middle(
    make_deck: Callable[..., DeckIR],
) -> None:
    valid = make_deck(slides=[{"id": "s01", "title": "Dari Pengajuan ke Keputusan"}])
    invalid = make_deck(slides=[{"id": "s01", "title": "Dari Pengajuan Ke Keputusan"}])

    assert "title_case" not in rules(check_copy(valid))
    assert "title_case" in rules(check_copy(invalid))


def test_title_case_preserves_acronym(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(slides=[{"id": "s01", "title": "Panduan API"}])

    assert "title_case" not in rules(check_copy(deck))


def test_title_case_english_function_word(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(language="en", slides=[{"id": "s01", "title": "The Road To Results"}])

    diagnostics = check_copy(deck)

    assert "title_case" in rules(diagnostics)


def test_title_case_accepts_english_title(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(language="en", slides=[{"id": "s01", "title": VALID_TITLE_EN}])

    assert "title_case" not in rules(check_copy(deck))


def test_title_case_falls_back_to_display_role(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "blocks": [
                    {
                        "id": "headline",
                        "type": "text",
                        "role": "display",
                        "text": "Peta tiga bagian",
                    }
                ],
            }
        ]
    )

    diagnostics = check_copy(deck)

    assert "title_case" in rules(diagnostics)
    assert any(item.key == "s01.title" for item in diagnostics)


def title_case_findings(title: str) -> list[tuple[str, int]]:
    return [(violation.message, violation.offset) for violation in check_title_case(title)]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "peta Tiga Bagian",
            [("Kata 'peta' pada judul harus diawali huruf kapital.", 0)],
        ),
        (
            "Dari Pengajuan Ke Keputusan",
            [("Kata fungsi 'Ke' di tengah judul harus huruf kecil.", 15)],
        ),
        (
            "Peta Tiga bagian",
            [("Kata 'bagian' pada judul harus diawali huruf kapital.", 10)],
        ),
        (
            "Laporan Tahunan.   ",
            [("Judul slide tidak boleh diakhiri titik.", 15)],
        ),
        (
            "Peta Tiga, Bagian",
            [("Judul slide tidak boleh memuat koma.", 9)],
        ),
        (
            "Peta  Tiga   bagian",
            [("Kata 'bagian' pada judul harus diawali huruf kapital.", 13)],
        ),
    ],
)
def test_title_case_reports_exact_violation_offsets(
    title: str,
    expected: list[tuple[str, int]],
) -> None:
    assert title_case_findings(title) == expected


def test_title_case_requires_last_function_word_capitalized() -> None:
    assert check_title_case("Jalan Ke") == ()

    assert title_case_findings("Jalan ke") == [
        ("Kata 'ke' pada judul harus diawali huruf kapital.", 6)
    ]


def test_title_case_checks_the_last_token_in_a_very_long_title() -> None:
    # 1026 token melewati cache integer CPython; token terakhir tetap harus diperiksa
    # tanpa bergantung pada identitas objek integer.
    title = " ".join(["A"] * 1025 + ["ke"])

    assert title_case_findings(title) == [
        ("Kata 'ke' pada judul harus diawali huruf kapital.", 2050)
    ]


def test_title_case_checks_words_after_punctuation_only_token() -> None:
    assert title_case_findings("Peta ... tiga Bagian") == [
        ("Kata 'tiga' pada judul harus diawali huruf kapital.", 9)
    ]


def test_title_case_checks_words_after_middle_function_word() -> None:
    assert title_case_findings("Dari Pengajuan ke hasil Akhir") == [
        ("Kata 'hasil' pada judul harus diawali huruf kapital.", 18)
    ]


def test_title_case_uses_unicode_lowercase_for_function_word_detection() -> None:
    # U+212A KELVIN SIGN lowercase menjadi "k", sehingga "\u212ae" adalah kata fungsi "ke".
    assert title_case_findings("Dari Pengajuan \u212ae Keputusan") == [
        ("Kata fungsi '\u212ae' di tengah judul harus huruf kecil.", 15)
    ]


def test_banned_phrase_indonesian(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Ini krusial.")

    diagnostics = check_copy(deck)

    assert "banned_phrases" in rules_for(diagnostics, "s01.notes")


def test_banned_phrase_english(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "We delve into the data.", language="en")

    diagnostics = check_copy(deck)

    assert "banned_phrases" in rules_for(diagnostics, "s01.notes")


def test_banned_phrase_extra_from_config(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  banned_phrases:
    extra:
      id: ["frasa khusus"]
"""
    )
    deck = deck_with_notes(make_deck, "Ini frasa khusus.")

    diagnostics = check_copy(deck, config=config)

    assert "banned_phrases" in rules_for(diagnostics, "s01.notes")


def test_banned_phrase_extra_language_isolation(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  banned_phrases:
    extra:
      id: ["frasa khusus"]
"""
    )
    deck = deck_with_notes(make_deck, "Ini frasa khusus.", language="en")

    diagnostics = check_copy(deck, config=config)

    assert "banned_phrases" not in rules(diagnostics)


def test_indonesian_banned_phrase_not_applied_to_english(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Ini krusial.", language="en")

    diagnostics = check_copy(deck)

    assert "banned_phrases" not in rules(diagnostics)


def test_dash_rejects_em_dash(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Bagian A\u2014bagian B.")

    assert "dash" in rules(check_copy(deck))


def test_dash_rejects_en_dash(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Rentang 2024\u20132026.")

    assert "dash" in rules(check_copy(deck))


def test_dash_accepts_hyphen(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Rentang 2024-2026.")

    assert "dash" not in rules(check_copy(deck))


def test_sentence_length_accepts_exactly_25_words(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, " ".join(["kata"] * 25) + ".")

    diagnostics = check_copy(deck)

    assert "sentence_length" not in rules(diagnostics)


def test_sentence_length_warns_above_25_words(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, " ".join(["kata"] * 26) + ".")

    diagnostics = check_copy(deck)

    assert "sentence_length" in rules(diagnostics)
    assert all(diagnostic.severity == "warning" for diagnostic in diagnostics)


def test_sentence_length_honors_configured_max_words(make_deck: Callable[..., DeckIR]) -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  sentence_length:
    max_words: 5
"""
    )
    deck = deck_with_notes(make_deck, "Satu dua tiga empat lima enam.")

    diagnostics = check_copy(deck, config=config)

    assert "sentence_length" in rules(diagnostics)


@pytest.mark.parametrize(
    ("lead", "tail"),
    [
        ("bukan hanya", "tetapi"),
        ("tidak hanya", "tetapi"),
        ("bukan hanya", "tapi"),
        ("tidak hanya", "tapi"),
        ("bukan hanya", "melainkan"),
        ("tidak hanya", "melainkan"),
    ],
)
def test_negative_parallelism_variants(
    make_deck: Callable[..., DeckIR],
    lead: str,
    tail: str,
) -> None:
    deck = deck_with_notes(make_deck, f"Rapat ini {lead} catatan, {tail} juga keputusan.")

    diagnostics = check_copy(deck)

    assert "negative_parallelism" in rules(diagnostics)


def test_negative_parallelism_english(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(
        make_deck,
        "This is not only fast but also reliable.",
        language="en",
    )

    assert "negative_parallelism" in rules(check_copy(deck))


def test_contrast_pattern_positive(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Grafik ini contoh data, bukan capaian resmi.")

    assert "contrast_pattern" in rules(check_copy(deck))


def test_contrast_pattern_negative(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Grafik ini contoh data bukan capaian resmi.")

    assert "contrast_pattern" not in rules(check_copy(deck))


def test_forced_triad_positive(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Cepat, tepat, dan terpercaya.")

    diagnostics = check_copy(deck)

    assert "forced_triad" in rules(diagnostics)
    assert all(diagnostic.severity == "warning" for diagnostic in diagnostics)


def test_forced_triad_negative(make_deck: Callable[..., DeckIR]) -> None:
    deck = deck_with_notes(make_deck, "Cepat dan tepat.")

    assert "forced_triad" not in rules(check_copy(deck))


def test_one_line_closer_positive(make_deck: Callable[..., DeckIR]) -> None:
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

    diagnostics = check_copy(deck)

    assert "one_line_closer" in rules_for(diagnostics, "s01.points.item3.text")


def test_one_line_closer_negative_when_last_has_six_words(
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
                            "Satu dua tiga empat lima enam",
                            "Satu dua tiga empat lima enam",
                        ),
                    }
                ],
            }
        ]
    )

    assert "one_line_closer" not in rules(check_copy(deck))


def test_one_line_closer_requires_three_items(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "points",
                        "type": "bullets",
                        "items": ("Satu dua tiga empat lima enam", "Siap melangkah."),
                    }
                ],
            }
        ]
    )

    assert "one_line_closer" not in rules(check_copy(deck))


def test_paired_clause_label_positive(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
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

    diagnostics = check_copy(deck)

    assert "paired_clause_label" in rules_for(diagnostics, "s01.labels.item1.text")


def test_paired_clause_label_negative_with_verbs(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "labels",
                        "type": "bullets",
                        "items": ("Rapat berakhir, keputusan diambil.",),
                    }
                ],
            }
        ]
    )

    assert "paired_clause_label" not in rules(check_copy(deck))


def test_paired_clause_label_negative_too_long(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "labels",
                        "type": "bullets",
                        "items": ("Satu Dua Tiga Empat, Lima Enam Tujuh Delapan Sembilan",),
                    }
                ],
            }
        ]
    )

    assert "paired_clause_label" not in rules(check_copy(deck))


def test_paired_clause_label_negative_multiple_commas(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "labels",
                        "type": "bullets",
                        "items": ("Satu, Dua, Tiga",),
                    }
                ],
            }
        ]
    )

    assert "paired_clause_label" not in rules(check_copy(deck))


def test_paired_clause_label_negative_trailing_period(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "labels",
                        "type": "bullets",
                        "items": ("Tiga Kelompok, Satu Alur Baca.",),
                    }
                ],
            }
        ]
    )

    assert "paired_clause_label" not in rules(check_copy(deck))


def test_paired_clause_label_negative_without_long_word(make_deck: Callable[..., DeckIR]) -> None:
    deck = make_deck(
        slides=[
            {
                "id": "s01",
                "title": VALID_TITLE,
                "blocks": [
                    {
                        "id": "labels",
                        "type": "bullets",
                        "items": ("A, B",),
                    }
                ],
            }
        ]
    )

    assert "paired_clause_label" not in rules(check_copy(deck))


def test_paired_clause_fragments_reject_trailing_newline() -> None:
    assert paired_clause_fragments("Tiga Kelompok, Satu Alur Baca\n") is None


@pytest.mark.parametrize("text", ["", "   "])
def test_paired_clause_fragments_reject_empty_text(text: str) -> None:
    assert paired_clause_fragments(text) is None


@pytest.mark.parametrize("text", [", Kanan", "Kiri, "])
def test_paired_clause_fragments_reject_empty_fragment(text: str) -> None:
    assert paired_clause_fragments(text) is None


def test_paired_clause_fragments_reject_verb_without_sentence_punctuation() -> None:
    assert paired_clause_fragments("Rapat berakhir, keputusan diambil") is None


def test_forced_triad_truncates_long_excerpt() -> None:
    text = (
        "Kata pertama yang sangat panjang sekali, kata kedua yang juga sangat panjang, "
        "dan kata ketiga yang panjang"
    )

    (violation,) = check_forced_triad(text)

    compact = " ".join(text.split())
    assert violation.message == f"Teks memakai triad paksa: '{compact[:77]}...'."


def test_closer_key_parses_prefixed_index() -> None:
    group = parse_closer_key("s07.points.item3.text")

    assert group is not None
    assert group.prefix == "s07.points"
    assert group.index == "item3"
    assert group.leaf == "text"
    assert group.number == 3
    assert parse_closer_key("s07.points.item3.heading") is None


def test_closer_key_rejects_empty_prefix() -> None:
    assert parse_closer_key(".item3.text") is None


def test_english_language_pack_skips_indonesian_only_rules(
    make_deck: Callable[..., DeckIR],
) -> None:
    deck = deck_with_notes(make_deck, "Cepat, tepat, dan terpercaya.", language="en")

    diagnostics = check_copy(deck)

    assert "forced_triad" not in rules(diagnostics)
    assert "paired_clause_label" not in rules(diagnostics)
    assert "contrast_pattern" not in rules(diagnostics)
