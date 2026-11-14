"""Test parser transcript: heading, mapping ID, bahasa, dan durasi."""

from pathlib import Path

import pytest

from autooffice.deck.transcript import (
    TranscriptError,
    TranscriptIR,
    TranscriptProse,
    TranscriptSection,
    parse_transcript,
    parse_transcript_file,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "copy"
SLIDE_IDS = ("s01", "s02")
VALID_TRANSCRIPT = "\n".join(
    [
        "# Transkrip Demo",
        "",
        "## s02. Konteks",
        "",
        "### Indonesia",
        "",
        "Latar keputusan.",
        "",
        "**Perkiraan durasi:** 30 detik",
        "",
        "### English",
        "",
        "Context.",
        "",
        "## s01. Pembuka",
        "",
        "### Indonesia",
        "",
        "Selamat pagi.",
        "",
    ]
)


def test_transcript_maps_sections_by_slide_id() -> None:
    transcript = parse_transcript(VALID_TRANSCRIPT, slide_ids=SLIDE_IDS)

    assert [section.slide_id for section in transcript.sections] == ["s02", "s01"]
    assert transcript.by_slide_id["s01"].title == "Pembuka"
    assert transcript.by_slide_id["s02"].duration_seconds == 30


def test_transcript_preserves_prose_and_line_numbers() -> None:
    transcript = parse_transcript(VALID_TRANSCRIPT, slide_ids=SLIDE_IDS)
    section = transcript.by_slide_id["s02"]

    assert section.indonesian.text == "Latar keputusan."
    assert section.indonesian.line == 7
    assert section.english is not None
    assert section.english.text == "Context."
    assert section.english.line == 13


def test_transcript_keys_use_slide_and_language() -> None:
    transcript = parse_transcript(VALID_TRANSCRIPT, slide_ids=SLIDE_IDS)

    assert transcript.by_slide_id["s02"].id_key == "s02.transcript.id"
    assert transcript.by_slide_id["s02"].en_key == "s02.transcript.en"
    assert set(transcript.keys()) == {
        "s01.transcript.id",
        "s02.transcript.id",
        "s02.transcript.en",
    }


def test_transcript_english_is_optional() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
        ]
    )

    transcript = parse_transcript(text, slide_ids=("s01",))

    assert transcript.by_slide_id["s01"].english is None


def test_transcript_requires_all_slides() -> None:
    with pytest.raises(TranscriptError, match="tidak memuat bagian"):
        parse_transcript(VALID_TRANSCRIPT, slide_ids=("s01", "s02", "s03"))


def test_transcript_rejects_duplicate_slide() -> None:
    text = VALID_TRANSCRIPT + "\n## s01. Duplikat\n\n### Indonesia\n\nHalo.\n"

    with pytest.raises(TranscriptError, match="duplikat"):
        parse_transcript(text, slide_ids=SLIDE_IDS)


def test_transcript_rejects_unknown_slide() -> None:
    with pytest.raises(TranscriptError, match="tidak dikenal"):
        parse_transcript(VALID_TRANSCRIPT, slide_ids=("s01",))


def test_transcript_rejects_missing_indonesian() -> None:
    text = "\n".join(["## s01. Pembuka", "", "**Perkiraan durasi:** 10 detik", ""])

    with pytest.raises(TranscriptError, match="Indonesia"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_content_before_indonesia() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "Teks sebelum heading bahasa.",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="Indonesia"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_unknown_language() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Deutsch",
            "",
            "Guten Morgen.",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="tidak dikenal"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_duplicate_english() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
            "### English",
            "",
            "Good morning.",
            "",
            "### English",
            "",
            "Good morning again.",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="duplikat"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_english_before_indonesia() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### English",
            "",
            "Good morning.",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="sebelum"):
        parse_transcript(text, slide_ids=("s01",))


@pytest.mark.parametrize("value", ["0 detik", "-1 detik", "45", "abc detik", ""])
def test_transcript_rejects_invalid_duration(value: str) -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
            f"**Perkiraan durasi:** {value}",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="Durasi"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_duplicate_duration() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
            "**Perkiraan durasi:** 10 detik",
            "",
            "**Perkiraan durasi:** 20 detik",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="sekali"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_invalid_heading() -> None:
    text = "\n".join(
        [
            "## s01 - Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="Heading"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_heading_without_title() -> None:
    text = "\n".join(["## s01.", "", "### Indonesia", "", "Selamat pagi.", ""])

    with pytest.raises(TranscriptError, match="Heading"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_allows_free_h1_title() -> None:
    text = "\n".join(
        [
            "# Judul Bebas",
            "",
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
        ]
    )

    transcript = parse_transcript(text, slide_ids=("s01",))

    assert transcript.sections[0].slide_id == "s01"


def test_transcript_file_fixture() -> None:
    transcript = parse_transcript_file(FIXTURE_DIR / "transcripts.md", slide_ids=SLIDE_IDS)

    assert [section.slide_id for section in transcript.sections] == ["s02", "s01"]
    assert transcript.by_slide_id["s01"].indonesian.text == "Selamat pagi."


def test_transcript_file_missing_slide_fixture() -> None:
    with pytest.raises(TranscriptError, match="tidak memuat bagian"):
        parse_transcript_file(FIXTURE_DIR / "transcripts-missing.md", slide_ids=SLIDE_IDS)


def test_transcript_rejects_non_string_input() -> None:
    with pytest.raises(TranscriptError, match="harus string"):
        parse_transcript(None, slide_ids=SLIDE_IDS)  # type: ignore[arg-type]


def test_transcript_rejects_language_heading_outside_section() -> None:
    with pytest.raises(TranscriptError, match="di dalam bagian"):
        parse_transcript("### Indonesia\n\nHalo.\n", slide_ids=("s01",))


def test_transcript_rejects_unknown_heading_inside_section() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
            "# Subjudul bebas",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="tidak dikenal"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_text_outside_section() -> None:
    with pytest.raises(TranscriptError, match="di luar bagian"):
        parse_transcript("Teks liar.\n", slide_ids=("s01",))


def test_transcript_without_sections_and_slides_is_empty() -> None:
    transcript = parse_transcript("", slide_ids=())

    assert transcript.sections == ()
    assert len(transcript) == 0


def test_transcript_rejects_duplicate_indonesian_heading() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
            "### Indonesia",
            "",
            "Selamat pagi lagi.",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="duplikat"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_empty_indonesian_prose() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "   ",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="tidak boleh kosong"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_rejects_empty_english_prose() -> None:
    text = "\n".join(
        [
            "## s01. Pembuka",
            "",
            "### Indonesia",
            "",
            "Selamat pagi.",
            "",
            "### English",
            "",
            "",
        ]
    )

    with pytest.raises(TranscriptError, match="tidak boleh kosong"):
        parse_transcript(text, slide_ids=("s01",))


def test_transcript_file_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TranscriptError, match="tidak dapat dibaca"):
        parse_transcript_file(tmp_path / "tidak-ada.md", slide_ids=SLIDE_IDS)


def test_transcript_file_rejects_non_utf8(tmp_path: Path) -> None:
    path = tmp_path / "transcripts.md"
    path.write_bytes(b"## s01. Pembuka\n\n### Indonesia\n\n\xff\n")

    with pytest.raises(TranscriptError, match="harus UTF-8"):
        parse_transcript_file(path, slide_ids=("s01",))


def test_transcript_bilingual_duration_and_order_are_preserved() -> None:
    transcript = parse_transcript(VALID_TRANSCRIPT, slide_ids=("s01", "s02"))

    assert [section.slide_id for section in transcript] == ["s02", "s01"]
    assert len(transcript) == 2
    assert transcript.section("s02") is transcript.by_slide_id["s02"]
    assert transcript.section("s02").indonesian.text == "Latar keputusan."  # type: ignore[union-attr]
    assert transcript.section("s02").english is not None  # type: ignore[union-attr]
    assert transcript.section("s02").english.text == "Context."  # type: ignore[union-attr]
    assert transcript.section("s02").duration_seconds == 30  # type: ignore[union-attr]
    assert transcript.section("s99") is None


def test_prose_rejects_invalid_text_and_line() -> None:
    with pytest.raises(ValueError, match="tidak kosong"):
        TranscriptProse("   ")
    with pytest.raises(ValueError, match="tidak kosong"):
        TranscriptProse(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="negatif"):
        TranscriptProse("Halo.", line=-1)


def test_section_rejects_non_positive_duration() -> None:
    prose = TranscriptProse("Halo.")

    with pytest.raises(ValueError, match="positif"):
        TranscriptSection(slide_id="s01", title="Pembuka", indonesian=prose, duration_seconds=0)


def test_transcript_ir_rejects_duplicate_sections() -> None:
    section = TranscriptSection(
        slide_id="s01",
        title="Pembuka",
        indonesian=TranscriptProse("Halo."),
    )

    with pytest.raises(ValueError, match="duplikat"):
        TranscriptIR(sections=(section, section))


def test_transcript_ir_iter_len_and_section_lookup() -> None:
    section = TranscriptSection(
        slide_id="s01",
        title="Pembuka",
        indonesian=TranscriptProse("Halo."),
    )
    transcript = TranscriptIR(sections=(section,), source="uji.md")

    assert list(transcript) == [section]
    assert len(transcript) == 1
    assert transcript.section("s01") is section
    assert transcript.section("s02") is None
    assert transcript.keys() == ("s01.transcript.id",)
