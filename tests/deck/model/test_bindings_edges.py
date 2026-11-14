"""Test edge branch pembentukan binding dan validasi field."""

import pytest

from autooffice.deck.model import (
    BlockDefinition,
    ChartSeries,
    KeyBinding,
    KeyGrammarError,
    block_bindings,
    build_key_manifest,
    loads_deck,
    number_text,
)
from autooffice.deck.model.bindings import (
    _inline_binding,
    _plain_binding,
    _preserve_binding,
)


def _block(block_type: str, *, block_id: str = "b1", **fields: object) -> BlockDefinition:
    return BlockDefinition(
        block_id=block_id,
        block_type=block_type,
        span=None,
        role=None,
        fields=fields,
    )


def _bindings_for(block: BlockDefinition, *, slide_id: str = "s01") -> tuple[KeyBinding, ...]:
    return block_bindings(
        block,
        slide_id=slide_id,
        yaml_base=("slides", 0, "blocks", 0),
    )


def test_build_key_manifest_validates_and_returns_manifest() -> None:
    deck = loads_deck(
        """\
schema: autooffice.deck/v1
meta: {title: "Manifest", author: "Tim"}
slides:
  - id: s01
    layout: content
    blocks:
      - {id: title, type: text, text: "Judul"}
"""
    )

    manifest = build_key_manifest(deck)

    assert manifest.keys() == ("s01.title.text",)


def test_number_text_formats_integer_and_float_values() -> None:
    assert number_text(7) == "7"
    assert number_text(2.0) == "2"
    assert number_text(2.5) == "2.5"


def test_blocks_without_optional_fields_emit_only_required_bindings() -> None:
    cases: tuple[tuple[BlockDefinition, tuple[str, ...]], ...] = (
        (_block("text", block_id="text1", text="Isi"), ("s01.text1.text",)),
        (_block("bullets", block_id="points", items=("Satu",)), ("s01.points.item1.text",)),
        (_block("image", block_id="image1", path="a.png", alt="Alt", fit="cover"), ()),
        (
            _block("table", block_id="table1", columns=("A",), rows=(("1",),)),
            ("s01.table1.h1", "s01.table1.r1.c1"),
        ),
        (
            _block(
                "chart",
                block_id="chart1",
                title="Judul",
                categories=("A",),
                series=(ChartSeries(name="S", values=(1,)),),
            ),
            (
                "s01.chart1.title",
                "s01.chart1.cat1",
                "s01.chart1.series1.name",
                "s01.chart1.series1.value1",
            ),
        ),
        (_block("code", block_id="code1", code="print(1)"), ("s01.code1.code",)),
        (_block("quote", block_id="quote1", text="Kutipan"), ("s01.quote1.text",)),
        (_block("diagram", block_id="diagram1", source="a.mmd", alt="Alt"), ()),
        (
            _block("metric", block_id="metric1", label="Label", value="1"),
            ("s01.metric1.label", "s01.metric1.value"),
        ),
        (_block("divider", block_id="line1"), ()),
        (_block("spacer", block_id="gap1", size="md"), ()),
    )

    for block, expected_keys in cases:
        actual = tuple(binding.key for binding in _bindings_for(block))
        assert actual == expected_keys


def test_binding_kinds_and_sync_flags_follow_contract() -> None:
    code = _block("code", block_id="code1", code="print(1)", filename="a.py")
    quote = _block("quote", block_id="quote1", text="Kutipan", attribution="Tim")
    chart = _block(
        "chart",
        block_id="chart1",
        title="Judul",
        categories=("A",),
        series=(ChartSeries(name="S", values=(1.5,)),),
    )
    bindings = {
        binding.key: binding for block in (code, quote, chart) for binding in _bindings_for(block)
    }

    assert bindings["s01.code1.code"].kind == "text"
    assert bindings["s01.code1.code"].sync is True
    assert bindings["s01.code1.filename"].kind == "text"
    assert bindings["s01.code1.filename"].sync is True
    assert bindings["s01.quote1.text"].kind == "text"
    assert bindings["s01.quote1.text"].sync is True
    assert bindings["s01.quote1.attribution"].kind == "text"
    assert bindings["s01.chart1.title"].kind == "text"
    assert bindings["s01.chart1.title"].sync is False
    assert bindings["s01.chart1.cat1"].sync is False
    assert bindings["s01.chart1.series1.name"].sync is False
    assert bindings["s01.chart1.series1.value1"].kind == "data"
    assert bindings["s01.chart1.series1.value1"].sync is False


def test_unknown_block_type_is_rejected() -> None:
    with pytest.raises(KeyGrammarError, match="tanpa binding"):
        _bindings_for(_block("mystery", block_id="mystery1"))


@pytest.mark.parametrize(
    ("block", "match"),
    [
        (_block("text", text=123), "Field 'text' harus string"),
        (_block("bullets", items=["Satu"]), "Field 'items' harus tuple string"),
        (_block("bullets", items=("Satu", 1)), "Field 'items' harus tuple string"),
        (
            _block("table", columns=("A",), rows=["1"]),
            "Field 'rows' harus tuple baris string",
        ),
        (
            _block("table", columns=("A",), rows=(["1"],)),
            "Field 'rows' harus tuple baris string",
        ),
        (
            _block("table", columns=("A",), rows=(("1", 1),)),
            "Field 'rows' harus tuple baris string",
        ),
        (
            _block("chart", title="Judul", categories=("A",), series=["S"]),
            "Field 'series' harus tuple ChartSeries",
        ),
        (
            _block("chart", title="Judul", categories=("A",), series=(("S", (1,)),)),
            "Field 'series' harus tuple ChartSeries",
        ),
    ],
)
def test_binding_field_shape_errors_are_reported(block: BlockDefinition, match: str) -> None:
    with pytest.raises(KeyGrammarError, match=match):
        _bindings_for(block)


def test_inline_binding_rejects_non_inline_kind() -> None:
    with pytest.raises(KeyGrammarError, match="Binding inline"):
        _inline_binding(
            slide_id="s01",
            block_id="b1",
            leaf="text",
            kind="data",
            raw="Isi",
            yaml_path=("slides", 0, "blocks", 0, "text"),
        )


def test_plain_binding_rejects_non_text_kind() -> None:
    with pytest.raises(KeyGrammarError, match="Binding plain"):
        _plain_binding(
            slide_id="s01",
            block_id="b1",
            leaf="title",
            kind="data",
            sync=False,
            value="Judul",
            yaml_path=("slides", 0, "blocks", 0, "title"),
        )


def test_preserve_binding_rejects_non_preserve_kind() -> None:
    with pytest.raises(KeyGrammarError, match="Binding preserve"):
        _preserve_binding(
            slide_id="s01",
            block_id="b1",
            leaf="code",
            kind="data",
            value="print(1)",
            yaml_path=("slides", 0, "blocks", 0, "code"),
        )
