"""Validasi struktur YAML dan helper pemeriksaan umum.

Modul ini menolak alias, merge key, tag kustom, dan tipe YAML yang tidak
didukung, lalu menyediakan pemeriksaan bentuk mapping, daftar, kunci wajib,
serta kunci tak dikenal. Helper mengembalikan nilai yang sudah divalidasi, atau
``None`` untuk pemeriksaan murni, dan melempar ``ConfigError`` saat gagal;
tidak ada helper yang memutasi input.

Semua error memakai ``ConfigError`` dengan kode stabil agar pesan dan
klasifikasi tetap sama di seluruh loader config.
"""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from ..errors import ConfigError

_ALLOWED_YAML_TAGS = frozenset(
    {
        "tag:yaml.org,2002:map",
        "tag:yaml.org,2002:seq",
        "tag:yaml.org,2002:str",
        "tag:yaml.org,2002:int",
        "tag:yaml.org,2002:float",
        "tag:yaml.org,2002:bool",
        "tag:yaml.org,2002:null",
    }
)


def _walk_yaml_nodes(node: Node, *, source: Path | str, label: str) -> None:
    tag = getattr(node, "tag", None)
    if getattr(node, "anchor", None) is not None:
        raise ConfigError(
            f"{label} memakai anchor/alias YAML; alias tidak didukung",
            code="CFG-YAML-ALIAS",
            path=str(source),
            key=label,
        )
    if tag not in _ALLOWED_YAML_TAGS:
        raise ConfigError(
            f"{label} memakai tag YAML yang tidak didukung: {tag}",
            code="CFG-YAML-TYPE",
            path=str(source),
            key=label,
        )
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode) and key_node.value == "<<":
                raise ConfigError(
                    f"{label} memakai merge key '<<'; alias tidak didukung",
                    code="CFG-YAML-ALIAS",
                    path=str(source),
                    key=label,
                )
            _walk_yaml_nodes(key_node, source=source, label=label)
            _walk_yaml_nodes(value_node, source=source, label=label)
    elif isinstance(node, SequenceNode):
        for child in node.value:
            _walk_yaml_nodes(child, source=source, label=label)


def _assert_safe_value(value: Any, *, source: Path | str, label: str, key: str = "") -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_safe_value(
                item,
                source=source,
                label=label,
                key=f"{key}[{index}]" if key else str(index),
            )
        return
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise ConfigError(
                    f"{label} memuat kunci non-teks: {child_key!r}",
                    code="CFG-YAML-TYPE",
                    path=str(source),
                    key=key or label,
                )
            _assert_safe_value(
                child,
                source=source,
                label=label,
                key=f"{key}.{child_key}" if key else child_key,
            )
        return
    raise ConfigError(
        f"{label} memuat tipe YAML yang tidak didukung: {type(value).__name__}",
        code="CFG-YAML-TYPE",
        path=str(source),
        key=key or label,
    )


def _err(message: str, *, code: str, path: Path, key: str) -> ConfigError:
    return ConfigError(message, code=code, path=path, key=key)


def _expect_mapping(value: Any, *, path: Path, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _err(
            f"'{key}' harus berupa pemetaan",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return value


def _expect_list(value: Any, *, path: Path, key: str) -> list[Any]:
    if not isinstance(value, list):
        raise _err(
            f"'{key}' harus berupa daftar",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    return value


def _check_unknown(
    mapping: Mapping[str, Any],
    allowed: Iterable[str],
    *,
    path: Path,
    key: str,
) -> None:
    allowed_set = set(allowed)
    for raw_key in mapping:
        child = str(raw_key)
        if child in allowed_set:
            continue
        raise _err(
            f"kunci '{child}' tidak dikenal",
            code="CFG-UNKNOWN-KEY",
            path=path,
            key=f"{key}.{child}" if key else child,
        )


def _required(mapping: Mapping[str, Any], child: str, *, path: Path, key: str) -> Any:
    if child not in mapping or mapping[child] is None:
        raise _err(
            f"kunci '{child}' wajib diisi",
            code="CFG-REQUIRED",
            path=path,
            key=f"{key}.{child}" if key else child,
        )
    return mapping[child]
