"""Loader YAML strict untuk deck AutoOffice v1."""

from itertools import islice
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.composer import MaxDepthExceededError
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import AliasEvent

from .schema import DeckDefinition, DeckSchemaError, validate_deck

# Batas keamanan YAML. Deck normal (termasuk demo 24 slide) jauh di bawah
# batas ini; nilai ini menolak berkas besar, alias bomb, dan nesting ekstrem.
MAX_DECK_BYTES = 5 * 1024 * 1024
MAX_DECK_DOCUMENTS = 1
MAX_DECK_ALIASES = 100
MAX_DECK_NESTING_DEPTH = 64
_SIZE_HINT = "Pindahkan aset biner ke berkas terpisah atau pecah deck."


class DeckLoadError(DeckSchemaError):
    """Berkas YAML tidak dapat dibaca atau bukan satu dokumen deck."""


def _check_deck_size(size: int, *, source_name: str, unit: str) -> None:
    if size > MAX_DECK_BYTES:
        raise DeckLoadError(
            f"{source_name}: ukuran deck {size} {unit} melebihi batas "
            f"{MAX_DECK_BYTES} {unit} ({MAX_DECK_BYTES // (1024 * 1024)} MiB). "
            f"{_SIZE_HINT}"
        )


def _check_yaml_aliases(text: str, *, source_name: str) -> None:
    """Hitung alias YAML tanpa membangun objek Python."""

    yaml = YAML(typ="safe", pure=True)
    count = 0
    try:
        for event in yaml.parse(text):
            if not isinstance(event, AliasEvent):
                continue
            count += 1
            if count > MAX_DECK_ALIASES:
                raise DeckLoadError(
                    f"{source_name}: jumlah alias YAML melebihi batas "
                    f"{MAX_DECK_ALIASES}; hapus anchor/alias berulang atau pecah deck."
                )
    except YAMLError as error:
        raise DeckLoadError(f"{source_name}: YAML tidak valid: {error}") from error


def load_deck(path: str | Path, *, base_dir: str | Path | None = None) -> DeckDefinition:
    """Baca satu berkas ``deck.yaml`` UTF-8 dan validasi schema-nya."""
    deck_path = Path(path)
    if not deck_path.is_file():
        raise DeckLoadError(f"Berkas deck tidak ditemukan: {deck_path}")
    try:
        with deck_path.open("rb") as handle:
            raw_bytes = handle.read(MAX_DECK_BYTES + 1)
    except OSError as error:
        raise DeckLoadError(f"Berkas deck tidak dapat dibaca: {deck_path}: {error}") from error
    if len(raw_bytes) > MAX_DECK_BYTES:
        _check_deck_size(len(raw_bytes), source_name=str(deck_path), unit="byte")
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DeckLoadError(f"Berkas deck harus UTF-8: {deck_path}: {error}") from error
    text = text.removeprefix("﻿")
    deck_root = deck_path.parent
    return loads_deck(
        text,
        base_dir=base_dir if base_dir is not None else deck_root,
        source_name=str(deck_path),
    )


def loads_deck(
    text: str,
    *,
    base_dir: str | Path | None = None,
    source_name: str = "<deck>",
) -> DeckDefinition:
    """Load satu dokumen YAML dari string dengan safe loader."""
    if not isinstance(text, str):
        raise DeckLoadError(f"{source_name}: input YAML harus string.")
    text = text.removeprefix("﻿")
    if len(text) > MAX_DECK_BYTES:
        _check_deck_size(len(text), source_name=source_name, unit="karakter")
    _check_deck_size(
        len(text.encode("utf-8")),
        source_name=source_name,
        unit="byte",
    )
    _check_yaml_aliases(text, source_name=source_name)

    yaml = YAML(typ="safe", pure=True)
    yaml.allow_duplicate_keys = False
    yaml.max_depth = MAX_DECK_NESTING_DEPTH
    try:
        documents: list[object] = list(islice(yaml.load_all(text), MAX_DECK_DOCUMENTS + 1))
    except MaxDepthExceededError as error:
        raise DeckLoadError(
            f"{source_name}: kedalaman struktur YAML melebihi batas "
            f"{MAX_DECK_NESTING_DEPTH}; ratakan struktur deck atau pecah slide."
        ) from error
    except YAMLError as error:
        raise DeckLoadError(f"{source_name}: YAML tidak valid: {error}") from error
    if len(documents) > MAX_DECK_DOCUMENTS:
        raise DeckLoadError(
            f"{source_name}: deck harus berisi tepat satu dokumen YAML, "
            f"bukan lebih dari {MAX_DECK_DOCUMENTS}."
        )
    if len(documents) != 1:
        raise DeckLoadError(
            f"{source_name}: deck harus berisi tepat satu dokumen YAML, bukan {len(documents)}."
        )
    document = documents[0]
    if document is None:
        raise DeckLoadError(f"{source_name}: deck tidak boleh kosong.")
    try:
        return validate_deck(document, base_dir=base_dir)
    except DeckSchemaError as error:
        raise DeckLoadError(
            f"{source_name}: {error.message}",
            path=error.path,
            slide_id=error.slide_id,
            block_id=error.block_id,
            key=error.key,
        ) from error


def load_deck_object(
    data: object,
    *,
    base_dir: str | Path | None = None,
) -> DeckDefinition:
    """Validasi objek Python yang sudah diparse sebagai deck."""
    return validate_deck(data, base_dir=base_dir)
