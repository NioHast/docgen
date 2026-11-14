"""Test grammar key, registry, dan stabilitas key."""

from pathlib import Path

import pytest
from ruamel.yaml import YAML

from autooffice.deck.model import (
    KeyBinding,
    KeyGrammarError,
    KeyRegistry,
    compile_deck,
    load_deck,
    loads_deck,
    make_key,
    parse_key,
    validate_key,
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
    sync: bool = True,
) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,  # type: ignore[arg-type]
        sync=sync,
        yaml_path=yaml_path,
        value=value,
        plain_text=plain_text,
    )


def test_make_key_for_block() -> None:
    assert make_key("s03", "kpi1", "value") == "s03.kpi1.value"


def test_make_key_for_slide_notes_and_source() -> None:
    assert make_key("s01", None, "notes") == "s01.notes"
    assert make_key("s01", None, "source.text") == "s01.source.text"


@pytest.mark.parametrize("slide_id", ["s1", "x01", "s01a", "", "S01"])
def test_invalid_slide_id_rejected(slide_id: str) -> None:
    with pytest.raises(KeyGrammarError, match="Slide ID"):
        make_key(slide_id, "title", "text")


@pytest.mark.parametrize("block_id", ["Title", "1title", "title-name", "a" * 33, "ti.tle"])
def test_invalid_block_id_rejected(block_id: str) -> None:
    with pytest.raises(KeyGrammarError, match="Block ID"):
        make_key("s01", block_id, "text")


@pytest.mark.parametrize(
    "leaf",
    ["item0.text", "r0.c1", "series0.name", "value0", "Text", "item-1", "item..text", ""],
)
def test_invalid_leaf_rejected(leaf: str) -> None:
    with pytest.raises(KeyGrammarError, match=r"leaf|Leaf|Indeks"):
        make_key("s01", "title", leaf)


def test_key_length_limit_rejected() -> None:
    slide_id = "s" + ("0" * 200)

    with pytest.raises(KeyGrammarError, match="160"):
        make_key(slide_id, "title", "text")


def test_validate_key_accepts_block_and_slide_keys() -> None:
    assert validate_key("s04.chart1.series1.value3") == "s04.chart1.series1.value3"
    assert validate_key("s01.notes") == "s01.notes"
    assert validate_key("s01.source.text") == "s01.source.text"


def test_parse_key_slide_and_block() -> None:
    notes = parse_key("s01.notes")
    source = parse_key("s01.source.text")
    block = parse_key("s05.table1.r2.c3")

    assert notes.block_id is None
    assert notes.leaf == "notes"
    assert source.block_id is None
    assert source.leaf == "source.text"
    assert block.block_id == "table1"
    assert block.leaf == "r2.c3"


def test_key_registry_rejects_duplicate_key_and_names_both_paths() -> None:
    registry = KeyRegistry()
    registry.add(_binding("s01.title.text"))
    duplicate = _binding(
        "s01.title.text",
        yaml_path=("slides", 0, "blocks", 1, "text"),
    )

    with pytest.raises(
        KeyGrammarError, match=r"duplikat.*slides\[0\]\.blocks\[1\]\.text.*slides\[0\]\.blocks\[0\]"
    ):
        registry.add(duplicate)


def test_key_registry_rejects_key_owner_mismatch() -> None:
    registry = KeyRegistry()
    binding = _binding("s01.title.text", block_id="lead", leaf="text")

    with pytest.raises(KeyGrammarError, match="tidak cocok"):
        registry.add(binding)


def test_key_registry_rejects_block_id_that_parses_as_slide_source() -> None:
    registry = KeyRegistry()
    binding = _binding("s01.source.text", block_id="source", leaf="text")

    with pytest.raises(KeyGrammarError, match="block_id"):
        registry.add(binding)


def test_key_registry_rejects_duplicate_yaml_path() -> None:
    registry = KeyRegistry()
    registry.add(_binding("s01.title.text"))
    other = _binding(
        "s01.lead.text",
        block_id="lead",
        yaml_path=("slides", 0, "blocks", 0, "text"),
        value="Lead",
        plain_text="Lead",
    )

    with pytest.raises(KeyGrammarError, match="yaml_path duplikat"):
        registry.add(other)


def test_key_registry_manifest_is_ordered() -> None:
    registry = KeyRegistry()
    registry.add(_binding("s01.title.text"))
    registry.add(
        _binding(
            "s01.lead.text",
            block_id="lead",
            yaml_path=("slides", 0, "blocks", 1, "text"),
            value="Lead",
            plain_text="Lead",
        )
    )

    assert registry.manifest().keys() == ("s01.title.text", "s01.lead.text")


def test_yaml_path_points_to_source_value(fixture_dir: Path) -> None:
    path = fixture_dir / "minimal.yaml"
    deck = compile_deck(load_deck(path))
    binding = next(item for item in deck.keys.bindings if item.key == "s01.title.text")
    raw = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    value: object = raw
    for segment in binding.yaml_path:
        if isinstance(segment, int):
            assert isinstance(value, list)
            value = value[segment]
        else:
            assert isinstance(value, dict)
            value = value[segment]

    assert value == "Satu skema untuk **semua** target."
    assert binding.value == value
    assert binding.plain_text == "Satu skema untuk semua target."


def test_yaml_path_for_custom_block_uses_rows(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "custom-grid.yaml"))
    binding = next(item for item in deck.keys.bindings if item.key == "s07.insight.text")

    assert binding.yaml_path == ("slides", 0, "rows", 2, "blocks", 1, "text")


def _ordered_deck(order: tuple[str, str]) -> str:
    slides = []
    for slide_id in order:
        title_id = "title"
        slides.append(
            "\n".join(
                [
                    f"  - id: {slide_id}",
                    "    layout: content",
                    "    blocks:",
                    f"      - id: {title_id}",
                    "        type: text",
                    f'        text: "Judul {slide_id}"',
                    "      - id: points",
                    "        type: bullets",
                    f'        items: ["Poin {slide_id}"]',
                ]
            )
        )
    return (
        "schema: autooffice.deck/v1\n"
        'meta: {title: "Reorder", author: "Tim"}\n'
        "slides:\n" + "\n".join(slides) + "\n"
    )


def test_slide_reorder_preserves_keys() -> None:
    first = compile_deck(loads_deck(_ordered_deck(("s01", "s02"))))
    second = compile_deck(loads_deck(_ordered_deck(("s02", "s01"))))

    first_keys = {(binding.slide_id, binding.key) for binding in first.keys.bindings}
    second_keys = {(binding.slide_id, binding.key) for binding in second.keys.bindings}

    assert first_keys == second_keys
    assert "s01.title.text" in {binding.key for binding in second.keys.bindings}


def test_block_reorder_preserves_keys() -> None:
    template = """\
schema: autooffice.deck/v1
meta: {{title: "Reorder", author: "Tim"}}
slides:
  - id: s01
    layout: content
    blocks:
{blocks}
"""
    first = template.format(
        blocks=(
            '      - {id: title, type: text, text: "Judul"}\n'
            '      - {id: points, type: bullets, items: ["Poin"]}'
        )
    )
    second = template.format(
        blocks=(
            '      - {id: points, type: bullets, items: ["Poin"]}\n'
            '      - {id: title, type: text, text: "Judul"}'
        )
    )

    first_keys = set(compile_deck(loads_deck(first)).keys.keys())
    second_keys = set(compile_deck(loads_deck(second)).keys.keys())

    assert first_keys == second_keys
