# Quickstart

Panduan singkat untuk menulis satu laporan dari nol. Semua perintah dijalankan
dari akar repositori. Jika memakai `uv`, pasang dulu dengan `uv tool install .`
lalu ganti `python -m laporan` dengan `laporan`.

## 1. Pilih struktur

Lihat struktur dan format yang tersedia:

```bash
python -m laporan list
```

| Struktur | Cocok untuk | Penomoran |
| --- | --- | --- |
| `assignment` | Tugas kuliah, tiga bab | `1.`, `1.1`, `1.1.1` |
| `proposal` | Proposal tesis, empat bab | `1.`, `1.1`, `1.1.1` |
| `thesis` | Tesis atau skripsi, lima bab | `BAB I`, `1.1`, `1.1.1` |

Format yang tersedia saat ini adalah `undip-msi`. Untuk proyek banyak bab,
buat kerangka folder:

```bash
python -m laporan new assignment --format undip-msi --out tugas
```

## 2. Tulis `document.md`

Mode satu berkas memakai YAML front matter di awal berkas, lalu seluruh naskah
di body. Setiap heading H1 menjadi satu bab.

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

Letakkan gambar di `gambar/`, berkas `.bib` di folder yang sama dengan
`document.md`, dan jangan menulis nomor bab manual. Rincian kunci front matter
ada di [document-format.md](document-format.md). Untuk mode folder, edit
`metadata.yml` dan `chapters/*.md` hasil `new`.

## 3. Check

Periksa perkakas dan sumber sebelum build:

```bash
python -m laporan doctor
python tools/check_prose.py document.md
python tools/check_captions.py document.md
```

Untuk proyek folder, jalankan validasi manifest:

```bash
python -m laporan check tugas
```

`check` memastikan struktur, format, metadata, dan berkas bab konsisten.
Pemeriksa prosa dan caption membaca Markdown dan tidak mengubah berkas.

## 4. Build

Bangun DOCX:

```bash
python -m laporan build-file document.md --target docx
```

Ganti target menjadi `pdf` atau `both` bila perlu PDF:

```bash
python -m laporan build-file document.md --target both
```

Mode folder memakai perintah yang setara:

```bash
python -m laporan build tugas --target docx
```

Build pertama akan menjalankan Pandoc dan seluruh pascaproses DOCX. Build PDF
mengekspor DOCX final melalui Word di Windows atau LibreOffice di Debian/Linux.
Lihat [troubleshooting.md](troubleshooting.md) bila perkakas belum lengkap.

## 5. Output

Hasil build ditulis di folder yang sama dengan `document.md`:

```text
Tugas.docx
Tugas.pdf
```

Nama keluaran mengikuti kunci `report_name` (default `Tugas`). Mode folder
menulis `<report_name>.docx` dan `<report_name>.pdf` di direktori proyek.
Tambahkan `--keep` pada `build-file` bila workspace `.laporan-build/` perlu
diperiksa setelah build.

Contoh lengkap ada di [`examples/assignment-single/`](../../examples/assignment-single/).
Lanjutkan ke [writing-rules.md](writing-rules.md) sebelum menulis naskah
panjang.
