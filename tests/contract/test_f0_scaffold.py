"""Tes kontrak scaffold F0 AutoOffice."""

from pathlib import Path

import pytest

import autooffice
from autooffice.cli.main import main
from autooffice.deck.blocks.registry import block_names, block_specs
from autooffice.deck.layout.registry import discover_layouts, layout_names
from autooffice.deck.layout.spec import LayoutPlan
from autooffice.deck.model.deck_ir import DeckIR, KeyManifest

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_PRESET_LAYOUTS: tuple[str, ...] = (
    "cover",
    "toc",
    "content",
    "section",
    "closing",
    "kpi",
    "bars",
    "line",
    "donut",
    "table",
    "comparison",
    "matrix",
    "background",
    "flow",
    "code",
    "diagram",
    "image-split",
    "image-full",
    "image-grid",
)

EXPECTED_LAYOUTS: tuple[str, ...] = (*EXPECTED_PRESET_LAYOUTS, "custom")

EXPECTED_BLOCKS: tuple[str, ...] = (
    "text",
    "bullets",
    "image",
    "table",
    "chart",
    "code",
    "quote",
    "diagram",
    "divider",
    "spacer",
    "metric",
)


def test_package_version() -> None:
    assert autooffice.__version__ == "0.1.0"


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0


def test_main_returns_zero() -> None:
    assert main([]) == 0


def test_block_registry_has_exact_eleven_names() -> None:
    assert block_names() == EXPECTED_BLOCKS
    assert len(set(block_names())) == 11
    assert tuple(spec.block_type for spec in block_specs()) == EXPECTED_BLOCKS


def test_layout_registry_has_exact_nineteen_presets_plus_custom() -> None:
    discovered = {layout.layout_id for layout in discover_layouts()}
    names = layout_names()

    assert discovered == set(EXPECTED_PRESET_LAYOUTS)
    assert len(EXPECTED_PRESET_LAYOUTS) == 19
    assert "custom" not in EXPECTED_PRESET_LAYOUTS
    assert set(names) == set(EXPECTED_LAYOUTS)
    assert len(names) == 20
    assert len(set(names)) == 20
    assert tuple(names[:-1]) == tuple(sorted(discovered))
    assert names[-1] == "custom"


def test_gitignore_ignores_autooffice_workspaces() -> None:
    rules = {
        line.strip() for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    assert ".autooffice/" in rules
    assert ".autooffice-build/" in rules


def test_ir_is_constructible_with_empty_slides() -> None:
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={},
        theme_name="indigo",
        slides=(),
        keys=KeyManifest(bindings=()),
    )
    plan = LayoutPlan(slides=())

    assert deck.slides == ()
    assert deck.keys.keys() == ()
    assert plan.slides == ()
