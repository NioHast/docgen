"""Regression check: a clean-source wheel contains only the ``autooffice`` package.

The test copies the working tree without build caches or ignored artifacts,
builds a wheel in the temporary copy, and inspects the archive. A stale
``build/lib`` directory from the pre-rename distribution must never leak into a
published wheel.
"""

import configparser
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.packaging, pytest.mark.integration, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_TIMEOUT_S = 600
ENTRY_POINT = "autooffice.cli.main:main"

_EXCLUDED_NAMES = frozenset(
    {
        ".autooffice",
        ".autooffice-build",
        ".cache",
        ".eggs",
        ".git",
        ".hypothesis",
        ".idea",
        ".import_linter_cache",
        ".laporan",
        ".laporan-build",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".venv315",
        ".vscode",
        "__pycache__",
        "acuan",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "nul",
        "out",
        "review",
    }
)

_FONT_FILES = (
    "autooffice/assets/fonts/plus-jakarta-sans/OFL.txt",
    "autooffice/assets/fonts/plus-jakarta-sans/PlusJakartaSans-Bold.ttf",
    "autooffice/assets/fonts/plus-jakarta-sans/PlusJakartaSans-ExtraBold.ttf",
    "autooffice/assets/fonts/plus-jakarta-sans/PlusJakartaSans-Regular.ttf",
    "autooffice/assets/fonts/plus-jakarta-sans/PlusJakartaSans-SemiBold.ttf",
)

_PACKAGE_DATA_FILES = (
    "autooffice/design/data/themes.yaml",
    "autooffice/design/data/tokens.yaml",
    "autooffice/docx/data/formats/undip-msi/citation.csl",
    "autooffice/docx/data/formats/undip-msi/format.yml",
    "autooffice/docx/data/formats/undip-msi/logo.jpg",
    "autooffice/docx/data/formats/undip-msi/reference.docx",
    "autooffice/docx/data/glossary/istilah.tsv",
    "autooffice/docx/data/structures/assignment/structure.yml",
)


def _ignore_generated(directory: str, names: list[str]) -> set[str]:
    """Exclude VCS metadata, build outputs, caches, and ignored local inputs."""
    ignored: set[str] = set()
    for name in names:
        folded = name.casefold()
        if (
            folded in _EXCLUDED_NAMES
            or folded.endswith(".egg-info")
            or folded.startswith(".coverage")
            or folded == ".cov.json"
        ):
            ignored.add(name)
    return ignored


def _run_uv_build(source: Path, out_dir: Path) -> None:
    """Build a wheel from ``source`` with uv and fail with captured output."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv tidak tersedia di PATH")

    completed = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=BUILD_TIMEOUT_S,
    )
    assert completed.returncode == 0, (
        "uv build --wheel gagal "
        f"(exit {completed.returncode})\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )


def test_clean_source_wheel_contains_only_autooffice(tmp_path: Path) -> None:
    """A clean build ships autooffice, one console script, data, and no stale modules."""
    source = tmp_path / "source"
    shutil.copytree(REPO_ROOT, source, ignore=_ignore_generated)

    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    name = project["project"]["name"]
    version = project["project"]["version"]
    assert name == "autooffice"
    out_dir = tmp_path / "dist"
    dist_info = f"{name}-{version}.dist-info"

    _run_uv_build(source, out_dir)

    wheels = sorted(out_dir.glob(f"{name}-{version}-*.whl"))
    assert len(wheels) == 1, f"wheel tidak tunggal: {wheels}"
    wheel = wheels[0]

    with zipfile.ZipFile(wheel) as archive:
        entries = archive.namelist()
        stale = sorted(entry for entry in entries if "docgen" in entry.casefold())
        assert stale == [], f"wheel memuat modul legacy: {stale[:10]}"
        assert f"{name}/__init__.py" in entries

        top_level = archive.read(f"{dist_info}/top_level.txt").decode("utf-8").split()
        assert top_level == [name]

        parser = configparser.ConfigParser()
        parser.read_string(archive.read(f"{dist_info}/entry_points.txt").decode("utf-8"))
        assert dict(parser["console_scripts"]) == {"autooffice": ENTRY_POINT}

        missing = sorted(
            entry for entry in (*_FONT_FILES, *_PACKAGE_DATA_FILES) if entry not in entries
        )
        assert missing == [], f"package data hilang dari wheel: {missing}"
