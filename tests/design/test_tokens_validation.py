"""Tes jalur error validasi tokens dan themes dari data package."""

import copy
from pathlib import Path

import pytest

import autooffice.design.tokens as tokens_module
from autooffice.design.tokens import DesignTokenError, load_themes, load_tokens

_MISSING = object()


def _set_path(data: dict, path: str, value: object) -> None:
    keys = path.split(".")
    target = data
    for key in keys[:-1]:
        target = target[key]
    if value is _MISSING:
        del target[keys[-1]]
    else:
        target[keys[-1]] = value


def _read_tokens(data: dict[str, object]):
    """Ganti pembacaan YAML dengan data uji yang sudah dimutasi."""
    return lambda _path: data


def test_read_yaml_reports_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(DesignTokenError, match="tidak dapat dibaca"):
        tokens_module._read_yaml(tmp_path / "tidak-ada.yaml")


def test_read_yaml_reports_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "rusak.yaml"
    path.write_text("a: [1,\n", encoding="utf-8")

    with pytest.raises(DesignTokenError, match="bukan YAML valid"):
        tokens_module._read_yaml(path)


def test_read_yaml_requires_mapping(tmp_path: Path) -> None:
    path = tmp_path / "skalar.yaml"
    path.write_text("hanya teks\n", encoding="utf-8")

    with pytest.raises(DesignTokenError, match="wajib berupa mapping"):
        tokens_module._read_yaml(path)


def test_read_yaml_rejects_non_string_key(tmp_path: Path) -> None:
    path = tmp_path / "kunci.yaml"
    path.write_text("1: nilai\n", encoding="utf-8")

    with pytest.raises(DesignTokenError, match="kunci non-string"):
        tokens_module._read_yaml(path)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("schema", "", "teks tidak kosong"),
        ("schema", "v0", "tokens.schema"),
        ("typography.family", _MISSING, "kehilangan kunci"),
        ("extra", 1, "tak dikenal"),
        ("typography.title_pt", "besar", "berupa angka"),
        ("grid.gutter_emu", True, "bilangan bulat"),
        ("grid.gutter_emu", 0, "lebih besar dari nol"),
        ("grid.columns", 11, "bernilai 12"),
        ("colors.background", 123, "heksadesimal"),
        ("colors.background", "#12345", "enam digit"),
        ("colors.status", [], "wajib berupa mapping"),
        ("chart.series", "bukan daftar", "daftar warna"),
        ("chart.series", ["#111111", "#222222"], "tepat 4 warna"),
        ("typography.weights", [400, 600], "empat bilangan bulat"),
        ("typography.weights", [400, 600, 700, 1000], "100-900"),
    ],
    ids=[
        "empty-schema",
        "wrong-schema",
        "missing-key",
        "unexpected-key",
        "non-number",
        "bool-integer",
        "non-positive-integer",
        "grid-columns",
        "non-string-hex",
        "invalid-hex",
        "status-not-mapping",
        "series-not-list",
        "series-wrong-length",
        "weights-wrong-length",
        "weight-out-of-range",
    ],
)
def test_load_tokens_rejects_invalid_data(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    value: object,
    message: str,
) -> None:
    data = copy.deepcopy(load_tokens())
    _set_path(data, path, value)
    monkeypatch.setattr(tokens_module, "_read_yaml", _read_tokens(data))

    with pytest.raises(DesignTokenError, match=message):
        load_tokens()


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("schema", "v0", "themes.schema"),
        ("default", "hitam", "themes.default"),
        ("themes.hitam", _MISSING, "tepat:"),
        ("themes.indigo.mode", "dark", "mode wajib"),
        ("themes.indigo.label", "", "teks tidak kosong"),
        ("themes.indigo.label", _MISSING, "kehilangan kunci"),
        ("themes.indigo.extra", 1, "tak dikenal"),
        ("themes.indigo.colors", [], "wajib berupa mapping"),
        ("themes.indigo.colors.accent", 123, "heksadesimal"),
        ("themes.indigo.cover", [], "wajib berupa mapping"),
        ("themes.indigo.cover.from", "#12345", "enam digit"),
        ("themes.indigo.chart", [], "wajib berupa mapping"),
        ("themes.indigo.chart.series", "bukan daftar", "daftar warna"),
        ("themes.indigo.chart.series", ["#111111", "#222222"], "tepat 4 warna"),
    ],
    ids=[
        "wrong-schema",
        "wrong-default",
        "theme-names",
        "theme-mode",
        "empty-label",
        "missing-label",
        "unexpected-key",
        "colors-not-mapping",
        "non-string-hex",
        "cover-not-mapping",
        "invalid-hex",
        "chart-not-mapping",
        "series-not-list",
        "series-wrong-length",
    ],
)
def test_load_themes_rejects_invalid_data(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    value: object,
    message: str,
) -> None:
    data = copy.deepcopy(load_themes())
    _set_path(data, path, value)
    monkeypatch.setattr(tokens_module, "_read_yaml", _read_tokens(data))

    with pytest.raises(DesignTokenError, match=message):
        load_themes()


def test_load_themes_requires_top_level_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tokens_module, "_read_yaml", _read_tokens(["bukan", "mapping"]))

    with pytest.raises(DesignTokenError, match="wajib berupa mapping"):
        load_themes()
