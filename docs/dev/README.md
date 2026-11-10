# Dokumentasi Developer

Halaman ini adalah pintu masuk dokumentasi developer. Mulai dari
[arsitektur](architecture.md), lalu pilih area yang sedang diubah. Indeks
dokumentasi pengguna dan developer ada di [docs/README.md](../README.md).

## Belajar

Materi belajar berlapis untuk programmer pemula sampai kontributor ada di
[learn/README.md](learn/README.md). Mulai dari
[00 - Mulai di Sini](learn/00-start-here.md) jika baru mengenal repo, atau
pilih jalur baca yang sesuai di indeks materi belajar.

## Orientasi

| Dokumen | Isi |
| --- | --- |
| [architecture.md](architecture.md) | Lapisan konten, struktur, format, pipeline, dan invariant utama. |
| [repo-map.md](repo-map.md) | Peta direktori dan tanggung jawab berkas. |
| [glossary.md](glossary.md) | Istilah codebase: artefak, package, part, manifest, dan sejenisnya. |
| [refactor-plan.md](archive/refactor-plan.md) | Rencana refactor aktif dan keputusan kerja. |

## Pipeline

| Dokumen | Isi |
| --- | --- |
| [pipeline/README.md](pipeline/README.md) | Indeks dokumentasi pipeline. |
| [pipeline/overview.md](pipeline/overview.md) | Model eksekusi, satu load/save, Adeu hook, idempotensi, logging. |
| [pipeline/stages.md](pipeline/stages.md) | Urutan 18 stage dan guard. |
| [pipeline/options.md](pipeline/options.md) | Flag build dan matriks target. |
| [pipeline/outputs.md](pipeline/outputs.md) | `report_name` dan artefak pengguna. |
| [pipeline/artifacts.md](pipeline/artifacts.md) | Workspace dan artefak antara. |
| [pipeline/errors.md](pipeline/errors.md) | Error pipeline dan exit code. |

## DOCX

| Dokumen | Isi |
| --- | --- |
| [docx/README.md](docx/README.md) | Indeks dokumentasi lapisan DOCX. |
| [docx/overview.md](docx/overview.md) | Posisi lapisan dan peta modul. |
| [docx/package.md](docx/package.md) | `DocumentPackage`, part, dan idempotensi. |
| [docx/styles.md](docx/styles.md) | Style inti dan `reference.docx`. |
| [docx/paragraphs.md](docx/paragraphs.md) | Helper paragraf. |
| [docx/runs.md](docx/runs.md) | Helper run. |
| [docx/numbering.md](docx/numbering.md) | Angka Romawi, nomor bab, dan heading numbering. |
| [docx/page.md](docx/page.md) | Ukuran halaman dan `content_width`. |
| [docx/sections.md](docx/sections.md) | Section, header, dan footer. |
| [docx/fields.md](docx/fields.md) | Field TOC, SEQ, PAGE, dan sejenisnya. |
| [docx/bookmarks.md](docx/bookmarks.md) | Bookmark dan manifest. |
| [docx/captions.md](docx/captions.md) | Caption dan tabel. |
| [docx/layout.md](docx/layout.md) | Layout paragraf. |
| [docx/terms.md](docx/terms.md) | Glosarium, penanda istilah, verifikasi, dan audit. |

## Kontrak

| Dokumen | Isi |
| --- | --- |
| [contracts/config.md](contracts/config.md) | Kontrak `format.yml`, `structure.yml`, dan front matter. |
| [contracts/docx-api.md](contracts/docx-api.md) | Kontrak API `src/docgen/docx/`. |
| [contracts/stage-api.md](contracts/stage-api.md) | Kontrak stage, urutan, error, output, dan CLI. |

## Fitur dan operasi

| Dokumen | Isi |
| --- | --- |
| [formats.md](formats.md) | Skema format dan struktur yang tersedia. |
| [adeu-integration.md](adeu-integration.md) | Bookmark, manifest, source scan, dan reconcile. |
| [pdf.md](pdf.md) | Ekspor PDF Word-only dan batas Debian. |
| [packaging.md](packaging.md) | Entry point, package data, dan pemakaian repo-local. |

## Kerja dan verifikasi

| Dokumen | Isi |
| --- | --- |
| [contributing.md](contributing.md) | Alur kontribusi, tes, dan aturan perubahan. |
| [testing.md](testing.md) | Golden invariant dan cara menjalankan tes. |
| [code-style.md](code-style.md) | Konfigurasi Ruff, mypy, dan tabel rule. |
| [references.md](references.md) | Registry resmi label dan URL dokumentasi eksternal. |

## Keputusan dan arsip

| Dokumen | Isi |
| --- | --- |
| [decisions/](decisions/) | Delapan ADR keputusan arsitektur. |
| [archive/](archive/) | Rencana historis yang sudah superseded. |

ADR yang tersedia:

- [0001-single-file.md](decisions/0001-single-file.md)
- [0002-pandoc.md](decisions/0002-pandoc.md)
- [0003-python-orchestrator.md](decisions/0003-python-orchestrator.md)
- [0004-format-vs-structure.md](decisions/0004-format-vs-structure.md)
- [0005-one-docx-pass.md](decisions/0005-one-docx-pass.md)
- [0006-docx-lua-parity.md](decisions/0006-docx-lua-parity.md)
- [0007-seq-hybrid.md](decisions/0007-seq-hybrid.md)
- [0008-refactor-boundaries.md](decisions/0008-refactor-boundaries.md)
