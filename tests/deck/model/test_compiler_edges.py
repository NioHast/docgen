"""Test edge case compiler: deck kosong, ID duplikat, field opsional, dan field cacat."""

import json
from pathlib import Path

import pytest

import autooffice.deck.model.compiler as compiler_module
from autooffice.deck.model import (
    BlockDefinition,
    ChartSeries,
    DeckDefaults,
    DeckDefinition,
    DeckMeta,
    DeckSchemaError,
    SlideDefinition,
    SourceDefinition,
    compile_deck,
    compile_deck_file,
    compile_file,
    loads_deck,
)


def _block(
    block_type: str,
    fields: dict[str, object],
    *,
    block_id: str = "block1",
) -> BlockDefinition:
    return BlockDefinition(
        block_id=block_id,
        block_type=block_type,
        span=None,
        role=None,
        fields=fields,
    )


def _slide(
    *blocks: BlockDefinition,
    slide_id: str = "s01",
    layout: str = "content",
    notes: str | None = None,
    source: SourceDefinition | None = None,
) -> SlideDefinition:
    return SlideDefinition(
        slide_id=slide_id,
        layout=layout,
        notes=notes,
        source=source,
        blocks=blocks,
        rows=(),
    )


def _definition(*slides: SlideDefinition) -> DeckDefinition:
    return DeckDefinition(
        schema="autooffice.deck/v1",
        meta=DeckMeta(title="Edge Deck", author="Tim AutoOffice"),
        theme_name="indigo",
        defaults=DeckDefaults(),
        slides=slides,
    )


def test_compile_rejects_empty_deck() -> None:
    with pytest.raises(DeckSchemaError, match="minimal satu slide"):
        compile_deck(_definition())


def test_compile_rejects_duplicate_slide_id_with_context() -> None:
    definition = _definition(_slide(slide_id="s01"), _slide(slide_id="s01"))

    with pytest.raises(DeckSchemaError, match="duplikat") as error:
        compile_deck(definition)

    assert error.value.slide_id == "s01"


def test_compile_file_alias_matches_compile_deck_file(fixture_dir: Path) -> None:
    path = fixture_dir / "minimal.yaml"

    assert compile_file(path).keys == compile_deck_file(path).keys


def test_compile_keeps_table_caption_and_emphasis_column() -> None:
    block = _block(
        "table",
        {
            "columns": ("Lane", "Status"),
            "rows": (("Model", "Selesai"),),
            "caption": "**Status** lane",
            "emphasis_column": 2,
        },
        block_id="table1",
    )

    compiled = compile_deck(_definition(_slide(block))).slides[0].blocks[0]

    assert compiled.fields["caption"] == "Status lane"
    assert compiled.fields["emphasis_column"] == 2


def test_compile_omits_optional_fields_when_absent() -> None:
    blocks = (
        _block("text", {"text": "Teks"}, block_id="text1"),
        _block(
            "table",
            {"columns": ("A", "B"), "rows": (("1", "2"),)},
            block_id="table1",
        ),
        _block(
            "chart",
            {
                "kind": "line",
                "title": "Judul",
                "alt": "Alt chart",
                "categories": ("Q1", "Q2"),
                "series": (ChartSeries("Satu", (1, 2)),),
            },
            block_id="chart1",
        ),
        _block(
            "code",
            {"code": "print(1)", "language": "python", "line_numbers": True},
            block_id="code1",
        ),
        _block("quote", {"text": "Kutipan"}, block_id="quote1"),
        _block("image", {"path": "a.png", "alt": "Alt", "fit": "contain"}, block_id="image1"),
        _block("diagram", {"source": "a.mmd", "alt": "Alt"}, block_id="diagram1"),
        _block(
            "metric",
            {"label": "Label", "value": "1", "status": "neutral"},
            block_id="metric1",
        ),
    )

    slides = compile_deck(_definition(_slide(*blocks))).slides
    compiled = {block.block_id: block for block in slides[0].blocks}

    assert "heading" not in compiled["text1"].fields
    assert "caption" not in compiled["table1"].fields
    assert "emphasis_column" not in compiled["table1"].fields
    assert "orientation" not in compiled["chart1"].fields
    assert "unit" not in compiled["chart1"].fields
    assert "caption" not in compiled["chart1"].fields
    assert "filename" not in compiled["code1"].fields
    assert "attribution" not in compiled["quote1"].fields
    assert "caption" not in compiled["image1"].fields
    assert "caption" not in compiled["diagram1"].fields
    assert "caption" not in compiled["metric1"].fields


def test_compile_source_without_url_keeps_text_only() -> None:
    slide = _slide(source=SourceDefinition(text="Sumber internal"))

    compiled = compile_deck(_definition(slide)).slides[0]

    assert dict(compiled.source or {}) == {"text": "Sumber internal"}
    assert compiled.notes is None


def _public_deck_yaml(block_type: str, fields: dict[str, object]) -> str:
    """Deck YAML minimal yang melewati loader dan schema publik."""
    return json.dumps(
        {
            "schema": "autooffice.deck/v1",
            "meta": {"title": "Edge Deck", "author": "Tim AutoOffice"},
            "slides": [
                {
                    "id": "s01",
                    "layout": "content",
                    "blocks": [{"id": "block1", "type": block_type, **fields}],
                }
            ],
        }
    )


@pytest.mark.parametrize(
    ("block_type", "fields", "match"),
    [
        ("mystery", {}, "Block type 'mystery' tidak dikenal"),
        ("text", {"text": 1}, "text harus string"),
        (
            "bullets",
            {"items": ["Satu"], "ordered": "ya"},
            "ordered harus boolean",
        ),
        (
            "table",
            {"columns": ["A"], "rows": [["1"]], "emphasis_column": "2"},
            "emphasis_column harus bilangan bulat",
        ),
        (
            "table",
            {"columns": ["A"], "rows": [["1"]], "emphasis_column": True},
            "emphasis_column harus bilangan bulat",
        ),
        ("bullets", {"items": ["Satu", 2]}, r"items\[1\] harus string"),
        ("table", {"columns": ["A"], "rows": [[1]]}, r"rows\[0\]\[0\] harus string"),
        (
            "chart",
            {
                "kind": "bar",
                "title": "Judul",
                "alt": "Alt",
                "categories": ["Q1", "Q2"],
                "series": [],
            },
            "minimal satu seri",
        ),
        (
            "chart",
            {
                "kind": "bar",
                "title": "Judul",
                "alt": "Alt",
                "categories": ["Q1", "Q2"],
                "series": ["bukan-series"],
            },
            "chart series harus mapping",
        ),
    ],
)
def test_compile_from_public_loader_rejects_malformed_block_fields(
    block_type: str,
    fields: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(DeckSchemaError, match=match):
        compile_deck(loads_deck(_public_deck_yaml(block_type, fields)))


@pytest.mark.parametrize(
    ("block_type", "fields", "match"),
    [
        ("bullets", {"items": ["Satu"]}, "harus tuple string"),
        ("bullets", {"items": ("Satu", 2)}, "harus tuple string"),
        ("table", {"columns": ("A",), "rows": [("1",)]}, "harus tuple baris string"),
        ("table", {"columns": ("A",), "rows": (["1"],)}, "harus tuple baris string"),
        ("table", {"columns": ("A",), "rows": ((1,),)}, "harus tuple baris string"),
        (
            "chart",
            {
                "kind": "bar",
                "title": "Judul",
                "alt": "Alt",
                "categories": ("Q1", "Q2"),
                "series": [],
            },
            "harus tuple ChartSeries",
        ),
        (
            "chart",
            {
                "kind": "bar",
                "title": "Judul",
                "alt": "Alt",
                "categories": ("Q1", "Q2"),
                "series": ("bukan-series",),
            },
            "harus tuple ChartSeries",
        ),
    ],
)
def test_defensive_compile_rejects_non_tuple_ir_fields(
    monkeypatch: pytest.MonkeyPatch,
    block_type: str,
    fields: dict[str, object],
    match: str,
) -> None:
    """Guard tipe internal compiler untuk IR yang dibangun di luar jalur publik.

    ``loads_deck`` menormalkan list YAML menjadi tuple dan memvalidasi isi
    field, sehingga bentuk non-tuple di sini hanya dapat muncul dari pemanggil
    internal yang membangun ``DeckDefinition`` langsung. Binding sengaja
    dilewati agar guard compiler sendiri yang diuji, bukan guard di modul
    binding.
    """
    monkeypatch.setattr(compiler_module, "build_bindings", lambda _definition: ())
    block = _block(block_type, fields)

    with pytest.raises(DeckSchemaError, match=match):
        compile_deck(_definition(_slide(block)))
