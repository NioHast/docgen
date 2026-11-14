#!/usr/bin/env python3
"""Pemeriksa gaya Python 3.15 untuk AutoOffice.

Checker statis ini menolak `from __future__ import annotations`, alias typing
warisan, dan API standard library yang sudah deprecated. Pemeriksaan memakai
AST dan tokenize, tidak menjalankan kode, tidak mengakses jaringan, dan tidak
menulis berkas.

Pemakaian:
    python tools/quality/check_python.py
    python tools/quality/check_python.py --list
    python tools/quality/check_python.py --format json src/autooffice tests

Kode keluar 0 bila bersih, 1 bila ada temuan, dan 2 bila path tidak ditemukan.
"""

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATHS: tuple[str, ...] = ("src/autooffice", "tests")

LEGACY_TYPING: dict[str, str] = {
    "AnyStr": "type parameter dengan constraint PEP 695",
    "ByteString": "bytes | bytearray | memoryview atau collections.abc.Buffer",
    "Callable": "collections.abc.Callable",
    "Dict": "dict",
    "FrozenSet": "frozenset",
    "Hashable": "collections.abc.Hashable",
    "Iterable": "collections.abc.Iterable",
    "Iterator": "collections.abc.Iterator",
    "List": "list",
    "Mapping": "collections.abc.Mapping",
    "MutableMapping": "collections.abc.MutableMapping",
    "NoReturn": "typing.Never",
    "Optional": "X | None",
    "Sequence": "collections.abc.Sequence",
    "Set": "set",
    "Sized": "collections.abc.Sized",
    "Text": "str",
    "Tuple": "tuple",
    "Type": "type",
    "TypeAlias": "type statement PEP 695",
    "TypeGuard": "typing.TypeIs bila narrowing dua arah dibutuhkan",
    "Union": "X | Y",
}

DEPRECATED_CALLS: dict[str, tuple[str, str]] = {
    "datetime.datetime.utcnow": (
        "datetime-utcnow",
        "datetime.utcnow() deprecated; gunakan datetime.now(UTC)",
    ),
    "datetime.utcnow": (
        "datetime-utcnow",
        "datetime.utcnow() deprecated; gunakan datetime.now(UTC)",
    ),
    "datetime.datetime.utcfromtimestamp": (
        "datetime-utcnow",
        "datetime.utcfromtimestamp() deprecated; gunakan datetime.fromtimestamp(ts, UTC)",
    ),
    "datetime.utcfromtimestamp": (
        "datetime-utcnow",
        "datetime.utcfromtimestamp() deprecated; gunakan datetime.fromtimestamp(ts, UTC)",
    ),
    "asyncio.get_event_loop": (
        "asyncio-loop",
        "asyncio.get_event_loop() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "asyncio.events.get_event_loop": (
        "asyncio-loop",
        "asyncio.get_event_loop() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "asyncio.get_event_loop_policy": (
        "asyncio-loop",
        "asyncio.get_event_loop_policy() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "asyncio.events.get_event_loop_policy": (
        "asyncio-loop",
        "asyncio.get_event_loop_policy() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "codecs.open": (
        "codecs-open",
        "codecs.open() deprecated; gunakan open() bawaan",
    ),
}


@dataclass(frozen=True)
class Rule:
    """Satu aturan checker dengan nama stabil untuk komentar allow."""

    name: str
    description: str


RULES: tuple[Rule, ...] = (
    Rule(
        "future-annotations",
        "Tolak from __future__ import annotations; anotasi lazy PEP 649/749 sudah default.",
    ),
    Rule(
        "legacy-typing",
        "Tolak alias typing warisan; gunakan builtin generik dan X | None.",
    ),
    Rule(
        "datetime-utcnow",
        "Tolak datetime.utcnow/utcfromtimestamp; gunakan datetime.now(UTC).",
    ),
    Rule(
        "asyncio-loop",
        "Tolak get_event_loop/get_event_loop_policy; gunakan asyncio.run atau Runner.",
    ),
    Rule(
        "pkg-resources",
        "Tolak pkg_resources; gunakan importlib.resources.",
    ),
    Rule(
        "codecs-open",
        "Tolak codecs.open; gunakan open() bawaan.",
    ),
    Rule(
        "unreadable",
        "Berkas tidak dapat diparse; perbaiki sintaks atau encoding.",
    ),
)

ALLOW_PATTERN = re.compile(
    r"#\s*python-style:\s*allow\s+"
    r"(?P<aturan>[A-Za-z0-9_-]+(?:\s*,\s*[A-Za-z0-9_-]+)*)"
)


@dataclass(frozen=True)
class Finding:
    """Satu temuan checker dengan lokasi dan nama aturan."""

    rule: str
    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.rule}] {self.message}"


@dataclass(frozen=True)
class Result:
    """Ringkasan hasil pemeriksaan."""

    file_count: int = 0
    findings: tuple[Finding, ...] = ()


def _display_name(path: Path, cwd: Path) -> str:
    """Path relatif terhadap cwd bila memungkinkan, selain itu path absolut."""
    try:
        return path.resolve().relative_to(cwd.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _iter_files(paths: list[str], cwd: Path) -> list[Path]:
    """Kumpulkan berkas Python secara deterministik tanpa duplikasi."""
    selected: dict[Path, None] = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(raw)
        candidates = [path] if path.is_file() else sorted(path.rglob("*.py"))
        for item in candidates:
            if item.suffix == ".py" and item.is_file():
                selected[item] = None
    return sorted(selected, key=lambda item: _display_name(item, cwd))


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Petakan nama lokal import ke nama lengkapnya."""
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    result[alias.asname] = alias.name
                else:
                    root = alias.name.split(".", 1)[0]
                    result[root] = root
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            if node.level:
                prefix = "." * node.level + prefix
            for alias in node.names:
                if alias.name == "*":
                    continue
                full_name = f"{prefix}.{alias.name}" if prefix else alias.name
                result[alias.asname or alias.name] = full_name
    return result


def _full_name(node: ast.AST, aliases: dict[str, str]) -> str:
    """Nama lengkap ekspresi Name/Attribute dengan alias import diterapkan."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _full_name(node.value, aliases)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _allow_map(text: str) -> dict[int, set[str]]:
    """Baca komentar `# python-style: allow <rule>` per baris."""
    result: dict[int, set[str]] = {}
    try:
        token_stream = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in token_stream:
            if token.type != tokenize.COMMENT:
                continue
            match = ALLOW_PATTERN.search(token.string)
            if match is None:
                continue
            rule = {parts.strip() for parts in match.group("aturan").split(",")}
            result.setdefault(token.start[0], set()).update(rule)
    except IndentationError:
        return result
    except tokenize.TokenError:
        return result
    return result


def _add(
    result: list[Finding],
    allow: dict[int, set[str]],
    rule: str,
    display: str,
    line: int,
    message: str,
) -> None:
    """Tambahkan temuan kecuali baris yang sama mengizinkannya atau duplikat."""
    if rule in allow.get(line, set()):
        return
    if any(item.rule == rule and item.line == line and item.message == message for item in result):
        return
    result.append(Finding(rule, display, line, message))


def _is_pkg_resources_module(name: str) -> bool:
    """True bila nama modul adalah pkg_resources atau submodulnya."""
    return name == "pkg_resources" or name.startswith("pkg_resources.")


def _check_tree(tree: ast.Module, text: str, display: str) -> list[Finding]:
    """Periksa satu AST dan kembalikan temuan mentah."""
    aliases = _aliases(tree)
    allow = _allow_map(text)
    result: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            _check_import_from(node, allow, display, result)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_pkg_resources_module(alias.name):
                    _add(
                        result,
                        allow,
                        "pkg-resources",
                        display,
                        node.lineno,
                        "pkg_resources deprecated; gunakan importlib.resources",
                    )
        elif isinstance(node, ast.Call):
            name = _full_name(node.func, aliases)
            if name in DEPRECATED_CALLS:
                rule, message = DEPRECATED_CALLS[name]
                _add(result, allow, rule, display, node.lineno, message)
        elif isinstance(node, (ast.Attribute, ast.Name)):
            name = _full_name(node, aliases)
            if name in DEPRECATED_CALLS:
                rule, message = DEPRECATED_CALLS[name]
                _add(result, allow, rule, display, node.lineno, message)
            elif isinstance(node, ast.Attribute) and name.startswith("typing."):
                attribute = name.rsplit(".", 1)[-1]
                replacement = LEGACY_TYPING.get(attribute)
                if replacement is not None:
                    _add(
                        result,
                        allow,
                        "legacy-typing",
                        display,
                        node.lineno,
                        f"typing.{attribute} warisan; gunakan {replacement}",
                    )
    return result


def _check_import_from(
    node: ast.ImportFrom,
    allow: dict[int, set[str]],
    display: str,
    result: list[Finding],
) -> None:
    """Periksa import from untuk future annotations, typing, dan pkg_resources."""
    if node.level == 0 and node.module == "__future__":
        for alias in node.names:
            if alias.name == "annotations":
                _add(
                    result,
                    allow,
                    "future-annotations",
                    display,
                    node.lineno,
                    "hapus from __future__ import annotations; target Python 3.15 lazy",
                )
    if node.level == 0 and node.module == "typing":
        for alias in node.names:
            replacement = LEGACY_TYPING.get(alias.name)
            if replacement is None:
                continue
            _add(
                result,
                allow,
                "legacy-typing",
                display,
                getattr(alias, "lineno", node.lineno),
                f"typing.{alias.name} warisan; gunakan {replacement}",
            )
    if node.level == 0 and _is_pkg_resources_module(node.module or ""):
        _add(
            result,
            allow,
            "pkg-resources",
            display,
            node.lineno,
            "pkg_resources deprecated; gunakan importlib.resources",
        )


def _check_file(path: Path, display: str) -> list[Finding]:
    """Baca dan periksa satu berkas Python."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=display)
    return _check_tree(tree, text, display)


def check(paths: list[str] | None = None, cwd: Path | None = None) -> Result:
    """Pindai path dan kembalikan temuan secara deterministik."""
    root = (cwd or Path.cwd()).resolve()
    requested = list(paths) if paths else list(DEFAULT_PATHS)
    files = _iter_files(requested, root)
    findings: list[Finding] = []
    for path in files:
        display = _display_name(path, root)
        try:
            findings.extend(_check_file(path, display))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    "unreadable",
                    display,
                    0,
                    f"tidak dapat diperiksa: {exc.__class__.__name__}",
                )
            )
    findings.sort(key=lambda item: (item.file, item.line, item.rule, item.message))
    return Result(file_count=len(files), findings=tuple(findings))


def _print_text(result: Result) -> None:
    """Cetak ringkasan dan temuan dalam format teks."""
    print(f"Berkas diperiksa: {result.file_count}")
    print(f"Temuan: {len(result.findings)}")
    for item in result.findings:
        print(f"- {item}")


def _print_json(result: Result) -> None:
    """Cetak hasil dalam JSON yang stabil dan mudah dibaca mesin."""
    by_rule: dict[str, int] = {}
    for item in result.findings:
        by_rule[item.rule] = by_rule.get(item.rule, 0) + 1
    data = {
        "files": result.file_count,
        "findings": len(result.findings),
        "by_rule": by_rule,
        "violations": [
            {
                "rule": item.rule,
                "file": item.file,
                "line": item.line,
                "message": item.message,
            }
            for item in result.findings
        ],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _print_rule_list() -> None:
    """Cetak nama dan deskripsi aturan untuk dokumentasi dan allow comment."""
    for rule in RULES:
        print(f"{rule.name:22} {rule.description}")


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI tanpa menjalankan pemeriksaan."""
    parser = argparse.ArgumentParser(
        prog="check_python.py",
        description="Periksa gaya Python 3.15 tanpa menjalankan kode.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="berkas atau direktori Python; default src/autooffice dan tests",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_rules",
        help="cetak nama dan deskripsi aturan",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="format keluaran; default text",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar 0, 1, atau 2."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_rules:
        _print_rule_list()
        return 0
    try:
        result = check(args.paths or None)
    except FileNotFoundError as exc:
        print(f"path tidak ditemukan: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        _print_json(result)
    else:
        _print_text(result)
    return 1 if result.findings else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
