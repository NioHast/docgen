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
structure: assignment
format: undip-msi
toc: false
bibliography: references.bib
---

# Pendahuluan

## Latar Belakang

Laporan akademik menuntut struktur, penomoran, dan sitasi yang konsisten. Penulisan langsung di pengolah kata sering membuat format berpindah saat dokumen disunting ulang. Pemisahan antara naskah dan presentasi mengurangi masalah tersebut: naskah ditulis dalam Markdown, lalu dikonversi oleh Pandoc [@pandoc2024] menjadi DOCX atau PDF.

Pendekatan ini juga memudahkan peninjauan melalui Git. Perubahan teks tampil sebagai diff baris, bukan sebagai berkas biner yang tidak terbaca. Mesin keluaran dapat diganti tanpa menulis ulang isi laporan.

## Rumusan Masalah

1. Bagaimana menyusun naskah tugas dalam struktur bab yang baku?
2. Bagaimana memastikan format, metadata, dan sitasi konsisten saat build?
3. Bagaimana memisahkan konten dari aturan visual agar mudah dipakai ulang?

## Tujuan

Tujuan tugas ini adalah menghasilkan contoh laporan yang dibangun dari struktur `assignment`, format `undip-msi`, dan pipeline build yang sudah ada.

# Pembahasan

## Lapisan Format

Format menyimpan aturan visual yang tidak bergantung pada isi, misalnya margin, tipografi, dan gaya sitasi. Pada contoh ini format `undip-msi` memakai preset `undip-msi-proposal`, CSL `refs/undip-msi.csl`, dan bibliografi `references.bib`.

## Lapisan Struktur

Struktur menentukan urutan bagian. Struktur `assignment` memakai penomoran Arab bertitik dengan tiga bab:

: Peran berkas dalam struktur assignment

| Urutan | Berkas | Peran |
| --- | --- | --- |
| 1 | `chapters/01-pendahuluan.md` | Pendahuluan |
| 2 | `chapters/02-pembahasan.md` | Pembahasan |
| 3 | `chapters/03-penutup.md` | Penutup |

Struktur tidak menyimpan teks naskah. Dengan begitu, struktur yang sama dapat dipakai banyak proyek konten.

## Lapisan Konten dan Platform

Konten berisi metadata, bab Markdown, gambar, dan bibliografi. Platform menyediakan perintah `list`, `new`, `check`, `build`, dan `doctor`. Perintah `build` hanya memanggil `build-docx.sh` atau `build.sh`; logika DOCX dan PDF tidak diduplikasi.

```{.mermaid caption="Alur build satu berkas"}
flowchart LR
  A[Berkas Markdown] --> B[Workspace build]
  B --> C[DOCX atau PDF]
```

Pandoc menangani konversi dokumen [@pandoc2024], sedangkan Typst dipakai pipeline PDF [@typst2024]. Keduanya menerima sumber Markdown yang sama sehingga isi laporan tidak perlu ditulis dua kali.

# Penutup

## Kesimpulan

Pemisahan format, struktur, konten, dan platform membuat laporan lebih mudah diperiksa dan dibangun ulang. Naskah tetap berupa Markdown, sedangkan aturan visual serta urutan bab disimpan di berkas YAML yang dapat dipakai ulang.

## Saran

Langkah berikutnya adalah menambahkan pemeriksaan otomatis untuk variabel front matter yang belum didukung pipeline lama, lalu memperluas contoh ke struktur `proposal` dan `thesis`.
