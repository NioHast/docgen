# Contoh AutoOffice

Tiga contoh single-file di direktori ini memakai format `undip-msi` dan
struktur yang berbeda. Setiap contoh berdiri sendiri: front matter, naskah,
gambar, dan `references.bib` berada dalam satu direktori.

## Matriks fitur

| Fitur | `assignment-single` | `thesis-single` | `proposal-single` |
| --- | --- | --- | --- |
| Struktur | `assignment` | `thesis` | `proposal` |
| Format | `undip-msi` | `undip-msi` | `undip-msi` |
| Bab body | 3 | 5 | 4 |
| Front matter dari dokumen | - | kata pengantar, abstrak ID/EN | - |
| Tabel | 1 | 2 | 1 |
| Gambar biasa | - | 1 | - |
| Diagram Mermaid | 1 | 1 | - |
| Persamaan display | - | 1 | - |
| Blok kode | - | 1 | - |
| Sitasi BibTeX | 2 kunci | 5 kunci | 5 kunci |
| Daftar isi | tidak | ya | ya |
| Daftar gambar/tabel | tidak | ya | tidak |
| Lampiran | - | 1 | - |

Daftar isi dan daftar gambar/tabel diaktifkan oleh `structure.yml`, bukan oleh
kunci front matter `document.md`. Jangan menulis `toc`, `daftar_gambar`, atau
`daftar_tabel` di contoh.

## Check

Jalankan pemeriksaan konfigurasi tanpa membangun DOCX:

```bash
uv run --project <repo> autooffice check examples/assignment-single/document.md
uv run --project <repo> autooffice check examples/thesis-single/document.md
uv run --project <repo> autooffice check examples/proposal-single/document.md
```

`check` memvalidasi front matter, format, struktur, aset, urutan Heading 1, dan
caption Markdown. Perintah ini tidak memanggil Pandoc atau Word.

## Build

Build DOCX:

```bash
uv run --project <repo> autooffice build examples/thesis-single/document.md --target docx
```

Di Windows dengan Microsoft Word terpasang, `--target all` juga menghasilkan
PDF. Di Debian atau lingkungan tanpa Word, gunakan `--target docx`.

```bash
uv run --project <repo> autooffice build examples/thesis-single/document.md --target all
```

## Artefak

Untuk dokumen di `examples/<name>/document.md`, output ditulis ke
`examples/<name>/out/`:

```text
examples/thesis-single/
|-- document.md
|-- references.bib
|-- gambar/
|-- out/
|   |-- Tugas.docx
|   `-- Tugas.pdf
|-- .laporan/
|   `-- manifest.json
`-- .laporan-build/      # hanya dengan --keep-intermediate
```

`out/`, `.laporan/`, dan `.laporan-build/` di-ignore Git. Nama berkas
mengikuti `report_name` yang wajib ditulis eksplisit di front matter; tidak
ada nama default. DOCX dan PDF memakai stem yang sama. Tidak ada output di
`build/` atau `review/`.

## Catatan

- `assignment-single` adalah contoh ringkas tiga bab dengan satu tabel dan
  satu diagram Mermaid.
- `thesis-single` adalah contoh terlengkap: front matter tesis, lima bab, dua
  tabel, gambar biasa, Mermaid, persamaan, blok kode, sitasi, dan lampiran.
- `proposal-single` adalah contoh empat bab dengan daftar isi dan satu tabel.

Rincian format ada di
[docs/user/document-format.md](../docs/user/document-format.md). Rincian
perintah ada di [docs/user/quickstart.md](../docs/user/quickstart.md).
