#!/usr/bin/env python3
"""Pemeriksa kebijakan coverage berbasis risiko AutoOffice.

Kebijakan membedakan tiga tingkat risiko:

- global line+branch minimal 90.0%;
- modul kritis minimal 100.0%;
- modul adapter minimal 85.0%.

Data dibaca dari berkas ``.coverage`` lewat API ``coverage`` tanpa subprocess.
Skrip tidak mengakses jaringan dan tidak menulis berkas. Kegagalan kebijakan
mencetak baris dan branch yang hilang, lalu keluar dengan kode 1. Kode 2
dipakai bila data coverage tidak ada atau tidak dapat dianalisis.

Pemakaian:
    python tools/quality/check_coverage.py
    python tools/quality/check_coverage.py --format json
    python tools/quality/check_coverage.py --list
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from coverage import Coverage
from coverage.exceptions import CoverageException
from coverage.report_core import get_analysis_to_report

AKAR = Path(__file__).resolve().parents[2]
GLOBAL_MINIMUM = 90.0
CRITICAL_MINIMUM = 100.0
ADAPTER_MINIMUM = 85.0
GLOBAL_SCOPE = "global"
CRITICAL_SCOPE = "critical"
ADAPTER_SCOPE = "adapter"

CRITICAL_MODULES: tuple[str, ...] = (
    "autooffice.deck.model.keys",
    "autooffice.deck.model.bindings",
    "autooffice.deck.layout.grid",
    "autooffice.deck.layout.spec",
    "autooffice.deck.copy.rules.title_case",
    "autooffice.deck.copy.rules.patterns",
    "autooffice.deck.charts.spec",
    "autooffice.deck.transcript.parser",
)

ADAPTER_PATTERNS: tuple[str, ...] = (
    "autooffice.google.*",
    "autooffice.pdf.*",
    "autooffice.cli.*",
    "autooffice.docx.*",
)


class CoveragePolicyError(Exception):
    """Data coverage tidak dapat dibaca atau tidak memenuhi prasyarat."""


@dataclass(frozen=True, slots=True)
class ModuleCoverage:
    """Statistik coverage satu modul impor."""

    module: str
    statements: int
    missing_lines: tuple[int, ...] = ()
    branches: int = 0
    missing_branches: tuple[tuple[int, int], ...] = ()
    measured: bool = True

    @property
    def covered_statements(self) -> int:
        """Jumlah statement yang dieksekusi."""
        if not self.measured:
            return 0
        return max(0, self.statements - len(self.missing_lines))

    @property
    def covered_branches(self) -> int:
        """Jumlah branch tujuan yang dieksekusi."""
        if not self.measured:
            return 0
        return max(0, self.branches - len(self.missing_branches))

    @property
    def line_percent(self) -> float:
        """Persentase line coverage."""
        if not self.measured:
            return 0.0
        if self.statements == 0:
            return 100.0
        return 100.0 * self.covered_statements / self.statements

    @property
    def branch_percent(self) -> float:
        """Persentase branch coverage; 100 bila modul tidak punya branch."""
        if not self.measured:
            return 0.0
        if self.branches == 0:
            return 100.0
        return 100.0 * self.covered_branches / self.branches

    @property
    def percent(self) -> float:
        """Persentase gabungan line dan branch."""
        if not self.measured:
            return 0.0
        total = self.statements + self.branches
        if total == 0:
            return 100.0
        covered = self.covered_statements + self.covered_branches
        return 100.0 * covered / total


@dataclass(frozen=True, slots=True)
class PolicyCheck:
    """Satu pemeriksaan kebijakan beserta modul yang diperiksa."""

    scope: str
    name: str
    minimum: float
    modules: tuple[ModuleCoverage, ...]
    missing_modules: tuple[str, ...] = ()
    matched: bool = True

    @property
    def statements(self) -> int:
        """Total statement pada cakupan pemeriksaan."""
        return sum(module.statements for module in self.modules)

    @property
    def branches(self) -> int:
        """Total branch pada cakupan pemeriksaan."""
        return sum(module.branches for module in self.modules)

    @property
    def covered(self) -> int:
        """Total statement dan branch yang dieksekusi."""
        return sum(module.covered_statements + module.covered_branches for module in self.modules)

    @property
    def percent(self) -> float:
        """Persentase gabungan line dan branch untuk cakupan ini."""
        if not self.modules:
            return 0.0
        total = self.statements + self.branches
        if total == 0:
            return 100.0 if all(module.measured for module in self.modules) else 0.0
        return 100.0 * self.covered / total

    @property
    def line_percent(self) -> float:
        """Persentase line coverage untuk cakupan ini."""
        statements = self.statements
        if statements == 0:
            return 100.0 if self.modules else 0.0
        return 100.0 * sum(module.covered_statements for module in self.modules) / statements

    @property
    def branch_percent(self) -> float:
        """Persentase branch coverage untuk cakupan ini."""
        branches = self.branches
        if branches == 0:
            return 100.0 if self.modules else 0.0
        return 100.0 * sum(module.covered_branches for module in self.modules) / branches

    @property
    def passed(self) -> bool:
        """True bila cakupan cocok, lengkap, dan memenuhi ambang."""
        return self.matched and not self.missing_modules and self.percent >= self.minimum


@dataclass(frozen=True, slots=True)
class PolicyReport:
    """Hasil lengkap kebijakan coverage."""

    checks: tuple[PolicyCheck, ...]

    @property
    def passed(self) -> bool:
        """True bila semua pemeriksaan lulus."""
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[PolicyCheck, ...]:
        """Pemeriksaan yang gagal."""
        return tuple(check for check in self.checks if not check.passed)


def _matches_adapter(module: str, pattern: str) -> bool:
    """Cocokkan modul adapter; pola ``paket.*`` juga mencakup paket itu sendiri."""
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return module == prefix or module.startswith(f"{prefix}.")
    return module == pattern


def evaluate_policy(
    stats: Mapping[str, ModuleCoverage],
    *,
    global_minimum: float = GLOBAL_MINIMUM,
    critical_modules: Sequence[str] = CRITICAL_MODULES,
    critical_minimum: float = CRITICAL_MINIMUM,
    adapter_patterns: Sequence[str] = ADAPTER_PATTERNS,
    adapter_minimum: float = ADAPTER_MINIMUM,
) -> PolicyReport:
    """Terapkan kebijakan coverage pada mapping nama modul ke statistiknya."""
    modules = tuple(stats[name] for name in sorted(stats))
    checks: list[PolicyCheck] = [
        PolicyCheck(
            scope=GLOBAL_SCOPE,
            name="line+branch",
            minimum=global_minimum,
            modules=modules,
            matched=bool(modules),
        )
    ]
    for module in critical_modules:
        coverage = stats.get(module)
        if coverage is None:
            checks.append(
                PolicyCheck(
                    scope=CRITICAL_SCOPE,
                    name=module,
                    minimum=critical_minimum,
                    modules=(),
                    missing_modules=(module,),
                )
            )
        else:
            checks.append(
                PolicyCheck(
                    scope=CRITICAL_SCOPE,
                    name=module,
                    minimum=critical_minimum,
                    modules=(coverage,),
                )
            )
    for pattern in adapter_patterns:
        selected = tuple(module for module in modules if _matches_adapter(module.module, pattern))
        checks.append(
            PolicyCheck(
                scope=ADAPTER_SCOPE,
                name=pattern,
                minimum=adapter_minimum,
                modules=selected,
                matched=bool(selected),
            )
        )
    return PolicyReport(tuple(checks))


def format_line_numbers(lines: Iterable[int]) -> str:
    """Format nomor baris menjadi rentang yang ringkas dan deterministik."""
    ordered = sorted(set(lines))
    if not ordered:
        return "-"
    parts: list[str] = []
    start = previous = ordered[0]
    for line in ordered[1:]:
        if line == previous + 1:
            previous = line
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = line
    parts.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(parts)


def format_branch_arcs(arcs: Iterable[tuple[int, int]]) -> str:
    """Format arc branch hilang sebagai ``sumber->tujuan``."""
    labels = [
        f"{source}->{'exit' if destination < 0 else destination}"
        for source, destination in sorted(set(arcs))
    ]
    return ", ".join(labels) if labels else "-"


def _check_label(check: PolicyCheck) -> str:
    """Label stabil untuk keluaran teks."""
    if check.scope == GLOBAL_SCOPE:
        return "global"
    return f"{check.scope} {check.name}"


def _failure_details(check: PolicyCheck) -> list[str]:
    """Baris detail untuk satu pemeriksaan yang gagal."""
    details: list[str] = []
    for module in check.modules:
        parts: list[str] = []
        if module.missing_lines:
            parts.append(f"missing lines {format_line_numbers(module.missing_lines)}")
        if module.missing_branches:
            parts.append(f"missing branches {format_branch_arcs(module.missing_branches)}")
        if parts:
            details.append(f"  {module.module}: {'; '.join(parts)}")
    for missing_module in check.missing_modules:
        details.append(f"  {missing_module}: modul tidak ditemukan di data coverage")
    if not check.modules and not check.missing_modules:
        details.append(f"  {check.name}: tidak ada modul yang cocok")
    return details


def render_text(report: PolicyReport) -> str:
    """Render laporan kebijakan sebagai teks yang dapat dibaca manusia."""
    lines = [f"coverage policy: {'PASS' if report.passed else 'FAIL'}"]
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(
            f"{status} {_check_label(check)}: {check.percent:.2f}% "
            f"(minimum {check.minimum:.2f}%; line {check.line_percent:.2f}%, "
            f"branch {check.branch_percent:.2f}%)"
        )
        if not check.passed:
            lines.extend(_failure_details(check))
    return "\n".join(lines)


def _module_payload(module: ModuleCoverage) -> dict[str, object]:
    """Representasi JSON satu modul."""
    return {
        "module": module.module,
        "statements": module.statements,
        "missing_lines": sorted(module.missing_lines),
        "branches": module.branches,
        "missing_branches": [
            [source, destination] for source, destination in sorted(module.missing_branches)
        ],
        "percent": round(module.percent, 2),
    }


def _check_payload(check: PolicyCheck) -> dict[str, object]:
    """Representasi JSON satu pemeriksaan."""
    return {
        "scope": check.scope,
        "name": check.name,
        "minimum": check.minimum,
        "percent": round(check.percent, 2),
        "line_percent": round(check.line_percent, 2),
        "branch_percent": round(check.branch_percent, 2),
        "passed": check.passed,
        "missing_modules": list(check.missing_modules),
        "modules": [_module_payload(module) for module in check.modules],
    }


def report_payload(report: PolicyReport) -> dict[str, object]:
    """Representasi JSON laporan kebijakan."""
    return {
        "passed": report.passed,
        "checks": [_check_payload(check) for check in report.checks],
    }


def render_json(report: PolicyReport) -> str:
    """Render laporan kebijakan sebagai JSON deterministik."""
    return json.dumps(report_payload(report), ensure_ascii=False, indent=2) + "\n"


def format_policy_list() -> str:
    """Cetak aturan kebijakan tanpa membaca data coverage."""
    lines = [f"global {GLOBAL_MINIMUM:.2f} line+branch"]
    lines.extend(f"critical {CRITICAL_MINIMUM:.2f} {module}" for module in CRITICAL_MODULES)
    lines.extend(f"adapter {ADAPTER_MINIMUM:.2f} {pattern}" for pattern in ADAPTER_PATTERNS)
    return "\n".join(lines)


def module_name(filename: str | Path, root: Path) -> str | None:
    """Ubah path sumber menjadi nama modul ``autooffice``; None bila di luar cakupan."""
    path = Path(filename)
    if not path.is_absolute():
        path = root / path
    try:
        relative = path.resolve().relative_to((root / "src").resolve())
    except ValueError:
        return None
    if relative.suffix != ".py":
        return None
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    if not parts or parts[0] != "autooffice":
        return None
    return ".".join(parts)


def read_coverage(
    coverage_file: str | Path = ".coverage",
    root: Path = AKAR,
) -> dict[str, ModuleCoverage]:
    """Baca ``.coverage`` lewat API coverage dan kembalikan statistik per modul."""
    path = Path(coverage_file)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise CoveragePolicyError(f"berkas coverage tidak ditemukan: {path}")
    coverage = Coverage(data_file=str(path), branch=True)
    try:
        coverage.load()
    except (CoverageException, OSError) as exc:
        raise CoveragePolicyError(f"gagal membaca {path}: {exc}") from exc
    if not coverage.get_data().has_arcs():
        raise CoveragePolicyError(
            "data coverage tidak memuat branch; jalankan pytest dengan --cov-branch"
        )
    stats: dict[str, ModuleCoverage] = {}
    try:
        for reporter, analysis in get_analysis_to_report(coverage, None):
            name = module_name(reporter.filename, root)
            if name is None:
                continue
            numbers = analysis.numbers
            missing_branches = tuple(
                sorted(
                    (line, destination)
                    for line, destinations in analysis.missing_branch_arcs().items()
                    for destination in destinations
                )
            )
            stats[name] = ModuleCoverage(
                module=name,
                statements=numbers.n_statements,
                missing_lines=tuple(sorted(analysis.missing)),
                branches=numbers.n_branches,
                missing_branches=missing_branches,
            )
    except CoverageException as exc:
        raise CoveragePolicyError(f"gagal menganalisis {path}: {exc}") from exc
    if not stats:
        raise CoveragePolicyError(f"tidak ada modul autooffice di {path}")
    return stats


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI tanpa membaca data coverage."""
    parser = argparse.ArgumentParser(
        prog="check_coverage",
        description="Periksa kebijakan coverage berbasis risiko AutoOffice.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="format keluaran; default text",
    )
    parser.add_argument(
        "--coverage-file",
        default=".coverage",
        metavar="PATH",
        help="berkas data coverage; default .coverage",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=AKAR,
        help="akar repo untuk memetakan path sumber",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_policy",
        help="cetak aturan kebijakan tanpa membaca coverage",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan pemeriksa dan kembalikan kode keluar tanpa sys.exit."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_policy:
        print(format_policy_list())
        return 0
    try:
        stats = read_coverage(args.coverage_file, args.root)
    except CoveragePolicyError as exc:
        print(f"check_coverage: {exc}", file=sys.stderr)
        return 2
    report = evaluate_policy(stats)
    output = render_json(report) if args.format == "json" else render_text(report)
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
