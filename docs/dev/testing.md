# Testing

Untuk kriteria memilih kasus test, batas mocking, dan review test, lihat
[test-quality.md](test-quality.md). Dokumen ini fokus pada cara menjalankan tes
dan invariant golden baseline.

Dokumen ini mencatat invariant golden baseline P0.1. Baseline diambil dari
output lama commit `06bda0b` tanpa build ulang. Tujuannya membekukan perilaku
output sebelum refactor, bukan menggantikan tes domain yang sudah ada.

## Daftar Isi

- [Gerbang check lokal](#gerbang-check-lokal)
- [Golden invariant P0.1](#golden-invariant-p01)
- [Menjalankan tes golden](#menjalankan-tes-golden)
- [AutoOffice testing](#autooffice-testing)
- [Hasil verifikasi akhir](#hasil-verifikasi-akhir)
- [Hasil verifikasi P0.1](#hasil-verifikasi-p01)

## Gerbang check lokal

Jalankan gate dari root repo sebelum commit:

```bash
uv run python tools/quality/gate.py
```

`gate.py` menjalankan ruff format, ruff check, mypy, lint-imports, pytest,
lock check (`uv lock --check`), docs checker, test-quality checker, dan
no-legacy list. Gate berhenti pada kegagalan pertama, menulis
`[gate] GAGAL: <nama>`, dan keluar dengan kode perintah tersebut. Gate tidak
memakai Microsoft Word dan tidak mengubah berkas.

Langkah `lint-imports` memeriksa kontrak import di `[tool.importlinter]` pada
`pyproject.toml`. Untuk membaca temuan test-quality secara manual, jalankan
`uv run python tools/quality/check_tests.py`.

## Golden invariant P0.1

### Fixture

| Artefak | Path | Status |
|---|---|---|
| DOCX baseline | `tests/fixtures/golden/laporan-baseline.docx` | disimpan di repo |
| PDF baseline | `tests/fixtures/golden/laporan-baseline.pdf` | **tidak disimpan** (456 KiB) |
| Invariant PDF | `tests/fixtures/golden/pdf-baseline.json` | disimpan di repo |

`laporan-baseline.docx` adalah salinan `Laporan.docx` baseline. Metadata
pribadi di `docProps/core.xml` sudah diganti placeholder:

- `dc:title` = `Laporan Baseline`
- `dc:creator` = `docgen-golden` (metadata fixture historis, tidak diubah)
- `cp:lastModifiedBy` = `docgen-golden` (metadata fixture historis, tidak diubah)

`Laporan.docx` asli sudah tidak ada di root repo. Fixture DOCX berukuran
88.020 byte dengan SHA-256
`f0d96979ea43a6a7d5c9f7ea8e69a18e667209c1e3cc7d1cfb19db9b9e5049f0`.

PDF baseline hanya dicatat invariant-nya. Untuk menjalankan perbandingan PDF
secara lokal di Windows, salin `Laporan.pdf` ke
`tests/fixtures/golden/laporan-baseline.pdf`; jangan commit file tersebut.

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

Dari root repo, memakai venv lokal Windows:

```bash
.venv/Scripts/python.exe -m pytest tests/integration/test_golden_docx.py -v
.venv/Scripts/python.exe -m pytest -m windows tests/integration/test_golden_pdf.py -v
```

Perilaku tes:

- `test_golden_docx.py` **gagal** jika fixture DOCX tidak ada. Fixture ini
  wajib ada di repo.
- `test_golden_pdf.py` memakai marker `windows` dan
  `pytest.mark.skipif(sys.platform != "win32", reason="Word-only")`. Di
  Linux/Debian seluruh modul di-skip.
- Di Windows, tes kontrak `pdf-baseline.json` tetap berjalan. Tes perbandingan
  PDF **skip eksplisit** jika `laporan-baseline.pdf` tidak ada, sehingga tidak
  menjadi false-green.
- `pytest.ini` mendaftarkan marker `unit`, `integration`, `packaging`, `e2e`,
  `word`, dan `windows` dengan `--strict-markers`.

## AutoOffice testing

Test AutoOffice memakai fixture bersama di `tests/autooffice/conftest.py`.
Fixture tersebut deterministik dan offline:

| Fixture | Kegunaan |
| --- | --- |
| `temp_workspace` | Direktori `input`, `output`, dan `cache` di bawah `tmp_path`. |
| `fake_clock` | Waktu tetap 2026-01-01T00:00:00Z; hanya berubah lewat `advance`. |
| `fake_com` | Urutan respons COM palsu yang mencatat setiap panggilan. |
| `fake_google` | Skeleton respons Slides/Sheets per method tanpa transport HTTP. |
| `golden_normalizer` | Normalisasi teks, XML, timestamp, UUID, dan part ZIP. |

Aturan yang ditegakkan checker dan review:

- tidak ada network, `time.sleep`, atau panggilan COM/Google live di unit test;
- setiap test punya assertion perilaku, bukan `assert True`;
- penulisan berkas hanya di `tmp_path` atau fixture turunannya;
- golden membandingkan part yang sudah dinormalisasi, bukan binary mentah.

Jalankan checker kualitas test dan gate lokal:

```bash
uv run python tools/quality/check_tests.py
uv run python tools/quality/gate.py --list
uv run python tools/quality/gate.py --dry-run
```

Detail urutan gate ada di [quality-gates.md](quality-gates.md).

## Hasil verifikasi akhir

Diverifikasi ulang pada 2026-11-10 setelah seluruh stage Python aktif:

- Suite penuh: **508 passed, 2 subtests**.
- Build contoh thesis (`examples/thesis-single`, target `both`) menghasilkan
  `out/<report_name>.docx` dan `out/<report_name>.pdf`; contoh memakai
  `report_name: "Tugas"`.
- Tes golden DOCX (`tests/integration/test_golden_docx.py`) lulus.

Angka suite penuh berlaku untuk keadaan tes saat ini; perbarui bila menambah
tes atau mengubah fixture golden.

## Hasil verifikasi P0.1

Diverifikasi pada 2026-11-09:

- `test_golden_docx.py`: **8 passed**.
- `test_golden_pdf.py`: **1 passed, 1 skipped** (kontrak baseline JSON lulus;
  perbandingan PDF skip karena fixture PDF tidak ada).
- Verifikasi tambahan dengan menyalin sementara `Laporan.pdf` ke path fixture:
  **2 passed**; fixture PDF dihapus kembali setelah tes.
