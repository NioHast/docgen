"""Model IR deck, slide, block, dan manifest key."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

KeyKind = Literal["text", "data", "notes", "source", "media_text"]

# Disalin dari layout custom agar model tidak mengimpor layout.
_CUSTOM_LAYOUT = "custom"


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
    """Satu slide tervalidasi beserta block, rows custom, notes, dan sumbernya."""

    slide_id: str
    layout: str
    order: int
    blocks: tuple[BlockIR, ...]
    notes: str | None
    source: Mapping[str, str] | None
    rows: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        self._validate_rows()
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

    def _validate_rows(self) -> None:
        """Pastikan rows merujuk block slide tanpa duplikat."""
        if not self.rows:
            return
        block_ids = {block.block_id for block in self.blocks}
        seen: set[str] = set()
        for row_index, row in enumerate(self.rows):
            if not row:
                raise ValueError(
                    f"SlideIR.rows slide '{self.slide_id}' memuat row {row_index} tanpa block ID."
                )
            for block_id in row:
                if block_id not in block_ids:
                    raise ValueError(
                        f"SlideIR.rows slide '{self.slide_id}' memuat block ID '{block_id}' "
                        "yang tidak ada di blocks."
                    )
                if block_id in seen:
                    raise ValueError(
                        f"SlideIR.rows slide '{self.slide_id}' menduplikasi block ID '{block_id}'."
                    )
                seen.add(block_id)
        if self.layout != _CUSTOM_LAYOUT:
            return
        missing = [block.block_id for block in self.blocks if block.block_id not in seen]
        if missing:
            raise ValueError(
                f"SlideIR.rows slide '{self.slide_id}' layout custom harus memuat setiap block "
                f"tepat satu kali; hilang: {', '.join(missing)}."
            )


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
