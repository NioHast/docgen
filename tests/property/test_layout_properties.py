"""Properti layout custom, span, tinggi row, dan media contain."""

from collections.abc import Mapping
from io import StringIO

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from ruamel.yaml import YAML

from autooffice.deck.layout.custom import (
    CustomLayoutError,
    plan_custom_slide,
    rows_for_slide,
)
from autooffice.deck.layout.grid import (
    Grid,
    SpanError,
    validate_row_spans,
)
from autooffice.deck.layout.measure import measure_block, measure_text
from autooffice.deck.model import BlockIR, SlideIR, compile_deck, loads_deck
from autooffice.design.theme import resolve_theme

_THEME = resolve_theme("indigo")
_GRID = Grid.from_theme(_THEME)

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_WORD = st.from_regex(r"[a-z0-9]{1,6}", fullmatch=True)
_TEXT = st.lists(_WORD, min_size=1, max_size=3).map(" ".join)


def _dump(data: Mapping[str, object]) -> str:
    yaml = YAML(typ="safe")
    stream = StringIO()
    yaml.dump(dict(data), stream)
    return stream.getvalue()


@st.composite
def _spans(draw, *, min_total: int, max_total: int, max_items: int = 6) -> tuple[int, ...]:
    total = draw(st.integers(min_total, max_total))
    minimum_count = 1 if total <= 12 else 2
    count = draw(st.integers(minimum_count, min(total, max_items)))
    remaining = total
    spans: list[int] = []
    for index in range(count):
        slots_left = count - index - 1
        lower = max(1, remaining - 12 * slots_left)
        upper = min(12, remaining - slots_left)
        span = draw(st.integers(lower, upper))
        spans.append(span)
        remaining -= span
    return tuple(spans)


def _text_block(block_id: str, span: int, text: str = "Isi") -> BlockIR:
    return BlockIR(
        block_id=block_id,
        block_type="text",
        span=span,
        role="body",
        fields={"text": text},
    )


def _custom_slide(spans: tuple[int, ...]) -> SlideIR:
    blocks = tuple(_text_block(f"b{index:02d}", span) for index, span in enumerate(spans))
    return SlideIR(
        slide_id="s01",
        layout="custom",
        order=0,
        blocks=blocks,
        notes=None,
        source=None,
        rows=(tuple(block.block_id for block in blocks),),
    )


@settings(max_examples=60, deadline=None)
@given(spans=_spans(min_total=1, max_total=12))
def test_spans_within_twelve_plan_without_error(spans: tuple[int, ...]) -> None:
    assert sum(spans) <= 12
    assert validate_row_spans(spans) == sum(spans)

    plan = plan_custom_slide(_custom_slide(spans), _THEME)

    assert len(plan.boxes) == len(spans)
    assert plan.overflow_keys == ()


@settings(max_examples=50, deadline=None)
@given(spans=_spans(min_total=13, max_total=24))
def test_spans_above_twelve_are_rejected(spans: tuple[int, ...]) -> None:
    assert sum(spans) > 12

    with pytest.raises(SpanError, match="maksimal 12"):
        validate_row_spans(spans)

    with pytest.raises(CustomLayoutError, match="maksimal 12"):
        plan_custom_slide(_custom_slide(spans), _THEME)


@st.composite
def _random_rows(draw) -> tuple[tuple[tuple[str, int, str], ...], ...]:
    rows: list[tuple[tuple[str, int, str], ...]] = []
    for row_index in range(draw(st.integers(1, 3))):
        spans = draw(_spans(min_total=1, max_total=12))
        blocks: list[tuple[str, int, str]] = []
        for span in spans:
            blocks.append((f"b{row_index}_{len(blocks)}", span, draw(_TEXT)))
        rows.append(tuple(blocks))
    return tuple(rows)


@settings(max_examples=30, deadline=None)
@given(rows=_random_rows())
def test_row_heights_are_deterministic(
    rows: tuple[tuple[tuple[str, int, str], ...], ...],
) -> None:
    blocks = tuple(
        _text_block(block_id, span, text) for row in rows for block_id, span, text in row
    )
    slide = SlideIR(
        slide_id="s01",
        layout="custom",
        order=0,
        blocks=blocks,
        notes=None,
        source=None,
        rows=tuple(tuple(block_id for block_id, _, _ in row) for row in rows),
    )

    first = plan_custom_slide(slide, _THEME)
    second = plan_custom_slide(slide, _THEME)

    assert first == second
    blocks_by_id = {block.block_id: block for block in blocks}
    offset = 0
    previous_bottom = None
    for row in rows:
        row_boxes = first.boxes[offset : offset + len(row)]
        offset += len(row)

        assert len({box.top_emu for box in row_boxes}) == 1
        assert len({box.height_emu for box in row_boxes}) == 1
        expected_height = max(
            measure_block(
                blocks_by_id[block_id],
                width_emu=_GRID.span_width(span),
                theme=_THEME,
            ).height_emu
            for block_id, span, _ in row
        )
        assert row_boxes[0].height_emu == expected_height
        if previous_bottom is not None:
            assert row_boxes[0].top_emu == previous_bottom + _GRID.row_gap_emu
        previous_bottom = row_boxes[0].top_emu + row_boxes[0].height_emu


@st.composite
def _custom_deck_dict(draw) -> tuple[dict[str, object], tuple[tuple[str, ...], ...]]:
    rows: list[dict[str, object]] = []
    expected: list[tuple[str, ...]] = []
    block_index = 0
    for _ in range(draw(st.integers(1, 3))):
        spans = draw(_spans(min_total=1, max_total=12))
        blocks: list[dict[str, object]] = []
        block_ids: list[str] = []
        for span in spans:
            block_id = f"b{block_index:02d}"
            block_index += 1
            blocks.append(
                {
                    "id": block_id,
                    "type": "text",
                    "text": draw(_TEXT),
                    "span": span,
                }
            )
            block_ids.append(block_id)
        rows.append({"blocks": blocks})
        expected.append(tuple(block_ids))
    data: dict[str, object] = {
        "schema": "autooffice.deck/v1",
        "meta": {"title": "Custom", "author": "Tim"},
        "slides": [{"id": "s01", "layout": "custom", "rows": rows}],
    }
    return data, tuple(expected)


@settings(max_examples=25, deadline=None)
@given(deck_data=_custom_deck_dict())
def test_custom_rows_match_compiled_ir(
    deck_data: tuple[dict[str, object], tuple[tuple[str, ...], ...]],
) -> None:
    data, expected = deck_data

    deck = compile_deck(loads_deck(_dump(data)))
    slide = deck.slides[0]

    assert slide.rows == expected
    rows = rows_for_slide(slide)
    assert tuple(tuple(block.block_id for block in row) for row in rows) == expected

    plan = plan_custom_slide(slide, _THEME)
    assert tuple(box.block_id for box in plan.boxes) == tuple(
        block_id for row in expected for block_id in row
    )


_MEDIA_TYPE = st.sampled_from(("image", "chart", "diagram"))
_CAPTION = st.one_of(st.none(), _TEXT)


def _media_block(block_type: str, caption: str | None) -> BlockIR:
    fields: dict[str, object]
    if block_type == "image":
        fields = {"path": "assets/gambar.png", "alt": "Ilustrasi"}
    elif block_type == "diagram":
        fields = {"source": "assets/diagram.mmd", "alt": "Diagram"}
    else:
        fields = {
            "kind": "bar",
            "title": "Judul",
            "alt": "Grafik",
            "categories": ("A", "B"),
            "series": (),
        }
    if caption is not None:
        fields["caption"] = caption
    return BlockIR(
        block_id="media1",
        block_type=block_type,
        span=12,
        role=None,
        fields=fields,
    )


@settings(max_examples=60, deadline=None)
@given(
    block_type=_MEDIA_TYPE,
    width=st.integers(1, 8_000_000),
    max_height=st.integers(0, 8_000_000),
    caption=_CAPTION,
)
def test_media_contain_respects_available_height(
    block_type: str,
    width: int,
    max_height: int,
    caption: str | None,
) -> None:
    measurement = measure_block(
        _media_block(block_type, caption),
        width_emu=width,
        theme=_THEME,
        max_height_emu=max_height,
    )
    minimum_media_height = _THEME.spacing.md_emu
    caption_height = (
        measure_text(caption, available_width_emu=width, theme=_THEME).height_emu
        if caption is not None
        else 0
    )
    caption_gap = _THEME.spacing.sm_emu if caption is not None else 0
    minimum_total = minimum_media_height + caption_gap + caption_height
    natural_media_height = max(minimum_media_height, width * 9 // 16)
    natural_total = natural_media_height + caption_gap + caption_height

    # Invarian contain, bukan salinan rumus overflow internal.
    assert measurement.width_emu >= width
    assert measurement.height_emu >= minimum_media_height
    assert measurement.height_emu <= natural_total
    if max_height >= natural_total:
        assert measurement.height_emu == natural_total
        if caption is None and width * 9 // 16 >= minimum_media_height:
            assert measurement.height_emu * 16 == pytest.approx(width * 9, abs=16)
    elif max_height >= minimum_total:
        assert measurement.height_emu == max_height
    else:
        # Tidak ada ruang untuk tinggi minimum; contain mempertahankan minimum
        # dan melaporkan sisa ruang lewat overflow.
        assert measurement.height_emu == minimum_total
        assert measurement.height_emu > max_height
