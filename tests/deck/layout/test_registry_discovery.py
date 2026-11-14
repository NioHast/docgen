"""Test discovery preset: modul privat, package hilang, dan import gagal."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from autooffice.deck.layout.registry import (
    LayoutRegistryError,
    discover_layouts,
    layout_names,
    layout_registry,
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


def test_private_modules_are_skipped(tmp_path: Path, monkeypatch) -> None:
    _write_package(
        tmp_path,
        "private_layout_presets",
        {
            "_hidden": _preset_source("hidden"),
            "public": _preset_source("public"),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    layouts = discover_layouts("private_layout_presets")

    assert tuple(layout.layout_id for layout in layouts) == ("public",)


def test_missing_package_is_reported() -> None:
    with pytest.raises(LayoutRegistryError, match="tidak dapat diimpor"):
        discover_layouts("layout_presets_that_do_not_exist")


def test_module_without_package_path_is_rejected(tmp_path: Path, monkeypatch) -> None:
    module = tmp_path / "plain_layout_presets.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(LayoutRegistryError, match="bukan package preset"):
        discover_layouts("plain_layout_presets")


def test_preset_import_error_is_reported(tmp_path: Path, monkeypatch) -> None:
    _write_package(
        tmp_path,
        "broken_layout_presets",
        {"broken": "import missing_dependency_for_layout_test\n"},
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(LayoutRegistryError, match="tidak dapat diimpor"):
        discover_layouts("broken_layout_presets")


def test_discovery_is_deterministic_and_sorted(tmp_path: Path, monkeypatch) -> None:
    _write_package(
        tmp_path,
        "stable_layout_presets",
        {
            "b_module": _preset_source("beta"),
            "a_module": _preset_source("alpha"),
            "c_module": _preset_source("gamma"),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    first = discover_layouts("stable_layout_presets")
    second = discover_layouts("stable_layout_presets")

    assert first == second
    assert tuple(layout.layout_id for layout in first) == ("alpha", "beta", "gamma")
    assert tuple(layout_registry("stable_layout_presets")) == ("alpha", "beta", "gamma")


def test_custom_preset_is_not_duplicated_in_layout_names(tmp_path: Path, monkeypatch) -> None:
    _write_package(
        tmp_path,
        "custom_layout_presets",
        {
            "cover": _preset_source("cover"),
            "custom": _preset_source("custom"),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    assert layout_names("custom_layout_presets") == ("cover", "custom")
