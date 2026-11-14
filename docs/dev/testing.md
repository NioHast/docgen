# Testing

Untuk kriteria memilih kasus test, batas mocking, dan review test, lihat
[test-quality.md](test-quality.md). Dokumen ini fokus pada cara menjalankan tes
dan invariant golden baseline.

Baseline diambil dari output pipeline DOCX legacy commit `06bda0b` tanpa build
ulang. Tujuannya membekukan perilaku output sebelum refactor, bukan
menggantikan tes domain yang sudah ada.

## Daftar Isi

- [Gerbang check lokal](#gerbang-check-lokal)
- [Golden invariant baseline](#golden-invariant-baseline)
- [Menjalankan tes golden](#menjalankan-tes-golden)
- [Fixture dan fake](#fixture-dan-fake)
- [Verifikasi](#verifikasi)

## Gerbang check lokal

Jalankan gate dari root repo sebelum commit:

```bash
uv run python tools/quality/gate.py
```

`gate.py` menjalankan ruff format, ruff check, mypy, lint-imports, pytest,
lock check (`uv lock --check`), docs checker, test-quality checker,
no-legacy checker, dan Python style checker. Gate berhenti pada kegagalan
pertama, menulis `[gate] GAGAL: <nama>`, dan keluar dengan kode perintah
tersebut. Gate tidak memakai Microsoft Word dan tidak mengubah berkas.

Langkah `lint-imports` memeriksa kontrak import di `[tool.importlinter]` pada
`pyproject.toml`. Untuk membaca temuan test-quality secara manual, jalankan
`uv run python tools/quality/check_tests.py`.

## Golden invariant baseline

### Fixture

| Artefak | Path | Status |
|---|---|---|
| DOCX baseline | `tests/fixtures/golden/laporan-baseline.docx` | disimpan di repo |
| PDF baseline | `tests/fixtures/golden/laporan-baseline.pdf` | **tidak disimpan** (456 KiB) |
| Invariant PDF | `tests/fixtures/golden/pdf-baseline.json` | disimpan di repo |
| Golden part DOCX minimal | `tests/fixtures/golden/docx/minimal/baseline.json` | disimpan di repo |

`laporan-baseline.docx` adalah salinan `Laporan.docx` baseline. Metadata
pribadi di `docProps/core.xml` sudah diganti placeholder:

- `dc:title` = `Laporan Baseline`
- `dc:creator` = `docgen-golden` (nilai metadata fixture historis, tidak diubah)
- `cp:lastModifiedBy` = `docgen-golden` (nilai metadata fixture historis, tidak diubah)

`Laporan.docx` asli sudah tidak ada di root repo. Fixture DOCX berukuran
88.020 byte dengan SHA-256
`f0d96979ea43a6a7d5c9f7ea8e69a18e667209c1e3cc7d1cfb19db9b9e5049f0`.

PDF baseline hanya dicatat invariant-nya. Untuk perbandingan PDF lokal di
Windows, salin `Laporan.pdf` ke `tests/fixtures/golden/laporan-baseline.pdf`;
jangan commit file tersebut.

### Invariant DOCX

- Tepat **1 field TOC** dengan instruksi `TOC \o "1-3" \h \z \u`.
- Tepat **1 `w:sdt`** dengan gallery `Table of Contents`.
- TOC berisi 44 entri; style `TOC1`, `TOC2`, dan `TOC3` tersedia sebagai
  paragraph style.
- Entri `2.6.1` memiliki tab leader titik, field `PAGEREF`, dan nomor halaman
  **9**. Entri `3.2.3` memiliki tab leader titik, field `PAGEREF`, dan nomor
  halaman **13**.
- Caption tabel baseline:
  - `Tabel 2.1 Pemetaan Sintaks Markdown dalam Pipeline Laporan Akademik`
  - `Tabel 3.1 Skema Parameter Preset Kampus Deklaratif`
  - `Tabel 4.1 Perbandingan Kinerja Pipeline Laporan Generator, LaTeX, dan Microsoft Word`
- Caption gambar baseline: **0** (tidak ada caption `Gambar x.y` pada dokumen
  ini; satu-satunya drawing adalah logo sampul).
- Ada 5 tabel kode. Semuanya **1 baris x 1 kolom**, memakai style `SourceCode`,
  dan memiliki border penuh di sisi atas, kiri, bawah, dan kanan (bukan
  `nil`/`none`).
- Tidak ada placeholder `{{` atau `}}` di part XML/RELS mana pun.

### Invariant PDF

- Jumlah halaman: **26**.
- Ukuran halaman: **595,5 x 842,25 pt** (A4).
- Teks kunci yang harus tetap ada:
  - `OTOMATISASI PEMBUATAN DOKUMEN LAPORAN`
  - `MENGGUNAKAN PANDOC, TYPST, DAN MARKDOWN`
  - `KATA PENGANTAR`, `DAFTAR ISI`
  - `BAB I`, `PENDAHULUAN`, `BAB V`, `PENUTUP`
  - `DAFTAR PUSTAKA`
- TOC PDF berisi 44 entri dengan nomor halaman yang sama seperti DOCX,
  termasuk `2.6.1` halaman 9, `3.2.3` halaman 13, dan `DAFTAR PUSTAKA`
  halaman 22.

## Menjalankan tes golden

Dari root repo:

```bash
uv run --extra dev pytest tests/docx/test_command.py -v
uv run --extra dev pytest tests/docx/test_toc.py tests/docx/test_sections.py tests/docx/test_page_numbers.py -v
```

Perilaku tes:

- `test_command.py` membandingkan part DOCX ternormalisasi dengan
  `tests/fixtures/golden/docx/minimal/baseline.json`. Fixture ini wajib ada.
- `test_toc.py`, `test_sections.py`, dan `test_page_numbers.py` membaca
  `tests/fixtures/golden/laporan-baseline.docx` dan memeriksa invariant field,
  section, serta penomoran halaman.
- `tests/docx/test_pdf.py` menguji stage PDF dan pemetaan error dengan fake COM.
  Perbandingan PDF nyata hanya smoke Windows pada gate final; suite offline
  tidak mengklaim PDF lulus.
- `pytest.ini` mendaftarkan marker `unit`, `integration`, `packaging`,
  `word`, `windows`, dan `slow` dengan `--strict-markers`.

## Fixture dan fake

Fixture dibagi menurut suite dan tetap deterministik serta offline:

| Lokasi | Kegunaan |
| --- | --- |
| `tests/conftest.py` | Konfigurasi pytest bersama. |
| `tests/cli/conftest.py` | Deck contoh, fake Google, dan aset CLI. |
| `tests/_helpers/paths.py` | Path repo yang tidak bergantung cwd. |
| `autooffice.google.fake` | Fake Google Services tanpa transport HTTP. |
| `tests/pdf/` | Fake COM, fake process control, dan snapshot. |

Aturan yang ditegakkan checker dan review:

- tidak ada network, `time.sleep`, atau panggilan COM/Google live di unit test;
- setiap test punya assertion perilaku, bukan `assert True`;
- penulisan berkas hanya di `tmp_path` atau fixture turunannya;
- golden membandingkan part yang sudah dinormalisasi, bukan binary mentah.

## Verifikasi

Jalankan checker kualitas test dan gate lokal:

```bash
uv run python tools/quality/check_tests.py
uv run python tools/quality/gate.py --list
uv run python tools/quality/gate.py --dry-run
```

Detail urutan gate ada di [quality-gates.md](quality-gates.md).
