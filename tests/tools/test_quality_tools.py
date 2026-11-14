"""Tes checker dokumentasi, checker test, dan parser gate AutoOffice."""

import subprocess
from pathlib import Path

import pytest

from tools.quality import check_docs, check_tests, gate

REGISTRY_VALID = """# Referensi

| Label | URL | Dipakai untuk |
| --- | --- | --- |
| Python 3.15 | https://docs.python.org/3.15/ | Bahasa. |
| Ruff | https://docs.astral.sh/ruff/ | Lint. |
"""


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _docs_clean(root: Path) -> None:
    _write(root, "README.md", "# Repo\n")
    _write(
        root,
        "docs/README.md",
        "# Dokumentasi\n\n[Panduan](panduan.md)\n[Referensi](dev/references.md)\n",
    )
    _write(root, "docs/panduan.md", "# Panduan\n")
    _write(root, "docs/dev/references.md", REGISTRY_VALID)


def _run_tests(root: Path, source: str) -> check_tests.Hasil:
    _write(root, "tests/test_contoh.py", source)
    return check_tests.periksa([str(root / "tests")])


def test_docs_clean_tree_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _docs_clean(tmp_path)

    result = check_docs.periksa(tmp_path)
    code = check_docs.main([str(tmp_path)])

    assert result.masalah == ()
    assert result.berkas == 4
    assert result.entri == 2
    assert code == 0
    assert "Broken: 0" in capsys.readouterr().out


def test_docs_detects_broken_link(tmp_path: Path) -> None:
    _write(tmp_path, "docs/README.md", "# Dokumentasi\n\n[Hilang](hilang.md)\n")

    result = check_docs.periksa_dokumen(tmp_path)

    assert len(result.masalah) == 1
    assert result.masalah[0].berkas == "docs/README.md"
    assert "tautan rusak" in result.masalah[0].pesan
    assert result.masalah[0].baris == 3


def test_docs_detects_heading_and_fence_violations(tmp_path: Path) -> None:
    _write(tmp_path, "docs/README.md", "# Dokumentasi\n\n[Contoh](contoh.md)\n")
    _write(tmp_path, "docs/contoh.md", "# Satu\n\n# Dua\n\n```\nkode\n```\n")

    result = check_docs.periksa_dokumen(tmp_path)

    pesan = " ".join(masalah.pesan for masalah in result.masalah)
    assert "judul level 1" in pesan
    assert "code fence tanpa bahasa" in pesan


def test_docs_detects_unreachable_page(tmp_path: Path) -> None:
    _write(tmp_path, "docs/README.md", "# Dokumentasi\n\n[Panduan](panduan.md)\n")
    _write(tmp_path, "docs/panduan.md", "# Panduan\n")
    _write(tmp_path, "docs/yatim.md", "# Yatim\n")

    result = check_docs.periksa_dokumen(tmp_path)

    assert len(result.masalah) == 1
    assert "tidak terjangkau" in result.masalah[0].pesan


def test_docs_detects_invalid_toc_anchor(tmp_path: Path) -> None:
    isi = "# Panjang\n\n## Daftar Isi\n\n- [Hilang](#bagian-hilang)\n\n## Bagian\n\n"
    _write(tmp_path, "docs/README.md", "# Dokumentasi\n\n[Panjang](panjang.md)\n")
    _write(tmp_path, "docs/panjang.md", isi + "Isi paragraf.\n" * 160)

    result = check_docs.periksa_dokumen(tmp_path)

    assert len(result.masalah) == 1
    assert "anchor daftar isi tidak valid" in result.masalah[0].pesan


def test_docs_registry_rejects_duplicate_and_invalid_url(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "docs/dev/references.md",
        "| Label | URL | Dipakai untuk |\n"
        "| --- | --- | --- |\n"
        "| Python | https://docs.python.org/3.15/ | Bahasa. |\n"
        "| Python lagi | https://docs.python.org/3.15/ | Duplikat. |\n"
        "| mypy | ftp://example.com/mypy | Salah. |\n",
    )

    result = check_docs.periksa_registry(path)

    assert len(result.masalah) == 2
    pesan = " ".join(masalah.pesan for masalah in result.masalah)
    assert "URL duplikat" in pesan
    assert "URL tidak valid" in pesan


def test_docs_main_returns_nonzero_on_violation(tmp_path: Path) -> None:
    _write(tmp_path, "docs/README.md", "# Dokumentasi\n\n[Hilang](hilang.md)\n")

    assert check_docs.main([str(tmp_path)]) == 1


def test_test_checker_clean_file_exits_zero(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "def test_tambah():\n    assert 2 + 2 == 4\n",
    )

    assert result.berkas == 1
    assert result.test == 1
    assert result.masalah == ()
    assert check_tests.main([str(tmp_path / "tests")]) == 0


def test_test_checker_detects_assert_true(tmp_path: Path) -> None:
    result = _run_tests(tmp_path, "def test_tautologi():\n    assert True\n")

    assert [masalah.jenis for masalah in result.masalah] == ["assert_true"]
    assert check_tests.main([str(tmp_path / "tests")]) == 1


def test_test_checker_detects_sleep(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "import time\n\ndef test_tunggu():\n    time.sleep(1)\n    assert 2 + 2 == 4\n",
    )

    assert "sleep" in {masalah.jenis for masalah in result.masalah}


def test_test_checker_detects_requests_network(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "import requests\n\ndef test_jaringan():\n"
        '    respons = requests.get("https://example.com")\n'
        "    assert respons.status_code == 200\n",
    )

    assert "network" in {masalah.jenis for masalah in result.masalah}


def test_test_checker_detects_urllib_network(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "import urllib.request\n\ndef test_jaringan():\n"
        '    respons = urllib.request.urlopen("https://example.com")\n'
        "    assert respons.status == 200\n",
    )

    assert "network" in {masalah.jenis for masalah in result.masalah}


def test_test_checker_detects_write_outside_tmp_path(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "from pathlib import Path\n\ndef test_tulis():\n"
        '    path = Path("keluaran.txt")\n'
        '    path.write_text("isi", encoding="utf-8")\n'
        '    assert path.name == "keluaran.txt"\n',
    )

    assert "write" in {masalah.jenis for masalah in result.masalah}


def test_test_checker_accepts_write_inside_tmp_path(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "def test_tulis(tmp_path):\n"
        '    path = tmp_path / "keluaran.txt"\n'
        '    path.write_text("isi", encoding="utf-8")\n'
        '    assert path.read_text(encoding="utf-8") == "isi"\n',
    )

    assert result.masalah == ()


def test_test_checker_detects_missing_assertion(tmp_path: Path) -> None:
    result = _run_tests(tmp_path, "def test_kosong():\n    pass\n")

    assert [masalah.jenis for masalah in result.masalah] == ["no_assert"]


def test_test_checker_accepts_local_assertion_helper(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "def _cek(nilai):\n    assert nilai == 4\n\ndef test_lewat_helper():\n    _cek(2 + 2)\n",
    )

    assert result.masalah == ()


def test_test_checker_detects_skip_without_reason(tmp_path: Path) -> None:
    result = _run_tests(
        tmp_path,
        "import pytest\n\n@pytest.mark.skip\ndef test_lewati():\n    assert 2 + 2 == 4\n",
    )

    assert [masalah.jenis for masalah in result.masalah] == ["skip_without_reason"]


def test_gate_parser_defaults_to_all_steps() -> None:
    args = gate.build_parser().parse_args([])

    assert args.steps == []
    assert args.list_steps is False
    assert args.dry_run is False
    assert args.keep_going is False
    assert gate.select_steps(args.steps) == gate.build_steps()


def test_gate_step_order_matches_documented_gate() -> None:
    assert gate.step_names() == (
        "format",
        "lint",
        "types",
        "imports",
        "tests",
        "coverage-policy",
        "lock",
        "docs",
        "test-quality",
        "no-legacy",
        "python-style",
    )


def test_gate_coverage_steps_use_risk_based_policy() -> None:
    steps = {step.nama: step for step in gate.build_steps()}

    assert "--cov-fail-under=90" in steps["tests"].perintah
    assert steps["coverage-policy"].perintah == (
        "uv",
        "run",
        "python",
        "tools/quality/check_coverage.py",
    )
    assert steps["coverage-policy"].memblokir is True
    assert steps["python-style"].memblokir is True


def test_gate_select_steps_preserves_gate_order() -> None:
    steps = gate.select_steps(["docs", "lint"])

    assert gate.step_names(steps) == ("lint", "docs")


def test_gate_parser_rejects_unknown_step() -> None:
    with pytest.raises(SystemExit) as error:
        gate.build_parser().parse_args(["tidak-ada"])

    assert error.value.code == 2


def test_gate_list_prints_steps(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(["--list", "docs"])

    assert code == 0
    assert "docs" in capsys.readouterr().out


def test_gate_list_includes_lock_and_no_legacy(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(["--list"])

    names = [line.split()[0] for line in capsys.readouterr().out.splitlines()]
    assert code == 0
    assert "lock" in names
    assert "no-legacy" in names


def test_gate_dry_run_does_not_execute(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(["--dry-run", "docs"])

    output = capsys.readouterr().out
    assert code == 0
    assert "tools/quality/check_docs.py" in output
    assert "pytest" not in output


def test_gate_stops_on_first_failure(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0)

    code = gate.run_steps(gate.select_steps(["lint", "docs"]), tmp_path, runner=runner)

    assert code == 1
    assert len(calls) == 1
    assert calls[0] == ("uv", "run", "ruff", "check", ".")


def test_gate_keep_going_returns_nonzero_when_a_step_fails(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0)

    code = gate.run_steps(
        gate.select_steps(["lint", "docs"]),
        tmp_path,
        runner=runner,
        keep_going=True,
    )

    assert code == 1
    assert len(calls) == 2
    assert calls[0] == ("uv", "run", "ruff", "check", ".")
    assert calls[1] == ("uv", "run", "python", "tools/quality/check_docs.py")


def test_gate_keep_going_returns_zero_when_all_steps_pass(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    code = gate.run_steps(
        gate.select_steps(["lint", "docs"]),
        tmp_path,
        runner=runner,
        keep_going=True,
    )

    assert code == 0
    assert len(calls) == 2


def test_gate_commands_never_call_live_office_or_google() -> None:
    command = " ".join(gate.format_command(step) for step in gate.build_steps()).lower()

    assert "autooffice doctor" not in command
    assert "autooffice build" not in command
    assert "google" not in command
    assert "word" not in command
    assert "powerpoint" not in command
