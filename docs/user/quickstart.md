# Quickstart

Panduan singkat dari naskah kosong sampai DOCX, lalu dari `deck.yaml` sampai
PPTX/PDF/Slides. Semua perintah `autooffice` dijalankan dari akar repo:

```bash
uv run autooffice <perintah> ...
```

## Daftar isi

- [1. Pilih struktur](#1-pilih-struktur)
- [2. Siapkan berkas](#2-siapkan-berkas)
- [3. Tulis front matter](#3-tulis-front-matter)
- [4. Check](#4-check)
- [5. Build](#5-build)
- [6. Periksa output](#6-periksa-output)
- [7. Quickstart deck](#7-quickstart-deck)
- [Contoh](#contoh)

## 1. Pilih struktur

Struktur menentukan urutan bab, front matter, penomoran, dan daftar. Format
`undip-msi` menentukan margin, font, caption, sitasi, dan aset visual.

| Struktur | Cocok untuk | Bab body | Penomoran |
| --- | --- | ---: | --- |
| `assignment` | Tugas kuliah | 3 | `1.`, `1.1`, `1.1.1` |
| `proposal` | Proposal tesis | 4 | `1.`, `1.1`, `1.1.1` |
| `thesis` | Tesis atau skripsi | 5 | `BAB I`, `1.1`, `1.1.1` |

Struktur `thesis` menambahkan halaman pengesahan, pernyataan, kata pengantar,
abstrak Indonesia dan Inggris, daftar isi, daftar tabel, daftar gambar, dan
lampiran. Struktur `proposal` menambahkan halaman pengesahan dan daftar isi.
Struktur `assignment` hanya memuat sampul.

## 2. Siapkan berkas

Buat direktori kerja dengan isi minimal:

```text
tugas/
|-- document.md
|-- references.bib
`-- gambar/          # opsional, dipakai bila ada gambar
```

Cara tercepat adalah menyalin salah satu contoh dari akar repo, lalu
menyesuaikan isinya:

```bash
cp -r examples/assignment-single tugas
rm -rf tugas/out tugas/.laporan tugas/Tugas.pdf
```

Jangan menyalin `out/` atau `.laporan/` dari contoh. Keduanya artefak build.

## 3. Tulis front matter

Front matter wajib berada di awal `document.md` dan dibatasi `---`. Kunci
wajib adalah `title`, `author`, `report_name`, `structure`, dan `format`.

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

# Pendahuluan

Latar belakang dengan sitasi [@pandoc2024].

# Pembahasan

Isi pembahasan.

# Penutup

Kesimpulan.
```

Heading 1 harus sama dengan urutan `body` struktur. Jangan menulis nomor bab.
Rincian kunci lain ada di [document-format.md](document-format.md).

## 4. Check

Jalankan pemeriksaan sumber sebelum build:

```bash
uv run autooffice check document.md
```

`check` memvalidasi front matter, keberadaan format dan struktur, template,
bibliografi, gambar, urutan Heading 1, dan caption Markdown. Perintah ini tidak
memanggil Pandoc atau Word dan tidak menulis berkas.

Pemeriksa prosa terpisah dan hanya memberi petunjuk:

```bash
uv run autooffice doctor
uv run python tools/dev/check_prose.py document.md
```

## 5. Build

Bangun DOCX:

```bash
uv run autooffice build document.md --target docx
```

Di Windows dengan Microsoft Word terpasang, bangun DOCX dan PDF:

```bash
uv run autooffice build document.md --target docx,pdf
```

Di Debian atau lingkungan tanpa Word, gunakan `--target docx`. Target `pdf`
memerlukan Word COM dan tidak memiliki fallback diam-diam.

Tambahkan `--keep-intermediate` bila workspace `.laporan-build/` perlu
diperiksa setelah build. Tambahkan `--terms` bila ingin mengaktifkan gate
glosarium.

## 6. Periksa output

Output ditulis di direktori yang sama dengan `document.md`:

```text
tugas/
|-- document.md
|-- references.bib
|-- Tugas.docx
|-- Tugas.pdf            # hanya Windows dengan Word
|-- .laporan/
|   `-- manifest.json
`-- .laporan-build/      # hanya dengan --keep-intermediate
```

Nama berkas mengikuti `report_name` yang wajib di front matter. Tidak ada nama
default, dan DOCX serta PDF memakai stem yang sama. Manifest berisi bookmark
`pNNNN` untuk penelusuran edit Word.

## 7. Quickstart deck

Deck memakai satu `deck.yaml` sebagai sumber. Salin contoh demo, lalu hapus
artefak build yang terbawa:

```bash
cp -r examples/demo-deck deck-saya
rm -rf deck-saya/out deck-saya/.autooffice deck-saya/.autooffice-build
```

Edit `deck.yaml`, lalu sesuaikan `copy.yaml`, `transcripts.md`, `assets/`, dan
`diagrams/` bila ada. Path aset relatif terhadap `deck.yaml`.

Periksa sumber tanpa menulis output:

```bash
uv run autooffice check deck-saya/deck.yaml
```

`check` berjalan di Linux, macOS, dan Windows. Final `pptx` dan `pdf`
memerlukan Windows dengan Microsoft PowerPoint desktop dan `pywin32`
(`uv sync --extra windows`). Final `pptx` menanam font Plus Jakarta Sans lewat
PowerPoint COM; pasang font per-user lebih dulu:

```bash
python tools/install_fonts.py
```

Di Windows, bangun PPTX, lalu PPTX dan PDF:

```bash
uv run autooffice build deck-saya/deck.yaml --target pptx
uv run autooffice build deck-saya/deck.yaml --target pptx,pdf
```

Di Linux/macOS, `check` tetap berjalan dan DOCX dari Markdown dapat dibangun,
tetapi final PPTX/PDF tidak tersedia karena penanaman font dan ekspor memakai
Office COM.

Sinkronkan ke Google Slides setelah `uv sync --extra google` dan kredensial
OAuth siap:

```bash
uv run autooffice build deck-saya/deck.yaml --target slides
```

Rincian authoring ada di [deck-authoring.md](deck-authoring.md), target dan
flag di [CLI AutoOffice](cli.md), dan konsep pipeline di
[deck-pipeline.md](../learn/deck-pipeline.md).

## Contoh

- [assignment-single](../../examples/assignment-single/document.md): tiga bab,
  satu tabel, satu diagram Mermaid.
- [proposal-single](../../examples/proposal-single/document.md): empat bab,
  satu tabel, daftar isi.
- [thesis-single](../../examples/thesis-single/document.md): lima bab, front
  matter lengkap, gambar, Mermaid, persamaan, kode, dan lampiran.

Lanjutkan ke [writing-rules.md](writing-rules.md) sebelum menulis naskah
panjang. Bila ada kegagalan, lihat [troubleshooting.md](troubleshooting.md).
