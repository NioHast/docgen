# 06 - Resep Perubahan

Halaman ini mengubah pengetahuan sebelumnya menjadi prosedur kerja. Setelah
membacanya, pembaca bisa memilih lapisan yang tepat, membuat perubahan kecil,
menambahkan tes, dan memverifikasi tanpa melanggar kontrak.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. memilih berkas yang tepat untuk perubahan konten, format, struktur, DOCX,
   atau dokumentasi;
2. mengikuti urutan kerja yang menghasilkan diff kecil dan dapat diuji;
3. menjalankan perintah verifikasi yang relevan;
4. menghindari fallback, workaround, dan perubahan baseline yang tidak
   beralasan;
5. menyiapkan perubahan untuk review.

## Prasyarat

- [00 - Mulai di Sini](00-start-here.md) sampai
  [05 - Tes dan Debugging](05-testing-and-debugging.md).
- Bisa menjalankan `uv run docgen` dan `uv run --extra dev pytest`.
- Memahami bahwa `document.md` adalah satu sumber dan DOCX adalah artefak.

## Daftar isi

- [Pola kerja umum](#pola-kerja-umum)
- [Aturan yang tidak boleh dilanggar](#aturan-yang-tidak-boleh-dilanggar)
- [Resep 1: mengubah konten atau metadata](#resep-1-mengubah-konten-atau-metadata)
- [Resep 2: mengubah format atau struktur](#resep-2-mengubah-format-atau-struktur)
- [Resep 3: mengubah helper DOCX atau stage](#resep-3-mengubah-helper-docx-atau-stage)
- [Resep 4: menambah atau mengubah field](#resep-4-menambah-atau-mengubah-field)
- [Resep 5: mengubah fitur istilah](#resep-5-mengubah-fitur-istilah)
- [Resep 6: mengubah dokumentasi](#resep-6-mengubah-dokumentasi)
- [Menghubungkan perubahan dengan Adeu](#menghubungkan-perubahan-dengan-adeu)
- [Peta gejala ke pemilik](#peta-gejala-ke-pemilik)
- [Checklist sebelum selesai](#checklist-sebelum-selesai)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## Pola kerja umum

Untuk setiap perubahan:

1. tulis satu kalimat perilaku yang ingin dicapai;
2. tentukan lapisan pemilik nilai tersebut;
3. cari sumber kebenaran dan kontraknya;
4. buat perubahan sekecil mungkin;
5. tambahkan atau perbarui tes di tingkat yang tepat;
6. jalankan tes targeted;
7. perbarui dokumentasi jika perilaku terlihat pengguna atau kontributor;
8. jalankan `uv run python tools/dev/check_docs.py` bila dokumentasi berubah;
9. periksa `git diff` sebelum menyerahkan perubahan.

Jangan memulai dari DOCX hasil build. Mulai dari sumber dan kontrak.

## Aturan yang tidak boleh dilanggar

- Satu concern, satu sumber kebenaran.
- Skema `format.yml`, `structure.yml`, dan front matter bersifat tertutup.
  Key baru harus punya konsumen nyata dan tes.
- Stage tidak memanggil `DocumentPackage.load` atau `save` untuk package
  target.
- Stage hanya memutasi part yang dideklarasikan.
- Tidak ada fallback diam-diam atau nilai default untuk input wajib.
- Tidak ada monkey patch, workaround, atau dead code.
- Jangan melemahkan tes atau mengubah golden hanya agar lulus.
- Jangan commit artefak build, PDF besar, atau file sementara.

## Resep 1: mengubah konten atau metadata

Contoh perubahan: mengganti judul, `report_name`, menambah paragraf, atau
menambah sitasi.

Berkas yang disentuh:

- `document.md` di proyek pengguna atau contoh;
- `references.bib` jika menambah sitasi;
- `gambar/` jika menambah gambar;
- `istilah.tsv` jika menambah glosarium pengguna.

Langkah:

1. ubah front matter atau body di `document.md`;
2. pastikan Heading 1 tetap cocok dengan `structure.body`;
3. jalankan check:

```bash
uv run docgen check examples/assignment-single/document.md
```

4. build DOCX:

```bash
uv run docgen build examples/assignment-single/document.md --target docx
```

Cara memeriksa:

- `check` harus `[OK]`;
- DOCX muncul di `examples/assignment-single/out/<report_name>.docx`;
- jika `report_name` berubah, nama DOCX ikut berubah;
- manifest baru berada di `.laporan/manifest.json`;
- tidak ada perubahan pada `format.yml` atau `structure.yml`.

Jika perubahan menambah bab, ubah juga `body` di
`src/docgen/data/structures/<id>/structure.yml`. Jangan hanya menambah
Heading 1 di `document.md`; `check` akan menolak dengan `CFG-BODY-ORDER`.

## Resep 2: mengubah format atau struktur

Contoh perubahan: margin, font, ukuran caption, urutan front matter, atau
penomoran.

Berkas yang disentuh:

- `src/docgen/data/formats/<id>/format.yml` untuk nilai visual;
- `src/docgen/data/structures/<id>/structure.yml` untuk urutan, TOC, daftar,
  dan penomoran;
- aset format seperti `reference.docx`, `logo.jpg`, atau `citation.csl` bila
  path berubah.

Langkah:

1. baca kontrak [config.md](../contracts/config.md);
2. ubah hanya key yang sudah ada di skema;
3. jalankan check pada ketiga contoh:

```bash
uv run docgen check examples/assignment-single/document.md
uv run docgen check examples/proposal-single/document.md
uv run docgen check examples/thesis-single/document.md
```

4. build satu contoh untuk melihat hasil:

```bash
uv run docgen build examples/thesis-single/document.md --target docx
```

Cara memeriksa:

- check tidak menghasilkan `CFG-UNKNOWN-KEY`;
- nilai baru terlihat di DOCX, misalnya margin atau caption;
- TOC dan daftar konsisten dengan `structure.toc` dan `structure.lists`;
- tidak ada key yang hanya disimpan tetapi tidak dibaca kode;
- jika mengubah perilaku output, jalankan tes konfigurasi dan golden terkait.

Jangan menambah key `toc` di front matter dokumen. TOC milik `structure.yml`.
Jangan menambah margin ke `document.md`. Margin milik `format.yml`.

## Resep 3: mengubah helper DOCX atau stage

Contoh perubahan: memperbaiki helper paragraf, menambah dukungan field, atau
mengubah stage caption.

Langkah:

1. tentukan modul pemilik. Untuk helper kanonis, lihat
   [04 - Model DOCX](04-docx-model.md);
2. baca kontrak [docx-api.md](../contracts/docx-api.md) dan
   [stage-api.md](../contracts/stage-api.md);
3. ubah satu modul, bukan menyalin helper ke stage;
4. tambahkan tes unit di file yang sesuai;
5. jalankan tes targeted:

```bash
uv run --extra dev pytest tests/unit/test_docx_paragraphs.py -q
uv run --extra dev pytest tests/unit/test_pipeline.py -q
```

6. jika output DOCX berubah, jalankan tes integration terkait:

```bash
uv run --extra dev pytest tests/integration/test_golden_docx.py -q
uv run --extra dev pytest tests/integration/test_pipeline_python.py -q
```

Cara memeriksa:

- tes unit lulus;
- tes integration lulus atau dijelaskan alasannya;
- part non-target tetap byte-identik;
- `document.xml` tetap semantic-equal bila perubahan tidak dimaksudkan
  mengubah output;
- tidak ada helper kedua dengan nama berbeda.

Untuk stage baru, perubahan lebih besar: tambahkan `StageName`, urutan di
`CANONICAL_ORDER` dan `_RAW_STAGE_SPECS`, kelas `BaseStage`, pendaftaran di
`stages/__init__.py`, guard, kontrak, dan tes. Jangan menambah stage untuk
kebutuhan yang bisa diselesaikan di stage yang sudah ada.

## Resep 4: menambah atau mengubah field

Contoh perubahan: field baru, posisi TOC, atau hasil `SEQ`.

Langkah:

1. gunakan `insert_field` dengan `FieldPosition`; jangan menulis XML field
   manual di stage;
2. untuk TOC, gunakan `insert_toc` dan opsi `before`/`keep_existing` yang
   sudah ada;
3. untuk `SEQ`, gunakan `insert_seq` atau helper caption;
4. tambahkan tes di `tests/unit/test_toc.py`, `test_page_numbers.py`, atau
   `test_stages_captions.py` sesuai pemilik;
5. jika menyentuh Word, tambahkan tes dengan marker `word` dan `windows`.

Contoh pemakaian:

```python
from docgen.docx.fields import FieldPosition, insert_field

field = insert_field(
    ["PAGE"],
    FieldPosition(paragraph=paragraph),
    "1",
)
```

Cara memeriksa:

- instruksi field benar dan lengkap;
- tidak ada `w:dirty` palsu;
- hasil cache awal tidak diklaim sebagai hasil final Word;
- field TOC tetap berada di dalam `w:sdt`;
- tes field lama tidak berubah tanpa alasan.

Jangan menambah parser field kedua. `fields.py` adalah satu-satunya parser
`w:fldChar`/`w:fldSimple`.

## Resep 5: mengubah fitur istilah

Contoh perubahan: menambah istilah, mengubah marker, atau memperbaiki review.

Berkas yang disentuh:

- `src/docgen/data/glossary/istilah.tsv` untuk glosarium paket;
- `istilah.tsv` di samping `document.md` untuk override pengguna;
- `src/docgen/docx/terms/` untuk logika;
- `src/docgen/stages/terms.py` untuk stage;
- `document.md` untuk marker `{{?…?}}`.

Langkah:

1. pastikan header TSV tepat `term<TAB>italic`;
2. nilai `italic` hanya `yes` atau `no`;
3. tambahkan marker di Markdown bila istilah belum diputuskan;
4. jalankan build dengan `--terms`:

```bash
uv run docgen build examples/thesis-single/document.md --target docx --terms
```

5. periksa `.laporan/istilah-baru.txt`;
6. audit DOCX bila perlu:

```bash
uv run python tools/dev/audit_terms.py --docx examples/thesis-single/out/Tugas.docx --out .laporan/istilah-audit.md
```

Cara memeriksa:

- review file berisi satu istilah per baris dan deterministik;
- tidak ada `TERMS-VERIFY`;
- istilah `italic: yes` memakai style `IstilahAsing`;
- istilah `italic: no` tidak miring;
- marker tidak tersisa di DOCX.

Jangan memproses istilah tanpa `--terms`. Tanpa flag itu, tidak ada review
file dan tidak ada verifikasi.

## Resep 6: mengubah dokumentasi

Langkah:

1. tentukan halaman pemilik. Materi belajar ada di `docs/dev/learn/`, kontrak
   di `docs/dev/contracts/`, dan referensi eksternal di
   `docs/dev/references.md`;
2. gunakan tautan relatif yang menunjuk berkas yang ada;
3. untuk teknologi, sebut label registry, bukan URL baru;

```bash
uv run python tools/dev/check_docs.py
```

4. jika menambah halaman lebih dari 150 baris, tambahkan daftar isi dengan
   anchor yang valid;
5. periksa tidak ada em dash atau en dash.

Cara memeriksa:

- `Broken: 0`;
- semua tautan relatif dapat dibuka;
- label registry yang disebut benar-benar ada di `references.md`;
- halaman baru terhubung dari indeks yang relevan;
- tidak ada klaim API yang tidak ada di kode.

### Menghubungkan perubahan dengan Adeu

Adeu adalah server MCP (Model Context Protocol) eksternal yang menghubungkan
DOCX dengan LLM. Repo ini tidak mengimplementasikan server MCP; repo ini
menghasilkan bookmark `pNNNN` dan
manifest `.laporan/manifest.json` saat build. Setelah DOCX diedit lewat Adeu
atau agent, jalankan:

```bash
uv run docgen reconcile document.md
```

`docgen reconcile` membandingkan DOCX hasil edit dengan manifest, menulis
laporan `.laporan/reconcile.md`, dan tidak mengubah DOCX atau `document.md`.
Setujui perubahan di laporan, terapkan manual ke `document.md`, lalu build
ulang. Alur lengkap ada di [Integrasi Adeu](../adeu-integration.md). Label
registry resminya `Adeu GitHub`, `Adeu PyPI`, `Adeu MCP server npm`,
`Adeu MCP tools`, dan `Adeu`; URL resminya ada di
[registry referensi](../references.md).

## Peta gejala ke pemilik

| Gejala | Mulai dari |
| --- | --- |
| Nama output salah atau tidak muncul | `metadata.report_name`, `paths.output_directory` |
| Front matter ditolak | `document.py`, `metadata.py`, `config/` |
| Margin atau font salah | `data/formats/<id>/format.yml`, `docx/styles.py` |
| Urutan bab salah | `data/structures/<id>/structure.yml`, `document.py` |
| Caption tabel/gambar gagal | `stages/validate.py`, `stages/captions.py` |
| TOC kosong | `stages/toc.py`, finalisasi Word, `structure.toc` |
| Nomor halaman salah | `stages/page_numbers.py`, `docx/sections.py` |
| Lebar konten error | `docx/page.py` (`content_width`) |
| Field rusak | `docx/fields.py` |
| Istilah tidak miring | `docx/terms/`, `stages/terms.py`, `istilah.tsv` |
| Manifest atau reconcile gagal | `adeu/`, `paths.output_directory` |

## Checklist sebelum selesai

- [ ] Perubahan hanya menyentuh area yang menjadi tanggung jawab.
- [ ] Tidak ada nilai default baru untuk input wajib.
- [ ] Tidak ada fallback atau pencarian lokasi cadangan.
- [ ] Tes targeted lulus.
- [ ] Tes integration terkait lulus atau dijelaskan alasannya.
- [ ] Golden tidak diubah tanpa alasan dan pembaruan invariant.
- [ ] Dokumentasi dan tautan diperbarui.
- [ ] `uv run python tools/dev/check_docs.py` menghasilkan `Broken: 0`.
- [ ] Tidak ada em dash atau en dash.
- [ ] `git diff` diperiksa dan tidak memuat artefak build.

## Latihan

### 1. Ganti report_name dan verifikasi nama output

Salin `examples/assignment-single` ke direktori sementara, ubah
`report_name` menjadi `"Latihan"`, lalu jalankan:

```bash
uv run docgen check <path-salinan>/document.md
uv run docgen build <path-salinan>/document.md --target docx
```

Cara memeriksa: `check` lulus, DOCX muncul sebagai `out/Latihan.docx`, dan
manifest berada di `.laporan/manifest.json`. Tidak boleh ada default
`Tugas.docx`.

### 2. Tambah istilah pengguna di salinan

Pada salinan yang sama, buat `istilah.tsv` dengan header `term<TAB>italic` dan
satu entri `pipeline` pada kolom `term` serta `yes` pada kolom `italic`.
Pemisah kolom adalah tab asli, bukan teks `\t`. Tambahkan marker
`{{?pipeline?}}` di body, lalu jalankan:

```bash
uv run docgen build <path-salinan>/document.md --target docx --terms
```

Cara memeriksa: build berhasil, `.laporan/istilah-baru.txt` memuat
`pipeline`, dan DOCX menggunakan style istilah. Jika marker masih tersisa
atau verifikasi gagal, baca pesan `TERMS-VERIFY`.

### 3. Jalankan pemeriksa dokumentasi

Jalankan:

```bash
uv run python tools/dev/check_docs.py
```

Cara memeriksa: output memuat `Broken: 0`. Jika ada tautan rusak, perbaiki
path relatif, bukan menghapus tautan tanpa alasan.

## Halaman berikutnya

Kembali ke [indeks materi belajar](README.md) atau lanjut ke
[panduan kontribusi](../contributing.md) untuk alur review dan aturan
perubahan kontrak.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Kontribusi dan checklist | [contributing.md](../contributing.md) |
| Arsitektur | [architecture.md](../architecture.md) |
| Kontrak konfigurasi | [contracts/config.md](../contracts/config.md) |
| Kontrak DOCX | [contracts/docx-api.md](../contracts/docx-api.md) |
| Kontrak stage | [contracts/stage-api.md](../contracts/stage-api.md) |
| Testing | [testing.md](../testing.md) |
| Format dan struktur | [formats.md](../formats.md) |
| Istilah dan glosarium | [docx/terms.md](../docx/terms.md) |
| Registry referensi | [references.md](../references.md) |
| Indeks materi belajar | [README.md](README.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `Ruff configuration`, `Ruff rules`,
`Ruff formatter`, `mypy configuration`, `pytest documentation`,
`uv documentation`, `Adeu GitHub`, `Adeu PyPI`, `Adeu MCP server npm`,
`Adeu MCP tools`, dan `Adeu`. URL resminya ada di
[registry referensi](../references.md).
