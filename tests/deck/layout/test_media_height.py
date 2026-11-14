"""Test tinggi media contain terhadap ruang vertikal yang tersisa."""

from collections.abc import Callable

import pytest

from autooffice.deck.layout.grid import Grid
from autooffice.deck.layout.overflow import plan_deck
from autooffice.deck.layout.presets import diagram, image_full
from autooffice.deck.layout.spec import LayoutPlan, LayoutSpec
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, SlideIR
from autooffice.design.theme import Theme

MEDIA_CASES = (
    (image_full.LAYOUT, "image1", "image"),
    (diagram.LAYOUT, "diagram1", "diagram"),
)
MEDIA_IDS = ("image-full", "diagram")


def _media_plan(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
    *,
    layout: LayoutSpec,
    block_id: str,
    block_type: str,
    title: str = "Judul",
    caption: str | None = None,
) -> LayoutPlan:
    fields: dict[str, object] = {"path": f"assets/{block_id}.png"}
    if caption is not None:
        fields["caption"] = caption
    slide = slide_factory(
        (
            block_factory("title", "text", fields={"text": title}, role="title"),
            block_factory(block_id, block_type, fields=fields),
        ),
        layout=layout.layout_id,
    )
    return plan_deck(
        deck_factory((slide,)),
        theme,
        layouts={layout.layout_id: layout},
        fail_on_overflow=False,
    )


@pytest.mark.parametrize(
    ("layout", "block_id", "block_type"),
    MEDIA_CASES,
    ids=MEDIA_IDS,
)
def test_full_width_media_is_capped_to_remaining_height(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
    grid: Grid,
    layout: LayoutSpec,
    block_id: str,
    block_type: str,
) -> None:
    plan = _media_plan(
        block_factory,
        slide_factory,
        deck_factory,
        theme,
        layout=layout,
        block_id=block_id,
        block_type=block_type,
    )
    title_box, media_box = plan.slides[0].boxes
    natural_height = grid.span_width(12) * 9 // 16
    remaining_height = grid.content_bottom_emu - media_box.top_emu

    assert plan.slides[0].overflow_keys == ()
    assert media_box.top_emu == title_box.top_emu + title_box.height_emu + grid.row_gap_emu
    assert media_box.height_emu == remaining_height
    assert media_box.height_emu < natural_height
    assert media_box.top_emu + media_box.height_emu == grid.content_bottom_emu


def test_media_below_minimum_height_reports_block_scoped_key(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
) -> None:
    plan = _media_plan(
        block_factory,
        slide_factory,
        deck_factory,
        theme,
        layout=image_full.LAYOUT,
        block_id="image1",
        block_type="image",
        title="\n".join(["baris"] * 11),
    )
    _, image_box = plan.slides[0].boxes

    assert image_box.height_emu == theme.spacing.md_emu
    assert plan.slides[0].overflow_keys == ("s01.image1",)


def test_media_caption_that_cannot_fit_reports_caption_key(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
    grid: Grid,
) -> None:
    plan = _media_plan(
        block_factory,
        slide_factory,
        deck_factory,
        theme,
        layout=image_full.LAYOUT,
        block_id="image1",
        block_type="image",
        title="\n".join(["baris"] * 10),
        caption="Baris pertama\nBaris kedua",
    )
    _, image_box = plan.slides[0].boxes
    remaining_height = grid.content_bottom_emu - image_box.top_emu

    assert image_box.height_emu > remaining_height
    assert plan.slides[0].overflow_keys == ("s01.image1.caption",)


def test_image_full_reserves_subtitle_and_credit_before_capping_media(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
    grid: Grid,
) -> None:
    slide = slide_factory(
        (
            block_factory("title", "text", fields={"text": "Judul"}, role="title"),
            block_factory(
                "image1",
                "image",
                fields={"path": "assets/hero.png", "alt": "Ilustrasi"},
            ),
            block_factory(
                "subtitle",
                "text",
                fields={"text": "Subjudul yang menjelaskan gambar"},
                role="lead",
            ),
            block_factory(
                "credit",
                "text",
                fields={"text": "Sumber: dokumentasi tim"},
                role="caption",
            ),
        ),
        layout="image-full",
    )
    plan = plan_deck(
        deck_factory((slide,)),
        theme,
        layouts={"image-full": image_full.LAYOUT},
        fail_on_overflow=False,
    )
    _, image_box, subtitle_box, credit_box = plan.slides[0].boxes

    assert plan.slides[0].overflow_keys == ()
    assert image_box.top_emu + image_box.height_emu < grid.content_bottom_emu
    assert subtitle_box.top_emu == image_box.top_emu + image_box.height_emu + grid.row_gap_emu
    assert subtitle_box.top_emu + subtitle_box.height_emu <= grid.content_bottom_emu
    assert credit_box.top_emu + credit_box.height_emu <= grid.content_bottom_emu
    reserved_height = subtitle_box.height_emu + credit_box.height_emu + 2 * grid.row_gap_emu
    assert grid.content_bottom_emu - (image_box.top_emu + image_box.height_emu) == reserved_height
