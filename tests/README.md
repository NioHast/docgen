# Tes (`tests`)

## Tujuan

Folder ini memverifikasi perilaku `docgen` pada beberapa tingkat: unit,
integrasi, end-to-end, dan packaging. Tes menjadi bukti kontrak dan invariant
output; fixture golden membekukan perilaku DOCX/PDF. Jalankan pytest dari akar
repo dengan `uv run --project . pytest`.

## Ownership

- [Testing](../docs/dev/testing.md) adalah acuan golden baseline dan cara
  menjalankan tes; [kontrak stage](../docs/dev/contracts/stage-api.md) dan
  [kontrak DOCX](../docs/dev/contracts/docx-api.md) adalah acuan perilaku.
- `tests/_helpers/`, `tests/factories/`, `tests/conftest.py`, dan harness
  `tests/integration/` dimiliki pemilik infrastruktur tes. Tes domain dimiliki
  pemilik modul yang diuji.
- Perubahan `tests/fixtures/golden/` harus disertai alasan, pembaruan invariant
  JSON/hash, dan review; jangan mengubah baseline agar tes lulus.
- `pytest.ini` adalah sumber marker; jangan menambah marker tanpa
  mendaftarkannya.

## Pembagian folder

| Path | Isi dan kapan dipakai |
| --- | --- |
| `unit/` | Tes cepat tanpa Word, Pandoc, atau `mmdc`; memakai objek di memori dan fixture kecil. |
| `integration/` | Tes yang membutuhkan Pandoc nyata, golden DOCX, pipeline, atau Word; termasuk `test_pipeline_python.py` dan `test_golden_docx.py`. |
| `e2e/` | Menjalankan CLI `docgen` dari luar modul pada contoh yang disalin ke direktori sementara. |
| `packaging/` | Memeriksa entry point `uv run --project <repo> docgen` dan perilaku repo-local. |
| `fixtures/` | Sumber dan baseline tes: `golden/`, `e2e/`, `paragraph_ids/`, `reconcile/`. Bukan kode produksi; jangan diubah tanpa alasan. |
| `factories/` | Pembuat DOCX minimal berbasis `python-docx` untuk kebutuhan tes. |
| `_helpers/` | Helper path dan utilitas bersama yang tidak bergantung cwd. |

Tes alat pengembang berada di `tests/test_check_docs.py`,
`tests/test_check_prose.py`, dan `tests/test_prose_docx.py`; tes itu mengimpor
modul dari paket `tools.dev`.

## Kapan memakai Word

- Gunakan Word hanya untuk perilaku yang memang dihitung Word: pembaruan field
  TOC/PAGEREF, paginasi, dan ekspor PDF. Tes semacam ini wajib memakai marker
  `word` dan `windows`, serta hanya berjalan di Windows dengan Word terpasang.
- Jangan memakai Word untuk tes unit, parsing, XML, atau logika transformasi
  yang bisa diuji tanpa Word. Mock Word bukan bukti untuk perilaku Word.
- `tests/integration/test_golden_pdf.py` membangun ulang PDF dari
  `examples/thesis-single` dan membandingkannya dengan `pdf-baseline.json`.
  PDF fixture tidak disimpan; tes tidak boleh skip karena fixture hilang.
- Tes PDF di Windows tanpa Word harus gagal dengan pesan jelas. Tes Word lain
  boleh skip hanya karena platform atau perkakas tidak tersedia, bukan karena
  fixture hilang.

## Larangan

- Jangan menulis ke repo dari tes; gunakan `tmp_path` dan salin fixture.
- Jangan mengakses jaringan atau layanan eksternal.
- Jangan menghapus tes atau melemahkan assertion untuk membuat suite lulus.
- Jangan menambah skip karena fixture hilang; perbaiki fixture atau tes.
- Jangan memakai `python-docx` di kode runtime; di tes dan factory tetap boleh.
- Jangan menyimpan PDF besar atau artefak build di `tests/fixtures/`.

## Tautan

- [Testing](../docs/dev/testing.md)
- [Kontrak stage](../docs/dev/contracts/stage-api.md)
- [Kontrak DOCX](../docs/dev/contracts/docx-api.md)
- [Rencana refactor](../docs/dev/archive/refactor-plan.md)
- [Marker pytest](../pytest.ini)
- [README fixture reconcile](fixtures/reconcile/README.md)
