# Kontrak Ownership

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 14 (14.1-14.2), 13.2, dan 15.6.
Pemilik kontrak: integration owner.

## Tujuan

Kontrak ini membekukan peta lane dan kepemilikan file. Satu file atau glob
hanya boleh punya satu owner aktif. Lane tidak boleh menulis area lane lain,
termasuk untuk memperbaiki konflik.

## Peta lane dan ownership

| Owner/lane | Path atau glob | Fase | Catatan |
| --- | --- | --- | --- |
| integration owner | `pyproject.toml`, `uv.lock`, `src/autooffice/__init__.py`, `src/autooffice/__main__.py`, `src/autooffice/cli/**`, `src/autooffice/common/**`, `src/autooffice/errors.py`, `src/autooffice/deck/blocks/registry.py`, `src/autooffice/deck/layout/registry.py`, `src/autooffice/deck/render/protocol.py`, `docs/contracts/README.md`, `docs/contracts/cli.md`, `docs/contracts/coverage.md`, `docs/decisions/**`, `docs/README.md`, `docs/user/cli.md`, `docs/dev/**`, `tests/acceptance/**`, `README.md`, `AGENTS.md` | 0-3 | Entry point, CLI, registry, dependency, acceptance, docs developer, dan navigasi. `.github/workflows/**` dihapus. `render/protocol.py` diserahkan ke PPTX owner setelah F1-PPTX. |
| design owner | `src/autooffice/design/**`, `src/autooffice/assets/fonts/**`, `tests/design/**`, `docs/contracts/design-token.md` | 1-3 | Token, theme, font, lisensi, dan kontrak token setelah F1-DESIGN. |
| DOCX owner | `src/autooffice/docx/**`, `tests/docx/**`, `examples/docx/**`, `docs/contracts/docx.md` | 1-3 | Migrasi docgen, contoh lama, dan kontrak DOCX setelah F1-DOCX. |
| model owner | `src/autooffice/deck/model/**`, `src/autooffice/deck/blocks/**` kecuali `registry.py`, `tests/deck/model/**`, `docs/contracts/deck-schema.md`, `docs/contracts/key-grammar.md`, `docs/contracts/deck-ir.md`, `docs/contracts/block-spec.md` | 1-3 | Schema, compiler, key, IR, block spec, dan registry block setelah F1-MODEL. |
| layout owner | `src/autooffice/deck/layout/**` kecuali `presets/`, `custom.py`, dan `registry.py`, `tests/deck/layout/**`, `docs/contracts/layout-spec.md` | 1-2 | Grid, measure, rows, overflow, discovery preset, dan kontrak layout setelah F1-LAYOUT. |
| custom grid owner | `src/autooffice/deck/layout/custom.py` dan test uniknya | 2 | Custom composition level 2. |
| layout lane owners | `src/autooffice/deck/layout/presets/*.py`, test dan golden unik per layout | 2 | Satu owner per file preset. |
| charts owner | `src/autooffice/deck/charts/**`, `src/autooffice/deck/render/pptx/chart.py`, `tests/deck/charts/**`, `docs/contracts/chart-contract.md` | 2-3 | Transfer ownership chart dan kontrak chart setelah F2-CHARTS. |
| copy owner | `src/autooffice/deck/copy/**`, `src/autooffice/deck/transcript/**`, `tests/deck/copy/**`, `tests/fixtures/copy/**`, `docs/contracts/copy.md`, `docs/contracts/transcript.md` | 1-3 | Rule copy, config, parser transkrip, dan kontraknya. |
| PPTX owner | `src/autooffice/deck/render/pptx/**` kecuali `chart.py`, `tests/deck/render/pptx/**`, `docs/contracts/pptx-renderer.md` | 1-3 | Primitives, coverage, dan kontrak PPTX setelah F1-PPTX; protokol renderer diambil alih setelah handoff. |
| Google owner | `src/autooffice/google/**`, `tests/google/**`, `docs/contracts/google-state.md` | 2-3 | Satu owner untuk seluruh Google dan kontrak state setelah F2-GOOGLE. |
| PDF owner | `src/autooffice/pdf/**`, `tests/pdf/**` | 2-3 | COM dan lock global. Tidak ada kontrak PDF aktif di F0. |
| demo deck owner | `examples/demo-deck/**` termasuk `transcripts.md` dan `copy.yaml`, `tests/fixtures/demo/**` | 2-3 | Demo acceptance. |
| test infrastructure owner | `tests/conftest.py`, `tests/fixtures/**`, `tests/contract/**` bersama integration, `tests/golden/**` bersama integration, `tools/quality/**`, `tools/dev/check_docs.py`, `docs/dev/**` bersama integration | 1-3 | Fixture shared, gate, docs developer, dan kontrak test setelah F1-TEST. |
| docs owner | `docs/user/**` kecuali `docs/user/cli.md`, `docs/learn/**` | 2-3 | Dokumentasi pengguna dan konsep. |

## Kepemilikan kontrak F0

Seluruh berkas `docs/contracts/**` dimiliki integration owner pada F0. Lane
terkait mengambil alih setelah deliverable dan acceptance-nya lulus. Sebelum
handoff, perubahan diajukan ke integration owner, bukan diedit langsung.

| Berkas kontrak | Owner F0 | Handoff |
| --- | --- | --- |
| `README.md` | integration owner | integration owner |
| `deck-schema.md` | integration owner | model owner, F1-MODEL |
| `key-grammar.md` | integration owner | model owner, F1-MODEL |
| `deck-ir.md` | integration owner | model owner, F1-MODEL |
| `block-spec.md` | integration owner | model owner, F1-MODEL |
| `layout-spec.md` | integration owner | layout owner, F1-LAYOUT |
| `pptx-renderer.md` | integration owner | PPTX owner, F1-PPTX |
| `chart-contract.md` | integration owner | charts owner, F2-CHARTS |
| `copy.md` | integration owner | copy owner, F1-COPY |
| `transcript.md` | integration owner | copy owner, F1-COPY |
| `google-state.md` | integration owner | Google owner, F2-GOOGLE |
| `cli.md` | integration owner | integration owner |
| `coverage.md` | integration owner | integration owner |
| `design-token.md` | integration owner | design owner, F1-DESIGN |
| `docx.md` | integration owner | DOCX owner, F1-DOCX |
| `documentation.md` | integration owner | integration owner dan docs owner |
| `ownership.md` | integration owner | integration owner |
| `test-quality.md` | integration owner | test infrastructure owner, F1-TEST |

## Handoff berkas non-kontrak F0

Integration owner memiliki berkas berikut pada F0. Setelah lane domain lulus
acceptance, kepemilikan diserahkan sesuai tabel di bawah dan peta lane di atas;
tidak ada berkas tanpa owner.

| Berkas atau glob | Owner F0 | Handoff |
| --- | --- | --- |
| `src/autooffice/deck/model/deck_ir.py` | integration owner | model owner, F1-MODEL |
| `src/autooffice/deck/blocks/spec.py` | integration owner | model owner, F1-MODEL |
| `src/autooffice/deck/layout/spec.py` | integration owner | layout owner, F1-LAYOUT |
| `src/autooffice/design/theme.py` | integration owner | design owner, F1-DESIGN |
| `src/autooffice/deck/render/protocol.py` | integration owner | PPTX owner, F1-PPTX |
| `src/autooffice/**/__init__.py` | integration owner | owner domain per package, F1/F2; `src/autooffice/__init__.py` tetap integration owner |
| `tools/quality/check_no_legacy.py` | integration owner | test infrastructure owner, F1-TEST |
| `docs/learn/README.md` | integration owner | docs owner, F2-DOCS |
| `AGENTS.md` | integration owner | integration owner, tetap |
| `AUTO_OFFICE_EXECUTION_LOG.md` | integration owner | integration owner, tetap |
| `.gitignore` | integration owner | integration owner, tetap |

Marker package mengikuti owner domain direktori induknya; root
`src/autooffice/__init__.py` tetap integration owner.

## Invarian anti-konflik

1. Satu file hanya satu owner aktif. Satu glob hanya satu owner aktif.
2. Integration owner satu-satunya yang boleh mengedit file shared.
3. Layout lane hanya menambah file preset dan test unik. Custom grid lane
   hanya menambah `custom.py` dan test unik. Tidak ada layout lane yang
   mengedit registry.
4. Registry layout F0 adalah daftar statis. Discovery preset deterministik
   adalah deliverable F1-LAYOUT; sampai itu ada, menambah preset memerlukan
   integration owner mengubah `src/autooffice/deck/layout/registry.py`.
5. Block registry tetap untuk 11 block type. Block type baru memerlukan ADR.
6. `pyproject.toml` dan `uv.lock` tidak boleh diedit lane. Dependency request
   ditulis di lane card dan dieksekusi integration owner.
7. Tidak ada katalog layout generated terpisah di F0; daftar layout F0 adalah
   registry statis dan katalog plan bagian 6.2.
8. File golden existing hanya diperbarui golden owner dengan flag update
   eksplisit. Lane boleh menambah golden baru di path unik miliknya.
9. File fixture existing tidak boleh diedit lane. Lane boleh menambah file
   baru dengan nama unik.
10. Lane tidak boleh mengedit test lane lain. Perubahan diajukan ke owner.
11. Dua branch yang menyentuh file yang sama tidak boleh di-merge tanpa
    integration step.
12. Konflik merge dianggap pelanggaran ownership. Pekerjaan dihentikan, file
    dipetakan ulang, lalu dijadwalkan serial.
13. Lane yang blocked tetap memegang lock hanya bila pekerjaan aktif. Lane
    yang parkir harus melepas slot.
14. Tidak ada workaround lintas lane untuk menghindari kontrak.
15. Setelah F0, perubahan kontrak memerlukan ADR. Menambah field, layout,
    block, atau perilaku renderer tanpa ADR adalah pelanggaran kontrak.

## Contoh

Lane layout data menambah preset baru tanpa menyentuh registry:

```text
+ src/autooffice/deck/layout/presets/data.py
+ tests/deck/layout/test_layout_data.py
+ tests/golden/layout/data.yaml
! src/autooffice/deck/layout/registry.py  (integration owner)
```

Discovery preset F1-LAYOUT menemukan file baru. Sampai discovery itu ada,
lane mengajukan perubahan registry ke integration owner.

## Pemetaan acceptance

| Invarian | Bukti |
| --- | --- |
| Satu owner per file | Review peta lane; `tools/quality/check_no_legacy.py` F3. |
| Shared file tidak diedit lane | Review diff; integration owner merge. |
| Registry statis dan discovery | Contract test registry F0; discovery F1-LAYOUT. |
| Golden dan fixture | Review golden flag; bagian 14.2. |
| Konflik merge | Merge protocol bagian 15.6; integration gate. |
| Kontrak beku | ADR di `docs/decisions/**`; review F0. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
