"""Test permukaan API publik paket copy dan transcript."""

import autooffice.deck.copy as copy
import autooffice.deck.transcript as transcript


def test_copy_package_exports_checker_api() -> None:
    assert callable(copy.check_copy)
    assert callable(copy.load_copy_config)
    assert callable(copy.loads_copy_config)
    assert callable(copy.normalize_language)
    assert copy.RULE_NAMES
    assert copy.normalize_language("en-US") == "en"
    assert copy.loads_copy_config("schema: 1").rule("dash").active is True


def test_copy_package_exports_diagnostic_and_config_types() -> None:
    assert copy.Diagnostic
    assert copy.CopyConfig
    assert copy.CopyConfigError
    assert copy.CopyTargets
    assert copy.RuleConfig
    config = copy.CopyConfig()
    assert config.schema == 1
    assert config.rule("sentence_length").max_words == 25


def test_transcript_package_exports_parser_api() -> None:
    assert callable(transcript.parse_transcript)
    assert callable(transcript.parse_transcript_file)
    assert callable(transcript.load_transcript)
    assert transcript.TranscriptError
    assert transcript.TranscriptIR
    assert transcript.TranscriptSection
    parsed = transcript.parse_transcript(
        "## s01. Pembuka\n\n### Indonesia\n\nHalo.\n",
        slide_ids=("s01",),
    )
    assert parsed.by_slide_id["s01"].indonesian.text == "Halo."
