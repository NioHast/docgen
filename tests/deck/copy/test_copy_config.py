"""Test schema, merge, disable, dan allowlist ``copy.yaml``."""

from pathlib import Path

import pytest

from autooffice.deck.copy import (
    CopyConfigError,
    CopyTargets,
    load_copy_config,
    loads_copy_config,
    validate_allowlist,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "copy"


def test_default_config_has_all_rules_enabled() -> None:
    config = load_copy_config()

    assert config.schema == 1
    assert config.targets == CopyTargets()
    assert {
        name: (rule.severity, rule.active, rule.max_words) for name, rule in config.rules.items()
    } == {
        "banned_phrases": ("error", True, None),
        "title_case": ("error", True, None),
        "dash": ("error", True, None),
        "sentence_length": ("warning", True, 25),
        "negative_parallelism": ("error", True, None),
        "contrast_pattern": ("error", True, None),
        "forced_triad": ("warning", True, None),
        "one_line_closer": ("warning", True, None),
        "paired_clause_label": ("warning", True, None),
    }
    assert dict(config.rule("banned_phrases").extra) == {}
    assert config.allow == ()


def test_partial_rule_merge_keeps_other_defaults() -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  sentence_length:
    max_words: 12
  dash:
    severity: off
"""
    )

    assert config.rule("sentence_length").max_words == 12
    assert config.rule("sentence_length").severity == "warning"
    assert config.rule("dash").severity == "off"
    assert config.rule("banned_phrases").severity == "error"


def test_partial_targets_merge_keeps_defaults() -> None:
    config = loads_copy_config(
        """
schema: 1
targets:
  notes: false
"""
    )

    assert config.targets.slides is True
    assert config.targets.notes is False
    assert config.targets.transcript is True


def test_severity_off_disables_rule() -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  dash:
    severity: off
"""
    )

    assert config.rule("dash").active is False
    assert config.rule("dash").diagnostic_severity is None


def test_enabled_false_disables_rule() -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  sentence_length:
    enabled: false
"""
    )

    assert config.rule("sentence_length").active is False
    assert config.rule("sentence_length").max_words == 25


def test_extra_phrases_are_additive_per_language() -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  banned_phrases:
    extra:
      id: ["frasa khusus"]
      en: ["special phrase"]
"""
    )

    assert config.rule("banned_phrases").extra_for("id") == ("frasa khusus",)
    assert config.rule("banned_phrases").extra_for("en") == ("special phrase",)


def test_unknown_root_key_is_rejected() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        loads_copy_config("schema: 1\nfoo: true\n")


def test_unknown_target_key_is_rejected() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        loads_copy_config("schema: 1\ntargets:\n  docx: true\n")


def test_unknown_rule_is_rejected() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        loads_copy_config("schema: 1\nrules:\n  unknown_rule:\n    severity: error\n")


def test_unknown_rule_setting_is_rejected() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        loads_copy_config("schema: 1\nrules:\n  dash:\n    max_words: 10\n")


def test_max_words_must_be_positive_integer() -> None:
    with pytest.raises(CopyConfigError, match="max_words"):
        loads_copy_config("schema: 1\nrules:\n  sentence_length:\n    max_words: 0\n")


def test_extra_requires_literal_string_list() -> None:
    with pytest.raises(CopyConfigError, match="daftar frasa"):
        loads_copy_config("schema: 1\nrules:\n  banned_phrases:\n    extra:\n      id: true\n")


def test_allow_requires_reason() -> None:
    with pytest.raises(CopyConfigError, match="reason"):
        loads_copy_config(
            """
schema: 1
allow:
  - key: s01.notes
    rules: [dash]
"""
        )


def test_allow_requires_known_rule() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        loads_copy_config(
            """
schema: 1
allow:
  - key: s01.notes
    rules: [unknown_rule]
    reason: alasan
"""
        )


def test_allow_requires_non_empty_key() -> None:
    with pytest.raises(CopyConfigError, match=r"allow\.key"):
        loads_copy_config(
            """
schema: 1
allow:
  - key: ""
    rules: [dash]
    reason: alasan
"""
        )


def test_allow_rejects_duplicate_rule() -> None:
    with pytest.raises(CopyConfigError, match="duplikat"):
        loads_copy_config(
            """
schema: 1
allow:
  - key: s01.notes
    rules: [dash, dash]
    reason: alasan
"""
        )


def test_schema_must_be_one() -> None:
    with pytest.raises(CopyConfigError, match="Schema"):
        loads_copy_config("schema: 2\n")


def test_allow_key_must_exist_on_deck() -> None:
    config = loads_copy_config(
        """
schema: 1
allow:
  - key: s99.notes
    rules: [dash]
    reason: alasan
"""
    )

    with pytest.raises(CopyConfigError, match="tidak ditemukan"):
        validate_allowlist(config, {"s01.notes"})


def test_fixture_copy_yaml_loads() -> None:
    config = load_copy_config(FIXTURE_DIR / "copy.yaml")

    assert config.targets.transcript is True
    assert config.rule("sentence_length").max_words == 12
    assert config.rule("banned_phrases").extra_for("id") == ("frasa khusus",)


def test_copy_path_outside_deck_dir_is_rejected(tmp_path: Path) -> None:
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    outside = tmp_path / "copy.yaml"
    outside.write_text("schema: 1\n", encoding="utf-8", newline="\n")

    with pytest.raises(CopyConfigError, match="folder deck"):
        load_copy_config(outside, deck_dir=deck_dir)
