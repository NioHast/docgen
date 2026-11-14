"""Test discovery preset deterministik tanpa fallback nama layout."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from autooffice.deck.layout.registry import (
    LayoutRegistryError,
    discover_layouts,
    layout_names,
    layout_registry,
    preset_layouts,
)


def _preset_source(layout_id: str) -> str:
    return (
        "from autooffice.deck.layout.spec import LayoutSpec, SlotSpec\n"
        "\n"
        f"LAYOUT = LayoutSpec(\n"
        f"    layout_id={layout_id!r},\n"
        "    slots=(SlotSpec(slot_id='title', required=True, "
        "block_types=('text',), role='title'),),\n"
        "    rows=(('title',),),\n"
        "    accepts_source=False,\n"
        ")\n"
    )


def _write_package(
    tmp_path: Path,
    package: str,
    modules: Mapping[str, str],
) -> None:
    package_dir = tmp_path / package
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    for module, source in modules.items():
        (package_dir / f"{module}.py").write_text(source, encoding="utf-8")


def test_empty_package_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _write_package(tmp_path, "empty_layout_presets", {})
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(LayoutRegistryError, match="tidak memuat satu pun LAYOUT"):
        discover_layouts("empty_layout_presets")

    with pytest.raises(LayoutRegistryError, match="tidak memuat satu pun LAYOUT"):
        layout_registry("empty_layout_presets")

    with pytest.raises(LayoutRegistryError, match="tidak memuat satu pun LAYOUT"):
        layout_names("empty_layout_presets")


def test_discovery_sorts_by_layout_id_not_module_name(tmp_path: Path, monkeypatch) -> None:
    _write_package(
        tmp_path,
        "sorted_layout_presets",
        {
            "a_module": _preset_source("zeta"),
            "z_module": _preset_source("alpha"),
            "helper": "VALUE = 1\n",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    layouts = discover_layouts("sorted_layout_presets")

    assert tuple(layout.layout_id for layout in layouts) == ("alpha", "zeta")
    assert preset_layouts("sorted_layout_presets") == layouts
    assert tuple(layout_registry("sorted_layout_presets")) == ("alpha", "zeta")
    assert layout_names("sorted_layout_presets") == ("alpha", "zeta", "custom")


def test_duplicate_layout_ids_are_rejected(tmp_path: Path, monkeypatch) -> None:
    _write_package(
        tmp_path,
        "duplicate_layout_presets",
        {
            "first": _preset_source("same"),
            "second": _preset_source("same"),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(LayoutRegistryError, match="duplikat"):
        discover_layouts("duplicate_layout_presets")


def test_layout_must_be_a_layout_spec(tmp_path: Path, monkeypatch) -> None:
    _write_package(
        tmp_path,
        "invalid_layout_presets",
        {"broken": "LAYOUT = object()\n"},
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(LayoutRegistryError, match="bukan LayoutSpec"):
        discover_layouts("invalid_layout_presets")
