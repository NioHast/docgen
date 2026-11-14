"""Kontrak renderer deck."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from autooffice.deck.layout.spec import LayoutPlan
from autooffice.deck.model.deck_ir import DeckIR
from autooffice.design.theme import Theme


class OutputTarget(StrEnum):
    """Target output yang didukung renderer deck."""

    PPTX = "pptx"
    PDF = "pdf"
    SLIDES = "slides"


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Ringkasan coverage key, teks tanpa key, dan alt text."""

    missing_keys: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    unkeyed_visible: tuple[str, ...]
    missing_alt: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Kembalikan ``True`` bila tidak ada temuan coverage."""
        return not (
            self.missing_keys or self.duplicate_keys or self.unkeyed_visible or self.missing_alt
        )


@dataclass(frozen=True, slots=True)
class RenderRequest:
    """Input lengkap satu operasi render."""

    deck: DeckIR
    layout: LayoutPlan
    theme: Theme
    target: OutputTarget
    workspace: Path


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Hasil satu operasi render beserta bukti coverage."""

    artifact_path: Path
    coverage: CoverageReport
    warnings: tuple[str, ...]
    content_hash: str
    target_metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_metadata", MappingProxyType(dict(self.target_metadata)))


class DeckRenderer(Protocol):
    """Kontrak renderer yang menerima satu ``RenderRequest``."""

    def render(self, request: RenderRequest) -> RenderResult:
        """Render deck lalu kembalikan hasil artefak dan coverage."""
        ...
