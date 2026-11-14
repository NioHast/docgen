"""Schema dan merge konfigurasi ``copy.yaml`` AutoOffice v1.

Berkas ini adalah satu-satunya tempat yang membaca bentuk ``copy.yaml``.
Schema bersifat strict: key yang tidak dikenal, severity yang tidak valid,
allowlist tanpa alasan, dan ``extra`` yang bukan daftar frasa literal ditolak.
Tanpa berkas, seluruh rule memakai default yang dibekukan di sini.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from autooffice.deck.model.schema import DeckSchemaError
from autooffice.deck.model.schema import Language as Language
from autooffice.deck.model.schema import normalize_language as _normalize_model_language
from autooffice.errors import AutoOfficeError

Severity = Literal["error", "warning"]
SeveritySetting = Literal["error", "warning", "off"]

COPY_SCHEMA_VERSION = 1
DEFAULT_MAX_WORDS = 25
RULE_NAMES: tuple[str, ...] = (
    "banned_phrases",
    "title_case",
    "dash",
    "sentence_length",
    "negative_parallelism",
    "contrast_pattern",
    "forced_triad",
    "one_line_closer",
    "paired_clause_label",
)
DEFAULT_SEVERITIES: Mapping[str, Severity] = MappingProxyType(
    {
        "banned_phrases": "error",
        "title_case": "error",
        "dash": "error",
        "sentence_length": "warning",
        "negative_parallelism": "error",
        "contrast_pattern": "error",
        "forced_triad": "warning",
        "one_line_closer": "warning",
        "paired_clause_label": "warning",
    }
)
DEFAULT_RULE_SEVERITIES = DEFAULT_SEVERITIES
_VALID_SEVERITIES = frozenset({"error", "warning", "off"})
_ROOT_FIELDS = ("schema", "targets", "rules", "allow")
_TARGET_FIELDS = ("slides", "notes", "transcript")
_EXTRA_FIELDS = ("id", "en")
_ALLOW_FIELDS = ("key", "rules", "reason")


class CopyConfigError(AutoOfficeError):
    """``copy.yaml`` atau nilai konfigurasi copy melanggar kontrak v1."""

    def __init__(
        self,
        message: str,
        *,
        path: tuple[str | int, ...] = (),
        source: str | None = "copy.yaml",
    ) -> None:
        self.message = message
        self.path = path
        self.source = source
        location = _format_path(path)
        if source and location:
            prefix = f"{source}: {location}"
        elif source:
            prefix = source
        elif location:
            prefix = location
        else:
            prefix = "copy"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True, slots=True)
class RuleConfig:
    """Konfigurasi efektif satu rule setelah merge dengan default."""

    name: str
    severity: SeveritySetting
    enabled: bool = True
    max_words: int | None = None
    extra: Mapping[Language, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.name not in RULE_NAMES:
            raise CopyConfigError(f"Rule '{self.name}' tidak dikenal.")
        if self.severity not in _VALID_SEVERITIES:
            raise CopyConfigError(f"Severity '{self.severity}' tidak valid.")
        if not isinstance(self.enabled, bool):
            raise CopyConfigError("Field 'enabled' harus boolean.")
        if self.max_words is not None and (
            isinstance(self.max_words, bool)
            or not isinstance(self.max_words, int)
            or self.max_words <= 0
        ):
            raise CopyConfigError("Field 'max_words' harus bilangan bulat positif.")
        extra = {language: tuple(phrases) for language, phrases in self.extra.items()}
        object.__setattr__(self, "extra", MappingProxyType(extra))

    @property
    def active(self) -> bool:
        """True bila rule tidak dimatikan lewat ``enabled`` atau ``severity``."""
        return self.enabled and self.severity != "off"

    @property
    def diagnostic_severity(self) -> Severity | None:
        """Severity efektif untuk diagnostic, atau None bila rule mati."""
        if not self.active:
            return None
        return cast(Severity, self.severity)

    def extra_for(self, language: Language) -> tuple[str, ...]:
        """Frasa literal tambahan untuk satu bahasa."""
        return self.extra.get(language, ())


@dataclass(frozen=True, slots=True)
class CopyTargets:
    """Target teks yang diperiksa copy checker."""

    slides: bool = True
    notes: bool = True
    transcript: bool = True


@dataclass(frozen=True, slots=True)
class AllowEntry:
    """Satu pengecualian diagnostic dengan alasan eksplisit."""

    key: str
    rules: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise CopyConfigError("Field 'allow.key' harus string tidak kosong.")
        if not self.rules:
            raise CopyConfigError(f"Allow key '{self.key}' wajib memuat minimal satu rule.")
        for rule in self.rules:
            if rule not in RULE_NAMES:
                raise CopyConfigError(
                    f"Allow key '{self.key}' memakai rule '{rule}' yang tidak dikenal."
                )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise CopyConfigError(f"Allow key '{self.key}' wajib memiliki reason.")
        object.__setattr__(self, "rules", tuple(self.rules))


def _default_rule_map() -> dict[str, RuleConfig]:
    rules: dict[str, RuleConfig] = {}
    for name in RULE_NAMES:
        max_words = DEFAULT_MAX_WORDS if name == "sentence_length" else None
        rules[name] = RuleConfig(
            name=name,
            severity=DEFAULT_SEVERITIES[name],
            max_words=max_words,
        )
    return rules


DEFAULT_RULES: Mapping[str, RuleConfig] = MappingProxyType(_default_rule_map())


@dataclass(frozen=True, slots=True)
class CopyConfig:
    """Konfigurasi copy checker yang sudah di-merge dengan default."""

    schema: int = COPY_SCHEMA_VERSION
    targets: CopyTargets = field(default_factory=CopyTargets)
    rules: Mapping[str, RuleConfig] = field(default_factory=_default_rule_map)
    allow: tuple[AllowEntry, ...] = ()

    def __post_init__(self) -> None:
        if self.schema != COPY_SCHEMA_VERSION:
            raise CopyConfigError(
                f"Schema copy '{self.schema}' tidak didukung; gunakan {COPY_SCHEMA_VERSION}."
            )
        merged = dict(DEFAULT_RULES)
        for name, rule in self.rules.items():
            if name not in DEFAULT_RULES:
                raise CopyConfigError(f"Rule '{name}' tidak dikenal.")
            if rule.name != name:
                raise CopyConfigError(f"Rule '{name}' memiliki nama internal '{rule.name}'.")
            merged[name] = rule
        object.__setattr__(self, "rules", MappingProxyType(merged))
        object.__setattr__(self, "allow", tuple(self.allow))

    def rule(self, name: str) -> RuleConfig:
        """Ambil konfigurasi satu rule yang sudah pasti ada."""
        try:
            return self.rules[name]
        except KeyError as error:
            raise CopyConfigError(f"Rule '{name}' tidak dikenal.") from error

    def active_rule(self, name: str) -> RuleConfig | None:
        """Ambil rule bila aktif, atau None bila dimatikan."""
        rule = self.rule(name)
        return rule if rule.active else None

    def allowed(self, key: str, rule: str) -> bool:
        """True bila allowlist menekan pasangan key dan rule ini."""
        return any(entry.key == key and rule in entry.rules for entry in self.allow)


DEFAULT_COPY_CONFIG = CopyConfig()


def normalize_language(value: object) -> Language:
    """Normalisasi BCP 47 sederhana ke ``id`` atau ``en``.

    ``id-ID`` menjadi ``id`` dan ``en-US`` menjadi ``en``. Bahasa lain ditolak
    tanpa fallback diam-diam.
    """
    try:
        return _normalize_model_language(value)
    except DeckSchemaError as error:
        raise CopyConfigError(error.message) from error


def load_copy_config(
    path: str | Path | None = None,
    *,
    deck_dir: str | Path | None = None,
) -> CopyConfig:
    """Baca ``copy.yaml`` UTF-8, atau kembalikan default bila path None.

    Path di-resolve terlebih dahulu. Bila ``deck_dir`` diberikan, berkas hasil
    resolve wajib berada di dalam folder deck tersebut; ``..`` pada path sumber
    tetap diterima selama hasil akhirnya berada di dalam folder deck. Bila
    ``deck_dir`` tidak diberikan (pemakaian API mandiri), path hanya
    di-resolve tanpa pemeriksaan containment.
    """
    if path is None:
        return DEFAULT_COPY_CONFIG
    source = Path(path)
    resolved = _resolve(source)
    if deck_dir is not None:
        root = _resolve(Path(deck_dir))
        if not resolved.is_relative_to(root):
            raise CopyConfigError(
                f"Path copy harus berada di folder deck yang sama; traversal ditolak: {source}",
                source=None,
            )
    if not resolved.is_file():
        raise CopyConfigError(f"Berkas copy tidak ditemukan: {source}", source=None)
    try:
        raw = resolved.read_bytes()
    except OSError as error:
        raise CopyConfigError(f"Berkas copy tidak dapat dibaca: {error}", source=None) from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CopyConfigError(f"Berkas copy harus UTF-8: {source}: {error}", source=None) from error
    return loads_copy_config(text, source_name=str(source))


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError) as error:
        raise CopyConfigError(
            f"Path copy tidak dapat di-resolve: {path}: {error}", source=None
        ) from error


def loads_copy_config(text: str, *, source_name: str = "copy.yaml") -> CopyConfig:
    """Parse dan validasi satu dokumen ``copy.yaml`` dari string."""
    if not isinstance(text, str):
        raise CopyConfigError("Input copy.yaml harus string.", source=source_name)
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    try:
        documents: list[object] = list(yaml.load_all(text))
    except YAMLError as error:
        raise CopyConfigError(f"YAML tidak valid: {error}", source=source_name) from error
    if not documents:
        raise CopyConfigError("copy.yaml tidak boleh kosong.", source=source_name)
    if len(documents) != 1:
        raise CopyConfigError(
            f"copy.yaml harus berisi tepat satu dokumen YAML, bukan {len(documents)}.",
            source=source_name,
        )
    document = documents[0]
    if document is None:
        raise CopyConfigError("copy.yaml tidak boleh kosong.", source=source_name)
    mapping = _require_mapping(document, path=(), context="copy.yaml", source=source_name)
    _check_fields(mapping, _ROOT_FIELDS, path=(), context="copy.yaml", source=source_name)

    schema = mapping.get("schema", COPY_SCHEMA_VERSION)
    if isinstance(schema, bool) or not isinstance(schema, int):
        raise CopyConfigError(
            "Field 'schema' harus bilangan bulat 1.", path=("schema",), source=source_name
        )
    if schema != COPY_SCHEMA_VERSION:
        raise CopyConfigError(
            f"Schema copy '{schema}' tidak didukung; gunakan {COPY_SCHEMA_VERSION}.",
            path=("schema",),
            source=source_name,
        )

    targets = _parse_targets(mapping.get("targets"), source=source_name)
    rules = _parse_rules(mapping.get("rules"), source=source_name)
    allow = _parse_allow(mapping.get("allow"), source=source_name)
    return CopyConfig(schema=schema, targets=targets, rules=rules, allow=allow)


def validate_allowlist(config: CopyConfig, known_keys: Iterable[str]) -> None:
    """Pastikan setiap allow key benar-benar ada pada deck atau transkrip."""
    keys = set(known_keys)
    for entry in config.allow:
        if entry.key not in keys:
            raise CopyConfigError(
                f"Allow key '{entry.key}' tidak ditemukan pada deck atau transkrip."
            )


def _parse_targets(value: object, *, source: str) -> CopyTargets:
    if value is None:
        return CopyTargets()
    mapping = _require_mapping(value, path=("targets",), context="targets", source=source)
    _check_fields(mapping, _TARGET_FIELDS, path=("targets",), context="targets", source=source)
    values: dict[str, bool] = {}
    for name in _TARGET_FIELDS:
        raw = mapping.get(name, True)
        if not isinstance(raw, bool):
            raise CopyConfigError(
                f"Field 'targets.{name}' harus boolean.",
                path=("targets", name),
                source=source,
            )
        values[name] = raw
    return CopyTargets(**values)


def _parse_rules(value: object, *, source: str) -> dict[str, RuleConfig]:
    rules = _default_rule_map()
    if value is None:
        return rules
    mapping = _require_mapping(value, path=("rules",), context="rules", source=source)
    for name, raw in mapping.items():
        if not isinstance(name, str) or name not in RULE_NAMES:
            raise CopyConfigError(
                f"Rule '{name}' tidak dikenal.",
                path=("rules", str(name)),
                source=source,
            )
        rules[name] = _parse_rule(name, raw, source=source)
    return rules


def _parse_rule(name: str, value: object, *, source: str) -> RuleConfig:
    default = DEFAULT_RULES[name]
    if value is None:
        return default
    path = ("rules", name)
    mapping = _require_mapping(value, path=path, context=f"rule {name}", source=source)
    allowed = {"severity", "enabled"}
    if name == "sentence_length":
        allowed.add("max_words")
    if name == "banned_phrases":
        allowed.add("extra")
    unknown = sorted(str(key) for key in set(mapping) - allowed)
    if unknown:
        raise CopyConfigError(
            f"Key {_format_keys(unknown)} tidak dikenal pada rule '{name}'.",
            path=path,
            source=source,
        )

    severity = mapping.get("severity", default.severity)
    if not isinstance(severity, str) or severity not in _VALID_SEVERITIES:
        raise CopyConfigError(
            "Field 'severity' harus error, warning, atau off.",
            path=(*path, "severity"),
            source=source,
        )
    enabled = mapping.get("enabled", True)
    if not isinstance(enabled, bool):
        raise CopyConfigError(
            "Field 'enabled' harus boolean.",
            path=(*path, "enabled"),
            source=source,
        )

    max_words: int | None = None
    if name == "sentence_length":
        raw_max_words = mapping.get("max_words", DEFAULT_MAX_WORDS)
        if (
            isinstance(raw_max_words, bool)
            or not isinstance(raw_max_words, int)
            or raw_max_words <= 0
        ):
            raise CopyConfigError(
                "Field 'max_words' harus bilangan bulat positif.",
                path=(*path, "max_words"),
                source=source,
            )
        max_words = raw_max_words

    extra: Mapping[Language, tuple[str, ...]] = {}
    if name == "banned_phrases":
        extra = _parse_extra(mapping.get("extra"), source=source)

    return RuleConfig(
        name=name,
        severity=cast(SeveritySetting, severity),
        enabled=enabled,
        max_words=max_words,
        extra=extra,
    )


def _parse_extra(value: object, *, source: str) -> Mapping[Language, tuple[str, ...]]:
    if value is None:
        return {}
    mapping = _require_mapping(
        value, path=("rules", "banned_phrases", "extra"), context="extra", source=source
    )
    _check_fields(
        mapping,
        _EXTRA_FIELDS,
        path=("rules", "banned_phrases", "extra"),
        context="extra",
        source=source,
    )
    extra: dict[Language, tuple[str, ...]] = {}
    for language in _EXTRA_FIELDS:
        if language not in mapping:
            continue
        raw = mapping[language]
        if not isinstance(raw, list):
            raise CopyConfigError(
                f"Field 'extra.{language}' harus daftar frasa literal.",
                path=("rules", "banned_phrases", "extra", language),
                source=source,
            )
        seen: set[str] = set()
        phrases: list[str] = []
        for index, phrase in enumerate(raw):
            if not isinstance(phrase, str) or not phrase.strip():
                raise CopyConfigError(
                    f"Frasa pada 'extra.{language}[{index}]' harus string tidak kosong.",
                    path=("rules", "banned_phrases", "extra", language, index),
                    source=source,
                )
            normalized = phrase.strip()
            folded = normalized.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            phrases.append(normalized)
        extra[cast(Language, language)] = tuple(phrases)
    return extra


def _parse_allow(value: object, *, source: str) -> tuple[AllowEntry, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CopyConfigError(
            "Field 'allow' harus daftar entri.",
            path=("allow",),
            source=source,
        )
    entries: list[AllowEntry] = []
    for index, raw in enumerate(value):
        path = ("allow", index)
        mapping = _require_mapping(raw, path=path, context="allow", source=source)
        _check_fields(mapping, _ALLOW_FIELDS, path=path, context="allow", source=source)
        key = mapping.get("key")
        if not isinstance(key, str) or not key.strip():
            raise CopyConfigError(
                "Field 'allow.key' harus string tidak kosong.",
                path=(*path, "key"),
                source=source,
            )
        raw_rules = mapping.get("rules")
        if not isinstance(raw_rules, list):
            raise CopyConfigError(
                "Field 'allow.rules' harus daftar nama rule.",
                path=(*path, "rules"),
                source=source,
            )
        rules: list[str] = []
        for rule_index, rule in enumerate(raw_rules):
            if not isinstance(rule, str) or rule not in RULE_NAMES:
                raise CopyConfigError(
                    f"Rule allow '{rule}' tidak dikenal.",
                    path=(*path, "rules", rule_index),
                    source=source,
                )
            if rule in rules:
                raise CopyConfigError(
                    f"Rule allow '{rule}' duplikat.",
                    path=(*path, "rules", rule_index),
                    source=source,
                )
            rules.append(rule)
        if not rules:
            raise CopyConfigError(
                "Field 'allow.rules' wajib memuat minimal satu rule.",
                path=(*path, "rules"),
                source=source,
            )
        reason = mapping.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise CopyConfigError(
                "Field 'allow.reason' wajib diisi.",
                path=(*path, "reason"),
                source=source,
            )
        entries.append(AllowEntry(key=key.strip(), rules=tuple(rules), reason=reason.strip()))
    return tuple(entries)


def _require_mapping(
    value: object,
    *,
    path: tuple[str | int, ...],
    context: str,
    source: str,
) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise CopyConfigError(f"{context} harus mapping.", path=path, source=source)
    return value


def _check_fields(
    mapping: Mapping[object, object],
    allowed: Iterable[str],
    *,
    path: tuple[str | int, ...],
    context: str,
    source: str,
) -> None:
    allowed_set = set(allowed)
    unknown = sorted(str(key) for key in mapping if key not in allowed_set)
    if unknown:
        raise CopyConfigError(
            f"Key {_format_keys(unknown)} tidak dikenal pada {context}.",
            path=path,
            source=source,
        )


def _format_keys(keys: Iterable[str]) -> str:
    values = [f"'{key}'" for key in keys]
    return ", ".join(values)


def _format_path(path: tuple[str | int, ...]) -> str:
    if not path:
        return ""
    parts: list[str] = []
    for segment in path:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        elif parts:
            parts.append(f".{segment}")
        else:
            parts.append(segment)
    return "".join(parts)
