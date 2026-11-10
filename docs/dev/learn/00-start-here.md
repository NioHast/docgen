# 00 - Mulai di Sini

Halaman ini adalah pintu masuk materi belajar `docgen`. Setelah membacanya,
pembaca bisa menjelaskan apa yang dibangun repo ini, menyiapkan environment,
menjalankan perintah yang aman, dan memilih halaman berikutnya sesuai tujuan.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. menjelaskan alur singkat `document.md` menjadi DOCX dan PDF;
2. membedakan konten, struktur, format, dan pipeline;
3. menyiapkan environment dengan `uv`;
4. menjalankan `docgen --version`, `doctor`, dan `check` tanpa memanggil Word;
5. menemukan nama output dari `report_name` di front matter.

## Prasyarat

- Terminal di Windows, Linux, atau lingkungan Unix lain.
- Git dasar untuk membaca status dan diff.
- Tidak perlu memahami Python, Pandoc, atau OOXML untuk halaman ini.
- Tidak perlu Microsoft Word. Word hanya dibutuhkan untuk PDF dan finalisasi
  field pada tahap lanjut.
- Semua perintah dijalankan dari akar repo (path checkout masing-masing).

## Daftar isi

- [Apa yang dibangun](#apa-yang-dibangun)
- [Istilah singkat](#istilah-singkat)
- [Tiga lapis data](#tiga-lapis-data)
- [Peta folder minimum](#peta-folder-minimum)
- [Menyiapkan environment](#menyiapkan-environment)
- [Perintah aman pertama](#perintah-aman-pertama)
- [report_name dan lokasi output](#report_name-dan-lokasi-output)
- [Zero-fallback](#zero-fallback)
- [Memilih jalur belajar](#memilih-jalur-belajar)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## Apa yang dibangun

`docgen` adalah pipeline dokumen akademik. Sumber kebenaran adalah satu berkas
`document.md` berisi front matter YAML dan body Markdown. Pipeline memvalidasi
front matter, merender blok Mermaid bila ada, memanggil Pandoc, lalu merapikan
DOCX dengan stage Python.

Alur besarnya:

```text
document.md + references.bib + gambar/
        |
        |  docgen check
        v
   validasi front matter, struktur, aset, caption
        |
        |  docgen build
        v
   Mermaid -> front matter Markdown -> Pandoc -> package DOCX
        |
        |  stage Python: sections, captions, fields, TOC, nomor halaman
        v
   DOCX final secara struktur
        |
        |  Word di Windows: perbarui field/TOC, repaginasi
        v
   DOCX final Word -> PDF
```

DOCX dibuat oleh pipeline Python; Pandoc dipakai sebagai konverter Markdown
ke DOCX di dalam pipeline. Word tidak dipakai untuk menulis isi. Word dipakai
untuk finalisasi field seperti TOC, `PAGEREF`, nomor halaman, dan ekspor PDF.
Tanpa Word, DOCX tetap bisa dibuat dengan `--target docx`, tetapi field tidak
diperbarui. Pipeline memberi peringatan bahwa TOC memakai cache terakhir;
karena field TOC baru belum punya entri cache, TOC bisa tampil kosong sampai
dokumen dibuka di Word dan field diperbarui.

## Istilah singkat

| Istilah | Arti di repo ini |
| --- | --- |
| DOCX | Format dokumen Microsoft Word berbasis OOXML. |
| OOXML | Office Open XML, format XML di dalam package DOCX. |
| YAML | Format teks untuk front matter `document.md` dan data konfigurasi. |
| Front matter | Blok di awal `document.md` di antara `---` pembuka dan penutup. |
| Artefak | Hasil build seperti DOCX, PDF, manifest, dan review istilah. |
| TOC | Table of Contents, daftar isi native Word. |
| Field | Instruksi Word seperti TOC, PAGE, atau SEQ yang hasil finalnya dihitung Word. |

## Tiga lapis data

Jangan mencampur aturan visual ke naskah. Repo memisahkan tiga lapis:

| Lapis | Lokasi | Mengatur | Tidak boleh mengatur |
| --- | --- | --- | --- |
| Konten | `document.md`, `references.bib`, `istilah.tsv`, `gambar/` | Teks, sitasi, glosarium tambahan, aset | Margin, font, urutan bab |
| Struktur | `src/docgen/data/structures/<id>/structure.yml` | Front matter, urutan bab, TOC, daftar, penomoran | Margin, font, teks naskah |
| Format | `src/docgen/data/formats/<id>/format.yml` | Halaman, font, heading, caption, kode, aset visual | Teks naskah, urutan bab |

Pipeline berada di `src/docgen/`. Pipeline membaca data paket, bukan menyalin
aturan format ke setiap dokumen.

`document.md` adalah satu berkas. Tidak ada mode folder bab, tidak ada
`chapters/*.md`, dan tidak ada `metadata.yml` terpisah. Front matter dan body
berada di berkas yang sama.

## Peta folder minimum

| Path | Isi |
| --- | --- |
| `src/docgen/cli.py` | Entry point perintah `docgen`. |
| `src/docgen/pipeline.py` | Orkestrasi stage, opsi build, output, manifest. |
| `src/docgen/config/` | Package pembaca dan validator `format.yml` serta `structure.yml`. |
| `src/docgen/document.py` | Parser `document.md` dan validasi body. |
| `src/docgen/docx/` | Model package DOCX dan helper XML. |
| `src/docgen/stages/` | 18 stage kanonik pipeline. |
| `src/docgen/data/` | Format, struktur, template, glosarium, logo, CSL, `reference.docx`. |
| `examples/` | Tiga contoh single-file: assignment, proposal, thesis. |
| `tests/` | Unit, integration, e2e, packaging, dan fixture golden. |
| `scripts/word.ps1` | Adaptor Word untuk finalisasi field dan ekspor PDF. |
| `docs/dev/` | Dokumentasi developer, kontrak, ADR, dan materi belajar ini. |

## Menyiapkan environment

Python yang dibutuhkan adalah Python 3.15. `uv` membaca `pyproject.toml`,
menyiapkan environment, dan menjalankan perintah proyek. Langkah pertama:

```bash
uv --version
uv sync --extra dev
uv run docgen --version
```

Hasil `uv sync --extra dev` adalah environment dengan dependensi runtime dan
dependensi pengembangan seperti pytest. Setelah itu, periksa perkakas:

```bash
uv run docgen doctor
```

`doctor` memeriksa Python, Pandoc, Word, dan `mmdc`. Di Windows, Word
ditampilkan bila ditemukan. Di Linux, Word ditampilkan sebagai tidak berlaku.
Exit code 1 berarti dependensi wajib untuk DOCX belum lengkap, misalnya
Python di bawah 3.15 atau Pandoc tidak ditemukan. `mmdc` hanya wajib bila
dokumen memakai blok Mermaid.

## Perintah aman pertama

Perintah `check` tidak memanggil Pandoc atau Word. Perintah ini membaca front
matter, format, struktur, template, aset, urutan Heading 1, dan caption
Markdown. Contoh:

```bash
uv run docgen check examples/assignment-single/document.md
```

Keluaran yang diharapkan diawali `[OK]` dan memuat ringkasan format, struktur,
jumlah penulis, dan jumlah bab. Jika ada masalah, perintah berhenti dengan
`[ERROR]` dan menyebut path, key, serta kode error.

Untuk melihat perintah yang tersedia:

```bash
uv run docgen --help
```

Subperintah yang ada adalah `check`, `build`, `doctor`, dan `reconcile`.
Tidak ada perintah `new` atau `list`.

## report_name dan lokasi output

`report_name` wajib di front matter. Tidak ada nilai default `"Tugas"` dan
tidak ada flag CLI `--report-name`. Nilai ini menjadi nama berkas DOCX dan
PDF.

Contoh ringkas dari `examples/assignment-single/document.md`; field lain di
berkas asli tidak ditampilkan:

```yaml
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
report_name: "Tugas"
structure: assignment
format: undip-msi
bibliography: references.bib
---
```

Aturan lokasi output:

- Dokumen di `examples/<nama>/document.md` menghasilkan
  `examples/<nama>/out/<report_name>.docx`.
- Dokumen pengguna lain menghasilkan `<folder-document>/<report_name>.docx`.
- Manifest berada di `.laporan/manifest.json` di samping `document.md`.
- Workspace sementara berada di `.laporan-build/` di samping `document.md`.

Lokasi ini dihitung oleh `docgen.paths.output_directory`. Tidak ada fallback
ke direktori kerja saat ini atau ke folder `build/` dan `review/`.

## Zero-fallback

Repo ini memakai aturan zero-fallback: input yang tidak lengkap menghasilkan
error yang menunjuk penyebabnya, bukan nilai tebakan. Contoh yang bisa
ditemui:

| Situasi | Perilaku |
| --- | --- |
| `report_name` tidak ada atau kosong | `CFG-REQUIRED`, bukan nama default. |
| Kunci front matter tidak dikenal | `CFG-UNKNOWN-KEY`, bukan diabaikan. |
| Artifact Markdown untuk Pandoc hilang | `PANDOC-INPUT`, bukan membaca berkas cadangan. |
| Lebar konten tidak bisa dibaca dari section | `PAGE-WIDTH`, bukan angka twip tebakan. |

Saat membaca error, perhatikan path, key, dan kode. Perbaiki input atau data
konfigurasi. Jangan menambahkan fallback diam-diam agar build lewat.

## Memilih jalur belajar

| Tujuan | Baca |
| --- | --- |
| Ingin tahu cara kerja repo | [01 - Model Mental](01-mental-model.md) |
| Ingin segera menghasilkan DOCX | [02 - Build Pertama](02-first-build.md) |
| Ingin melacak stage | [03 - Tahap Pipeline](03-pipeline-stages.md) |
| Ingin mengubah XML DOCX | [04 - Model DOCX](04-docx-model.md) |
| Ingin menjalankan tes dan debug | [05 - Tes dan Debugging](05-testing-and-debugging.md) |
| Ingin mengubah fitur atau data | [06 - Resep Perubahan](06-change-recipes.md) |

## Latihan

### 1. Periksa environment

Jalankan:

```bash
uv run docgen --version
uv run docgen doctor
```

Cara memeriksa: `--version` harus mencetak `docgen 0.1.0` atau versi paket
yang lebih baru. Pada `doctor`, baris Python harus menunjukkan versi 3.15 atau
lebih baru dan baris Pandoc harus menemukan executable. Jika Word tidak ada,
baris Word boleh menunjukkan tidak ditemukan selama target yang dipakai hanya
DOCX.

### 2. Verifikasi perintah yang tersedia

Jalankan:

```bash
uv run docgen --help
uv run docgen build --help
```

Cara memeriksa: output `--help` memuat `check`, `build`, `doctor`, dan
`reconcile`. Output `build --help` memuat `--target`, `--keep`, `--terms`,
`--no-manifest`, `--no-adeu`, dan `--allow-missing-word`. Tidak boleh ada flag
`--report-name`.

### 3. Jalankan check pada tiga contoh

Jalankan:

```bash
uv run docgen check examples/assignment-single/document.md
uv run docgen check examples/proposal-single/document.md
uv run docgen check examples/thesis-single/document.md
```

Cara memeriksa: ketiga perintah mengembalikan exit code 0 dan mencetak
`[OK]`. Contoh assignment menampilkan `struktur=assignment bab=3`, proposal
menampilkan `bab=4`, dan thesis menampilkan `bab=5`.

## Halaman berikutnya

Lanjut ke [01 - Model Mental](01-mental-model.md) untuk memahami lapisan dan
alur data sebelum menjalankan build.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Gambaran arsitektur dan invariant | [architecture.md](../architecture.md) |
| Peta folder dan tanggung jawab | [repo-map.md](../repo-map.md) |
| Kontrak front matter, format, struktur | [contracts/config.md](../contracts/config.md) |
| Kontrak stage dan CLI | [contracts/stage-api.md](../contracts/stage-api.md) |
| Indeks dokumentasi developer | [../README.md](../README.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `Python 3.15 language reference`,
`uv documentation`, `Pandoc installation`, dan `Word COM object model (VBA
reference)`. URL resminya ada di [registry referensi](../references.md).
