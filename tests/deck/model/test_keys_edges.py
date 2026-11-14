"""Test edge branch grammar key dan registry yang belum tercakup."""

from typing import cast

import pytest

from autooffice.deck.model import (
    MAX_KEY_LENGTH,
    KeyBinding,
    KeyGrammarError,
    KeyRegistry,
    make_key,
    parse_key,
    validate_block_id,
    validate_key,
    validate_leaf,
    validate_slide_id,
)


def _binding(
    key: str,
    *,
    slide_id: str = "s01",
    block_id: str | None = "title",
    leaf: str = "text",
    yaml_path: tuple[str | int, ...] = ("slides", 0, "blocks", 0, "text"),
    value: str | int | float = "Judul",
    plain_text: str = "Judul",
    kind: str = "text",
) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,  # type: ignore[arg-type]
        sync=True,
        yaml_path=yaml_path,
        value=value,
        plain_text=plain_text,
    )


def test_non_string_slide_id_is_rejected() -> None:
    with pytest.raises(KeyGrammarError, match="Slide ID harus string"):
        validate_slide_id(cast("str", 1))


def test_non_string_block_id_is_rejected() -> None:
    with pytest.raises(KeyGrammarError, match="Block ID harus string"):
        validate_block_id(cast("str", 1))


def test_non_string_leaf_is_rejected() -> None:
    with pytest.raises(KeyGrammarError, match="Leaf key tidak boleh kosong"):
        validate_leaf(cast("str", 1))


def test_make_key_rejects_unknown_slide_leaf() -> None:
    with pytest.raises(KeyGrammarError, match="Leaf slide"):
        make_key("s01", None, "title")


def test_key_length_boundary_is_exactly_160_characters() -> None:
    prefix = "s01.title."
    leaf = "a" * (MAX_KEY_LENGTH - len(prefix))

    key = make_key("s01", "title", leaf)

    assert len(key) == MAX_KEY_LENGTH
    with pytest.raises(KeyGrammarError, match="melebihi 160"):
        make_key("s01", "title", leaf + "a")


def test_parse_key_rejects_unknown_two_segment_slide_key() -> None:
    with pytest.raises(KeyGrammarError, match="bukan key slide"):
        parse_key("s01.title")


@pytest.mark.parametrize(
    ("key", "match"),
    [
        (cast("str", 1), "Key harus string"),
        ("", "Key tidak boleh kosong"),
        ("s01." + ("a" * 160), "melebihi 160"),
    ],
)
def test_validate_key_rejects_invalid_key_text(key: str, match: str) -> None:
    with pytest.raises(KeyGrammarError, match=match):
        validate_key(key)


def test_registry_properties_follow_insertion_order() -> None:
    registry = KeyRegistry()
    first = _binding("s01.title.text")
    second = _binding(
        "s01.lead.text",
        block_id="lead",
        yaml_path=("slides", 0, "blocks", 1, "text"),
        value="Lead",
        plain_text="Lead",
    )

    registry.extend((first, second))

    assert registry.bindings == (first, second)
    assert registry.keys == ("s01.title.text", "s01.lead.text")


@pytest.mark.parametrize("key", ["", cast("str", 7)])
def test_registry_rejects_missing_key(key: str) -> None:
    with pytest.raises(KeyGrammarError, match="key yang tidak kosong"):
        KeyRegistry().add(_binding(key))


@pytest.mark.parametrize("value", [True, cast("str | int | float", None)])
def test_registry_rejects_boolean_and_none_values(value: str | int | float) -> None:
    with pytest.raises(KeyGrammarError, match="value yang bukan"):
        KeyRegistry().add(_binding("s01.title.text", value=value))


@pytest.mark.parametrize("plain_text", [cast("str", None), "   "])
def test_registry_rejects_empty_plain_text(plain_text: str) -> None:
    with pytest.raises(KeyGrammarError, match="plain_text kosong"):
        KeyRegistry().add(_binding("s01.title.text", plain_text=plain_text))


@pytest.mark.parametrize(
    "yaml_path",
    [(), cast("tuple[str | int, ...]", ["slides", 0])],
)
def test_registry_rejects_invalid_yaml_path(yaml_path: tuple[str | int, ...]) -> None:
    with pytest.raises(KeyGrammarError, match="harus memiliki yaml_path"):
        KeyRegistry().add(_binding("s01.title.text", yaml_path=yaml_path))


def test_registry_rejects_unknown_binding_kind() -> None:
    with pytest.raises(KeyGrammarError, match="kind tidak dikenal"):
        KeyRegistry().add(_binding("s01.title.text", kind="bogus"))


def test_registry_rejects_key_owned_by_different_slide() -> None:
    binding = _binding("s01.title.text", slide_id="s02")

    with pytest.raises(KeyGrammarError, match=r"tidak cocok dengan pemiliknya.*s02\.title\.text"):
        KeyRegistry().add(binding)
