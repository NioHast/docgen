"""Validasi kebersihan fixture golden.

Fixture tidak boleh memuat token historis terlarang, tidak boleh menyimpan PDF
baseline, dan catatan JSON tidak boleh menunjuk field ``fixture`` yang membuat
tes bergantung pada berkas PDF yang tidak di-commit.
"""

import json
import zipfile
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "golden"
DOCX_FIXTURE = GOLDEN_DIR / "laporan-baseline.docx"
JSON_FIXTURES = sorted(GOLDEN_DIR.glob("*.json"))
FORBIDDEN_TOKEN = b"typst"


def _iter_json_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_iter_json_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_iter_json_keys(child))
    return keys


def test_golden_fixture_files_exist() -> None:
    assert DOCX_FIXTURE.is_file(), f"fixture DOCX tidak ada: {DOCX_FIXTURE}"
    assert JSON_FIXTURES, "tidak ada catatan JSON golden"
    assert (GOLDEN_DIR / "pdf-baseline.json").is_file()
    assert (GOLDEN_DIR / "baseline-4a5b777.json").is_file()


def test_docx_fixture_has_no_forbidden_token() -> None:
    assert DOCX_FIXTURE.is_file(), f"fixture DOCX tidak ada: {DOCX_FIXTURE}"
    with zipfile.ZipFile(DOCX_FIXTURE) as archive:
        for name in archive.namelist():
            payload = archive.read(name).lower()
            assert FORBIDDEN_TOKEN not in payload, f"teks terlarang ditemukan di {name}"


def test_json_fixtures_have_no_forbidden_token() -> None:
    assert JSON_FIXTURES, "tidak ada catatan JSON golden"
    for path in JSON_FIXTURES:
        payload = path.read_text(encoding="utf-8")
        assert FORBIDDEN_TOKEN.decode("ascii") not in payload.casefold(), (
            f"teks terlarang ditemukan di {path.name}"
        )


def test_json_fixtures_have_no_fixture_field() -> None:
    assert JSON_FIXTURES, "tidak ada catatan JSON golden"
    for path in JSON_FIXTURES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        keys = _iter_json_keys(payload)
        assert "fixture" not in keys, f"field 'fixture' masih ada di {path.name}"


def test_no_pdf_baseline_fixture() -> None:
    assert not (GOLDEN_DIR / "laporan-baseline.pdf").exists(), (
        "fixture PDF baseline tidak boleh disimpan di repo"
    )
    assert not list(GOLDEN_DIR.glob("*.pdf")), "tidak boleh ada fixture PDF di direktori golden"
