"""Properti grammar key dan binding teks deck AutoOffice v1."""

import re
from collections import Counter
from collections.abc import Mapping
from io import StringIO

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ruamel.yaml import YAML

from autooffice.deck.model import (
    MAX_KEY_LENGTH,
    KeyGrammarError,
    build_coverage_plan,
    compile_deck,
    loads_deck,
    make_key,
    parse_key,
    validate_block_id,
    validate_key,
    validate_leaf,
    validate_slide_id,
)

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_WORD = st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True)
_TEXT = st.lists(_WORD, min_size=1, max_size=4).map(" ".join)
_NOTES = st.lists(_TEXT, min_size=1, max_size=3).map("\n".join)
_BLOCK_ID = st.text(alphabet=_ALPHABET + "_", min_size=1, max_size=8).map(
    lambda suffix: f"b{suffix}"
)
_VALID_BLOCK_ID = st.text(
    alphabet=_ALPHABET + "_",
    min_size=0,
    max_size=20,
).map(lambda suffix: f"b{suffix}")
_VALID_SLIDE_ID = st.integers(0, 999999).map(lambda number: f"s{number:02d}")

_INDEX_PREFIX = st.sampled_from(("item", "cat", "series", "value", "r", "c", "h"))


def _dump(data: Mapping[str, object]) -> str:
    yaml = YAML(typ="safe")
    stream = StringIO()
    yaml.dump(dict(data), stream)
    return stream.getvalue()


@st.composite
def _block(draw, block_id: str) -> dict[str, object]:
    block_type = draw(
        st.sampled_from(
            (
                "text",
                "bullets",
                "quote",
                "table",
                "chart",
                "metric",
                "code",
                "image",
                "diagram",
            )
        )
    )
    if block_type == "text":
        block: dict[str, object] = {
            "id": block_id,
            "type": "text",
            "text": draw(_TEXT),
        }
        if draw(st.booleans()):
            block["heading"] = draw(_TEXT)
        return block
    if block_type == "bullets":
        block = {
            "id": block_id,
            "type": "bullets",
            "items": [draw(_TEXT) for _ in range(draw(st.integers(1, 3)))],
        }
        if draw(st.booleans()):
            block["ordered"] = draw(st.booleans())
        return block
    if block_type == "quote":
        block = {
            "id": block_id,
            "type": "quote",
            "text": draw(_TEXT),
        }
        if draw(st.booleans()):
            block["attribution"] = draw(_TEXT)
        return block
    if block_type == "table":
        column_count = draw(st.integers(1, 3))
        block = {
            "id": block_id,
            "type": "table",
            "columns": [draw(_TEXT) for _ in range(column_count)],
            "rows": [
                [draw(_TEXT) for _ in range(column_count)] for _ in range(draw(st.integers(1, 2)))
            ],
        }
        if draw(st.booleans()):
            block["caption"] = draw(_TEXT)
        return block
    if block_type == "chart":
        kind = draw(st.sampled_from(("bar", "line", "donut")))
        category_count = draw(st.integers(2, 4 if kind == "donut" else 5))
        categories = [draw(_WORD) for _ in range(category_count)]
        series_count = 1 if kind == "donut" else draw(st.integers(1, 3))
        series = []
        for index in range(series_count):
            values = [draw(st.integers(-999, 999)) for _ in range(category_count)]
            series.append({"name": f"seri{index + 1}", "values": values})
        block = {
            "id": block_id,
            "type": "chart",
            "kind": kind,
            "title": draw(_TEXT),
            "alt": draw(_TEXT),
            "categories": categories,
            "series": series,
        }
        if draw(st.booleans()):
            block["caption"] = draw(_TEXT)
        return block
    if block_type == "metric":
        block = {
            "id": block_id,
            "type": "metric",
            "label": draw(_TEXT),
            "value": draw(_TEXT),
        }
        if draw(st.booleans()):
            block["caption"] = draw(_TEXT)
        return block
    if block_type == "code":
        block = {"id": block_id, "type": "code", "code": draw(_TEXT)}
        if draw(st.booleans()):
            block["filename"] = draw(_TEXT)
        return block
    if block_type == "image":
        block = {
            "id": block_id,
            "type": "image",
            "path": "assets/gambar.png",
            "alt": draw(_TEXT),
        }
        if draw(st.booleans()):
            block["caption"] = draw(_TEXT)
        return block
    block = {
        "id": block_id,
        "type": "diagram",
        "source": "assets/diagram.mmd",
        "alt": draw(_TEXT),
    }
    if draw(st.booleans()):
        block["caption"] = draw(_TEXT)
    return block


@st.composite
def _deck_dict(draw) -> dict[str, object]:
    numbers = draw(st.lists(st.integers(0, 999), min_size=1, max_size=3, unique=True))
    slides: list[dict[str, object]] = []
    for number in numbers:
        block_ids = draw(st.lists(_BLOCK_ID, min_size=1, max_size=3, unique=True))
        slide: dict[str, object] = {
            "id": f"s{number:02d}",
            "layout": "content",
            "blocks": [draw(_block(block_id)) for block_id in block_ids],
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
def _valid_leaf(draw) -> str:
    segment_count = draw(st.integers(1, 3))
    segments: list[str] = []
    for _ in range(segment_count):
        if draw(st.booleans()):
            prefix = draw(_INDEX_PREFIX)
            number = draw(st.integers(1, 999))
            segments.append(f"{prefix}{number}")
        else:
            suffix = draw(st.text(alphabet=_ALPHABET + "_", min_size=0, max_size=8))
            segments.append(f"f{suffix}")
    return ".".join(segments)


def _leaf_is_valid(value: str) -> bool:
    if not value:
        return False
    segments = value.split(".")
    if any(not segment for segment in segments):
        return False
    for segment in segments:
        if re.fullmatch(r"[a-z][a-z0-9_]*", segment) is None:
            return False
        indexed = re.fullmatch(
            r"(?:item|cat|series|value|r|c|h)(\d+)",
            segment,
        )
        if indexed is not None and int(indexed.group(1)) < 1:
            return False
    return True


@settings(max_examples=20, deadline=None)
@given(data=_deck_dict())
def test_visible_text_has_exactly_one_binding(data: Mapping[str, object]) -> None:
    deck = compile_deck(loads_deck(_dump(data)))
    bindings = deck.keys.bindings
    counts = Counter(binding.key for binding in bindings)

    assert counts
    assert all(count == 1 for count in counts.values())
    assert len({binding.yaml_path for binding in bindings}) == len(bindings)
    assert all(len(key) <= MAX_KEY_LENGTH for key in counts)

    plan = build_coverage_plan(deck)

    assert plan.ok
    assert plan.unkeyed_visible == ()
    assert plan.duplicate_keys == ()
    assert len(plan.visible_keys) == len(set(plan.visible_keys))
    assert set(plan.visible_keys) <= set(counts)


@settings(max_examples=60, deadline=None)
@given(
    slide_id=_VALID_SLIDE_ID,
    block_id=_VALID_BLOCK_ID,
    leaf=_valid_leaf(),
)
def test_make_key_accepts_valid_components(
    slide_id: str,
    block_id: str,
    leaf: str,
) -> None:
    key = make_key(slide_id, block_id, leaf)
    parsed = parse_key(key)

    assert len(key) <= MAX_KEY_LENGTH
    assert validate_key(key) == key
    assert parsed.key == key
    assert parsed.slide_id == slide_id
    assert parsed.block_id == block_id
    assert parsed.leaf == leaf


@settings(max_examples=30, deadline=None)
@given(
    slide_id=_VALID_SLIDE_ID,
    leaf=st.sampled_from(("notes", "source.text")),
)
def test_make_slide_key_accepts_known_leaves(slide_id: str, leaf: str) -> None:
    key = make_key(slide_id, None, leaf)
    parsed = parse_key(key)

    assert parsed.slide_id == slide_id
    assert parsed.block_id is None
    assert parsed.leaf == leaf


@settings(max_examples=40, deadline=None)
@given(slide_id=_VALID_SLIDE_ID, leaf=_valid_leaf())
def test_slide_key_rejects_block_leaves(slide_id: str, leaf: str) -> None:
    with pytest.raises(KeyGrammarError, match="Leaf slide"):
        make_key(slide_id, None, leaf)


@settings(max_examples=60, deadline=None)
@given(value=st.text(alphabet=_ALPHABET + "S_- ", min_size=0, max_size=8))
def test_slide_id_accepts_only_grammar(value: str) -> None:
    expected = re.fullmatch(r"s[0-9]{2,}", value) is not None

    if expected:
        assert validate_slide_id(value) == value
    else:
        with pytest.raises(KeyGrammarError, match="Slide ID"):
            validate_slide_id(value)


@settings(max_examples=60, deadline=None)
@given(value=st.text(alphabet=_ALPHABET + "._-A", min_size=0, max_size=36))
def test_block_id_accepts_only_grammar(value: str) -> None:
    expected = re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None and 1 <= len(value) <= 32

    if expected:
        assert validate_block_id(value) == value
    else:
        with pytest.raises(KeyGrammarError, match="Block ID"):
            validate_block_id(value)


@settings(max_examples=60, deadline=None)
@given(value=st.text(alphabet=_ALPHABET + "._-A", min_size=0, max_size=18))
def test_leaf_accepts_only_grammar(value: str) -> None:
    expected = _leaf_is_valid(value)

    if expected:
        assert validate_leaf(value) == value
    else:
        with pytest.raises(KeyGrammarError, match=r"Leaf|leaf|Indeks"):
            validate_leaf(value)


@settings(max_examples=50, deadline=None)
@given(prefix=_INDEX_PREFIX, index=st.integers(-5, 0))
def test_non_positive_indexes_are_rejected(prefix: str, index: int) -> None:
    with pytest.raises(KeyGrammarError, match=r"Indeks|Segmen"):
        validate_leaf(f"{prefix}{index}")


@settings(max_examples=40, deadline=None)
@given(prefix=_INDEX_PREFIX, zeros=st.integers(1, 3))
def test_zero_padded_indexes_are_rejected(prefix: str, zeros: int) -> None:
    with pytest.raises(KeyGrammarError, match="Indeks"):
        validate_leaf(f"{prefix}{'0' * zeros}")


@settings(max_examples=20, deadline=None)
@given(extra=st.integers(0, 8))
def test_key_length_limit_is_exact(extra: int) -> None:
    block_id = "b" + "a" * 31
    leaf = "f" + "a" * (122 + extra)
    key = f"s01.{block_id}.{leaf}"

    assert len(key) == MAX_KEY_LENGTH + extra

    if extra == 0:
        assert make_key("s01", block_id, leaf) == key
        assert validate_key(key) == key
    else:
        with pytest.raises(KeyGrammarError, match="160"):
            make_key("s01", block_id, leaf)
        with pytest.raises(KeyGrammarError, match="160"):
            validate_key(key)
