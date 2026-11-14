"""Test edge case loader YAML: BOM, dokumen null, error baca, dan delegasi."""

from pathlib import Path

import pytest

from autooffice.deck.model import DeckLoadError, load_deck, load_deck_object, loads_deck

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


def test_loads_deck_rejects_non_string_input() -> None:
    with pytest.raises(DeckLoadError, match="harus string"):
        loads_deck(1)  # type: ignore[arg-type]


def test_loads_deck_rejects_null_document() -> None:
    with pytest.raises(DeckLoadError, match="tidak boleh kosong"):
        loads_deck("---\n")


def test_loads_deck_accepts_bom_prefixed_text() -> None:
    deck = loads_deck("\ufeff" + _MINIMAL)

    assert deck.meta.title == "Deck Minimal"


def test_load_deck_accepts_utf8_bom_file(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_bytes(b"\xef\xbb\xbf" + _MINIMAL.encode("utf-8"))

    assert load_deck(path).meta.author == "Tim AutoOffice"


def test_load_deck_wraps_read_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "deck.yaml"
    path.write_text(_MINIMAL, encoding="utf-8")

    def _raise_os_error(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr(Path, "open", _raise_os_error)

    with pytest.raises(DeckLoadError, match="tidak dapat dibaca"):
        load_deck(path)


def test_load_deck_object_validates_mapping() -> None:
    deck = load_deck_object(
        {
            "schema": "autooffice.deck/v1",
            "meta": {"title": "Dari Objek", "author": "Tim"},
            "slides": [
                {
                    "id": "s01",
                    "layout": "content",
                    "blocks": [{"id": "title", "type": "text", "text": "Judul"}],
                }
            ],
        }
    )

    assert deck.meta.title == "Dari Objek"
    assert deck.slides[0].slide_id == "s01"


def test_loader_rejects_malformed_yaml_flow_mapping() -> None:
    with pytest.raises(DeckLoadError, match="YAML tidak valid"):
        loads_deck("schema: [\n")


def test_loader_rejects_duplicate_nested_mapping_key() -> None:
    text = """\
schema: autooffice.deck/v1
meta:
  title: "Deck A"
  title: "Deck B"
  author: "Tim"
slides: []
"""

    with pytest.raises(DeckLoadError, match="YAML tidak valid"):
        loads_deck(text)
