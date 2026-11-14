"""Test permukaan API publik paket copy dan transcript."""

import autooffice.deck.copy as copy
import autooffice.deck.transcript as transcript


def test_copy_package_exports_checker_api() -> None:
    assert callable(copy.check_copy)
    assert callable(copy.load_copy_config)
    assert callable(copy.loads_copy_config)
    assert callable(copy.normalize_language)
    assert copy.RULE_NAMES


def test_copy_package_exports_diagnostic_and_config_types() -> None:
    assert copy.Diagnostic
    assert copy.CopyConfig
    assert copy.CopyConfigError
    assert copy.CopyTargets
    assert copy.RuleConfig


def test_transcript_package_exports_parser_api() -> None:
    assert callable(transcript.parse_transcript)
    assert callable(transcript.parse_transcript_file)
    assert callable(transcript.load_transcript)
    assert transcript.TranscriptError
    assert transcript.TranscriptIR
    assert transcript.TranscriptSection
