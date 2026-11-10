# 03 - Tahap Pipeline

Halaman ini membahas urutan kerja `Pipeline.run` dan 18 stage kanonik. Setelah
membacanya, pembaca bisa melacak tempat suatu perubahan terjadi, membaca
`StageResult`, dan menelusuri kegagalan stage tanpa menebak.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. menyebutkan 18 stage dan urutannya;
2. membedakan stage yang memutasi workspace, package, dan part DOCX;
3. menjelaskan tahap sebelum save, save tunggal, dan finalisasi setelah save;
4. membaca `StageResult` dan artifact yang dihasilkan;
5. memilih tes atau perintah untuk mendiagnosis stage yang gagal.

## Prasyarat

- [01 - Model Mental](01-mental-model.md).
- [02 - Build Pertama](02-first-build.md).
- Bisa membaca Python sederhana dan decorator/class dasar.
- Tidak perlu Word. Build DOCX tanpa Word cukup untuk sebagian besar latihan.

## Daftar isi

- [Kontrak Pipeline.run](#kontrak-pipelinerun)
- [Tiga tahap eksekusi](#tiga-tahap-eksekusi)
- [Delapan belas stage kanonik](#delapan-belas-stage-kanonik)
- [Guard dan alasan urutan](#guard-dan-alasan-urutan)
- [Satu load dan satu save](#satu-load-dan-satu-save)
- [StageResult dan stage yang dilewati](#stageresult-dan-stage-yang-dilewati)
- [ArtifactStore dan workspace](#artifactstore-dan-workspace)
- [Membaca kegagalan stage](#membaca-kegagalan-stage)
- [Contoh konkret: thesis](#contoh-konkret-thesis)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## Kontrak Pipeline.run

`Pipeline.run(document_path, options)` melakukan:

1. `load_project(document_path)` untuk membaca front matter, format,
   struktur, dan aset;
2. `_resolve_target(options)` untuk memutuskan target efektif dan warning
   platform;
3. membuat `output_dir` dengan `paths.output_directory`;
4. membuat `Workspace` di `.laporan-build/` di samping dokumen;
5. menjalankan stage sebelum `office` pada satu `DocumentPackage`;
6. menyimpan package satu kali;
7. menulis manifest;
8. menjalankan `office` dan `pdf`;
9. membersihkan workspace di blok `finally`, kecuali `--keep`.

Kontrak lengkap ada di [contracts/stage-api.md](../contracts/stage-api.md).

## Tiga tahap eksekusi

| Tahap | Stage | State utama |
| --- | --- | --- |
| Persiapan | `validate` sampai `pandoc` | Workspace, Markdown final, package DOCX baru. |
| Mutasi package | `sections` sampai `lists` | `ctx.package` di memori. |
| Finalisasi | `office`, `pdf` | DOCX di disk, lalu PDF. |

`pandoc` adalah satu-satunya stage yang membuat `ctx.package`. Sebelum
`pandoc`, `ctx.package is None`. Setelah `pandoc`, stage lain hanya memutasi
package yang sama.

## Delapan belas stage kanonik

| Order | Stage | Modul | Memutasi | Tugas utama |
| ---: | --- | --- | --- | --- |
| 10 | `validate` | `stages/validate.py` | - | Caption tabel dan alt text gambar di Markdown. |
| 20 | `mermaid` | `stages/mermaid.py` | workspace | Render blok Mermaid menjadi PNG dan tulis `mermaid.md`. |
| 30 | `style_reference` | `stages/style_reference.py` | workspace, cache | Hasilkan `reference.docx` turunan dari `format.yml`. |
| 35 | `front_matter` | `stages/front_matter.py` | workspace | Sampul, template, abstrak, penomoran heading, Markdown final. |
| 40 | `pandoc` | `stages/pandoc.py` | package | Markdown final menjadi DOCX awal. |
| 50 | `sections` | `stages/sections.py` | `word/document.xml` | Section break, margin, ukuran halaman, nomor heading DOCX. |
| 60 | `code` | `stages/code.py` | `word/document.xml` | Blok kode menjadi tabel 1x1. |
| 70 | `captions` | `stages/captions.py` | `word/document.xml` | Caption tabel/gambar, nomor bab, layout gambar. |
| 80 | `normalize` | `stages/normalize.py` | `word/document.xml` | Spasi 1,5, justify, hapus bold body. |
| 90 | `equations` | `stages/equations.py` | `word/document.xml` | Nomor persamaan `(bab.n)`. |
| 100 | `numbering` | `stages/numbering.py` | `word/document.xml`, `word/numbering.xml` | Indentasi daftar. |
| 110 | `blank_lines` | `stages/blank_lines.py` | `word/document.xml` | Paragraf kosong sesuai aturan layout. |
| 120 | `terms` | `stages/terms.py` | `word/document.xml`, `word/styles.xml` | Style istilah, verifikasi, review file. |
| 130 | `toc` | `stages/toc.py` | `word/document.xml`, `word/styles.xml` | Field TOC native dan style TOC. |
| 140 | `page_numbers` | `stages/page_numbers.py` | document, header/footer, rels, content types | Romawi front matter, Arab body. |
| 150 | `lists` | `stages/lists.py` | `word/document.xml` | Daftar tabel/gambar dan field `SEQ`. |
| 160 | `office` | `stages/office.py` | package | Word memperbarui field dan menyimpan DOCX. |
| 170 | `pdf` | `stages/pdf.py` | - | Word mengekspor PDF. |

Beberapa stage tidak selalu berjalan:

- `terms` hanya aktif dengan `--terms`;
- `toc` dilewati jika `structure.toc` bernilai `false`;
- `lists` dilewati jika tidak ada daftar tabel/gambar di struktur;
- `office` dan `pdf` dapat dilewati atau gagal sesuai target dan ketersediaan
  Word.

## Guard dan alasan urutan

Urutan bukan saran. `validate_stage_order` menolak stage yang hilang,
duplikat, salah urutan, atau memutasi part yang tidak dikenal.

Guard penting:

1. `style_reference` sebelum `front_matter` sebelum `pandoc`;
2. `sections` sebelum `code` sebelum `captions` sebelum `normalize`;
3. `normalize` sebelum `equations` sebelum `blank_lines`;
4. `terms` sebelum `toc` sebelum `page_numbers` sebelum `lists`;
5. `office` sebelum `pdf`.

Alasannya:

- Reference dan front matter harus siap sebelum Pandoc membaca Markdown.
- Section dan nomor bab harus stabil sebelum caption dan tabel kode diolah.
- Tabel kode harus berbentuk tabel 1x1 sebelum captions agar tidak dianggap
  tabel data.
- Italic istilah memengaruhi paginasi, jadi `terms` harus selesai sebelum TOC
  dan nomor halaman.
- TOC dan `PAGEREF` harus ada sebelum format nomor halaman.
- PDF diekspor dari DOCX yang sudah difinalkan Word.

## Satu load dan satu save

Di `pipeline.py`, stage dipisahkan berdasarkan order `office`:

```python
office_order = self._spec_by_name[StageName.OFFICE].order
pre_save = tuple(stage for stage in self.stages if stage.order < office_order)
post_save = tuple(stage for stage in self.stages if stage.order >= office_order)
```

Semua stage `pre_save` berjalan pada package yang sama. Setelah itu:

```python
ctx.package.save(docx_path)
ctx.artifacts.put("docx", docx_path)
```

Baru setelah save, `office` dan `pdf` berjalan. Stage tidak boleh memanggil
`load` atau `save` untuk package target. Pengecualian:

- `style_reference` memuat dan menyimpan `reference.docx` sumber, bukan
  package target;
- `office` memakai Word yang dapat menulis ulang package dari luar.

## StageResult dan stage yang dilewati

Setiap stage mengembalikan `StageResult`:

| Field | Arti |
| --- | --- |
| `stage` | Nama stage, misalnya `captions`. |
| `status` | `ok` atau `skipped`. |
| `changed` | Apakah stage benar-benar mengubah inputnya. |
| `duration_ms` | Durasi dalam milidetik. |
| `metrics` | Angka ringkas, misalnya jumlah field atau byte. |
| `warnings` | Peringatan yang tidak menggagalkan build. |
| `artifacts` | Path yang dihasilkan stage. |

`status="skipped"` bukan error. Contohnya `terms` tanpa `--terms`, `toc` pada
struktur tanpa TOC, dan `office` saat Word tidak tersedia untuk target DOCX.
Pada kasus terakhir, pipeline mencetak peringatan dan TOC yang baru belum
berisi entri sehingga bisa tampil kosong sampai Word memperbarui field.
Warnings dari stage dikumpulkan di `BuildReport` lalu dicetak CLI.

Error tidak dikembalikan sebagai `StageResult`. Error dilempar sebagai
`DocgenError` atau subclass. Exception yang tidak dikenal dibungkus
`StageError` dengan nama stage, path, dan cause.

## ArtifactStore dan workspace

`ArtifactStore` menyimpan path dengan key yang ketat. Key standar:

| Key | Isi |
| --- | --- |
| `markdown` | Markdown final untuk Pandoc dari `front_matter`. |
| `mermaid.markdown` | Markdown mentah hasil render Mermaid. |
| `reference_docx` | `reference.docx` turunan. |
| `pandoc_docx` | DOCX sementara hasil Pandoc. |
| `docx` | DOCX final di path output. |
| `manifest` | Manifest Adeu. |
| `terms_review` | Review istilah. |
| `pdf` | PDF final. |

Key berprefix nama stage juga sah. Key yang sudah ada tidak boleh ditimpa
tanpa deklarasi.

Workspace default adalah `.laporan-build/` di samping `document.md`. Tanpa
`--keep`, workspace dihapus di blok `finally`, termasuk saat build gagal.
Dengan `--keep`, isinya dipertahankan untuk diperiksa, misalnya
`front_matter.md`, `mermaid.md`, `reference.docx`, `pandoc-metadata.yml`, dan
DOCX antara.

## Membaca kegagalan stage

Format error CLI:

```text
[ERROR] <path>: kunci '<key>': <pesan> (<KODE>)
```

Untuk `StageError`, nama stage muncul di depan:

```text
[ERROR] [captions] <path>: <pesan> (<KODE>)
```

Langkah diagnosis:

1. baca nama stage dan kode error;
2. cari modul stage di tabel 18 stage;
3. baca deklarasi `mutates` dan guard-nya;
4. jalankan tes unit stage terkait;
5. jika perlu, build ulang dengan `--keep` dan periksa workspace.

Jangan mengubah urutan stage atau menambahkan fallback sebelum penyebab
ditemukan. `validate_stage_order` sengaja keras agar kesalahan urutan tidak
menghasilkan output yang tampak benar.

## Contoh konkret: thesis

`examples/thesis-single/document.md` memakai struktur `thesis`. Struktur itu
memiliki TOC dan daftar tabel/gambar. Tanpa `--terms`, alur efektifnya:

```text
validate
-> mermaid
-> style_reference
-> front_matter
-> pandoc
-> sections
-> code
-> captions
-> normalize
-> equations
-> numbering
-> blank_lines
-> terms (skipped)
-> toc
-> page_numbers
-> lists
-> office (Word bila ada)
-> pdf (bila diminta)
```

Dengan `--terms`, stage `terms` berjalan dan menulis review file. Dengan
`--target docx`, `pdf` dilewati. Dengan `--target both` di Windows dan Word
tersedia, `office` dan `pdf` berjalan.

## Latihan

### 1. Cetak urutan kanonik

Jalankan:

```bash
uv run python -c "from docgen.pipeline import CANONICAL_ORDER; print(len(CANONICAL_ORDER)); print(', '.join(item.value for item in CANONICAL_ORDER))"
```

Cara memeriksa: angka pertama harus `18`, lalu daftar dimulai `validate` dan
diakhiri `pdf`. Jika ada stage tambahan atau hilang, kontrak pipeline berubah.

### 2. Temukan stage yang memutasi part tertentu

Jalankan:

```bash
grep -RIn "mutates = " src/docgen/stages
```

Cara memeriksa: `terms` dan `toc` memutasi `word/styles.xml`. Stage
`numbering` memutasi `word/document.xml` dan `word/numbering.xml`. Stage
`office` memutasi package. Cocokkan hasil dengan tabel di halaman ini.

### 3. Periksa workspace dengan --keep

Pada salinan contoh di direktori sementara, jalankan:

```bash
uv run docgen build <path-salinan>/document.md --target docx --keep
```

Cara memeriksa: direktori `.laporan-build/` masih ada dan memuat antara lain
`front_matter.md`, `mermaid.md`, `reference.docx`, dan DOCX antara. Tanpa
`--keep`, direktori itu harus hilang setelah build selesai.

## Halaman berikutnya

Lanjut ke [04 - Model DOCX](04-docx-model.md) untuk memahami package, part,
dan helper XML yang dipakai stage.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Model eksekusi dan idempotensi | [pipeline/overview.md](../pipeline/overview.md) |
| Urutan stage dan guard | [pipeline/stages.md](../pipeline/stages.md) |
| Opsi build | [pipeline/options.md](../pipeline/options.md) |
| Artefak dan workspace | [pipeline/artifacts.md](../pipeline/artifacts.md) |
| Error dan exit code | [pipeline/errors.md](../pipeline/errors.md) |
| Kontrak stage | [contracts/stage-api.md](../contracts/stage-api.md) |
| Kontrak DOCX | [contracts/docx-api.md](../contracts/docx-api.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `pytest documentation`, `pytest
markers`, dan `lxml documentation`. URL resminya ada di
[registry referensi](../references.md).
