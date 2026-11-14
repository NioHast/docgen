"""Fixture minimal renderer PPTX: deck, layout EMU tetap, dan aset gambar."""

from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock, SlideLayout
from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyKind,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.model.schema import ChartSeries
from autooffice.design.theme import Theme, resolve_theme

SLIDE_ID = "s01"


@dataclass(frozen=True)
class RenderCase:
    """Satu deck uji beserta layout plan EMU tetap dan workspace render."""

    deck: DeckIR
    layout: LayoutPlan
    workspace: Path


@pytest.fixture(scope="session")
def theme() -> Theme:
    """Theme indigo hasil resolusi token."""
    return resolve_theme("indigo")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Workspace build di bawah ``tmp_path``."""
    path = tmp_path / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def hero_image(workspace: Path) -> str:
    """Gambar PNG kecil relatif terhadap workspace."""
    assets = workspace / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 200), (30, 60, 90)).save(assets / "hero.png")
    return "assets/hero.png"


def binding(
    key: str,
    *,
    slide_id: str = SLIDE_ID,
    block_id: str | None,
    leaf: str,
    kind: KeyKind = "text",
) -> KeyBinding:
    """Bangun binding manifest deterministik untuk fixture."""
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, leaf),
        value="nilai",
        plain_text="nilai",
    )


def table_bindings(block_id: str, columns: int, rows: int) -> list[KeyBinding]:
    """Binding header dan sel tabel."""
    result = [
        binding(f"{SLIDE_ID}.{block_id}.h{index}", block_id=block_id, leaf=f"h{index}")
        for index in range(1, columns + 1)
    ]
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            leaf = f"r{row}.c{column}"
            result.append(binding(f"{SLIDE_ID}.{block_id}.{leaf}", block_id=block_id, leaf=leaf))
    return result


@pytest.fixture
def minimal_case(workspace: Path, hero_image: str) -> RenderCase:
    """Deck dua slide berisi text, bullets, table, image, notes, dan source."""
    blocks = (
        BlockIR("title", "text", None, "title", {"text": "Judul deck"}),
        BlockIR("body", "bullets", None, None, {"items": ("Satu", "Dua"), "ordered": False}),
        BlockIR(
            "table1",
            "table",
            None,
            None,
            {
                "columns": ("Lane", "Deliverable", "Status"),
                "rows": (
                    ("Model", "Skema", "Selesai"),
                    ("PPTX", "Native", "42"),
                ),
                "caption": "Status lane",
            },
        ),
        BlockIR(
            "image1",
            "image",
            None,
            None,
            {
                "path": hero_image,
                "alt": "Tim meninjau arsitektur",
                "fit": "cover",
                "caption": "Sesi desain",
            },
        ),
    )
    bindings = [
        binding("s01.title.text", block_id="title", leaf="text"),
        binding("s01.body.item1.text", block_id="body", leaf="item1.text"),
        binding("s01.body.item2.text", block_id="body", leaf="item2.text"),
        *table_bindings("table1", 3, 2),
        binding("s01.table1.caption", block_id="table1", leaf="caption"),
        binding("s01.image1.caption", block_id="image1", leaf="caption", kind="media_text"),
        KeyBinding(
            key="s01.notes",
            slide_id="s01",
            block_id=None,
            leaf="notes",
            kind="notes",
            sync=True,
            yaml_path=("slides", 0, "notes"),
            value="Catatan pembicara",
            plain_text="Catatan pembicara",
        ),
        KeyBinding(
            key="s01.source.text",
            slide_id="s01",
            block_id=None,
            leaf="source.text",
            kind="source",
            sync=True,
            yaml_path=("slides", 0, "source", "text"),
            value="Sumber: data internal",
            plain_text="Sumber: data internal",
        ),
        KeyBinding(
            key="s02.title.text",
            slide_id="s02",
            block_id="title",
            leaf="text",
            kind="text",
            sync=True,
            yaml_path=("slides", 1, "blocks", 0, "text"),
            value="Slide dua",
            plain_text="Slide dua",
        ),
    ]
    slides = (
        SlideIR(
            "s01",
            "content",
            0,
            blocks,
            "Catatan pembicara untuk slide satu.",
            {"text": "Sumber: data internal, 2026", "url": "https://example.com/data"},
        ),
        SlideIR(
            "s02",
            "content",
            1,
            (BlockIR("title", "text", None, "title", {"text": "Slide dua"}),),
            None,
            None,
        ),
    )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Minimal Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=slides,
        keys=KeyManifest(tuple(bindings)),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (
                    PlacedBlock("title", 914400, 609600, 10363200, 700000),
                    PlacedBlock("body", 914400, 1400000, 5000000, 2800000),
                    PlacedBlock("table1", 6000000, 1400000, 5200000, 2800000),
                    PlacedBlock("image1", 914400, 4600000, 5000000, 1500000),
                ),
                (),
            ),
            SlideLayout(
                "s02",
                (PlacedBlock("title", 914400, 609600, 10363200, 700000),),
                (),
            ),
        )
    )
    return RenderCase(deck=deck, layout=layout, workspace=workspace)


@pytest.fixture
def chart_case(workspace: Path) -> RenderCase:
    """Deck satu slide dengan chart placeholder F1."""
    block = BlockIR(
        "chart1",
        "chart",
        None,
        None,
        {
            "kind": "line",
            "title": "Adopsi per kuartal",
            "alt": "Grafik garis adopsi naik setiap kuartal",
            "categories": ("Q1", "Q2"),
            "series": (ChartSeries("2025", (1, 2)), ChartSeries("2026", (3, 4))),
            "caption": "Target internal",
        },
    )
    leaves = (
        "title",
        "cat1",
        "cat2",
        "series1.name",
        "series1.value1",
        "series1.value2",
        "series2.name",
        "series2.value1",
        "series2.value2",
        "caption",
    )
    bindings = [
        binding(
            f"s01.chart1.{leaf}",
            block_id="chart1",
            leaf=leaf,
            kind="data" if leaf.startswith(("cat", "series")) else "text",
        )
        for leaf in leaves
    ]
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Chart Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "line", 0, (block,), None, None),),
        keys=KeyManifest(tuple(bindings)),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (PlacedBlock("chart1", 914400, 609600, 10363200, 4000000),),
                (),
            ),
        )
    )
    return RenderCase(deck=deck, layout=layout, workspace=workspace)


@pytest.fixture
def missing_manifest_case(workspace: Path) -> RenderCase:
    """Deck dengan satu text box yang tidak punya key di manifest."""
    block = BlockIR("title", "text", None, "title", {"text": "Tanpa key"})
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Missing Manifest", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (block,), None, None),),
        keys=KeyManifest(()),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (PlacedBlock("title", 914400, 609600, 10363200, 700000),),
                (),
            ),
        )
    )
    return RenderCase(deck=deck, layout=layout, workspace=workspace)


@pytest.fixture
def missing_alt_case(workspace: Path, hero_image: str) -> RenderCase:
    """Deck dengan gambar yang alt text-nya kosong."""
    block = BlockIR(
        "image1",
        "image",
        None,
        None,
        {"path": hero_image, "alt": "", "fit": "contain"},
    )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Missing Alt", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (block,), None, None),),
        keys=KeyManifest(()),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (PlacedBlock("image1", 914400, 609600, 5000000, 1500000),),
                (),
            ),
        )
    )
    return RenderCase(deck=deck, layout=layout, workspace=workspace)
