# Packaging

`docgen` dipakai sebagai project `uv` repo-local. Entry point tidak perlu
dipasang global. Perintah dari direktori mana pun:

```bash
uv run --project <repo> docgen --version
uv run --project <repo> docgen check document.md
```

`uv` membaca `pyproject.toml` dan `uv.lock`, lalu menjalankan perintah di
environment proyek.

## Metadata paket

`pyproject.toml` menetapkan:

| Bagian | Nilai |
| --- | --- |
| Nama | `docgen` |
| Versi | `0.1.0` |
| Python | `>=3.15` |
| Build backend | `setuptools.build_meta` |
| Entry point | `docgen = "docgen.cli:main"` |
| Package discovery | `src/docgen` |
| Package data | `docgen = ["data/**/*"]` |

## Dependensi

| Jenis | Paket | Alasan |
| --- | --- | --- |
| Runtime | `lxml`, `ruamel.yaml` | Dipakai pipeline saat `docgen` dijalankan. |
| Dev | `pytest`, `pypdf`, `python-docx`, `mypy`, `ruff` | Tes dan tooling pengembangan. |

`python-docx` hanya dependensi dev karena `src/docgen` tidak mengimpornya.
Paket itu dipakai tes untuk membuat fixture DOCX dan memeriksa hasil build.
`pypdf` juga hanya untuk tes PDF. `Pillow` tidak dipakai; fixture PNG dibuat
tanpa Pillow, jadi paket itu tidak ada di manifest maupun lock.

`src/docgen/data/` wajib ikut sebagai package data karena berisi format,
struktur, template, glosarium, logo, CSL, dan `reference.docx`. Data dibaca
lewat `src/docgen/paths.py`; tidak ada fallback ke direktori kerja.

## Environment pengembangan

```bash
uv sync --extra dev
uv run --extra dev pytest tests/unit
```

Dari luar repo, tambahkan `--project <repo>`:

```bash
uv sync --project <repo> --extra dev
uv run --project <repo> --extra dev pytest tests/unit
```

`uv.lock` menyimpan resolusi dependensi. Jangan mengedit lock secara manual.
Setelah mengubah `pyproject.toml`, jalankan `uv lock`.

## Pemakaian dari luar repo

Tes packaging menjalankan `docgen` dari direktori sementara di luar repo:

```bash
uv run --project <repo> docgen check /tmp/proyek/document.md
```

Tes `tests/packaging/test_repo_local.py` memastikan:

- `docgen --version` tersedia dari luar repo;
- `check` menerima dokumen minimal;
- perintah tidak mengubah `git status` repo;
- working directory tes berada di luar repo.

Tes ini tidak membangun DOCX atau PDF.

## Distribusi

Jalur rilis yang diuji adalah repo-local. Wheel standalone belum menjadi jalur
distribusi resmi. Bila wheel diperlukan nanti, package data dan entry point
sudah dideklarasikan, tetapi validasi wheel harus ditambahkan lebih dulu.

Jangan mengandalkan `pip install -e .` global untuk dokumentasi pengguna.
Perintah resmi selalu memakai `uv run --project <repo> docgen`.

## Menjalankan tes

```bash
uv run --project <repo> --extra dev pytest tests/unit
uv run --project <repo> --extra dev pytest -m "not integration and not packaging and not e2e and not word and not windows"
uv run --project <repo> --extra dev pytest
```

Di Debian, tes Word dan Windows dilewati. Tes PDF golden hanya berjalan di
Windows dengan Word. Lihat [testing.md](testing.md).
