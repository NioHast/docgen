#!/usr/bin/env python3
"""Pemeriksa path, package, dan teknologi legacy yang dilarang AutoOffice.

Checker memindai pohon kerja secara read-only dan deterministik. Pelanggaran
aktif adalah keberadaan path terlarang, import atau entry point package lama,
dan rujukan teknologi renderer yang sudah dihapus. Riwayat migrasi pada plan,
execution log, arsip, ADR, kontrak, fixture golden, dan guard negatif
diizinkan secara eksplisit lewat allowlist.

Pemakaian:
    python tools/quality/check_no_legacy.py [akar-repo]
    python tools/quality/check_no_legacy.py --list

Kode keluar 0 bila bersih, 1 bila ada pelanggaran aktif, dan 2 bila akar repo
tidak ditemukan. Skrip tidak mengakses jaringan dan tidak menulis berkas.
"""

import argparse
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Rule:
    """Satu pola legacy yang dicari pada berkas teks."""

    name: str
    target: str
    description: str
    pattern: re.Pattern[str]


RULES: tuple[Rule, ...] = (
    Rule(
        "src-docgen",
        "src/docgen",
        "path package legacy",
        re.compile(r"src[\\/]docgen(?![A-Za-z0-9_])", re.IGNORECASE),
    ),
    Rule(
        "src-autooffice-legacy",
        "src/autooffice/legacy",
        "path shim legacy",
        re.compile(r"src[\\/]autooffice[\\/]legacy(?![A-Za-z0-9_])", re.IGNORECASE),
    ),
    Rule(
        "docgen-import",
        "from docgen / import docgen",
        "import package legacy",
        re.compile(
            r"(?m)^[ \t]*(?:from[ \t]+docgen(?:\.[A-Za-z_]\w*)*[ \t]+import"
            r"|import[ \t]+docgen(?:\.[A-Za-z_]\w*)*)\b"
        ),
    ),
    Rule(
        "docgen-module",
        "docgen.<module>",
        "rujukan modul package legacy",
        re.compile(r"(?<![\w-])docgen(?:\.[A-Za-z_]\w*)+"),
    ),
    Rule(
        "docgen-name",
        "docgen",
        "nama package, entry point, atau perintah legacy",
        re.compile(r"(?<![\w-])docgen(?!\w)"),
    ),
    Rule(
        "word-ps1",
        "scripts/word.ps1",
        "adapter PowerShell legacy",
        re.compile(r"(?i)\bword\.ps1\b"),
    ),
    Rule(
        "package-json",
        "package.json",
        "manifest Node legacy",
        re.compile(r"(?i)\bpackage\.json\b"),
    ),
    Rule(
        "node-modules",
        "node_modules",
        "dependency Node legacy",
        re.compile(r"(?i)\bnode_modules\b"),
    ),
    Rule(
        "pptxgenjs",
        "PptxGenJS",
        "renderer PPTX JavaScript legacy",
        re.compile(r"(?i)\bpptxgenjs\b"),
    ),
    Rule(
        "reveal",
        "Reveal / Reveal.js",
        "renderer HTML legacy",
        re.compile(r"\bReveal(?:\.js)?\b|\breveal\.js\b"),
    ),
)

ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "AUTO_OFFICE_PLAN.md",
        "AUTO_OFFICE_EXECUTION_LOG.md",
        "docs/dev/f3-cleanup.md",
        "tests/cli/test_cli.py",
        "tests/docx/test_office.py",
        "tests/packaging/test_autooffice_package.py",
        "tests/packaging/test_wheel_contents.py",
        "tests/tools/test_no_legacy.py",
        "tests/tools/test_quality_tools.py",
        "tools/quality/check_no_legacy.py",
    }
)

ALLOWED_DIRECTORIES: tuple[str, ...] = (
    "docs/contracts/",
    "docs/decisions/",
    "docs/dev/archive/",
    "docs/dev/decisions/",
    "tests/fixtures/golden/",
)

# Literal historis yang hanya boleh muncul di berkas tertentu. Masking ini
# mempertahankan panjang baris sehingga nomor baris temuan lain tidak bergeser.
ALLOWED_LITERALS: dict[str, tuple[str, ...]] = {
    "docs/dev/testing.md": ("docgen-golden",),
}

SKIPPED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".autooffice",
        ".autooffice-build",
        ".cache",
        ".eggs",
        ".git",
        ".hypothesis",
        ".idea",
        ".import_linter_cache",
        ".laporan",
        ".laporan-build",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".venv315",
        ".vscode",
        "__pycache__",
        "acuan",
        "build",
        "dist",
        "htmlcov",
        "out",
        "review",
    }
)


@dataclass(frozen=True)
class Violation:
    """Satu temuan checker dengan lokasi berkas dan baris."""

    file: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.rule}: {self.message}"


@dataclass(frozen=True)
class Result:
    """Ringkasan hasil pemindaian."""

    file_count: int = 0
    violations: tuple[Violation, ...] = ()


def _is_allowed(relative: str) -> bool:
    """True bila berkas termasuk riwayat migrasi atau guard negatif."""
    if relative in ALLOWED_FILES:
        return True
    return any(relative.startswith(prefix) for prefix in ALLOWED_DIRECTORIES)


def _is_skipped_directory(name: str) -> bool:
    """True untuk cache, artefak build, dan metadata package yang diabaikan."""
    folded = name.casefold()
    return folded in SKIPPED_DIRECTORIES or folded.endswith(".egg-info")


def _mask_literals(line: str, literals: tuple[str, ...]) -> str:
    """Ganti literal historis dengan spasi agar tidak memicu aturan."""
    for item in literals:
        line = line.replace(item, " " * len(item))
    return line


def _read_text(path: Path) -> str | None:
    """Baca berkas UTF-8; kembalikan None untuk biner atau tak terbaca."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _scan_tree(root: Path) -> tuple[list[Path], list[Violation]]:
    """Kumpulkan berkas teks dan pelanggaran berbasis keberadaan path."""
    files: list[Path] = []
    violations: list[Violation] = []
    for directory, directory_names, file_names in os.walk(root):
        location = Path(directory)
        directory_names.sort()
        for name in list(directory_names):
            relative = (location / name).relative_to(root).as_posix()
            if name.casefold() == "node_modules":
                violations.append(
                    Violation(
                        relative,
                        0,
                        "node-modules",
                        "direktori dependency Node legacy tidak boleh ada",
                    )
                )
                directory_names.remove(name)
            elif relative in {"src/docgen", "src/autooffice/legacy"}:
                rule = "src-docgen" if relative == "src/docgen" else "src-autooffice-legacy"
                violations.append(
                    Violation(
                        relative,
                        0,
                        rule,
                        "path legacy tidak boleh ada",
                    )
                )
                directory_names.remove(name)
            elif _is_skipped_directory(name):
                directory_names.remove(name)
        for name in sorted(file_names):
            path = location / name
            relative = path.relative_to(root).as_posix()
            if name.casefold() == "package.json":
                violations.append(
                    Violation(relative, 0, "package-json", "manifest Node legacy tidak boleh ada")
                )
            if relative == "scripts/word.ps1":
                violations.append(
                    Violation(relative, 0, "word-ps1", "adapter PowerShell legacy tidak boleh ada")
                )
            files.append(path)
    return files, violations


def _scan_text(path: Path, relative: str) -> list[Violation]:
    """Cari aturan legacy pada setiap baris satu berkas teks."""
    text = _read_text(path)
    if text is None:
        return []
    literals = ALLOWED_LITERALS.get(relative, ())
    result: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if literals:
            line = _mask_literals(line, literals)
        for rule in RULES:
            if rule.pattern.search(line):
                result.append(Violation(relative, line_number, rule.name, rule.description))
                break
    return result


def check(root: Path = REPO_ROOT) -> Result:
    """Pindai seluruh pohon kerja dan kembalikan temuan deterministik."""
    root = root.resolve()
    files, violations = _scan_tree(root)
    file_count = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        if _is_allowed(relative):
            continue
        file_count += 1
        violations.extend(_scan_text(path, relative))
    unique: dict[tuple[str, int], Violation] = {}
    for item in violations:
        unique.setdefault((item.file, item.line), item)
    ordered = sorted(unique.values(), key=lambda item: (item.file, item.line, item.rule))
    return Result(file_count=file_count, violations=tuple(ordered))


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser pemeriksa no-legacy."""
    parser = argparse.ArgumentParser(
        prog="check_no_legacy.py",
        description="Periksa path, package, dan teknologi legacy yang dilarang AutoOffice.",
    )
    parser.add_argument("root", nargs="?", type=Path, default=REPO_ROOT, help="akar repo")
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_targets",
        help="Cetak seluruh target legacy dan keluar tanpa memindai.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar 0, 1, atau 2."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_targets:
        for rule in RULES:
            print(f"{rule.name:22} {rule.target:30} {rule.description}")
        return 0
    root = args.root.resolve()
    if not root.is_dir():
        print(f"akar repo tidak ditemukan: {root}", file=sys.stderr)
        return 2
    result = check(root)
    print(f"Berkas diperiksa: {result.file_count}")
    print(f"Pelanggaran aktif: {len(result.violations)}")
    for item in result.violations:
        print(f"- {item}")
    return 0 if not result.violations else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
