# RESTRUCTURE_PLAN - design-system-format-laporan menjadi docgen

**Versi:** 0.13
**Status:** implemented dengan deviasi terdokumentasi. WS1-WS15 selesai per 2026-11-09.
**Repo:** `C:\dev\apps\design-system-format-laporan`
**Commit baseline:** `06bda0b`
**Sifat:** rencana yang sudah diimplementasikan; deviasi dicatat di bagian Implementation status.

## Implementation status

WS1-WS15 selesai. Artefak generated lama dibersihkan; `uv.lock` dan dokumen ini di-track.

- **Deviasi LOC WS4:** target 1.840-2.180 baris fisik (1.700-1.900 baris kode); aktual 3.375 baris fisik di `docx/captions.py`, `docx/tables.py`, `stages/captions.py`, `stages/code.py`, dan `stages/validate.py`. Kelebihan diterima karena helper caption/tabel dipisah dari stage dan karakterisasi golden XML.
- **Deviasi LOC WS10:** target 1.000-1.130 LOC dengan parser/model/CLI bersama (770-880 tanpa source matching); aktual 2.920 baris fisik di `features/adeu/**`, `docx/bookmarks.py`, dan `markdown/blocks.py`. Kelebihan diterima karena pemisahan manifest, paragraph ID, dan reconcile.
- **Stage/modul baru:** `stages/front_matter.py` (FrontMatterStage, urutan 35) sudah masuk target tree v0.13; `MermaidStage` berada di `stages/mermaid.py`; `docx/headings.py` menangani penomoran heading Markdown; helper bersama `docx/bookmarks.py` (bookmark Adeu) dan `markdown/blocks.py` (parser blok bersama) juga ada di target tree.
- **Deviasi kontrak:** `docgen new` dan `src/docgen/docx/cli.py` belum diimplementasikan dan ditandai `future, not implemented` di kontrak. Flag transisi CLI sudah dihapus setelah cutover. `Stage` Protocol belum ada; implementasi memakai `BaseStage`. Registry konsumen `CFG-DEAD-KEY` beserta tesnya belum ada.
- **`acuan/`:** tetap berada di disk dan di-ignore `.gitignore`; tidak direferensikan oleh kode, build, contoh, atau dokumentasi pengguna. Plan ini hanya mencatat statusnya.
- **Catatan historis:** penyebutan `src/laporan`, shell build, dan `docx.lua` di bagian historis plan ini adalah catatan audit, bukan path atau artefak aktif.

## Changelog

| Versi | Tanggal | Perubahan |
|---|---|---|
| 0.13 | 2026-11-09 | Menambahkan `front_matter` ke urutan kanonik dan target tree; menambahkan `tools/dev/rules.yml`, `docs/dev/adeu-integration.md`, `docs/dev/contributing.md`, `docs/dev/decisions/0007-seq-hybrid.md`; mencatat `acuan/` tetap ignored; memperbarui status implementasi dan deviasi LOC |
| 0.12 | 2026-11-09 | Menambahkan skipif golden PDF, perintah full test Debian tanpa marker windows, dan klarifikasi ownership style_reference |
| 0.11 | 2026-11-09 | Memperbaiki aktor removal stub style_reference, qualifier Windows golden PDF, acceptance P0.1, dan intermediate DOCX hanya untuk --keep |
| 0.10 | 2026-11-09 | Memperbaiki cleanup tool/PS lama, ownership tes lengkap, stub style_reference, dependency WS14, golden PDF, fast gate, lifecycle --keep, validator template, dan tes CLI |
| 0.9 | 2026-11-09 | Memperbaiki pipeline style_reference, code-table, cleanup repo lama, handoff pyproject, ownership tes, acceptance Windows-only, dan risiko v0.8 |
| 0.8 | 2026-11-09 | Memperbaiki ownership, kompatibilitas fase 1, acceptance, urutan stage, paritas docx.lua, tree, CLI, SEQ gate, byte identity, Word-only, dan temuan audit yang hilang |
| 0.7 | 2026-11-09 | Menambahkan lane 2; semua 12 audit selesai; memperbarui WS4, risiko, status audit |
| 0.6 | 2026-11-09 | Menambahkan lane 5; memperbarui WS3, WS10, risiko, status audit |
| 0.5 | 2026-11-09 | Menambahkan lane 8; memperbarui WS3, WS6, WS7, WS10, WS12, risiko, status audit |
| 0.4 | 2026-11-09 | Menambahkan lane 12; memperbarui WS12, target tes, risiko false-green, status audit |
| 0.3 | 2026-11-09 | Menambahkan lane 4, 9, 11; memperbarui WS6, WS7, WS11, risiko, status audit |
| 0.2 | 2026-11-09 | Menambahkan temuan lane 1, 3, 6, 7, 10; menandai lane 2, 4, 5, 8, 9, 11, 12 sebagai pending |
| 0.1 | 2026-11-09 | Draft awal berdasarkan audit lintas area |

## 0. Tujuan dan batas

### Tujuan

- Satu input: `document.md`.
- Satu orchestrator: Python (`docgen`).
- Satu DOCX load/save, bukan 10 rewrite.
- Dua lapis konfigurasi: `formats/` untuk rupa, `structures/` untuk urutan/sumber/teks legal.
- Repo-local: `uv run --project <repo> docgen build <file>`.
- Output DOCX+PDF di samping `document.md`.
- Repo bersih: tanpa `build/`, `review/`, `presets/`, `metadata.yml`, `cover.md`, `docx.lua`, shell build, DOTX, lampiran.

### Di luar scope

- Folder mode.
- Typst.
- DOTX.
- Lampiran.
- `docx-pagenum` (dihapus; Word mengisi TOC).
- Penggantian Pandoc dengan Typst.
- Standalone wheel (repo-local dulu).

## 1. Keputusan yang sudah terkunci

| Area | Keputusan |
|---|---|
| Package/CLI | `docgen` |
| Input | `document.md` |
| Struktur | thesis + proposal + assignment |
| Output | DOCX + PDF |
| PDF | Word saja |
| Debian | best-effort hanya build DOCX; PDF tidak didukung di Debian |
| DOCX pass | satu |
| `docx.lua` | port penuh termasuk bug fix; ADR 0006 |
| Adeu | dipertahankan, manifest default, `--no-manifest` opt-out |
| Daftar gambar/tabel | `SEQ` dengan decision gate WS11 |
| Urutan stage | kontrak P0.2 dan WS15 |
| Byte identity | part non-target byte-identik; `document.xml` c14n+sha256; idempotensi dua run |
| Gate istilah | `--terms` default off |
| DOTX | hapus |
| `docx-pagenum` | hapus |
| `reference.docx` | source asset; derived reference di cache/temp |
| Glosarium | package default + user override `istilah.tsv` |
| Format source | `format.yml` |
| `preset:` | error setelah migrasi |
| Examples | `examples/<name>/out/` |
| Fixtures DOCX | di-commit |
| Lisensi | MIT |
| `acuan/` | tetap di disk, ignored, tidak direferensikan |
| Makefile | hapus di WS15 |
| Shims | dokumentasi, bukan repo |
| Python | 3.15 konsisten |
| Git history | best practice, review jika repo dibagikan |

## 2. Target arsitektur

### 2.1 Struktur repo

```text
.
├── README.md
├── AGENTS.md
├── LICENSE
├── .gitattributes
├── pyproject.toml
├── uv.lock
├── docs/
│   ├── README.md
│   ├── agent/
│   │   ├── quickstart.md
│   │   ├── document-format.md
│   │   ├── single-file.md
│   │   ├── mermaid.md
│   │   ├── writing-rules.md
│   │   └── troubleshooting.md
│   └── dev/
│       ├── architecture.md
│       ├── pipeline.md
│       ├── docx.md
│       ├── formats.md
│       ├── terms.md
│       ├── pdf.md
│       ├── testing.md
│       ├── packaging.md
│       ├── adeu-integration.md
│       ├── contributing.md
│       ├── repo-map.md
│       ├── restructure-plan.md
│       ├── duplication-map.md
│       ├── contracts/
│       │   ├── config.md
│       │   ├── docx-api.md
│       │   └── stage-api.md
│       └── decisions/
│           ├── 0001-single-file.md
│           ├── 0002-pandoc.md
│           ├── 0003-python-orchestrator.md
│           ├── 0004-format-vs-structure.md
│           ├── 0005-one-docx-pass.md
│           ├── 0006-docx-lua-parity.md
│           └── 0007-seq-hybrid.md
├── examples/
│   ├── assignment-single/
│   │   ├── document.md
│   │   ├── references.bib
│   │   ├── gambar/
│   │   └── out/            # ignored
│   ├── thesis-single/
│   └── proposal-single/
├── src/docgen/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── document.py
│   ├── metadata.py
│   ├── assets.py
│   ├── errors.py
│   ├── paths.py
│   ├── pipeline.py
│   ├── stages/
│   │   ├── validate.py
│   │   ├── mermaid.py
│   │   ├── style_reference.py
│   │   ├── front_matter.py
│   │   ├── pandoc.py
│   │   ├── sections.py
│   │   ├── code.py
│   │   ├── captions.py
│   │   ├── normalize.py
│   │   ├── equations.py
│   │   ├── numbering.py
│   │   ├── blank_lines.py
│   │   ├── terms.py
│   │   ├── toc.py
│   │   ├── page_numbers.py
│   │   ├── lists.py
│   │   ├── office.py
│   │   └── pdf.py
│   ├── docx/
│   │   ├── package.py
│   │   ├── io.py
│   │   ├── xml.py
│   │   ├── names.py
│   │   ├── cli.py         # future, not implemented
│   │   ├── styles.py
│   │   ├── sections.py
│   │   ├── captions.py
│   │   ├── tables.py
│   │   ├── layout.py
│   │   ├── fields.py
│   │   ├── headings.py
│   │   ├── bookmarks.py
│   │   └── terms.py
│   ├── markdown/
│   │   └── blocks.py
│   ├── features/
│   │   └── adeu/
│   │       ├── manifest.py
│   │       ├── paragraph_ids.py
│   │       ├── reconcile.py
│   │       └── cli.py
│   └── data/
│       ├── formats/undip-msi/
│       │   ├── format.yml
│       │   ├── logo.jpg
│       │   ├── reference.docx
│       │   └── citation.csl
│       ├── structures/
│       │   ├── thesis/structure.yml + templates/
│       │   ├── proposal/structure.yml + templates/
│       │   └── assignment/structure.yml + templates/
│       └── glossary/istilah.tsv
├── resources/
│   └── word.ps1
├── tools/
│   └── dev/
│       ├── check_prose.py
│       ├── audit_terms.py
│       └── rules.yml
└── tests/
    ├── _helpers/
    ├── factories/
    ├── unit/
    ├── integration/
    ├── packaging/
    ├── e2e/
    └── fixtures/
```

### 2.2 Pipeline

```text
document.md
  -> config          baca front matter + format + structure
  -> validate        field wajib, aset, caption
  -> mermaid         opsional
  -> style_reference derived reference dari format.yml
  -> front_matter    cover, template legal, abstrak, penomoran heading
  -> pandoc          Markdown -> DOCX
  -> postprocess     satu load: sections -> code -> captions/figures
                     -> normalize -> equations -> numbering -> blank_lines
                     -> terms -> toc -> page_numbers -> lists; satu save
  -> office          update field/TOC via Word
  -> DOCX
  -> PDF             via Word
```

### 2.3 Dua lapis konfigurasi

| Lapis | Isi | Contoh |
|---|---|---|
| Format | Rupa dan aset | margin, font, spacing, caption, code, CSL, logo, `reference.docx` |
| Structure | Urutan, sumber, teks legal | front matter, chapter order, TOC, daftar gambar/tabel, approval/statement |
| Document | Isi | title, author, NIM, abstrak ID/EN, Kata Pengantar, bab, gambar, `.bib` |

Abstract dan preface adalah isi, jadi berada di `document.md`. Structure hanya menentukan posisi dan sumber. Template legal (approval, statement) berada di `structures/<id>/templates/`.

### 2.4 CLI

```text
docgen new <dir>          # future, not implemented
docgen check <file>
docgen build <file> --target docx|pdf|both --terms --no-manifest --no-adeu --allow-missing-word --keep
docgen doctor
docgen reconcile <file>
```

Default `--target both`. `--target both` hanya dijalankan di Windows; di Debian gunakan `--target docx`. `--terms` default off; flag ini mengaktifkan apply + verify + gate istilah.

### 2.5 Output

- User task: `Tugas.docx` dan `Tugas.pdf` di samping `document.md`.
- Contoh repo: `examples/<name>/out/` dan di-ignore.
- Manifest Adeu: `.laporan/manifest.json` di samping dokumen, default aktif, `--no-manifest` opt-out.
- Workspace dimiliki WS2 `pipeline.py`; dibuat hanya jika diperlukan (Mermaid/intermediate) dan dibersihkan secara default.
- Jalur normal hanya satu DOCX pass; intermediate DOCX hanya dibuat/disimpan saat `--keep`.
- `--keep`: mencegah cleanup dan menyimpan `.laporan-build/` serta file intermediate DOCX untuk debugging; default false. Output tetap di samping `document.md`.

## 3. Prinsip eksekusi paralel

1. Satu pemilik per file. Tidak ada dua workstream mengedit file yang sama.
2. Kontrak dibekukan sebelum paralel: `docx/` API, stage API, config schema, CLI.
3. `docx/` adalah fondasi WS3. Setelah fondasi selesai, API fondasi dibekukan; helper domain dimiliki lane masing-masing.
4. Stage lane bekerja dengan fixture DOCX. Tidak perlu pipeline lengkap.
5. `pipeline.py` dimiliki WS2 di Fase 1 dan di-handoff ke WS15 di Fase 3. `config.py`, `document.py` hanya diedit WS2.
6. YAML hanya diedit WS1.
7. Tes per lane. `tests/_helpers`, `tests/factories`, `tests/packaging`, `tests/integration` dimiliki WS12.
8. Integrasi hanya di WS15. Tidak ada lane yang mengubah urutan stage; kontrak urutan ada di P0.2 dan WS15.
9. Barrier hanya di Fase 0, Fase 3, dan Fase 5. Fase 1 dan 2 rolling.
10. Semua audit selesai. Lane mulai setelah kontrak dan blocker review ditutup.

## 4. Workstream dan ownership

| WS | Nama | File utama | Dependensi | Output |
|---|---|---|---|---|
| WS0 | Baseline dan kontrak | tests golden, docs contracts | - | Invariant + API |
| WS1 | Config dan data | `src/docgen/data/**` | WS0 | format/structure baru |
| WS2 | Core package | `cli/config/document/metadata/assets/errors/paths/pipeline`, `stages/pandoc.py` | WS0, WS14 Phase 1 pyproject | CLI + loader; `pipeline.py` Fase 1 |
| WS3 | DOCX core | `docx/package.py`, `io.py`, `xml.py`, `names.py`, `cli.py` | WS0 | API fondasi DOCX |
| WS4 | Captions/figures/code | `stages/validate.py`, `captions.py`, `code.py`, `docx/captions.py`, `tables.py` | WS3 | 3 stage |
| WS5 | Equations/numbering/layout | `stages/equations.py`, `numbering.py`, `normalize.py`, `blank_lines.py`, `docx/layout.py` | WS3 | 4 stage |
| WS6 | Sections/TOC/page numbers | `stages/sections.py`, `toc.py`, `page_numbers.py`, `docx/sections.py`, `fields.py` | WS3, lane 9 (selesai) | 4 stage |
| WS7 | Terms/style/reference | `stages/terms.py`, `style_reference.py`, `docx/styles.py`, `terms.py` | WS3, lane 4/11 (selesai) | 2 stage |
| WS8 | Office/PDF | `stages/office.py`, `pdf.py`, `resources/word.ps1` | WS2 | Word adapter; Word-only |
| WS9 | Mermaid | `stages/mermaid.py` | WS2 | render inline |
| WS10 | Adeu | `features/adeu/**`, `docx/bookmarks.py`, `markdown/blocks.py` | WS2, WS3, lane 5 (selesai) | manifest + reconcile |
| WS11 | Daftar gambar/tabel | `stages/lists.py` | WS4, WS6, spike SEQ | list fields |
| WS12 | Tests/packaging | `tests/_helpers/**`, `tests/factories/**`, `tests/packaging/**`, `tests/e2e/**`, harness `tests/integration/` | semua, kontinu; final setelah WS15 | shared harness + handoff |
| WS13 | Docs/examples | `docs/**`, `examples/**`, README, AGENTS | WS0 skeleton; WS15 final | dokumentasi |
| WS14 | Hygiene | `.gitignore`, `.gitattributes`, LICENSE, pyproject, artifacts | - | repo bersih; pyproject handoff; plan tracked |
| WS15 | Integrasi/cutover | `pipeline.py` | semua | DOCX/PDF parity; pipeline handoff |

### Batas ownership

| Objek | Pemilik | Aturan |
|---|---|---|
| `docx/package.py`, `io.py`, `xml.py`, `names.py`, `cli.py` | WS3 | hanya fondasi; bukan seluruh `docx/**` |
| `docx/captions.py`, `docx/tables.py` | WS4 | helper domain caption dan tabel |
| `docx/layout.py` | WS5 | helper layout |
| `docx/sections.py`, `docx/fields.py` | WS6 | helper section dan field |
| `docx/styles.py`, `docx/terms.py` | WS7 | helper style dan terms |
| `docx/bookmarks.py` | WS10 | helper bookmark Adeu |
| `src/docgen/cli.py` | WS2 | WS6 menyediakan fungsi command; WS2 mendaftarkan |
| `pipeline.py` | WS2 Fase 1; WS15 Fase 3 | handoff eksplisit, tanpa editor lain |
| Tes domain per lane | lane masing-masing | WS12 membuat daftar handoff; lane pemilik mengeksekusi |
| `tests/_helpers`, `tests/factories`, `tests/packaging`, `tests/e2e`, harness `tests/integration` | WS12 | shared infrastructure; tidak mengedit/menghapus tes domain |

### Pemilik tes domain

| Tes | Pemilik |
|---|---|
| `test_format_figures`, `test_format_code`, `test_check_captions` | WS4 |
| `test_format_equations`, `test_format_numbering`, `test_insert_blank_lines`, `test_normalize_layout` | WS5 |
| `test_pagenumber`, `test_toc_gating`, `test_heading_numbering`, `test_docx_lua_escaping` | WS6 |
| `test_terms`, `test_audit_terms`, `test_build_style` | WS7 |
| `test_citation_style`, `test_integration_terms` | WS7 |
| `test_export_pdf` | WS8 |
| `test_platform_native` | WS2 |
| `test_mermaid` | WS9 |
| `test_paragraph_ids`, `test_reconcile` | WS10 |
| `test_golden_docx`, `test_golden_pdf` | WS12 |
| `test_check_prose`, `test_check_prose_docx` | WS14 |
| `test_export_dotx` | WS14 |
| `test_modular_cli`, `test_singlefile`, `test_cli` | WS2 |

Satu file tes hanya boleh punya satu pemilik. Tidak ada entri dua pemilik.

Catatan: tabel di atas memakai nama tes baseline audit pra-port. Tes aktual
setelah restrukturisasi berada di `tests/unit/`, `tests/integration/`,
`tests/e2e/`, dan `tests/packaging/`; nama final dan acceptance per kontrak
ada di `docs/dev/contracts/stage-api.md` dan `docx-api.md`.

## 5. Fase 0 - Baseline dan kontrak (barrier)

### P0.1 Bekukan invariant

Langkah:

1. Build DOCX/PDF dari kondisi sekarang.
2. Simpan salinan ke folder temp, bukan repo.
3. Catat invariant: jumlah field TOC, `w:sdt`, caption, border tabel kode, halaman PDF, entri TOC kunci, style TOC1/2/3.
4. Catat part non-target byte-identik, `document.xml` semantic-equivalent via canonical XML c14n + sha256, dan idempotensi dua run.
5. Tulis `tests/integration/test_golden_docx.py` dan `test_golden_pdf.py` bersama WS12; WS12 menjadi owner setelah handoff. `test_golden_pdf.py` wajib memakai `pytest.mark.skipif(sys.platform != "win32", reason="Word-only")` atau module-level skip setara.

Acceptance:

- `uv run --project <repo> pytest tests/integration/test_golden_docx.py` lulus pada output lama.
- Windows: `test_golden_pdf.py` lulus dengan marker `windows`.
- Linux/Debian: `test_golden_pdf.py` tidak dikoleksi/dijalankan via `skipif`, bukan hanya marker; golden PDF manual/not gate.
- Invariant terdokumentasi di `docs/dev/testing.md`.

### P0.2 Bekukan kontrak

Tulis:

- `docs/dev/contracts/config.md`: skema `format.yml`, `structure.yml`, `document.md`.
- `docs/dev/contracts/docx-api.md`: fungsi fondasi dan helper domain `docx/`.
- `docs/dev/contracts/stage-api.md`: `Stage.run(ctx)`, urutan, error, idempotensi.

Urutan stage kanonik dibekukan di kontrak:

```text
validate
-> mermaid
-> style_reference
-> front_matter
-> pandoc
-> sections
-> code
-> captions/figures
-> normalize
-> equations
-> numbering
-> blank_lines
-> terms
-> toc
-> page_numbers
-> lists
-> office
-> pdf
```

Acceptance: tiga kontrak dan urutan stage kanonik disetujui sebelum WS3/WS4 mulai.

### P0.3 Baseline audit

- Catat status lane: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 selesai.
- Setiap lane yang selesai menambah baris di changelog plan.

## 6. Fase 1 - Fondasi paralel

### WS1 - Config dan data

Langkah:

1. Salin `formats/` ke `src/docgen/data/formats/`.
2. Gabung `presets/undip-skripsi.yml` dan `presets/undip-msi-proposal.yml` ke `format.yml`.
3. Salin perbedaan proposal ke `structure.yml`.
4. Buat `structures/thesis`, `proposal`, `assignment` dengan `structure.yml`.
5. Buat template legal di `structures/<id>/templates/`.
6. Salin `citation.csl`, `logo.jpg`, `reference.docx` ke `formats/undip-msi/`.
7. Tulis `front_matter` di `structure.yml`.
8. Buat tes schema.

Format `front_matter`:

```yaml
front_matter:
  - { id: approval, source: template, template: approval.md }
  - { id: statement, source: template, template: statement.md }
  - { id: preface, source: document }
  - { id: abstract_id, source: document }
  - { id: abstract_en, source: document }
  - { id: cover, source: generated }
  - { id: toc, source: generated }
  - { id: list_of_tables, source: generated }
  - { id: list_of_figures, source: generated }
```

Acceptance:

- `uv run --project <repo> docgen check <file>` membaca format/structure baru.
- Aset lama tetap ada sampai WS15; shell fallback valid sampai cutover.
- Semua template legal ada.
- Schema `front_matter` tervalidasi dan pemetaan `id -> template` wajib ada.
- Validator menolak `source: template` jika file template tidak ada.

### WS2 - Core package skeleton

Langkah:

1. Buat `src/docgen/` dengan `cli.py`, `config.py`, `document.py`, `metadata.py`, `assets.py`, `errors.py`, `paths.py`, `pipeline.py`.
2. Daftarkan CLI `check`, `build`, `doctor`, `reconcile`; `new` tetap future, not implemented dan tidak menjadi acceptance sampai diimplementasikan. `cli.py` hanya diedit WS2.
3. `build` awalnya memanggil shell lama sebagai fallback.
4. `config.py` membaca data baru.
5. `document.py` mem-parse front matter dan validasi field.
6. Satu error base `DocgenError` + subclass.
7. Hapus fallback YAML 211 LOC.
8. Ganti lifecycle workspace lama dengan lifecycle baru di `pipeline.py`: dibuat hanya jika perlu dan dibersihkan default; `--keep` mencegah cleanup.
9. `pipeline.py` Fase 1 dimiliki WS2; handoff ke WS15 di Fase 3.
10. Stub `style_reference` ditempatkan di `stages/pandoc.py` milik WS2; stub mengembalikan `reference.docx` source apa adanya sampai WS7 siap. WS7 memberi tahu WS2 bahwa `stages/style_reference.py` siap; WS7 tetap pemilik file; WS2 hanya menghapus stub.
11. Tulis `test_cli` untuk `--target` default both, `--keep`, `--terms`, `--no-manifest`, dan `--no-adeu`.

Acceptance:

- `uv run --project <repo> docgen --version`.
- `uv run --project <repo> docgen check examples/assignment-single/document.md` lulus.
- `uv run --project <repo> docgen build ...` pada fase ini menghasilkan output yang sama lewat shell fallback.
- Tidak ada fallback YAML atau mutasi glosarium.
- Lifecycle workspace baru berjalan: tanpa `--keep` workspace dihapus dan tidak ada intermediate DOCX; dengan `--keep` workspace dan intermediate DOCX ada.
- `test_cli` mencakup `--target` default both, `--keep`, `--terms`, `--no-manifest`, dan `--no-adeu`.
- Stub `style_reference` di `stages/pandoc.py` mengembalikan `reference.docx` source apa adanya sampai WS7 siap.
- Setelah WS7 memberi tahu bahwa stage siap, stub dihapus oleh WS2; derived reference berasal dari `stages/style_reference.py`.
- Acceptance `uv run --project <repo> docgen --version` bergantung pada handoff `pyproject.toml` WS14 Phase 1.

### WS3 - DOCX core

Langkah:

1. `docx/package.py`, `docx/io.py`: load/save DOCX, zip, rels, content types.
2. `docx/xml.py`, `docx/names.py`: qn, pPr/rPr order, span, field, text.
3. `docx/cli.py`: CLI internal fondasi, future, not implemented; jangan dijadikan acceptance sampai modulnya ada.
4. Unit test dengan fixture DOCX.

Acceptance:

- Helper dipakai minimal oleh satu stage prototipe.
- Tidak ada traversal lxml ad-hoc di stage baru.
- API fondasi dibekukan.
- WS3 tidak memiliki helper domain di luar fondasi; helper domain mengikuti Batas ownership.

Estimasi program migrasi helper lintas lane, bukan langkah WS3:

- Skenario gross duplikasi 1.290 LOC dengan helper 250-300 LOC: net -990 sampai -1.040 LOC.
- Skenario minimal gross 900 LOC: net -650 LOC.
- Catatan penting: paket `docx/` penuh bisa LOC-netral di Fase 1; manfaat utamanya satu invariant DOCX dan penghapusan duplikasi, bukan pengurangan LOC.

### WS12 - Test harness

Baseline: 368 tes, 26 file, 10.060 LOC, 259 detik.

Target:

- 315-330 tes; unit 260-270; integration 40-50; packaging 12.
- File 22-24; LOC 7.800-8.500; runtime <300 detik.

Struktur:

- `tests/unit`, `tests/integration` (harness), `tests/packaging`, `tests/e2e`, `tests/_helpers`, `tests/factories`.
- `--strict-markers`.

Marker:

- `unit` default, `integration`, `packaging`, `e2e`, `word`, `windows`.
- Gate cepat: `uv run --project <repo> pytest -m "not integration and not packaging and not e2e and not word and not windows"`.

Langkah:

1. WS12 membuat daftar handoff: 10-12 tes style/caption/border dari `test_pagenumber`, 2 duplikat TOC, 2 exact-count `check_prose`, 4-5 caption `format_figures`, 4-5 `export_dotx`, 3-4 guard `platform_native`; lane pemilik mengeksekusi.
2. Handoff TOC parameterized `docx_toc=true/false/None` ke WS6; caption satu kontrak ke WS4; WS12 memiliki `tests/_helpers` dan `tests/factories/docx.py`.
3. Handoff daftar pertahankan: `test_terms.py` 35, `test_reconcile.py` 19, `test_singlefile.py` 26, `test_build_style.py` 6 sampai WS15, seluruh `test_format_*`, `test_check_captions.py`.
4. Handoff `test_modular_cli.py` 11 ke WS2 untuk dipindah atau dihapus di Fase 4.
5. WS12 menambah 10-12 tes packaging, 5 e2e, 3 golden invariant.
6. P0: handoff skip `Laporan.docx`; jangan biarkan 27 tes skip hijau (26 `test_pagenumber` + 1 `test_integration_terms`).
7. P1: WS12 bereskan helper dan fixture.
8. P2: handoff assertion shell ke WS2 saat shell dihapus.

WS12 tidak menghapus atau mengedit tes domain langsung. Lane pemilik mengeksekusi handoff.

Packaging test untuk repo-local: jalankan `uv run --project <repo> docgen check <file>` dari folder luar repo. Tes wheel hanya jika standalone dipilih nanti. Tes packaging Fase 1 dijalankan setelah handoff `pyproject.toml` WS14 Phase 1.

Mock Word/PDF bukan bukti PDF nyata. Manual spike Word wajib dan diberi marker `word`/`windows`.

Golden test fungsi high-CC:

- `reconcile.parse_markdown_blocks`
- `finalize.process`
- `terms.verify_docx` / `transform_runs`
- `add_paragraph_ids._markdown_candidates`
- `format_figures._ensure_table_caption` / `_ensure_image_caption`
- `build_style.build_style_patch`
- `manifest._parse_scalar`
- `singlefile._build_plan` / `_build_metadata`

Pola: canonical XML c14n + sha256, idempotensi dua run, korpus 8 fixture DOCX.

Acceptance:

- `uv run --project <repo> pytest tests/unit` cepat dan tidak menyentuh Word/Pandoc/mmdc.
- `uv run --project <repo> pytest tests/integration` memakai tool nyata atau fake eksplisit.
- `uv run --project <repo> pytest -m "not integration and not packaging and not e2e and not word and not windows"` lulus.
- Semua tes Word/Windows memakai marker `word`/`windows`.
- Manual spike Word wajib; mock tidak dihitung sebagai bukti PDF nyata.

### WS13 - Docs skeleton

- README 100-150 baris.
- AGENTS 50 baris.
- Satu `docs/README.md`.
- ADR 0001-0005.
- `docs/dev/repo-map.md`.

### WS14 - Hygiene dan pyproject handoff

- LICENSE MIT.
- `.gitattributes`: `.sh`/`.py` LF, DOCX/JPG binary.
- `.gitignore`: `out/`, `.laporan/`, `build/`, `review/`, `.venv*`, `acuan/`, `NUL`, generated DOCX/PDF.
- Hapus `build/`, `review/`, `build/lib`, egg-info, DOCX/PDF generated.
- `acuan/` tetap di disk dan tetap di-ignore; tidak dirujuk kode, build, contoh, atau dokumentasi pengguna.
- Tulis `pyproject.toml` lengkap: `[project.scripts] docgen = "docgen.cli:main"`, package discovery `src/docgen`, package-data `docgen/data/**`, dan build-system. `resources/word.ps1` adalah aset repo-local dan tidak masuk package-data wheel.
- Track `docs/dev/restructure-plan.md` dan `docs/dev/duplication-map.md` pada Fase 1.

Acceptance:

- `pyproject.toml` memiliki entry point `docgen`, package discovery `src/docgen`, package-data `docgen/data/**`, dan build-system.
- `git status` bersih hanya setelah plan dan duplication map di-track.
- `git ls-files` tidak memuat generated binary baru.

## 7. Fase 2 - Port stage paralel

Semua lane memakai `docx/` API yang sudah dibekukan. Setiap lane hanya mengedit file miliknya.

### WS4 - Captions/figures/code

Baseline 2.614 LOC; target 1.840-2.180 LOC fisik (-17% sampai -30%), 1.700-1.900 LOC kode.

Tidak ada fungsi >50 LOC. Fungsi terbesar:

- `_ensure_image_caption` 47
- `check_markdown` 47
- `_make_table` 46
- `_process_captions` 45
- `_ensure_table_caption` 41
- `_format_table` 41
- `_format_code_table` 40
- `_format_caption_paragraph` 40
- `_write_docx` 40

7 fungsi multi-tanggung jawab: `_ensure_image_caption`, `_ensure_table_caption`, `_process_captions`, `_format_table`, `_make_table`, `_format_code_table`, `check_markdown`.

Duplikasi:

- `format_figures` vs `format_code`: 306 baris nonblank identik, sekitar 260-300 LOC near-duplicate; 42 konstanta `W_*`, `TBLPR_ORDER`/`TCPR_ORDER`, set style kode, border.
- `check_captions._masked_lines` vs `singlefile._masked_lines`: 37 baris identik, rasio 0,89; divergensi HTML `<code>`.
- Caption/label dan style caption terduplikasi di 4 tool; style kode di 3 tool.
- Regex gambar `check_captions` (alt saja) vs `singlefile` (alt+dest+title) berbeda.

Dead code/cabang mati:

- `normalized_tables` double-count.
- `if not lines`, `_replace_caption_prefix` jalur False, `_is_delimiter_row` empty, `_format_table` selalu True, `as_dict` tidak dipakai, cabang `_prefix_overlaps_field`.
- Docs mismatch: `check_captions` menjanjikan exit 2 untuk error berkas, aktual 1.

Code table:

- Pertahankan `_is_code_table`, `CODE_TABLE_BORDERS`, `_format_table`, dan skip `_ensure_captions`; pindahkan helper ke `docx/tables.py`.

Target modul:

- `docx/captions.py`: teks/field/prefix, nomor bab, format, anchor, fill, create.
- `stages/captions.py`: orkestrasi/report/CLI DOCX.
- `docx/tables.py`: border/margin/header, `_is_code_table`, `_format_table`.
- `stages/code.py`: deteksi, build, normalisasi legacy, report/CLI.
- `stages/validate.py`: validasi Markdown; `stages/captions.py` menangani DOCX.

Urutan stage: mengikuti kontrak P0.2/WS15; WS4 tidak menetapkan urutan.

Tes: 57 tes target lulus; coverage figures 88,1%, code 89,3%, captions 91,2%.

Acceptance:

- Caption wajib dan border kode 1x1.
- Urutan stage mengikuti kontrak P0.2/WS15.
- Karakterisasi code-table dan golden XML lulus.
- 57 tes target lulus.
- Code table tidak diberi caption tabel data, tidak diubah menjadi tabel ilmiah, dan tetap 1x1 border penuh.
- Run pertama untuk tabel baru `normalized_tables == 0`; run kedua juga 0.
- Validasi Markdown ada di `stages/validate.py`; validasi DOCX ada di `stages/captions.py`.
- Dokumentasi exit code `check_captions` sesuai aktual.

Gap P0: golden `document.xml` lintas stage, karakterisasi urutan code-table, caption gambar kosong di atas, `fldChar` begin/end, paritas masking HTML/reference image.

Risiko tinggi: urutan stage, idempotensi dua run dan `document.xml` semantic-equivalent via c14n+sha256, heuristik anchor caption. Mitigasi: golden XML + characterization test.

### WS5 - Equations/numbering/layout

Target:

| Stage | Estimasi |
|---|---:|
| `stages/equations.py` | 400-460 |
| `stages/numbering.py` | 420-480 |
| `stages/normalize.py` + `stages/blank_lines.py` | 720-820 |
| Total | 1.870-2.140 (dari 2.700, -21% sampai -31%) |

Acceptance:

1. Guard urutan `normalize -> equations -> blank_lines`; urutan penuh mengikuti kontrak P0.2/WS15.
2. Bold field exempt dicek sebelum bold dihapus.
3. Tab stop kustom dipertahankan.
4. `w:ins`/`w:del` tidak memutus blok blank line.
5. Heading 4-9 punya aturan gap atau tidak diklasifikasi.
6. `ChapterTitle` dikenali equations; tes persamaan `BAB 2`, Romawi IV/IX.
7. Part DOCX non-target byte-identik; `document.xml` semantic-equivalent via canonical XML c14n + sha256; idempotensi dua run.

### WS6 - Sections/TOC/page numbers

Paling berisiko.

Sumber dan temuan:

- `docx.lua` 585 LOC; `Pandoc` 250 LOC (42,7%); `balance_title` 74 LOC.
- P1 bug: `balance_title` crash untuk judul 2 kata >55 karakter.
- P1: field `TOC \c "Gambar"`/`"Tabel"` sudah ada, tetapi tidak ada `SEQ`, jadi daftar kosong.
- P1: TOC hilang jika tidak ada H1 bernomor.
- P1: H2 sebelum H1 menghasilkan `0.1.`.
- P1: `author` scalar dipecah menjadi tiga `CoverName`; `keywords` scalar pecah; abstract multiline kehilangan paragraf.
- Margin punya 4 sumber: Lua default, `Meta`, `build_style`, `finalize`.
- `finalize.process` 181 LOC, CC 36; `fix_toc_styles` 103 LOC.

Langkah:

- Port `docx.lua` penuh: cover, TOC field, heading numbering, approval/abstract, page break, inline formatting heading.
- `balance_title` diport penuh dengan guard agar tidak crash pada judul 2 kata >55 karakter.
- `spacer` diport sebagai spacing eksplisit.
- Margin diport; sumber nilai dari `format.yml`, bukan default Lua.
- Port `finalize-docx.py`: sections, page number Romawi/Arab, header/footer, TOC styles.
- Hapus `docx-pagenum.py`.
- Hapus `settings_only`, `fix_daftar_isi_title`, `sync_section_margins`.
- Perbaiki H2 di bawah H1 unnumbered; `cover_show_lecturer` case-insensitive.
- Buat `stages/sections.py`, `toc.py`, `page_numbers.py`, `docx/sections.py`, `fields.py`.
- Pecah bagian WS6 dari `finalize-docx.py` menjadi `stages/sections.py`, `toc.py`, `page_numbers.py`, `docx/sections.py`, `fields.py`; komponen package, styles, dan cli dimiliki WS3, WS7, dan WS2.
- Urutan port: metadata util -> heading numbering -> section/margin -> TOC/lists -> cover/approval/abstract.
- Tulis ADR 0006 `docx.lua parity scope`: port penuh termasuk bug fix, bukan penghapusan perilaku.

Tes:

- Wajib golden test untuk `process` dan TOC.
- Tes: 1 field TOC, `w:sdt`, TOC1/2/3, `3.2.3 ......13`, section Romawi/Arab, blank page hilang.
- Tes wajib: blank page, TOC, scalar metadata, H2 sebelum H1, tanpa H1.
- Tes: H2 di bawah H1 unnumbered, `cover_show_lecturer` case-insensitive, inline formatting heading.

Acceptance:

- Semua perilaku cover/TOC/heading/approval/abstract/page break ada.
- Bug `balance_title` tidak crash.
- 1 field TOC, `w:sdt`, TOC1/2/3, `3.2.3 ......13`, section Romawi/Arab, tidak ada halaman kosong.
- `settings_only`, `fix_daftar_isi_title`, `sync_section_margins` dihapus.
- H2 di bawah H1 unnumbered benar; `cover_show_lecturer` case-insensitive.
- Inline formatting heading dipertahankan.
- WS6 tidak mengedit `cli.py`.

Estimasi: Python 450-650 LOC dengan reuse helper `finalize`/`format_figures`; tes 250-350 LOC.

Dependensi: lane 9 dan lane 1 selesai.

### WS7 - Terms/style/reference

Sumber dan temuan:

- `build_style.py` 1.346 LOC, 37 fungsi + `terms.py` 1.304 LOC, 39 fungsi + `audit_terms.py` 878 = 3.528 LOC.
- Target 3.000-3.250 LOC (-11%).
- 9 fungsi style XML duplikat (337 LOC) pindah ke `docgen/docx/styles.py`.
- `terms.StyleResolver` dan `audit_terms.ItalicResolver` digabung ke `docgen/docx/terms.py`.
- Dead code: `parse_flat_yaml`, field `line_no`/`gloss_first`/`status`, `ApplyResult.paragraph_count`, `make_context.window`.
- `audit_terms.py` menjadi dev-only.
- `scripts/make-reference-docx.py` 666 LOC legacy, tidak dipakai build; hapus script.
- `reference.docx` tetap source asset dengan 63 style; tambah regression test style ID/nilai.
- `build_style.main` 152 LOC dan `build_style_patch` 87 LOC; keduanya dipecah.
- Estimasi hapus make-ref: -613 LOC net.

Langkah:

- Port `terms.py` ke `stages/terms.py` + `docx/terms.py`.
- Port `build_style.py` ke `stages/style_reference.py` + `docx/styles.py`.
- Pecah `terms.py` menjadi glossary/model/transform/verify; pisahkan preset vs OOXML generator.
- Pecah `build_style.main` 152 LOC dan `build_style_patch` 87 LOC.
- Glosarium default `src/docgen/data/glossary/istilah.tsv`; override user `istilah.tsv` di samping `document.md`.
- Precedence user > package; merge per frasa; validasi.
- Hapus generator `make-reference-docx.py`.
- WS7 memberi tahu WS2 bahwa `stages/style_reference.py` siap. WS7 tetap pemilik file. WS2 hanya menghapus stub dari `stages/pandoc.py`. WS15 memverifikasi tidak ada stub.
- `reference.docx` source asset tidak pernah ditimpa; `stages/style_reference.py` menghasilkan derived reference di cache/temp.
- Gate istilah default off. `--terms` mengaktifkan apply + verify + gate; tanpa `--terms` tidak ada auto-italic dan tidak ada gate.

Tes: apply/verify, TNR 12, spacing 1.5, style caption. Golden test untuk `verify_docx`, `transform_runs`, `build_style_patch`.

Acceptance:

- Style sesuai format dan terms apply/verify lulus.
- WS2 sudah menghapus stub; derived reference berasal dari `stages/style_reference.py`, bukan stub.
- Derived `reference.docx` dihasilkan dari `format.yml` sebelum Pandoc.
- `reference.docx` source tidak tertimpa; derived reference berada di cache/temp.
- `build_style.main` dan `build_style_patch` sudah dipecah.
- Tidak ada fallback YAML.
- `--terms` on/off diuji; tanpa flag tidak ada auto-italic dan tidak ada gate.

Risiko: byte drift `styles.xml`; unifikasi resolver mengubah verify/audit.

Dependensi: lane 4 dan lane 11 selesai.

### WS8 - Office/PDF

- Gabung `export_pdf.py` + `word_finalize.py` ke `stages/office.py`.
- Gabung `export_pdf.ps1` + `update_fields.ps1` ke satu `resources/word.ps1`.
- Wajib memeriksa hasil Word; gagal berarti error dan exit nonzero, bukan warning.
- `--allow-missing-word` opt-in.
- `stages/office.py` hanya Word; PDF hanya Word; tidak ada jalur LibreOffice, `soffice`, atau Poppler.
- Debian best-effort hanya DOCX; PDF tidak didukung di Debian.
- Hapus `export_dotx` 403 LOC + 486 LOC tes; docs DOTX dihapus.
- `check_prose` tetap dev-only; baseline 726 LOC; refactor WS14: hapus parser YAML manual 155 LOC, pakai `ruamel.yaml`, hapus `--validasi`, target 540-570 LOC.
- Tes: command builder, mock, manual spike Word.
- Estimasi lane 7: 2.140 ke 1.160-1.260 LOC.

Acceptance:

- Word sukses/gagal terdeteksi dan exit nonzero saat gagal.
- `--allow-missing-word` opt-in.
- Tidak ada `export_with_libreoffice`, `soffice`, atau Poppler.
- Hanya satu `resources/word.ps1`.
- `resources/word.ps1` adalah aset repo-local; `pyproject.toml` hanya memuat package-data `docgen/data/**/*`, jadi skrip ini tidak ikut wheel. Jalur pencarian kode memakai root repo; standalone wheel memerlukan keputusan packaging terpisah.
- Tidak ada jalur LibreOffice.
- Di Debian, acceptance build memakai `--target docx`; PDF tidak didukung.

### WS9 - Mermaid

- Pindahkan `mermaid.py` ke `stages/mermaid.py`; hapus `src/docgen/mermaid.py`.
- Integrasikan inline ke pipeline; hapus batch CLI.
- Error jelas jika `mmdc` hilang.
- Tambahkan cache render.
- Tes fake `mmdc` + opsional nyata.

Acceptance:

- Mermaid dirender inline oleh `stages/mermaid.py`.
- Error `mmdc` hilang jelas.
- Cache bekerja.
- Tidak ada batch CLI Mermaid.

### WS10 - Adeu

Sumber dan temuan:

- 2.059 baris fisik = 1.626 baris kode; 750-900 LOC logika unik; 900-1.000 LOC duplikasi/overlap.
- `reconcile.parse_markdown_blocks` 198 LOC, radon CC 45 (branch count 46); `add._markdown_candidates` 144 LOC, CC 32; `reconcile.load_manifest` 93 LOC, CC 24; `reconcile._walk_xml` 80 LOC, CC 28; `add.add_paragraph_ids` 62 LOC.
- Wajib golden test canonical XML + sha256 sebelum port.

Target modul:

- `features/adeu/manifest.py`, `paragraph_ids.py`, `reconcile.py`, `cli.py`.
- Wajib pakai `docx/package.py`, `docx/xml.py`, `docx/fields.py`, `docx/bookmarks.py`.
- Tambahkan `src/docgen/markdown/blocks.py` sebagai parser Markdown bersama; satukan `add._markdown_candidates` dan `reconcile.parse_markdown_blocks`.

Rencana:

- Pindahkan `add_paragraph_ids.py` + `reconcile.py` ke `features/adeu/`.
- Manifest default: `.laporan/manifest.json` di samping dokumen; `--no-manifest` mematikan manifest dan pemindaian `--source-dir`; `--no-adeu` mematikan bookmark + manifest + source scan.
- Single-file: manifest harus persisten di samping dokumen, bukan di workspace yang dihapus. Default-on hanya masuk akal jika manifest ditulis di samping dokumen.
- Hapus `built_at` atau buat deterministik; manifest saat ini tidak byte-deterministik.
- Perbaiki docs drift: `adeu-integration.md` memakai `## p0042:` sedangkan kode memakai em dash.

Estimasi:

- 2.059 ke sekitar 1.680 dengan docx helper; 1.000-1.130 dengan parser Markdown + model manifest + CLI bersama; 770-880 tanpa source matching.

Tes:

- text box/nested, Track Changes, tabel/list/quote/fence, field multi-paragraf, bookmark duplikat, schema manifest, exit code, `--docx-name`, `--no-manifest`, `--no-adeu` (bookmark absen, manifest absen, source scan absen).

Acceptance:

- Schema manifest valid dan default `.laporan/manifest.json`.
- `--no-manifest` mematikan manifest + source scan.
- `--no-adeu` mematikan bookmark + manifest + source scan; tes memastikan ketiganya absen.
- `uv run --project <repo> docgen reconcile` tersedia sebagai entry point.
- Manifest deterministik dan `text_sha256` diverifikasi.
- Exit code `add` dan `reconcile` konsisten.
- Validasi manifest ketat; `built_at` dihapus atau deterministik.

### WS11 - Daftar gambar/tabel

- Field `TOC \c` sudah ada di `docx.lua`, tetapi tanpa `SEQ` sehingga daftar kosong.
- Implementasi `stages/lists.py`; gunakan `docx/fields.py` milik WS6 tanpa mengedit.
- Caption memakai `SEQ Tabel`/`SEQ Gambar`; keputusan hybrid prefix bab literal + `SEQ` dicatat di `docs/dev/decisions/0007-seq-hybrid.md`.
- Daftar memakai `TOC \c "Tabel"` dan `TOC \c "Gambar"`.

Gate SEQ:

- Owner: WS11.
- Timebox: 1 hari.
- Sukses: caption `Tabel 2.1` dan daftar terisi di Word.
- Fallback: daftar statis atau defer dengan ADR.

Tes: field ada, daftar terisi setelah Word update; marker `word`/`windows`.

Acceptance:

- Gate SEQ diputuskan sebelum implementasi.
- Caption `Tabel 2.1` benar.
- Daftar terisi setelah Word update.
- Manual Word gate wajib; mock bukan bukti.
- Fallback tersedia jika gate gagal.

Dependensi: WS4, WS6, spike SEQ.

## 8. Fase 3 - Integrasi dan cutover (barrier)

WS15 langkah:

1. Handoff `pipeline.py` dari WS2 dan daftarkan stage pada urutan kanonik.
2. Panggil `stages/style_reference.py` milik WS7 sebelum Pandoc; verifikasi tidak ada stub `style_reference` tersisa di `stages/pandoc.py`.
3. Satu `DocumentPackage` load/save.
4. Ganti `docgen build` dari shell ke pipeline.
5. Jalankan golden DOCX/PDF.
6. Hapus kode dan aset lama:
   - Pindahkan `tools/check_prose.py` ke `tools/dev/check_prose.py`; hapus file lama.
   - Pindahkan `tools/audit_terms.py` ke `tools/dev/audit_terms.py`; hapus file lama.
   - `src/laporan/` dan `laporan.py`
   - `tools/format_*`, `tools/terms.py`, `tools/build_style.py`, `tools/reconcile.py`, `tools/add_paragraph_ids.py`
   - `tools/export_pdf.py`, `tools/word_finalize.py`, `tools/export_pdf.ps1`, `tools/update_fields.ps1`
   - Pastikan `tools/export_dotx.py` dan `scripts/*` lama sudah dihapus.
   - `scripts/finalize-docx.py`, `scripts/make-reference-docx.py`, `scripts/docx-pagenum.py`
   - `chapters/`, `content/`, `writing/`
   - `structures/`, `formats/`, `presets/`, `refs/`, `metadata.yml`, `cover.md`, `logo.jpg` root, `reference.docx` root
   - `docx.lua`, `build-docx.sh`, `build.sh`, `build-proposal.sh`, `Makefile`
7. Perbaiki trust boundary: kode hanya dari package; folder konten hanya data.

Urutan kanonik:

```text
validate
-> mermaid
-> style_reference
-> front_matter
-> pandoc
-> sections
-> code
-> captions/figures
-> normalize
-> equations
-> numbering
-> blank_lines
-> terms
-> toc
-> page_numbers
-> lists
-> office
-> pdf
```

Acceptance:

- `uv run --project <repo> docgen build <task>/document.md --target both` berhasil (Windows-only).
- Di Debian, acceptance memakai `--target docx`.
- `style_reference` berjalan sebelum Pandoc; derived `reference.docx` berasal dari `stages/style_reference.py`, bukan stub; source tidak tertimpa.
- Tidak ada stub `style_reference` tersisa di `stages/pandoc.py`.
- DOCX/PDF invariant sama.
- Part non-target byte-identik; `document.xml` semantic-equivalent via canonical XML c14n + sha256; idempotensi dua run.
- Tanpa `--keep`, workspace `.laporan-build/` dihapus dan tidak ada intermediate DOCX tersisa; dengan `--keep`, workspace dan intermediate DOCX ada.
- Target tree tercapai; tidak ada path lama seperti `src/laporan/`, `laporan.py`, `tools/format_*`, `scripts/finalize-docx.py`, `chapters/`, `content/`, `writing/`, root `structures/`, root `formats/`, `presets/`, `refs/`, `metadata.yml`, `cover.md`, `logo.jpg`, `reference.docx`, `docx.lua`, shell build, atau Makefile.
- Tidak ada `build/` dan `review/`.
- Tidak ada eksekusi kode dari folder konten.
- Urutan stage sesuai kontrak P0.2 dan daftar kanonik di atas.

## 9. Fase 4 - Tests, docs, examples

### WS12 final

- Capai target 315-330 tes, 22-24 file, 7.800-8.500 LOC, runtime <300 detik.
- Serahkan daftar handoff tes legacy (folder mode, Lua default, Typst, preset lama, shell) ke lane pemilik; WS12 tidak menghapus tes domain langsung.
- Handoff `test_modular_cli.py` ke WS2; handoff `test_build_style.py` ke WS7 untuk diganti/dihapus setelah WS15.
- Windows: `uv run --project <repo> pytest` (termasuk marker `windows` dan golden PDF).
- Debian: `uv run --project <repo> pytest -m "not windows"`.
- `test_golden_pdf.py` wajib `pytest.mark.skipif(sys.platform != "win32", reason="Word-only")` atau module-level skip setara; di Debian tidak dikoleksi/dijalankan, bukan hanya marker.
- Golden PDF Windows: `uv run --project <repo> pytest -m windows tests/integration/test_golden_pdf.py`; di Debian manual/not gate.
- Jalankan e2e dan packaging smoke dari folder luar.
- Pastikan tidak ada skip hijau `Laporan.docx`; 27 skip harus eksplisit (26 `test_pagenumber` + 1 `test_integration_terms`).
- 3 golden invariant, golden test high-CC, golden PDF Windows, dan 5 e2e lulus.
- Manual spike Word dilakukan; mock bukan bukti PDF nyata.

### WS13 final

- README/AGENTS final.
- `docs/agent/` dan `docs/dev/`.
- `repo-map.md`, `testing.md`, `packaging.md`, `pipeline.md`.
- ADR.
- Link check.
- `examples/assignment-single`, `thesis-single`, `proposal-single` + `out/`.
- Build 3 contoh dengan `uv run --project <repo> docgen build <file> --target both` (Windows-only; Debian `--target docx`).

### WS14 final

Acceptance:

- Hapus sisa artefak.
- Cek `git ls-files` tidak memuat generated.
- Cek `acuan/` tetap di-ignore dan tidak dirujuk kode, build, contoh, atau dokumentasi pengguna.
- Cek `.gitignore` lengkap.
- Cek LICENSE dan metadata.
- Pastikan `docs/dev/restructure-plan.md` tracked dan `git status` bersih. Jika belum di-track, acceptance WS14 gagal.
- Hapus sisa `export_dotx` 403 LOC + 486 LOC tes dan docs DOTX.
- Refactor `check_prose` dev-only: 726 LOC -> 540-570 LOC; hapus parser YAML manual 155 LOC, pakai `ruamel.yaml`, hapus `--validasi`. Acceptance: LOC <= 570 dan tidak ada parser YAML manual.

### Gate Fase 4

- Full test sesuai OS: Windows `uv run --project <repo> pytest`; Debian `uv run --project <repo> pytest -m "not windows"`.
- Link check lulus.
- 3 contoh build DOCX/PDF dengan `uv run --project <repo> docgen build <file> --target both` (Windows-only; Debian `--target docx`).
- Tidak ada false-green; manual Word spike tercatat.

## 10. Fase 5 - Release

Acceptance:

- Lulus jika Windows: `uv run --project <repo> pytest` (termasuk marker `windows` dan `test_golden_pdf`).
- Lulus jika Debian: `uv run --project <repo> pytest -m "not windows"`; golden PDF hanya Windows.
- Lulus jika 3 contoh build dengan `uv run --project <repo> docgen build <file> --target both` berhasil (Windows-only; di Debian `--target docx`).
- Lulus jika TOC, caption, daftar gambar/tabel, dan halaman Romawi/Arab terverifikasi.
- Lulus jika target tree tercapai dan tidak ada path lama.
- Lulus jika target tree untuk area tools/PS hanya memuat `tools/dev/check_prose.py`, `tools/dev/audit_terms.py`, dan `resources/word.ps1`; tidak ada `tools/export_pdf.py`, `tools/word_finalize.py`, `tools/export_pdf.ps1`, `tools/update_fields.ps1`, `tools/export_dotx.py`, atau `scripts/*` lama.
- Lulus jika tidak ada false-green dan manual Word spike sudah dilakukan.
- Lulus jika plan tracked dan `git status` bersih.
- Lulus jika tag dibuat.
- Gagal jika salah satu kriteria di atas tidak terpenuhi.

## 11. Dependency graph

```text
WS0 (barrier)
 ├─ WS1 config
 ├─ WS3 docx
 ├─ WS12 test harness (kontinu; final setelah WS15)
 ├─ WS13 docs skeleton
 └─ WS14 hygiene

WS0 + WS14 Phase 1 pyproject
 └─ WS2 core

WS3 fondasi selesai
 ├─ WS4 captions/tables
 ├─ WS5 layout/normalize/blank_lines
 ├─ WS6 sections/fields (lane 9 selesai)
 ├─ WS7 styles/terms (lane 4, lane 11 selesai)
 └─ WS10 adeu (butuh WS2 + WS3)

WS2 selesai
 ├─ WS8 office/pdf
 ├─ WS9 mermaid
 └─ WS10 adeu (butuh WS3)

WS4 + WS6 selesai
 └─ WS11 lists (spike SEQ)

Semua selesai
 └─ WS15 integrasi (barrier; `style_reference` WS7 sebelum Pandoc)
     ├─ WS12 final tests + packaging smoke
     ├─ WS13 final docs
     └─ WS14 final cleanup
```

WS12 berjalan kontinu. Final dan packaging smoke menunggu WS15. WS2 menyerahkan `pipeline.py` ke WS15 di Fase 3. WS2 menunggu handoff `pyproject.toml` WS14 Phase 1 untuk acceptance `--version`; tes packaging WS12 Fase 1 menyusul setelah handoff itu.

## 12. Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Port `docx.lua` tidak paritas | TOC/cover/numbering rusak | Golden test, spike Word, port bertahap |
| Word non-Windows | PDF tidak tersedia | PDF hanya Word di Windows; Debian DOCX only |
| Trust boundary | Eksekusi kode dari folder konten | Kode hanya dari package; data dari dokumen |
| Urutan stage kanonik | Persamaan/numbering rusak | Kontrak P0.2/WS15 + guard + golden test |
| DOCX part non-target berubah | File rusak | Tes byte-preservation per part |
| `document.xml` canonical mismatch | DOCX tidak semantik-identik | c14n+sha256 + idempotensi dua run |
| Bold field exempt hilang | TOC/PAGEREF/SEQ rusak | Tes bold exempt |
| Tab stop kustom hilang | Numbering rusak | Tes tab kustom |
| Packaging repo-local | `uv run` path salah | `--project` eksplisit, tes dari folder luar |
| Python 3.15 di Debian | Build gagal | `uv python install 3.15`; dokumentasikan |
| Tes legacy menghalangi | Refactor lambat | Hapus tes sesuai fitur yang dipotong |
| Docs drift | AI/new dev bingung | Satu indeks, ADR, repo-map |
| `balance_title` crash | Judul 2 kata panjang gagal build | Port penuh + guard; tes judul 2 kata >55 karakter |
| Metadata scalar pecah | Author/keywords salah | Normalisasi metadata di `document.py` |
| Resolver duplikat | Verify/audit berbeda hasil | Satu `docx/terms.py`, matriks tes |
| `styles.xml` byte drift | Style berubah | Golden test styles.xml |
| Halaman kosong `sectPr` | PDF punya halaman kosong | Golden test section |
| Daftar gambar/tabel kosong | Fitur list gagal | Spike `SEQ` |
| False-green dari skip | 27 tes skip hijau tanpa menguji | 26 `test_pagenumber` + 1 `test_integration_terms`; build fixture segar atau fail eksplisit |
| Duplikasi helper tes | 400-450 LOC copy-paste | `tests/_helpers`, `tests/factories` |
| Package-data repo-local | `docgen/data/**` tidak terbaca dari `uv run --project` | Uji dari folder luar; package-data di `pyproject.toml` |
| Mock Word/PDF selalu hijau | PDF rusak lolos | Marker `word`/`windows` + manual spike Word |
| Overlap TOC/style/caption | 14 tes TOC di 9 file | Satu parameterized suite |
| Fungsi high-CC | Port berisiko mengubah perilaku | Golden test c14n+sha256 |
| Duplikasi 1.351 baris | Refactor menyebar | `docx/` helper, P0 |
| `docx/` LOC-netral | Ekspektasi pengurangan LOC tidak terpenuhi | Ukur invariant, bukan LOC |
| Manifest tidak deterministik | Manifest berubah tiap build | Hapus `built_at` atau normalisasi |
| Duplikasi Adeu 900-1.000 LOC | Refactor besar | Pakai `docx/` + `markdown/blocks.py` |
| `--no-manifest` tidak mematikan source scan | Build tetap lambat | Satu flag mematikan manifest + source-dir |
| Coverage Adeu rendah | Bug tidak tertangkap | Tes text box, track changes, tabel, schema |
| Urutan code/figures | Caption/tabel kode salah | Kontrak urutan + golden XML |
| Duplikasi 306 baris figures/code | Refactor menyebar | `docx/` helper, satu owner |
| Anchor caption heuristik | Caption menempel ke gambar salah | Characterization test |

## 13. Status audit dan update plan

### Selesai

| Lane | Scope | Temuan utama | WS terdampak |
|---|---|---|---|
| 1 | `finalize-docx.py`, `docx-pagenum.py` | 1.685 LOC, 67 fungsi; `process` 181 LOC, 34 branch; duplikasi 300-350 LOC; `parse_entries` 0/432 paragraf; 27 tes skip: 26 `test_pagenumber` + 1 `test_integration_terms` | WS6 |
| 2 | `format_figures`, `check_captions`, `format_code` | 2.614 LOC; target 1.840-2.180; 306 baris identik figures vs code; code-table harus dipertahankan | WS4 |
| 3 | `format_equations`, `format_numbering`, `insert_blank_lines`, `normalize_layout` | 2.700 LOC; duplikasi sekitar 960; target 1.870-2.140; urutan normalize ke equations wajib; bold field exempt bug | WS5 |
| 4 | `build_style`, `terms`, `audit_terms` | 3.528 LOC; target 3.000-3.250; 9 fungsi style XML duplikat 337 LOC; resolver terms vs audit duplikat | WS7 |
| 5 | `add_paragraph_ids.py`, `reconcile.py`, manifest Adeu | 2.059 baris fisik = 1.626 baris kode; hanya 750-900 LOC logika unik; 900-1.000 LOC duplikasi/overlap | WS3, WS10 |
| 6 | `src/laporan/*` | 3.266 LOC; target 2.600; dead code 211 + 237; `_build_metadata` 95, `_build_plan` 94 | WS2 |
| 7 | `office` tools | 2.140 LOC; PowerShell similarity 71,2%; `word_finalize` mengabaikan hasil; target 1.160-1.260 | WS8 |
| 8 | Peta spaghetti lintas file | 57 file Python, 18.395 LOC, 671 def, 33 blok duplikat, 1.351 baris duplikat (7,3%); 44 fungsi >50 LOC; max radon CC 45; max branch count 46 | WS3, WS6, WS7, WS10, WS12 |
| 9 | `docx.lua` | 585 LOC; `Pandoc` 250 LOC (42,7%); `balance_title` crash; TOC list tanpa SEQ; metadata scalar pecah | WS6, WS11 |
| 10 | Shell build | 1.078 LOC; 31 baris identik; trust boundary; target Python 750-850 | WS2, WS15 |
| 11 | `make-reference-docx.py`, `reference.docx` | 666 LOC legacy; tidak dipakai build; `reference.docx` 63 style = source asset; hapus generator | WS7 |
| 12 | `tests/` | 368 tes, 26 file, 10.060 LOC, 259 detik; 40 tes bisa false-green; duplikasi helper 400-450 LOC; 0 tes packaging | WS12 |

### Pending

Tidak ada. Semua 12 lane audit selesai.

### Peta spaghetti

#### Metrik

- 57 file Python, 18.395 LOC produksi, 671 def.
- 33 blok duplikat, 1.351 baris duplikat (7,3%).
- 44 fungsi >50 LOC; 69 fungsi radon CC>10; 19 fungsi radon CC>20; max radon CC 45; max branch count 46.
- MI grade C: finalize 0,00; format_figures 0,00; terms 0,00; reconcile 0,00; singlefile 3,27; check_prose 5,22; add_paragraph_ids 8,16; manifest 8,96.

#### Top fungsi

| LOC | Radon CC | File | Fungsi |
|---:|---:|---|---|
| 198 | 45 | `tools/reconcile.py:526` | `parse_markdown_blocks` |
| 181 | 36 | `scripts/finalize-docx.py:1251` | `process` |
| 169 | 27 | `tools/check_prose.py:518` | `tes` |
| 152 | 21 | `tools/build_style.py:1191` | `main` |
| 147 | 35 | `tools/audit_terms.py:482` | `collect_occurrences` |
| 144 | 32 | `tools/add_paragraph_ids.py:543` | `_markdown_candidates` |
| 119 | 13 | `tools/audit_terms.py:694` | `render_report` |
| 115 | 1 | `tools/terms.py:335` | `build_paragraph_model` |
| 113 | 30 | `tools/terms.py:1032` | `verify_docx` |
| 108 | 20 | `tools/format_numbering.py:511` | `format_numbering` |
| 103 | 4 | `scripts/finalize-docx.py:1459` | `fix_toc_styles` |
| 95 | 16 | `src/laporan/singlefile.py:750` | `_build_plan` |

Tabel memakai radon CC. `parse_markdown_blocks` memiliki branch count 46.

#### Duplikasi terbesar

- `format_equations` 35,0%; `normalize_layout` 29,1%; `format_code` 25,7%; `format_numbering` 21,9%; `format_figures` 20,3%.
- Blok terbesar: equations vs figures 102 baris; code vs equations 62; blank lines vs normalize 58; add_paragraph_ids vs code 51.
- `finalize-docx` vs `build_style`: sekitar 211 baris mirip.

#### Prioritas refactor

- P0: buat fondasi `docgen/docx/` (`package.py`, `io.py`, `xml.py`, `names.py`, `cli.py`); migrasi 6 formatter + `add_paragraph_ids` dilakukan lane domain, bukan WS3.
- P0: pecah `finalize-docx.py` menjadi package/style/sections/toc/process/cli lintas owner.
- P1: pecah `format_figures.py`, `terms.py`, `reconcile.py`, `build_style.py`.
- P2: hapus `src/laporan/singlefile.py` setelah port; hapus fallback YAML `manifest.py`.

### Aturan update

1. Setiap lane selesai menambah baris di changelog.
2. Update tabel status audit.
3. Update WS yang terdampak: scope, estimasi, tes, risiko.
4. Jangan mulai lane yang scope-nya bergantung pada audit yang belum selesai.
5. Jika audit menemukan fitur mati baru, tambahkan ke daftar cut dan update fase.
6. Jika audit menemukan duplikasi baru, tambahkan ke `docs/dev/duplication-map.md`.

## 14. Langkah pertama yang bisa dieksekusi

1. P0.1 buat golden invariant.
2. P0.2 tulis tiga kontrak dan urutan stage kanonik.
3. WS14 Phase 1: hygiene dasar dan `pyproject.toml` plus console script.
4. WS1 salin data ke `src/docgen/data/`.
5. WS12 buat test harness.
6. WS13 buat docs skeleton.
7. WS2 buat skeleton `docgen` setelah WS14 Phase 1 menyelesaikan `pyproject.toml` dan console script.
8. WS3 buat fondasi `docx/` core.

Empat langkah pertama setelah P0.1/P0.2 yang boleh paralel adalah WS14 Phase 1, WS1, WS12, dan WS13. WS2 menunggu handoff pyproject WS14 Phase 1.
