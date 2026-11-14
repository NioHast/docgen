# 05 - Tes dan Debugging

Halaman ini menghubungkan jenis tes di repo dengan cara menelusuri error.
Setelah membacanya, pembaca bisa memilih tes paling kecil yang relevan,
membaca kegagalan, dan memakai `--keep-intermediate` atau fixture tanpa menebak.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. membedakan tes domain, integration, e2e, dan packaging;
2. memilih perintah pytest yang sesuai dengan perubahan;
3. membaca kegagalan `DocgenError` dan `StageError`;
4. men-debug build DOCX memakai `check`, `--keep-intermediate`, manifest, dan fixture;
5. menjaga tes golden agar tidak berubah hanya untuk membuat suite lulus.

## Prasyarat

- [02 - Build Pertama](02-first-build.md) sampai
  [04 - Model DOCX](04-docx-model.md).
- Mengenal pytest dasar: file tes, fungsi `test_*`, fixture, dan marker.
- Pandoc atau Word hanya diperlukan untuk tes yang memang memakainya.

## Daftar isi

- [Prinsip verifikasi](#prinsip-verifikasi)
- [Tingkat tes di repo](#tingkat-tes-di-repo)
- [Perintah pytest](#perintah-pytest)
- [Membaca kegagalan](#membaca-kegagalan)
- [Debug build DOCX](#debug-build-docx)
- [Tes golden](#tes-golden)
- [Debug fitur istilah](#debug-fitur-istilah)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## Prinsip verifikasi

Urutan verifikasi yang disarankan:

1. jalankan `autooffice check` untuk input dan konfigurasi;
2. jalankan tes domain untuk modul yang berubah;
3. jalankan tes integration yang menyentuh pipeline atau tool nyata;
4. jalankan e2e atau packaging hanya jika perubahan menyentuh CLI, path, atau
   packaging;
5. jalankan suite penuh sebelum menyatakan selesai.

Tes harus menunjukkan perilaku yang berubah, bukan sekadar menambah cakupan.
Jangan menghapus assertion, melemahkan tes, atau memperbarui golden hanya agar
tes berhenti gagal.

## Tingkat tes di repo

| Tingkat | Lokasi | Ciri | Tool eksternal |
| --- | --- | --- | --- |
| Domain | `tests/docx/`, `tests/deck/`, `tests/design/` | Cepat, memakai objek di memori dan fixture kecil. | Tidak menyentuh Word, Pandoc, atau `mmdc`. |
| Integration | `tests/integration/` | Menyentuh pipeline, Pandoc, golden DOCX, atau Word. | Tergantung tes. |
| E2E | `tests/e2e/` | Menjalankan CLI dari luar modul pada contoh yang disalin. | Pandoc, `mmdc`, dan Word bila tersedia. |
| Packaging | `tests/packaging/` | Memeriksa entry point dan perilaku repo-local. | `uv`, build package. |

Marker di `pytest.ini`:

- `unit`: tes cepat tanpa Word/Pandoc/mmdc;
- `integration`: membutuhkan Pandoc, Word, atau artefak build;
- `packaging`: packaging repo-local atau wheel;
- `e2e`: end-to-end dari luar repo;
- `word`: membutuhkan Microsoft Word;
- `windows`: hanya Windows.

## Perintah pytest

Selalu jalankan dari akar repo dan sertakan `--extra dev` agar pytest tersedia:

```bash
uv run --extra dev pytest tests/docx -q
```

Tes domain tertentu:

```bash
uv run --extra dev pytest tests/docx/test_docx_page.py -q
uv run --extra dev pytest tests/docx/test_pipeline.py -q
```

Filter nama tes:

```bash
uv run --extra dev pytest -k report_name -q
```

Subset cepat tanpa integration, packaging, e2e, Word, dan Windows:

```bash
uv run --extra dev pytest -m "not integration and not packaging and not e2e and not word and not windows" -q
```

Tes Word/Windows:

```bash
uv run --extra dev pytest -m windows tests/integration/test_golden_pdf.py -q
uv run --extra dev pytest -m word tests/integration/test_lists_word.py -q
```

Suite penuh:

```bash
uv run --extra dev pytest
```

Di Linux, tes Word dan Windows akan di-skip. Jangan mengklaim PDF lulus jika
Word tidak tersedia. Untuk perubahan kecil, mulai dari file tes yang paling
dekat, lalu naik ke integration jika perlu.

## Membaca kegagalan

Urutan membaca output pytest:

1. nama tes dan baris assertion yang gagal;
2. tipe exception dan pesan;
3. kode error di dalam tanda kurung, misalnya `CFG-REQUIRED` atau
   `PAGE-WIDTH`;
4. path dan key yang disebut;
5. stage pembungkus jika error berasal dari pipeline.

Contoh format error dari CLI:

```text
[ERROR] C:\path\document.md: kunci 'report_name': kunci 'report_name' wajib diisi (CFG-REQUIRED)
```

Contoh error stage:

```text
[ERROR] [validate] C:\path\document.md: caption Markdown tidak valid (VAL-CAPTION)
```

Jika error dibungkus `StageError`, penyebab asli ada di atribut `cause` pada
kode. Dari CLI, nama stage di awal pesan menunjukkan modul stage yang harus
dibaca.

Hindari diagnosis berbasis tebakan seperti "mungkin Pandoc salah". Baca kode
error, path, dan bagian kontrak yang mengatur input tersebut.

## Debug build DOCX

Alur yang disarankan:

1. jalankan `uv run autooffice check <document.md>`;
2. jika check lulus, build dengan `--target docx --keep-intermediate`;
3. periksa workspace `.laporan-build/`;
4. periksa DOCX dengan `DocumentPackage` atau buka di Word untuk melihat
   field;
5. periksa manifest untuk memastikan bookmark dan teks paragraf.

Contoh:

```bash
uv run autooffice check examples/thesis-single/document.md
uv run autooffice build examples/thesis-single/document.md --target docx --keep-intermediate
```

Isi workspace antara lain:

| Berkas | Arti |
| --- | --- |
| `mermaid.md` | Body setelah blok Mermaid diganti gambar. |
| `front_matter.md` | Markdown final untuk Pandoc. |
| `reference.docx` | Reference turunan dari `format.yml`. |
| `pandoc-metadata.yml` | Metadata yang dikirim ke Pandoc. |
| `<report_name>.docx` | DOCX antara hasil Pandoc. |

Jika build gagal sebelum save, workspace dengan `--keep-intermediate` membantu melihat
tahap terakhir yang berhasil. Tanpa `--keep-intermediate`, workspace dihapus di blok
`finally`.

Untuk memeriksa DOCX hasil build tanpa Word:

```bash
uv run python -c "from autooffice.docx.package import DocumentPackage; p = DocumentPackage.load('examples/thesis-single/out/Tugas.docx'); print(len(p.part_names())); print(p.has_part('word/document.xml'))"
```

Ganti path jika `report_name` berbeda. Jika file tidak ada, periksa output
build dan path output sebelum menyalahkan parser.

Untuk melihat edit manual pada DOCX, gunakan modul rekonsiliasi internal
`autooffice.docx.adeu.reconcile`. Modul ini tidak diekspos sebagai subperintah
CLI AutoOffice v1. Modul membaca manifest dan DOCX, lalu menulis laporan tanpa
mengubah DOCX, manifest, atau Markdown. Exit code 3 berarti ada perubahan
manual; exit code 4 berarti ada pelanggaran paragraf terlindungi. Setelah
perubahan disetujui, terapkan ke `document.md` dan build ulang.

## Tes golden

Fixture golden ada di `tests/fixtures/golden/`:

- `laporan-baseline.docx` untuk invariant DOCX;
- `baseline-4a5b777.json` untuk metadata invariant;
- `pdf-baseline.json` untuk invariant PDF.

`tests/integration/test_golden_docx.py` membekukan struktur output, bukan
membangun ulang DOCX. Tes ini memeriksa field TOC, caption, tabel kode,
style, dan content type tertentu. Fixture DOCX wajib ada.

`tests/integration/test_golden_pdf.py` memakai marker `windows` dan `word`.
Perbandingan PDF memerlukan fixture PDF lokal yang tidak disimpan di repo;
kontrak `pdf-baseline.json` tetap berjalan. Di Linux seluruh modul di-skip.
Jangan menambahkan skip karena fixture hilang. Perbaiki fixture atau tes.

Aturan golden:

- perubahan output yang disengaja harus disertai alasan dan pembaruan
  invariant;
- jangan mengubah baseline agar tes lulus;
- jangan commit PDF besar atau artefak build;
- jalankan tes golden terkait setelah perubahan yang memengaruhi output.

## Debug fitur istilah

Aktifkan `--terms`:

```bash
uv run autooffice build examples/thesis-single/document.md --target docx --terms
```

Yang diperiksa:

- `.laporan/istilah-baru.txt` berisi istilah yang perlu diputuskan;
- build gagal dengan `TERMS-VERIFY` jika ada pelanggaran;
- pesan pelanggaran menyebut istilah dan paragraf;
- tanpa `--terms`, tidak ada review file dan tidak ada verifikasi.

Audit DOCX hasil build:

```bash
uv run python -m tools.dev.audit_terms --docx examples/thesis-single/out/Tugas.docx --out .laporan/istilah-audit.md
```

Alat ini menulis laporan audit dan tidak mengubah DOCX. Jika glosarium
pengguna dipakai, tambahkan `--glossary <path-istilah.tsv>`. Format header
wajib `term<TAB>italic`.

## Latihan

### 1. Jalankan subset domain

Jalankan:

```bash
uv run --extra dev pytest tests/docx/test_docx_page.py tests/docx/test_docx_paragraphs.py -q
```

Cara memeriksa: semua tes lulus dan ringkasan berakhir dengan `passed`.
Jika ada kegagalan, baca nama tes dan assertion sebelum mengubah kode.

### 2. Uji error input pada salinan

Salin `examples/assignment-single` ke direktori sementara, hapus
`report_name`, lalu jalankan:

```bash
uv run autooffice check <path-salinan>/document.md
```

Cara memeriksa: exit code 1 dan pesan memuat `report_name` serta
`CFG-REQUIRED`. Tidak ada output DOCX yang boleh dibuat dari input ini.

### 3. Hitung field TOC pada fixture

Jalankan:

```bash
uv run python -c "from autooffice.docx.package import DocumentPackage; from autooffice.docx.package.fields import FieldKind, iter_fields; p = DocumentPackage.load('tests/fixtures/golden/laporan-baseline.docx'); print(sum(f.kind is FieldKind.TOC for f in iter_fields(p)))"
```

Cara memeriksa: hasilnya `3` pada fixture saat ini. Jika berbeda, periksa
apakah fixture berubah atau apakah parser field kehilangan field.

## Halaman berikutnya

Lanjut ke [06 - Resep Perubahan](06-change-recipes.md) untuk menerapkan
perubahan kecil dengan urutan kerja yang aman.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Testing dan golden baseline | [testing.md](../testing.md) |
| Error dan exit code | [pipeline/errors.md](../pipeline/errors.md) |
| Model pipeline | [pipeline/overview.md](../pipeline/overview.md) |
| Kontrak DOCX | [contracts/docx.md](../../contracts/docx.md) |
| Kontrak CLI | [contracts/cli.md](../../contracts/cli.md) |
| Kontribusi dan perintah tes | [contributing.md](../contributing.md) |
| Adeu dan modul rekonsiliasi internal | [adeu-integration.md](../adeu-integration.md) |
| Indeks tes | [tests/README.md](../../../tests/README.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `pytest documentation`, `pytest
markers`, `pypdf documentation`, `uv documentation`, dan `Ruff rules`. URL
resminya ada di [registry referensi](../references.md).
