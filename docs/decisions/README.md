# Indeks Architecture Decision Record

Status: F0 index, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 19.2 dan 13.2.

ADR mencatat keputusan yang mengikat kontrak. ADR yang sudah diterima tidak
diedit diam-diam; perubahan dilakukan dengan ADR baru yang menandai ADR lama
sebagai `superseded`. Perubahan schema, layout, block, atau perilaku renderer
setelah F0 wajib memiliki ADR.

## Daftar ADR

| ADR | Keputusan | Status |
| --- | --- | --- |
| [0001-assumption-closure.md](0001-assumption-closure.md) | Penutupan asumsi A1-A25 untuk kelulusan F0. | diterima |
| [0002-scope-and-package.md](0002-scope-and-package.md) | Satu proyek, satu package Python, satu CLI, dan penghapusan repo lama. | diterima |
| [0003-deck-model-and-keys.md](0003-deck-model-and-keys.md) | Satu YAML per deck, ID stabil, flat key, dan 11 block type. | diterima |
| [0004-layouts-and-rendering.md](0004-layouts-and-rendering.md) | Katalog layout, grid, design token, PPTX native, dan font. | diterima |
| [0005-google-sheets-and-pdf.md](0005-google-sheets-and-pdf.md) | Linked Sheets chart, state Google, preflight table, dan PDF COM. | diterima |
| [0006-quality-migration-and-humanizer.md](0006-quality-migration-and-humanizer.md) | Gate lokal, copy checker deterministik, transkrip, dan migrasi. | diterima |
| [0007-slot-span.md](0007-slot-span.md) | Span per slot preset untuk layout asimetris, terpisah dari span custom. | diterima |
| [0008-min-one-of.md](0008-min-one-of.md) | Grup slot minimal satu untuk alternatif seperti toc group1-3 dan kpi kpi1-4. | diterima |
| [0009-explicit-custom-rows.md](0009-explicit-custom-rows.md) | Rows custom eksplisit di `SlideIR`; compiler mengisi, planner memakai. | diterima |
| [0010-risk-based-coverage.md](0010-risk-based-coverage.md) | Coverage global 90%, modul kritis 100%, adapter 85%; checker dan gate. | diterima |
| [0011-f3-cleanup.md](0011-f3-cleanup.md) | Daftar hapus/update F3, inventaris referensi legacy, urutan operasi, dan rollback. | diterima |
| [0012-chart-kind-preset.md](0012-chart-kind-preset.md) | `SlotSpec.chart_kind` mengikat kind chart pada slot preset `bars`, `line`, dan `donut`. | diterima |

## Aturan ADR

1. ADR wajib memuat konteks, keputusan, konsekuensi, alternatif, dan status.
2. ADR menyebut keputusan terkunci L01-L25 yang relevan.
3. ADR tidak menggantikan plan; plan tetap sumber keputusan produk.
4. Kontrak yang berubah wajib menautkan ADR yang mengubahnya.
5. ADR yang tidak lagi berlaku ditandai `superseded` dan menautkan pengganti.
6. ADR disimpan di `docs/decisions` dan terdaftar di halaman ini.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
