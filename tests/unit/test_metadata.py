"""Tes kontrak ``report_name`` dan API metadata kanonik."""

from pathlib import Path
from typing import Any

import pytest

from docgen import metadata as metadata_module
from docgen.document import parse_document
from docgen.errors import MetadataError
from docgen.metadata import Author, Metadata, normalize_metadata

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _front_matter(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "title": "Laporan Uji",
        "author": "Nama Mahasiswa",
        "report_name": "Tugas",
    }
    values.update(overrides)
    return values


def _report_name_error(values: dict[str, Any]) -> MetadataError:
    with pytest.raises(MetadataError) as error:
        normalize_metadata(values, source="test")
    return error.value


def test_report_name_required() -> None:
    values = _front_matter()
    del values["report_name"]

    error = _report_name_error(values)

    assert error.code == "CFG-REQUIRED"
    assert error.key == "report_name"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_report_name_empty_or_whitespace_rejected(value: str) -> None:
    error = _report_name_error(_front_matter(report_name=value))

    assert error.code == "CFG-REQUIRED"
    assert error.key == "report_name"


def test_report_name_preserved_after_strip() -> None:
    normalized = normalize_metadata(_front_matter(report_name="  Laporan Akhir  "), source="test")

    assert normalized.report_name == "Laporan Akhir"


def test_report_name_rejects_path_characters() -> None:
    error = _report_name_error(_front_matter(report_name="a/b"))

    assert error.code == "CFG-TYPE"
    assert error.key == "report_name"


@pytest.mark.parametrize("value", [".", "..", "laporan."])
def test_report_name_rejects_unsafe_file_name(value: str) -> None:
    error = _report_name_error(_front_matter(report_name=value))

    assert error.code == "CFG-TYPE"
    assert error.key == "report_name"


def test_metadata_requires_report_name_on_construction() -> None:
    with pytest.raises(TypeError):
        Metadata(title="Laporan Uji", authors=(Author("Nama Mahasiswa"),))


def test_old_api_report_name_and_normalize_author_missing() -> None:
    assert not hasattr(metadata_module, "DEFAULT_REPORT_NAME")
    assert not hasattr(metadata_module, "normalize_author")


@pytest.mark.parametrize(
    "path",
    sorted(_EXAMPLES.glob("*/document.md")),
    ids=lambda path: path.parent.name,
)
def test_example_writes_explicit_report_name(path: Path) -> None:
    raw = parse_document(path)

    assert "report_name" in raw.front_matter
    assert normalize_metadata(raw.front_matter, source=raw.path).report_name
