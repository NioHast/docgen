"""Model IR deck, slide, block, dan manifest key."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

KeyKind = Literal["text", "data", "notes", "source", "media_text"]


@dataclass(frozen=True, slots=True)
class KeyBinding:
    """Pemetaan dua arah antara satu key dan path YAML sumbernya."""

    key: str
    slide_id: str
    block_id: str | None
    leaf: str
    kind: KeyKind
    sync: bool
    yaml_path: tuple[str | int, ...]
    value: str | int | float
    plain_text: str


@dataclass(frozen=True, slots=True)
class KeyManifest:
    """Daftar binding key yang deterministik untuk satu build deck."""

    bindings: tuple[KeyBinding, ...]

    def keys(self) -> tuple[str, ...]:
        """Kembalikan seluruh key sesuai urutan binding."""
        return tuple(binding.key for binding in self.bindings)


@dataclass(frozen=True, slots=True)
class BlockIR:
    """Satu block tervalidasi pada slide."""

    block_id: str
    block_type: str
    span: int | None
    role: str | None
    fields: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True, slots=True)
class SlideIR:
    """Satu slide tervalidasi beserta block, notes, dan sumbernya."""

    slide_id: str
    layout: str
    order: int
    blocks: tuple[BlockIR, ...]
    notes: str | None
    source: Mapping[str, str] | None

    def __post_init__(self) -> None:
        if self.source is None:
            return
        source = dict(self.source)
        if "text" not in source:
            raise ValueError("SlideIR.source wajib memuat 'text'.")
        unexpected = set(source) - {"text", "url"}
        if unexpected:
            raise ValueError(
                f"SlideIR.source hanya menerima 'text' dan 'url', bukan {sorted(unexpected)}."
            )
        object.__setattr__(self, "source", MappingProxyType(source))


@dataclass(frozen=True, slots=True)
class DeckIR:
    """IR deck lengkap yang siap masuk layout engine."""

    schema: str
    meta: Mapping[str, str]
    theme_name: str
    slides: tuple[SlideIR, ...]
    keys: KeyManifest

    def __post_init__(self) -> None:
        object.__setattr__(self, "meta", MappingProxyType(dict(self.meta)))
        for index, slide in enumerate(self.slides):
            if slide.order != index:
                raise ValueError(
                    f"Slide {slide.slide_id} memiliki order {slide.order}; seharusnya {index}."
                )
