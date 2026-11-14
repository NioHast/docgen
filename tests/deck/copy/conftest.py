"""Fixture dan builder untuk test copy checker dan transcript parser."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyBinding, KeyManifest, SlideIR
from autooffice.deck.transcript.model import TranscriptIR, TranscriptProse, TranscriptSection


def build_deck(
    *,
    language: str = "id",
    slides: Sequence[Mapping[str, Any]] = (),
) -> DeckIR:
    slide_irs: list[SlideIR] = []
    bindings: list[KeyBinding] = []
    for order, slide in enumerate(slides):
        slide_id = slide["id"]
        blocks: list[BlockIR] = []
        title = slide.get("title")
        if title is not None:
            blocks.append(
                BlockIR(
                    block_id="title",
                    block_type="text",
                    span=None,
                    role="title",
                    fields={"text": title},
                )
            )
            bindings.append(
                _binding(
                    key=f"{slide_id}.title.text",
                    slide_id=slide_id,
                    block_id="title",
                    leaf="text",
                    kind="text",
                    value=title,
                )
            )
        for block in slide.get("blocks", ()):
            block_ir, block_bindings = _block(slide_id, block)
            blocks.append(block_ir)
            bindings.extend(block_bindings)
        notes = slide.get("notes")
        if notes is not None:
            bindings.insert(
                0,
                _binding(
                    key=f"{slide_id}.notes",
                    slide_id=slide_id,
                    block_id=None,
                    leaf="notes",
                    kind="notes",
                    value=notes,
                ),
            )
        slide_irs.append(
            SlideIR(
                slide_id=slide_id,
                layout="custom",
                order=order,
                blocks=tuple(blocks),
                notes=notes,
                source=None,
            )
        )
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Fixture", "author": "Test", "language": language},
        theme_name="indigo",
        slides=tuple(slide_irs),
        keys=KeyManifest(bindings=tuple(bindings)),
    )


def build_transcript(
    sections: Sequence[Mapping[str, Any]],
    *,
    source: str = "transcripts.md",
) -> TranscriptIR:
    section_irs: list[TranscriptSection] = []
    for section in sections:
        english = section.get("en")
        section_irs.append(
            TranscriptSection(
                slide_id=section["slide_id"],
                title=section.get("title", "Judul"),
                indonesian=TranscriptProse(section["id"], line=section.get("line", 1)),
                english=(
                    TranscriptProse(english, line=section.get("en_line", 1))
                    if english is not None
                    else None
                ),
                duration_seconds=section.get("duration"),
                heading_line=section.get("heading_line", 1),
            )
        )
    return TranscriptIR(sections=tuple(section_irs), source=source)


def _block(slide_id: str, block: Mapping[str, Any]) -> tuple[BlockIR, list[KeyBinding]]:
    block_id = block["id"]
    block_type = block["type"]
    bindings: list[KeyBinding] = []
    if block_type == "text":
        fields: dict[str, object] = {"text": block["text"]}
        bindings.append(
            _binding(
                key=f"{slide_id}.{block_id}.text",
                slide_id=slide_id,
                block_id=block_id,
                leaf="text",
                kind="text",
                value=block["text"],
            )
        )
        if "heading" in block:
            fields["heading"] = block["heading"]
            bindings.append(
                _binding(
                    key=f"{slide_id}.{block_id}.heading",
                    slide_id=slide_id,
                    block_id=block_id,
                    leaf="heading",
                    kind="text",
                    value=block["heading"],
                )
            )
        return (
            BlockIR(
                block_id=block_id,
                block_type=block_type,
                span=block.get("span"),
                role=block.get("role"),
                fields=fields,
            ),
            bindings,
        )
    if block_type == "bullets":
        items = tuple(block["items"])
        for index, item in enumerate(items, start=1):
            bindings.append(
                _binding(
                    key=f"{slide_id}.{block_id}.item{index}.text",
                    slide_id=slide_id,
                    block_id=block_id,
                    leaf=f"item{index}.text",
                    kind="text",
                    value=item,
                )
            )
        return (
            BlockIR(
                block_id=block_id,
                block_type=block_type,
                span=block.get("span"),
                role=block.get("role"),
                fields={"items": items, "ordered": False},
            ),
            bindings,
        )
    if block_type == "chart":
        title = block["title"]
        bindings.append(
            _binding(
                key=f"{slide_id}.{block_id}.title",
                slide_id=slide_id,
                block_id=block_id,
                leaf="title",
                kind="text",
                value=title,
            )
        )
        return (
            BlockIR(
                block_id=block_id,
                block_type=block_type,
                span=block.get("span"),
                role=block.get("role"),
                fields={
                    "kind": "bar",
                    "title": title,
                    "alt": "Alt chart",
                    "categories": (),
                    "series": (),
                },
            ),
            bindings,
        )
    raise AssertionError(f"Block type test tidak didukung: {block_type}")


def _binding(
    *,
    key: str,
    slide_id: str,
    block_id: str | None,
    leaf: str,
    kind: str,
    value: str,
) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,  # type: ignore[arg-type]
        sync=True,
        yaml_path=("slides", slide_id, leaf),
        value=value,
        plain_text=value,
    )


@pytest.fixture
def make_deck() -> Callable[..., DeckIR]:
    """Builder DeckIR minimal untuk test copy checker."""
    return build_deck


@pytest.fixture
def make_transcript() -> Callable[..., TranscriptIR]:
    """Builder TranscriptIR minimal untuk test checker."""
    return build_transcript
