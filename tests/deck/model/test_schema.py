"""Test validasi schema deck strict."""

from pathlib import Path

import pytest

from autooffice.deck.model import (
    DeckSchemaError,
    validate_deck,
)


def _block(block_type: str, block_id: str = "b1", **fields: object) -> dict[str, object]:
    return {"id": block_id, "type": block_type, **fields}


def _slide(**overrides: object) -> dict[str, object]:
    slide: dict[str, object] = {
        "id": "s01",
        "layout": "content",
        "blocks": [_block("text", "title", text="Judul")],
    }
    slide.update(overrides)
    return slide


def _custom_slide(rows: list[object], **overrides: object) -> dict[str, object]:
    slide: dict[str, object] = {"id": "s01", "layout": "custom", "rows": rows}
    slide.update(overrides)
    return slide


def _deck(
    slide: dict[str, object] | None = None,
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema": "autooffice.deck/v1",
        "meta": meta if meta is not None else {"title": "Deck", "author": "Tim"},
        "slides": [slide if slide is not None else _slide()],
    }


def _row(*blocks: dict[str, object]) -> dict[str, object]:
    return {"blocks": list(blocks)}


def _span_block(
    block_type: str, block_id: str, span: object = 12, **fields: object
) -> dict[str, object]:
    return {**_block(block_type, block_id, **fields), "span": span}


def test_unknown_top_level_field_rejected() -> None:
    deck = _deck()
    deck["extra"] = {}

    with pytest.raises(DeckSchemaError, match="tidak dikenal"):
        validate_deck(deck)


def test_unknown_meta_field_rejected() -> None:
    deck = _deck(meta={"title": "Deck", "author": "Tim", "token": "x"})

    with pytest.raises(DeckSchemaError, match="tidak dikenal"):
        validate_deck(deck)


def test_unknown_slide_field_rejected() -> None:
    deck = _deck(_slide(timing="fast"))

    with pytest.raises(DeckSchemaError, match="tidak dikenal"):
        validate_deck(deck)


def test_unknown_block_field_rejected() -> None:
    deck = _deck(_slide(blocks=[_block("text", "title", text="Judul", extra="x")]))

    with pytest.raises(DeckSchemaError, match="tidak dikenal"):
        validate_deck(deck)


@pytest.mark.parametrize("field", ["x", "y", "width", "height", "position", "z_index"])
def test_geometry_field_rejected(field: str) -> None:
    deck = _deck(_slide(blocks=[_block("text", "title", text="Judul", **{field: 1})]))

    with pytest.raises(DeckSchemaError, match="geometri"):
        validate_deck(deck)


@pytest.mark.parametrize("field", ["color", "font_size", "margin", "padding"])
def test_style_field_rejected(field: str) -> None:
    deck = _deck(_slide(blocks=[_block("text", "title", text="Judul", **{field: "x"})]))

    with pytest.raises(DeckSchemaError, match="style"):
        validate_deck(deck)


@pytest.mark.parametrize("field", ["title", "author"])
def test_required_meta_field_rejected(field: str) -> None:
    meta = {"title": "Deck", "author": "Tim"}
    del meta[field]
    deck = _deck(meta=meta)

    with pytest.raises(DeckSchemaError, match=field):
        validate_deck(deck)


def test_duplicate_slide_id_rejected() -> None:
    deck = _deck()
    deck["slides"] = [_slide(), _slide()]

    with pytest.raises(DeckSchemaError, match="duplikat"):
        validate_deck(deck)


def test_duplicate_block_id_rejected() -> None:
    slide = _slide(
        blocks=[
            _block("text", "title", text="Satu"),
            _block("text", "title", text="Dua"),
        ]
    )

    with pytest.raises(DeckSchemaError, match="duplikat"):
        validate_deck(_deck(slide))


def test_blocks_and_rows_together_rejected() -> None:
    slide = _slide(rows=[_row(_span_block("text", "title", text="Judul"))])

    with pytest.raises(DeckSchemaError, match="blocks dan rows"):
        validate_deck(_deck(slide))


def test_custom_layout_requires_rows() -> None:
    slide = {"id": "s01", "layout": "custom"}

    with pytest.raises(DeckSchemaError, match="wajib memiliki rows"):
        validate_deck(_deck(slide))


def test_custom_layout_rejects_blocks() -> None:
    slide = {"id": "s01", "layout": "custom", "blocks": [_block("text", text="Judul")]}

    with pytest.raises(DeckSchemaError, match="wajib memakai rows"):
        validate_deck(_deck(slide))


def test_preset_layout_rejects_rows() -> None:
    slide = {
        "id": "s01",
        "layout": "content",
        "rows": [_row(_span_block("text", "title", text="Judul"))],
    }

    with pytest.raises(DeckSchemaError, match="tidak boleh memiliki rows"):
        validate_deck(_deck(slide))


def test_preset_layout_requires_blocks() -> None:
    slide = {"id": "s01", "layout": "content"}

    with pytest.raises(DeckSchemaError, match="wajib memiliki blocks"):
        validate_deck(_deck(slide))


def test_span_on_preset_rejected() -> None:
    slide = _slide(blocks=[_block("text", "title", text="Judul", span=2)])

    with pytest.raises(DeckSchemaError, match="Span hanya"):
        validate_deck(_deck(slide))


@pytest.mark.parametrize("span", [0, 13, -1])
def test_custom_span_out_of_range_rejected(span: int) -> None:
    slide = _custom_slide([_row(_span_block("text", "title", span=span, text="Judul"))])

    with pytest.raises(DeckSchemaError, match="1 sampai 12"):
        validate_deck(_deck(slide))


def test_custom_span_must_be_integer() -> None:
    slide = _custom_slide([_row(_span_block("text", "title", span=True, text="Judul"))])

    with pytest.raises(DeckSchemaError, match="bilangan bulat"):
        validate_deck(_deck(slide))


def test_custom_span_required() -> None:
    slide = _custom_slide([_row(_block("text", "title", text="Judul"))])

    with pytest.raises(DeckSchemaError, match="span"):
        validate_deck(_deck(slide))


def test_custom_row_span_sum_over_twelve_rejected() -> None:
    slide = _custom_slide(
        [
            _row(
                _span_block("text", "title", span=7, text="Judul"),
                _span_block("text", "lead", span=6, text="Lead"),
            )
        ]
    )

    with pytest.raises(DeckSchemaError, match="maksimal 12"):
        validate_deck(_deck(slide))


def test_custom_requires_at_least_one_row() -> None:
    slide = _custom_slide([])

    with pytest.raises(DeckSchemaError, match="minimal satu row"):
        validate_deck(_deck(slide))


def test_custom_row_requires_at_least_one_block() -> None:
    slide = _custom_slide([_row()])

    with pytest.raises(DeckSchemaError, match="minimal satu block"):
        validate_deck(_deck(slide))


@pytest.mark.parametrize("block_type", ["divider", "spacer"])
def test_divider_and_spacer_rejected_in_preset(block_type: str) -> None:
    slide = _slide(blocks=[_block(block_type, "decoration")])

    with pytest.raises(DeckSchemaError, match="hanya boleh dipakai pada layout custom"):
        validate_deck(_deck(slide))


def _chart(
    *,
    kind: str = "bar",
    categories: list[str] | None = None,
    series: list[dict[str, object]] | None = None,
    **fields: object,
) -> dict[str, object]:
    categories = categories if categories is not None else ["Q1", "Q2"]
    series = series if series is not None else [{"name": "Satu", "values": [1, 2]}]
    return _block(
        "chart",
        "chart1",
        kind=kind,
        title="Grafik",
        alt="Alt grafik",
        categories=categories,
        series=series,
        **fields,
    )


@pytest.mark.parametrize(
    ("kind", "series", "match"),
    [
        ("bar", [{"name": str(index), "values": [1, 2]} for index in range(5)], "1 sampai 4 seri"),
        ("line", [{"name": str(index), "values": [1, 2]} for index in range(5)], "1 sampai 4 seri"),
        (
            "donut",
            [
                {"name": "Satu", "values": [1, 2]},
                {"name": "Dua", "values": [3, 4]},
            ],
            "tepat satu seri",
        ),
    ],
)
def test_chart_series_limits(kind: str, series: list[dict[str, object]], match: str) -> None:
    slide = _slide(blocks=[_chart(kind=kind, series=series)])

    with pytest.raises(DeckSchemaError, match=match):
        validate_deck(_deck(slide))


def test_donut_five_categories_rejected() -> None:
    slide = _slide(
        blocks=[
            _chart(
                kind="donut",
                categories=["A", "B", "C", "D", "E"],
                series=[{"name": "Satu", "values": [1, 2, 3, 4, 5]}],
            )
        ]
    )

    with pytest.raises(DeckSchemaError, match="2 sampai 4 kategori"):
        validate_deck(_deck(slide))


def test_chart_values_length_must_match_categories() -> None:
    slide = _slide(blocks=[_chart(series=[{"name": "Satu", "values": [1, 2, 3]}])])

    with pytest.raises(DeckSchemaError, match="jumlah kategori"):
        validate_deck(_deck(slide))


def test_chart_orientation_only_for_bar() -> None:
    slide = _slide(blocks=[_chart(kind="line", orientation="horizontal")])

    with pytest.raises(DeckSchemaError, match="hanya valid untuk chart bar"):
        validate_deck(_deck(slide))


def test_table_row_must_match_columns() -> None:
    slide = _slide(
        blocks=[
            _block(
                "table",
                "table1",
                columns=["A", "B"],
                rows=[["satu"]],
            )
        ]
    )

    with pytest.raises(DeckSchemaError, match="jumlah kolom"):
        validate_deck(_deck(slide))


def test_table_requires_column_and_row() -> None:
    slide = _slide(blocks=[_block("table", "table1", columns=[], rows=[])])

    with pytest.raises(DeckSchemaError, match="minimal satu kolom"):
        validate_deck(_deck(slide))


def test_emphasis_column_only_for_comparison() -> None:
    slide = _slide(
        blocks=[
            _block(
                "table",
                "table1",
                columns=["A", "B"],
                rows=[["satu", "dua"]],
                emphasis_column=2,
            )
        ]
    )

    with pytest.raises(DeckSchemaError, match="layout comparison"):
        validate_deck(_deck(slide))


def test_emphasis_column_out_of_range() -> None:
    slide = _slide(
        layout="comparison",
        blocks=[
            _block(
                "table",
                "table1",
                columns=["A", "B"],
                rows=[["satu", "dua"]],
                emphasis_column=3,
            )
        ],
    )

    with pytest.raises(DeckSchemaError, match="di luar jumlah kolom"):
        validate_deck(_deck(slide))


def test_source_requires_text() -> None:
    slide = _slide(source={"url": "https://example.com"})

    with pytest.raises(DeckSchemaError, match="text"):
        validate_deck(_deck(slide))


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "file:///tmp/x", "example.com", "https://", "https://exa mple.com"],
)
def test_source_url_rejects_non_http_or_unsafe(url: str) -> None:
    slide = _slide(source={"text": "Sumber", "url": url})

    with pytest.raises(DeckSchemaError, match=r"source\.url"):
        validate_deck(_deck(slide))


def test_notes_must_not_be_empty() -> None:
    slide = _slide(notes="   \n ")

    with pytest.raises(DeckSchemaError, match="tidak boleh kosong"):
        validate_deck(_deck(slide))


@pytest.mark.parametrize(
    ("language", "expected"),
    [("id-ID", "id"), ("en-US", "en"), ("id", "id"), ("EN", "en")],
)
def test_language_normalization(language: str, expected: str) -> None:
    deck = _deck()
    meta = deck["meta"]
    assert isinstance(meta, dict)
    meta["language"] = language

    definition = validate_deck(deck)

    assert definition.meta.language == expected


@pytest.mark.parametrize("language", ["fr-FR", "in-ID", "id_ID", ""])
def test_unsupported_language_rejected(language: str) -> None:
    deck = _deck(meta={"title": "Deck", "author": "Tim", "language": language})

    with pytest.raises(DeckSchemaError, match=r"language|Bahasa"):
        validate_deck(deck)


def _image_path_deck(path: str) -> dict[str, object]:
    return _deck(_slide(blocks=[_block("image", "image1", path=path, alt="Alt")]))


@pytest.mark.parametrize(
    "path",
    [
        "../hero.png",
        "/abs/hero.png",
        "C:/hero.png",
        "C:\\hero.png",
        "\\\\server\\share\\hero.png",
        "https://example.com/hero.png",
        "assets//hero.png",
        "assets/./hero.png",
        "assets/../hero.png",
        "assets\\hero.png",
    ],
)
def test_asset_path_traversal_and_remote_rejected(path: str) -> None:
    with pytest.raises(DeckSchemaError, match=r"path|direktori|segmen|remote|backslash"):
        validate_deck(_image_path_deck(path))


def test_image_extension_must_be_supported() -> None:
    with pytest.raises(DeckSchemaError, match="berekstensi"):
        validate_deck(_image_path_deck("assets/hero.svg"))


def test_diagram_extension_must_be_mmd() -> None:
    slide = _slide(
        blocks=[_block("diagram", "diagram1", source="diagrams/process.png", alt="Alt diagram")]
    )

    with pytest.raises(DeckSchemaError, match="berekstensi"):
        validate_deck(_deck(slide))


def test_asset_path_valid_passes() -> None:
    definition = validate_deck(_image_path_deck("assets/hero.webp"))

    assert definition.slides[0].blocks[0].fields["path"] == "assets/hero.webp"


def test_theme_must_be_known() -> None:
    deck = _deck()
    deck["theme"] = {"name": "malam"}

    with pytest.raises(DeckSchemaError, match="Theme"):
        validate_deck(deck)


def test_defaults_layout_must_be_known() -> None:
    deck = _deck()
    deck["defaults"] = {"layout": "unknown"}

    with pytest.raises(DeckSchemaError, match="Layout default"):
        validate_deck(deck)


def test_image_alt_must_not_be_empty() -> None:
    slide = _slide(blocks=[_block("image", "image1", path="assets/hero.png", alt="  ")])

    with pytest.raises(DeckSchemaError, match="tidak boleh kosong"):
        validate_deck(_deck(slide))


def test_invalid_text_role_rejected() -> None:
    slide = _slide(blocks=[_block("text", "title", text="Judul", role="hero")])

    with pytest.raises(DeckSchemaError, match="role"):
        validate_deck(_deck(slide))


def test_bullets_require_items() -> None:
    slide = _slide(blocks=[_block("bullets", "points", items=[])])

    with pytest.raises(DeckSchemaError, match="minimal satu item"):
        validate_deck(_deck(slide))


def test_schema_identifier_must_match_contract() -> None:
    deck = _deck()
    deck["schema"] = "autooffice.deck/v2"

    with pytest.raises(DeckSchemaError, match="Schema harus"):
        validate_deck(deck)


def test_deck_requires_at_least_one_slide() -> None:
    deck = _deck()
    deck["slides"] = []

    with pytest.raises(DeckSchemaError, match="minimal satu slide"):
        validate_deck(deck)


def test_meta_language_must_be_string() -> None:
    deck = _deck(meta={"title": "Deck", "author": "Tim", "language": 123})

    with pytest.raises(DeckSchemaError, match=r"meta\.language harus string"):
        validate_deck(deck)


def test_slide_without_layout_uses_default_layout() -> None:
    slide = {"id": "s01", "blocks": [_block("text", "title", text="Judul")]}

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].layout == "content"


def test_unknown_slide_layout_rejected() -> None:
    deck = _deck(_slide(layout="fancy"))

    with pytest.raises(DeckSchemaError, match="Layout 'fancy' tidak dikenal"):
        validate_deck(deck)


def test_unknown_block_type_rejected() -> None:
    deck = _deck(_slide(blocks=[_block("video", "media")]))

    with pytest.raises(DeckSchemaError, match="Block type 'video' tidak dikenal"):
        validate_deck(deck)


def test_missing_required_block_field_rejected() -> None:
    deck = _deck(_slide(blocks=[_block("image", "image1", alt="Alt")]))

    with pytest.raises(DeckSchemaError, match="wajib memiliki 'path'"):
        validate_deck(deck)


def test_image_fit_choice_is_applied() -> None:
    slide = _slide(
        blocks=[_block("image", "image1", path="assets/hero.png", alt="Alt", fit="cover")]
    )

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].blocks[0].fields["fit"] == "cover"


def test_table_requires_at_least_one_row() -> None:
    slide = _slide(blocks=[_block("table", "table1", columns=["A"], rows=[])])

    with pytest.raises(DeckSchemaError, match="minimal satu baris"):
        validate_deck(_deck(slide))


def test_emphasis_column_valid_on_comparison_layout() -> None:
    slide = _slide(
        layout="comparison",
        blocks=[
            _block(
                "table",
                "table1",
                columns=["A", "B"],
                rows=[["satu", "dua"]],
                emphasis_column=2,
            )
        ],
    )

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].blocks[0].fields["emphasis_column"] == 2


def test_chart_requires_at_least_two_categories() -> None:
    slide = _slide(
        blocks=[
            _chart(
                categories=["Q1"],
                series=[{"name": "Satu", "values": [1]}],
            )
        ]
    )

    with pytest.raises(DeckSchemaError, match="minimal dua kategori"):
        validate_deck(_deck(slide))


def test_donut_accepts_two_to_four_categories() -> None:
    slide = _slide(
        blocks=[
            _chart(
                kind="donut",
                categories=["A", "B", "C"],
                series=[{"name": "Satu", "values": [1, 2, 3]}],
            )
        ]
    )

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].blocks[0].fields["kind"] == "donut"


def test_bar_orientation_choice_is_applied() -> None:
    slide = _slide(blocks=[_chart(kind="bar", orientation="horizontal")])

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].blocks[0].fields["orientation"] == "horizontal"


def test_chart_requires_at_least_one_series() -> None:
    slide = _slide(blocks=[_chart(series=[])])

    with pytest.raises(DeckSchemaError, match="minimal satu seri"):
        validate_deck(_deck(slide))


def test_quote_without_attribution_is_valid() -> None:
    slide = _slide(blocks=[_block("quote", "quote1", text="Kutipan")])

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].blocks[0].fields == {"text": "Kutipan"}


def test_diagram_without_caption_is_valid() -> None:
    slide = _slide(
        blocks=[
            _block(
                "diagram",
                "diagram1",
                source="diagrams/flow.mmd",
                alt="Alt diagram",
            )
        ]
    )

    definition = validate_deck(_deck(slide))

    fields = definition.slides[0].blocks[0].fields
    assert fields == {"source": "diagrams/flow.mmd", "alt": "Alt diagram"}


def test_spacer_defaults_to_medium_size() -> None:
    slide = _custom_slide([_row(_span_block("spacer", "spacer1"))])

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].rows[0][0].fields["size"] == "md"


def test_asset_path_rejects_control_characters() -> None:
    deck = _deck(_slide(blocks=[_block("image", "image1", path="assets/hero\x01.png", alt="Alt")]))

    with pytest.raises(DeckSchemaError, match="karakter kontrol"):
        validate_deck(deck)


def test_asset_path_must_stay_inside_base_dir(tmp_path: Path) -> None:
    base_dir = tmp_path / "deck"
    base_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (base_dir / "assets").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink tidak didukung pada environment ini")

    with pytest.raises(DeckSchemaError, match="keluar dari direktori deck"):
        validate_deck(_image_path_deck("assets/hero.png"), base_dir=base_dir)


def test_non_string_mapping_key_rejected() -> None:
    with pytest.raises(DeckSchemaError, match="Key root deck harus string"):
        validate_deck({1: "x"})


def test_slides_must_be_array() -> None:
    deck = _deck()
    deck["slides"] = "s01"

    with pytest.raises(DeckSchemaError, match="slides harus array"):
        validate_deck(deck)


def test_meta_title_must_be_string() -> None:
    deck = _deck(meta={"title": 123, "author": "Tim"})

    with pytest.raises(DeckSchemaError, match=r"meta\.title harus string"):
        validate_deck(deck)


def test_text_rejects_unsupported_inline_markdown() -> None:
    slide = _slide(blocks=[_block("text", "title", text="*miring*")])

    with pytest.raises(DeckSchemaError, match="italic"):
        validate_deck(_deck(slide))


def test_alt_rejects_plain_markdown() -> None:
    slide = _slide(blocks=[_block("image", "image1", path="assets/hero.png", alt="**tebal**")])

    with pytest.raises(DeckSchemaError, match="bold"):
        validate_deck(_deck(slide))


def test_bullets_ordered_must_be_boolean() -> None:
    slide = _slide(blocks=[_block("bullets", "points", items=["Satu"], ordered="yes")])

    with pytest.raises(DeckSchemaError, match="ordered harus boolean"):
        validate_deck(_deck(slide))


def test_chart_values_must_be_numbers() -> None:
    slide = _slide(blocks=[_chart(series=[{"name": "Satu", "values": ["1", 2]}])])

    with pytest.raises(DeckSchemaError, match="harus angka"):
        validate_deck(_deck(slide))


def test_chart_values_must_be_finite() -> None:
    slide = _slide(blocks=[_chart(series=[{"name": "Satu", "values": [float("inf"), 2]}])])

    with pytest.raises(DeckSchemaError, match="angka finite"):
        validate_deck(_deck(slide))


def test_slide_id_grammar_rejected() -> None:
    deck = _deck(_slide(id="s1"))

    with pytest.raises(DeckSchemaError, match="Slide ID 's1' harus cocok"):
        validate_deck(deck)


def test_block_id_grammar_rejected() -> None:
    deck = _deck(_slide(blocks=[_block("text", "Title", text="Judul")]))

    with pytest.raises(DeckSchemaError, match="Block ID 'Title' harus cocok"):
        validate_deck(deck)


def test_meta_as_mapping_includes_description() -> None:
    deck = _deck(meta={"title": "Deck", "author": "Tim", "description": "Ringkasan"})

    definition = validate_deck(deck)

    assert definition.meta.as_mapping()["description"] == "Ringkasan"


def test_schema_error_formats_key_context() -> None:
    error = DeckSchemaError(
        "gagal",
        path=("slides", 0),
        slide_id="s01",
        block_id="b1",
        key="s01.b1.text",
    )

    assert str(error) == "slides[0]: gagal (slide=s01, block=b1, key=s01.b1.text)"


def test_custom_block_id_source_rejected() -> None:
    slide = _custom_slide([_row(_span_block("text", "source", text="Isi"))])

    with pytest.raises(DeckSchemaError, match=r"source\.text") as error:
        validate_deck(_deck(slide))

    assert "block=source" in str(error.value)


@pytest.mark.parametrize(
    "url",
    ["http://[::1", "http://example.com\uff0fx"],
)
def test_source_url_malformed_rejected(url: str) -> None:
    slide = _slide(source={"text": "Sumber", "url": url})

    with pytest.raises(DeckSchemaError, match=r"source\.url"):
        validate_deck(_deck(slide))


@pytest.mark.parametrize("url", ["http://:80", "http://user@"])
def test_source_url_requires_host(url: str) -> None:
    slide = _slide(source={"text": "Sumber", "url": url})

    with pytest.raises(DeckSchemaError, match=r"source\.url.*host"):
        validate_deck(_deck(slide))


def _slide_with_text_field(field: str, value: str) -> dict[str, object]:
    if field == "text":
        return _slide(blocks=[_block("text", "title", text=value)])
    if field == "heading":
        return _slide(blocks=[_block("text", "title", text="Judul", heading=value)])
    if field == "title":
        return _slide(
            blocks=[
                _block(
                    "chart",
                    "chart1",
                    kind="bar",
                    title=value,
                    alt="Alt grafik",
                    categories=["Q1", "Q2"],
                    series=[{"name": "Satu", "values": [1, 2]}],
                )
            ]
        )
    if field == "alt":
        return _slide(blocks=[_block("image", "image1", path="assets/hero.png", alt=value)])
    if field == "caption":
        return _slide(
            blocks=[_block("image", "image1", path="assets/hero.png", alt="Alt", caption=value)]
        )
    if field == "source.text":
        return _slide(source={"text": value})
    if field == "notes":
        return _slide(notes=value)
    if field == "code":
        return _slide(blocks=[_block("code", "code1", code=value)])
    raise AssertionError(f"field tidak dikenal: {field}")


@pytest.mark.parametrize(
    "field",
    ["text", "heading", "title", "alt", "caption", "source.text", "notes", "code"],
)
@pytest.mark.parametrize("value", ["\x00", "\x01", "\u200b"])
def test_displayed_text_rejects_control_and_invisible_characters(field: str, value: str) -> None:
    with pytest.raises(DeckSchemaError, match=r"karakter kontrol|tak terlihat"):
        validate_deck(_deck(_slide_with_text_field(field, value)))


@pytest.mark.parametrize("value", ["a\tb", "a\nb"])
def test_notes_and_code_allow_tabs_and_newlines(value: str) -> None:
    slide = _slide(notes=value, blocks=[_block("code", "code1", code=value)])

    definition = validate_deck(_deck(slide))

    assert definition.slides[0].notes == value
    assert definition.slides[0].blocks[0].fields["code"] == value


def test_asset_path_symlink_loop_rejected(tmp_path: Path) -> None:
    base_dir = tmp_path / "deck"
    assets = base_dir / "assets"
    assets.mkdir(parents=True)
    loop = assets / "loop.png"
    try:
        loop.symlink_to("loop.png")
    except OSError, RuntimeError:
        pytest.skip("symlink tidak didukung pada environment ini")

    with pytest.raises(DeckSchemaError, match=r"loop\.png"):
        validate_deck(_image_path_deck("assets/loop.png"), base_dir=base_dir)
