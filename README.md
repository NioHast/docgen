# docgen

`docgen` adalah pipeline dokumen akademik berbasis Markdown untuk format
Universitas Diponegoro, Magister Sistem Informasi. Satu berkas `document.md`
menjadi sumber kebenaran. Pipeline memvalidasi konfigurasi, memanggil Pandoc,
lalu merapikan DOCX melalui tahap Python yang berurutan. PDF dibuat dari DOCX
final menggunakan Microsoft Word di Windows.

Repo ini menyediakan tiga struktur siap pakai: `assignment`, `proposal`, dan
`thesis`. Semua memakai format `undip-msi`. Aturan visual berada di
`src/docgen/data/formats/undip-msi/format.yml`, sedangkan urutan bab dan
front matter berada di `src/docgen/data/structures/<id>/structure.yml`.

## Prasyarat

- **Python 3.15** dan **uv**. `uv run --project <repo>` membaca `pyproject.toml`
  dan menyiapkan environment proyek.
- **Pandoc** dengan `--citeproc` untuk konversi Markdown ke DOCX.
- **Microsoft Word desktop** di Windows untuk finalisasi field dan ekspor PDF.
  Word Online tidak menyediakan COM.
- **Mermaid CLI (`mmdc`)** bila dokumen memakai blok Mermaid. Pasang Node.js
  lalu jalankan `npm install -g @mermaid-js/mermaid-cli`.
- **Debian/Linux**: DOCX dapat dibangun selama Python dan Pandoc tersedia.
  PDF tidak didukung karena ekspor PDF hanya memakai Word.

Jalankan `uv sync --extra dev` sekali dari akar repo. Perintah
`uv run --project <repo> docgen ...` dapat dipanggil dari direktori mana pun;
ganti `<repo>` dengan path absolut repo ini. Perintah `doctor` memeriksa Python,
Pandoc, Word, dan `mmdc`, lalu memberi exit code 1 bila dependensi wajib
belum lengkap.

## Quickstart

1. Pilih struktur lewat front matter: `assignment`, `proposal`, atau `thesis`.
2. Tulis `document.md` dengan front matter YAML dan body Markdown.
3. Letakkan gambar di `gambar/`, bibliografi di `references.bib`, dan glosarium
   tambahan di `istilah.tsv` bila diperlukan.
4. Jalankan `check`, lalu `build`.

```yaml
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
report_name: "Tugas"
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

```bash
uv run --project <repo> docgen check document.md
uv run --project <repo> docgen build document.md --target docx
```

Di Windows dengan Word terpasang, `--target both` menghasilkan DOCX dan PDF.
Di Debian, gunakan `--target docx`.

## Perintah

| Perintah | Kegunaan |
| --- | --- |
| `uv run --project <repo> docgen check <document.md>` | Memvalidasi front matter, format, struktur, aset, urutan Heading 1, dan caption Markdown. Tidak memanggil Pandoc atau Word. |
| `uv run --project <repo> docgen build <document.md> --target docx` | Membangun DOCX. Word tidak wajib. |
| `uv run --project <repo> docgen build <document.md> --target both` | Membangun DOCX dan PDF. Hanya Windows dengan Word. |
| `uv run --project <repo> docgen doctor` | Memeriksa Python, Pandoc, Word, dan `mmdc`. |
| `uv run --project <repo> docgen reconcile <document.md>` | Membandingkan DOCX hasil edit dengan manifest dan menulis laporan tinjauan. |

Flag build yang tersedia: `--target docx|pdf|both`, `--keep`, `--terms`,
`--no-manifest`, `--no-adeu`, dan `--allow-missing-word`. Build hanya memakai
pipeline Python; tidak ada jalur shell atau fallback lama.

## Output

Untuk dokumen pengguna, output ditulis di direktori yang sama dengan
`document.md`:

| Artefak | Lokasi | Keterangan |
| --- | --- | --- |
| `<report_name>.docx` | samping `document.md` | `report_name` wajib di front matter; tidak ada default; tidak ada flag CLI. |
| `<report_name>.pdf` | samping `document.md` | Hanya Windows dengan Word. |
| `.laporan/manifest.json` | samping `document.md` | Bookmark `pNNNN` dan manifest Adeu. |
| `.laporan/istilah-baru.txt` | samping `document.md` | Hanya dengan `--terms`. |
| `.laporan-build/` | samping `document.md` | Workspace sementara; hanya disimpan dengan `--keep`. |

Untuk dokumen di `examples/<name>/document.md`, output ditulis ke
`examples/<name>/out/`. Tidak ada output di `build/` atau `review/`.

## Peta repo

| Path | Isi |
| --- | --- |
| `src/docgen/` | CLI, loader konfigurasi, pipeline, stage, dan API DOCX. |
| `src/docgen/data/` | Format, struktur, template, glosarium, logo, CSL, dan `reference.docx` sumber. |
| `examples/` | Tiga contoh single-file: `assignment-single`, `proposal-single`, dan `thesis-single`. |
| `docs/` | Indeks, panduan agent, dokumen pengembang, kontrak, dan ADR. |
| `tools/dev/` | Pemeriksa prosa dan audit istilah untuk pengembang. |
| `tests/` | Unit, integrasi, end-to-end, packaging, dan fixture golden. |
| `scripts/word.ps1` | Adaptor Word untuk finalisasi field dan ekspor PDF. |

Detail arsitektur ada di [docs/dev/architecture.md](docs/dev/architecture.md).
Panduan penulis ada di [docs/agent/quickstart.md](docs/agent/quickstart.md). Indeks lengkap ada di [docs/README.md](docs/README.md).

## Contoh

| Contoh | Struktur | Isi utama |
| --- | --- | --- |
| [`examples/assignment-single`](examples/assignment-single/) | `assignment` | Tiga bab, satu tabel, satu diagram Mermaid. |
| [`examples/proposal-single`](examples/proposal-single/) | `proposal` | Empat bab, satu tabel, daftar isi. |
| [`examples/thesis-single`](examples/thesis-single/) | `thesis` | Lima bab, front matter lengkap, gambar, Mermaid, persamaan, kode, dan lampiran. |

```bash
uv run --project <repo> docgen check examples/thesis-single/document.md
uv run --project <repo> docgen build examples/thesis-single/document.md --target docx
```

Hasil contoh ditulis ke `examples/thesis-single/out/Tugas.docx` dan manifest
ke `examples/thesis-single/.laporan/manifest.json`. Keduanya di-ignore Git.
Rincian ada di [examples/README.md](examples/README.md).

## Batasan

- PDF hanya didukung di Windows dengan Microsoft Word desktop. Debian hanya
  menghasilkan DOCX best-effort; field TOC dan nomor halaman belum difinalkan
  tanpa Word.
- TOC dan daftar tabel/gambar memakai field native yang perlu diperbarui Word.
  Di Windows tahap `office` melakukan pembaruan itu.
- Caption tabel wajib berupa baris `: Judul tabel`; gambar wajib memiliki alt
  text. Sumber kebenaran adalah Markdown, bukan DOCX atau PDF hasil build.
- Tidak ada perintah pembuat proyek dan mode folder lama. Salin salah satu
  contoh, lalu sesuaikan front matter dan isinya.

## Lisensi

MIT. Komponen pemeriksa prosa di `tools/dev/check_prose.py` berasal dari
proyek naskah-id (MIT, Copyright (c) 2026 nothinx). Teks lisensi lengkap ada di
[`LICENSE`](LICENSE).
