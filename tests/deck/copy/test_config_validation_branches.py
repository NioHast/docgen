"""Test validasi ``copy.yaml`` untuk cabang schema yang belum tercakup."""

from pathlib import Path
from typing import Any

import pytest

from autooffice.deck.copy import (
    DEFAULT_COPY_CONFIG,
    DEFAULT_RULES,
    AllowEntry,
    CopyConfig,
    CopyConfigError,
    RuleConfig,
    load_copy_config,
    loads_copy_config,
)


def test_rule_config_rejects_unknown_rule() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        RuleConfig(name="unknown_rule", severity="error")


def test_rule_config_rejects_invalid_severity() -> None:
    with pytest.raises(CopyConfigError, match="Severity"):
        RuleConfig(name="dash", severity="fatal")  # type: ignore[arg-type]


def test_rule_config_requires_boolean_enabled() -> None:
    with pytest.raises(CopyConfigError, match="enabled"):
        RuleConfig(name="dash", severity="error", enabled="yes")  # type: ignore[arg-type]


@pytest.mark.parametrize("max_words", [True, 0, -1, "5"])
def test_rule_config_requires_positive_max_words(max_words: Any) -> None:
    with pytest.raises(CopyConfigError, match="max_words"):
        RuleConfig(name="sentence_length", severity="warning", max_words=max_words)


def test_allow_entry_requires_non_empty_key() -> None:
    with pytest.raises(CopyConfigError, match=r"allow\.key"):
        AllowEntry(key="   ", rules=("dash",), reason="alasan")


def test_allow_entry_requires_at_least_one_rule() -> None:
    with pytest.raises(CopyConfigError, match="minimal satu rule"):
        AllowEntry(key="s01.notes", rules=(), reason="alasan")


def test_allow_entry_rejects_unknown_rule() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        AllowEntry(key="s01.notes", rules=("unknown_rule",), reason="alasan")


def test_allow_entry_requires_reason() -> None:
    with pytest.raises(CopyConfigError, match="reason"):
        AllowEntry(key="s01.notes", rules=("dash",), reason="   ")


def test_copy_config_rejects_unsupported_schema() -> None:
    with pytest.raises(CopyConfigError, match="tidak didukung"):
        CopyConfig(schema=2)


def test_copy_config_rejects_unknown_rule_key() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        CopyConfig(rules={"mystery": DEFAULT_RULES["dash"]})


def test_copy_config_rejects_rule_key_name_mismatch() -> None:
    with pytest.raises(CopyConfigError, match="nama internal"):
        CopyConfig(rules={"dash": DEFAULT_RULES["title_case"]})


def test_rule_lookup_rejects_unknown_name() -> None:
    with pytest.raises(CopyConfigError, match="tidak dikenal"):
        DEFAULT_COPY_CONFIG.rule("mystery")


def test_load_copy_config_reports_unreadable_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "copy.yaml"
    path.write_text("schema: 1\n", encoding="utf-8")

    def fail_read(self: Path) -> bytes:
        raise OSError("disk penuh")

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    with pytest.raises(CopyConfigError, match="tidak dapat dibaca"):
        load_copy_config(path)


def test_load_copy_config_rejects_non_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "copy.yaml"
    path.write_bytes(b"schema: \xff\n")

    with pytest.raises(CopyConfigError, match="UTF-8"):
        load_copy_config(path)


def test_loads_copy_config_requires_text() -> None:
    with pytest.raises(CopyConfigError, match="harus string"):
        loads_copy_config(None)  # type: ignore[arg-type]


def test_loads_copy_config_rejects_invalid_yaml() -> None:
    with pytest.raises(CopyConfigError, match="YAML tidak valid"):
        loads_copy_config("schema: [1\n")


def test_loads_copy_config_requires_single_document() -> None:
    with pytest.raises(CopyConfigError, match="tepat satu dokumen"):
        loads_copy_config("schema: 1\n---\nschema: 1\n")


def test_loads_copy_config_rejects_null_document() -> None:
    with pytest.raises(CopyConfigError, match="tidak boleh kosong"):
        loads_copy_config("null\n")


@pytest.mark.parametrize("raw", ["true", "[1]", "satu"])
def test_schema_must_be_integer(raw: str) -> None:
    with pytest.raises(CopyConfigError, match="bilangan bulat"):
        loads_copy_config(f"schema: {raw}\n")


def test_target_requires_boolean() -> None:
    with pytest.raises(CopyConfigError, match=r"targets\.notes"):
        loads_copy_config("schema: 1\ntargets:\n  notes: 1\n")


def test_null_rule_uses_default() -> None:
    config = loads_copy_config("schema: 1\nrules:\n  dash:\n")

    assert config.rule("dash") == DEFAULT_RULES["dash"]


def test_rule_rejects_invalid_severity_setting() -> None:
    with pytest.raises(CopyConfigError, match="error, warning, atau off"):
        loads_copy_config("schema: 1\nrules:\n  dash:\n    severity: fatal\n")


def test_rule_requires_boolean_enabled_setting() -> None:
    with pytest.raises(CopyConfigError, match="enabled"):
        loads_copy_config("schema: 1\nrules:\n  dash:\n    enabled: 1\n")


def test_null_extra_is_empty() -> None:
    config = loads_copy_config("schema: 1\nrules:\n  banned_phrases:\n    extra:\n")

    assert dict(config.rule("banned_phrases").extra) == {}
    assert config.rule("banned_phrases").extra_for("id") == ()


@pytest.mark.parametrize("item", ['""', '"   "', "3"])
def test_extra_rejects_blank_or_non_string_phrase(item: str) -> None:
    text = f"schema: 1\nrules:\n  banned_phrases:\n    extra:\n      id: [{item}]\n"

    with pytest.raises(CopyConfigError, match="string tidak kosong"):
        loads_copy_config(text)


def test_extra_deduplicates_case_insensitively() -> None:
    config = loads_copy_config(
        """
schema: 1
rules:
  banned_phrases:
    extra:
      id: ["Frasa Khusus", "frasa khusus", " lain "]
"""
    )

    assert config.rule("banned_phrases").extra_for("id") == ("Frasa Khusus", "lain")


def test_allow_requires_list() -> None:
    with pytest.raises(CopyConfigError, match="daftar entri"):
        loads_copy_config("schema: 1\nallow: true\n")


def test_allow_rules_must_be_list() -> None:
    text = """
schema: 1
allow:
  - key: s01.notes
    rules: dash
    reason: alasan
"""

    with pytest.raises(CopyConfigError, match="daftar nama rule"):
        loads_copy_config(text)


def test_allow_rules_must_not_be_empty() -> None:
    text = """
schema: 1
allow:
  - key: s01.notes
    rules: []
    reason: alasan
"""

    with pytest.raises(CopyConfigError, match="minimal satu rule"):
        loads_copy_config(text)


@pytest.mark.parametrize("document", ["targets: []\n", "rules: x\n"])
def test_config_sections_require_mapping(document: str) -> None:
    with pytest.raises(CopyConfigError, match="harus mapping"):
        loads_copy_config("schema: 1\n" + document)


def test_copy_config_error_formats_path_without_source() -> None:
    error = CopyConfigError("Pesan", path=("rules", "dash"), source=None)

    assert str(error) == "rules.dash: Pesan"


def test_copy_config_error_formats_indexed_path() -> None:
    error = CopyConfigError("Pesan", path=("allow", 0, "rules"), source="copy.yaml")

    assert str(error) == "copy.yaml: allow[0].rules: Pesan"
