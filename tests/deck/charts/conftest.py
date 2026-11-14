"""Fixture bersama untuk test chart spec, native PPTX, dan placeholder."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

import pytest
from pptx import Presentation
from pptx.slide import Slide

from autooffice.deck.charts.spec import ChartSpec, build_chart_spec
from autooffice.deck.model import BlockIR, ChartSeries, DeckIR, compile_deck_file
from autooffice.design.theme import Theme, resolve_theme

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "charts"
CHART_BOX = {"left": 914400, "top": 914400, "width": 7315200, "height": 4572000}


@pytest.fixture(scope="session")
def charts_fixture_dir() -> Path:
    """Direktori fixture chart milik lane F2-CHARTS."""
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def chart_deck() -> DeckIR:
    """Deck fixture chart yang sudah dikompilasi menjadi IR."""
    return compile_deck_file(FIXTURE_DIR / "charts.yaml")


@pytest.fixture(scope="session")
def chart_specs(chart_deck: DeckIR) -> Mapping[str, ChartSpec]:
    """Seluruh chart spec fixture, dipetakan berdasarkan ``chart_id``."""
    specs: dict[str, ChartSpec] = {}
    for slide in chart_deck.slides:
        for block in slide.blocks:
            if block.block_type == "chart":
                chart_id = f"{slide.slide_id}.{block.block_id}"
                specs[chart_id] = build_chart_spec(block, slide_id=slide.slide_id)
    return MappingProxyType(specs)


@pytest.fixture(params=("indigo", "hitam"), ids=("indigo", "hitam"))
def theme(request: pytest.FixtureRequest) -> Theme:
    """Theme indigo dan hitam hasil resolusi token."""
    return resolve_theme(str(request.param))


@pytest.fixture
def presentation() -> Presentation:
    """Presentasi kosong in-memory; tidak menyentuh file atau template eksternal."""
    return Presentation()


@pytest.fixture
def slide(presentation: Presentation) -> Slide:
    """Slide kosong dari layout blank untuk chart native atau placeholder."""
    return presentation.slides.add_slide(presentation.slide_layouts[6])


@pytest.fixture
def chart_box() -> Mapping[str, int]:
    """Box chart deterministik dalam EMU, setara satu slot layout."""
    return MappingProxyType(dict(CHART_BOX))


@pytest.fixture
def chart_block_factory() -> Callable[..., BlockIR]:
    """Factory block chart dengan default valid untuk test batas spec."""

    def factory(
        *,
        kind: str = "bar",
        categories: Sequence[object] = ("Q1", "Q2"),
        series: Sequence[object] | None = None,
        title: object = "Judul chart",
        alt: object = "Alt chart untuk pembaca layar",
        orientation: object = None,
        unit: object = None,
        block_id: str = "chart1",
    ) -> BlockIR:
        fields: dict[str, object] = {
            "kind": kind,
            "title": title,
            "alt": alt,
            "categories": tuple(categories),
            "series": (
                (ChartSeries(name="Seri 1", values=(10, 20)),) if series is None else tuple(series)
            ),
        }
        if orientation is not None:
            fields["orientation"] = orientation
        if unit is not None:
            fields["unit"] = unit
        return BlockIR(
            block_id=block_id,
            block_type="chart",
            span=12,
            role=None,
            fields=fields,
        )

    return factory
