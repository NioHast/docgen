"""Tes permukaan CLI, exit code, dry-run, check, dan doctor."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]


def _document(tmp_path: Path, *, body: str | None = None) -> Path:
    source = tmp_path / "document.md"
    (tmp_path / "references.bib").write_text(
        "@article{pandoc2024,\n  title = {Pandoc},\n  author = {Doe, Jane},\n  year = {2024},\n}\n",
        encoding="utf-8",
    )
    content = body or (
        "# Pendahuluan\n\nTeks pendahuluan.\n\n"
        "# Pembahasan\n\nTeks pembahasan.\n\n"
        "# Penutup\n\nTeks penutup.\n"
    )
    source.write_text(
        "---\n"
        'title: "Uji CLI"\n'
        'author: "Penulis"\n'
        'report_name: "Laporan Uji"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "---\n\n"
        f"{content}",
        encoding="utf-8",
    )
    return source


def test_help_lists_only_supported_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "build" in output
    assert "check" in output
    assert "doctor" in output
    assert "docgen" not in output


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert "autooffice 0.1.0" in capsys.readouterr().out


def test_no_command_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "build" in capsys.readouterr().out


def test_build_markdown_dry_run_writes_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _document(tmp_path)
    assert main(["build", str(source), "--target", "docx", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "[RENCANA] target: docx" in output
    assert str(tmp_path / "Laporan Uji.docx") in output
    assert not (tmp_path / "Laporan Uji.docx").exists()
    assert not (tmp_path / ".laporan").exists()


def test_build_markdown_dry_run_with_out_does_not_create_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _document(tmp_path)
    out = tmp_path / "custom"
    assert main(["build", str(source), "--target", "docx", "--out", str(out), "--dry-run"]) == 0
    assert str(out / "Laporan Uji.docx") in capsys.readouterr().out
    assert not out.exists()


def test_build_markdown_dry_run_records_expanded_home_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _document(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    assert (
        main(
            [
                "build",
                str(source),
                "--target",
                "docx",
                "--out",
                "~/records",
                "--dry-run",
            ]
        )
        == 0
    )

    assert str(home / "records" / "Laporan Uji.docx") in capsys.readouterr().out
    assert not (tmp_path / "~").exists()


def test_build_markdown_dry_run_does_not_call_build_docx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _document(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("build_docx tidak boleh dipanggil pada --dry-run")

    monkeypatch.setattr("autooffice.docx.command.build_docx", fail)
    assert main(["build", str(source), "--target", "docx", "--dry-run"]) == 0


def test_build_markdown_dry_run_lists_pdf_and_terms(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _document(tmp_path)
    assert (
        main(
            [
                "build",
                str(source),
                "--target",
                "docx,pdf",
                "--terms",
                "--dry-run",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert str(tmp_path / "Laporan Uji.pdf") in output
    assert str(tmp_path / ".laporan" / "istilah-baru.txt") in output


def test_build_requires_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _document(tmp_path)
    assert main(["build", str(source)]) == 2
    assert "--target" in capsys.readouterr().err


def test_build_rejects_invalid_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _document(tmp_path)
    assert main(["build", str(source), "--target", "pptx"]) == 2
    assert "target tidak valid" in capsys.readouterr().err


def test_build_rejects_theme_for_markdown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _document(tmp_path)
    assert main(["build", str(source), "--target", "docx", "--theme", "hitam"]) == 2
    assert "--theme" in capsys.readouterr().err


def test_build_rejects_terms_for_yaml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")
    assert main(["build", str(source), "--target", "pptx", "--terms"]) == 2
    assert "--terms" in capsys.readouterr().err


def test_build_rejects_sync_without_slides(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")
    assert main(["build", str(source), "--target", "pptx", "--sync", "diff"]) == 2
    assert "--sync" in capsys.readouterr().err


def test_build_rejects_unknown_sync_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")
    assert main(["build", str(source), "--target", "slides", "--sync", "nope"]) == 2
    assert "mode sync" in capsys.readouterr().err


def test_build_slides_requires_google_extra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")

    def fail() -> None:
        raise CliError(
            "extra 'google' belum terpasang",
            code="CLI-GOOGLE-EXTRA",
            exit_code=1,
        )

    monkeypatch.setattr("autooffice.cli.main.require_google_extra", fail)
    assert main(["build", str(source), "--target", "slides"]) == 1
    assert "google" in capsys.readouterr().err


def test_missing_input_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", "missing.md", "--target", "docx"]) == 2
    assert "tidak ditemukan" in capsys.readouterr().err


def test_unknown_extension_is_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "document.txt"
    source.write_text("x", encoding="utf-8")
    assert main(["build", str(source), "--target", "docx"]) == 2
    assert ".md atau .yaml" in capsys.readouterr().err


def test_out_file_is_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _document(tmp_path)
    out = tmp_path / "out"
    out.write_text("x", encoding="utf-8")
    assert main(["build", str(source), "--target", "docx", "--out", str(out), "--dry-run"]) == 2
    assert "--out" in capsys.readouterr().err


def test_check_markdown_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _document(tmp_path)
    assert main(["check", str(source)]) == 0
    output = capsys.readouterr()
    assert "[OK]" in output.out
    assert "bersih" in output.out


def test_check_markdown_reports_structure_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _document(tmp_path, body="# Pendahuluan\n\nTeks pendahuluan.\n")
    assert main(["check", str(source)]) == 1
    assert "[ERROR]" in capsys.readouterr().err


def test_check_rejects_theme_for_markdown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _document(tmp_path)
    assert main(["check", str(source), "--theme", "indigo"]) == 2
    assert "--theme" in capsys.readouterr().err


def test_check_rejects_invalid_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")
    assert main(["check", str(source), "--target", "docx"]) == 2
    assert "target tidak valid" in capsys.readouterr().err


def test_doctor_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["doctor", "--json"])
    data = json.loads(capsys.readouterr().out)
    names = {check["name"] for check in data["checks"]}
    assert {"python", "pandoc", "mmdc", "word", "powerpoint", "fonts"} <= names
    assert data["ok"] is (exit_code == 0)


def test_doctor_json_without_google_extra_is_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from autooffice.cli import doctor

    real_find_spec = importlib.util.find_spec

    def find_spec(name: str) -> object | None:
        if name == "google" or name.startswith("google."):
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_find_spec(name)

    monkeypatch.setattr(doctor.importlib.util, "find_spec", find_spec)

    exit_code = main(["doctor", "--json"])
    data = json.loads(capsys.readouterr().out)
    google = next(check for check in data["checks"] if check["name"] == "google")

    assert exit_code in (0, 1)
    assert data["ok"] is (exit_code == 0)
    assert google["ok"] is False
    assert google["detail"] == "google extra tidak terpasang"


def test_help_does_not_import_deck_google_or_pdf_domain() -> None:
    code = (
        "import sys; import autooffice.cli.main; "
        "prefixes = ('autooffice.deck', 'autooffice.google', 'autooffice.pdf'); "
        "print(','.join(sorted(m for m in sys.modules if m.startswith(prefixes))))"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=environment,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == ""
