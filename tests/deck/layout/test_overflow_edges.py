"""Test deduplikasi key overflow dan fallback key dari manifest."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from autooffice.deck.layout.overflow import (
    LayoutOverflowError,
    plan_deck,
    plan_overflow_keys,
)
from autooffice.deck.layout.spec import LayoutSpec
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyBinding, KeyManifest, SlideIR
from autooffice.design.theme import Theme


def _slide(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    body_text: str,
    *,
    slide_id: str = "s01",
) -> SlideIR:
    return slide_factory(
        (
            block_factory("title", "text", fields={"text": "Judul"}, role="title"),
            block_factory("body", "text", fields={"text": body_text}, role="body"),
        ),
        slide_id=slide_id,
    )


def _binding(key: str, slide_id: str, *, leaf: str = "text") -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id="body",
        leaf=leaf,
        kind="text",
        sync=True,
        yaml_path=("slides", 0, "blocks", 1, "text"),
        value="x",
        plain_text="x",
    )


def _layouts(spec: LayoutSpec) -> dict[str, LayoutSpec]:
    return {spec.layout_id: spec}


def test_plan_overflow_keys_deduplicates_keys_across_slides(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme: Theme,
) -> None:
    first = _slide(block_factory, slide_factory, "W" * 400)
    second = replace(first, slide_id="s02", order=1)
    manifest = KeyManifest(
        bindings=(
            _binding("shared.overflow", "s01"),
            _binding("shared.overflow", "s02"),
        )
    )

    plan = plan_deck(
        deck_factory((first, second), keys=manifest),
        theme,
        layouts=_layouts(demo_spec),
        fail_on_overflow=False,
    )

    assert tuple(slide.overflow_keys for slide in plan.slides) == (
        ("shared.overflow",),
        ("shared.overflow",),
    )
    assert plan_overflow_keys(plan) == ("shared.overflow",)


def test_same_block_width_and_height_overflow_share_one_key(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme: Theme,
) -> None:
    body = "\n".join(["W" * 400] * 40)
    deck = deck_factory((_slide(block_factory, slide_factory, body),))
    layouts = _layouts(demo_spec)

    raw = plan_deck(deck, theme, layouts=layouts, fail_on_overflow=False)
    assert raw.slides[0].overflow_keys == ("s01.body.text",)

    with pytest.raises(LayoutOverflowError) as error:
        plan_deck(deck, theme, layouts=layouts)

    kinds = {finding.kind for finding in error.value.findings}
    assert {"lebar", "tinggi"} <= kinds
    assert error.value.overflow_keys == ("s01.body.text",)


def test_manifest_binding_is_used_when_leaf_does_not_match(
    block_factory: Callable[..., BlockIR],
    slide_factory: Callable[..., SlideIR],
    deck_factory: Callable[..., DeckIR],
    demo_spec: LayoutSpec,
    theme: Theme,
) -> None:
    manifest = KeyManifest(
        bindings=(
            _binding("other.slide", "s99"),
            _binding("s01.body.value", "s01", leaf="value"),
        )
    )
    deck = deck_factory((_slide(block_factory, slide_factory, "W" * 400),), keys=manifest)

    plan = plan_deck(
        deck,
        theme,
        layouts=_layouts(demo_spec),
        fail_on_overflow=False,
    )

    assert plan.slides[0].overflow_keys == ("s01.body.value",)
