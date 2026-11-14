# Golden DOCX fixture minimal

Baseline ini membekukan output `autooffice.docx.command.build_docx` untuk
`tests/fixtures/docx/minimal/document.md`. Baseline dipakai oleh
`tests/docx/test_command.py` untuk mendeteksi perubahan part DOCX setelah
kode `docgen` lama dihapus.

## Format baseline

`baseline.json` berisi manifest part hasil normalisasi, bukan DOCX biner.
Untuk setiap part XML/rels, nilainya adalah XML yang sudah di-pretty-print dan
dinormalisasi. Part biner (misalnya gambar) diringkas menjadi ukuran byte dan
SHA-256.

Normalisasi yang diterapkan `normalize.py`:

- `dcterms:created` dan `dcterms:modified` menjadi `<TIMESTAMP>`;
- Id relationship menjadi `rId1`, `rId2`, ... berdasarkan type, target, dan
  target mode;
- referensi `r:id`, `r:embed`, dan `r:link` serta nama part media yang memuat
  Id relationship ikut diperbarui;
- path direktori data paket menjadi `<PACKAGE_DATA>` dengan pemisah `/`;
- XML diserialisasi ulang secara pretty-print;
- part non-XML diringkas menjadi `bytes` dan `sha256`.

Dengan normalisasi ini baseline tidak menyimpan path absolut mesin pembuat,
timestamp build, atau detail ZIP.

## Membangun ulang baseline

Jalankan dari root repo:

```bash
uv run python tests/fixtures/golden/docx/minimal/normalize.py --update
```

Perintah tersebut menyalin fixture ke direktori sementara, memanggil
`build_docx` dengan `terms=False` dan `keep_intermediate=False`, lalu menulis
`baseline.json` baru. Word sengaja dinonaktifkan selama pembuatan baseline agar
hasilnya deterministik dan tidak bergantung pada versi Microsoft Word. Perilaku
Word nyata diuji terpisah dengan fake Word di `tests/docx/test_office.py` dan
`tests/docx/test_pdf.py`; output Word tidak boleh masuk ke golden ini.

## Memeriksa baseline

Bandingkan output saat ini dengan baseline tanpa menulis file:

```bash
uv run python tests/fixtures/golden/docx/minimal/normalize.py
```

Perintah ini mencetak daftar part yang berbeda dan mengembalikan kode keluar
non-nol bila baseline tidak cocok.

Untuk review perubahan:

```bash
git diff -- tests/fixtures/golden/docx/minimal/baseline.json
```

Periksa hanya part yang memang sengaja berubah. Pembaruan golden harus melalui
review integration owner sesuai `docs/contracts/test-quality.md`.

Test yang memakai baseline:

```bash
uv run pytest tests/docx/test_command.py -q
```
