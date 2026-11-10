"""Helper nilai generik dan pembacaan YAML untuk konfigurasi dokumen.

Modul ini memuat loader YAML aman serta konversi nilai generik (teks, boolean,
angka, dimensi, ukuran font, warna, perataan, enum, dan daftar teks) yang
dipakai bersama oleh parser ``format.yml`` dan ``structure.yml``. Semua
kegagalan input dilempar sebagai ``ConfigError`` dengan kode stabil; tidak ada
helper yang memutasi input dan tidak ada fallback.

Kontrak data ada di ``docs/dev/formats.md``.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError
from ruamel.yaml.nodes import MappingNode

from ..errors import ConfigError
from .validation import _assert_safe_value, _err, _walk_yaml_nodes


def parse_yaml_mapping(
    text: str,
    *,
    source: Path | str,
    label: str = "YAML",
) -> dict[str, Any]:
    """Parse YAML menjadi mapping aman, menolak duplikat/alias/tag kustom."""

    if not text.strip():
        raise ConfigError(
            f"{label} kosong",
            code="CFG-REQUIRED",
            path=str(source),
            key=label,
        )
    try:
        composer = YAML(typ="safe", pure=True)
        root_node = composer.compose(text)
    except YAMLError as exc:
        raise ConfigError(
            f"{label} tidak valid: {exc}",
            code="CFG-YAML",
            path=str(source),
            key=label,
        ) from exc

    if root_node is None:
        raise ConfigError(
            f"{label} kosong",
            code="CFG-REQUIRED",
            path=str(source),
            key=label,
        )
    _walk_yaml_nodes(root_node, source=source, label=label)
    if not isinstance(root_node, MappingNode):
        raise ConfigError(
            f"{label} wajib berupa pemetaan YAML",
            code="CFG-YAML-TYPE",
            path=str(source),
            key=label,
        )

    try:
        loader = YAML(typ="safe", pure=True)
        loader.allow_duplicate_keys = False
        data = loader.load(text)
    except DuplicateKeyError as exc:
        raise ConfigError(
            f"{label} memuat kunci YAML duplikat: {exc}",
            code="CFG-YAML-DUPLICATE",
            path=str(source),
            key=label,
        ) from exc
    except YAMLError as exc:
        raise ConfigError(
            f"{label} tidak valid: {exc}",
            code="CFG-YAML",
            path=str(source),
            key=label,
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"{label} wajib berupa pemetaan YAML",
            code="CFG-YAML-TYPE",
            path=str(source),
            key=label,
        )
    _assert_safe_value(data, source=source, label=label)
    return {str(key): value for key, value in data.items()}


def load_yaml_mapping(path: Path, *, label: str = "YAML") -> dict[str, Any]:
    """Baca berkas UTF-8 (BOM diizinkan) dan parse sebagai mapping YAML aman."""

    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"berkas tidak ditemukan: {path}",
            code="CFG-ASSET-MISSING",
            path=path,
        ) from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(
            f"berkas harus UTF-8: {exc}",
            code="CFG-YAML",
            path=path,
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"berkas tidak dapat dibaca: {exc}",
            code="CFG-ASSET-MISSING",
            path=path,
        ) from exc
    return parse_yaml_mapping(text, source=path, label=label)


_DIMENSION_RE = re.compile(
    r"^(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?P<unit>cm|mm|in|pt|twip)$"
)
_COLOR_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_ALIGNMENTS = frozenset({"left", "right", "center", "justify", "both"})


def _text(
    value: Any,
    *,
    path: Path,
    key: str,
    default: str | None = None,
    allow_empty: bool = False,
) -> str:
    if value is None:
        if default is None:
            raise _err(
                f"'{key}' wajib diisi",
                code="CFG-REQUIRED",
                path=path,
                key=key,
            )
        text = default
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise _err(
            f"'{key}' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    if not text and not allow_empty:
        raise _err(
            f"'{key}' tidak boleh kosong",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    return text


def _boolean(value: Any, *, path: Path, key: str, default: bool | None = None) -> bool:
    if value is None:
        if default is None:
            raise _err(
                f"'{key}' wajib diisi",
                code="CFG-REQUIRED",
                path=path,
                key=key,
            )
        return default
    if not isinstance(value, bool):
        raise _err(
            f"'{key}' harus bernilai true/false",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return value


def _number(
    value: Any,
    *,
    path: Path,
    key: str,
    default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Validasi angka YAML dan terapkan batas; kembalikan ``float``.

    ``bool`` ditolak walau subclass ``int``. Nilai kosong memakai ``default``
    atau melempar ``ConfigError`` berkode ``CFG-REQUIRED``/``CFG-TYPE``.
    """

    if value is None:
        if default is None:
            raise _err(
                f"'{key}' wajib diisi",
                code="CFG-REQUIRED",
                path=path,
                key=key,
            )
        result = default
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _err(
            f"'{key}' harus berupa angka",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    else:
        result = float(value)
    if minimum is not None and result < minimum:
        raise _err(
            f"'{key}' harus >= {minimum}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    if maximum is not None and result > maximum:
        raise _err(
            f"'{key}' harus <= {maximum}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return result


def _dimension(
    value: Any,
    *,
    path: Path,
    key: str,
    default: str | None = None,
    minimum: int = 0,
    positive: bool = False,
) -> int:
    """Konversi dimensi teks (``cm``/``mm``/``in``/``pt``/``twip``) ke twip.

    ``default`` dipakai bila nilai kosong. Nilai non-positif atau di bawah
    ``minimum`` ditolak dengan ``ConfigError``.
    """

    raw = value if value is not None else default
    if raw is None:
        raise _err(
            f"'{key}' wajib diisi",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    if not isinstance(raw, str):
        raise _err(
            f"'{key}' harus berupa dimensi teks (mis. 4cm)",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    match = _DIMENSION_RE.fullmatch(raw.strip())
    if match is None:
        raise _err(
            f"'{key}' bukan dimensi yang valid: {raw!r}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    number = float(match.group("value"))
    unit = match.group("unit")
    factor = {"cm": 1440 / 2.54, "mm": 1440 / 25.4, "in": 1440, "pt": 20, "twip": 1}[unit]
    twips = round(number * factor)
    if positive and twips <= 0:
        raise _err(
            f"'{key}' harus > 0",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    if not positive and twips < minimum:
        raise _err(
            f"'{key}' harus >= {minimum} twip",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return twips


def _font_size(value: Any, *, path: Path, key: str, default: str | None = None) -> int:
    raw = value if value is not None else default
    if raw is None:
        raise _err(
            f"'{key}' wajib diisi",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    if not isinstance(raw, str):
        raise _err(
            f"'{key}' harus berupa ukuran font (mis. 12pt)",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    match = _DIMENSION_RE.fullmatch(raw.strip())
    if match is None or match.group("unit") != "pt":
        raise _err(
            f"'{key}' harus memakai satuan pt: {raw!r}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    points = float(match.group("value"))
    if points < 6 or points > 72:
        raise _err(
            f"'{key}' harus 6-72 pt",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return round(points * 2)


def _color(value: Any, *, path: Path, key: str, default: str = "000000") -> str:
    raw = value if value is not None else default
    if not isinstance(raw, str) or not _COLOR_RE.fullmatch(raw.strip()):
        raise _err(
            f"'{key}' harus berupa warna heksadesimal 6 digit",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return raw.strip().upper()


def _alignment(value: Any, *, path: Path, key: str, default: str = "justify") -> str:
    raw = value if value is not None else default
    if not isinstance(raw, str) or raw.strip().lower() not in _ALIGNMENTS:
        raise _err(
            f"'{key}' harus salah satu: {', '.join(sorted(_ALIGNMENTS))}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    text = raw.strip().lower()
    return "justify" if text == "both" else text


def _enum(
    value: Any,
    *,
    path: Path,
    key: str,
    choices: Iterable[str],
    default: str | None = None,
) -> str:
    raw = value if value is not None else default
    allowed = set(choices)
    if not isinstance(raw, str) or raw not in allowed:
        raise _err(
            f"'{key}' harus salah satu: {', '.join(sorted(allowed))}",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return raw


def _text_list(
    value: Any, *, path: Path, key: str, default: tuple[str, ...] = ()
) -> tuple[str, ...]:
    """Validasi daftar teks, trim, dan tolak duplikat casefold.

    Nilai kosong memakai ``default``. Pelanggaran melempar ``ConfigError``
    dengan kode ``CFG-TYPE``/``CFG-DUPLICATE``.
    """

    raw = value if value is not None else list(default)
    if not isinstance(raw, list):
        raise _err(
            f"'{key}' harus berupa daftar teks",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, str) or not item.strip():
            raise _err(
                f"item ke-{index} pada '{key}' harus berupa teks tidak kosong",
                code="CFG-TYPE",
                path=path,
                key=f"{key}[{index}]",
            )
        text = item.strip()
        folded = text.casefold()
        if folded in seen:
            raise _err(
                f"item '{text}' duplikat pada '{key}'",
                code="CFG-DUPLICATE",
                path=path,
                key=key,
            )
        seen.add(folded)
        result.append(text)
    if not result:
        raise _err(
            f"'{key}' minimal memuat satu item",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    return tuple(result)
