# Indeks Dokumentasi

Dokumentasi dipisahkan menurut pembaca. Mulai dari [README utama](../README.md)
bila baru mengenal repo, lalu pilih salah satu pintu berikut:

- **Pengguna dan penulis**: menulis `document.md` atau `deck.yaml`, memilih
  struktur atau layout, dan membangun DOCX/PDF atau PPTX/Slides.
- **Developer**: memahami arsitektur, pipeline, lapisan DOCX, dan kontrak.
- **Referensi**: kontrak, glosarium, registry resmi, ADR, dan arsip.

## Untuk pengguna dan penulis

| Dokumen | Isi |
| --- | --- |
| [user/README.md](user/README.md) | Indeks panduan pengguna dan penulis. |
| [user/quickstart.md](user/quickstart.md) | Langkah awal DOCX dan deck: struktur atau layout, check, build, dan output. |
| [user/cli.md](user/cli.md) | Perintah `autooffice`, target, output, flag, dan kode keluar. |
| [user/deck-authoring.md](user/deck-authoring.md) | Authoring `deck.yaml`: meta, 19 layout preset, custom rows, block, aset, transkrip, copy, dan build. |
| [user/document-format.md](user/document-format.md) | Front matter, heading, caption, gambar, tabel, kode, persamaan, dan sitasi. |
| [user/single-file.md](user/single-file.md) | Alur satu berkas `document.md` dan asetnya. |
| [user/mermaid.md](user/mermaid.md) | Diagram Mermaid, caption wajib, dan `mmdc`. |
| [user/writing-rules.md](user/writing-rules.md) | Aturan prosa, istilah, sitasi, dan perintah pemeriksa. |
| [user/troubleshooting.md](user/troubleshooting.md) | Masalah umum caption, Mermaid, Pandoc, Word, dan path. |

## Untuk developer

| Dokumen | Isi |
| --- | --- |
| [dev/README.md](dev/README.md) | Indeks lengkap dokumentasi developer. |
| [dev/architecture.md](dev/architecture.md) | Lapisan konten, struktur, format, pipeline DOCX/deck, dan invariant. |
| [dev/pipeline/README.md](dev/pipeline/README.md) | Urutan stage, opsi build, output, artefak, dan error. |
| [dev/docx/README.md](dev/docx/README.md) | Model package DOCX, modul internal, field, bookmark, dan istilah. |
| [dev/formats.md](dev/formats.md) | Skema `format.yml`, `structure.yml`, dan struktur yang tersedia. |
| [dev/docx/terms.md](dev/docx/terms.md) | Glosarium, penanda istilah, stage `terms`, dan verifikasi. |
| [dev/pdf.md](dev/pdf.md) | Ekspor PDF lewat Word/PowerPoint, embedding font, dan batas platform. |
| [dev/adeu-integration.md](dev/adeu-integration.md) | Adeu (MCP DOCX↔LLM): bookmark `pNNNN`, manifest, source scan, dan modul rekonsiliasi internal. |
| [dev/packaging.md](dev/packaging.md) | Entry point, package data, dan pemakaian repo-local. |
| [dev/repo-map.md](dev/repo-map.md) | Peta direktori dan tanggung jawab berkas. |
| [dev/contributing.md](dev/contributing.md) | Alur kontribusi, tes, dan aturan perubahan. |
| [dev/com.md](dev/com.md) | Guard COM Word/PowerPoint, watchdog, PID, lock, dan cleanup proses. |
| [dev/security.md](dev/security.md) | Batas keamanan resource input tidak tepercaya. |
| [dev/f3-cleanup.md](dev/f3-cleanup.md) | Status pembersihan legacy F3, verifikasi, dan tautan ke ADR 0011. |
| [dev/testing.md](dev/testing.md) | Golden invariant dan cara menjalankan tes. |
| [dev/quality-gates.md](dev/quality-gates.md) | Gate lokal AutoOffice, checker, dan urutan verifikasi. |
| [dev/test-quality.md](dev/test-quality.md) | Prinsip memilih kasus test dan hasil audit suite. |
| [dev/code-style.md](dev/code-style.md) | Konfigurasi Ruff, mypy, dan tabel rule. |
| [dev/python-315-style.md](dev/python-315-style.md) | Anotasi lazy PEP 649/749, fitur Python 3.13 sampai 3.15, API deprecated, dan checker gaya. |

## Konsep deck

| Dokumen | Isi |
| --- | --- |
| [learn/README.md](learn/README.md) | Indeks materi belajar AutoOffice. |
| [learn/deck-pipeline.md](learn/deck-pipeline.md) | Alur YAML sampai PPTX/Slides, DeckIR, key, copy checker, dan invariant. |
| [learn/layout-system.md](learn/layout-system.md) | Grid 12 kolom, preset vs custom, span slot, `min_one_of`, overflow, dan larangan absolute. |
| [learn/design-system.md](learn/design-system.md) | Token, theme, font, dan kontras. |
| [learn/humanizer.md](learn/humanizer.md) | Copy checker dan batas editorial. |

## AutoOffice

Kontrak normatif ada di [contracts/README.md](contracts/README.md) dan
keputusan ada di [decisions/README.md](decisions/README.md). Materi konsep
bertahap ada di [learn/README.md](learn/README.md). Riwayat pembersihan
legacy ada di [dev/f3-cleanup.md](dev/f3-cleanup.md) dan
[decisions/0011-f3-cleanup.md](decisions/0011-f3-cleanup.md). Dokumen
[AUTO_OFFICE_PLAN.md](../AUTO_OFFICE_PLAN.md) adalah rencana migrasi dan
bukan dokumentasi pengguna.

## Referensi

| Dokumen | Isi |
| --- | --- |
| [dev/glossary.md](dev/glossary.md) | Istilah codebase: artefak, package, part, manifest, dan sejenisnya. |
| [dev/references.md](dev/references.md) | Registry resmi label dan URL dokumentasi eksternal. |
| [contracts/docx.md](contracts/docx.md) | Kontrak DOCX: API `build_docx`, stage, invariant, dan output. |
| [contracts/cli.md](contracts/cli.md) | Permukaan CLI, target, output, flag, dan exit code. |
| [contracts/pdf.md](contracts/pdf.md) | Word/PowerPoint COM, ekspor PDF, dan embedding font. |
| [dev/archive/refactor-plan.md](dev/archive/refactor-plan.md) | Rencana refactor (arsip) dan keputusan kerja. |
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
