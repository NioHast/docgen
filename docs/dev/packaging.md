# Packaging

AutoOffice dipakai sebagai project `uv` repo-local. Entry point tidak perlu
dipasang global. Perintah dari direktori mana pun:

```bash
uv run --project <repo> autooffice --version
uv run --project <repo> autooffice check document.md
```

`uv` membaca `pyproject.toml` dan `uv.lock`, lalu menjalankan perintah di
environment proyek.

## Metadata paket

`pyproject.toml` menetapkan:

| Bagian | Nilai |
| --- | --- |
| Versi | `0.1.0` |
| Python | `>=3.15` |
| Build backend | `setuptools.build_meta` |
| Entry point | `autooffice = "autooffice.cli.main:main"` |
| Package discovery | `src` |
| Package data | `autooffice = ["assets/**/*", "design/data/**/*", "docx/data/**/*"]` |

Nama distribusi dan entry point resmi adalah `autooffice`.

## Dependensi

| Jenis | Paket | Alasan |
| --- | --- | --- |
| Runtime | `lxml`, `python-pptx`, `ruamel.yaml` | Parser DOCX/XML, renderer PPTX, dan parser YAML. |
| Dev | `pytest`, `pypdf`, `python-docx`, `mypy`, `ruff`, `pytest-cov`, `hypothesis`, `import-linter`, `cosmic-ray` | Tes dan tooling pengembangan. |
| Google | `google-api-python-client`, `google-auth-oauthlib` | Target `slides` dan sinkronisasi Google. |
| Windows | `pywin32` | Word dan PowerPoint COM untuk PDF dan embedding font. |

`python-docx` hanya dependensi dev. Paket itu dipakai tes untuk membuat
fixture DOCX dan memeriksa hasil build, bukan oleh pipeline produksi. `pypdf`
juga hanya untuk tes PDF.

`src/autooffice/docx/data/` wajib ikut sebagai package data karena berisi
format, struktur, template, glosarium, logo, CSL, dan `reference.docx`. Data
dibaca lewat `src/autooffice/docx/paths.py`; tidak ada fallback ke direktori
kerja. Aset font PPTX berada di `src/autooffice/assets/fonts/` dan data design
di `src/autooffice/design/data/`.

## Environment pengembangan

```bash
uv sync --extra dev
uv run --extra dev pytest tests/cli tests/docx
```

Dari luar repo, tambahkan `--project <repo>`:

```bash
uv sync --project <repo> --extra dev
uv run --project <repo> --extra dev pytest tests/cli tests/docx
```

`uv.lock` menyimpan resolusi dependensi. Jangan mengedit lock secara manual.
Setelah mengubah `pyproject.toml`, jalankan `uv lock`.

## Pemakaian dari luar repo

Tes CLI menjalankan entry point dari repo dan dari subprocess:

```bash
uv run --project <repo> autooffice check /tmp/proyek/document.md
```

`tests/cli/test_cli_lazy.py` memastikan:

- `autooffice --version` tersedia lewat `python -m autooffice` dan subprocess;
- modul entry point tidak menjalankan CLI saat diimpor;
- working directory tes tidak mengubah state build pengguna.

Tes ini tidak membangun DOCX atau PDF. Smoke Word/PowerPoint nyata hanya
dijalankan pada gate final di Windows.

## Distribusi

Jalur rilis yang diuji adalah repo-local. Wheel standalone belum menjadi jalur
distribusi resmi. Bila wheel diperlukan nanti, package data dan entry point
sudah dideklarasikan, tetapi validasi wheel harus ditambahkan lebih dulu.

Jangan mengandalkan `pip install -e .` global untuk dokumentasi pengguna.
Perintah resmi selalu memakai `uv run --project <repo> autooffice`.

## Menjalankan tes

```bash
uv run --project <repo> --extra dev pytest tests/cli tests/docx
uv run --project <repo> --extra dev pytest -m "not integration and not packaging and not word and not windows and not slow"
uv run --project <repo> --extra dev pytest
```

Di Linux, tes Word dan Windows dilewati. Smoke PDF nyata hanya berjalan di
Windows dengan Word. Lihat [testing.md](testing.md).
