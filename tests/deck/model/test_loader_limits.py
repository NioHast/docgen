"""Tes batas keamanan berkas YAML deck."""

import io
from pathlib import Path

import pytest

from autooffice.deck.model import DeckLoadError, load_deck, loads_deck
from autooffice.deck.model import loader as loader_module
from autooffice.deck.model.loader import (
    MAX_DECK_ALIASES,
    MAX_DECK_BYTES,
    MAX_DECK_NESTING_DEPTH,
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

_DEMO_DECK = Path(__file__).resolve().parents[3] / "examples" / "demo-deck" / "deck.yaml"


def test_loads_deck_rejects_text_over_size_limit() -> None:
    text = _MINIMAL + "#" * (MAX_DECK_BYTES + 1)

    with pytest.raises(DeckLoadError, match="melebihi batas"):
        loads_deck(text)


def test_load_deck_rejects_file_over_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "deck.yaml"
    path.write_bytes(_MINIMAL.encode("utf-8") + b"#" * (MAX_DECK_BYTES + 1))

    with pytest.raises(DeckLoadError, match="melebihi batas"):
        load_deck(path)


def test_load_deck_reads_at_most_limit_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deck.yaml"
    path.write_bytes(_MINIMAL.encode("utf-8") + b"#" * (MAX_DECK_BYTES + 1024))

    class _TrackingReader(io.BytesIO):
        def __init__(self, data: bytes) -> None:
            super().__init__(data)
            self.read_sizes: list[int] = []

        def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            return super().read(size)

    reader = _TrackingReader(path.read_bytes())

    def _open(*_args: object, **_kwargs: object) -> _TrackingReader:
        return reader

    monkeypatch.setattr(Path, "open", _open)

    with pytest.raises(DeckLoadError, match="melebihi batas"):
        load_deck(path)

    assert reader.read_sizes == [MAX_DECK_BYTES + 1]


def test_loads_deck_rejects_multiple_documents() -> None:
    with pytest.raises(DeckLoadError, match="tepat satu dokumen"):
        loads_deck(_MINIMAL + "---\n" + _MINIMAL)


def test_loads_deck_accepts_small_alias_count() -> None:
    text = _MINIMAL.replace(
        'title: "Deck Minimal"',
        'title: &judul "Deck Minimal"',
    ).replace('author: "Tim AutoOffice"', "author: *judul")

    deck = loads_deck(text)

    assert deck.meta.author == "Deck Minimal"


def test_loads_deck_rejects_multibyte_text_over_size_limit() -> None:
    text = "é" * (MAX_DECK_BYTES // 2 + 1)

    with pytest.raises(DeckLoadError, match="melebihi batas"):
        loads_deck(text)


def test_loads_deck_rejects_alias_count_over_limit() -> None:
    lines = [_MINIMAL, "anchor: &a nilai", "aliases:"]
    lines.extend("  - *a" for _ in range(MAX_DECK_ALIASES + 1))

    with pytest.raises(DeckLoadError, match="alias YAML"):
        loads_deck("\n".join(lines))


def _deep_yaml() -> str:
    lines = [_MINIMAL, "deep:"]
    for index in range(MAX_DECK_NESTING_DEPTH + 1):
        lines.append("  " * (index + 1) + f"level{index}:")
    lines.append("  " * (MAX_DECK_NESTING_DEPTH + 2) + "value")
    return "\n".join(lines)


def test_loads_deck_rejects_nesting_over_limit() -> None:
    with pytest.raises(DeckLoadError, match="kedalaman struktur YAML"):
        loads_deck(_deep_yaml())


def test_loads_deck_depth_cap_uses_pure_python_yaml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    real_yaml = loader_module.YAML

    def _yaml(*args: object, **kwargs: object) -> object:
        calls.append(dict(kwargs))
        return real_yaml(*args, **kwargs)

    monkeypatch.setattr(loader_module, "YAML", _yaml)

    with pytest.raises(DeckLoadError, match="kedalaman struktur YAML"):
        loads_deck(_deep_yaml())

    assert calls
    assert all(call.get("pure") is True for call in calls)
    assert all(call.get("typ") == "safe" for call in calls)


def test_load_deck_accepts_demo_deck() -> None:
    deck = load_deck(_DEMO_DECK)

    assert deck.meta.title == "Demo Design System AutoOffice"
    assert len(deck.slides) == 24
