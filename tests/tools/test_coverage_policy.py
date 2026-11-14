"""Tes kebijakan coverage berbasis risiko AutoOffice."""

import json

from hypothesis import given
from hypothesis import strategies as st

from tools.quality import check_coverage

ADAPTER_SAMPLES: tuple[str, ...] = (
    "autooffice.google.slides",
    "autooffice.pdf.word",
    "autooffice.cli.main",
    "autooffice.docx.pipeline",
)


def _module(
    name: str,
    *,
    statements: int = 10,
    missing_lines: tuple[int, ...] = (),
    branches: int = 0,
    missing_branches: tuple[tuple[int, int], ...] = (),
) -> check_coverage.ModuleCoverage:
    return check_coverage.ModuleCoverage(
        module=name,
        statements=statements,
        missing_lines=missing_lines,
        branches=branches,
        missing_branches=missing_branches,
    )


def _baseline() -> dict[str, check_coverage.ModuleCoverage]:
    stats = {name: _module(name) for name in check_coverage.CRITICAL_MODULES}
    stats.update({name: _module(name) for name in ADAPTER_SAMPLES})
    return stats


def _check(
    report: check_coverage.PolicyReport,
    scope: str,
    name: str,
) -> check_coverage.PolicyCheck:
    matches = [check for check in report.checks if check.scope == scope and check.name == name]
    assert len(matches) == 1
    return matches[0]


def test_policy_passes_when_all_thresholds_meet() -> None:
    report = check_coverage.evaluate_policy(_baseline())

    assert report.passed is True
    assert report.failures == ()
    assert _check(report, "global", "line+branch").percent == 100.0


def test_global_failure_when_combined_coverage_below_ninety() -> None:
    stats = _baseline()
    stats["autooffice.deck.render.one"] = _module(
        "autooffice.deck.render.one",
        missing_lines=tuple(range(1, 11)),
    )
    stats["autooffice.deck.render.two"] = _module(
        "autooffice.deck.render.two",
        missing_lines=tuple(range(1, 11)),
    )

    report = check_coverage.evaluate_policy(stats)
    global_check = _check(report, "global", "line+branch")

    assert global_check.percent < 90.0
    assert global_check.passed is False
    assert report.passed is False


def test_critical_failure_when_line_missing() -> None:
    target = "autooffice.deck.model.keys"
    stats = _baseline()
    stats[target] = _module(target, missing_lines=(4,))

    report = check_coverage.evaluate_policy(stats)
    check = _check(report, "critical", target)

    assert check.percent == 90.0
    assert check.passed is False
    assert report.passed is False


def test_critical_failure_when_branch_missing() -> None:
    target = "autooffice.deck.model.bindings"
    stats = _baseline()
    stats[target] = _module(target, branches=4, missing_branches=((5, 6),))

    report = check_coverage.evaluate_policy(stats)
    check = _check(report, "critical", target)

    assert check.percent < 100.0
    assert check.passed is False


def test_critical_failure_when_module_is_not_measured() -> None:
    target = "autooffice.deck.layout.grid"
    stats = _baseline()
    del stats[target]

    report = check_coverage.evaluate_policy(stats)
    check = _check(report, "critical", target)

    assert check.missing_modules == (target,)
    assert check.passed is False


def test_adapter_failure_when_package_below_eighty_five() -> None:
    target = "autooffice.google.slides"
    stats = _baseline()
    stats[target] = _module(target, missing_lines=(1, 2))

    report = check_coverage.evaluate_policy(stats)
    check = _check(report, "adapter", "autooffice.google.*")

    assert check.percent == 80.0
    assert check.passed is False
    assert report.passed is False


def test_text_output_prints_missing_lines_and_branches() -> None:
    target = "autooffice.deck.copy.rules.patterns"
    stats = _baseline()
    stats[target] = _module(
        target,
        missing_lines=(3, 4, 5, 9),
        branches=4,
        missing_branches=((2, 3), (2, -1)),
    )

    text = check_coverage.render_text(check_coverage.evaluate_policy(stats))

    assert "coverage policy: FAIL" in text
    assert "missing lines 3-5, 9" in text
    assert "missing branches 2->exit, 2->3" in text


def test_json_output_contains_missing_details() -> None:
    target = "autooffice.deck.transcript.parser"
    stats = _baseline()
    stats[target] = _module(
        target,
        missing_lines=(3, 4, 5, 9),
        branches=4,
        missing_branches=((2, 3), (2, -1)),
    )

    payload = json.loads(check_coverage.render_json(check_coverage.evaluate_policy(stats)))
    check = next(
        item for item in payload["checks"] if item["scope"] == "critical" and item["name"] == target
    )
    module = check["modules"][0]

    assert payload["passed"] is False
    assert module["missing_lines"] == [3, 4, 5, 9]
    assert module["missing_branches"] == [[2, -1], [2, 3]]


def test_list_policy_does_not_require_coverage(capsys) -> None:
    code = check_coverage.main(["--list"])

    output = capsys.readouterr().out
    assert code == 0
    assert "critical 100.00 autooffice.deck.model.keys" in output
    assert "adapter 85.00 autooffice.google.*" in output


@given(
    statements=st.integers(min_value=0, max_value=200),
    missing=st.integers(min_value=0, max_value=200),
    branches=st.integers(min_value=0, max_value=200),
    missing_branches=st.integers(min_value=0, max_value=200),
)
def test_module_percent_is_bounded(
    statements: int,
    missing: int,
    branches: int,
    missing_branches: int,
) -> None:
    missing_line_count = min(missing, statements)
    missing_branch_count = min(missing_branches, branches)
    coverage = check_coverage.ModuleCoverage(
        module="autooffice.example",
        statements=statements,
        missing_lines=tuple(range(1, missing_line_count + 1)),
        branches=branches,
        missing_branches=tuple((line, line + 1) for line in range(1, missing_branch_count + 1)),
    )

    assert 0.0 <= coverage.percent <= 100.0
    assert 0.0 <= coverage.line_percent <= 100.0
    assert 0.0 <= coverage.branch_percent <= 100.0
    if missing_line_count == 0 and missing_branch_count == 0:
        assert coverage.percent == 100.0
    else:
        assert coverage.percent < 100.0
