---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
lecturer: "Dr. Nama Dosen Pengampu, M.Kom."
lecturer_label: "Dosen Pengampu:"
course: "Penulisan Laporan Akademik"
institution: "Universitas Diponegoro"
faculty: "Program Studi Magister Sistem Informasi"
year: "2026"
date: "Agustus 2026"
lang: "id-ID"
report_name: "Tugas"
structure: assignment
format: undip-msi
bibliography: references.bib
---

# Pendahuluan

## Latar Belakang

Laporan akademik menuntut struktur, penomoran, dan sitasi yang konsisten. Penulisan langsung di pengolah kata sering membuat format berpindah saat dokumen disunting ulang. Pemisahan antara naskah dan presentasi mengurangi masalah tersebut: naskah ditulis dalam Markdown, lalu dikonversi oleh Pandoc [@pandoc2024] menjadi DOCX atau PDF.

Pendekatan ini juga memudahkan peninjauan melalui Git. Perubahan teks tampil sebagai diff baris, bukan sebagai berkas biner yang tidak terbaca. Aturan keluaran dapat diganti tanpa menulis ulang isi laporan.

## Rumusan Masalah

1. Bagaimana menyusun naskah tugas dalam struktur bab yang baku?
2. Bagaimana memastikan format, front matter, dan sitasi konsisten saat build?
3. Bagaimana memisahkan konten dari aturan visual agar mudah dipakai ulang?

## Tujuan

Tujuan tugas ini adalah menghasilkan contoh laporan yang dibangun dari struktur `assignment`, format `undip-msi`, dan pipeline Python `autooffice`.

# Pembahasan

## Lapisan Format

Format menyimpan aturan visual yang tidak bergantung pada isi, misalnya margin, tipografi, dan gaya caption. Pada contoh ini format `undip-msi` dibaca dari `src/autooffice/docx/data/formats/undip-msi/format.yml`; berkas itu juga menunjuk CSL `citation.csl`. Path bibliografi ditulis di front matter `document.md`, sedangkan nilai visual tetap berada di `format.yml`.

## Lapisan Struktur

Struktur menentukan urutan bagian dan aturan penomoran. Struktur `assignment` dibaca dari `src/autooffice/docx/data/structures/assignment/structure.yml` dan memakai penomoran Arab bertitik dengan tiga bab:

: Peran berkas dalam pipeline satu berkas

| Lapisan | Berkas | Peran |
| --- | --- | --- |
| Format | `src/autooffice/docx/data/formats/undip-msi/format.yml` | Margin, tipografi, caption, dan `citation.csl` |
| Struktur | `src/autooffice/docx/data/structures/assignment/structure.yml` | Urutan bab, TOC, dan penomoran |
| Konten | `document.md` | Front matter, naskah, tabel, gambar, dan sitasi |
| Aset | `references.bib`, `gambar/` | Entri BibTeX dan gambar lokal |

Struktur tidak menyimpan teks naskah. Dengan begitu, struktur yang sama dapat dipakai banyak proyek konten.

## Lapisan Konten dan Pipeline

Konten berisi front matter, bab Markdown, gambar, dan bibliografi. Perintah `autooffice check` memvalidasi front matter, format, struktur, template, aset, dan urutan bab. Perintah `autooffice build` menjalankan pipeline Python: render Mermaid, materialisasi front matter, konversi Pandoc, lalu stage DOCX untuk caption, persamaan, penomoran, daftar isi, dan nomor halaman.

```bash
uv run --project . autooffice check examples/assignment-single/document.md
uv run --project . autooffice build examples/assignment-single/document.md --target docx
```

```{.mermaid caption="Alur check dan build satu berkas"}
flowchart LR
  A[document.md] --> B[autooffice check]
  B --> C[autooffice build]
  C --> D[Pandoc]
  D --> E[Stage Python DOCX]
  E --> F[DOCX]
  F --> G[PDF melalui Word]
```

Pandoc menangani konversi dokumen [@pandoc2024], sedangkan stage Python bekerja pada paket Office Open XML [@iso2021openxml] untuk merapikan caption, persamaan, dan penomoran. Sumber Markdown yang sama dipakai untuk DOCX maupun PDF, sehingga isi laporan tidak perlu ditulis dua kali. PDF diekspor dari DOCX melalui Microsoft Word pada Windows.

# Penutup

## Kesimpulan

Pemisahan format, struktur, dan konten membuat laporan lebih mudah diperiksa dan dibangun ulang. Naskah tetap berupa Markdown, sedangkan aturan visual serta urutan bab disimpan di berkas YAML yang dapat dipakai ulang. Pipeline Python `autooffice` menjalankan validasi dan seluruh stage DOCX tanpa memerlukan skrip build terpisah.

## Saran

Langkah berikutnya adalah menambah format institusi lain dan memperluas pemeriksaan paritas keluaran DOCX. Contoh juga dapat diperluas dengan studi kasus yang memakai tabel dan gambar dalam jumlah lebih banyak.
