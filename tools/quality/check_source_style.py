#!/usr/bin/env python3
"""Pemeriksa gaya komentar dan docstring Python AutoOffice.

Checker ini hanya membaca komentar lewat ``tokenize`` dan docstring lewat AST.
Literal string biasa, teks CLI, nama test, nama fixture, dan prosa fixture tidak
diperiksa. Temuan dibatasi pada bahasa perencanaan atau riwayat yang tidak boleh
muncul di komentar dan docstring: tag fase, istilah pembagian kerja, kata
riwayat, penanda pekerjaan tertunda, label tahap bernomor, dan istilah siklus
kerja.

Prosa Indonesia yang sah, misalnya "rencana layout", tidak ditandai karena
label tahap hanya dicocokkan bila diikuti nomor. Kata "iterasi" sebagai kata
kerja loop atau penelusuran juga tidak ditandai; hanya label iterasi bernomor
atau berdiri sendiri yang dianggap bahasa rencana. Baris yang memuat komentar
``# style-ok`` dikecualikan dari pemeriksaan.

Pemakaian:
    python tools/quality/check_source_style.py
    python tools/quality/check_source_style.py --list
    python tools/quality/check_source_style.py --format json src/autooffice tests

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

DEFAULT_PATHS: tuple[str, ...] = ("src/autooffice", "tests", "tools/quality")

STYLE_ALLOW_PATTERN = re.compile(r"#\s*style-ok\b")

DOCSTRING_PARENTS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

# Berkas yang memakai kata kunci riwayat sebagai nama domain alat, bukan sebagai
# catatan riwayat. Allowance dibatasi ke path relatif persis berikut.
LEGACY_DOMAIN_FILES: frozenset[str] = frozenset(
    {
        "tools/quality/check_no_legacy.py",
        "tests/tools/test_no_legacy.py",
    }
)

ALLOWANCES: tuple[str, ...] = (
    "legacy: hanya tools/quality/check_no_legacy.py dan tests/tools/test_no_legacy.py; "
    "kata itu adalah domain alat pemeriksa path/package.",
    "iterasi: hanya label bernomor, berkolon, atau berdiri sendiri; "
    "kata kerja loop/list dan prosa berakhir titik diabaikan.",
    "F0-F3: hanya komentar dan docstring; string, nama test, dan nama fixture diabaikan.",
)


@dataclass(frozen=True)
class Rule:
    """Satu pola bahasa rencana atau riwayat dengan nama stabil."""

    name: str
    description: str
    pattern: re.Pattern[str] | None = None
    exempt_files: frozenset[str] = frozenset()


RULES: tuple[Rule, ...] = (
    Rule(
        "phase-tag",
        "Tolak tag fase F0 sampai F3 di komentar atau docstring.",
        re.compile(r"(?<![A-Za-z0-9_])F[0-3](?![A-Za-z0-9_])"),
    ),
    Rule(
        "lane",
        "Tolak istilah lane atau lanes di komentar atau docstring.",
        re.compile(r"(?i)\blanes?\b"),
    ),
    Rule(
        "legacy",
        "Tolak kata legacy di komentar atau docstring, kecuali berkas domain alat.",
        re.compile(r"(?i)\blegacy\b"),
        exempt_files=LEGACY_DOMAIN_FILES,
    ),
    Rule(
        "todo",
        "Tolak penanda TODO di komentar atau docstring.",
        re.compile(r"\bTODO\b"),
    ),
    Rule(
        "fixme",
        "Tolak penanda FIXME di komentar atau docstring.",
        re.compile(r"\bFIXME\b"),
    ),
    Rule(
        "tahap",
        "Tolak label Tahap yang diikuti nomor.",
        re.compile(r"(?i)\bTahap\s+\d+\b"),
    ),
    Rule(
        "fase",
        "Tolak label Fase yang diikuti nomor.",
        re.compile(r"(?i)\bFase\s+\d+\b"),
    ),
    Rule(
        "rencana",
        "Tolak label Rencana yang diikuti nomor.",
        re.compile(r"(?i)\bRencana\s+\d+\b"),
    ),
    Rule(
        "phase",
        "Tolak label Phase yang diikuti nomor.",
        re.compile(r"(?i)\bPhase\s+\d+\b"),
    ),
    Rule(
        "milestone",
        "Tolak istilah Milestone di komentar atau docstring.",
        re.compile(r"(?i)\bmilestones?\b"),
    ),
    Rule(
        "sprint",
        "Tolak istilah Sprint di komentar atau docstring.",
        re.compile(r"(?i)\bsprints?\b"),
    ),
    Rule(
        "iterasi",
        "Tolak label Iterasi bernomor, berkolon, atau berdiri sendiri; kata kerja loop diabaikan.",
        re.compile(r"(?i)\biterasi\b(?=\s*(?:\d|[:;)]|$))"),
    ),
    Rule(
        "unreadable",
        "Berkas tidak dapat diparse; perbaiki sintaks atau encoding.",
    ),
)


@dataclass(frozen=True)
class Finding:
    """Satu temuan checker dengan lokasi dan teks yang cocok."""

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


def _allow_lines(text: str) -> set[int]:
    """Kumpulkan baris yang memuat komentar ``# style-ok``."""
    result: set[int] = set()
    try:
        token_stream = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in token_stream:
            if token.type == tokenize.COMMENT and STYLE_ALLOW_PATTERN.search(token.string):
                result.add(token.start[0])
    except IndentationError, tokenize.TokenError:
        return result
    return result


def _docstrings(tree: ast.Module) -> list[tuple[str, int, int]]:
    """Kembalikan isi, baris awal, dan baris akhir setiap docstring."""
    result: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, DOCSTRING_PARENTS):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        value = first.value.value
        if not isinstance(value, str):
            continue
        result.append((value, first.value.lineno, first.value.end_lineno or first.value.lineno))
    return result


def _scan_line(line: str, rule: Rule) -> str | None:
    """Kembalikan teks yang cocok bila satu baris melanggar aturan."""
    if rule.pattern is None:
        return None
    match = rule.pattern.search(line)
    return match.group(0) if match is not None else None


def _rule_applies(rule: Rule, display: str) -> bool:
    """True bila aturan tidak dikecualikan untuk berkas ini."""
    return display not in rule.exempt_files


def _add(
    findings: list[Finding],
    seen: set[tuple[str, int, str]],
    display: str,
    line: int,
    rule: Rule,
    matched: str,
) -> None:
    """Tambahkan temuan tanpa duplikat aturan pada baris yang sama."""
    key = (display, line, rule.name)
    if key in seen:
        return
    seen.add(key)
    findings.append(Finding(rule.name, display, line, matched))


def _check_comments(
    text: str,
    display: str,
    findings: list[Finding],
    seen: set[tuple[str, int, str]],
) -> None:
    """Periksa komentar dari tokenize; string tidak pernah masuk ke sini."""
    try:
        token_stream = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in token_stream:
            if token.type != tokenize.COMMENT:
                continue
            if STYLE_ALLOW_PATTERN.search(token.string):
                continue
            for rule in RULES:
                if not _rule_applies(rule, display):
                    continue
                matched = _scan_line(token.string, rule)
                if matched is not None:
                    _add(findings, seen, display, token.start[0], rule, matched)
    except IndentationError, tokenize.TokenError:
        return


def _check_docstrings(
    tree: ast.Module,
    text: str,
    display: str,
    findings: list[Finding],
    seen: set[tuple[str, int, str]],
) -> None:
    """Periksa docstring per baris; docstring dengan style-ok dilewati."""
    escaped = _allow_lines(text)
    for content, start, end in _docstrings(tree):
        if escaped.intersection(range(start, end + 1)):
            continue
        for offset, line in enumerate(content.splitlines() or [""]):
            line_number = start + offset
            for rule in RULES:
                if not _rule_applies(rule, display):
                    continue
                matched = _scan_line(line, rule)
                if matched is not None:
                    _add(findings, seen, display, line_number, rule, matched)


def _check_tree(tree: ast.Module, text: str, display: str) -> list[Finding]:
    """Periksa komentar dan docstring satu AST."""
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()
    _check_comments(text, display, findings, seen)
    _check_docstrings(tree, text, display, findings, seen)
    return findings


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
    """Cetak satu diagnostik per baris tanpa ringkasan tambahan."""
    for item in result.findings:
        print(item)


def _print_json(result: Result) -> None:
    """Cetak hasil dalam JSON yang stabil dan mudah dibaca mesin."""
    data = {
        "files": result.file_count,
        "findings": len(result.findings),
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
    """Cetak nama, deskripsi aturan, dan allowance yang disengaja."""
    for rule in RULES:
        print(f"{rule.name:12} {rule.description}")
    print()
    for allowance in ALLOWANCES:
        print(f"allowance: {allowance}")


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI tanpa menjalankan pemeriksaan."""
    parser = argparse.ArgumentParser(
        prog="check_source_style.py",
        description="Periksa komentar dan docstring tanpa menjalankan kode.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="berkas atau direktori Python; default src/autooffice, tests, dan tools/quality",
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
