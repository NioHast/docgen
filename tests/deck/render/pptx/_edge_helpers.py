"""Helper lokal untuk tes cabang edge renderer PPTX."""

from types import SimpleNamespace
from typing import Any

from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.slide import Slide

from autooffice.deck.layout.spec import LayoutPlan, SlideLayout
from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyKind,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def new_slide() -> Slide:
    """Buat satu slide kosong dari template library python-pptx."""
    presentation = Presentation()
    return presentation.slides.add_slide(presentation.slide_layouts[6])


def line_spacing_points(paragraph) -> int | None:
    """Baca ``a:spcPts/@val`` paragraf dalam seperseratus poin."""
    node = paragraph._p.find(".//" + qn("a:spcPts"))
    return None if node is None else int(node.get("val", "0"))


def has_percentage_line_spacing(paragraph) -> bool:
    """True bila paragraf masih memakai ``a:spcPct`` relatif."""
    return paragraph._p.find(".//" + qn("a:spcPct")) is not None


def binding(
    key: str = "s01.title.text",
    *,
    slide_id: str = "s01",
    block_id: str | None = "title",
    leaf: str = "text",
    kind: KeyKind = "text",
    value: str = "nilai",
) -> KeyBinding:
    """Bangun satu binding manifest minimal."""
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, leaf),
        value=value,
        plain_text=value,
    )


def single_slide_deck(
    blocks: tuple[BlockIR, ...] = (),
    *,
    keys: tuple[KeyBinding, ...] = (),
    slide_id: str = "s01",
    notes: str | None = None,
    source: dict[str, str] | None = None,
) -> DeckIR:
    """Bangun deck satu slide tanpa layout engine."""
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Edge Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR(slide_id, "content", 0, blocks, notes, source),),
        keys=KeyManifest(keys),
    )


def single_slide_layout(
    boxes: tuple[Any, ...] = (),
    *,
    slide_id: str = "s01",
    overflow_keys: tuple[str, ...] = (),
) -> LayoutPlan:
    """Bangun LayoutPlan satu slide."""
    return LayoutPlan((SlideLayout(slide_id, tuple(boxes), overflow_keys),))


def request(case: Any, theme: Any, *, target: OutputTarget = OutputTarget.PPTX) -> RenderRequest:
    """Bungkus RenderCase menjadi RenderRequest."""
    return RenderRequest(
        deck=case.deck,
        layout=case.layout,
        theme=theme,
        target=target,
        workspace=case.workspace,
    )


def shape_with_metadata(name: str, *, title: str | None = None) -> SimpleNamespace:
    """Bangun shape palsu yang hanya memiliki ``p:cNvPr`` untuk metadata."""
    element = etree.Element(qn("p:sp"))
    node = etree.SubElement(element, qn("p:cNvPr"))
    node.set("name", name)
    if title is not None:
        node.set("title", title)
    return SimpleNamespace(_element=element)
