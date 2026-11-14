"""Tes pemeriksa path, package, dan teknologi legacy AutoOffice."""

from pathlib import Path

import pytest

from tools.quality import check_no_legacy


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _violations(root: Path) -> tuple[check_no_legacy.Violation, ...]:
    return check_no_legacy.check(root).violations


def test_clean_tree_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "README.md", "# Repo\n")
    _write(tmp_path, "src/autooffice/__init__.py", "")

    result = check_no_legacy.check(tmp_path)
    code = check_no_legacy.main([str(tmp_path)])

    assert result.file_count == 2
    assert result.violations == ()
    assert code == 0
    assert "Pelanggaran aktif: 0" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("from docgen import build\n", "docgen-import"),
        ("import docgen.cli\n", "docgen-import"),
        ("modul = docgen.docx\n", "docgen-module"),
        ("jalankan `docgen build` untuk membangun\n", "docgen-name"),
        ("metadata `docgen-golden` aktif\n", "docgen-name"),
        ("path src/docgen/lama.py tidak dipakai\n", "src-docgen"),
        ("path src/autooffice/legacy/lama.py tidak dipakai\n", "src-autooffice-legacy"),
        ("adapter scripts/word.ps1 sudah dihapus\n", "word-ps1"),
        ("manifest package.json tidak dipakai\n", "package-json"),
        ("dependency node_modules tidak dipakai\n", "node-modules"),
        ("renderer PptxGenJS sudah dihapus\n", "pptxgenjs"),
        ("renderer Reveal.js sudah dihapus\n", "reveal"),
    ],
)
def test_active_reference_is_violation(tmp_path: Path, text: str, rule: str) -> None:
    _write(tmp_path, "docs/aktif.md", text)

    assert {item.rule for item in _violations(tmp_path)} == {rule}
    assert check_no_legacy.main([str(tmp_path)]) == 1


@pytest.mark.parametrize(
    "relative",
    [
        "src/autooffice.egg-info/PKG-INFO",
        "src/docgen.egg-info/PKG-INFO",
        "build/lib/autooffice/lama.py",
        "dist/autooffice/lama.py",
        ".cache/docgen.json",
        ".pytest_cache/docgen.txt",
        ".mypy_cache/docgen.txt",
        ".ruff_cache/docgen.txt",
        ".import_linter_cache/docgen.meta.json",
        "__pycache__/docgen.cpython-315.pyc",
    ],
)
def test_ignored_artifacts_are_skipped(tmp_path: Path, relative: str) -> None:
    _write(tmp_path, relative, "from docgen import build\n")

    assert _violations(tmp_path) == ()


def test_fixture_metadata_literal_is_allowed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/dev/testing.md",
        "- `dc:creator` = `docgen-golden` (metadata historis)\n"
        "- `cp:lastModifiedBy` = `docgen-golden` (metadata historis)\n",
    )

    assert _violations(tmp_path) == ()


def test_fixture_metadata_allowance_does_not_hide_other_violations(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/dev/testing.md",
        "`docgen-golden`\nfrom docgen import build\n",
    )

    findings = _violations(tmp_path)

    assert {item.rule for item in findings} == {"docgen-import"}
    assert findings[0].line == 2


def test_fixture_metadata_literal_is_file_specific(tmp_path: Path) -> None:
    _write(tmp_path, "docs/aktif.md", "`docgen-golden`\n")

    assert {item.rule for item in _violations(tmp_path)} == {"docgen-name"}


def test_existing_legacy_paths_are_violations(tmp_path: Path) -> None:
    _write(tmp_path, "src/docgen/__init__.py", "")
    _write(tmp_path, "src/autooffice/legacy/__init__.py", "")
    _write(tmp_path, "package.json", "{}\n")
    _write(tmp_path, "node_modules/pkg/index.js", "module.exports = {};\n")
    _write(tmp_path, "scripts/word.ps1", "# adapter lama\n")

    rule = {item.rule for item in _violations(tmp_path)}

    assert rule == {
        "src-docgen",
        "src-autooffice-legacy",
        "package-json",
        "node-modules",
        "word-ps1",
    }


@pytest.mark.parametrize(
    "relative",
    [
        "AUTO_OFFICE_PLAN.md",
        "AUTO_OFFICE_EXECUTION_LOG.md",
        "docs/dev/archive/lama.md",
        "docs/dev/decisions/0001-lama.md",
        "docs/decisions/0011-f3-cleanup.md",
        "docs/contracts/cli.md",
        "docs/dev/f3-cleanup.md",
        "tests/fixtures/golden/baseline.json",
        "tests/cli/test_cli.py",
        "tests/docx/test_office.py",
        "tests/packaging/test_autooffice_package.py",
        "tests/packaging/test_wheel_contents.py",
        "tests/tools/test_no_legacy.py",
        "tests/tools/test_quality_tools.py",
        "tools/quality/check_no_legacy.py",
    ],
)
def test_historical_and_guard_paths_are_allowed(tmp_path: Path, relative: str) -> None:
    _write(
        tmp_path,
        relative,
        "from docgen import build\njalankan `docgen build`\nscripts/word.ps1\n",
    )

    assert _violations(tmp_path) == ()


def test_one_finding_per_line(tmp_path: Path) -> None:
    _write(tmp_path, "docs/aktif.md", "src/docgen dan docgen build\n")

    assert len(_violations(tmp_path)) == 1


def test_list_prints_all_targets(capsys: pytest.CaptureFixture[str]) -> None:
    code = check_no_legacy.main(["--list"])

    output = capsys.readouterr().out
    assert code == 0
    for target in (
        "src/docgen",
        "src/autooffice/legacy",
        "from docgen / import docgen",
        "docgen.<module>",
        "word.ps1",
        "package.json",
        "node_modules",
        "PptxGenJS",
        "Reveal",
    ):
        assert target in output


def test_missing_root_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = check_no_legacy.main([str(tmp_path / "tidak-ada")])

    assert code == 2
    assert "akar repo tidak ditemukan" in capsys.readouterr().err
