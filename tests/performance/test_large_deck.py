"""Tes performa dan skala deck besar: kompilasi, key, plan, dan render smoke."""

import time
from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation

from autooffice.deck.layout.overflow import plan_deck
from autooffice.deck.layout.spec import LayoutPlan
from autooffice.deck.model import DeckIR, compile_deck_file
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.protocol import OutputTarget, RenderRequest
from autooffice.design.theme import Theme, resolve_theme

LARGE_SLIDE_COUNT = 100
SMALL_SLIDE_COUNT = 1
SLOW_COMPILE_SLIDE_COUNT = 500
RENDER_SLIDE_COUNT = 10

WALL_CLOCK_LIMIT_SECONDS = 15.0
SLOW_COMPILE_LIMIT_SECONDS = 30.0
LINEARITY_TOLERANCE = 0.05

_HEADER = """\
schema: autooffice.deck/v1
meta:
  title: "{title}"
  author: "AutoOffice"
  language: "id"
theme:
  name: indigo
defaults:
  layout: content
  image_fit: contain
  code_language: text
slides:
"""


def _slide_yaml(index: int) -> str:
    """Satu slide custom dengan teks, bullets, tabel, chart, gambar, dan notes."""
    slide_id = f"s{index:03d}"
    return f"""\
  - id: {slide_id}
    layout: custom
    notes: |
      Catatan pembicara untuk slide {slide_id}.
      Deck besar tetap deterministik dan offline.
    rows:
      - blocks:
          - {{id: title, type: text, role: title, text: "Ringkasan {index}", span: 12}}
      - blocks:
          - {{id: lead, type: text, role: lead, text: "Konten campuran.", span: 12}}
      - blocks:
          - id: points
            type: bullets
            span: 4
            items:
              - "Butir pertama {index}"
              - "Butir kedua {index}"
          - id: table1
            type: table
            span: 8
            columns: ["Metrik", "Nilai"]
            rows:
              - ["Slide", "{index}"]
              - ["Key", "21"]
            caption: "Tabel ringkas"
      - blocks:
          - id: chart1
            type: chart
            span: 7
            kind: bar
            title: "Tren singkat"
            alt: "Diagram batang tren singkat"
            categories: ["Q1", "Q2", "Q3"]
            series:
              - name: "2026"
                values: [10, 20, 30]
            unit: "unit"
          - id: image1
            type: image
            span: 5
            path: "assets/pixel.png"
            alt: "Gambar referensi kecil"
            caption: "Gambar referensi"
"""


def _deck_yaml(slide_count: int, *, title: str) -> str:
    """Bangun YAML deck dengan jumlah slide yang seragam."""
    return _HEADER.format(title=title) + "".join(
        _slide_yaml(index) for index in range(1, slide_count + 1)
    )


def _write_deck(directory: Path, slide_count: int, *, title: str) -> Path:
    """Tulis deck YAML dan aset gambar kecil di ``directory``."""
    assets = directory / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), (40, 80, 120)).save(assets / "pixel.png")
    path = directory / "deck.yaml"
    path.write_text(_deck_yaml(slide_count, title=title), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def theme() -> Theme:
    """Theme indigo hasil resolusi token."""
    return resolve_theme("indigo")


@pytest.fixture(scope="module")
def large_deck_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Deck 100 slide di ``tmp_path`` untuk pemeriksaan skala."""
    root = tmp_path_factory.mktemp("large-deck")
    return _write_deck(root, LARGE_SLIDE_COUNT, title="Large Deck 100")


@pytest.fixture(scope="module")
def small_deck_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Deck satu slide dengan bentuk konten yang sama."""
    root = tmp_path_factory.mktemp("small-deck")
    return _write_deck(root, SMALL_SLIDE_COUNT, title="Small Deck 1")


@pytest.fixture(scope="module")
def large_deck(large_deck_path: Path) -> DeckIR:
    """Deck 100 slide yang sudah dikompilasi."""
    return compile_deck_file(large_deck_path)


@pytest.fixture(scope="module")
def large_plan(large_deck: DeckIR, theme: Theme) -> LayoutPlan:
    """Layout plan untuk seluruh slide deck 100 slide."""
    return plan_deck(large_deck, theme)


@pytest.mark.slow
def test_large_deck_compile_and_plan_stays_within_wall_clock_budget(
    large_deck_path: Path,
    theme: Theme,
) -> None:
    """Kompilasi dan layout 100 slide selesai dalam batas waktu longgar."""
    started = time.perf_counter()
    deck = compile_deck_file(large_deck_path)
    plan = plan_deck(deck, theme)
    elapsed = time.perf_counter() - started

    assert len(deck.slides) == LARGE_SLIDE_COUNT
    assert len(plan.slides) == LARGE_SLIDE_COUNT
    assert elapsed < WALL_CLOCK_LIMIT_SECONDS, f"compile+plan memakan {elapsed:.2f} detik"
    assert all(slide.overflow_keys == () for slide in plan.slides)


@pytest.mark.slow
def test_key_count_scales_linearly_with_slide_count(
    large_deck: DeckIR,
    small_deck_path: Path,
) -> None:
    """Manifest key deck 100 slide kira-kira 100 kali manifest satu slide."""
    small_deck = compile_deck_file(small_deck_path)
    small_count = len(small_deck.keys.bindings)
    large_count = len(large_deck.keys.bindings)

    assert small_count > 0
    ratio = large_count / small_count
    assert ratio == pytest.approx(LARGE_SLIDE_COUNT, rel=LINEARITY_TOLERANCE)


@pytest.mark.slow
def test_key_manifest_has_no_duplicate_keys(large_deck: DeckIR) -> None:
    """Seluruh key pada deck besar tetap unik."""
    keys = large_deck.keys.keys()

    assert keys
    assert len(keys) == len(set(keys))


@pytest.mark.slow
def test_compile_and_plan_are_deterministic(
    large_deck: DeckIR,
    large_plan: LayoutPlan,
    large_deck_path: Path,
    theme: Theme,
) -> None:
    """Dua run compile dan plan menghasilkan IR serta plan yang identik."""
    second_deck = compile_deck_file(large_deck_path)
    second_plan = plan_deck(second_deck, theme)

    assert second_deck == large_deck
    assert second_deck.keys.keys() == large_deck.keys.keys()
    assert second_plan == large_plan


def test_single_slide_compile_and_plan_smoke(
    small_deck_path: Path,
    theme: Theme,
) -> None:
    """Smoke cepat yang tetap berjalan pada default ``-m 'not slow'``."""
    deck = compile_deck_file(small_deck_path)
    plan = plan_deck(deck, theme)

    assert len(deck.slides) == SMALL_SLIDE_COUNT
    assert len(plan.slides) == SMALL_SLIDE_COUNT
    assert plan.slides[0].overflow_keys == ()


@pytest.mark.slow
def test_500_slide_deck_compiles_within_budget(tmp_path: Path) -> None:
    """Smoke kompilasi 500 slide tanpa layout plan atau render."""
    deck_path = _write_deck(tmp_path, SLOW_COMPILE_SLIDE_COUNT, title="Large Deck 500")

    started = time.perf_counter()
    deck = compile_deck_file(deck_path)
    elapsed = time.perf_counter() - started

    keys = deck.keys.keys()
    assert len(deck.slides) == SLOW_COMPILE_SLIDE_COUNT
    assert len(keys) == len(set(keys))
    assert elapsed < SLOW_COMPILE_LIMIT_SECONDS, f"compile memakan {elapsed:.2f} detik"


@pytest.mark.slow
def test_ten_slide_deck_renders_to_pptx(tmp_path: Path, theme: Theme) -> None:
    """Smoke render 10 slide memastikan jalur PPTX tetap berfungsi."""
    deck_path = _write_deck(tmp_path, RENDER_SLIDE_COUNT, title="Render Smoke")
    deck = compile_deck_file(deck_path)
    plan = plan_deck(deck, theme)

    result = PptxRenderer().render(
        RenderRequest(
            deck=deck,
            layout=plan,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=tmp_path,
        )
    )
    presentation = Presentation(str(result.artifact_path))

    assert len(presentation.slides) == RENDER_SLIDE_COUNT
    assert result.coverage.ok
    assert result.artifact_path.is_file()
