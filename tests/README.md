# Tes (`tests`)

## Tujuan

Folder ini memverifikasi perilaku `autooffice` pada beberapa tingkat: domain,
contract, CLI, Google, PDF, acceptance deck, packaging, performa, properti, dan
visual. Tes menjadi bukti kontrak dan invariant output; fixture golden
membekukan perilaku DOCX. Jalankan pytest dari akar repo dengan
`uv run --project . pytest`.

## Ownership

- [Testing](../docs/dev/testing.md) adalah acuan golden baseline dan cara
  menjalankan tes; [kontrak DOCX](../docs/contracts/docx.md) dan
  [kontrak test quality](../docs/contracts/test-quality.md) adalah acuan
  perilaku.
- `tests/_helpers/`, `tests/conftest.py`, dan fixture bersama dimiliki oleh
  pemilik infrastruktur tes. Tes domain dimiliki pemilik modul yang diuji.
- Perubahan `tests/fixtures/golden/` harus disertai alasan, pembaruan invariant
  JSON/hash, dan review; jangan mengubah baseline agar tes lulus.
- `pytest.ini` adalah sumber marker; jangan menambah marker tanpa
  mendaftarkannya.

## Pembagian folder

| Path | Isi dan kapan dipakai |
| --- | --- |
| `acceptance/` | Build PPTX/PDF demo deck nyata dengan font tertanam; marker `integration` dan `slow`. |
| `cli/` | Parser, target, output, doctor, build Markdown/deck, dan entry point. |
| `contract/` | Bentuk API dan scaffold kontrak. |
| `deck/` | Model, layout, chart, copy, transcript, renderer PPTX, dan Mermaid. |
| `design/` | Token, theme, font, dan kontras. |
| `docx/` | Pipeline DOCX, package, stage, terms, PDF stage, dan golden part. |
| `google/` | Auth, Drive, Sheets, Slides, state, dan fake contract. |
| `packaging/` | Metadata package, entry point `autooffice`, dan package data. |
| `pdf/` | Adapter COM Word/PowerPoint dengan fake COM dan fake process control. |
| `performance/` | Deck besar dengan marker `slow`. |
| `property/` | Property test schema, key, layout, dan chart. |
| `tools/` | Checker quality dan installer font. |
| `visual/` | Smoke render PPTX ke PNG lewat fake COM atau PowerPoint. |
| `fixtures/` | Baseline golden, fixture DOCX, chart, copy, deck, dan reconcile. |
| `_helpers/` | Helper path dan utilitas bersama yang tidak bergantung cwd. |

## Kapan memakai Word

- Suite offline memakai fake COM. Word dan PowerPoint nyata hanya dipakai pada
  smoke manual gate final di Windows.
- Tes yang memang butuh Word wajib memakai marker `word` dan `windows`, serta
  hanya berjalan di Windows dengan Word terpasang.
- Jangan memakai Word untuk tes unit, parsing, XML, atau logika transformasi
  yang bisa diuji tanpa Word. Mock Word bukan bukti untuk perilaku Word.
- PDF fixture tidak disimpan; `tests/docx/test_pdf.py` menguji stage dan
  pemetaan error tanpa membangun PDF nyata.
- Tes PDF di Windows tanpa Word harus gagal dengan pesan jelas bila memanggil
  adapter nyata. Tes Word lain boleh skip hanya karena platform atau perkakas
  tidak tersedia, bukan karena fixture hilang.

## Larangan

- Jangan menulis ke repo dari tes; gunakan `tmp_path` dan salin fixture.
- Jangan mengakses jaringan atau layanan eksternal.
- Jangan menghapus tes atau melemahkan assertion untuk membuat suite lulus.
- Jangan menambah skip karena fixture hilang; perbaiki fixture atau tes.
- Jangan memakai `python-docx` di kode runtime; di tes dan factory tetap boleh.
- Jangan menyimpan PDF besar atau artefak build di `tests/fixtures/`.

## Tautan

- [Testing](../docs/dev/testing.md)
- [Kontrak DOCX](../docs/contracts/docx.md)
- [Kontrak test quality](../docs/contracts/test-quality.md)
- [Rencana refactor](../docs/dev/archive/refactor-plan.md)
- [Marker pytest](../pytest.ini)
- [README fixture reconcile](fixtures/reconcile/README.md)
