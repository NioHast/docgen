"""Registry layout dengan discovery preset deterministik.

F1-LAYOUT memindai package ``autooffice.deck.layout.presets`` untuk modul yang
mengekspos ``LAYOUT: LayoutSpec``. Hasil diurutkan berdasarkan ``layout_id``.
Bila package belum berisi satu pun modul preset, registry memakai fallback nama
katalog F0 agar schema tetap bisa memvalidasi nama layout selama transisi.
"""

import importlib
import pkgutil
from collections.abc import Mapping, Sequence
from types import MappingProxyType, ModuleType
from typing import cast

from autooffice.deck.layout.spec import LayoutError, LayoutSpec

PRESETS_PACKAGE = "autooffice.deck.layout.presets"
CUSTOM_LAYOUT = "custom"

F0_LAYOUT_NAMES: tuple[str, ...] = (
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
    "custom",
)

# Nama lama dipertahankan agar import privat F0 tidak langsung rusak.
_LAYOUT_NAMES = F0_LAYOUT_NAMES


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

    Bila belum ada preset yang ditemukan, fallback F0 mengembalikan katalog
    lengkap dalam urutan katalog. Bila discovery menemukan preset, nama
    diurutkan berdasarkan ``layout_id`` dan ``custom`` tetap tersedia.
    """
    layouts = discover_layouts(package)
    if not layouts:
        return F0_LAYOUT_NAMES
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
