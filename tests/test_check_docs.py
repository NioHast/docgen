"""Tes checker dokumentasi dan registry referensi."""

from pathlib import Path

import check_docs

REGISTRY_VALID = """# Referensi

| Label | URL | Dipakai untuk |
| --- | --- | --- |
| Python 3.15 | https://docs.python.org/3.15/ | Bahasa. |
| Ruff rules | https://docs.astral.sh/ruff/rules/ | Lint. |
"""


def _tulis(akar: Path, nama: str, teks: str) -> Path:
    jalur = akar / nama
    jalur.parent.mkdir(parents=True, exist_ok=True)
    jalur.write_text(teks, encoding="utf-8")
    return jalur


def _tulis_registry(akar: Path, teks: str = REGISTRY_VALID) -> Path:
    return _tulis(akar, "docs/dev/references.md", teks)


def test_tautan_relatif_valid(tmp_path: Path) -> None:
    _tulis(tmp_path, "docs/panduan.md", "# Panduan\n")
    _tulis(
        tmp_path,
        "README.md",
        "[Panduan](docs/panduan.md)\n[Bagian](docs/panduan.md#mulai)\n",
    )

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.berkas == 2
    assert hasil.tautan == 2
    assert hasil.masalah == ()


def test_tautan_relatif_rusak_terdeteksi(tmp_path: Path) -> None:
    _tulis(tmp_path, "README.md", "# Judul\n\n[Hilang](docs/hilang.md)\n")

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.tautan == 1
    assert len(hasil.masalah) == 1
    assert hasil.masalah[0].berkas == "README.md"
    assert hasil.masalah[0].baris == 3
    assert "docs/hilang.md" in hasil.masalah[0].pesan


def test_url_eksternal_diabaikan(tmp_path: Path) -> None:
    _tulis(
        tmp_path,
        "README.md",
        "[Python](https://docs.python.org/3.15/)\n"
        "[Pandoc](<https://pandoc.org/MANUAL.html>)\n"
        "[Surel](mailto:contoh@example.com)\n",
    )

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.tautan == 0
    assert hasil.masalah == ()


def test_anchor_same_file_diabaikan(tmp_path: Path) -> None:
    _tulis(tmp_path, "README.md", "[Bagian](#bagian)\n[Atas](#)\n")

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.tautan == 0
    assert hasil.masalah == ()


def test_kode_fence_dan_inline_code_diabaikan(tmp_path: Path) -> None:
    _tulis(
        tmp_path,
        "README.md",
        "`[inline](hilang-inline.md)`\n\n"
        "```markdown\n[fence](hilang-fence.md)\n```\n\n"
        "[nyata](hilang-nyata.md)\n",
    )

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.tautan == 1
    assert len(hasil.masalah) == 1
    assert "hilang-nyata.md" in hasil.masalah[0].pesan


def test_readme_di_luar_docs_dipindai(tmp_path: Path) -> None:
    _tulis(tmp_path, "src/docgen/README.md", "# Modul\n\n[Panduan](panduan.md)\n")
    _tulis(tmp_path, "src/docgen/panduan.md", "# Panduan\n")
    _tulis(tmp_path, "src/docgen/docx/README.md", "# DOCX\n")
    _tulis(tmp_path, "tests/README.md", "# Tes\n")
    _tulis(tmp_path, "tools/README.md", "# Alat\n")
    _tulis(tmp_path, "scripts/README.md", "# Skrip\n")

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.berkas == 5
    assert hasil.tautan == 1
    assert hasil.masalah == ()


def test_tautan_rusak_di_readme_luar_docs_terdeteksi(tmp_path: Path) -> None:
    _tulis(tmp_path, "tests/README.md", "# Tes\n\n[Hilang](hilang.md)\n")

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.tautan == 1
    assert len(hasil.masalah) == 1
    assert hasil.masalah[0].berkas == "tests/README.md"
    assert hasil.masalah[0].baris == 3
    assert "hilang.md" in hasil.masalah[0].pesan


def test_arsip_dikecualikan(tmp_path: Path) -> None:
    _tulis(tmp_path, "docs/dev/archive/lama.md", "[Hilang](tidak-ada.md)\n")
    _tulis(tmp_path, "src/docgen/README.md", "# Modul\n")

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.berkas == 1
    assert hasil.masalah == ()


def test_dokumen_panjang_tanpa_toc_terdeteksi(tmp_path: Path) -> None:
    _tulis(tmp_path, "docs/panjang.md", "# Panjang\n\n" + "Isi paragraf.\n" * 160)

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert len(hasil.masalah) == 1
    assert hasil.masalah[0].berkas == "docs/panjang.md"
    assert "tanpa daftar isi" in hasil.masalah[0].pesan


def test_anchor_toc_tidak_valid_terdeteksi(tmp_path: Path) -> None:
    _tulis(
        tmp_path,
        "docs/panjang.md",
        "# Panjang\n\n## Daftar isi\n\n- [Hilang](#bagian-hilang)\n\n"
        "## Bagian\n\n" + "Isi paragraf.\n" * 160,
    )

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert len(hasil.masalah) == 1
    assert "anchor daftar isi tidak valid" in hasil.masalah[0].pesan


def test_toc_valid_diterima(tmp_path: Path) -> None:
    _tulis(
        tmp_path,
        "docs/panjang.md",
        "# Panjang\n\n## Daftar isi\n\n- [Bagian](#bagian)\n\n"
        "## Bagian\n\n" + "Isi paragraf.\n" * 160,
    )

    hasil = check_docs.periksa_dokumen(tmp_path)

    assert hasil.toc == 1
    assert hasil.masalah == ()


def test_registry_valid(tmp_path: Path) -> None:
    jalur = _tulis_registry(tmp_path)

    hasil = check_docs.periksa_registry(jalur)

    assert hasil.entri == 2
    assert hasil.masalah == ()


def test_registry_url_duplikat_dan_invalid_terdeteksi(tmp_path: Path) -> None:
    jalur = _tulis_registry(
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

    hasil = check_docs.periksa_registry(jalur)

    assert hasil.entri == 5
    assert len(hasil.masalah) == 4
    pesan = " ".join(masalah.pesan for masalah in hasil.masalah)
    assert "URL duplikat" in pesan
    assert pesan.count("URL tidak valid") == 3


def test_registry_label_duplikat_terdeteksi(tmp_path: Path) -> None:
    jalur = _tulis_registry(
        tmp_path,
        """| Label | URL | Dipakai untuk |
| --- | --- | --- |
| Ruff | https://docs.astral.sh/ruff/rules/ | Lint. |
| ruff | https://docs.astral.sh/ruff/configuration/ | Konfigurasi. |
""",
    )

    hasil = check_docs.periksa_registry(jalur)

    assert len(hasil.masalah) == 1
    assert "label duplikat" in hasil.masalah[0].pesan


def test_periksa_menggabungkan_dokumen_dan_registry(tmp_path: Path) -> None:
    _tulis_registry(tmp_path)
    _tulis(tmp_path, "docs/panduan.md", "# Panduan\n")
    _tulis(
        tmp_path,
        "README.md",
        "[Panduan](docs/panduan.md)\n[Hilang](docs/hilang.md)\n",
    )

    hasil = check_docs.periksa(tmp_path)

    assert hasil.berkas == 3
    assert hasil.tautan == 2
    assert hasil.entri == 2
    assert len(hasil.masalah) == 1
    assert hasil.masalah[0].berkas == "README.md"


def test_main_mengembalikan_exit_code(tmp_path: Path) -> None:
    _tulis_registry(tmp_path)
    _tulis(tmp_path, "README.md", "[Hilang](docs/hilang.md)\n")

    assert check_docs.main([str(tmp_path)]) == 1

    _tulis(tmp_path, "docs/hilang.md", "# Ada\n")
    assert check_docs.main([str(tmp_path)]) == 0


def test_refactor_plan_archive_memuat_banner_archived() -> None:
    akar = Path(__file__).resolve().parents[1]
    teks = (akar / "docs/dev/archive/refactor-plan.md").read_text(encoding="utf-8")

    assert teks.startswith("> **ARCHIVED**:")
