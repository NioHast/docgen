"""Test seluruh block type dan default authoring."""

from pathlib import Path

from autooffice.deck.model import compile_deck, load_deck, loads_deck

EXPECTED_TYPES = (
    "text",
    "bullets",
    "image",
    "table",
    "chart",
    "code",
    "quote",
    "diagram",
    "divider",
    "spacer",
    "metric",
)


def _all_blocks_ir(fixture_dir: Path):
    return compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))


def test_all_eleven_block_types_compile(fixture_dir: Path) -> None:
    deck = _all_blocks_ir(fixture_dir)

    assert tuple(block.block_type for block in deck.slides[0].blocks) == EXPECTED_TYPES


def test_all_block_keys_are_present(fixture_dir: Path) -> None:
    keys = set(_all_blocks_ir(fixture_dir).keys.keys())

    expected = {
        "s01.title.text",
        "s01.points.item1.text",
        "s01.points.item2.text",
        "s01.image1.caption",
        "s01.table1.h1",
        "s01.table1.r1.c2",
        "s01.table1.caption",
        "s01.chart1.title",
        "s01.chart1.cat1",
        "s01.chart1.cat2",
        "s01.chart1.cat3",
        "s01.chart1.cat4",
        "s01.chart1.series1.name",
        "s01.chart1.series1.value1",
        "s01.chart1.series2.value4",
        "s01.chart1.caption",
        "s01.snippet.code",
        "s01.snippet.filename",
        "s01.quote1.text",
        "s01.quote1.attribution",
        "s01.process.caption",
        "s01.kpi1.label",
        "s01.kpi1.value",
        "s01.kpi1.caption",
    }

    assert expected <= keys


def test_divider_and_spacer_have_no_keys(fixture_dir: Path) -> None:
    keys = set(_all_blocks_ir(fixture_dir).keys.keys())

    assert not {key for key in keys if key.startswith("s01.line1.")}
    assert not {key for key in keys if key.startswith("s01.gap1.")}


def test_block_defaults_are_resolved(fixture_dir: Path) -> None:
    blocks = {block.block_id: block for block in _all_blocks_ir(fixture_dir).slides[0].blocks}

    assert blocks["points"].fields["ordered"] is True
    assert blocks["image1"].fields["fit"] == "cover"
    assert blocks["table1"].fields["columns"] == ("Lane", "Status")
    assert blocks["snippet"].fields["language"] == "python"
    assert blocks["snippet"].fields["line_numbers"] is True
    assert blocks["gap1"].fields["size"] == "md"
    assert blocks["kpi1"].fields["status"] == "success"


def test_line_chart_has_no_orientation_field(fixture_dir: Path) -> None:
    blocks = {block.block_id: block for block in _all_blocks_ir(fixture_dir).slides[0].blocks}

    assert "orientation" not in blocks["chart1"].fields


def test_bar_chart_defaults_to_vertical_orientation(fixture_dir: Path) -> None:
    blocks = {
        block.block_id: block
        for block in compile_deck(load_deck(fixture_dir / "custom-grid.yaml")).slides[0].blocks
    }

    assert blocks["chart2"].fields["orientation"] == "vertical"


def test_code_keeps_internal_newlines_and_spacing(fixture_dir: Path) -> None:
    blocks = {block.block_id: block for block in _all_blocks_ir(fixture_dir).slides[0].blocks}
    code = blocks["snippet"].fields["code"]

    assert code == (
        'def key(slide_id: str, block_id: str) -> str:\n    return f"{slide_id}.{block_id}.text"'
    )


def test_inline_markdown_is_normalized_in_ir_fields(fixture_dir: Path) -> None:
    blocks = {block.block_id: block for block in _all_blocks_ir(fixture_dir).slides[0].blocks}

    assert blocks["points"].fields["items"] == (
        "Teks dengan bold.",
        "Teks dengan inline code.",
    )


def test_binding_kinds_and_sync_flags(fixture_dir: Path) -> None:
    bindings = {binding.key: binding for binding in _all_blocks_ir(fixture_dir).keys.bindings}

    assert bindings["s01.image1.caption"].kind == "media_text"
    assert bindings["s01.chart1.title"].kind == "text"
    assert bindings["s01.chart1.title"].sync is False
    assert bindings["s01.chart1.series1.value1"].kind == "data"
    assert bindings["s01.chart1.series1.value1"].sync is False
    assert bindings["s01.notes"].kind == "notes"
    assert bindings["s01.source.text"].kind == "source"


def test_alt_text_and_source_url_are_not_keys(fixture_dir: Path) -> None:
    keys = set(_all_blocks_ir(fixture_dir).keys.keys())

    assert "s01.image1.alt" not in keys
    assert "s01.chart1.alt" not in keys
    assert "s01.process.alt" not in keys
    assert "s01.source.url" not in keys


def test_source_and_notes_are_in_ir(fixture_dir: Path) -> None:
    slide = _all_blocks_ir(fixture_dir).slides[0]

    assert slide.notes == "Slide custom dengan seluruh block type."
    assert slide.source == {
        "text": "Sumber: fixture internal",
        "url": "http://example.com/source",
    }


def test_custom_spans_are_preserved(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "custom-grid.yaml"))
    spans = [block.span for block in deck.slides[0].blocks]

    assert spans == [12, 7, 5, 7, 5]


def test_custom_text_without_role_defaults_to_body() -> None:
    text = """\
schema: autooffice.deck/v1
meta: {title: "Custom", author: "Tim"}
slides:
  - id: s01
    layout: custom
    rows:
      - blocks:
          - {id: body1, type: text, text: "Isi", span: 12}
"""

    block = compile_deck(loads_deck(text)).slides[0].blocks[0]

    assert block.role == "body"


def test_metric_status_defaults_to_neutral() -> None:
    text = """\
schema: autooffice.deck/v1
meta: {title: "Metric", author: "Tim"}
slides:
  - id: s01
    layout: content
    blocks:
      - {id: kpi1, type: metric, label: "Label", value: "1"}
"""

    block = compile_deck(loads_deck(text)).slides[0].blocks[0]

    assert block.fields["status"] == "neutral"


def test_image_fit_default_comes_from_defaults() -> None:
    text = """\
schema: autooffice.deck/v1
meta: {title: "Image", author: "Tim"}
defaults: {image_fit: cover}
slides:
  - id: s01
    layout: content
    blocks:
      - {id: image1, type: image, path: "assets/a.png", alt: "Alt"}
"""

    block = compile_deck(loads_deck(text)).slides[0].blocks[0]

    assert block.fields["fit"] == "cover"


def test_code_language_default_comes_from_defaults() -> None:
    text = """\
schema: autooffice.deck/v1
meta: {title: "Code", author: "Tim"}
defaults: {code_language: python}
slides:
  - id: s01
    layout: content
    blocks:
      - {id: code1, type: code, code: "print(1)"}
"""

    block = compile_deck(loads_deck(text)).slides[0].blocks[0]

    assert block.fields["language"] == "python"
