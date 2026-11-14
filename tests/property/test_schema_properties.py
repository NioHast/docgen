"""Properti schema dan compiler deck AutoOffice v1."""

from collections.abc import Mapping
from io import StringIO

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ruamel.yaml import YAML

from autooffice.deck.model import (
    DeckSchemaError,
    compile_deck,
    loads_deck,
    validate_deck,
)

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_WORD = st.from_regex(r"[a-z0-9]{1,8}", fullmatch=True)
_TEXT = st.lists(_WORD, min_size=1, max_size=4).map(" ".join)
_NOTES = st.lists(_TEXT, min_size=1, max_size=3).map("\n".join)
_BLOCK_ID = st.text(alphabet=_ALPHABET + "_", min_size=1, max_size=10).map(
    lambda suffix: f"b{suffix}"
)


def _dump(data: Mapping[str, object]) -> str:
    yaml = YAML(typ="safe")
    stream = StringIO()
    yaml.dump(dict(data), stream)
    return stream.getvalue()


@st.composite
def _deck_dict(
    draw: st.DrawFn,
    *,
    min_slides: int = 1,
    max_slides: int = 4,
) -> dict[str, object]:
    slide_count = draw(st.integers(min_slides, max_slides))
    numbers = draw(
        st.lists(
            st.integers(0, 9999),
            min_size=slide_count,
            max_size=slide_count,
            unique=True,
        )
    )
    slides: list[dict[str, object]] = []
    for number in numbers:
        block_ids = draw(st.lists(_BLOCK_ID, min_size=1, max_size=3, unique=True))
        blocks = [{"id": block_id, "type": "text", "text": draw(_TEXT)} for block_id in block_ids]
        slide: dict[str, object] = {
            "id": f"s{number:02d}",
            "layout": "content",
            "blocks": blocks,
        }
        if draw(st.booleans()):
            slide["notes"] = draw(_NOTES)
        if draw(st.booleans()):
            slide["source"] = {"text": draw(_TEXT)}
        slides.append(slide)
    return {
        "schema": "autooffice.deck/v1",
        "meta": {"title": draw(_TEXT), "author": draw(_TEXT)},
        "slides": slides,
    }


@st.composite
def _reordered_decks(
    draw: st.DrawFn,
) -> tuple[dict[str, object], dict[str, object]]:
    deck = draw(_deck_dict(min_slides=2))
    slides = list(deck["slides"])
    order = draw(st.permutations(range(len(slides))))
    reordered = {**deck, "slides": [slides[index] for index in order]}
    return deck, reordered


def _binding_signature(deck: object) -> dict[str, tuple[object, ...]]:
    return {
        binding.key: (
            binding.slide_id,
            binding.block_id,
            binding.leaf,
            binding.kind,
            binding.sync,
            binding.value,
            binding.plain_text,
        )
        for binding in deck.keys.bindings
    }


def _text_slide(slide_id: str, block_ids: tuple[str, ...]) -> dict[str, object]:
    return {
        "id": slide_id,
        "layout": "content",
        "blocks": [{"id": block_id, "type": "text", "text": "Isi slide"} for block_id in block_ids],
    }


def _image_deck(path: str) -> dict[str, object]:
    return {
        "schema": "autooffice.deck/v1",
        "meta": {"title": "Path", "author": "Tim"},
        "slides": [
            {
                "id": "s01",
                "layout": "content",
                "blocks": [
                    {
                        "id": "image1",
                        "type": "image",
                        "path": path,
                        "alt": "Gambar uji",
                    }
                ],
            }
        ],
    }


@settings(max_examples=15, deadline=None)
@given(data=_deck_dict())
def test_generated_decks_compile_deterministically(data: Mapping[str, object]) -> None:
    text = _dump(data)

    first = compile_deck(loads_deck(text))
    second = compile_deck(loads_deck(text))

    assert first == second
    assert first.keys.keys() == second.keys.keys()
    assert first.meta["title"] == data["meta"]["title"]
    assert tuple(slide.notes for slide in first.slides) == tuple(
        slide.get("notes") for slide in data["slides"]
    )


@settings(max_examples=20, deadline=None)
@given(decks=_reordered_decks())
def test_slide_reorder_preserves_keys(
    decks: tuple[dict[str, object], dict[str, object]],
) -> None:
    original, reordered = decks

    first = compile_deck(loads_deck(_dump(original)))
    second = compile_deck(loads_deck(_dump(reordered)))

    assert set(first.keys.keys()) == set(second.keys.keys())
    assert _binding_signature(first) == _binding_signature(second)
    assert [slide.slide_id for slide in first.slides] == [
        slide["id"] for slide in original["slides"]
    ]
    assert [slide.slide_id for slide in second.slides] == [
        slide["id"] for slide in reordered["slides"]
    ]


@settings(max_examples=50, deadline=None)
@given(
    number=st.integers(0, 9999),
    block_id=_BLOCK_ID,
)
def test_duplicate_slide_ids_are_rejected(number: int, block_id: str) -> None:
    slide_id = f"s{number:02d}"
    deck = {
        "schema": "autooffice.deck/v1",
        "meta": {"title": "Duplikat", "author": "Tim"},
        "slides": [
            _text_slide(slide_id, (block_id,)),
            _text_slide(slide_id, (f"b{block_id}",)),
        ],
    }

    with pytest.raises(DeckSchemaError, match="duplikat"):
        validate_deck(deck)


@settings(max_examples=50, deadline=None)
@given(number=st.integers(0, 9999), block_id=_BLOCK_ID)
def test_duplicate_block_ids_are_rejected(number: int, block_id: str) -> None:
    deck = {
        "schema": "autooffice.deck/v1",
        "meta": {"title": "Duplikat", "author": "Tim"},
        "slides": [_text_slide(f"s{number:02d}", (block_id, block_id))],
    }

    with pytest.raises(DeckSchemaError, match="duplikat"):
        validate_deck(deck)


_TRAVERSAL_PATH = st.one_of(
    st.integers(1, 3).map(lambda depth: "../" * depth + "hero.png"),
    st.integers(1, 2).map(lambda depth: "assets/" + "../" * depth + "hero.png"),
    st.sampled_from(
        (
            "..\\hero.png",
            "/hero.png",
            "C:/hero.png",
            "assets/../hero.png",
            "./hero.png",
            "assets//hero.png",
            "https://example.com/hero.png",
            "a/./b.png",
            "a/../../b.png",
        )
    ),
)


@settings(max_examples=40, deadline=None)
@given(path=_TRAVERSAL_PATH)
def test_path_traversal_is_always_rejected(path: str) -> None:
    with pytest.raises(DeckSchemaError, match="path"):
        validate_deck(_image_deck(path))
