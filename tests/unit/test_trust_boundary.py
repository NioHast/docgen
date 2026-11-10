"""Guard trust boundary: kode pipeline hanya berasal dari package.

Folder input adalah data, bukan sumber kode. Pipeline tidak boleh memuat
``tools/``, ``scripts/``, ``docx.lua``, atau skrip shell lama dari folder
dokumen pengguna.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from docgen import paths
from docgen.pipeline import CANONICAL_STAGES

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "docgen"
FORBIDDEN = (
    "docx.lua",
    "--lua-filter",
    "build-docx.sh",
    "build.sh",
    "build-proposal.sh",
    "tools/",
    "scripts/",
)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Id node Constant yang berfungsi sebagai docstring (bukan kode)."""

    nodes: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            nodes.add(id(body[0].value))
    return nodes


def _string_constants(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.value


def test_stage_module_berada_di_dalam_package() -> None:
    """Setiap stage memakai modul package, bukan path dari folder input."""

    for spec in CANONICAL_STAGES:
        module = PACKAGE / spec.module
        assert module.is_file(), spec.module
        assert module.resolve().is_relative_to(PACKAGE.resolve())
        assert not Path(spec.module).is_absolute()
        assert ".." not in Path(spec.module).parts


def test_tidak_ada_referensi_eksekusi_kode_lama_di_package() -> None:
    """String kode (bukan docstring) tidak menunjuk skrip lama/folder input."""

    temuan: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for value in _string_constants(path):
            for needle in FORBIDDEN:
                if needle in value:
                    temuan.append(f"{path.relative_to(ROOT)}: {value!r}")
    assert temuan == []


def test_data_paket_tidak_fallback_ke_direktori_kerja(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``data_root`` selalu package, meskipun cwd berisi data lama."""

    monkeypatch.chdir(tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docx.lua").write_text("-- kode lama", encoding="utf-8")

    data = paths.data_root()
    assert data == PACKAGE / "data"
    assert data.resolve().is_relative_to(PACKAGE.resolve())
    assert not data.resolve().is_relative_to(tmp_path.resolve())
    assert paths.glossary_file() == PACKAGE / "data" / "glossary" / "istilah.tsv"
