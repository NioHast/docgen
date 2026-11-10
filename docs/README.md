# Indeks Dokumentasi

Dokumentasi dipisahkan menurut pembaca. Mulai dari [README utama](../README.md)
bila baru mengenal repo, lalu pilih salah satu pintu berikut:

- **Pengguna dan penulis**: menulis `document.md`, memilih struktur, dan
  membangun DOCX/PDF.
- **Developer**: memahami arsitektur, pipeline, lapisan DOCX, dan kontrak.
- **Referensi**: kontrak, glosarium, registry resmi, ADR, dan arsip.

## Untuk pengguna dan penulis

| Dokumen | Isi |
| --- | --- |
| [agent/quickstart.md](agent/quickstart.md) | Langkah awal memilih struktur, check, build, dan output. |
| [agent/document-format.md](agent/document-format.md) | Front matter, heading, caption, gambar, tabel, kode, persamaan, dan sitasi. |
| [agent/single-file.md](agent/single-file.md) | Alur satu berkas `document.md` dan asetnya. |
| [agent/mermaid.md](agent/mermaid.md) | Diagram Mermaid, caption wajib, dan `mmdc`. |
| [agent/writing-rules.md](agent/writing-rules.md) | Aturan prosa, istilah, sitasi, dan perintah pemeriksa. |
| [agent/troubleshooting.md](agent/troubleshooting.md) | Masalah umum caption, Mermaid, Pandoc, Word, dan path. |

## Untuk developer

| Dokumen | Isi |
| --- | --- |
| [dev/README.md](dev/README.md) | Indeks lengkap dokumentasi developer. |
| [dev/architecture.md](dev/architecture.md) | Lapisan konten, struktur, format, dan pipeline. |
| [dev/pipeline/README.md](dev/pipeline/README.md) | Urutan stage, opsi build, output, artefak, dan error. |
| [dev/docx/README.md](dev/docx/README.md) | Model package DOCX, modul internal, field, bookmark, dan istilah. |
| [dev/formats.md](dev/formats.md) | Skema `format.yml`, `structure.yml`, dan struktur yang tersedia. |
| [dev/docx/terms.md](dev/docx/terms.md) | Glosarium, penanda istilah, stage `terms`, dan audit. |
| [dev/pdf.md](dev/pdf.md) | Ekspor PDF Word-only dan batas Debian. |
| [dev/adeu-integration.md](dev/adeu-integration.md) | Bookmark `pNNNN`, manifest, source scan, dan reconcile. |
| [dev/packaging.md](dev/packaging.md) | Entry point, package data, dan pemakaian repo-local. |
| [dev/repo-map.md](dev/repo-map.md) | Peta direktori dan tanggung jawab berkas. |
| [dev/contributing.md](dev/contributing.md) | Alur kontribusi, tes, dan aturan perubahan. |
| [dev/testing.md](dev/testing.md) | Golden invariant dan cara menjalankan tes. |
| [dev/code-style.md](dev/code-style.md) | Konfigurasi Ruff, mypy, dan tabel rule. |

## Referensi

| Dokumen | Isi |
| --- | --- |
| [dev/glossary.md](dev/glossary.md) | Istilah codebase: artefak, package, part, manifest, dan sejenisnya. |
| [dev/references.md](dev/references.md) | Registry resmi label dan URL dokumentasi eksternal. |
| [dev/contracts/config.md](dev/contracts/config.md) | Kontrak `format.yml`, `structure.yml`, dan front matter. |
| [dev/contracts/docx-api.md](dev/contracts/docx-api.md) | Kontrak API `src/docgen/docx/`. |
| [dev/contracts/stage-api.md](dev/contracts/stage-api.md) | Kontrak stage, urutan, error, output, dan CLI. |
| [dev/refactor-plan.md](dev/refactor-plan.md) | Rencana refactor aktif dan keputusan kerja. |
| [dev/archive/restructure-plan.md](dev/archive/restructure-plan.md) | Arsip rencana restrukturisasi (superseded). |
| [dev/archive/duplication-map.md](dev/archive/duplication-map.md) | Arsip peta duplikasi DOCX (superseded). |

## Architecture Decision Record

| ADR | Keputusan |
| --- | --- |
| [0001](dev/decisions/0001-single-file.md) | Satu `document.md` sebagai sumber. |
| [0002](dev/decisions/0002-pandoc.md) | Pandoc sebagai konverter Markdown ke DOCX. |
| [0003](dev/decisions/0003-python-orchestrator.md) | Orkestrasi pipeline di Python. |
| [0004](dev/decisions/0004-format-vs-structure.md) | Pemisahan format dan struktur. |
| [0005](dev/decisions/0005-one-docx-pass.md) | Satu load dan satu save package DOCX. |
| [0006](dev/decisions/0006-docx-lua-parity.md) | Paritas perilaku filter Lua lama. |
| [0007](dev/decisions/0007-seq-hybrid.md) | Hybrid `SEQ` untuk daftar tabel dan gambar. |
| [0008](dev/decisions/0008-refactor-boundaries.md) | Batas refactor dan keputusan yang mengikat. |
