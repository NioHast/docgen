"""Fixture deck, fake Google, dan aset untuk test CLI AutoOffice."""

from pathlib import Path

import pytest
from PIL import Image

import autooffice.pdf
from autooffice.deck.model import compile_deck_file
from autooffice.google.fake import FakeGoogleServices
from autooffice.google.slides import (
    ElementSize,
    ElementTransform,
    PageElement,
    PresentationSnapshot,
    SlideSnapshot,
)

BASE_DECK = """schema: autooffice.deck/v1

meta:
  title: "Deck Uji Build"
  author: "Tim AutoOffice"
  language: "id"

theme:
  name: indigo

defaults:
  layout: content
  image_fit: contain
  code_language: text

slides:
  - id: s01
    layout: content
    notes: |
      Catatan pembicara slide pertama.
    source:
      text: "Sumber: data internal."
    blocks:
      - id: title
        type: text
        role: title
        text: "Ringkasan Build"
      - id: points
        type: bullets
        items:
          - "Model data stabil."
          - "Layout tanpa overflow."
  - id: s02
    layout: table
    blocks:
      - id: title
        type: text
        role: title
        text: "Tabel Status"
      - id: table1
        type: table
        columns: ["Aspek", "Status"]
        rows:
          - ["Model", "Selesai"]
          - ["Render", "Berjalan"]
        caption: "Status terkini."
  - id: s03
    layout: bars
    blocks:
      - id: title
        type: text
        role: title
        text: "Chart Kunjungan"
      - id: chart1
        type: chart
        kind: bar
        title: "Kunjungan per kanal"
        alt: "Diagram batang kunjungan per kanal"
        categories: ["Organik", "Referral"]
        series:
          - name: "Kunjungan"
            values: [10, 5]
        caption: "Data contoh."
  - id: s04
    layout: image-split
    blocks:
      - id: title
        type: text
        role: title
        text: "Gambar Kerja"
      - id: body
        type: text
        role: body
        text: "Ruang kerja dengan meja rapi."
      - id: image1
        type: image
        path: "{image_path}"
        alt: "Meja kerja dengan laptop"
        caption: "Meja kerja."
"""

DIAGRAM_SLIDE = """  - id: s05
    layout: diagram
    blocks:
      - id: title
        type: text
        role: title
        text: "Alur Proses"
      - id: subtitle
        type: text
        role: lead
        text: "Diagram alur proses."
      - id: diagram1
        type: diagram
        source: "{diagram_path}"
        alt: "Diagram alur proses build"
        caption: "Alur proses."
"""

CUSTOM_SLIDE = """  - id: s06
    layout: custom
    rows:
      - blocks:
          - id: title
            type: text
            role: title
            text: "Slide Custom"
            span: 12
      - blocks:
          - id: body
            type: text
            role: body
            text: "Grid custom dengan satu gambar."
            span: 6
          - id: image1
            type: image
            path: "assets/hero.png"
            alt: "Gambar pada slide custom"
            caption: "Gambar custom."
            span: 6
"""

BASE_TRANSCRIPT = """# Transkrip Deck Uji Build

## s01. Ringkasan Build
### Indonesia
Deck ini menjadi contoh build.

## s02. Tabel Status
### Indonesia
Tabel ini memuat status terkini.

## s03. Chart Kunjungan
### Indonesia
Chart ini memuat data contoh.

## s04. Gambar Kerja
### Indonesia
Gambar ini memuat meja kerja.
"""

DIAGRAM_TRANSCRIPT = """
## s05. Alur Proses
### Indonesia
Diagram ini memuat alur proses.
"""

CUSTOM_TRANSCRIPT = """
## s06. Slide Custom
### Indonesia
Slide ini memakai grid custom.
"""

INCOMPLETE_TRANSCRIPT = """# Transkrip Tidak Lengkap

## s01. Ringkasan Build
### Indonesia
Bagian ini hanya memuat satu slide.
"""


def _write_deck(
    root: Path,
    *,
    image_path: str = "assets/hero.png",
    diagram_path: str = "diagrams/flow.mmd",
    include_diagram: bool = False,
    include_custom: bool = False,
    transcript: str = BASE_TRANSCRIPT,
) -> Path:
    assets = root / "assets"
    diagrams = root / "diagrams"
    assets.mkdir(parents=True, exist_ok=True)
    diagrams.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 180), (30, 60, 90)).save(assets / "hero.png")
    (diagrams / "flow.mmd").write_text("flowchart LR\n  A --> B\n", encoding="utf-8")
    text = BASE_DECK.format(image_path=image_path)
    if include_diagram:
        text += DIAGRAM_SLIDE.format(diagram_path=diagram_path)
        transcript += DIAGRAM_TRANSCRIPT
    if include_custom:
        text += CUSTOM_SLIDE
        transcript += CUSTOM_TRANSCRIPT
    deck = root / "deck.yaml"
    deck.write_text(text, encoding="utf-8")
    (root / "transcripts.md").write_text(transcript, encoding="utf-8")
    return deck


@pytest.fixture(autouse=True)
def fake_font_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Jangan sentuh PowerPoint COM di test CLI; embedding diuji di tests/pdf."""

    def fake_embed(path: Path) -> Path:
        return Path(path)

    monkeypatch.setattr(autooffice.pdf, "embed_pptx_fonts", fake_embed)


@pytest.fixture
def deck_path(tmp_path: Path) -> Path:
    """Deck kecil berisi text, table, chart, image, notes, dan source."""
    return _write_deck(tmp_path / "base")


@pytest.fixture
def all_types_deck_path(tmp_path: Path) -> Path:
    """Deck kecil dengan tambahan block diagram dan layout custom."""
    return _write_deck(tmp_path / "all-types", include_diagram=True, include_custom=True)


@pytest.fixture
def missing_asset_deck_path(tmp_path: Path) -> Path:
    """Deck dengan gambar yang tidak ada di direktori deck."""
    return _write_deck(tmp_path / "missing-asset", image_path="assets/missing.png")


@pytest.fixture
def missing_diagram_deck_path(tmp_path: Path) -> Path:
    """Deck dengan diagram yang tidak ada di direktori deck."""
    return _write_deck(
        tmp_path / "missing-diagram",
        include_diagram=True,
        diagram_path="diagrams/missing.mmd",
    )


@pytest.fixture
def incomplete_transcript_deck_path(tmp_path: Path) -> Path:
    """Deck dengan transkrip yang tidak memuat seluruh slide."""
    return _write_deck(tmp_path / "incomplete-transcript", transcript=INCOMPLETE_TRANSCRIPT)


def _fake_google_for(deck_path: Path) -> FakeGoogleServices:
    deck = compile_deck_file(deck_path)

    def converter(_path: Path, name: str, presentation_id: str) -> PresentationSnapshot:
        slides: list[SlideSnapshot] = []
        for slide in deck.slides:
            page_object_id = f"slide-{slide.slide_id}"
            elements: list[PageElement] = []
            notes_elements: list[PageElement] = []
            tables = {
                block.block_id: block for block in slide.blocks if block.block_type == "table"
            }
            charts = {
                block.block_id: block for block in slide.blocks if block.block_type == "chart"
            }
            added_tables: set[str] = set()
            added_charts: set[str] = set()
            for binding in deck.keys.bindings:
                if binding.slide_id != slide.slide_id:
                    continue
                block_id = binding.block_id
                if block_id in tables:
                    block = tables[block_id]
                    if block_id not in added_tables:
                        columns = block.fields["columns"]
                        rows = block.fields["rows"]
                        assert isinstance(columns, tuple)
                        assert isinstance(rows, tuple)
                        header = tuple(str(column) for column in columns)
                        body = tuple(tuple(str(cell) for cell in row) for row in rows)
                        elements.append(
                            PageElement(
                                object_id=f"table-{slide.slide_id}-{block_id}",
                                page_object_id=page_object_id,
                                kind="table",
                                title=f"{slide.slide_id}.{block_id}",
                                row_count=len(rows) + 1,
                                column_count=len(columns),
                                cells=(header, *body),
                            )
                        )
                        added_tables.add(block_id)
                    if binding.leaf == "caption":
                        elements.append(
                            PageElement(
                                object_id=f"shape-{slide.slide_id}-{block_id}-caption",
                                page_object_id=page_object_id,
                                kind="shape",
                                title=binding.key,
                                text=binding.plain_text,
                            )
                        )
                    continue
                if block_id in charts:
                    if block_id not in added_charts:
                        elements.append(
                            PageElement(
                                object_id=f"chart-{slide.slide_id}-{block_id}",
                                page_object_id=page_object_id,
                                kind="shape",
                                title=f"autooffice:chart:{slide.slide_id}.{block_id}",
                                size=ElementSize(width=2_000_000, height=1_000_000),
                                transform=ElementTransform(),
                            )
                        )
                        added_charts.add(block_id)
                    if binding.leaf == "caption":
                        elements.append(
                            PageElement(
                                object_id=f"shape-{slide.slide_id}-{block_id}-caption",
                                page_object_id=page_object_id,
                                kind="shape",
                                title=binding.key,
                                text=binding.plain_text,
                            )
                        )
                    continue
                if binding.leaf == "notes":
                    notes_elements.append(
                        PageElement(
                            object_id=f"notes-{slide.slide_id}",
                            page_object_id=f"notes-{slide.slide_id}",
                            kind="shape",
                            title=binding.key,
                            text=str(binding.plain_text),
                        )
                    )
                    continue
                leaf = binding.leaf.replace(".", "-")
                elements.append(
                    PageElement(
                        object_id=f"shape-{slide.slide_id}-{block_id or 'slide'}-{leaf}",
                        page_object_id=page_object_id,
                        kind="shape",
                        title=binding.key,
                        text=str(binding.plain_text),
                    )
                )
            slides.append(
                SlideSnapshot(
                    object_id=page_object_id,
                    index=slide.order,
                    page_elements=tuple(elements),
                    notes_page_elements=tuple(notes_elements),
                )
            )
        return PresentationSnapshot(
            presentation_id=presentation_id,
            title=name,
            revision_id="revision-1",
            slides=tuple(slides),
        )

    return FakeGoogleServices.create(converter=converter)


@pytest.fixture
def fake_google(deck_path: Path) -> FakeGoogleServices:
    """Fake Google yang sudah terhubung ke deck fixture."""
    return _fake_google_for(deck_path)
