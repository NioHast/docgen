# Peta Repo

Repo ini berisi paket Python `docgen`, data format dan struktur, contoh
single-file, tes, serta dokumentasi. Semua path relatif terhadap akar repo.

## Pohon ringkas

```text
.
|-- README.md
|-- AGENTS.md
|-- LICENSE
|-- pyproject.toml
|-- uv.lock
|-- .python-version
|-- src/
|   `-- docgen/
|       |-- cli.py
|       |-- pipeline.py
|       |-- config.py
|       |-- document.py
|       |-- metadata.py
|       |-- assets.py
|       |-- paths.py
|       |-- errors.py
|       |-- data/
|       |   |-- formats/undip-msi/
|       |   |-- structures/{assignment,proposal,thesis}/
|       |   `-- glossary/istilah.tsv
|       |-- docx/
|       |-- features/adeu/
|       |-- markdown/
|       `-- stages/
|-- examples/
|   |-- assignment-single/
|   |-- proposal-single/
|   `-- thesis-single/
|-- docs/
|   |-- README.md
|   |-- agent/
|   `-- dev/
|       |-- contracts/
|       `-- decisions/
|-- tools/
|   `-- dev/
|-- tests/
|   |-- unit/
|   |-- integration/
|   |-- e2e/
|   |-- packaging/
|   |-- fixtures/
|   |-- factories/
|   `-- _helpers/
`-- resources/
    `-- word.ps1
```

## Berkas dan tanggung jawab

| Path | Tanggung jawab |
| --- | --- |
| `src/docgen/cli.py` | Parser `docgen` dan handler `check`, `build`, `doctor`, `reconcile`. |
| `src/docgen/pipeline.py` | Urutan stage, `BuildOptions`, `StageContext`, output, manifest hook. |
| `src/docgen/config.py` | Skema dan validasi `format.yml` dan `structure.yml`. |
| `src/docgen/document.py` | Parse `document.md`, validasi front matter dan body. |
| `src/docgen/metadata.py` | Normalisasi metadata penulis dan field front matter. |
| `src/docgen/assets.py` | Resolusi gambar, bibliografi, glosarium, dan template. |
| `src/docgen/paths.py` | Lokasi data paket dan validasi path relatif. |
| `src/docgen/errors.py` | Hierarki error dan pemetaan exit code. |
| `src/docgen/data/` | Format, struktur, template, glosarium, logo, CSL, `reference.docx`. |
| `src/docgen/docx/` | Model package DOCX dan seluruh mutasi XML. |
| `src/docgen/features/adeu/` | Bookmark `pNNNN`, manifest, source scan, reconcile. |
| `src/docgen/markdown/` | Parser blok Markdown untuk manifest dan reconcile. |
| `src/docgen/stages/` | Stage kanonik pipeline. |
| `examples/assignment-single/` | Contoh tiga bab, tabel, dan Mermaid. |
| `examples/proposal-single/` | Contoh empat bab dan daftar isi. |
| `examples/thesis-single/` | Contoh lengkap dengan front matter, gambar, kode, dan lampiran. |
| `docs/agent/` | Panduan penulis dan agent. |
| `docs/dev/` | Dokumentasi pengembang, kontrak, ADR, dan rencana. |
| `tools/dev/check_prose.py` | Pemeriksa prosa dan pembanding versi. |
| `tools/dev/audit_terms.py` | Audit italic istilah pada DOCX. |
| `tools/dev/rules.yml` | Sumber pola pemeriksa prosa. |
| `tests/` | Unit, integrasi, e2e, packaging, dan fixture golden. |
| `resources/word.ps1` | Adaptor Word untuk finalisasi field dan ekspor PDF. |

## Data paket

`src/docgen/data/` adalah bagian dari paket, bukan direktori kerja pengguna.
Jangan menaruh output build di sana.

```text
data/
|-- formats/
|   `-- undip-msi/
|       |-- format.yml
|       |-- citation.csl
|       |-- logo.jpg
|       `-- reference.docx
|-- structures/
|   |-- assignment/structure.yml
|   |-- proposal/
|   |   |-- structure.yml
|   |   `-- templates/approval.md
|   `-- thesis/
|       |-- structure.yml
|       `-- templates/
|           |-- approval.md
|           `-- statement.md
`-- glossary/istilah.tsv
```

## Artefak yang tidak dilacak

Artefak berikut ditulis di samping `document.md` atau di `examples/<name>/`:

- `<report_name>.docx` dan `<report_name>.pdf`;
- `.laporan/manifest.json`, `.laporan/istilah-baru.txt`,
  `.laporan/reconcile.md`, `.laporan/istilah-audit.md`;
- `.laporan-build/`;
- `examples/<name>/out/`.

Semua di-ignore Git. Jangan menyunting artefak ini sebagai sumber.

## Di luar cakupan

Folder `tests/fixtures/golden/` menyimpan baseline DOCX dan invariant PDF.
Fixture itu hanya untuk tes, bukan contoh penggunaan. `docs/dev/refactor-plan.md`
adalah acuan kerja aktif; arsip historis berada di `docs/dev/archive/`, dan
kontrak adalah acuan implementasi, bukan panduan pengguna.
