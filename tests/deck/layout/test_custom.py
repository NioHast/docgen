"""Test komposisi layout custom, validasi rows, dan dispatch plan_deck."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from autooffice.deck.layout.custom import (
    CustomLayoutError,
    plan_custom_slide,
    plan_custom_slide_with_findings,
    rows_for_slide,
    validate_custom_rows,
)
from autooffice.deck.layout.grid import Grid
from autooffice.deck.layout.measure import measure_block
from autooffice.deck.layout.overflow import plan_deck
from autooffice.deck.model import compile_deck, compile_deck_file, loads_deck
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, SlideIR

DEMO_DECK = Path(__file__).resolve().parents[3] / "examples" / "demo-deck" / "deck.yaml"


@pytest.fixture(scope="module")
def demo_custom_deck() -> DeckIR:
    """Deck demo yang hanya berisi slide custom s19 dan s20."""
    deck = compile_deck_file(DEMO_DECK)
    custom_slides = [slide for slide in deck.slides if slide.layout == "custom"]
    slides = tuple(replace(slide, order=index) for index, slide in enumerate(custom_slides))
    return DeckIR(
        schema=deck.schema,
        meta=deck.meta,
        theme_name=deck.theme_name,
        slides=slides,
        keys=deck.keys,
    )


def test_demo_custom_slides_plan_without_overflow(
    demo_custom_deck: DeckIR,
    theme,
) -> None:
    plan = plan_deck(demo_custom_deck, theme)

    by_id = {slide.slide_id: slide for slide in plan.slides}
    assert tuple(by_id) == ("s19", "s20")
    assert by_id["s19"].overflow_keys == ()
    assert by_id["s20"].overflow_keys == ()
    assert tuple(box.block_id for box in by_id["s19"].boxes) == (
        "title",
        "quote1",
        "insight",
        "divider1",
        "spacer1",
    )
    assert tuple(box.block_id for box in by_id["s20"].boxes) == (
        "title",
        "metric1",
        "metric2",
        "metric3",
        "coverage",
        "facts",
    )


def test_demo_custom_rows_share_the_tallest_height(
    demo_custom_deck: DeckIR,
    theme,
) -> None:
    plan = plan_deck(demo_custom_deck, theme)
    by_id = {slide.slide_id: slide for slide in plan.slides}
    s19 = {box.block_id: box for box in by_id["s19"].boxes}
    s20 = {box.block_id: box for box in by_id["s20"].boxes}

    assert s19["quote1"].top_emu == s19["insight"].top_emu
    assert s19["quote1"].height_emu == s19["insight"].height_emu
    assert s20["metric1"].top_emu == s20["metric2"].top_emu == s20["metric3"].top_emu
    assert s20["metric1"].height_emu == s20["metric2"].height_emu == s20["metric3"].height_emu
    assert s20["coverage"].top_emu == s20["facts"].top_emu
    assert s20["coverage"].height_emu == s20["facts"].height_emu


def test_custom_plan_is_deterministic(
    demo_custom_deck: DeckIR,
    theme,
) -> None:
    first = plan_deck(demo_custom_deck, theme)
    second = plan_deck(demo_custom_deck, theme)

    assert first == second


def test_partial_rows_use_ir_row_boundaries(theme) -> None:
    deck = compile_deck(
        loads_deck(
            """\
schema: autooffice.deck/v1
meta: {title: "Custom partial", author: "Tim"}
slides:
  - id: s01
    layout: custom
    rows:
      - blocks:
          - {id: top, type: text, text: "Baris pertama", span: 7}
      - blocks:
          - {id: bottom, type: text, text: "Baris kedua", span: 5}
"""
        )
    )

    assert deck.slides[0].rows == (("top",), ("bottom",))

    plan = plan_deck(deck, theme)
    top_box, bottom_box = plan.slides[0].boxes
    grid = Grid.from_theme(theme)

    assert bottom_box.top_emu == top_box.top_emu + top_box.height_emu + grid.row_gap_emu


def test_partial_unkeyed_rows_use_explicit_ir_rows(theme) -> None:
    deck = compile_deck(
        loads_deck(
            """\
schema: autooffice.deck/v1
meta: {title: "Custom unkeyed", author: "Tim"}
slides:
  - id: s01
    layout: custom
    rows:
      - blocks:
          - {id: divider1, type: divider, span: 6}
      - blocks:
          - {id: spacer1, type: spacer, size: md, span: 6}
      - blocks:
          - {id: title, type: text, role: title, text: "Judul", span: 12}
"""
        )
    )
    slide = deck.slides[0]
    grid = Grid.from_theme(theme)

    assert slide.rows == (("divider1",), ("spacer1",), ("title",))

    first = plan_deck(deck, theme)
    second = plan_deck(deck, theme)
    assert first == second

    divider_box, spacer_box, title_box = first.slides[0].boxes
    assert spacer_box.top_emu == (divider_box.top_emu + divider_box.height_emu + grid.row_gap_emu)
    assert title_box.top_emu == (spacer_box.top_emu + spacer_box.height_emu + grid.row_gap_emu)


def test_row_span_sum_over_twelve_is_rejected(
    block_factory: Callable[..., BlockIR],
    theme,
) -> None:
    left = block_factory("left", "text", fields={"text": "Kiri"}, span=7)
    right = block_factory("right", "text", fields={"text": "Kanan"}, span=6)

    with pytest.raises(CustomLayoutError, match="maksimal 12"):
        validate_custom_rows(((left, right),), slide_id="s01")


def test_nested_rows_are_rejected(
    block_factory: Callable[..., BlockIR],
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, span=12)

    with pytest.raises(CustomLayoutError, match="nested"):
        validate_custom_rows((((block,),),), slide_id="s01")


@pytest.mark.parametrize(
    ("rows", "match"),
    (
        ((), "minimal satu row"),
        (((),), "minimal memiliki satu block"),
    ),
)
def test_empty_rows_and_empty_row_are_rejected(
    rows: object,
    match: str,
) -> None:
    with pytest.raises(CustomLayoutError, match=match):
        validate_custom_rows(rows, slide_id="s01")


def test_absolute_geometry_fields_are_rejected(
    block_factory: Callable[..., BlockIR],
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi", "width": 100}, span=12)

    with pytest.raises(CustomLayoutError, match="geometri terlarang: width"):
        validate_custom_rows(((block,),), slide_id="s01")


def test_duplicate_block_ids_are_rejected(
    block_factory: Callable[..., BlockIR],
) -> None:
    first = block_factory("same", "text", fields={"text": "Satu"}, span=6)
    second = block_factory("same", "text", fields={"text": "Dua"}, span=6)

    with pytest.raises(CustomLayoutError, match="duplikat"):
        validate_custom_rows(((first, second),), slide_id="s01")


def test_invalid_block_type_is_rejected(
    block_factory: Callable[..., BlockIR],
) -> None:
    block = block_factory("body", "mystery", fields={"text": "Isi"}, span=12)

    with pytest.raises(CustomLayoutError, match="tidak dikenal"):
        validate_custom_rows(((block,),), slide_id="s01")


def test_preset_slot_field_is_rejected(
    block_factory: Callable[..., BlockIR],
) -> None:
    block = block_factory(
        "body",
        "text",
        fields={"text": "Isi", "slot": "title"},
        span=12,
    )

    with pytest.raises(CustomLayoutError, match="slot preset"):
        validate_custom_rows(((block,),), slide_id="s01")


def test_row_height_follows_the_tallest_block(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    title = block_factory("title", "text", fields={"text": "Judul"}, role="title", span=12)
    short = block_factory("short", "text", fields={"text": "Pendek"}, role="body", span=6)
    long = block_factory(
        "long",
        "text",
        fields={
            "text": (
                "Kalimat yang cukup panjang untuk membungkus beberapa baris pada kolom ini. " * 3
            )
        },
        role="body",
        span=6,
    )
    rows = ((title,), (short, long))
    slide = slide_factory((title, short, long), layout="custom")

    plan = plan_custom_slide(slide, theme, rows=rows)
    title_box, short_box, long_box = plan.boxes
    short_measurement = measure_block(short, width_emu=grid.span_width(6), theme=theme)
    long_measurement = measure_block(long, width_emu=grid.span_width(6), theme=theme)

    assert long_measurement.height_emu > short_measurement.height_emu
    assert short_box.height_emu == long_measurement.height_emu
    assert long_box.height_emu == long_measurement.height_emu
    assert short_box.top_emu == title_box.top_emu + title_box.height_emu + grid.row_gap_emu
    assert long_box.left_emu == grid.column_left(6)
    assert short_box.width_emu == grid.span_width(6)
    assert long_box.width_emu == grid.span_width(6)


def test_custom_media_uses_contain_height(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    title = block_factory("title", "text", fields={"text": "Judul"}, role="title", span=12)
    image = block_factory(
        "image1",
        "image",
        fields={"path": "assets/hero.png", "alt": "Ilustrasi"},
        span=12,
    )
    slide = slide_factory((title, image), layout="custom")

    plan = plan_custom_slide(slide, theme, rows=((title,), (image,)))
    _, image_box = plan.boxes
    natural_height = grid.span_width(12) * 9 // 16

    assert image_box.top_emu + image_box.height_emu == grid.content_bottom_emu
    assert image_box.height_emu < natural_height


def test_custom_media_reserves_following_body_row(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    image = block_factory(
        "image1",
        "image",
        fields={"path": "assets/hero.png", "alt": "Ilustrasi"},
        span=12,
    )
    body = block_factory(
        "body",
        "text",
        fields={"text": "Isi yang mengikuti gambar."},
        role="body",
        span=12,
    )
    slide = slide_factory((image, body), layout="custom")

    plan = plan_custom_slide(slide, theme, rows=((image,), (body,)))
    image_box, body_box = plan.boxes

    assert plan.overflow_keys == ()
    assert image_box.top_emu + image_box.height_emu < grid.content_bottom_emu
    assert body_box.top_emu == image_box.top_emu + image_box.height_emu + grid.row_gap_emu
    assert body_box.top_emu + body_box.height_emu <= grid.content_bottom_emu
    assert (
        grid.content_bottom_emu - (image_box.top_emu + image_box.height_emu)
        == body_box.height_emu + grid.row_gap_emu
    )


def test_source_and_notes_are_allowed_on_custom_slides(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    slide = slide_factory(
        (block,),
        layout="custom",
        source={"text": "Sumber internal"},
        notes="Catatan pembicara",
    )

    plan = plan_custom_slide(slide, theme, rows=((block,),))

    assert tuple(box.block_id for box in plan.boxes) == ("body",)
    assert plan.overflow_keys == ()


def test_rows_for_slide_rejects_preset_layout(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, role="body")
    slide = slide_factory((block,), layout="demo")

    with pytest.raises(CustomLayoutError, match="bukan 'custom'"):
        rows_for_slide(slide)


def test_planner_rejects_preset_layout_with_findings(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, role="body")
    slide = slide_factory((block,), layout="demo")

    with pytest.raises(CustomLayoutError, match="bukan 'custom'"):
        plan_custom_slide_with_findings(slide, theme)


def test_custom_overflow_findings_deduplicate_width_and_height_keys(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
) -> None:
    text = "W" * 400 + "\n" + "\n".join(["baris"] * 200)
    block = block_factory("body", "text", fields={"text": text}, span=12)
    slide = slide_factory((block,), layout="custom")

    plan = plan_custom_slide_with_findings(slide, theme, rows=((block,),))

    assert plan.layout.overflow_keys == ("s01.body.text",)
    assert tuple(finding.kind for finding in plan.overflows) == ("lebar", "tinggi")
    assert all(finding.key == "s01.body.text" for finding in plan.overflows)
    assert all(finding.estimated_overflow_emu > 0 for finding in plan.overflows)


def test_custom_media_caption_height_overflow_uses_caption_key(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    title = block_factory(
        "title",
        "text",
        fields={"text": "\n".join(["baris"] * 11)},
        role="title",
        span=12,
    )
    image = block_factory(
        "image1",
        "image",
        fields={
            "path": "assets/hero.png",
            "alt": "Ilustrasi",
            "caption": "Keterangan gambar",
        },
        span=12,
    )
    slide = slide_factory((title, image), layout="custom")

    plan = plan_custom_slide_with_findings(slide, theme, rows=((title,), (image,)))
    image_box = plan.layout.boxes[1]

    assert plan.layout.overflow_keys == ("s01.image1.caption",)
    assert tuple((finding.kind, finding.key) for finding in plan.overflows) == (
        ("tinggi", "s01.image1.caption"),
    )
    assert plan.overflows[0].estimated_overflow_emu > 0
    assert image_box.top_emu + image_box.height_emu > grid.content_bottom_emu


def test_custom_rows_below_content_bottom_report_height_findings(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
    grid: Grid,
) -> None:
    blocks = tuple(
        block_factory(f"b{index:02d}", "text", fields={"text": "baris"}, span=12)
        for index in range(20)
    )
    rows = tuple((block,) for block in blocks)
    slide = slide_factory(blocks, layout="custom")

    plan = plan_custom_slide_with_findings(slide, theme, rows=rows)
    last_box = plan.layout.boxes[-1]

    assert last_box.top_emu + last_box.height_emu > grid.content_bottom_emu
    assert plan.overflows
    assert all(finding.kind == "tinggi" for finding in plan.overflows)
    assert all(finding.estimated_overflow_emu > 0 for finding in plan.overflows)
    assert len(plan.layout.overflow_keys) == len(plan.overflows)
    assert plan.layout.overflow_keys[0].startswith("s01.b")


def test_rows_for_slide_returns_ir_rows(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    slide = replace(slide_factory((block,), layout="custom"), rows=(("body",),))

    assert rows_for_slide(slide) == ((block,),)


def test_custom_rows_must_cover_slide_blocks_in_order(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
) -> None:
    actual = block_factory("actual", "text", fields={"text": "Isi"}, role="body", span=12)
    other = block_factory("other", "text", fields={"text": "Lain"}, role="body", span=12)
    slide = slide_factory((actual,), layout="custom")

    with pytest.raises(CustomLayoutError, match="tidak cocok dengan urutan block"):
        plan_custom_slide(slide, theme, rows=((other,),))


def test_custom_slide_without_rows_or_blocks_is_rejected(
    slide_factory: Callable[..., SlideIR],
    theme,
) -> None:
    slide = slide_factory((), layout="custom")

    with pytest.raises(CustomLayoutError, match="tidak memiliki rows eksplisit"):
        plan_custom_slide(slide, theme)


def test_custom_slide_with_blocks_but_without_rows_is_rejected(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme,
) -> None:
    blocks = (
        block_factory("b0", "text", fields={"text": "Isi 0"}, span=12),
        block_factory("b1", "text", fields={"text": "Isi 1"}, span=6),
        block_factory("b2", "text", fields={"text": "Isi 2"}, span=6),
    )
    slide = slide_factory(blocks, layout="custom")

    with pytest.raises(CustomLayoutError, match="tidak memiliki rows eksplisit"):
        plan_custom_slide(slide, theme)

    with pytest.raises(CustomLayoutError, match="tidak memiliki rows eksplisit"):
        plan_custom_slide_with_findings(slide, theme)

    with pytest.raises(CustomLayoutError, match="tidak memiliki rows eksplisit"):
        rows_for_slide(slide)


def test_plan_deck_rejects_custom_slide_with_blocks_but_without_rows(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme,
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, role="body", span=12)
    slide = slide_factory((block,), layout="custom")

    with pytest.raises(CustomLayoutError, match="tidak memiliki rows eksplisit"):
        plan_deck(deck_factory((slide,)), theme, layouts={})


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        ("bukan rows", "harus berupa list row"),
        (("bukan row",), "harus berupa list block"),
    ],
)
def test_custom_rows_reject_non_sequence_inputs(rows: object, match: str) -> None:
    with pytest.raises(CustomLayoutError, match=match):
        validate_custom_rows(rows, slide_id="s01")


def test_custom_row_rejects_non_block_item() -> None:
    with pytest.raises(CustomLayoutError, match="hanya boleh berisi BlockIR"):
        validate_custom_rows(((object(),),), slide_id="s01")


def test_custom_block_requires_block_id(
    block_factory: Callable[..., BlockIR],
) -> None:
    block = block_factory("", "text", fields={"text": "Isi"}, span=12)

    with pytest.raises(CustomLayoutError, match="tanpa block_id"):
        validate_custom_rows(((block,),), slide_id="s01")


@pytest.mark.parametrize(
    ("span", "match"),
    [
        (None, "wajib memiliki span"),
        (True, "bukan bilangan bulat"),
        (6.0, "bukan bilangan bulat"),
    ],
)
def test_custom_block_span_must_be_integer(
    block_factory: Callable[..., BlockIR],
    span: object,
    match: str,
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, span=span)

    with pytest.raises(CustomLayoutError, match=match):
        validate_custom_rows(((block,),), slide_id="s01")


@pytest.mark.parametrize("span", [0, 13])
def test_custom_block_span_must_be_in_range(
    block_factory: Callable[..., BlockIR],
    span: int,
) -> None:
    block = block_factory("body", "text", fields={"text": "Isi"}, span=span)

    with pytest.raises(CustomLayoutError, match="Span harus 1 sampai 12"):
        validate_custom_rows(((block,),), slide_id="s01")


@pytest.mark.parametrize("field", ["x", "absolute", "translate"])
def test_custom_block_rejects_absolute_placement_fields(
    block_factory: Callable[..., BlockIR],
    field: str,
) -> None:
    block = block_factory(
        "body",
        "text",
        fields={"text": "Isi", field: 1},
        span=12,
    )

    with pytest.raises(CustomLayoutError, match=f"geometri terlarang: {field}"):
        validate_custom_rows(((block,),), slide_id="s01")
