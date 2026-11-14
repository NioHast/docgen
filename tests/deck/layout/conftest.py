"""Fixture bersama untuk test layout engine."""

from collections.abc import Callable, Mapping, Sequence

import pytest

from autooffice.deck.layout.grid import Grid
from autooffice.deck.layout.spec import LayoutSpec, SlotSpec
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyManifest, SlideIR
from autooffice.design.theme import Theme, resolve_theme

DEMO_SPEC = LayoutSpec(
    layout_id="demo",
    slots=(
        SlotSpec(
            slot_id="title",
            required=True,
            block_types=("text",),
            role="title",
            span=12,
        ),
        SlotSpec(
            slot_id="body",
            required=True,
            block_types=("text", "bullets"),
            role="body",
            span=6,
        ),
        SlotSpec(slot_id="note", required=False, block_types=("text",), role=None, span=6),
    ),
    rows=(("title",), ("body", "note")),
    accepts_source=True,
)


@pytest.fixture(scope="session")
def theme() -> Theme:
    """Theme indigo hasil resolusi token."""
    return resolve_theme("indigo")


@pytest.fixture(scope="session")
def grid(theme: Theme) -> Grid:
    """Grid dari theme indigo."""
    return Grid.from_theme(theme)


@pytest.fixture
def demo_spec() -> LayoutSpec:
    """Layout demo dengan slot wajib dan opsional."""
    return DEMO_SPEC


@pytest.fixture
def block_factory() -> Callable[..., BlockIR]:
    """Factory BlockIR dengan default yang valid."""

    def factory(
        block_id: str,
        block_type: str,
        *,
        fields: Mapping[str, object] | None = None,
        role: str | None = None,
        span: int | None = None,
    ) -> BlockIR:
        return BlockIR(
            block_id=block_id,
            block_type=block_type,
            span=span,
            role=role,
            fields={} if fields is None else dict(fields),
        )

    return factory


@pytest.fixture
def slide_factory() -> Callable[..., SlideIR]:
    """Factory SlideIR dengan source dan notes opsional."""

    def factory(
        blocks: Sequence[BlockIR],
        *,
        layout: str = "demo",
        slide_id: str = "s01",
        source: Mapping[str, str] | None = None,
        notes: str | None = None,
        rows: Sequence[Sequence[str]] = (),
    ) -> SlideIR:
        return SlideIR(
            slide_id=slide_id,
            layout=layout,
            order=0,
            blocks=tuple(blocks),
            notes=notes,
            source=source,
            rows=tuple(tuple(row) for row in rows),
        )

    return factory


@pytest.fixture
def deck_factory() -> Callable[..., DeckIR]:
    """Factory DeckIR satu slide dengan key manifest opsional."""

    def factory(
        slides: Sequence[SlideIR],
        *,
        keys: KeyManifest | None = None,
    ) -> DeckIR:
        return DeckIR(
            schema="autooffice.deck/v1",
            meta={"title": "Layout test"},
            theme_name="indigo",
            slides=tuple(slides),
            keys=KeyManifest(bindings=()) if keys is None else keys,
        )

    return factory
