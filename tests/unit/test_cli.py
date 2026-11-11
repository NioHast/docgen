"""Tes unit antarmuka ``docgen`` tanpa Word/Pandoc/mmdc."""

from pathlib import Path

import pytest

from docgen import cli
from docgen.errors import ConfigError
from docgen.pipeline import BuildResult

_BODY = """# Pendahuluan

Teks.

# Pembahasan

Teks.

# Penutup

Teks.
"""

_FRONT_MATTER = """title: "Laporan Uji"
author: "Nama Mahasiswa"
nim: "30000000000000"
report_name: "Tugas"
structure: assignment
format: undip-msi
bibliography: references.bib
"""


def _write_document(root: Path) -> Path:
    (root / "references.bib").write_text("@book{x}\n", encoding="utf-8", newline="\n")
    path = root / "document.md"
    path.write_text(
        "---\n" + _FRONT_MATTER + "---\n\n" + _BODY,
        encoding="utf-8",
        newline="\n",
    )
    return path


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["--version"])
    assert error.value.code == 0
    assert "docgen 0.1.0" in capsys.readouterr().out


def test_build_default_options() -> None:
    args = cli.build_parser().parse_args(["build", "document.md"])
    assert args.target == "both"
    assert args.keep is False
    assert args.terms is False
    assert args.no_manifest is False
    assert args.no_adeu is False
    assert args.allow_missing_word is False


def test_build_flag_options() -> None:
    args = cli.build_parser().parse_args(
        [
            "build",
            "document.md",
            "--target",
            "pdf",
            "--keep",
            "--terms",
            "--no-manifest",
            "--no-adeu",
            "--allow-missing-word",
        ]
    )
    assert args.target == "pdf"
    assert args.keep is True
    assert args.terms is True
    assert args.no_manifest is True
    assert args.no_adeu is True
    assert args.allow_missing_word is True


def test_build_rejects_report_name_flag() -> None:
    with pytest.raises(SystemExit) as error:
        cli.build_parser().parse_args(["build", "document.md", "--report-name", "Laporan"])

    assert error.value.code == 2


def test_reconcile_parser_registered() -> None:
    args = cli.build_parser().parse_args(
        [
            "reconcile",
            "document.md",
            "--docx",
            "Tugas.docx",
            "--manifest",
            ".laporan/manifest.json",
            "--out",
            ".laporan/reconcile.md",
        ]
    )
    assert args.command == "reconcile"
    assert args.document == "document.md"
    assert args.docx == Path("Tugas.docx")
    assert args.manifest == Path(".laporan/manifest.json")
    assert args.out == Path(".laporan/reconcile.md")


def test_reconcile_handler_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_reconcile(args: object) -> int:
        captured["document"] = args.document
        return 3

    monkeypatch.setattr(cli, "command_reconcile", fake_reconcile)
    assert cli.main(["reconcile", "document.md"]) == 3
    assert captured["document"] == "document.md"


def test_check_valid_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_document(tmp_path)
    assert cli.main(["check", str(path)]) == 0
    captured = capsys.readouterr()
    assert "[OK]" in captured.out
    assert "format=undip-msi" in captured.out


def test_check_invalid_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "document.md"
    path.write_text('---\ntitle: "Tanpa Struktur"\n---\n\n# Bab\n', encoding="utf-8")
    assert cli.main(["check", str(path)]) == 1
    assert "[ERROR]" in capsys.readouterr().err


@pytest.mark.parametrize("line", [None, 'report_name: ""\n', 'report_name: "   "\n'])
def test_check_rejects_missing_or_empty_report_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    line: str | None,
) -> None:
    (tmp_path / "references.bib").write_text("@book{x}\n", encoding="utf-8", newline="\n")
    front_matter = (
        _FRONT_MATTER.replace('report_name: "Tugas"\n', "")
        if line is None
        else _FRONT_MATTER.replace('report_name: "Tugas"\n', line)
    )
    path = tmp_path / "document.md"
    path.write_text("---\n" + front_matter + "---\n\n" + _BODY, encoding="utf-8", newline="\n")

    assert cli.main(["check", str(path)]) == 1
    error = capsys.readouterr().err
    assert "CFG-REQUIRED" in error
    assert "report_name" in error


def test_build_maps_flags_to_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(self: object, document: str | Path, options: object) -> BuildResult:
        captured["document"] = Path(document)
        captured["options"] = options

        return BuildResult(
            document=Path(document),
            docx=Path("Tugas.docx"),
            pdf=None,
            manifest=None,
            warnings=(),
            stages=(),
            kept_workspace=Path(".laporan-build"),
        )

    monkeypatch.setattr(cli.Pipeline, "run", fake_run)
    code = cli.main(
        [
            "build",
            "document.md",
            "--target",
            "docx",
            "--keep",
            "--terms",
            "--no-adeu",
            "--allow-missing-word",
        ]
    )
    assert code == 0
    options = captured["options"]
    assert options.target == "docx"
    assert options.keep is True
    assert options.terms is True
    assert options.manifest is False  # --no-adeu menyiratkan --no-manifest
    assert options.adeu is False
    assert options.allow_missing_word is True


def test_build_only_uses_python_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run(self: object, document: str | Path, options: object) -> BuildResult:
        calls.append("pipeline")
        return BuildResult(
            document=Path(document),
            docx=Path("Tugas.docx"),
            pdf=None,
            manifest=None,
            warnings=(),
            stages=(),
            kept_workspace=None,
        )

    def fail_subprocess(*args: object, **kwargs: object) -> None:
        raise AssertionError("build tidak boleh memanggil shell atau subprocess")

    monkeypatch.setattr(cli.Pipeline, "run", fake_run)
    monkeypatch.setattr(cli.subprocess, "run", fail_subprocess)
    assert cli.main(["build", "document.md", "--target", "docx"]) == 0
    assert calls == ["pipeline"]


def test_build_error_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_run(self: object, document: str | Path, options: object) -> BuildResult:
        raise ConfigError("rusak", code="CFG-TEST", path=Path(document))

    monkeypatch.setattr(cli.Pipeline, "run", fake_run)
    assert cli.main(["build", "document.md"]) == 1
    assert "CFG-TEST" in capsys.readouterr().err


def test_doctor_ready(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fake_find_tool(name: str) -> str | None:
        return "/usr/bin/pandoc" if name == "pandoc" else None

    monkeypatch.setattr(cli, "_find_tool", fake_find_tool)
    monkeypatch.setattr(cli, "_find_word", lambda: None)
    monkeypatch.setattr(cli, "_tool_version", lambda command: "pandoc 3.1")
    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "[OK] Pandoc" in output
    assert "siap untuk DOCX" in output


def test_doctor_missing_pandoc(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_find_tool", lambda name: None)
    monkeypatch.setattr(cli, "_find_word", lambda: None)
    assert cli.main(["doctor"]) == 1
    assert "belum siap" in capsys.readouterr().out


def test_check_does_not_require_pandoc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write_document(tmp_path)

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("check tidak boleh memanggil Pandoc/subprocess")

    monkeypatch.setattr(cli.subprocess, "run", fail)
    assert cli.main(["check", str(path)]) == 0
