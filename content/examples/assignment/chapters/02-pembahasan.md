# Pembahasan

## Lapisan Format

Format menyimpan aturan visual yang tidak bergantung pada isi, misalnya margin, tipografi, dan gaya sitasi. Pada contoh ini format `undip-msi` memakai preset `undip-msi-proposal`, CSL `refs/undip-msi.csl`, dan bibliografi `references.bib`.

## Lapisan Struktur

Struktur menentukan urutan bagian. Struktur `assignment` memakai penomoran Arab bertitik dengan tiga bab:

| Urutan | Berkas | Peran |
| --- | --- | --- |
| 1 | `chapters/01-pendahuluan.md` | Pendahuluan |
| 2 | `chapters/02-pembahasan.md` | Pembahasan |
| 3 | `chapters/03-penutup.md` | Penutup |

Struktur tidak menyimpan teks naskah. Dengan begitu, struktur yang sama dapat dipakai banyak proyek konten.

## Lapisan Konten dan Platform

Konten berisi metadata, bab Markdown, gambar, dan bibliografi. Platform menyediakan perintah `list`, `new`, `check`, `build`, dan `doctor`. Perintah `build` hanya memanggil `build-docx.sh` atau `build.sh`; logika DOCX dan PDF tidak diduplikasi.

Pandoc menangani konversi dokumen [@pandoc2024], sedangkan Typst dipakai pipeline PDF [@typst2024]. Keduanya menerima sumber Markdown yang sama sehingga isi laporan tidak perlu ditulis dua kali.
