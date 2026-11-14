"""Grammar key datar, registry key, dan binding deck AutoOffice v1."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from autooffice.errors import AutoOfficeError

from .deck_ir import KeyBinding, KeyManifest

MAX_KEY_LENGTH = 160
MAX_BLOCK_ID_LENGTH = 32

SLIDE_ID_PATTERN = re.compile(r"^s[0-9]{2,}$")
BLOCK_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
LEAF_SEGMENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_INDEXED_SEGMENT_PATTERN = re.compile(r"^(?:item|cat|series|value|r|c|h)(\d+)$")
_SLIDE_LEAVES = frozenset({"notes", "source.text"})


class KeyGrammarError(AutoOfficeError):
    """Key, ID, atau binding tidak memenuhi grammar yang dibekukan."""


@dataclass(frozen=True, slots=True)
class ParsedKey:
    """Hasil pemecahan satu key datar menjadi komponennya."""

    key: str
    slide_id: str
    block_id: str | None
    leaf: str


def validate_slide_id(value: str) -> str:
    """Validasi slide ID ``^s[0-9]{2,}$``."""
    if not isinstance(value, str):
        raise KeyGrammarError("Slide ID harus string.")
    if not SLIDE_ID_PATTERN.fullmatch(value):
        raise KeyGrammarError(f"Slide ID '{value}' harus cocok dengan pola ^s[0-9]{{2,}}$.")
    return value


def validate_block_id(value: str) -> str:
    """Validasi block ID, panjang, dan larangan titik."""
    if not isinstance(value, str):
        raise KeyGrammarError("Block ID harus string.")
    if not BLOCK_ID_PATTERN.fullmatch(value):
        raise KeyGrammarError(f"Block ID '{value}' harus cocok dengan pola ^[a-z][a-z0-9_]*$.")
    if len(value) > MAX_BLOCK_ID_LENGTH:
        raise KeyGrammarError(f"Block ID '{value}' melebihi {MAX_BLOCK_ID_LENGTH} karakter.")
    if "." in value:  # pragma: no cover - regex di atas sudah menolak titik
        raise KeyGrammarError(f"Block ID '{value}' tidak boleh memuat titik.")
    return value


def validate_leaf(leaf: str) -> str:
    """Validasi satu leaf lengkap, termasuk indeks 1-based."""
    if not isinstance(leaf, str) or not leaf:
        raise KeyGrammarError("Leaf key tidak boleh kosong.")
    segments = leaf.split(".")
    if any(not segment for segment in segments):
        raise KeyGrammarError(f"Leaf '{leaf}' memiliki segmen kosong.")
    for segment in segments:
        if not LEAF_SEGMENT_PATTERN.fullmatch(segment):
            raise KeyGrammarError(
                f"Segmen leaf '{segment}' hanya boleh huruf kecil, angka, dan underscore."
            )
        indexed = _INDEXED_SEGMENT_PATTERN.fullmatch(segment)
        if indexed is not None and int(indexed.group(1)) < 1:
            raise KeyGrammarError(f"Indeks leaf '{segment}' harus 1-based, bukan 0.")
    return leaf


def make_key(slide_id: str, block_id: str | None, leaf: str) -> str:
    """Bentuk key datar dari slide, block, dan leaf yang sudah valid."""
    validate_slide_id(slide_id)
    validate_leaf(leaf)
    if block_id is None:
        if leaf not in _SLIDE_LEAVES:
            raise KeyGrammarError(
                f"Leaf slide '{leaf}' tidak dikenal; hanya notes dan source.text."
            )
        key = f"{slide_id}.{leaf}"
    else:
        validate_block_id(block_id)
        key = f"{slide_id}.{block_id}.{leaf}"
    if len(key) > MAX_KEY_LENGTH:
        raise KeyGrammarError(
            f"Key '{key}' melebihi {MAX_KEY_LENGTH} karakter; schema harus disederhanakan."
        )
    return key


def parse_key(key: str) -> ParsedKey:
    """Pecah key datar menjadi slide ID, block ID opsional, dan leaf."""
    _validate_key_text(key)
    parts = key.split(".")
    slide_id = validate_slide_id(parts[0])
    if len(parts) == 2:
        if parts[1] != "notes":
            raise KeyGrammarError(f"Key '{key}' bukan key slide yang dikenal.")
        return ParsedKey(key=key, slide_id=slide_id, block_id=None, leaf="notes")
    if len(parts) == 3 and parts[1] == "source" and parts[2] == "text":
        return ParsedKey(key=key, slide_id=slide_id, block_id=None, leaf="source.text")
    block_id = validate_block_id(parts[1])
    leaf = validate_leaf(".".join(parts[2:]))
    return ParsedKey(key=key, slide_id=slide_id, block_id=block_id, leaf=leaf)


def validate_key(key: str) -> str:
    """Validasi key datar terhadap grammar dan batas panjang."""
    parse_key(key)
    return key


def _validate_key_text(key: str) -> None:
    if not isinstance(key, str):
        raise KeyGrammarError("Key harus string.")
    if not key:
        raise KeyGrammarError("Key tidak boleh kosong.")
    if len(key) > MAX_KEY_LENGTH:
        raise KeyGrammarError(
            f"Key '{key}' melebihi {MAX_KEY_LENGTH} karakter; schema harus disederhanakan."
        )


class KeyRegistry:
    """Kumpulan binding unik yang deterministik untuk satu build deck."""

    def __init__(self) -> None:
        self._bindings: list[KeyBinding] = []
        self._by_key: dict[str, KeyBinding] = {}
        self._by_yaml_path: dict[tuple[str | int, ...], KeyBinding] = {}

    @property
    def bindings(self) -> tuple[KeyBinding, ...]:
        """Kembalikan binding sesuai urutan penambahan."""
        return tuple(self._bindings)

    @property
    def keys(self) -> tuple[str, ...]:
        """Kembalikan key sesuai urutan penambahan."""
        return tuple(binding.key for binding in self._bindings)

    def add(self, binding: KeyBinding) -> None:
        """Tambahkan satu binding dan tolak duplikasi."""
        self._validate_binding(binding)
        existing = self._by_key.get(binding.key)
        if existing is not None:
            raise KeyGrammarError(
                f"Key duplikat '{binding.key}' pada {_format_yaml_path(binding.yaml_path)} "
                f"dan {_format_yaml_path(existing.yaml_path)}."
            )
        yaml_path = tuple(binding.yaml_path)
        existing_path = self._by_yaml_path.get(yaml_path)
        if existing_path is not None:
            raise KeyGrammarError(
                f"yaml_path duplikat {_format_yaml_path(yaml_path)} untuk key "
                f"'{existing_path.key}' dan '{binding.key}'."
            )
        self._bindings.append(binding)
        self._by_key[binding.key] = binding
        self._by_yaml_path[yaml_path] = binding

    def extend(self, bindings: Iterable[KeyBinding]) -> None:
        """Tambahkan beberapa binding dalam urutan yang diberikan."""
        for binding in bindings:
            self.add(binding)

    def manifest(self) -> KeyManifest:
        """Kembalikan manifest immutable dari binding yang sudah ditambahkan."""
        return KeyManifest(bindings=tuple(self._bindings))

    def _validate_binding(self, binding: KeyBinding) -> None:
        if not isinstance(binding.key, str) or not binding.key:
            raise KeyGrammarError("Binding harus memiliki key yang tidak kosong.")
        parsed = parse_key(binding.key)
        if binding.block_id is not None and parsed.block_id != binding.block_id:
            raise KeyGrammarError(
                f"Binding '{binding.key}' memiliki block_id '{binding.block_id}' yang tidak "
                f"cocok dengan hasil parse_key ({parsed.block_id!r})."
            )
        expected_key = make_key(binding.slide_id, binding.block_id, binding.leaf)
        if expected_key != binding.key:
            raise KeyGrammarError(
                f"Binding key '{binding.key}' tidak cocok dengan pemiliknya; seharusnya "
                f"'{expected_key}'."
            )
        if isinstance(binding.value, bool) or not isinstance(binding.value, str | int | float):
            raise KeyGrammarError(
                f"Binding '{binding.key}' memiliki value yang bukan string atau angka."
            )
        if not isinstance(binding.plain_text, str) or not binding.plain_text.strip():
            raise KeyGrammarError(f"Binding '{binding.key}' memiliki plain_text kosong.")
        if not isinstance(binding.yaml_path, tuple) or not binding.yaml_path:
            raise KeyGrammarError(f"Binding '{binding.key}' harus memiliki yaml_path.")
        if binding.kind not in {"text", "data", "notes", "source", "media_text"}:
            raise KeyGrammarError(f"Binding '{binding.key}' memiliki kind tidak dikenal.")


def _format_yaml_path(path: tuple[str | int, ...]) -> str:
    parts: list[str] = []
    for segment in path:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        elif parts:
            parts.append(f".{segment}")
        else:
            parts.append(segment)
    return "".join(parts) or "deck"
