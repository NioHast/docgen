"""Tes checker identifier Indonesia AutoOffice."""

import json
from pathlib import Path

import pytest

from tools.quality import check_identifiers


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _check(root: Path, relative: str, text: str) -> check_identifiers.Result:
    _write(root, relative, text)
    return check_identifiers.check([str(root / relative)], cwd=root)


def test_indonesian_variable_is_flagged(tmp_path: Path) -> None:
    result = _check(tmp_path, "src/autooffice/sample.py", "nama = 'contoh'\n")

    assert [(item.line, item.name) for item in result.findings] == [(1, "nama")]
    assert str(result.findings[0]) == "src/autooffice/sample.py:1: [identifier] nama"


def test_indonesian_function_and_parameter_are_flagged(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        "def hitung(jumlah):\n    return jumlah\n",
    )

    assert {(item.line, item.name) for item in result.findings} == {
        (1, "hitung"),
        (1, "jumlah"),
        (2, "jumlah"),
    }


def test_indonesian_test_name_is_flagged(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "tests/test_sample.py",
        "def test_laporan_build():\n    assert 2 + 2 == 4\n",
    )

    assert [item.name for item in result.findings] == ["test_laporan_build"]


def test_english_identifiers_pass(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        "def build_report(path: Path) -> str:\n    value = path.name\n    return value\n",
    )

    assert result.findings == ()


def test_indonesian_comments_and_strings_pass(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        '"""Laporan memakai nama variabel Indonesia di prosa."""\n'
        "\n"
        "def build_report() -> str:\n"
        "    # Variabel nama dan laporan tidak boleh dipindai.\n"
        "    return 'nama laporan'\n",
    )

    assert result.findings == ()


@pytest.mark.parametrize("name", ["hitam", "indigo"])
def test_theme_contract_names_are_allowed(tmp_path: Path, name: str) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        f"def test_{name}_theme() -> None:\n    {name} = '{name}'\n    assert {name} == '{name}'\n",
    )

    assert result.findings == ()


def test_identifier_ok_comment_suppresses_the_same_line(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        "def hitung(jumlah):  # identifier-ok\n    return 1\n",
    )

    assert result.findings == ()


def test_identifier_ok_does_not_suppress_other_lines(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        "nama = 1  # identifier-ok\njumlah = 2\n",
    )

    assert [(item.line, item.name) for item in result.findings] == [(2, "jumlah")]


def test_collects_targets_imports_attributes_and_exceptions(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        "import laporan as report\n"
        "for baris in report.rows:\n"
        "    pass\n"
        "with open('x') as berkas:\n"
        "    pass\n"
        "values = [nama for nama in report.rows]\n"
        "try:\n"
        "    pass\n"
        "except ValueError as kesalahan:\n"
        "    pass\n"
        "report.jumlah\n",
    )

    names = {item.name for item in result.findings}
    assert {"laporan", "baris", "berkas", "nama", "kesalahan", "jumlah"} <= names


def test_default_paths_cover_source_tests_and_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "src/autooffice/sample.py", "nama = 1\n")
    _write(tmp_path, "tests/test_sample.py", "nama = 1\n")
    _write(tmp_path, "tools/quality/sample.py", "nama = 1\n")
    monkeypatch.chdir(tmp_path)

    result = check_identifiers.check()

    assert result.file_count == 3
    assert {item.file for item in result.findings} == {
        "src/autooffice/sample.py",
        "tests/test_sample.py",
        "tools/quality/sample.py",
    }


def test_json_format_is_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "sample.py", "nama = 1\n")

    code = check_identifiers.main(["--format", "json", str(path)])

    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["files"] == 1
    assert data["findings"] == 1
    assert data["violations"][0]["name"] == "nama"
    assert data["violations"][0]["rule"] == "identifier"


def test_text_output_uses_diagnostic_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "sample.py", "nama = 1\n")

    code = check_identifiers.main([str(path)])

    assert code == 1
    assert f"{path.as_posix()}:1: [identifier] nama" in capsys.readouterr().out


def test_list_prints_rules(capsys: pytest.CaptureFixture[str]) -> None:
    code = check_identifiers.main(["--list"])

    output = capsys.readouterr().out
    assert code == 0
    assert "identifier" in output
    assert "hitam" in output


def test_missing_path_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = check_identifiers.main([str(tmp_path / "missing")])

    assert code == 2
    assert "path tidak ditemukan" in capsys.readouterr().err
