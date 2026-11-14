# Peta Repo

Repo ini berisi paket Python AutoOffice, data format dan struktur DOCX, data
design deck, contoh, tes, serta dokumentasi. Semua path relatif terhadap akar
repo.

## Daftar Isi

- [Pohon ringkas](#pohon-ringkas)
- [Berkas dan tanggung jawab](#berkas-dan-tanggung-jawab)
- [Data paket DOCX](#data-paket-docx)
- [Artefak yang tidak dilacak](#artefak-yang-tidak-dilacak)
- [Di luar cakupan](#di-luar-cakupan)

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
|   `-- autooffice/
|       |-- cli/                 # entry point, target, output, check, doctor
|       |-- common/              # helper lintas domain
|       |-- design/              # token, theme, font, kontras
|       |-- deck/
|       |   |-- model/           # schema, compiler, DeckIR, key, coverage
|       |   |-- layout/          # grid 12 kolom, preset, slot, overflow
|       |   |-- render/pptx/     # renderer python-pptx
|       |   |-- charts/          # chart native dan placeholder
|       |   |-- copy/            # copy checker dan diagnosis prosa
|       |   |-- transcript/      # parser transkrip
|       |   `-- media/           # render Mermaid
|       |-- docx/
|       |   |-- package/         # model DOCX/OPC dan seluruh mutasi XML
|       |   |-- stages/          # stage kanonik pipeline DOCX
|       |   |-- config/          # format.yml, structure.yml, validasi
|       |   |-- markdown/        # parser blok dan heading Markdown
|       |   |-- adeu/            # bookmark, manifest, source scan, rekonsiliasi
|       |   |-- terms/           # glosarium dan istilah
|       |   |-- data/            # format, struktur, template, glosarium, CSL
|       |   |-- command.py       # API build_docx
|       |   `-- pipeline.py      # orkestrasi stage DOCX
|       |-- google/              # Drive, Sheets, Slides, state, OAuth
|       |-- pdf/                 # adapter COM Word dan PowerPoint
|       `-- assets/fonts/        # Plus Jakarta Sans untuk PPTX/PDF
|-- examples/
|   |-- assignment-single/
|   |-- proposal-single/
|   |-- thesis-single/
|   `-- demo-deck/
|-- docs/
|   |-- README.md
|   |-- user/
|   |-- dev/
|   |-- learn/
|   |-- contracts/
|   `-- decisions/
|-- tools/
|   |-- quality/                 # gate dan checker
|   |-- visual/                  # smoke render PPTX ke PNG
|   |-- mutation/                # mutation testing manual
|   `-- install_fonts.py
`-- tests/
    |-- cli/
    |-- contract/
    |-- deck/
    |-- design/
    |-- docx/
    |-- google/
    |-- pdf/
    |-- performance/
    |-- property/
    |-- tools/
    |-- visual/
    `-- fixtures/
```

## Berkas dan tanggung jawab

| Path | Tanggung jawab |
| --- | --- |
| `src/autooffice/cli/main.py` | Parser `autooffice` dan handler `check`, `build`, `doctor`. |
| `src/autooffice/cli/build.py` | Orkestrasi build Markdown dan deck, preflight lane, embedding font, PDF, dan Google. |
| `src/autooffice/cli/targets.py` | Matriks target, parsing target, dan deteksi input `.md`/`.yaml`. |
| `src/autooffice/cli/outputs.py` | Path output, workspace, state, cache, review, dan tulis atomic. |
| `src/autooffice/docx/pipeline.py` | Urutan stage, `BuildOptions`, `StageContext`, output, manifest hook. |
| `src/autooffice/docx/command.py` | API publik `build_docx` untuk CLI Markdown. |
| `src/autooffice/docx/package/` | Model package DOCX, part, relationship, helper XML, field, bookmark, terms. |
| `src/autooffice/docx/stages/` | Stage kanonik pipeline DOCX. |
| `src/autooffice/docx/config/` | Skema, model, dan validasi `format.yml` serta `structure.yml`. |
| `src/autooffice/docx/document.py` | Parse `document.md`, validasi front matter dan body. |
| `src/autooffice/docx/paths.py` | Lokasi data paket dan validasi path relatif. |
| `src/autooffice/docx/errors.py` | Hierarki error DOCX dan pemetaan exit code. |
| `src/autooffice/docx/data/` | Format, struktur, template, glosarium, logo, CSL, `reference.docx`. |
| `src/autooffice/docx/adeu/` | Bookmark `pNNNN`, manifest, source scan, dan modul rekonsiliasi internal. |
| `src/autooffice/docx/markdown/` | Parser blok Markdown dan penomoran heading Markdown. |
| `src/autooffice/deck/model/` | Compiler `deck.yaml`, DeckIR, key manifest, dan coverage plan. |
| `src/autooffice/deck/layout/` | Grid, preset layout, custom rows, measurement, dan overflow. |
| `src/autooffice/deck/render/pptx/` | Renderer PPTX native, table, chart, image, notes, dan validasi package. |
| `src/autooffice/design/` | Token, theme `indigo`/`hitam`, font, dan kontras. |
| `src/autooffice/google/` | Autentikasi, Drive, Sheets, Slides, state, dan diff. |
| `src/autooffice/pdf/` | Word/PowerPoint COM, ekspor PDF, dan embedding font. |
| `examples/assignment-single/` | Contoh tiga bab, tabel, dan Mermaid. |
| `examples/proposal-single/` | Contoh empat bab dan daftar isi. |
| `examples/thesis-single/` | Contoh lengkap dengan front matter, gambar, kode, dan lampiran. |
| `examples/demo-deck/` | Contoh deck YAML, transkrip, aset, dan diagram. |
| `docs/user/` | Panduan pengguna dan penulis `document.md` serta `deck.yaml`. |
| `docs/dev/` | Dokumentasi pengembang, pipeline, tes, dan gate. |
| `tools/quality/` | `gate.py`, docs checker, test checker, coverage, Python style, dan no-legacy. |
| `tools/install_fonts.py` | Installer font Plus Jakarta Sans per-user tanpa admin. |
| `tests/` | Suite CLI, DOCX, deck, design, Google, PDF, performa, properti, dan visual. |

## Data paket DOCX

`src/autooffice/docx/data/` adalah bagian dari paket, bukan direktori kerja
pengguna. Jangan menaruh output build di sana.

```text
docx/data/
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

Artefak berikut ditulis di samping input atau di `examples/<name>/`:

- DOCX/PDF: `<report_name>.docx`, `<report_name>.pdf`;
- manifest dan istilah: `.laporan/manifest.json`,
  `.laporan/istilah-baru.txt`, `.laporan/istilah-audit.md`;
- workspace DOCX: `.laporan-build/`;
- deck: `<stem>.pptx`, `<stem>.pdf`, `<stem>.transcript.md`,
  `<stem>.slides-upload.pptx`;
- state deck: `.autooffice/state/`, `.autooffice/cache/`,
  `.autooffice/review/`;
- workspace deck: `.autooffice-build/<stem>/`;
- output contoh: `examples/<name>/out/`.

Semua di-ignore Git. Jangan menyunting artefak ini sebagai sumber.

## Di luar cakupan

Folder `tests/fixtures/golden/` menyimpan baseline DOCX dan invariant PDF.
Fixture itu hanya untuk tes, bukan contoh penggunaan. Arsip historis berada di
`docs/dev/archive/`, dan kontrak adalah acuan implementasi, bukan panduan
pengguna.
