# Workflow Satu Berkas Markdown

`python -m laporan build-file` membangun DOCX/PDF dari **satu berkas Markdown**. Berkas
sumber memuat YAML front matter di awal dan seluruh naskah di body. Pipeline
DOCX/PDF yang lama tetap dipakai; perintah ini hanya menyiapkan proyek
sementara yang kompatibel dengan `build-docx.sh` dan `build.sh`.

Cocok untuk tugas pendek, laporan satu penulis, atau naskah yang ditulis agent.
Untuk tesis panjang dengan banyak bab dan review per bab, gunakan mode folder
(`manifest.yml` + `chapters/`).

## Format sumber

```markdown
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
structure: assignment
format: undip-msi
toc: false
bibliography: references.bib
---

# Pendahuluan

Latar belakang dengan sitasi [@pandoc2024].

# Pembahasan

Isi pembahasan.

# Penutup

Kesimpulan.
```

Front matter wajib berada di awal berkas. Body boleh memuat beberapa bab; setiap
H1 diperlakukan sebagai bab oleh pipeline. Jangan menulis nomor bab manual
(`# BAB I`) karena `docx.lua` menambahkan penomoran sendiri. Berkas sumber tidak
diubah oleh `build-file`; TOC, caption, dan blok Mermaid diproses di workspace
seperti pada mode folder.

### Kunci front matter

| Kunci | Wajib | Keterangan |
| --- | --- | --- |
| `title` | ya | Judul laporan. |
| `author` | ya | Teks, pemetaan `{name, nim}`, atau daftar keduanya. |
| `nim` | tidak | Dipakai bila `author` berupa teks dan hanya ada satu penulis. |
| `structure` | tidak | Nama struktur di `structures/`; default `assignment`. |
| `format` | tidak | Nama format di `formats/`; default mengikuti struktur (`undip-msi`). |
| `preset` | tidak | Override preset; default `format.presets[structure]`. |
| `toc` | tidak | Default mengikuti struktur. |
| `bibliography` | tidak | Path `.bib` relatif terhadap berkas; default `references.bib`. |
| `report_name` | tidak | Nama keluaran tanpa ekstensi; default `Tugas`. |
| `glossary` | tidak | Path `istilah.tsv` relatif; default `writing/istilah.tsv` repositori. |

Kunci metadata lain yang lazim dipakai `docx.lua`/Pandoc (`subtitle`,
`lecturer`, `course`, `institution`, `faculty`, `year`, `date`, `lang`,
`approval`, `abstract_id`, `abstract_en`, `keywords_id`, `keywords_en`,
`daftar_gambar`, `daftar_tabel`, dan override heading) diteruskan ke
`metadata.yml` sementara.

Kunci yang mengatur materialisasi (`structure`, `format`, `preset`,
`bibliography`, `report_name`, `output`, `glossary`, `references`) tidak
diteruskan ke metadata Pandoc. Path absolut juga ditolak agar metadata tetap
portabel.

## Aset

- **Bibliografi**: berkas `.bib` harus berada di folder berkas sumber atau
  subfoldernya dan ditulis relatif, mis. `bibliography: references.bib`.
  Berkas disalin ke workspace sebagai `references.bib` karena
  `build-docx.sh` memakai nama tersebut.
- **Gambar**: semua gambar harus berada di `gambar/` relatif terhadap berkas
  sumber, mis. `![Diagram](gambar/diagram.png)`. Folder `gambar/` disalin utuh
  ke workspace. Path absolut, `..`, dan gambar di luar `gambar/` ditolak.
- **Glosarium**: `writing/istilah.tsv` repositori disalin ke workspace. Jika
  laporan memakai glosarium sendiri, isi `glossary: istilah.tsv` dan letakkan
  berkas itu di folder sumber.
- **Caption**: tabel memerlukan baris `: Judul tabel`; gambar memerlukan alt
  text non-kosong. Aturan ini tetap ditegakkan `build-docx.sh`.

## Perintah

```bash
python -m laporan build-file document.md
python -m laporan build-file document.md --target pdf
python -m laporan build-file document.md --target both
python -m laporan build-file document.md --target both --keep
```

| Flag | Arti |
| --- | --- |
| `--target docx` | Bangun DOCX saja (default). |
| `--target pdf` | Bangun PDF saja. DOCX tetap dibuat sebagai tahap antara di workspace, tetapi hanya PDF yang disalin ke folder sumber. |
| `--target both` | Bangun DOCX dan PDF. |
| `--keep` | Jangan hapus `.laporan-build/` setelah build. Berguna untuk memeriksa `metadata.yml`, `chapters/01.md`, `build/manifest-*.json`, dan `review/istilah-baru.txt`. |

Keluaran akhir ditulis di folder berkas sumber:

```text
folder-tugas/
|-- document.md
|-- references.bib
|-- gambar/
|-- Tugas.docx
`-- Tugas.pdf
```

Nama keluaran mengikuti `report_name` (default `Tugas`).

## Workspace sementara

Sebelum build, `build-file` membuat `.laporan-build/` **di folder berkas
sumber**, bukan di repositori:

```text
.laporan-build/
|-- metadata.yml
|-- cover.md
|-- chapters/01.md      # seluruh body
|-- references.bib
|-- gambar/
`-- writing/istilah.tsv
```

`build-docx.sh`/`build.sh` dipanggil dengan environment:

```text
LAPORAN_METADATA=<workspace>/metadata.yml
LAPORAN_CHAPTERS=<workspace>/chapters
LAPORAN_REPORT_NAME=<report_name>
LAPORAN_TOC=true|false
LAPORAN_PYTHON=<python yang menjalankan CLI>
OUTDIR=<workspace>
```

Workspace dihapus setelah build selesai, termasuk saat build gagal. Gunakan
`--keep` untuk mempertahankannya. Repositori tidak ditulis; aset pipeline
(`presets/`, `refs/`, `tools/`, `scripts/`, `docx.lua`, `reference.docx`)
dibaca dari akar repositori.

## Validasi dan exit code

`build-file` berhenti dengan exit code `1` bila:

- berkas tidak ada, bukan `.md`, atau bukan UTF-8;
- front matter tidak ada, kosong, atau YAML-nya tidak valid;
- `title`/`author` tidak ada;
- `structure`, `format`, atau `preset` tidak dikenal;
- `bibliography` atau `glossary` tidak ditemukan, absolut, atau keluar dari
  folder sumber;
- gambar yang dirujuk tidak ditemukan, absolut, memakai `..`, atau berada di
  luar `gambar/`;
- `report_name` memuat karakter path;
- `build-docx.sh`/`build.sh` gagal atau tidak menghasilkan keluaran.

Argumen yang salah ditangani `argparse` dengan exit code `2`.

## Contoh

Contoh lengkap ada di `examples/assignment-single/`:

```bash
python -m laporan build-file examples/assignment-single/document.md --target both
```

Hasilnya `examples/assignment-single/Tugas.docx` dan `Tugas.pdf`.
