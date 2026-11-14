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
| [architecture.md](architecture.md) | Lapisan konten, struktur, format, pipeline DOCX/deck, dan invariant utama. |
| [repo-map.md](repo-map.md) | Peta direktori dan tanggung jawab berkas. |
| [glossary.md](glossary.md) | Istilah codebase: artefak, package, part, manifest, dan sejenisnya. |
| [refactor-plan.md](archive/refactor-plan.md) | Rencana refactor (arsip) dan keputusan kerja. |

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
| [../contracts/docx.md](../contracts/docx.md) | Kontrak DOCX: API `build_docx`, stage, invariant parity, dan output. |
| [../contracts/cli.md](../contracts/cli.md) | Permukaan CLI, matriks target, output, flag, dan exit code. |
| [../contracts/pdf.md](../contracts/pdf.md) | Word/PowerPoint COM, ekspor PDF, timeout, cleanup, dan embedding font. |
| [../contracts/documentation.md](../contracts/documentation.md) | Struktur dokumentasi, TOC, tautan, dan aturan isi. |

Kontrak internal lama di `contracts/` hanya dipertahankan untuk transisi F3 dan
tidak menjadi acuan aktif:
[config.md](contracts/config.md), [docx-api.md](contracts/docx-api.md), dan
[stage-api.md](contracts/stage-api.md).

## Fitur dan operasi

| Dokumen | Isi |
| --- | --- |
| [formats.md](formats.md) | Skema format dan struktur yang tersedia. |
| [adeu-integration.md](adeu-integration.md) | Adeu (MCP eksternal DOCX↔LLM): bookmark `pNNNN`, manifest, source scan, dan modul rekonsiliasi internal. |
| [pdf.md](pdf.md) | Ekspor PDF lewat Word/PowerPoint, embedding font, dan batas platform. |
| [com.md](com.md) | Guard COM Word/PowerPoint, watchdog, PID, lock, dan cleanup proses. |
| [security.md](security.md) | Batas keamanan resource input tidak tepercaya: ZIP DOCX/PPTX, parser XML, dan `deck.yaml`. |
| [packaging.md](packaging.md) | Entry point, package data, dan pemakaian repo-local. |

## Kerja dan verifikasi

| Dokumen | Isi |
| --- | --- |
| [contributing.md](contributing.md) | Alur kontribusi, tes, dan aturan perubahan. |
| [testing.md](testing.md) | Golden invariant dan cara menjalankan tes. |
| [performance.md](performance.md) | Tes performa deck besar, marker `slow`, dan batas waktu. |
| [visual-testing.md](visual-testing.md) | Smoke harness render PPTX ke PNG lewat PowerPoint COM. |
| [quality-gates.md](quality-gates.md) | Gate lokal AutoOffice, checker, dan urutan verifikasi. |
| [f3-cleanup.md](f3-cleanup.md) | Runbook F3 untuk parity baseline, penghapusan legacy, gate, dan rollback. |
| [test-quality.md](test-quality.md) | Prinsip memilih kasus test dan hasil audit suite. |
| [mutation-testing.md](mutation-testing.md) | Mutation testing manual modul kritis: tool, scope, perintah, runtime, dan survivor. |
| [code-style.md](code-style.md) | Konfigurasi Ruff, mypy, dan tabel rule. |
| [python-315-style.md](python-315-style.md) | Anotasi lazy PEP 649/749, fitur 3.13 sampai 3.15, API deprecated, dan checker gaya. |
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
