"""Tes checker dokumentasi dan registry referensi."""

from pathlib import Path

from tools.dev import check_docs

REGISTRY_VALID = """# Referensi

| Label | URL | Dipakai untuk |
| --- | --- | --- |
| Python 3.15 | https://docs.python.org/3.15/ | Bahasa. |
| Ruff rules | https://docs.astral.sh/ruff/rules/ | Lint. |
"""


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_registry(root: Path, text: str = REGISTRY_VALID) -> Path:
    return _write(root, "docs/dev/references.md", text)


def test_relative_links_valid(tmp_path: Path) -> None:
    _write(tmp_path, "docs/panduan.md", "# Panduan\n")
    _write(
        tmp_path,
        "README.md",
        "[Panduan](docs/panduan.md)\n[Bagian](docs/panduan.md#mulai)\n",
    )

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.berkas == 2
    assert result.tautan == 2
    assert result.masalah == ()


def test_broken_relative_links_detected(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# Judul\n\n[Hilang](docs/hilang.md)\n")

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.tautan == 1
    assert len(result.masalah) == 1
    assert result.masalah[0].berkas == "README.md"
    assert result.masalah[0].baris == 3
    assert "docs/hilang.md" in result.masalah[0].pesan


def test_external_urls_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "README.md",
        "[Python](https://docs.python.org/3.15/)\n"
        "[Pandoc](<https://pandoc.org/MANUAL.html>)\n"
        "[Surel](mailto:contoh@example.com)\n",
    )

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.tautan == 0
    assert result.masalah == ()


def test_same_file_anchor_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "[Bagian](#bagian)\n[Atas](#)\n")

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.tautan == 0
    assert result.masalah == ()


def test_code_fence_and_inline_code_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "README.md",
        "`[inline](hilang-inline.md)`\n\n"
        "```markdown\n[fence](hilang-fence.md)\n```\n\n"
        "[nyata](hilang-nyata.md)\n",
    )

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.tautan == 1
    assert len(result.masalah) == 1
    assert "hilang-nyata.md" in result.masalah[0].pesan


def test_readme_outside_docs_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "src/docgen/README.md", "# Modul\n\n[Panduan](panduan.md)\n")
    _write(tmp_path, "src/docgen/panduan.md", "# Panduan\n")
    _write(tmp_path, "src/docgen/docx/README.md", "# DOCX\n")
    _write(tmp_path, "tests/README.md", "# Tes\n")
    _write(tmp_path, "tools/README.md", "# Alat\n")
    _write(tmp_path, "scripts/README.md", "# Skrip\n")

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.berkas == 5
    assert result.tautan == 1
    assert result.masalah == ()


def test_broken_links_in_readme_outside_docs_detected(tmp_path: Path) -> None:
    _write(tmp_path, "tests/README.md", "# Tes\n\n[Hilang](hilang.md)\n")

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.tautan == 1
    assert len(result.masalah) == 1
    assert result.masalah[0].berkas == "tests/README.md"
    assert result.masalah[0].baris == 3
    assert "hilang.md" in result.masalah[0].pesan


def test_archive_excluded(tmp_path: Path) -> None:
    _write(tmp_path, "docs/dev/archive/lama.md", "[Hilang](tidak-ada.md)\n")
    _write(tmp_path, "src/docgen/README.md", "# Modul\n")

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.berkas == 1
    assert result.masalah == ()


def test_long_document_without_toc_detected(tmp_path: Path) -> None:
    _write(tmp_path, "docs/panjang.md", "# Panjang\n\n" + "Isi paragraf.\n" * 160)

    result = check_docs.periksa_dokumen(tmp_path)

    assert len(result.masalah) == 1
    assert result.masalah[0].berkas == "docs/panjang.md"
    assert "tanpa daftar isi" in result.masalah[0].pesan


def test_invalid_toc_anchor_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/panjang.md",
        "# Panjang\n\n## Daftar isi\n\n- [Hilang](#bagian-hilang)\n\n"
        "## Bagian\n\n" + "Isi paragraf.\n" * 160,
    )

    result = check_docs.periksa_dokumen(tmp_path)

    assert len(result.masalah) == 1
    assert "anchor daftar isi tidak valid" in result.masalah[0].pesan


def test_valid_toc_accepted(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/panjang.md",
        "# Panjang\n\n## Daftar isi\n\n- [Bagian](#bagian)\n\n"
        "## Bagian\n\n" + "Isi paragraf.\n" * 160,
    )

    result = check_docs.periksa_dokumen(tmp_path)

    assert result.toc == 1
    assert result.masalah == ()


def test_registry_valid(tmp_path: Path) -> None:
    path = _write_registry(tmp_path)

    result = check_docs.periksa_registry(path)

    assert result.entri == 2
    assert result.masalah == ()


def test_registry_duplicate_and_invalid_url_detected(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        """| Label | URL | Dipakai untuk |
| --- | --- | --- |
| Python 3.15 | https://docs.python.org/3.15/ | Bahasa. |
| Ruff rules | https://docs.python.org/3.15/ | Duplikat. |
| mypy | ftp://example.com/mypy | Skema salah. |
| uv | docs.astral.sh/uv/ | Tanpa skema. |
| pypdf | https://example.com:port | Port salah. |
""",
    )

    result = check_docs.periksa_registry(path)

    assert result.entri == 5
    assert len(result.masalah) == 4
    message = " ".join(issue.pesan for issue in result.masalah)
    assert "URL duplikat" in message
    assert message.count("URL tidak valid") == 3


def test_registry_duplicate_label_detected(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        """| Label | URL | Dipakai untuk |
| --- | --- | --- |
| Ruff | https://docs.astral.sh/ruff/rules/ | Lint. |
| ruff | https://docs.astral.sh/ruff/configuration/ | Konfigurasi. |
""",
    )

    result = check_docs.periksa_registry(path)

    assert len(result.masalah) == 1
    assert "label duplikat" in result.masalah[0].pesan


def test_check_combines_documents_and_registry(tmp_path: Path) -> None:
    _write_registry(tmp_path)
    _write(tmp_path, "docs/panduan.md", "# Panduan\n")
    _write(
        tmp_path,
        "README.md",
        "[Panduan](docs/panduan.md)\n[Hilang](docs/hilang.md)\n",
    )

    result = check_docs.periksa(tmp_path)

    assert result.berkas == 3
    assert result.tautan == 2
    assert result.entri == 2
    assert len(result.masalah) == 1
    assert result.masalah[0].berkas == "README.md"


def test_main_returns_exit_code(tmp_path: Path) -> None:
    _write_registry(tmp_path)
    _write(tmp_path, "README.md", "[Hilang](docs/hilang.md)\n")

    assert check_docs.main([str(tmp_path)]) == 1

    _write(tmp_path, "docs/hilang.md", "# Ada\n")
    assert check_docs.main([str(tmp_path)]) == 0
