"""Test compiler deterministik, IR, dan batas import model."""

from pathlib import Path

import pytest

from autooffice.deck.model import (
    DeckSchemaError,
    compile_deck,
    compile_deck_file,
    load_deck,
    loads_deck,
)

_MODEL_DIR = Path(__file__).resolve().parents[3] / "src" / "autooffice" / "deck" / "model"


def _signature(deck) -> tuple[object, ...]:
    return tuple(
        (
            slide.slide_id,
            slide.layout,
            slide.order,
            slide.notes,
            tuple(sorted(slide.source.items())) if slide.source is not None else None,
            slide.rows,
            tuple(
                (block.block_id, block.block_type, block.span, block.role, block.fields)
                for block in slide.blocks
            ),
        )
        for slide in deck.slides
    )


def test_compile_is_deterministic(fixture_dir: Path) -> None:
    path = fixture_dir / "all-blocks.yaml"
    first = compile_deck(load_deck(path))
    second = compile_deck(load_deck(path))

    assert first.keys == second.keys
    assert _signature(first) == _signature(second)


def test_compile_file_matches_load_and_compile(fixture_dir: Path) -> None:
    path = fixture_dir / "minimal.yaml"
    direct = compile_deck_file(path)
    loaded = compile_deck(load_deck(path))

    assert direct.keys == loaded.keys


def test_compile_custom_rows_flattens_in_order(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "custom-grid.yaml"))

    assert tuple(block.block_id for block in deck.slides[0].blocks) == (
        "eyebrow",
        "title",
        "lead",
        "chart2",
        "insight",
    )


def test_compile_custom_rows_match_authoring_order(fixture_dir: Path) -> None:
    slide = compile_deck(load_deck(fixture_dir / "custom-grid.yaml")).slides[0]

    assert slide.rows == (
        ("eyebrow",),
        ("title", "lead"),
        ("chart2", "insight"),
    )
    assert tuple(block_id for row in slide.rows for block_id in row) == tuple(
        block.block_id for block in slide.blocks
    )


def test_compile_preset_slides_keep_empty_rows(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))

    assert tuple(slide.rows for slide in deck.slides) == ((),)


def test_compile_preserves_source_and_notes(fixture_dir: Path) -> None:
    slide = compile_deck(load_deck(fixture_dir / "minimal.yaml")).slides[0]

    assert slide.notes == (
        "Catatan pembicara untuk slide pertama.\nBaris kedua tetap dipertahankan."
    )
    assert slide.source is not None
    assert slide.source["text"] == "Sumber: data internal, 2026"
    assert slide.source["url"] == "https://example.com/data"


def test_meta_language_is_normalized_in_ir(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))

    assert deck.meta["language"] == "en"


def test_slide_order_matches_compiled_index(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))

    assert tuple(slide.order for slide in deck.slides) == (0,)


def test_compiler_rejects_block_id_source_collision() -> None:
    text = """\
schema: autooffice.deck/v1
meta: {title: "Duplicate", author: "Tim"}
slides:
  - id: s01
    layout: content
    source: {text: "Sumber"}
    blocks:
      - {id: source, type: text, text: "Teks"}
"""

    with pytest.raises(DeckSchemaError, match=r"source\.text"):
        compile_deck(loads_deck(text))


def test_compiler_rejects_custom_block_id_source_collision() -> None:
    text = """\
schema: autooffice.deck/v1
meta: {title: "Custom", author: "Tim"}
slides:
  - id: s01
    layout: custom
    rows:
      - blocks:
          - {id: source, type: text, text: "Teks", span: 12}
"""

    with pytest.raises(DeckSchemaError, match=r"source\.text"):
        compile_deck(loads_deck(text))


def test_model_modules_do_not_import_renderer_google_pptx_or_com() -> None:
    forbidden = (
        "autooffice.deck.render",
        "autooffice.google",
        "python-pptx",
        "import pptx",
        "win32com",
    )

    for path in sorted(_MODEL_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{path.name} memuat {marker}"
