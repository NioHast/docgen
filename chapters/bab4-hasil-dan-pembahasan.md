# HASIL DAN PEMBAHASAN

## Struktur Berkas dan Implementasi Sistem

Implementasi pipeline **Laporan Generator** menghasilkan struktur direktori yang modular dan terorganisasi secara sistematis:

```
laporan-generator/
|-- laporan                  # CLI Helper terpadu (build, pdf, docx, init, preset, check)
|-- build.sh                 # Skrip build utama PDF (Typst engine)
|-- build-docx.sh            # Skrip build DOCX (Pandoc + pascaproses)
|-- Makefile                 # Target otomasi (build, docx, html, watch, view, clean)
|-- template.typ             # Template visual Typst (font, margin, heading)
|-- docx.lua                 # Filter Lua penomoran bab & sampul DOCX
|-- reference.docx           # Template gaya Microsoft Word (A4, TNR 12pt)
|-- metadata.yml             # Konfigurasi judul, penulis, dosen, institusi, preset
|-- references.bib           # Basis data daftar pustaka (format BibTeX)
|-- refs/undip-msi.csl       # Aturan sitasi author-date
|-- cover.md                 # Kata pengantar & outline front matter
|-- chapters/                # Konten laporan modular (BAB I s/d BAB V)
|-- presets/                 # Konfigurasi format kampus (UI, ITB, UGM, ITS, UNDIP, dll.)
|-- scripts/                 # Utilitas Python (scan-preset, validate, docx-pagenum)
|-- tools/                   # Generator style, istilah, caption, ID paragraf, rekonsiliasi
|-- tests/                   # Suite pytest dan fixture
|-- writing/                 # Panduan penulisan, daftar larangan, glosarium istilah
|-- gambar/                  # Gambar yang dirujuk bab
\-- docs/                    # Dokumentasi rinci pipeline dan format
```

## Evaluasi Hasil Keluaran Dokumen PDF (Typst Engine)

Kompilasi dokumen PDF menggunakan Typst menghasilkan dokumen akademik dengan kualitas tipografi tingkat tinggi. Beberapa pencapaian visual utama meliputi:

1. **Struktur Penomoran Bab Dua Baris**: Sesuai dengan pedoman penulisan karya ilmiah di Indonesia, judul bab level 1 dirender dalam dua baris simetris: baris pertama berisi prefix angka Romawi tebal (contoh: `BAB I`), dan baris kedua berisi nama judul bab dalam huruf kapital tebal 14pt (contoh: `PENDAHULUAN`).
2. **Kerapian Spasi dan Indentasi Paragraf**: Teks isi menggunakan font Libertinus Serif 12pt dengan spasi baris 1.5 (`leading: 0.75em`) dan perataan rata kanan-kiri (*justified*). Baris pertama setiap alinea diindentasi secara presisi sebesar 1.25 cm.
3. **Penyusunan Tabel dan Gambar yang Bersih**: Seluruh gambar diposisikan di tengah halaman dengan keterangan caption di bagian bawah. Tabel akademik bergaris tipis 0.5pt abu-abu tanpa border vertikal berlebih.
4. **Sitasi Otomatis Format Author-Date**: Seluruh pengutipan dalam teks ditampilkan sebagai nama penulis dan tahun, misalnya `(Nama, tahun)`, dan ditautkan ke entri alfabetis tanpa nomor pada DAFTAR PUSTAKA di akhir dokumen dengan penataan *hanging indent* 1.25 cm.

## Evaluasi Hasil Keluaran Dokumen Word (DOCX Multi-Pass)

Dokumen Microsoft Word (`Laporan.docx`) yang dihasilkan melalui proses multi-pass berhasil memenuhi persyaratan format formal:

1. **Pemisahan Seksi dan Penomoran Halaman**: Sampul depan tampil bersih tanpa nomor halaman. Bagian KATA PENGANTAR dan DAFTAR ISI memiliki penomoran angka Romawi kecil (*i, ii*). Pada awal BAB I, penomoran halaman berhasil dimulai ulang (*restart*) dari angka Arab 1 (*1, 2, 3...*).
2. **Daftar Isi Otomatis Terhubung (Hyperlinked TOC)**: Entri Daftar Isi dihubungkan dengan *hyperlink internal* dan menampilkan nomor halaman aktual secara presisi berkat proses injeksi nilai cache oleh `docx-pagenum.py`.
3. **Konsistensi Gaya dan Font**: Dokumen Word menggunakan font Times New Roman berukuran 12pt pada teks normal dan 14pt tebal pada Heading 1, memastikan paritas visual yang identik dengan dokumen PDF.

## Analisis Komparasi Kinerja dan Efisiensi

Tabel berikut menyajikan perbandingan komprehensif antara pipeline **Laporan Generator (Typst Engine)**, pipeline berbasis **LaTeX Tradisional**, dan penyusunan manual menggunakan **Microsoft Word**:

| Parameter Evaluasi | Laporan Generator (Typst) | LaTeX Tradisional | Microsoft Word Manual |
|:---|:---|:---|:---|
| **Waktu Kompilasi Dokumen** | **< 1.0 detik** | 10 -- 30 detik | Tidak ada (Manual) |
| **Ukuran Toolchain / Instalasi** | **~25 MB** (Binary Typst) | ~4.5 GB (TeX Live) | ~2.5 GB (MS Office) |
| **Dukungan Version Control (Git)** | **Sangat Baik** (Plain Text) | Sangat Baik (Plain Text)| Sangat Buruk (Binary DOCX)|
| **Keluaran Format Ganda** | **PDF & DOCX Sinkron** | Hanya PDF | Hanya DOCX |
| **Penanganan Layout Drift** | **Deterministik & Otomatis** | Deterministik | Sering Bergeser Manual |
| **Konfigurasi Format Kampus** | **1 Baris YAML Preset** | Modifikasi .cls/macro | Setting Style GUI Manual |
| **Integrasi AI Agent** | **Terbuka (Markdown + CLI)** | Kustom / Manual | Terbatas |

## Hasil Verifikasi melalui Pytest dan Build

Verifikasi fungsional dilakukan dengan menjalankan suite pytest di direktori `tests/` yang terbagi dalam modul-modul pengujian. Modul-modul tersebut memeriksa kesesuaian gaya `reference.docx` dengan spesifikasi acuan, penomoran heading, format caption/gambar/tabel, struktur penomoran halaman DOCX, ekspor DOCX ke DOTX, injeksi ID paragraf dan manifest, penerapan istilah asing, integrasi dengan Pandoc, rekonsiliasi edit manual DOCX ke Markdown, serta pemeriksaan prosa.

Verifikasi integrasi dilakukan dengan membangun kedua keluaran menggunakan `bash build.sh` untuk PDF dan `bash build-docx.sh` untuk DOCX. Build DOCX juga menjalankan pascaproses section, caption, istilah, nomor halaman, dan ID paragraf. Karena jumlah kasus uji dapat berubah setiap kali suite diperbarui, laporan ini tidak mencantumkan angka kelulusan atau persentase keberhasilan yang tetap; hasil aktual diperoleh dengan menjalankan kedua perintah verifikasi tersebut pada repositori.
