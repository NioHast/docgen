"""Contract tests for the installed ``autooffice`` distribution.

The suite is offline: it inspects distribution metadata, the source
``pyproject.toml``, and package data paths without building a wheel.
"""

import importlib.metadata
import importlib.util
import tomllib

import pytest

from autooffice.design import fonts, tokens
from autooffice.docx import paths
from tests._helpers.paths import repo_root

pytestmark = pytest.mark.packaging

REPO_ROOT = repo_root()
ENTRY_POINT = "autooffice.cli.main:main"


def _console_scripts() -> dict[str, str]:
    """Return installed console script names mapped to their entry points."""

    return {
        entry.name: entry.value
        for entry in importlib.metadata.entry_points(group="console_scripts")
    }


def test_autooffice_console_script_is_installed() -> None:
    """The editable install exposes the ``autooffice`` console script."""

    assert _console_scripts().get("autooffice") == ENTRY_POINT


def test_font_package_data_resolves() -> None:
    """All bundled fonts and the OFL license exist inside the package."""

    for file_name in fonts.FONT_FILES:
        assert fonts.font_path(file_name).is_file(), file_name
    assert fonts.font_path(fonts.LICENSE_FILE).is_file()


def test_design_package_data_resolves() -> None:
    """Design token and theme YAML files are installed as package data."""

    assert tokens.TOKENS_PATH.is_file()
    assert tokens.THEMES_PATH.is_file()


def test_docx_package_data_resolves() -> None:
    """Format, structure, and glossary data resolve inside the package."""

    format_root = paths.format_dir("undip-msi")
    assert (format_root / "format.yml").is_file()
    assert (format_root / "citation.csl").is_file()
    assert (format_root / "reference.docx").is_file()
    assert (format_root / "logo.jpg").is_file()

    structure_root = paths.structure_dir("assignment")
    assert (structure_root / "structure.yml").is_file()

    assert paths.glossary_file().is_file()


def test_legacy_entry_point_and_package_are_removed() -> None:
    """The removed ``docgen`` package and console script are gone."""

    assert "docgen" not in _console_scripts()
    assert importlib.util.find_spec("docgen") is None


def test_pyproject_declares_autooffice_distribution() -> None:
    """The project metadata names the distribution ``autooffice``."""

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["name"] == "autooffice"
    assert pyproject["project"]["scripts"] == {"autooffice": ENTRY_POINT}


def test_pyproject_constrains_package_discovery_to_autooffice() -> None:
    """Package discovery cannot pick up a stale top-level package under ``src``."""

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = pyproject["tool"]["setuptools"]

    assert setuptools["package-dir"] == {"": "src"}
    assert setuptools["packages"]["find"] == {
        "where": ["src"],
        "include": ["autooffice*"],
    }
