"""Tes error lazy import CLI dan entrypoint ``python -m autooffice``."""

import importlib
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from autooffice.cli import CliError, require_callable, require_module
from autooffice.cli.outputs import ensure_directory

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_cli_error_formats_path_and_code() -> None:
    error = CliError("gagal", code="CLI-X", exit_code=1, path="deck.yaml")

    assert str(error) == "deck.yaml: gagal (CLI-X)"
    assert error.format() == "deck.yaml: gagal (CLI-X)"
    assert error.code == "CLI-X"
    assert error.exit_code == 1
    assert error.path == "deck.yaml"


def test_cli_error_without_path_omits_prefix() -> None:
    error = CliError("gagal")

    assert error.format() == "gagal (CLI)"
    assert error.exit_code == 2


def test_require_module_returns_imported_module() -> None:
    module = require_module("autooffice.cli.targets", "F1-CLI")

    assert module is sys.modules["autooffice.cli.targets"]


def test_require_module_missing_module_mentions_lane_and_name() -> None:
    with pytest.raises(CliError, match=r"autooffice\.tidak_ada.*F1-X") as error:
        require_module("autooffice.tidak_ada", "F1-X")

    assert error.value.code == "CLI-LANE-F1-X"
    assert error.value.exit_code == 1


def test_require_callable_returns_attribute() -> None:
    module = require_module("autooffice.cli.outputs", "F1-CLI")

    assert require_callable(module, "ensure_directory", "F1-CLI") is ensure_directory


def test_require_callable_missing_api_names_lane() -> None:
    module = require_module("autooffice.cli.outputs", "F1-CLI")

    with pytest.raises(CliError, match=r"'tidak_ada'.*F1-CLI") as error:
        require_callable(module, "tidak_ada", "F1-CLI")

    assert error.value.code == "CLI-LANE-F1-CLI"
    assert error.value.exit_code == 1


def test_python_m_autooffice_entrypoint_prints_version(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["autooffice", "--version"])

    with pytest.raises(SystemExit) as error:
        runpy.run_module("autooffice", run_name="__main__")

    assert error.value.code == 0
    assert "autooffice 0.1.0" in capsys.readouterr().out


def test_importing_entrypoint_module_does_not_run_cli() -> None:
    module = importlib.import_module("autooffice.__main__")

    assert module.__name__ == "autooffice.__main__"


def test_python_m_autooffice_subprocess_prints_version() -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "autooffice", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=environment,
        cwd=REPO_ROOT,
        timeout=60,
    )

    assert completed.returncode == 0
    assert "autooffice 0.1.0" in completed.stdout
