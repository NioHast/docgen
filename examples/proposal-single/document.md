---
title: "Rancangan Pipeline Validasi Dokumen Akademik Berbasis Markdown"
author: "Nama Mahasiswa"
nim: "30000000000000"
institution: "Universitas Diponegoro"
faculty: "Program Studi Magister Sistem Informasi"
year: "2026"
date: "November 2026"
lang: "id-ID"
structure: proposal
format: undip-msi
bibliography: references.bib
---

# Pendahuluan

## Latar Belakang

Dokumen akademik seperti proposal tesis memuat banyak aturan format yang
harus dipenuhi sekaligus: urutan bab, penomoran, caption, sitasi, dan daftar
pustaka. Penulisan langsung di pengolah kata membuat aturan tersebut mudah
berubah ketika naskah disunting. Pendekatan berbasis Markdown memisahkan isi
dari presentasi sehingga naskah dapat diperiksa sebagai teks biasa
[@gruber2004markdown; @pandoc2024].

Pipeline `docgen` menempatkan aturan visual di `format.yml`, urutan bab di
`structure.yml`, dan isi proposal di `document.md`. Sebelum build dijalankan,
front matter, urutan Heading 1, gambar, dan berkas bibliografi divalidasi.
Dengan cara ini, kesalahan konfigurasi ditemukan lebih awal dan tidak baru
terlihat setelah DOCX terbentuk.

## Tujuan Penelitian

Penelitian ini bertujuan merancang pipeline yang dapat:

1. memisahkan naskah proposal dari aturan format dan struktur;
2. memvalidasi front matter, aset, dan urutan bab sebelum proses konversi;
3. menghasilkan DOCX dengan caption, penomoran, dan sitasi yang konsisten.

## Manfaat Penelitian

Secara teoretis, rancangan ini menunjukkan penerapan prinsip pemisahan
tanggung jawab pada penulisan dokumen akademik. Secara praktis, mahasiswa dan
dosen dapat meninjau perubahan naskah melalui diff baris, memakai ulang
aturan format, dan mengurangi pekerjaan perapian manual.

# Tinjauan Pustaka

## Markdown dan Pandoc

Markdown menyediakan sintaks ringan untuk judul, daftar, tabel, dan tautan
[@gruber2004markdown]. Spesifikasi CommonMark menyeragamkan aturan sintaks
agar hasil konversi tidak bergantung pada implementasi tertentu
[@commonmark2021]. Pandoc memperluas cakupan tersebut dengan dukungan tabel
pipa, persamaan, sitasi BibTeX, dan filter pemrosesan dokumen
[@krewinkel2020pandoc].

Penelitian terdahulu tentang otomatisasi dokumen banyak menekankan
keterulangan build dan pemisahan konten dari format. Pada konteks dokumen
akademik Indonesia, tantangan tambahan muncul dari aturan penomoran halaman
Romawi dan Arab, caption per bab, serta istilah resmi kampus.

## Dasar Teori

Office Open XML menyimpan dokumen Word sebagai paket ZIP berisi
`word/document.xml`, `word/styles.xml`, `word/numbering.xml`, dan relasi
antarbagian [@iso2021openxml]. Pipeline memakai struktur tersebut untuk
memberi nomor caption dan persamaan, mengatur section, serta memperbarui
field daftar isi. Pendekatan ini memungkinkan aturan yang tidak dapat
diwakili AST Markdown tetap diterapkan secara eksplisit.

# Metode Penelitian

## Bahan dan Alat Penelitian

Bahan penelitian berupa naskah Markdown, berkas BibTeX, dan gambar lokal.
Alat yang dipakai meliputi Python 3.15, Pandoc, `python-docx`, `lxml`, dan
`ruamel.yaml`. Microsoft Word diperlukan hanya untuk ekspor PDF pada Windows.

## Prosedur Penelitian

Tahapan penelitian disusun sebagai berikut.

1. Menyusun front matter dan struktur bab proposal.
2. Menulis naskah Markdown beserta tabel, sitasi, dan aset gambar.
3. Menjalankan `docgen check` untuk memvalidasi konfigurasi dan aset.
4. Membangun DOCX dan memeriksa caption, penomoran, serta daftar isi.
5. Mengevaluasi hasil dan mencatat keterbatasan pipeline.

Kriteria keberhasilan pada tahap ini adalah `docgen check` lulus dan seluruh
aset yang dirujuk dapat ditemukan. Pemeriksaan tampilan akhir dilakukan
secara terpisah pada DOCX hasil build.

# Jadwal Penelitian

Jadwal penelitian disusun dalam bentuk matriks kegiatan dan waktu
pelaksanaan selama enam bulan.

: Jadwal penelitian

| No | Kegiatan | Bulan 1 | Bulan 2 | Bulan 3 | Bulan 4 | Bulan 5 | Bulan 6 |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | Studi literatur dan penyusunan kerangka teori | X | X |  |  |  |  |
| 2 | Penyusunan naskah dan struktur proposal |  | X | X |  |  |  |
| 3 | Validasi konfigurasi dan aset |  |  | X | X |  |  |
| 4 | Build DOCX dan pemeriksaan caption |  |  |  | X | X |  |
| 5 | Evaluasi dan penyusunan laporan |  |  |  |  | X | X |
