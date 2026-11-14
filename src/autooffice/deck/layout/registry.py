"""Registry layout dengan discovery preset deterministik.

Registry memindai package ``autooffice.deck.layout.presets`` untuk modul yang
mengekspos ``LAYOUT: LayoutSpec``. Hasil diurutkan berdasarkan ``layout_id``.
Package tanpa satu pun preset ditolak; tidak ada fallback nama layout.
"""

import importlib
import pkgutil
from collections.abc import Mapping, Sequence
from types import MappingProxyType, ModuleType
from typing import cast

from autooffice.deck.layout.spec import LayoutError, LayoutSpec

PRESETS_PACKAGE = "autooffice.deck.layout.presets"
CUSTOM_LAYOUT = "custom"


class LayoutRegistryError(LayoutError):
    """Package preset tidak bisa dipindai, modul tidak valid, atau ID duplikat."""


def discover_layouts(package: str = PRESETS_PACKAGE) -> tuple[LayoutSpec, ...]:
    """Temukan seluruh ``LAYOUT`` preset dan urutkan berdasarkan layout_id."""
    package_module = _import_package(package)
    found: list[LayoutSpec] = []
    for info in sorted(
        pkgutil.iter_modules(_package_paths(package_module)), key=lambda item: item.name
    ):
        if info.name.startswith("_"):
            continue
        module_name = f"{package}.{info.name}"
        module = _import_preset(module_name)
        layout = getattr(module, "LAYOUT", None)
        if layout is None:
            continue
        if not isinstance(layout, LayoutSpec):
            raise LayoutRegistryError(
                f"Modul preset '{module_name}' mengekspos LAYOUT bertipe "
                f"{type(layout).__name__}, bukan LayoutSpec."
            )
        found.append(layout)

    if not found:
        raise LayoutRegistryError(
            f"Package preset '{package}' tidak memuat satu pun LAYOUT; "
            "registry memerlukan minimal satu preset."
        )
    found.sort(key=lambda layout: layout.layout_id)
    duplicates = _duplicate_layout_ids(found)
    if duplicates:
        raise LayoutRegistryError("Layout ID preset duplikat: " + ", ".join(duplicates) + ".")
    return tuple(found)


def preset_layouts(package: str = PRESETS_PACKAGE) -> tuple[LayoutSpec, ...]:
    """Alias eksplisit untuk :func:`discover_layouts`."""
    return discover_layouts(package)


def layout_registry(package: str = PRESETS_PACKAGE) -> Mapping[str, LayoutSpec]:
    """Kembalikan mapping layout_id ke ``LayoutSpec`` yang deterministik."""
    return MappingProxyType({layout.layout_id: layout for layout in discover_layouts(package)})


def layout_names(package: str = PRESETS_PACKAGE) -> tuple[str, ...]:
    """Kembalikan nama layout valid untuk schema.

    Nama preset diurutkan berdasarkan ``layout_id`` dan ``custom`` tetap
    tersedia sebagai layout non-preset. Package tanpa preset ditolak oleh
    :func:`discover_layouts`; tidak ada fallback nama.
    """
    layouts = discover_layouts(package)
    names = tuple(layout.layout_id for layout in layouts if layout.layout_id != CUSTOM_LAYOUT)
    return (*names, CUSTOM_LAYOUT)


def _import_package(package: str) -> ModuleType:
    try:
        return importlib.import_module(package)
    except ImportError as exc:
        raise LayoutRegistryError(f"Package preset '{package}' tidak dapat diimpor: {exc}") from exc


def _package_paths(package: ModuleType) -> list[str]:
    paths = getattr(package, "__path__", None)
    if not isinstance(paths, list):
        raise LayoutRegistryError(f"'{package.__name__}' bukan package preset yang valid.")
    return cast("list[str]", paths)


def _import_preset(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise LayoutRegistryError(
            f"Modul preset '{module_name}' tidak dapat diimpor: {exc}"
        ) from exc


def _duplicate_layout_ids(layouts: Sequence[LayoutSpec]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for layout in layouts:
        if layout.layout_id in seen:
            duplicates.add(layout.layout_id)
        seen.add(layout.layout_id)
    return tuple(sorted(duplicates))
