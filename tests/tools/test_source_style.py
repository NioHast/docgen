"""Tes checker gaya komentar dan docstring AutoOffice."""

import json
from pathlib import Path

import pytest

from tools.quality import check_source_style


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _check(root: Path, relative: str, text: str) -> check_source_style.Result:
    _write(root, relative, text)
    return check_source_style.check([str(root / relative)], cwd=root)


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("# F1\n", "phase-tag"),
        ("# legacy\n", "legacy"),
        ("# TODO\n", "todo"),
        ("# lane\n", "lane"),
    ],
)
def test_comment_language_is_flagged(tmp_path: Path, source: str, rule: str) -> None:
    result = _check(tmp_path, "src/autooffice/sample.py", source)

    assert [item.rule for item in result.findings] == [rule]
    assert result.findings[0].line == 1


@pytest.mark.parametrize("tag", ["F0", "F1", "F2", "F3"])
def test_phase_tags_are_flagged(tmp_path: Path, tag: str) -> None:
    result = _check(tmp_path, "src/autooffice/sample.py", f"# {tag}\n")

    assert [item.rule for item in result.findings] == ["phase-tag"]


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("# Fase 1 selesai\n", "fase"),
        ("# Tahap 2 selesai\n", "tahap"),
        ("# Rencana 3 selesai\n", "rencana"),
        ("# Phase 4 selesai\n", "phase"),
        ("# Milestone satu\n", "milestone"),
        ("# Sprint dua\n", "sprint"),
        ("# Iterasi 3\n", "iterasi"),
        ("# Iterasi: lanjut\n", "iterasi"),
        ("# Iterasi\n", "iterasi"),
        ("# FIXME\n", "fixme"),
    ],
)
def test_history_language_is_flagged(tmp_path: Path, source: str, rule: str) -> None:
    result = _check(tmp_path, "src/autooffice/sample.py", source)

    assert [item.rule for item in result.findings] == [rule]


def test_iteration_domain_prose_passes(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        "def iter_bookmarks() -> None:\n"
        '    """Iterasi bookmark, iterasi caption, dan iterasi ``w:fldChar``."""\n'
        "    # Nomor dan iterasi tabel tetap prosa domain.\n"
        "    # Setiap iterasi.\n"
        "    return None\n",
    )

    assert result.findings == ()


def test_indonesian_prose_without_tags_passes(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        '"""Laporan ini merangkum isi dokumen."""\n'
        "\n"
        "def build_report() -> str:\n"
        "    # Hitung jumlah baris lalu simpan hasilnya.\n"
        "    # rencana layout memakai grid dua kolom dan layout plan tetap stabil.\n"
        '    return "laporan"\n',
    )

    assert result.findings == ()


def test_string_literal_with_tags_passes(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        'value = "F1 legacy TODO lane"\n',
    )

    assert result.findings == ()


def test_phase_tag_in_identifier_or_fixture_passes(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        'def test_f0_contract() -> None:\n    fixture = "F0"\n    assert fixture\n',
    )

    assert result.findings == ()


@pytest.mark.parametrize(
    "relative",
    [
        "tools/quality/check_no_legacy.py",
        "tests/tools/test_no_legacy.py",
    ],
)
def test_legacy_domain_file_is_allowed(tmp_path: Path, relative: str) -> None:
    result = _check(tmp_path, relative, "# legacy dan riwayat migrasi\n")

    assert result.findings == ()


def test_legacy_outside_domain_file_is_flagged(tmp_path: Path) -> None:
    result = _check(tmp_path, "src/autooffice/sample.py", "# legacy package\n")

    assert [item.rule for item in result.findings] == ["legacy"]


def test_docstring_language_is_flagged(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        'def build_report() -> str:\n    """F1 legacy TODO lane"""\n    return "ok"\n',
    )

    assert {(item.line, item.rule) for item in result.findings} == {
        (2, "phase-tag"),
        (2, "legacy"),
        (2, "todo"),
        (2, "lane"),
    }


def test_style_ok_comment_suppresses_the_same_line(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        "# F1 legacy TODO lane # style-ok\n",
    )

    assert result.findings == ()


def test_style_ok_after_docstring_suppresses_the_docstring(tmp_path: Path) -> None:
    result = _check(
        tmp_path,
        "src/autooffice/sample.py",
        'def build_report() -> str:\n    """F1\n    TODO\n    """  # style-ok\n    return "ok"\n',
    )

    assert result.findings == ()


def test_default_paths_cover_source_tests_and_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "src/autooffice/sample.py", "# F1\n")
    _write(tmp_path, "tests/test_sample.py", "# legacy\n")
    _write(tmp_path, "tools/quality/sample.py", "# TODO\n")
    monkeypatch.chdir(tmp_path)

    result = check_source_style.check()

    assert result.file_count == 3
    assert {item.file for item in result.findings} == {
        "src/autooffice/sample.py",
        "tests/test_sample.py",
        "tools/quality/sample.py",
    }


def test_json_format_is_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "sample.py", "# F1\n")

    code = check_source_style.main(["--format", "json", str(path)])

    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["files"] == 1
    assert data["findings"] == 1
    assert data["violations"][0]["rule"] == "phase-tag"
    assert data["violations"][0]["message"] == "F1"


def test_text_output_uses_diagnostic_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "sample.py", "# F1\n")

    code = check_source_style.main([str(path)])

    assert code == 1
    assert f"{path.as_posix()}:1: [phase-tag] F1" in capsys.readouterr().out


def test_list_prints_rules(capsys: pytest.CaptureFixture[str]) -> None:
    code = check_source_style.main(["--list"])

    output = capsys.readouterr().out
    assert code == 0
    assert "phase-tag" in output
    assert "legacy" in output
    assert "allowance:" in output
    assert "tools/quality/check_no_legacy.py" in output


def test_missing_path_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = check_source_style.main([str(tmp_path / "missing")])

    assert code == 2
    assert "path tidak ditemukan" in capsys.readouterr().err
