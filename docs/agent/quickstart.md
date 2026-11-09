# Quickstart

Panduan singkat dari naskah kosong sampai DOCX. Semua perintah `docgen`
memakai bentuk berikut dari direktori mana pun:

```bash
uv run --project <repo> docgen <perintah> ...
```

Ganti `<repo>` dengan path absolut repo ini. Jika sudah berada di akar repo,
bentuk yang setara adalah `uv run --project . docgen <perintah> ...`.

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
wajib adalah `title`, `author`, `structure`, dan `format`.

```yaml
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
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
uv run --project <repo> docgen check document.md
```

`check` memvalidasi front matter, keberadaan format dan struktur, template,
bibliografi, gambar, urutan Heading 1, dan caption Markdown. Perintah ini tidak
memanggil Pandoc atau Word dan tidak menulis berkas.

Pemeriksa prosa terpisah dan hanya memberi petunjuk:

```bash
uv run --project <repo> docgen doctor
uv run --project <repo> python tools/dev/check_prose.py document.md
```

## 5. Build

Bangun DOCX:

```bash
uv run --project <repo> docgen build document.md --target docx
```

Di Windows dengan Microsoft Word terpasang, bangun DOCX dan PDF:

```bash
uv run --project <repo> docgen build document.md --target both
```

Di Debian atau lingkungan tanpa Word, `--target both` berhenti dengan error
kecuali memakai `--allow-missing-word`. Opsi itu menghasilkan DOCX dan
melewati PDF dengan peringatan. Untuk pekerjaan normal di Debian, gunakan
`--target docx`.

Tambahkan `--keep` bila workspace `.laporan-build/` perlu diperiksa setelah
build. Tambahkan `--terms` bila ingin mengaktifkan gate glosarium.

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
`-- .laporan-build/      # hanya dengan --keep
```

Nama berkas mengikuti `report_name` di front matter. Default-nya `Tugas`.
Manifest berisi bookmark `pNNNN` untuk rekonsiliasi edit Word.

## 7. Rekonsiliasi edit Word

Bila DOCX disunting manual, bandingkan dengan manifest:

```bash
uv run --project <repo> docgen reconcile document.md
```

Laporan ditulis ke `.laporan/reconcile.md`. Alat ini tidak mengubah DOCX,
manifest, atau `document.md`. Terapkan perubahan ke Markdown secara manual,
lalu build ulang. Jangan menjadikan DOCX sebagai sumber.

## Contoh

- [assignment-single](../../examples/assignment-single/document.md): tiga bab,
  satu tabel, satu diagram Mermaid.
- [proposal-single](../../examples/proposal-single/document.md): empat bab,
  satu tabel, daftar isi.
- [thesis-single](../../examples/thesis-single/document.md): lima bab, front
  matter lengkap, gambar, Mermaid, persamaan, kode, dan lampiran.

Lanjutkan ke [writing-rules.md](writing-rules.md) sebelum menulis naskah
panjang. Bila ada kegagalan, lihat [troubleshooting.md](troubleshooting.md).
