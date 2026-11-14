# Indeks Kontrak AutoOffice F0

Direktori ini memuat kontrak normatif yang dibekukan pada Fase 0. Setiap lane
fitur membaca kontrak ini sebelum menulis kode, dan tidak boleh menambah field,
tipe block, layout, atau perilaku renderer tanpa ADR. Kontrak di sini mengatur
bentuk data dan invariant; detail implementasi tetap milik kode.

Status: F0 contract, version 1
Sumber: AUTO_OFFICE_PLAN.md bagian 13.2 (F0-CONTRACTS) dan 3.2 sampai 3.5.

## Daftar kontrak

| Berkas | Cakupan | Bagian plan |
| --- | --- | --- |
| [deck-schema.md](deck-schema.md) | Bentuk `deck.yaml`, meta, slide, block, path, teks. | 4 |
| [key-grammar.md](key-grammar.md) | Key datar, ID stabil, indeks 1-based, KeyBinding. | 5 |
| [deck-ir.md](deck-ir.md) | DeckIR, SlideIR, BlockIR, KeyManifest, immutability. | 3.4, 5.1, 8.1 |
| [layout-spec.md](layout-spec.md) | Grid 12 kolom, rows, span, overflow, LayoutPlan. | 6, 7 |
| [block-spec.md](block-spec.md) | 11 block type, field wajib, table dan chart native. | 4.7, 4.8, 4.14 |
| [pptx-renderer.md](pptx-renderer.md) | Renderer python-pptx, font, alt, key, larangan. | 8.1, 8.3 |
| [chart-contract.md](chart-contract.md) | Chart native, linked Sheets, placeholder, preflight. | 8.3, 8.4, 9.1 sampai 9.5 |
| [mermaid.md](mermaid.md) | Render `mmdc` ke PNG, cache, path, dan integrasi PPTX. | 4.8, 8.6, 18.7 |
| [copy.md](copy.md) | Copy checker, rule, severity, allowlist. | 4.16, 8.7, 12.13 |
| [transcript.md](transcript.md) | Transcript parser, output, dan validasi. | 4.15, 8.7, 12.13 |
| [google-state.md](google-state.md) | State Google, ownership, dan kegagalan. | 9 |
| [cli.md](cli.md) | Permukaan CLI, target matrix, output, exit code. | 10 |
| [coverage.md](coverage.md) | Coverage, exclusion, dan report. | 12.3, 12.11 |
| [design-token.md](design-token.md) | Token, theme, font, dan kontras. | 11 |
| [docx.md](docx.md) | DOCX API dan parity baseline DOCX. | 8.2 |
| [pdf.md](pdf.md) | Word COM, ekspor PDF, timeout, dan cleanup. | 8.5, F2-PDF |
| [documentation.md](documentation.md) | Gate dokumentasi dan TOC. | 12.9 |
| [ownership.md](ownership.md) | File ownership dan lane map. | 14, 15.6 |
| [test-quality.md](test-quality.md) | Test quality, golden, dan visual. | 12.1, 12.2, 12.10 |

## Invariant

- Kontrak bersifat normatif untuk F0 dan menjadi rujukan lane fitur.
- Perubahan schema setelah F0 wajib ADR di `docs/decisions/`.
- Prosa memakai bahasa Indonesia; identifier dan nama field memakai bahasa Inggris.
- Satu berkas kontrak maksimal 150 baris, atau wajib punya `## Daftar Isi` yang valid.
- Setiap kontrak memuat status, sumber plan, bentuk data/berkas/state, invariant, contoh, dan acceptance.
- Tautan relatif harus resolve dan diperiksa dengan `python tools/quality/check_docs.py`.
- Tidak ada kode produksi di direktori ini.
- Kontrak tidak menggantikan plan; plan tetap sumber keputusan dan asumsi.

## Bentuk data

```text
deck-schema.md
key-grammar.md
deck-ir.md
layout-spec.md
block-spec.md
pptx-renderer.md
chart-contract.md
mermaid.md
copy.md
transcript.md
google-state.md
cli.md
coverage.md
design-token.md
docx.md
pdf.md
documentation.md
ownership.md
test-quality.md
```

## Acceptance

| Gate | Bukti |
| --- | --- |
| Docs | `python tools/quality/check_docs.py` keluar 0 untuk `docs/contracts/**`. |
| Versi | Setiap kontrak memuat `Status: F0 contract, version 1`. |
| Sumber | Setiap kontrak menyebut bagian `AUTO_OFFICE_PLAN.md`. |
| Contoh | Setiap kontrak punya minimal satu contoh yang sesuai bentuknya: YAML, JSON, dataclass, perintah, tree, report, atau state. |
| Invariant | Setiap kontrak punya daftar invariant eksplisit. |
| Tautan | Tautan balik ke plan dan tautan antar kontrak resolve. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
