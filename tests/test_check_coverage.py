"""Tes analyzer coverage context dan pembacaan ``CoverageData``."""

import json
from pathlib import Path

import check_coverage
from coverage import CoverageData

SOURCE = "src/docgen"
UNIT_A = "tests/unit/test_a.py::test_a|run"
UNIT_B = "tests/unit/test_b.py::test_b|run"
INTEGRATION = "tests/integration/test_flow.py::test_flow|run"
E2E = "tests/e2e/test_app.py::test_app|run"


def _entry(report: dict[str, object], test_id: str) -> dict[str, object]:
    entries = [entry for entry in report["tests"] if entry["id"] == test_id]
    assert len(entries) == 1
    return entries[0]


def _write_sample_coverage(root: Path) -> tuple[Path, Path]:
    """Tulis data coverage sintetis lewat API ``CoverageData``."""
    package = root / "src" / "docgen"
    package.mkdir(parents=True)
    module = package / "mod.py"
    module.write_text(
        "def f():\n    return 1\n\ndef g():\n    return 2\n",
        encoding="utf-8",
    )
    outside = root / "src" / "other.py"
    outside.write_text("value = 1\n", encoding="utf-8")
    coverage_file = root / ".coverage"
    data = CoverageData(basename=str(coverage_file))
    data.set_context("tests/unit/test_mod.py::test_f|run")
    data.add_lines({str(module): {1, 2}})
    data.set_context("tests/unit/test_mod.py::test_f|setup")
    data.add_lines({str(module): {2, 3}})
    data.set_context("tests/integration/test_flow.py::test_flow|run")
    data.add_lines({str(module): {4, 5}})
    data.set_context("tests/integration/test_flow.py::test_flow|teardown")
    data.add_lines({str(module): {5}})
    data.add_lines({str(outside): {1}})
    data.write()
    return coverage_file, module


def test_parse_test_context_only_accepts_run_phase() -> None:
    assert check_coverage.parse_test_context(UNIT_A) == "tests/unit/test_a.py::test_a"
    assert check_coverage.parse_test_context("tests/unit/test_a.py::test_a|setup") is None
    assert check_coverage.parse_test_context("tests/unit/test_a.py::test_a|teardown") is None
    assert check_coverage.parse_test_context("tests/unit/test_a.py::test_a") is None
    assert check_coverage.parse_test_context("") is None
    assert check_coverage.parse_test_context("|run") is None


def test_unique_and_overlapping_lines() -> None:
    report = check_coverage.analyze_contexts(
        {
            f"{SOURCE}/mod.py": {
                1: [UNIT_A],
                2: [UNIT_A, UNIT_B],
                3: [UNIT_B],
            }
        },
        source=SOURCE,
    )

    test_a = _entry(report, "tests/unit/test_a.py::test_a")
    test_b = _entry(report, "tests/unit/test_b.py::test_b")
    assert test_a["covered_lines"] == 2
    assert test_a["unique_lines"] == 1
    assert test_a["verdict"] == "KEEP"
    assert test_a["confidence"] == "high"
    assert test_a["signals"] == []
    assert test_b["covered_lines"] == 2
    assert test_b["unique_lines"] == 1
    assert report["summary"] == {
        "tests": 2,
        "no_unique_coverage": 0,
        "god_test": 0,
        "integration_only_lines": 0,
    }
    assert report["files"] == [
        {
            "file": f"{SOURCE}/mod.py",
            "tests": 2,
            "covered_lines": 3,
            "unique_lines": 2,
        }
    ]
    assert report["integration_only_lines"] == []


def test_test_without_unique_lines_is_keep_weak_not_merge() -> None:
    report = check_coverage.analyze_contexts(
        {
            f"{SOURCE}/mod.py": {
                1: [UNIT_A, UNIT_B],
                2: [UNIT_A, UNIT_B],
            }
        },
        source=SOURCE,
    )

    test_a = _entry(report, "tests/unit/test_a.py::test_a")
    assert test_a["unique_lines"] == 0
    assert test_a["verdict"] == "KEEP-WEAK"
    assert test_a["confidence"] == "low"
    assert test_a["signals"] == ["no_unique_coverage"]
    assert test_a["suggested_action"] == (
        "Periksa overlap; test dengan banyak baris sama belum tentu duplikat. "
        "Bandingkan assertion dan tujuan test."
    )
    assert test_a["verdict"] != "MERGE"
    assert test_a["verdict"] != "REMOVE"
    assert report["summary"]["no_unique_coverage"] == 2


def test_god_test_threshold_is_strict() -> None:
    at_limit = {line: [UNIT_A] for line in range(1, 6)}
    report = check_coverage.analyze_contexts(
        {f"{SOURCE}/mod.py": at_limit},
        source=SOURCE,
        max_covered_lines=5,
    )
    assert _entry(report, "tests/unit/test_a.py::test_a")["verdict"] == "KEEP"
    assert report["summary"]["god_test"] == 0

    over_limit = {line: [UNIT_A] for line in range(1, 7)}
    report = check_coverage.analyze_contexts(
        {f"{SOURCE}/mod.py": over_limit},
        source=SOURCE,
        max_covered_lines=5,
    )
    entry = _entry(report, "tests/unit/test_a.py::test_a")
    assert entry["covered_lines"] == 6
    assert entry["verdict"] == "TRIM"
    assert entry["confidence"] == "medium"
    assert entry["signals"] == ["god_test"]
    assert entry["suggested_action"] == "pecah per perilaku"
    assert report["summary"]["god_test"] == 1


def test_default_max_covered_lines_is_1000() -> None:
    at_limit = {line: [UNIT_A] for line in range(1, 1001)}
    report = check_coverage.analyze_contexts(
        {f"{SOURCE}/mod.py": at_limit},
        source=SOURCE,
    )
    assert _entry(report, "tests/unit/test_a.py::test_a")["verdict"] == "KEEP"
    assert report["summary"]["god_test"] == 0

    over_limit = {line: [UNIT_A] for line in range(1, 1002)}
    report = check_coverage.analyze_contexts(
        {f"{SOURCE}/mod.py": over_limit},
        source=SOURCE,
    )
    assert _entry(report, "tests/unit/test_a.py::test_a")["verdict"] == "TRIM"
    assert report["summary"]["god_test"] == 1


def test_integration_only_lines_require_all_contexts_integration_or_e2e() -> None:
    report = check_coverage.analyze_contexts(
        {
            f"{SOURCE}/mod.py": {
                1: [INTEGRATION],
                2: [UNIT_A],
                3: [INTEGRATION, UNIT_A],
                4: [INTEGRATION, E2E],
                5: ["", INTEGRATION],
                6: ["", UNIT_A],
                7: ["tests/integration/test_flow.py::test_flow|setup", INTEGRATION],
                8: ["tests/integration/test_flow.py::test_flow|setup"],
            }
        },
        source=SOURCE,
    )

    rows = [(row["line"], row["tests"]) for row in report["integration_only_lines"]]
    assert rows == [
        (1, ["tests/integration/test_flow.py::test_flow"]),
        (4, ["tests/e2e/test_app.py::test_app", "tests/integration/test_flow.py::test_flow"]),
        (5, ["tests/integration/test_flow.py::test_flow"]),
        (7, ["tests/integration/test_flow.py::test_flow"]),
    ]
    assert report["summary"]["integration_only_lines"] == 4


def test_setup_and_teardown_contexts_do_not_count_as_coverage() -> None:
    report = check_coverage.analyze_contexts(
        {
            f"{SOURCE}/mod.py": {
                1: ["tests/unit/test_a.py::test_a|setup"],
                2: [UNIT_A, "tests/unit/test_a.py::test_a|teardown"],
                3: [UNIT_A],
            }
        },
        source=SOURCE,
    )

    entry = _entry(report, "tests/unit/test_a.py::test_a")
    assert entry["covered_lines"] == 2
    assert entry["unique_lines"] == 2
    assert report["files"] == [
        {
            "file": f"{SOURCE}/mod.py",
            "tests": 1,
            "covered_lines": 2,
            "unique_lines": 2,
        }
    ]
    assert report["integration_only_lines"] == []


def test_non_source_files_are_ignored() -> None:
    report = check_coverage.analyze_contexts(
        {
            f"{SOURCE}/mod.py": {1: [UNIT_A]},
            "tests/unit/test_a.py": {1: [UNIT_A, UNIT_B]},
        },
        source=SOURCE,
    )

    assert [entry["id"] for entry in report["tests"]] == ["tests/unit/test_a.py::test_a"]
    assert report["summary"]["tests"] == 1


def test_json_schema_and_determinism() -> None:
    data_a = {
        f"{SOURCE}/b.py": {5: [UNIT_B], 4: [UNIT_A, UNIT_B]},
        f"{SOURCE}/a.py": {1: [UNIT_B], 2: [UNIT_A]},
    }
    data_b = {
        f"{SOURCE}/a.py": {2: [UNIT_A], 1: [UNIT_B]},
        f"{SOURCE}/b.py": {4: [UNIT_B, UNIT_A], 5: [UNIT_B]},
    }

    report = check_coverage.analyze_contexts(data_a, source=SOURCE)
    raw = check_coverage.render_json(report)
    assert raw == check_coverage.render_json(check_coverage.analyze_contexts(data_b, source=SOURCE))

    parsed = json.loads(raw)
    assert set(parsed) == {
        "schema_version",
        "generated_by",
        "summary",
        "tests",
        "integration_only_lines",
        "files",
    }
    assert parsed["schema_version"] == 1
    assert parsed["generated_by"] == "tools/dev/check_coverage.py"
    assert set(parsed["summary"]) == {
        "tests",
        "no_unique_coverage",
        "god_test",
        "integration_only_lines",
    }
    assert [entry["id"] for entry in parsed["tests"]] == sorted(
        entry["id"] for entry in parsed["tests"]
    )
    assert [entry["file"] for entry in parsed["files"]] == sorted(
        entry["file"] for entry in parsed["files"]
    )
    assert all(
        set(entry)
        == {
            "id",
            "covered_lines",
            "unique_lines",
            "verdict",
            "confidence",
            "signals",
            "evidence",
            "suggested_action",
        }
        for entry in parsed["tests"]
    )


def test_markdown_contains_summary_and_tables() -> None:
    report = check_coverage.analyze_contexts(
        {
            f"{SOURCE}/mod.py": {
                1: [UNIT_A, UNIT_B],
                2: [UNIT_A, UNIT_B],
                3: [UNIT_A],
                4: [INTEGRATION],
            }
        },
        source=SOURCE,
    )

    markdown = check_coverage.render_markdown(report)
    assert markdown.startswith("# Laporan coverage context")
    assert "- Tests: **3**" in markdown
    assert "## Ringkasan per file" in markdown
    assert "| File | Test | Baris dicakup | Baris unik |" in markdown
    assert "## Test" in markdown
    assert (
        "| Test | Baris dicakup | Baris unik | Verdict | Confidence | Signal | Aksi |" in markdown
    )
    assert "tests/unit/test_a.py::test_a" in markdown
    assert "## Baris hanya integration/e2e" in markdown
    assert "Confidence: high. Aksi: tambah unit test atau pindahkan." in markdown
    assert "| File | Baris | Test |" in markdown


def test_fail_on_thresholds() -> None:
    weak = check_coverage.analyze_contexts(
        {f"{SOURCE}/mod.py": {1: [UNIT_A, UNIT_B]}},
        source=SOURCE,
    )
    assert check_coverage.should_fail(weak, "high") is False
    assert check_coverage.should_fail(weak, "medium") is False
    assert check_coverage.should_fail(weak, "low") is True

    high = check_coverage.analyze_contexts(
        {f"{SOURCE}/mod.py": {1: [INTEGRATION]}},
        source=SOURCE,
    )
    assert check_coverage.should_fail(high, "high") is True
    assert check_coverage.should_fail(high, "medium") is True
    assert check_coverage.should_fail(high, "low") is True

    clean = check_coverage.analyze_contexts(
        {f"{SOURCE}/mod.py": {1: [UNIT_A]}},
        source=SOURCE,
    )
    assert check_coverage.should_fail(clean, "low") is False


def test_read_coverage_uses_coverage_data_api(tmp_path: Path) -> None:
    coverage_file, module = _write_sample_coverage(tmp_path)

    collected = check_coverage.read_coverage(coverage_file, module.parent)

    assert set(collected) == {str(module)}
    assert collected[str(module)][1] == ("tests/unit/test_mod.py::test_f|run",)
    assert collected[str(module)][2] == (
        "tests/unit/test_mod.py::test_f|run",
        "tests/unit/test_mod.py::test_f|setup",
    )
    assert collected[str(module)][3] == ("tests/unit/test_mod.py::test_f|setup",)
    assert collected[str(module)][4] == ("tests/integration/test_flow.py::test_flow|run",)
    assert collected[str(module)][5] == (
        "tests/integration/test_flow.py::test_flow|run",
        "tests/integration/test_flow.py::test_flow|teardown",
    )


def test_main_json_output_and_fail_on(tmp_path: Path, capsys) -> None:
    coverage_file, module = _write_sample_coverage(tmp_path)
    common = [
        "--coverage-file",
        str(coverage_file),
        "--source",
        str(module.parent),
        "--format",
        "json",
    ]

    assert check_coverage.main(common) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["summary"] == {
        "tests": 2,
        "no_unique_coverage": 0,
        "god_test": 0,
        "integration_only_lines": 2,
    }
    assert [entry["id"] for entry in report["tests"]] == [
        "tests/integration/test_flow.py::test_flow",
        "tests/unit/test_mod.py::test_f",
    ]
    assert [row["line"] for row in report["integration_only_lines"]] == [4, 5]

    assert check_coverage.main([*common, "--fail-on", "high"]) == 1
    capsys.readouterr()


def test_default_format_is_json(tmp_path: Path, capsys) -> None:
    coverage_file, module = _write_sample_coverage(tmp_path)

    code = check_coverage.main(
        [
            "--coverage-file",
            str(coverage_file),
            "--source",
            str(module.parent),
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert check_coverage.build_parser().parse_args([]).format == "json"
    assert report["summary"]["tests"] == 2


def test_main_markdown_output_file(tmp_path: Path) -> None:
    coverage_file, module = _write_sample_coverage(tmp_path)
    output = tmp_path / "reports" / "coverage.md"

    code = check_coverage.main(
        [
            "--coverage-file",
            str(coverage_file),
            "--source",
            str(module.parent),
            "--format",
            "markdown",
            "--output",
            str(output),
        ]
    )

    assert code == 0
    assert not output.read_text(encoding="utf-8").startswith("{")
    markdown = output.read_text(encoding="utf-8")
    assert "## Ringkasan per file" in markdown
    assert "tests/unit/test_mod.py::test_f" in markdown


def test_main_rejects_missing_coverage_file(tmp_path: Path, capsys) -> None:
    code = check_coverage.main(
        [
            "--coverage-file",
            str(tmp_path / "missing.coverage"),
            "--source",
            str(tmp_path),
        ]
    )

    assert code == 2
    assert "tidak ditemukan" in capsys.readouterr().err
