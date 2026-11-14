"""Fixture bersama test lane Google: deck nyata dan fake in-memory."""

import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from autooffice.deck.charts import ChartSpec, build_chart_spec
from autooffice.deck.model import DeckIR, compile_deck_file
from autooffice.design import resolve_theme
from autooffice.design.theme import Theme
from autooffice.google.fake import FakeGoogleServices
from autooffice.google.slides import (
    ElementSize,
    ElementTransform,
    PageElement,
    PresentationSnapshot,
    SlideSnapshot,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "google"


@dataclass(frozen=True, slots=True)
class SnapshotOptions:
    """Opsi pembentuk snapshot fake untuk skenario preflight."""

    include_chart_placeholders: bool = True
    include_tables: bool = True
    table_kind: str = "table"
    table_rows: int | None = None
    table_columns: int | None = None


@pytest.fixture(scope="session")
def google_fixture_dir() -> Path:
    """Direktori fixture Google."""
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def google_deck_path() -> Path:
    """Path deck fixture Google."""
    return FIXTURE_DIR / "deck.yaml"


@pytest.fixture(scope="session")
def google_deck(google_deck_path: Path) -> DeckIR:
    """Deck fixture yang sudah dikompilasi."""
    return compile_deck_file(google_deck_path)


@pytest.fixture(scope="session")
def google_theme() -> Theme:
    """Theme indigo untuk chart Sheets."""
    return resolve_theme("indigo")


@pytest.fixture(scope="session")
def chart_specs(google_deck: DeckIR) -> Mapping[str, ChartSpec]:
    """Chart spec fixture berdasarkan chart_id logis."""
    result: dict[str, ChartSpec] = {}
    for slide in google_deck.slides:
        for block in slide.blocks:
            if block.block_type == "chart":
                spec = build_chart_spec(block, slide_id=slide.slide_id)
                result[spec.chart_id] = spec
    return result


@pytest.fixture
def make_snapshot(
    google_deck: DeckIR,
) -> Callable[..., PresentationSnapshot]:
    """Factory snapshot presentasi lengkap dengan placeholder, table, dan notes."""

    def factory(
        *,
        presentation_id: str = "presentation-1",
        title: str = "F2 Google",
        revision_id: str | None = "revision-1",
        options: SnapshotOptions | None = None,
    ) -> PresentationSnapshot:
        settings = SnapshotOptions() if options is None else options
        slides: list[SlideSnapshot] = []
        for slide in google_deck.slides:
            page_object_id = f"slide-{slide.slide_id}"
            elements: list[PageElement] = []
            for block in slide.blocks:
                if block.block_type == "text":
                    text = str(block.fields.get("text", ""))
                    elements.append(
                        PageElement(
                            object_id=f"shape-{slide.slide_id}-{block.block_id}",
                            page_object_id=page_object_id,
                            kind="shape",
                            title=f"{slide.slide_id}.{block.block_id}.text",
                            text=text,
                        )
                    )
                elif block.block_type == "table" and settings.include_tables:
                    columns = block.fields["columns"]
                    rows = block.fields["rows"]
                    assert isinstance(columns, tuple)
                    assert isinstance(rows, tuple)
                    header = tuple(str(column) for column in columns)
                    body = tuple(tuple(str(cell) for cell in row) for row in rows)
                    elements.append(
                        PageElement(
                            object_id=f"table-{slide.slide_id}-{block.block_id}",
                            page_object_id=page_object_id,
                            kind="table" if settings.table_kind == "table" else settings.table_kind,
                            title=f"{slide.slide_id}.{block.block_id}",
                            row_count=(
                                len(rows) + 1
                                if settings.table_rows is None
                                else settings.table_rows
                            ),
                            column_count=(
                                len(columns)
                                if settings.table_columns is None
                                else settings.table_columns
                            ),
                            cells=(header, *body),
                        )
                    )
                elif block.block_type == "chart" and settings.include_chart_placeholders:
                    elements.append(
                        PageElement(
                            object_id=f"chart-{slide.slide_id}-{block.block_id}",
                            page_object_id=page_object_id,
                            kind="shape",
                            title=f"autooffice:chart:{slide.slide_id}.{block.block_id}",
                            size=ElementSize(width=4_000_000, height=2_500_000),
                            transform=ElementTransform(
                                scale_x=1.0,
                                scale_y=1.0,
                                translate_x=914_400.0,
                                translate_y=914_400.0,
                            ),
                        )
                    )
                caption = block.fields.get("caption")
                if isinstance(caption, str) and caption:
                    elements.append(
                        PageElement(
                            object_id=f"caption-{slide.slide_id}-{block.block_id}",
                            page_object_id=page_object_id,
                            kind="shape",
                            title=f"{slide.slide_id}.{block.block_id}.caption",
                            text=caption,
                        )
                    )
            notes_elements: list[PageElement] = []
            if slide.notes:
                notes_elements.append(
                    PageElement(
                        object_id=f"notes-{slide.slide_id}",
                        page_object_id=f"notes-page-{slide.slide_id}",
                        kind="shape",
                        title=f"{slide.slide_id}.notes",
                        text=slide.notes,
                    )
                )
            if slide.source:
                elements.append(
                    PageElement(
                        object_id=f"source-{slide.slide_id}",
                        page_object_id=page_object_id,
                        kind="shape",
                        title=f"{slide.slide_id}.source.text",
                        text=slide.source["text"],
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
            title=title,
            revision_id=revision_id,
            slides=tuple(slides),
        )

    return factory


@pytest.fixture
def fake_google(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> FakeGoogleServices:
    """Fake Drive/Slides/Sheets yang saling terhubung."""

    def converter(_path: Path, _name: str, presentation_id: str) -> PresentationSnapshot:
        return make_snapshot(presentation_id=presentation_id)

    return FakeGoogleServices.create(converter=converter)


@pytest.fixture
def deck_copy(tmp_path: Path, google_deck_path: Path) -> Path:
    """Salinan deck di tmp_path agar test apply tidak menyentuh fixture."""
    destination = tmp_path / "deck.yaml"
    shutil.copyfile(google_deck_path, destination)
    return destination
