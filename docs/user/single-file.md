# Alur Satu Berkas

`autooffice` memakai satu berkas Markdown sebagai sumber: `document.md`.
Berkas itu memuat YAML front matter dan seluruh body. Tidak ada direktori `chapters/`,
tidak ada `manifest.yml`, dan tidak ada perintah `build-file` terpisah.
Perintah `check` dan `build` menerima path `document.md` secara langsung.

Alur ini cocok untuk tugas, proposal, dan tesis yang ditulis sebagai satu
naskah. Urutan bab tetap ditentukan struktur, bukan urutan berkas.

## Bentuk direktori

```text
laporan/
|-- document.md
|-- references.bib
|-- istilah.tsv          # opsional
`-- gambar/
    |-- diagram.png
    `-- mermaid-<hash>.png
```

Semua path di `document.md` relatif terhadap direktori berkas itu. Jangan
memakai path absolut atau `..`.

## Front matter

Front matter wajib di awal berkas:

```yaml
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
structure: assignment
format: undip-msi
bibliography: references.bib
report_name: "Tugas"
---

# Pendahuluan

Naskah dimulai di sini.
```

Kunci `title`, `author`, `report_name`, `structure`, dan `format` wajib.
`bibliography` wajib ada karena ketiga struktur memiliki daftar pustaka. Nilai
default-nya `references.bib`, tetapi berkasnya tetap harus tersedia.

## Body dan bab

Setiap Heading 1 adalah satu bab. Jumlah dan urutannya harus sama dengan
`body` pada `structure.yml`:

- `assignment`: Pendahuluan, Pembahasan, Penutup.
- `proposal`: Pendahuluan, Tinjauan Pustaka, Metode Penelitian, Jadwal
  Penelitian.
- `thesis`: Pendahuluan, Tinjauan Pustaka, Metodologi, Hasil dan Pembahasan,
  Penutup.

Jangan menulis nomor bab manual. Pipeline menambahkan nomor sesuai
`numbering.body`. Heading 2 dan Heading 3 boleh berbeda antar dokumen selama
tidak melompati level.

## Aset

| Aset | Aturan |
| --- | --- |
| Gambar | Letakkan di `gambar/`, rujuk dengan path relatif, dan beri alt text non-kosong. |
| Bibliografi | Berkas `.bib` di direktori dokumen atau subdirektori, dirujuk lewat `bibliography`. |
| Glosarium | `istilah.tsv` di samping `document.md` menimpa dan menambah glosarium paket. |
| Mermaid | Tulis blok `{.mermaid caption="..."}`; PNG dibuat saat build. |

`check` memastikan gambar dan bibliografi yang dirujuk ada. Berkas gambar di
luar direktori dokumen ditolak.

## Perintah

```bash
uv run --project <repo> autooffice check document.md
uv run --project <repo> autooffice build document.md --target docx
uv run --project <repo> autooffice build document.md --target all
```

`--target all` menghasilkan DOCX dan PDF, dan membutuhkan Microsoft Word di
Windows. Di Debian gunakan `--target docx`; target PDF memerlukan Word COM dan
tidak memiliki fallback diam-diam.

## Output

```text
laporan/
|-- Tugas.docx
|-- Tugas.pdf            # hanya Windows dengan Word
|-- .laporan/
|   |-- manifest.json
|   `-- istilah-baru.txt # hanya dengan --terms
`-- .laporan-build/      # hanya dengan --keep-intermediate
```

Nama berkas mengikuti `report_name` yang wajib diisi; DOCX dan PDF memakai
stem yang sama. Tidak ada nama default. Output ditulis di samping
`document.md`; tidak ada direktori `build/` atau `review/`.

## Batasan

- Tidak ada pemecahan bab ke berkas terpisah.
- Tidak ada perintah `new` atau `list`; salin contoh atau buat berkas sendiri.
- DOCX bukan sumber. Edit `document.md`, lalu build ulang.
- PDF hanya di Windows dengan Word. Debian menghasilkan DOCX best-effort.
