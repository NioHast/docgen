"""Kontrak satu block type deck."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockSpec:
    """Field dan key yang dihasilkan satu block type."""

    block_type: str
    required: tuple[str, ...]
    optional: tuple[str, ...]
    key_leaves: tuple[str, ...]
    allowed_in_preset: bool
