"""Test atribusi leaf overflow yang sebenarnya, bukan kandidat pertama."""

from collections.abc import Callable, Sequence

from autooffice.deck.layout.custom import plan_custom_slide_with_findings
from autooffice.deck.layout.overflow import plan_deck
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyManifest, SlideIR
from autooffice.design.theme import Theme

LONG = "W" * 200


def _plan(
    blocks: Sequence[BlockIR],
    *,
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
    keys: KeyManifest | None = None,
):
    slide = slide_factory(tuple(blocks), layout="custom")
    return plan_deck(
        deck_factory((slide,), keys=keys),
        theme,
        layouts={},
        fail_on_overflow=False,
    )


def test_bullets_overflow_reports_the_actual_item(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
) -> None:
    block = block_factory(
        "points",
        "bullets",
        fields={"items": ("Poin aman", LONG)},
        span=12,
    )

    plan = _plan(
        (block,),
        block_factory=block_factory,
        slide_factory=slide_factory,
        deck_factory=deck_factory,
        theme=theme,
    )

    assert plan.slides[0].overflow_keys == ("s01.points.item2.text",)


def test_metric_overflow_reports_the_actual_label(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
) -> None:
    block = block_factory(
        "metric1",
        "metric",
        fields={"value": "1", "label": LONG},
        span=12,
    )

    plan = _plan(
        (block,),
        block_factory=block_factory,
        slide_factory=slide_factory,
        deck_factory=deck_factory,
        theme=theme,
    )

    assert plan.slides[0].overflow_keys == ("s01.metric1.label",)


def test_table_overflow_reports_the_actual_cell(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
) -> None:
    block = block_factory(
        "table1",
        "table",
        fields={"columns": ("A",), "rows": ((LONG,),)},
        span=12,
    )

    plan = _plan(
        (block,),
        block_factory=block_factory,
        slide_factory=slide_factory,
        deck_factory=deck_factory,
        theme=theme,
    )

    assert plan.slides[0].overflow_keys == ("s01.table1.r1.c1",)


def test_text_overflow_reports_the_heading(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
) -> None:
    block = block_factory(
        "body",
        "text",
        fields={"heading": LONG, "text": "Isi"},
        role="body",
        span=12,
    )

    plan = _plan(
        (block,),
        block_factory=block_factory,
        slide_factory=slide_factory,
        deck_factory=deck_factory,
        theme=theme,
    )

    assert plan.slides[0].overflow_keys == ("s01.body.heading",)


def test_quote_overflow_reports_the_attribution(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
) -> None:
    block = block_factory(
        "quote1",
        "quote",
        fields={"text": "Kutipan", "attribution": LONG},
        span=12,
    )

    plan = _plan(
        (block,),
        block_factory=block_factory,
        slide_factory=slide_factory,
        deck_factory=deck_factory,
        theme=theme,
    )

    assert plan.slides[0].overflow_keys == ("s01.quote1.attribution",)


def test_captionless_media_uses_block_scoped_key(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    theme: Theme,
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
        fields={"path": "assets/hero.png", "alt": "Ilustrasi"},
        span=12,
    )

    plan = _plan(
        (title, image),
        block_factory=block_factory,
        slide_factory=slide_factory,
        deck_factory=deck_factory,
        theme=theme,
    )

    assert plan.slides[0].overflow_keys == ("s01.image1",)


def test_custom_findings_use_actual_leaf_without_key_resolver(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    theme: Theme,
) -> None:
    block = block_factory(
        "points",
        "bullets",
        fields={"items": ("Poin aman", LONG)},
        span=12,
    )
    slide = slide_factory((block,), layout="custom")

    plan = plan_custom_slide_with_findings(slide, theme)

    assert plan.layout.overflow_keys == ("s01.points.item2.text",)
    assert tuple(finding.key for finding in plan.overflows) == ("s01.points.item2.text",)
