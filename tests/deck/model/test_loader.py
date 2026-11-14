"""Test loader YAML strict dan kompilasi fixture deck."""

from pathlib import Path

import pytest

from autooffice.deck.model import (
    DeckLoadError,
    compile_deck,
    load_deck,
    loads_deck,
)

_MINIMAL = """\
schema: autooffice.deck/v1
meta:
  title: "Deck Minimal"
  author: "Tim AutoOffice"
slides:
  - id: s01
    layout: content
    blocks:
      - id: title
        type: text
        role: title
        text: "Judul"
"""


def test_loads_minimal_deck() -> None:
    deck = loads_deck(_MINIMAL)

    assert deck.meta.title == "Deck Minimal"
    assert deck.meta.language == "id"
    assert deck.theme_name == "indigo"
    assert len(deck.slides) == 1
    assert deck.slides[0].slide_id == "s01"


def test_minimal_fixture_loads_and_compiles(fixture_dir: Path) -> None:
    deck = load_deck(fixture_dir / "minimal.yaml")
    ir = compile_deck(deck)

    assert ir.schema == "autooffice.deck/v1"
    assert ir.meta["title"] == "Kontrak Deck"
    assert ir.meta["language"] == "id"
    assert ir.theme_name == "indigo"
    assert ir.slides[0].layout == "content"
    assert ir.keys.keys() == (
        "s01.notes",
        "s01.source.text",
        "s01.title.text",
        "s01.title.heading",
        "s01.points.item1.text",
        "s01.points.item2.text",
    )


def test_loads_deck_accepts_text_with_base_dir(tmp_path: Path) -> None:
    deck = loads_deck(_MINIMAL, base_dir=tmp_path)

    assert deck.slides[0].layout == "content"


def test_loader_rejects_duplicate_yaml_mapping_key() -> None:
    text = """\
schema: autooffice.deck/v1
schema: autooffice.deck/v1
meta:
  title: "Deck"
  author: "Tim"
slides: []
"""

    with pytest.raises(DeckLoadError, match="YAML tidak valid"):
        loads_deck(text)


def test_loader_rejects_custom_yaml_tag() -> None:
    text = """\
schema: !!python/object:builtins.object {}
meta:
  title: "Deck"
  author: "Tim"
slides: []
"""

    with pytest.raises(DeckLoadError, match="YAML tidak valid"):
        loads_deck(text)


def test_loader_rejects_multiple_yaml_documents() -> None:
    text = """\
---
schema: autooffice.deck/v1
---
schema: autooffice.deck/v1
"""

    with pytest.raises(DeckLoadError, match="tepat satu dokumen"):
        loads_deck(text)


def test_loader_rejects_empty_yaml() -> None:
    with pytest.raises(DeckLoadError, match="tepat satu dokumen"):
        loads_deck("")


def test_loader_rejects_non_mapping_root() -> None:
    with pytest.raises(DeckLoadError, match="mapping"):
        loads_deck("- satu\n- dua\n")


def test_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DeckLoadError, match="tidak ditemukan"):
        load_deck(tmp_path / "missing.yaml")


def test_loader_rejects_non_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(DeckLoadError, match="UTF-8"):
        load_deck(path)


def test_loader_rejects_schema_error_through_load(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_text("schema: autooffice.deck/v1\nslides: []\n", encoding="utf-8")

    with pytest.raises(DeckLoadError, match="meta"):
        load_deck(path)
