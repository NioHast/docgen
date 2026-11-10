#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 nothinx
"""Analisis coverage context untuk menemukan test yang tumpang tindih.

Skrip ini membaca data ``.coverage`` yang dihasilkan dengan
``--cov-context=test`` lewat API :class:`coverage.CoverageData`. Tidak ada
build Word/Pandoc dan tidak ada perubahan pada naskah. Temuan adalah sinyal
untuk ditinjau manusia, bukan keputusan otomatis untuk menghapus test.

Coverage adalah sinyal diagnostik, bukan vonis. ``no_unique_coverage`` lazim
pada suite yang test-nya saling tumpang tindih: beberapa test boleh menyentuh
baris yang sama dengan assertion dan tujuan yang berbeda. Karena itu temuan
tersebut berconfidence rendah (``KEEP-WEAK``) dan harus dibandingkan dengan isi
test, bukan dipakai sebagai alasan menghapus atau menggabungkan test.

Pemakaian:
    python tools/dev/check_coverage.py
    python tools/dev/check_coverage.py --format markdown --output coverage.md
    python tools/dev/check_coverage.py --fail-on high

Format keluaran default adalah JSON agar konsisten dengan
``tools/dev/check_tests.py``.

Kode keluar 0 secara default (peringatan saja), 1 bila temuan memenuhi
``--fail-on``, dan 2 bila berkas coverage tidak ditemukan atau argumen tidak
valid.
"""

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from coverage import CoverageData

SCHEMA_VERSION = 1
GENERATED_BY = "tools/dev/check_coverage.py"
DEFAULT_SOURCE = "src/docgen"
DEFAULT_MAX_COVERED_LINES = 1000
INTEGRATION_PREFIXES = ("tests/integration/", "tests/e2e/")
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

NO_UNIQUE_ACTION = (
    "Periksa overlap; test dengan banyak baris sama belum tentu duplikat. "
    "Bandingkan assertion dan tujuan test."
)
GOD_TEST_ACTION = "pecah per perilaku"
INTEGRATION_ONLY_ACTION = "tambah unit test atau pindahkan"
KEEP_ACTION = "pertahankan; coverage hanya sinyal, bukan target"


def parse_test_context(context: str) -> str | None:
    """Kembalikan id test untuk context ``|run``; fase lain diabaikan."""
    test_id, separator, phase = context.rpartition("|")
    if separator != "|" or phase != "run" or not test_id:
        return None
    return test_id.replace("\\", "/")


def _absolute_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (Path.cwd() / candidate).resolve()


def _source_root(source: str | Path) -> Path:
    return _absolute_path(source)


def _is_in_source(filename: str, source_root: Path) -> bool:
    try:
        _absolute_path(filename).relative_to(source_root)
    except ValueError:
        return False
    return True


def _display_path(filename: str, source: str | Path) -> str:
    candidate = _absolute_path(filename)
    cwd = Path.cwd().resolve()
    try:
        return candidate.relative_to(cwd).as_posix()
    except ValueError:
        pass
    try:
        relative = candidate.relative_to(_source_root(source)).as_posix()
    except ValueError:
        return candidate.as_posix()
    label = Path(source).as_posix().rstrip("/")
    if label in {"", "."}:
        return relative
    return f"{label}/{relative}"


def _is_integration_test(test_id: str) -> bool:
    return test_id.replace("\\", "/").startswith(INTEGRATION_PREFIXES)


def collect_coverage(
    data: CoverageData,
    source: str | Path = DEFAULT_SOURCE,
) -> dict[str, dict[int, tuple[str, ...]]]:
    """Ambil baris dan context dari ``CoverageData`` untuk file di ``source``."""
    root = _source_root(source)
    known_contexts = data.measured_contexts()
    collected: dict[str, dict[int, tuple[str, ...]]] = {}
    for filename in sorted(data.measured_files()):
        if not _is_in_source(filename, root):
            continue
        measured_lines = set(data.lines(filename) or ())
        contexts_by_line = data.contexts_by_lineno(filename)
        per_line: dict[int, tuple[str, ...]] = {}
        for line in sorted(measured_lines):
            contexts = tuple(
                sorted(
                    context
                    for context in contexts_by_line.get(line, ())
                    if context in known_contexts
                )
            )
            if contexts:
                per_line[line] = contexts
        if per_line:
            collected[filename] = per_line
    return collected


def read_coverage(
    coverage_file: str | Path,
    source: str | Path = DEFAULT_SOURCE,
) -> dict[str, dict[int, tuple[str, ...]]]:
    """Baca berkas coverage dan kembalikan context per baris di ``source``."""
    data = CoverageData(basename=str(coverage_file), read_only=True)
    data.read()
    return collect_coverage(data, source)


def _unique_lines(
    tests: Mapping[str, Mapping[str, set[int]]],
    line_tests: Mapping[str, Mapping[int, set[str]]],
) -> dict[str, int]:
    unique: dict[str, int] = defaultdict(int)
    for test_id, files in tests.items():
        for filename, lines in files.items():
            for line in lines:
                if line_tests[filename][line] == {test_id}:
                    unique[test_id] += 1
    return unique


def _signals(covered_lines: int, unique_lines: int, max_covered_lines: int) -> list[str]:
    signals: list[str] = []
    if unique_lines == 0:
        signals.append("no_unique_coverage")
    if covered_lines > max_covered_lines:
        signals.append("god_test")
    return signals


def _evidence(
    covered_lines: int,
    unique_lines: int,
    signals: Iterable[str],
    max_covered_lines: int,
) -> str:
    signal_set = set(signals)
    if "no_unique_coverage" in signal_set and "god_test" in signal_set:
        return (
            f"0 baris unik dari {covered_lines} baris yang dicakup; "
            f"{covered_lines} baris melebihi batas {max_covered_lines}"
        )
    if "no_unique_coverage" in signal_set:
        return (
            f"0 baris unik dari {covered_lines} baris yang dicakup; "
            "semua baris juga dicakup test lain"
        )
    if "god_test" in signal_set:
        return f"{covered_lines} baris dicakup, melebihi batas {max_covered_lines}"
    return f"{covered_lines} baris dicakup; {unique_lines} baris unik"


def _test_entry(
    test_id: str,
    covered_lines: int,
    unique_lines: int,
    max_covered_lines: int,
) -> dict[str, Any]:
    signals = _signals(covered_lines, unique_lines, max_covered_lines)
    if "god_test" in signals and "no_unique_coverage" in signals:
        verdict = "TRIM"
        confidence = "medium"
        action = f"{GOD_TEST_ACTION}; {NO_UNIQUE_ACTION}"
    elif "god_test" in signals:
        verdict = "TRIM"
        confidence = "medium"
        action = GOD_TEST_ACTION
    elif "no_unique_coverage" in signals:
        verdict = "KEEP-WEAK"
        confidence = "low"
        action = NO_UNIQUE_ACTION
    else:
        verdict = "KEEP"
        confidence = "high"
        action = KEEP_ACTION
    return {
        "id": test_id,
        "covered_lines": covered_lines,
        "unique_lines": unique_lines,
        "verdict": verdict,
        "confidence": confidence,
        "signals": signals,
        "evidence": _evidence(covered_lines, unique_lines, signals, max_covered_lines),
        "suggested_action": action,
    }


def analyze_contexts(
    line_contexts: Mapping[str, Mapping[int, Iterable[str]]],
    *,
    source: str | Path = DEFAULT_SOURCE,
    max_covered_lines: int = DEFAULT_MAX_COVERED_LINES,
) -> dict[str, Any]:
    """Analisis context per baris menjadi ringkasan test, file, dan sinyal."""
    root = _source_root(source)
    tests: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    line_tests: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for filename in sorted(line_contexts):
        if not _is_in_source(filename, root):
            continue
        display = _display_path(filename, source)
        for line, contexts in sorted(line_contexts[filename].items()):
            for context in contexts:
                test_id = parse_test_context(context)
                if test_id is None:
                    continue
                tests[test_id][display].add(line)
                line_tests[display][line].add(test_id)

    unique_counts = _unique_lines(tests, line_tests)
    test_entries: list[dict[str, Any]] = []
    for test_id in sorted(tests):
        covered_lines = sum(len(lines) for lines in tests[test_id].values())
        test_entries.append(
            _test_entry(
                test_id,
                covered_lines,
                unique_counts.get(test_id, 0),
                max_covered_lines,
            )
        )

    file_entries: list[dict[str, Any]] = []
    integration_only: list[dict[str, Any]] = []
    for filename in sorted(line_tests):
        covered_lines = 0
        unique_lines = 0
        test_ids: set[str] = set()
        for line in sorted(line_tests[filename]):
            ids = line_tests[filename][line]
            if not ids:
                continue
            covered_lines += 1
            test_ids.update(ids)
            if len(ids) == 1:
                unique_lines += 1
            sorted_ids = sorted(ids)
            if all(_is_integration_test(test_id) for test_id in sorted_ids):
                integration_only.append({"file": filename, "line": line, "tests": sorted_ids})
        file_entries.append(
            {
                "file": filename,
                "tests": len(test_ids),
                "covered_lines": covered_lines,
                "unique_lines": unique_lines,
            }
        )

    summary = {
        "tests": len(test_entries),
        "no_unique_coverage": sum(
            1 for entry in test_entries if "no_unique_coverage" in entry["signals"]
        ),
        "god_test": sum(1 for entry in test_entries if "god_test" in entry["signals"]),
        "integration_only_lines": len(integration_only),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "summary": summary,
        "tests": test_entries,
        "integration_only_lines": integration_only,
        "files": file_entries,
    }


def render_json(report: Mapping[str, Any]) -> str:
    """Render laporan sebagai JSON deterministik."""
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render laporan sebagai ringkasan dan tabel Markdown."""
    summary = report["summary"]
    lines = [
        "# Laporan coverage context",
        "",
        f"- Tests: **{summary['tests']}**",
        f"- `no_unique_coverage`: **{summary['no_unique_coverage']}**",
        f"- `god_test`: **{summary['god_test']}**",
        f"- `integration_only_lines`: **{summary['integration_only_lines']}**",
        "",
        "## Ringkasan per file",
        "",
        "| File | Test | Baris dicakup | Baris unik |",
        "| --- | ---: | ---: | ---: |",
    ]
    for entry in report["files"]:
        lines.append(
            f"| {_markdown_cell(entry['file'])} | {entry['tests']} | "
            f"{entry['covered_lines']} | {entry['unique_lines']} |"
        )
    lines.extend(
        [
            "",
            "## Test",
            "",
            "| Test | Baris dicakup | Baris unik | Verdict | Confidence | Signal | Aksi |",
            "| --- | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for entry in report["tests"]:
        signals = ", ".join(entry["signals"]) if entry["signals"] else "-"
        lines.append(
            f"| {_markdown_cell(entry['id'])} | {entry['covered_lines']} | "
            f"{entry['unique_lines']} | {entry['verdict']} | {entry['confidence']} | "
            f"{signals} | {_markdown_cell(entry['suggested_action'])} |"
        )
    lines.extend(
        [
            "",
            "## Baris hanya integration/e2e",
            "",
            f"Confidence: high. Aksi: {INTEGRATION_ONLY_ACTION}.",
            "",
            "| File | Baris | Test |",
            "| --- | ---: | --- |",
        ]
    )
    for entry in report["integration_only_lines"]:
        tests = ", ".join(entry["tests"])
        lines.append(
            f"| {_markdown_cell(entry['file'])} | {entry['line']} | {_markdown_cell(tests)} |"
        )
    return "\n".join(lines) + "\n"


def should_fail(report: Mapping[str, Any], fail_on: str) -> bool:
    """True bila ada temuan pada atau di atas ambang ``fail_on``."""
    threshold = CONFIDENCE_ORDER[fail_on]
    for entry in report["tests"]:
        if entry["signals"] and CONFIDENCE_ORDER[entry["confidence"]] >= threshold:
            return True
    if report["integration_only_lines"]:
        return CONFIDENCE_ORDER["high"] >= threshold
    return False


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("nilai harus bilangan bulat positif")
    return number


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI."""
    parser = argparse.ArgumentParser(
        description="Analisis coverage context dari berkas .coverage.",
    )
    parser.add_argument("--coverage-file", default=".coverage", metavar="PATH")
    parser.add_argument("--source", default=DEFAULT_SOURCE, metavar="PATH")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="format keluaran; default json",
    )
    parser.add_argument("--output", metavar="PATH")
    parser.add_argument(
        "--max-covered-lines",
        type=_positive_int,
        default=DEFAULT_MAX_COVERED_LINES,
        metavar="N",
    )
    parser.add_argument("--fail-on", choices=("high", "medium", "low"))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Jalankan analyzer dan kembalikan kode keluar."""
    args = build_parser().parse_args(argv)
    coverage_file = Path(args.coverage_file)
    if not coverage_file.is_file():
        print(f"error: berkas coverage tidak ditemukan: {coverage_file}", file=sys.stderr)
        return 2
    line_contexts = read_coverage(coverage_file, args.source)
    report = analyze_contexts(
        line_contexts,
        source=args.source,
        max_covered_lines=args.max_covered_lines,
    )
    text = render_json(report) if args.format == "json" else render_markdown(report)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.fail_on and should_fail(report, args.fail_on):
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main(sys.argv[1:]))
