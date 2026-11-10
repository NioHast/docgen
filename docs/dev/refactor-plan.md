# Refactor Plan Final - docgen

**Baseline:** commit `4a5b777`
**Status:** final; P0.2 selesai 2026-11-10, fase lain belum dieksekusi
**Bahasa:** Indonesia untuk prosa dan pesan pengguna, Inggris untuk identifier
**Ruang lingkup:** `src/docgen`, `tests`, `docs`, `examples`, `pyproject.toml`, `uv.lock`, `scripts`
**Di luar lingkup:** `acuan/`, konten naskah pengguna, dan perubahan perilaku pipeline

## Daftar isi

- [0. Status dan tujuan](#0-status-dan-tujuan)
- [1. Keputusan final](#1-keputusan-final)
- [2. Target struktur](#2-target-struktur)
- [3. Fase dan task](#3-fase-dan-task)
  - [Fase 3.5 - Zero fallback](#fase-35---zero-fallback)
- [4. Parallel execution map](#4-parallel-execution-map)
- [5. Acceptance global](#5-acceptance-global)
- [6. Keputusan yang telah dikonfirmasi](#6-keputusan-yang-telah-dikonfirmasi)

## 0. Status dan tujuan

### 0.1 Baseline

| Item | Nilai |
| --- | --- |
| Commit baseline | `4a5b777` |
| Status test | 475 passed, 1 skipped, 2 subtests. Skip berasal dari PDF fixture yang tidak di-commit; dihapus oleh P0.4. |
| Baseline style | Ruff 311 error, mypy 64 error. Angka ini dicatat di S1; Ruff ke 0 di S4, mypy ke 0 di S5. |
| Build baseline | Thesis DOCX dan PDF |
| Python | `>=3.15` |
| Versi paket | `0.1.0` |
| Folder acuan | `acuan/` ignored, tidak disentuh, tidak dirujuk oleh kode, build, contoh, atau docs aktif |

Baseline awal memiliki 1 skip PDF fixture yang dihapus P0.4. Setelah P0.4, baseline dianggap beku ketika empat hal ini benar:

1. Full test suite lulus; baseline awal 475 passed dan 2 subtests, dan tidak ada tes yang hilang.
2. Build thesis menghasilkan DOCX dan PDF yang dapat diperiksa.
3. Golden invariant mencatat hash dan fingerprint output baseline.
4. Tidak ada skip karena fixture hilang. Skip PDF hanya karena platform Windows.

### 0.2 Tujuan

- Menghapus legacy, tech debt, alias mati, dan fallback tersembunyi.
- Menjadikan setiap concern punya satu sumber kebenaran.
- Membuat struktur folder dan nama modul dapat ditebak tanpa membaca semua kode.
- Menyediakan dokumentasi berlapis untuk pemula, kontributor, dan AI.
- Menegakkan code style dengan Ruff dan mypy secara bertahap.
- Menjaga perilaku: tidak ada regresi output dan tidak ada tes yang hilang.

### 0.3 Prinsip

- KISS: solusi paling kecil yang memenuhi kontrak.
- YAGNI: tidak menambah abstraksi untuk kebutuhan yang belum ada.
- Readability > LOC: kode mudah dibaca lebih penting daripada jumlah baris.
- Satu alasan perubahan per modul.
- Tidak ada komentar historis di kode aktif.
- Tidak ada fallback tersembunyi atau perilaku ganda.
- Tidak ada workaround, monkey patch, atau dead code.
- Perubahan kecil dan atomik, disertai acceptance yang eksplisit.
- Verifikasi sebelum merge; tidak ada big-bang refactor.

## 1. Keputusan final

Tabel ini adalah default yang mengikat. Kelima item di bagian 6 telah dikonfirmasi dan dicatat di P0.2 serta [ADR 0008](decisions/0008-refactor-boundaries.md).

| Area | Keputusan final |
| --- | --- |
| Nama output | `report_name` wajib di front matter. Tidak ada default `"Tugas"`. Tidak ada flag CLI `--report-name`. |
| Legacy config | Hapus `CFG-LEGACY`, `_FORMAT_LEGACY`, `_STRUCTURE_LEGACY`, `_DOCUMENT_LEGACY`, `_DOCUMENT_COMPAT_KEYS`, dan `legacy_toc`. Kunci lama menjadi `CFG-UNKNOWN-KEY`. |
| Glosarium | Migrasikan `src/docgen/data/glossary/istilah.tsv` ke header `term<TAB>italic` sebelum menghapus dukungan header lama. |
| API mati | Hapus seluruh alias dan wrapper pada tabel 1.1. Tidak ada shim baru. |
| Heading Markdown | Pindahkan `docx/headings.py` ke `markdown/headings.py`. Rename `HeadingError` menjadi `MarkdownHeadingError`. |
| Adeu | Pindahkan `features/adeu/` menjadi `adeu/`. Hapus package `features/`. |
| Script Word | Pindahkan `resources/` menjadi `scripts/`. Pertahankan `scripts/word.ps1` sebagai adapter PowerShell. |
| Stage caption | Ubah `StageName.CAPTIONS` dari `"captions/figures"` menjadi `"captions"`. Tidak ada parser nilai lama. |
| Future import | Hapus `from __future__ import annotations` dari seluruh modul karena target Python 3.15 dan PEP 649. |
| Dependency | Pindahkan `python-docx` ke dev dependency. Hapus `Pillow`. `pypdf` tetap dev. |
| PDF baseline | Jangan commit PDF fixture besar. Ganti dengan E2E build PDF dari `examples/thesis-single` di Windows, verifikasi page count/TOC/teks kunci lewat `pdf-baseline.json`. Debian hanya skip platform. Fixture DOCX lama yang memuat Typst dihapus atau di-refresh. |
| Word adapter | Jangan migrasi ke Python COM sekarang. Jika standalone wheel dibutuhkan, masukkan `word.ps1` sebagai package-data. |
| API yang dipertahankan | `W_ALIASES`, `STYLE_ORDER`, `is_code_table`, dual artifact `markdown`/`mermaid.markdown`, `open_docx`, `number_markdown`, `DocxPackage`, `NormalizeError`. |
| Dokumen historis | Setelah isi penting dipindah ke plan ini, arsipkan `duplication-map.md` dan `restructure-plan.md` ke `docs/dev/archive/`. Hapus di Fase 6 jika tidak ada nilai audit. |
| Folder acuan | `acuan/` tetap ignored, tidak disentuh, dan tidak dirujuk oleh kode, build, contoh, atau dokumentasi pengguna aktif. Archive historis tidak menjadi acuan. |
| Dokumentasi pemula | Letakkan materi belajar di `docs/dev/learn/00-06`. |
| TOC | Wajib untuk setiap dokumen lebih dari 150 baris. |
| Code style | Ruff untuk format dan lint, mypy bertahap. Konfigurasi diberi komentar singkat; alasan lengkap di `docs/dev/code-style.md`. |

### 1.1 API mati dan penggantinya

| Simbol | Lokasi | Pengganti |
| --- | --- | --- |
| `DEFAULT_REPORT_NAME` | `metadata.py` | Field `report_name` wajib, tanpa nilai default. |
| `LayoutReport.paragraphs` | `docx/layout.py` | `LayoutReport.checked` |
| `LayoutReport.skipped_style` | `docx/layout.py` | `LayoutReport.skipped` |
| `LayoutReport.skipped_field` | `docx/layout.py` | `LayoutReport.fields_preserved` |
| `read_document` | `docx/layout.py` | `document_root` |
| `write_document` | `docx/layout.py` | `set_document_root` |
| `is_deleted` | `docx/layout.py` | `has_deleted_ancestor` |
| `TermsReport.term_count` | `docx/terms.py` | `TermsReport.applied` |
| `TermsReport.review_count` | `docx/terms.py` | `len(TermsReport.reviews)` |
| `TermsVerifyReport.failures` | `docx/terms.py` | `TermsVerifyReport.violations` |
| `TermsVerifyReport.direct_formatting` | `docx/terms.py` | `TermsVerifyReport.warnings` |
| `apply_to_docx` | `docx/terms.py` | `apply_terms` pada package, lalu pemanggil menyimpan package. |
| `verify_docx` | `docx/terms.py` | `verify_terms` pada package atau hasil `open_docx`. |
| `check_markdown` | `docx/terms.py` | `collect_markdown_terms` dan `write_review_file`. |
| `plain_inline` | `markdown/blocks.py` | `normalize_inline` |
| `normalize_author` | `metadata.py` | `normalize_authors` |
| `ParagraphIdError` | `features/adeu/paragraph_ids.py` | `ManifestError` |
| `StageSpec.owner` | `pipeline.py` | Tidak ada pengganti. Kepemilikan diatur di plan dan review, bukan runtime. |
| `FormatEquationsReport`, `number_equations`, `EquationStage`, alias privat equations | `stages/equations.py` | Nama kanonik `EquationReport`, `format_equations`, `EquationsStage`. |
| `blank_lines`, `BlankLineStage`, alias privat blank_lines | `stages/blank_lines.py` | Nama kanonik `insert_blank_lines`, `BlankLinesStage`. |
| `resolve_style_specs`, `generate_reference_docx`, `build_reference` | `stages/style_reference.py` | `style_specs_for_format`, `build_reference_docx`. |
| `format_code` | `stages/code.py` | `apply_code` |
| `CaptionStage`, `format_figures` | `stages/captions.py` | `CaptionsStage`, `apply_captions` |
| `normalize_numbering` | `stages/numbering.py` | `format_numbering` |
| `check_captions`, `validate_captions` | `stages/validate.py` | `check_markdown`, `validate_markdown` dari stage validasi. |
| `_FORMAT_LEGACY`, `_STRUCTURE_LEGACY` | `config.py` | Dihapus. Kunci lama menjadi `CFG-UNKNOWN-KEY`. |
| `_DOCUMENT_LEGACY`, `_DOCUMENT_COMPAT_KEYS`, `legacy_toc` | `document.py` | Dihapus. Kunci `toc` di front matter menjadi `CFG-UNKNOWN-KEY`. |

Catatan penting:

- `check_markdown` di `stages/validate.py` adalah implementasi validasi caption dan tetap dipertahankan. Yang dihapus hanya `check_markdown` di `docx/terms.py`.
- `DocxPackage` adalah nama publik package yang dipertahankan. Ia bukan alias kompatibilitas baru.
- `W_ALIASES` adalah tabel alias elemen OOXML, bukan alias API. Ia tetap.
- `number_markdown` adalah API penomoran Markdown dan tetap. Ia tidak sama dengan `number_markdown_headings`.

### 1.2 API dan perilaku yang dipertahankan

| Simbol atau perilaku | Alasan dipertahankan |
| --- | --- |
| `W_ALIASES` | Tabel pemetaan elemen OOXML, dipakai untuk normalisasi XML. |
| `STYLE_ORDER` | Menjaga urutan child style deterministik. |
| `is_code_table` | Predikat publik untuk membedakan tabel kode dari tabel data. |
| Dual artifact `markdown` dan `mermaid.markdown` | Kontrak artifact pipeline dan stage Mermaid. |
| `open_docx` | Loader path publik yang tetap dipakai tes dan alat. |
| `number_markdown` | API penomoran heading Markdown yang sudah menjadi kontrak. |
| `DocxPackage` | Nama publik package di kontrak dan tes. |
| `NormalizeError` | Error domain normalisasi, bukan alias. |

## 2. Target struktur

```text
src/docgen/
  README.md
  __init__.py
  __main__.py
  cli.py
  pipeline.py
  config.py
  document.py
  metadata.py
  assets.py
  paths.py
  errors.py

  docx/
    README.md
    __init__.py
    package.py
    io.py
    xml.py
    names.py
    styles.py
    sections.py
    heading_numbering.py
    captions.py
    tables.py
    layout.py
    fields.py
    bookmarks.py
    paragraphs.py
    runs.py
    numbering.py
    page.py
    terms/
      __init__.py
      glossary.py
      model.py
      apply.py
      verify.py

  markdown/
    README.md
    __init__.py
    blocks.py
    headings.py

  stages/
    README.md
    __init__.py
    validate.py
    mermaid.py
    style_reference.py
    front_matter.py
    pandoc.py
    sections.py
    code.py
    captions.py
    normalize.py
    equations.py
    numbering.py
    blank_lines.py
    terms.py
    toc.py
    page_numbers.py
    lists.py
    office.py
    pdf.py

  adeu/
    README.md
    __init__.py
    manifest.py
    paragraph_ids.py
    reconcile.py
    cli.py

  data/
    README.md
    formats/
    structures/
    glossary/

tests/
  README.md
  conftest.py
  _helpers/
  factories/
  fixtures/
  unit/
  integration/
  e2e/
  packaging/

tools/
  README.md
  dev/
    audit_terms.py
    check_prose.py
    check_docs.py
    rules.yml

scripts/
  README.md
  word.ps1

docs/
  README.md
  agent/
  dev/
    README.md
    refactor-plan.md
    learn/00-06
    architecture.md
    pipeline/
      README.md
      stages.md
      artifacts.md
      errors.md
      options.md
    docx/
      README.md
      package.md
      fields.md
      layout.md
      styles.md
      terms.md
    glossary.md
    references.md
    code-style.md
    contracts/
    decisions/
    archive/
examples/
  README.md
  assignment-single/
  proposal-single/
  thesis-single/
```

### 2.1 Batas modul

| Area | Tetap dipertahankan | Batas tanggung jawab |
| --- | --- | --- |
| `docx/` | Ya | Satu-satunya pemilik ZIP, OPC, XML Word, style, section, field, dan package. Tidak membaca Markdown, config, atau structure. |
| `stages/` | Ya, 18 stage | Satu modul per stage. Stage tidak melakukan load atau save package target dan tidak mengimpor stage lain. |
| `stages/lists.py` | Ya | Menangani daftar tabel dan daftar gambar sekaligus karena satu kontrak front matter dan satu mekanisme field. Tidak dipecah menjadi `tables.py` dan `figures.py`. |
| `stages/code.py` | Ya | Menangani tabel kode dan normalisasi kode dalam satu stage. Tidak dipecah menjadi beberapa stage. |
| `markdown/` | Ya | Parser dan penomoran Markdown murni. Tidak mengimpor `lxml`, `python-docx`, atau `docx/`. |
| `adeu/` | Ya | Fitur manifest, paragraph ID, dan reconcile. Tidak mengimpor pipeline atau stage. |
| `docx/terms/` | Ya, setelah F4 | Package kecil untuk glossary, model, apply, dan verify. `__init__.py` hanya mengekspor API publik. |
| `tools/dev/` | Ya | Alat pengembang, bukan runtime. Tidak diimpor `src/docgen`. |
| `scripts/word.ps1` | Ya | Adapter PowerShell untuk Microsoft Word. Bukan modul Python. |
| `data/` | Ya | Package data: format, structure, template, glosarium, logo, CSL, dan `reference.docx`. |

Catatan F5: tree di atas memakai `config.py` sebagai default. Jika gate F5 memutuskan split, ganti satu file itu dengan `config/__init__.py`, `config/models.py`, `config/parsers.py`, dan `config/validation.py`. Sisa tree tidak berubah.

### 2.2 Yang tidak dipakai

- `docx_utils.py` tidak dibuat. Helper XML tetap di `docx/xml.py`, `docx/paragraphs.py`, dan `docx/runs.py`.
- `list_of_figures.py` tidak dibuat. Daftar gambar tetap ditangani `stages/lists.py`; ID front matter `list_of_figures` tetap ada karena itu kontrak data, bukan nama modul.
- `docx/headings.py` tidak ada setelah N1. Isinya pindah ke `markdown/headings.py`.
- `docx/terms.py` tidak ada setelah F4. Isinya pindah ke `docx/terms/`.
- `features/` tidak ada setelah N2.
- `resources/` tidak ada setelah N3.
- `pywin32` tidak ditambahkan pada refactor ini.

## 3. Fase dan task

### Fase 0 - Baseline

Tujuan: mengunci perilaku sebelum ada perubahan kode.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| P0.1 | Bekukan golden DOCX baseline | `tests/integration/test_golden_docx.py`, `tests/integration/test_golden_pipeline.py`, `tests/e2e/test_thesis_e2e.py`, `tests/fixtures/golden/baseline-4a5b777.json` | - | Baseline sebelum guard: `475 passed, 1 skipped (PDF fixture), 2 subtests`; build thesis DOCX/PDF; hash c14n `word/document.xml` dan fingerprint artifact dicatat; setelah guard ditambahkan, tidak ada tes baseline yang hilang dan total minimal 475. | B0 |
| P0.2 | Catat keputusan | `docs/dev/refactor-plan.md`, `docs/dev/decisions/0008-refactor-boundaries.md` | P0.1 | **Selesai 2026-11-10.** Semua item bagian 6 dikonfirmasi; keputusan dicatat di [ADR 0008](decisions/0008-refactor-boundaries.md); tabel keputusan dan target struktur tidak bertentangan; tidak ada TBD. | B0 |
| P0.4 | Bersihkan skip PDF dan fixture Typst | `tests/integration/test_golden_pdf.py`, `tests/integration/test_golden_docx.py`, `tests/unit/test_golden_fixtures.py`, `tests/unit/test_docx_package.py`, `tests/unit/test_page_numbers.py`, `tests/unit/test_sections.py`, `tests/unit/test_toc.py`, `tests/fixtures/golden/pdf-baseline.json`, `tests/fixtures/golden/laporan-baseline.docx`, `tests/fixtures/golden/baseline-4a5b777.json` | P0.1, P0.2 | `tests/integration/test_golden_pdf.py::test_pdf_fixture_matches_baseline` tidak skip saat fixture hilang; tes diganti E2E `test_pdf_build_matches_baseline`; baseline JSON berasal dari `examples/thesis-single`; Debian skip hanya platform `windows`; tidak ada PDF fixture di repo; `pdf-baseline.json` dan DOCX fixture hasil refresh bebas Typst; semua konsumen fixture diperbarui; `test_golden_fixtures.py` lulus. | B0 |
| P0.3 | Tag baseline lokal | Tidak ada file | P0.1, P0.2, P0.4 | Annotated tag `baseline-4a5b777`; `git status` bersih; tidak dipush. | B0 |

Aturan P0.1:

- Golden DOCX membandingkan part yang relevan dan hash c14n, bukan byte ZIP mentah.
- PDF baseline ditangani P0.4. P0.1 hanya memastikan build thesis DOCX/PDF berhasil.
- Jangan commit PDF hasil build. DOCX fixture hanya boleh di-refresh oleh P0.4 dan harus bebas teks historis.
- Jika baseline saat ini berbeda dari `4a5b777`, hentikan fase dan perbaiki baseline sebelum lanjut.

Aturan P0.4:

- Jangan commit `tests/fixtures/golden/laporan-baseline.pdf` atau PDF fixture besar lain.
- `pdf-baseline.json` menyimpan `schema_version`, `source`, `page_count`, `page_size_points`, `key_text`, dan `toc`. Hapus field `fixture` dan catatan yang menyuruh skip.
- Sumber baseline baru adalah `examples/thesis-single`, bukan dokumen lama yang memuat Typst.
- `test_pdf_baseline_record_is_complete` berjalan di semua platform dan hanya memvalidasi schema serta isi JSON. Jangan menduplikasi angka baseline di konstanta `EXPECTED_*`.
- `test_pdf_build_matches_baseline` menyalin `examples/thesis-single` ke direktori sementara, build `--target pdf` atau `--target both`, lalu membandingkan page count, page size, TOC, dan teks kunci dengan JSON.
- Temukan artifact PDF lewat output build atau `report_name`, bukan hardcode `Tugas.pdf`, agar perubahan L3.3 tidak memutus test.
- Baseline PDF dibuat di Windows dengan versi Word yang sama. Jika versi Word berubah, refresh JSON dan review diff; jangan mengubah tes menjadi skip.
- Jangan jadikan seluruh modul Windows-only. `test_pdf_baseline_record_is_complete` tetap berjalan di Debian; hanya E2E build yang memakai marker `windows` dan `word`.
- Marker E2E PDF adalah `integration`, `windows`, dan `word`. Skip hanya `sys.platform != "win32"` dengan alasan platform. Tidak ada `pytest.skip` karena fixture hilang dan tidak ada `PDF_FIXTURE`.
- Di Windows tanpa Microsoft Word, test PDF gagal dengan pesan jelas. Jangan menggantinya dengan skip fixture atau skip Word.
- Refresh `tests/fixtures/golden/laporan-baseline.docx` dari build `examples/thesis-single` tanpa Typst. Hapus fixture hanya jika semua konsumen ditulis ulang; default adalah refresh. Jangan pertahankan fixture lama.
- Ganti docstring fixture lama yang menyebut `Laporan.docx` atau `06bda0b` dengan asal baru `examples/thesis-single`.
- Perbarui konsumen fixture: `test_golden_docx.py`, `test_docx_package.py`, `test_page_numbers.py`, `test_sections.py`, dan `test_toc.py`. Perbarui expected caption, tabel, dan TOC sesuai isi baru.
- `tests/unit/test_golden_fixtures.py` wajib memastikan JSON dan semua part XML di DOCX fixture tidak memuat `Typst`/`typst`, tidak ada `laporan-baseline.pdf`, dan JSON tidak memuat field `fixture`.

### Fase 1 - Mechanical style

Tujuan: menegakkan format, lint, dan baseline mypy non-strict tanpa mengubah perilaku.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| S1 | Konfigurasi Ruff dan mypy | `pyproject.toml`, `uv.lock`, `docs/dev/code-style.md` | P0.3 | Ruff dan mypy terpasang dan terkonfigurasi; baseline dicatat: Ruff 311 error, mypy 64 error; `mypy` belum harus 0; `ruff check` berjalan. | S |
| S2 | Hapus future import | Seluruh `.py` di `src`, `tests`, `tools`, `docs/dev/contributing.md` | S1 | `rg "from __future__ import annotations" src tests tools` kosong; `docs/dev/contributing.md` tidak lagi memuat instruksi memakai future import; `compileall` lulus; full suite minimal 475 pass dan tidak ada tes baseline hilang. | S |
| S3 | Format seluruh kode | `src/**`, `tests/**` | S2 | `ruff format --check` bersih; diff hanya formatting; full suite minimal 475 pass. | S |
| S4 | Perbaiki lint | `src/**`, `tests/**` | S3 | `ruff check --fix` untuk import dan quote; F401 diperbaiki manual; `ruff check` exit 0; full suite minimal 475 pass. | S |
| S5 | Baseline mypy ke 0 (non-strict) | `src/docgen/**`, `pyproject.toml` bila perlu | S4 | `uv run --extra dev mypy` exit 0; tidak menambah `ignore_errors` global; setiap `type: ignore` punya alasan. | S |

S1-S5 adalah satu train mechanical dan tidak boleh paralel. Satu owner memegang seluruh `src`, `tests`, `pyproject.toml`, dan `docs/dev/contributing.md` sampai S5 selesai.

Baseline S1: `ruff check` 311 error dan `mypy` 64 error. S4 menuntaskan Ruff sampai 0. S5 menuntaskan mypy non-strict sampai 0. Jangan menurunkan target dengan `ignore_errors` global.

Catatan S2: `docs/dev/contributing.md` masih menyebut `from __future__`; perbaiki di S2 dan verifikasi ulang di D7.

Contoh `pyproject.toml` yang wajib dipakai, dengan komentar singkat:

```toml
[tool.ruff]
# 100 kolom: cukup untuk ekspresi dan pesan error, tetap nyaman dibaca.
line-length = 100
# Target Python 3.15 agar UP dan RUF memakai sintaks modern.
target-version = "py315"
# Referensi konfigurasi: https://docs.astral.sh/ruff/configuration/

[tool.ruff.lint]
# Setiap kelompok dipilih karena menangkap kelas bug yang relevan.
# Daftar aturan: https://docs.astral.sh/ruff/rules/
select = [
  "E",   # pycodestyle error: spasi, indentasi, baris.
  "F",   # pyflakes: nama tidak terdefinisi dan import mati.
  "W",   # pycodestyle warning: trailing whitespace dan sejenisnya.
  "I",   # isort: urutan dan pengelompokan import.
  "UP",  # pyupgrade: sintaks lama yang sudah digantikan Python 3.15.
  "B",   # bugbear: pola rawan bug seperti mutable default.
  "SIM", # simplify: kontrol alur yang bisa disederhanakan.
  "RUF", # aturan khusus Ruff: konsistensi dan potensi bug.
  "BLE", # blind except: except terlalu luas tanpa alasan.
  "D",   # pydocstyle: kualitas docstring, dengan pengecualian di bawah.
]

# Pengecualian ini menjaga refactor tetap kecil dan tidak memaksa churn.
ignore = [
  "D101", # Docstring class publik ditunda; D8 menargetkan modul kunci.
  "D102", # Docstring method publik ditunda; kontrak ada di docs.
  "D103", # Docstring fungsi publik ditunda; D8 menargetkan fungsi panjang.
  "D105", # Docstring magic method tidak menambah informasi.
  "D107", # Docstring __init__ tidak perlu jika class sudah jelas.
  "D202", # Baris kosong setelah docstring tidak dipakai konsisten.
  "D401", # Imperative mood Inggris sulit diterapkan pada docstring Indonesia.
]

[tool.mypy]
# Non-strict dulu: target Fase 1 adalah baseline yang bersih, bukan strict total.
python_version = "3.15"
files = ["src/docgen"]
check_untyped_defs = true
no_implicit_optional = true
warn_unused_configs = true
warn_unused_ignores = true
warn_redundant_casts = true
# Stub pihak ketiga belum lengkap; longgarkan dulu, ketatkan per modul.
ignore_missing_imports = true
```

#### Prinsip dokumentasi code style

- Komentar di `pyproject.toml` harus singkat: satu baris untuk satu keputusan.
- Alasan lengkap, contoh kode, trade-off, dan tabel rule tinggal di `docs/dev/code-style.md`.
- Link resmi wajib ada untuk configuration, rules, settings, dan formatter.
- Tambahkan `ruff` dan `mypy` ke `[project.optional-dependencies].dev` dengan pin eksak saat implementasi. Jangan mengandalkan tool global.
- Jika versi Ruff yang dipin menolak kombinasi aturan D, selesaikan dengan ignore terdokumentasi di `docs/dev/code-style.md`. Jangan menurunkan `select`.
- `docs/dev/code-style.md` wajib memuat tabel rule dengan kolom `Rule`, `Status`, `Alasan`, `Contoh`, dan `Link resmi`.
- Tabel rule wajib mencakup E, F, W, I, UP, B, SIM, RUF, BLE, D, D101, D102, D103, D105, D107, D202, dan D401.
- `docs/dev/code-style.md` mencatat tahapan mypy: baseline non-strict dicatat di S1, S5 menuntaskan ke 0, strict per modul baru, dan strict total bukan gate v0.2.0.
- `docs/dev/code-style.md` wajib memuat link resmi untuk configuration, rules, settings, dan formatter:
  - Configuration: https://docs.astral.sh/ruff/configuration/
  - Rules: https://docs.astral.sh/ruff/rules/
  - Settings: https://docs.astral.sh/ruff/settings/
  - Formatter: https://docs.astral.sh/ruff/formatter/

### Fase 2 - Legacy, dependency, dan output naming

Tujuan: menghapus jalur lama, memindahkan dependency test, dan mewajibkan nama output.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| L1.1 | Pindahkan dependency | `pyproject.toml`, `uv.lock` | S5 | `python-docx` hanya di dev; `Pillow` hilang dari manifest dan lock; `pypdf` tetap dev; di env tanpa extra dev, import `docgen` tetap berhasil. | L1 |
| L1.2 | Perbarui dokumentasi packaging | `docs/dev/packaging.md` | L1.1 | Tabel dependency sesuai; perintah `uv sync --extra dev`; `uv lock --check` lulus. | L1 |
| L2.1 | Migrasikan glosarium | `src/docgen/data/glossary/istilah.tsv`, `docx/terms.py`, `tests/unit/test_stages_terms.py`, `docs/dev/terms.md` | S5 | Header hanya `term<TAB>italic`; `gloss_first` dan `status` dihapus; header lama ditolak dengan error jelas; glosarium default memuat semua istilah. | L2 |
| L2.2 | Hapus legacy config | `config.py`, `document.py`, `tests/unit/test_config.py`, `tests/unit/test_document.py`, `tests/unit/test_front_matter.py`, `docs/dev/contracts/config.md` | S5 | `CFG-LEGACY`, `_FORMAT_LEGACY`, `_STRUCTURE_LEGACY`, `_DOCUMENT_LEGACY`, `_DOCUMENT_COMPAT_KEYS`, `legacy_toc` hilang; kunci lama menjadi `CFG-UNKNOWN-KEY`; `toc` front matter ditolak. | L2 |
| L2.3 | Hapus API mati | `docx/layout.py`, `docx/terms.py`, `markdown/blocks.py`, `features/adeu/paragraph_ids.py`, `stages/equations.py`, `stages/blank_lines.py`, `stages/style_reference.py`, `stages/code.py`, `stages/captions.py`, `stages/numbering.py`, `stages/validate.py`, `pipeline.py`, tests terkait | S5 | Simbol tabel 1.1 di area L2 hilang; `normalize_author` menjadi handoff L3.1; tidak ada alias pengganti; `rg` acceptance bersih. | L2 |
| L2.4 | Perbarui test dan docs legacy | `tests/unit/test_config.py`, `tests/unit/test_document.py`, `tests/unit/test_stages_terms.py`, `tests/unit/test_stages_layout.py`, `tests/unit/test_stages_equations.py`, `tests/unit/test_stages_captions.py`, `tests/unit/test_stages_numbering.py`, `tests/unit/test_lists.py`, `tests/unit/test_toc.py`, `tests/unit/test_page_numbers.py`, `tests/unit/test_pipeline.py`, `tests/unit/test_style_reference.py`, `docs/dev/terms.md`, `docs/dev/contracts/config.md` | L2.1, L2.2, L2.3 | Test lama diubah ke perilaku baru; tidak ada test yang dihapus tanpa pengganti; docs tidak menyebut fallback. | L2 |
| L3.1 | Wajibkan `report_name` dan bersihkan metadata | `metadata.py`, `tests/unit/test_metadata.py` | S5 | `report_name` hilang, kosong, atau whitespace menghasilkan `CFG-REQUIRED`; field menjadi `str` tanpa default; `DEFAULT_REPORT_NAME` dan `normalize_author` hilang. | L3 |
| L3.2 | Hapus fallback nama output | `stages/pandoc.py`, `stages/office.py`, `features/adeu/reconcile.py`, handoff `pipeline.py` ke L2 | L3.1 | Tidak ada literal `"Tugas"` sebagai fallback di `src`; semua path memakai `metadata.report_name` langsung. | L3 |
| L3.3 | Perbarui contoh, test, docs | `examples/*/document.md`, `examples/README.md`, `tests/unit/test_cli.py`, `tests/unit/test_front_matter.py`, `tests/integration/*`, `docs/agent/*`, `docs/dev/pipeline.md`, `docs/dev/testing.md`, `docs/dev/adeu-integration.md`, `docs/dev/contracts/stage-api.md` | L2.2, L3.1, L3.2 | Semua contoh punya `report_name` eksplisit; test missing/empty; tidak ada flag `--report-name`; docs menyatakan field wajib. | L3 |
| L4.1 | Arsipkan plan lama | `docs/dev/restructure-plan.md`, `docs/dev/duplication-map.md`, `docs/dev/archive/*`, `docs/README.md`, tautan masuk | S5 | Kedua dokumen pindah ke archive dengan status superseded; tidak ada tautan rusak; plan ini menjadi acuan. | L4 |

Gate per lane:

- L1: `uv lock --check`, `uv sync --extra dev`, full unit test, `docgen check examples/thesis-single/document.md`, build thesis DOCX/PDF.
- L2: unit test untuk config, document, terms, layout, blocks, dan stage terkait; full unit test; `docgen check` semua contoh.
- L2.1: ubah TSV ke `term<TAB>italic` dan pastikan semua entri dimuat sebelum menghapus `_LEGACY_GLOSSARY_HEADER`. Jangan hapus parser header lama lebih dulu.
- L3: unit test metadata dan cli; integration thesis; semua contoh punya nama output; build thesis.
- L4: link check 0 broken; tidak ada referensi aktif ke plan lama selain archive.

Catatan ownership Fase 2:

- `pipeline.py` dimiliki L2 karena L2.3 menghapus `StageSpec.owner`. L3.2 menyerahkan perubahan fallback `report_name`; L2 menerapkannya sekali. L3 tidak mengedit file yang sama secara paralel.
- `docs/dev/contracts/config.md` dimiliki L2. L3 menyerahkan teks `report_name` wajib; L2 menerapkannya sekali.
- `document.py` dimiliki L2. L3 tidak mengedit file ini.
- `metadata.py` dimiliki L3.1. L2 menyerahkan penghapusan `normalize_author`; L3.1 menerapkannya bersama `report_name`.
- `tests/unit/test_front_matter.py` dimiliki L2.2 untuk penghapusan `legacy_toc`; L3.3 menambahkan `report_name` setelah L2.2 selesai.
- Tidak ada lane yang boleh memperbaiki file lane lain tanpa handoff eksplisit.

### Fase 3 - Naming dan reusable P0

Tujuan: memindahkan modul ke lapisan yang benar dan menyatukan helper DOCX yang berulang.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| N1 | Pindahkan heading Markdown | `docx/headings.py`, `markdown/headings.py`, `markdown/__init__.py`, `stages/front_matter.py`, `tests/unit/test_docx_headings.py`, `docs/dev/docx.md` | S5 | `docgen.docx.headings` tidak ada; `HeadingError` menjadi `MarkdownHeadingError` yang mewarisi `DocgenError`; tes pindah ke `tests/unit/test_markdown_headings.py`; output heading identik. | N-A |
| N2 | Pindahkan Adeu | `features/adeu/**`, `adeu/**`, `cli.py`, `pipeline.py`, tests Adeu, `docs/dev/adeu-integration.md` | S5 | `features/` hilang; import `docgen.adeu.*`; `python -m docgen.adeu.cli` berjalan; manifest dan reconcile identik. | N-B |
| N3 | Pindahkan script Word | `resources/word.ps1`, `scripts/word.ps1`, `stages/office.py`, `tests/unit/test_office.py`, `tests/integration/test_lists_word.py`, `docs/dev/pdf.md`, `docs/dev/repo-map.md` | S5 | `resources/` hilang; loader mencari `scripts/word.ps1`; grep `resources/word.ps1` kosong di kode aktif; Word test lulus. | N-A |
| N4 | Rename stage caption | `pipeline.py`, `stages/captions.py`, tests, docs | N2 | `StageName.CAPTIONS == "captions"`; `captions/figures` hilang dari kode dan docs aktif; output identik. | N-B |
| R1 | Modul `docx/paragraphs.py` | `docx/paragraphs.py`, `docx/__init__.py`, `docx/xml.py`, `docx/bookmarks.py`, `docx/captions.py`, `docx/fields.py`, `docx/layout.py`, `docx/sections.py`, `docx/tables.py`, `docx/terms.py`, `stages/lists.py` | N4 | `document_body`, `body_children`, `paragraph_style_id`, `heading_level`, `paragraph_text`, `remove_direct_children`, `int_attribute` hanya didefinisikan di `paragraphs.py`; export `docx/__init__.py` diperbarui; golden c14n sama. | R |
| R2 | Modul `docx/runs.py` | `docx/runs.py`, `docx/fields.py`, `docx/sections.py`, `docx/captions.py`, `docx/terms.py`, `docx/tables.py`, `stages/lists.py`, `stages/page_numbers.py` | R1 | `make_run`, `append_text_run`, `clone_run`, `copy_rpr`, `strip_bold_from_rpr` hanya di `runs.py`; tidak ada `_new_run` lokal; golden c14n sama. | R |
| R3 | Modul `docx/numbering.py` | `docx/numbering.py`, `docx/captions.py`, `docx/layout.py`, `docx/sections.py`, tests captions | R2 | `roman_to_int`, `chapter_number`, dan helper format Roman hanya di `numbering.py`; `markdown/headings.py` tetap mandiri; golden caption sama. | R |
| R4 | Modul `docx/page.py` | `docx/page.py`, `docx/sections.py`, `stages/front_matter.py`, `stages/style_reference.py`, tests | R3 | Konstanta A4 dan Letter serta helper ukuran/margin hanya di `page.py`; tidak ada map ukuran halaman di stage; golden section sama. | R |

Urutan eksekusi:

1. N1 dan N3 paralel karena file-disjoint.
2. N2 lalu N4 karena keduanya menyentuh `pipeline.py`.
3. R1, R2, R3, dan R4 berurutan. Keempatnya menyentuh modul `docx/` yang sama, jadi tidak boleh paralel.

Acceptance fase: tidak ada perubahan output; golden c14n thesis lulus; unit test lulus; Word test untuk field dan list lulus di Windows.

### Fase 3.5 - Zero fallback

Tujuan: menghapus jalur cadangan diam-diam agar satu input menghasilkan satu output dan error menunjuk penyebab sebenarnya.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| Z1 | Pandoc wajib artifact `markdown` | `src/docgen/stages/pandoc.py`, `tests/unit/test_pandoc_stage.py`, tests terkait | N4 | `_markdown_path` hanya menerima artifact `markdown`; fallback `workspace/front_matter.md` hilang; tidak ada file cadangan yang dibaca; `PANDOC-INPUT` dipertahankan. | Z |
| Z2 | Satu sumber `content_width` | `src/docgen/docx/layout.py`, `src/docgen/docx/tables.py`, `src/docgen/stages/equations.py`, tests | R4 | Hanya satu fungsi/konstanta lebar konten; fallback 9072/9360 dan `DEFAULT_RIGHT_TAB_TWIPS` 9072 dihapus atau diturunkan dari satu sumber; lebar tidak tersedia → error domain, bukan angka tebakan. | Z |
| Z3 | Path reconcile tunggal | `src/docgen/adeu/reconcile.py`, `src/docgen/adeu/cli.py`, tests | N2 | `_default_docx_path` tidak mencoba `out/` lalu folder dokumen; path dihitung dari aturan output yang sama dengan build atau diberikan eksplisit; DOCX tidak ada → `ReconcileError` jelas. | Z |
| Z4 | Sumber front matter tunggal | `src/docgen/stages/front_matter.py`, `src/docgen/stages/pandoc.py`, tests | Z1 | `_markdown_source` hanya membaca satu artifact yang dideklarasikan (bukan `markdown` lalu `mermaid.markdown` lalu `ctx.document.body`); tidak ada dual artifact; error `FRONT-MATTER-INPUT` bila sumber tidak ada. | Z |

Catatan:

- `Z5` sudah selesai di N3: loader hanya mencari `scripts/word.ps1`; env override `DOCGEN_WORD_SCRIPT` hanya untuk tes.
- Urutan eksekusi: Z1 → Z4 berurutan; Z2 dan Z3 boleh paralel dengan Z1 karena file-disjoint (pandoc vs layout/tables/equations vs adeu).
- Acceptance fase: output thesis identik (38/38 part XML), unit + integration lulus, tidak ada fallback yang tersisa di grep.

### Fase 4 - Fields dan split module

Tujuan: satu parser field, satu boundary section, satu package terms, dan keputusan config yang terukur.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| F1 | Konsolidasi `docx/fields.py` | `docx/fields.py`, `docx/layout.py`, `docx/terms.py`, `docx/captions.py`, `stages/blank_lines.py`, `stages/page_numbers.py`, `stages/toc.py` | R4 | Satu parser dan scanner field; `insert_field(switches, position, result)`; `insert_seq` menjadi wrapper tipis; `insert_toc` punya opsi `keep_existing` dan `before`; tidak ada parser field kedua. | F-A |
| F2 | Hapus workaround `stages/lists.py` | `stages/lists.py`, `tests/unit/test_lists.py`, `tests/integration/test_lists_word.py` | F1 | Workaround field dan SDT lama hilang; list memakai API `fields.py`; Word test lulus. | F-B |
| F3 | Split `docx/sections.py` | `docx/sections.py`, `docx/heading_numbering.py`, `docx/numbering.py`, `stages/front_matter.py`, `stages/sections.py`, tests | R4 | Section hanya berisi section, header, footer, page; heading numbering pindah ke `heading_numbering.py`; `heading_numbering.py` memakai `numbering.py`, tidak menduplikasi Roman; output identik. | F-A |
| F4 | Split `docx/terms.py` | `docx/terms.py`, `docx/terms/__init__.py`, `docx/terms/glossary.py`, `docx/terms/model.py`, `docx/terms/apply.py`, `docx/terms/verify.py`, tests terms | F1 | Import `docgen.docx.terms` tetap; `apply_terms`, `verify_terms`, `open_docx` tetap publik; alias lama hilang; tidak ada import melingkar. | F-B |
| F5 | Evaluasi split `config.py` | `config.py`, `config/**` jika dipecah, tests config | F1, F2, F3, F4 | Decision gate dijalankan; jika tetap lebih dari 1.500 LOC atau sulit dites, split menjadi `config/__init__.py`, `models.py`, `parsers.py`, `validation.py`; API publik tetap. | F5 |

Urutan eksekusi:

1. F1 dan F3 paralel karena fields dan sections file-disjoint.
2. F2 dan F4 paralel setelah F1 karena lists dan terms file-disjoint.
3. F5 setelah semua task di atas, dengan decision gate.

Acceptance fase:

- Golden TOC, lists, dan terms lulus.
- Word test `tests/integration/test_lists_word.py` lulus di Windows.
- `document.xml` c14n tidak berubah untuk thesis.
- F3 dan F4 tidak mengubah output.
- F5 hanya dilakukan jika gate menyetujui; keputusan dan alasannya dicatat.

### Fase 5 - Dokumentasi

Tujuan: dokumentasi berlapis, tautan resmi, TOC, dan tanpa komentar historis.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| D1 | Registry referensi | `docs/dev/references.md`, `tools/dev/check_docs.py` | F5 | Semua label dan URL resmi ada di satu registry; checker memeriksa tautan relatif dan URL registry; 0 broken. | D-A |
| D2 | Code style | `docs/dev/code-style.md` | S1 | Memuat tabel rule dengan kolom `Rule`, `Status`, `Alasan`, `Contoh`, `Link resmi`; semua select dan ignore tercakup; link configuration, rules, settings, formatter ada. | D-A |
| D3 | Materi belajar | `docs/dev/learn/00-start-here.md` sampai `06-change-recipes.md` | D5 | Tujuh halaman; setiap halaman punya tujuan, prasyarat, latihan, dan tautan berikutnya; TOC jika lebih dari 150 baris. | D-B |
| D4 | README folder | `src/docgen/README.md`, `src/docgen/docx/README.md`, `src/docgen/stages/README.md`, `src/docgen/markdown/README.md`, `src/docgen/adeu/README.md`, `src/docgen/data/README.md`, `tests/README.md`, `tools/README.md`, `scripts/README.md` | N2, N3, F4, F5 | Setiap README memuat tujuan, ownership, API publik, larangan, dan tautan; tidak ada duplikasi kontrak. | D-A |
| D5 | Pisahkan docs pipeline dan docx | `docs/dev/pipeline/*`, `docs/dev/docx/*`, `docs/dev/glossary.md`, `docs/dev/terms.md`, `docs/dev/README.md`, `docs/README.md` | F5 | `pipeline.md` dan `docx.md` diganti folder; `terms.md` pindah ke `docx/terms.md`; `glossary.md` berisi istilah codebase, bukan duplikat feature terms; indeks docs dan README dev diperbarui; tautan valid. | D-A |
| D6 | TOC dokumen panjang | Semua `docs/**/*.md` | D3, D5 | Setiap dokumen lebih dari 150 baris punya TOC anchor yang valid; checker gagal jika TOC hilang. | D-F |
| D7a | Bersihkan komentar historis di kode | `src/docgen/**` | F5 | Token `WS\d+`, `Fase`, `lane`, `spike`, `cutover`, `legacy`, `docx.lua`, `presets/` hilang dari kode aktif; komentar menjelaskan perilaku sekarang. | D-D |
| D7b | Bersihkan komentar historis di test | `tests/**` | F5 | Token historis hilang; fixture dan baseline bebas Typst; literal `Typst` di `test_golden_fixtures.py` hanya untuk assertion negatif. | D-E |
| D7c | Bersihkan komentar historis di docs | `docs/agent/**`, `docs/dev/**` kecuali `archive/**`, `decisions/**`, dan `refactor-plan.md` | D5 | Token historis hilang dari docs aktif, termasuk sisa `from __future__` di `docs/dev/contributing.md`; ADR, archive, dan plan ini tetap menyimpan instruksi sejarah. | D-E |
| D7d | Bersihkan komentar historis di data dan config | `src/docgen/data/**`, `pyproject.toml` | L1 | Komentar `presets/` dan referensi historis hilang; data menjelaskan nilai sekarang. | D-E |
| D8 | Docstring modul kunci | `pipeline.py`, `config.py`, `errors.py`, `document.py`, fungsi lebih dari 40 baris | D7a | Module docstring menjelaskan tujuan, invariant, API masuk, dan non-goals; fungsi lebih dari 40 baris punya docstring atau dipecah. | D-D |
| D9 | Tautkan dokumentasi resmi | Module docstring dan docs page | D5, D8 | URL dokumentasi eksternal hanya dari registry; namespace XML tidak dihitung sebagai link dokumen; link checker 0 broken; tidak ada link spam. | D-F |

Isi minimum `docs/dev/references.md`: Python 3.15, PEP 649, Ruff configuration, Ruff rules, Ruff settings, Ruff formatter, mypy, pytest, uv, Pandoc, python-docx, OOXML, pypdf, lxml, ruamel.yaml, dan Mermaid. Setiap entri memuat label, URL resmi, dan dipakai di halaman mana.

Aturan D7:

- Token historis yang dilarang di area aktif: `WS` diikuti angka, `Fase`, `lane`, `spike`, `cutover`, `legacy`, `docx.lua`, dan `presets/`.
- ADR di `docs/dev/decisions/` dan isi `docs/dev/archive/` dikecualikan karena memang catatan sejarah.
- `w:legacy` adalah nama elemen OOXML yang sah dan dikecualikan. Yang dilarang adalah identifier, komentar, atau nama tes yang menarasikan sejarah.
- Test trust boundary yang memeriksa artifact lama boleh memakai literal nama artifact sebagai data negatif, tetapi kumpulkan dalam satu konstanta `FORBIDDEN_ARTIFACTS`; jangan menulis komentar sejarah.
- `test_golden_fixtures.py` boleh memakai literal `Typst`/`typst` hanya untuk assertion negatif terhadap fixture. Literal itu bukan konten fixture.
- Ganti komentar dengan perilaku sekarang, bukan dengan sinonim token lama.
- Jangan menghapus komentar yang menjelaskan invariant atau alasan teknis yang masih berlaku.

Aturan D8:

- Module docstring wajib ada untuk `pipeline.py`, `config.py` atau `config/__init__.py` jika F5 memecah config, `errors.py`, dan `document.py`.
- Fungsi lebih dari 40 baris wajib punya docstring yang menjelaskan input, output, invariant, dan error utama.
- Docstring tidak boleh mengulang nama fungsi atau menulis sejarah.
- Jika fungsi lebih dari 80 baris dan punya banyak tanggung jawab, pecah pada fase terkait, bukan hanya menambah docstring.

Acceptance fase:

- Link checker 0 broken.
- Tidak ada token historis di area aktif.
- Semua dokumen lebih dari 150 baris punya TOC.
- Tabel rule di `code-style.md` lengkap dan setiap baris punya link resmi.
- Tidak ada halaman docs yang menjadi sumber kebenaran kedua untuk kontrak yang sama.

### Fase 6 - Final gate

Tujuan: membuktikan tidak ada regresi, lalu memberi tag rilis.

| ID | Task | File | Dependency | Acceptance | Lane |
| --- | --- | --- | --- | --- | --- |
| G1 | Style gate | Tidak ada file baru | D9 | `ruff format --check`, `ruff check`, dan `mypy` lulus. | G |
| G2 | Test gate | Tidak ada file baru | G1 | Full suite minimal 475 passed; setelah P0.4 tidak ada skip karena fixture hilang; skip PDF hanya platform Windows; skip platform/tool existing tidak bertambah; baseline 2 subtests tidak hilang; tidak ada tes yang hilang. | G |
| G3 | Build dan inspeksi | `examples/thesis-single/document.md` | G2 | Build DOCX dan PDF di Windows; TOC, daftar tabel, daftar gambar, caption, persamaan, dan istilah diperiksa; tidak ada placeholder atau error field. | G |
| G4 | Bersihkan archive | `docs/dev/archive/*`, tautan | G3 | Archive dihapus jika isinya sudah tercakup dan tidak ada tautan; jika dipertahankan, status archived jelas; `git status` bersih setelah keputusan. | G |
| G5 | Versi dan tag | `pyproject.toml`, `src/docgen/__init__.py` | G4 | Versi `0.2.0`; annotated tag `v0.2.0`; `git status` bersih; tidak dipush. | G |

Perintah gate:

```bash
uv run --project . ruff format --check src tests
uv run --project . ruff check src tests
uv run --project . --extra dev mypy
uv run --project . pytest
uv run --project . docgen check examples/thesis-single/document.md
uv run --project . docgen build examples/thesis-single/document.md --target both
git status --porcelain
```

G3 hanya menjalankan `--target both` di Windows dengan Microsoft Word. Di Debian, build DOCX saja dan catat bahwa PDF tidak diverifikasi.

## 4. Parallel execution map

| Fase | Lane | Scope | File ownership | Dependency | Barrier |
| --- | --- | --- | --- | --- | --- |
| 0 | B0 | Baseline dan keputusan | Golden tests, fixture, plan, ADR | - | Barrier setelah P0.3 |
| 1 | S | Mechanical style | `pyproject.toml`, seluruh `src`, seluruh `tests`, `docs/dev/contributing.md` | B0 | Barrier setelah S5 |
| 2 | L1 | Dependency | `pyproject.toml`, `uv.lock`, docs packaging | S5 | Gate lane |
| 2 | L2 | Legacy | `config.py`, `document.py`, `docx/layout.py`, `docx/terms.py`, `markdown/blocks.py`, stage aliases, unit tests terkait, `contracts/config.md` | S5 | Gate lane |
| 2 | L3 | `report_name` | `metadata.py`, `stages/pandoc.py`, `stages/office.py`, `adeu/reconcile.py`, examples, integration tests, docs agent | S5, handoff L2.2 untuk `test_front_matter.py` | Gate lane |
| 2 | L4 | Archive docs | `docs/dev/archive/*`, `docs/README.md`, tautan masuk | S5 | Gate lane |
| 3 | N-A | N1 dan N3 | `markdown/headings.py`, `scripts/word.ps1`, `stages/front_matter.py`, `stages/office.py`, tests terkait | S5 | Barrier setelah N-A |
| 3 | N-B | N2 lalu N4 | `adeu/**`, `cli.py`, `pipeline.py`, `stages/captions.py`, tests terkait | S5 | Barrier setelah N4 |
| 3 | R | R1 sampai R4 | Seluruh `docx/` dan stage pemanggil | N4 | Barrier setelah R4 |
| 4 | F-A | F1 dan F3 | `docx/fields.py`, `docx/layout.py`, `docx/sections.py`, `docx/heading_numbering.py`, tests terkait | R4 | Barrier setelah F-A |
| 4 | F-B | F2 dan F4 | `stages/lists.py`, `docx/terms/**`, tests terkait | F1 | Barrier setelah F-B |
| 4 | F5 | Config split decision | `config.py` atau `config/**`, tests config | F-A, F-B | Decision gate |
| 5 | D-A | D1, D2, D4, D5 | `references.md`, `code-style.md`, README folder, docs pipeline/docx | F5 | Barrier setelah D-A |
| 5 | D-B | D3 | `docs/dev/learn/**` | D5 | Barrier setelah D-B |
| 5 | D-C | D7a lalu D8 | `src/docgen/**` | F5 | Barrier setelah D8 |
| 5 | D-D | D7b, D7c, D7d | `tests/**`, docs aktif, data, `pyproject.toml` | F5, D5 | Barrier setelah D-D |
| 5 | D-E | D6 dan D9 | Semua docs, module docstring | D3, D5, D8 | Barrier setelah D-E |
| 6 | G | Final gate | Semua file | D6, D9 | Barrier final |

Aturan eksekusi:

- Satu file hanya punya satu owner aktif.
- Lane tidak boleh mengedit file lane lain. Jika butuh perubahan, kirim handoff tertulis ke owner.
- Tidak ada big-bang. Setiap task harus lulus acceptance sendiri sebelum task berikutnya yang bergantung dimulai.
- Task yang selesai lebih cepat tidak menunggu sibling yang tidak berhubungan.
- Barrier hanya dipakai untuk dependency nyata, shared file, atau final gate.
- Full test dijalankan ulang setelah merge task yang menyentuh area bersama.
- Build thesis dan Word test dijadwalkan sebagai resource eksklusif, tidak paralel dengan lane yang mengubah DOCX.

Shared file dan owner tunggal:

| File | Owner | Aturan |
| --- | --- | --- |
| `pyproject.toml` | S1 lalu S5 lalu L1 | S1 menambah Ruff/mypy; S5 boleh menyesuaikan mypy tanpa `ignore_errors` global; L1 memindahkan dependency. Semuanya berurutan. |
| `pipeline.py` | L2 lalu N2 lalu N4 | L2 menghapus `StageSpec.owner` dan menerapkan handoff L3.2; N2 memindahkan import Adeu; N4 mengubah nama stage. |
| `document.py` | L2 | L2 menghapus legacy. L3 tidak mengedit file ini. |
| `metadata.py` | L3.1 | L2 menyerahkan penghapusan `normalize_author`; L3.1 menerapkannya bersama `report_name`. |
| `tests/unit/test_front_matter.py` | L2.2 lalu L3.3 | L2.2 menghapus `legacy_toc`; L3.3 menambahkan `report_name` setelah L2.2 selesai. |
| `docs/dev/contracts/config.md` | L2 | L3 menyerahkan teks `report_name`; L2 menerapkan sekali. |
| `docx/terms.py` | L2 lalu F1 lalu F4 | L2 menghapus alias; F1 memakai scanner field; F4 memecah package. |
| `docx/sections.py` | R1 lalu R3 lalu R4 lalu F3 | Train sekuensial, tidak paralel. |
| `docs/README.md` | L4 lalu D5 | L4 memperbarui tautan archive; D5 memperbarui indeks final. |

## 5. Acceptance global

| Area | Acceptance | Bukti |
| --- | --- | --- |
| Legacy | Tidak ada `CFG-LEGACY`, `_FORMAT_LEGACY`, `_STRUCTURE_LEGACY`, `_DOCUMENT_LEGACY`, `_DOCUMENT_COMPAT_KEYS`, `legacy_toc`, atau komentar historis di area aktif. Pengecualian: `w:legacy`, ADR, archive, dan literal negative test. | `rg` bersih; review diff. |
| API mati | Semua simbol tabel 1.1 hilang; tidak ada alias pengganti. | `rg` per simbol; test import. |
| `report_name` | Wajib di front matter; tidak ada default; tidak ada flag CLI. | Test missing, empty, whitespace; test unknown CLI option; contoh valid. |
| Dependency | `python-docx` dev only; `Pillow` tidak ada; `pypdf` dev. | `pyproject.toml`, `uv.lock`, metadata wheel. |
| Style | Ruff format, Ruff lint, dan mypy lulus; config berkomentar; alasan lengkap di `code-style.md`. | Gate G1; tabel rule lengkap. |
| Dokumentasi | Lapisan docs, TOC, references registry, README folder, learn 00-06. | Link checker; TOC checker; review indeks. |
| PDF E2E | `test_pdf_build_matches_baseline` membangun thesis PDF di Windows dan memverifikasi page count/TOC/teks kunci; tidak ada skip karena fixture hilang. | `pytest -m windows tests/integration/test_golden_pdf.py`; `pdf-baseline.json`. |
| Fixture | `pdf-baseline.json` dan `laporan-baseline.docx` bebas Typst; tidak ada `laporan-baseline.pdf`; JSON tidak punya field `fixture`. | `test_golden_fixtures.py`; `rg -i typst`; `test ! -e`. |
| Perilaku | Minimal 475 passed; setelah P0.4 tidak ada skip fixture; skip PDF hanya platform Windows; baseline 2 subtests tidak hilang; build thesis DOCX dan PDF; inspect output. | Gate G2 dan G3. |
| Repo | `git status` bersih; tidak ada generated artifact tracked; `acuan/` tidak berubah. | Gate G5; `git status --porcelain`; `git check-ignore acuan/`. |
| Naming | `docx/headings.py`, `features/`, `resources/`, `captions/figures` tidak ada di kode aktif. | `rg`; tree review. |

Perintah verifikasi global:

```bash
rg "CFG-LEGACY|_FORMAT_LEGACY|_STRUCTURE_LEGACY|_DOCUMENT_LEGACY|_DOCUMENT_COMPAT_KEYS|legacy_toc" src tests docs -g '!docs/dev/refactor-plan.md' -g '!docs/dev/archive/**' -g '!docs/dev/decisions/**'
rg "from __future__ import annotations" src tests tools
rg "Pillow" pyproject.toml uv.lock
rg "python-docx" pyproject.toml
rg "DEFAULT_REPORT_NAME|or \"Tugas\"" src
rg "normalize_author|ParagraphIdError|plain_inline|StageSpec.owner" src tests
rg "captions/figures|docx\.headings|features/adeu|resources/word\.ps1" src tests docs -g '!docs/dev/refactor-plan.md' -g '!docs/dev/archive/**' -g '!docs/dev/decisions/**'
rg "WS[0-9]+|Fase|lane|spike|cutover|legacy|docx\.lua|presets/" src tests docs -g '!docs/dev/refactor-plan.md' -g '!docs/dev/archive/**' -g '!docs/dev/decisions/**'
rg -n "PDF_FIXTURE|fixture PDF tidak ada|pytest\.skip" tests/integration/test_golden_pdf.py
rg -in "typst" tests/fixtures/golden/pdf-baseline.json tests/integration/test_golden_pdf.py tests/integration/test_golden_docx.py
test ! -e tests/fixtures/golden/laporan-baseline.pdf
uv run --project . pytest tests/unit/test_golden_fixtures.py
uv run --project . pytest -m windows tests/integration/test_golden_pdf.py
uv run --project . ruff format --check src tests
uv run --project . ruff check src tests
uv run --project . --extra dev mypy
uv run --project . pytest
```

Catatan verifikasi:

- `pytest -m windows` untuk PDF hanya dijalankan di Windows. Di Debian, full `pytest` mencatat skip platform untuk test PDF, bukan skip fixture.
- `test_golden_fixtures.py` membaca XML di dalam DOCX, jadi pemeriksaan Typst mencakup isi biner fixture.
- `rg -i typst` pada file teks melengkapi pemeriksaan DOCX.

Catatan grep:

- `refactor-plan.md` sendiri dikecualikan dari pemeriksaan token historis karena memuat instruksi penghapusan.
- `docs/dev/archive/**` dan `docs/dev/decisions/**` dikecualikan dari pemeriksaan komentar historis.
- `acuan/**` tidak pernah menjadi target grep karena ignored dan tidak dirujuk.
- `w:legacy` adalah elemen OOXML sah, bukan komentar historis.
- Test trust boundary boleh memakai literal `docx.lua` sebagai data negatif di `FORBIDDEN_ARTIFACTS`, bukan sebagai komentar atau narasi.

## 6. Keputusan yang telah dikonfirmasi

Item berikut telah dikonfirmasi pada 2026-11-10 dengan pilihan rekomendasi di bawah. Kelima keputusan mengikat dan dicatat di P0.2 serta [ADR 0008](decisions/0008-refactor-boundaries.md).

| Item | Pilihan | Rekomendasi | Alasan | Dampak jika berbeda | Status |
| --- | --- | --- | --- | --- | --- |
| 1. Adapter Word | Pertahankan PowerShell atau migrasi ke `pywin32` | Pertahankan `scripts/word.ps1` | Tidak menambah dependency Python, script kecil, dan sudah menjadi kontrak. Migrasi COM menambah risiko platform. | Migrasi menambah test Windows, packaging, dan error handling baru. | **confirmed** |
| 2. Future import | Hapus atau pertahankan | Hapus seluruh `from __future__ import annotations` | Target Python 3.15 dan PEP 649 sudah membuat anotasi lazy. Import future menjadi noise. | Jika dipertahankan, S2 dibatalkan dan code style mencatat pengecualian. | **confirmed** |
| 3. Split `config.py` | Tunda/evaluate atau split sekarang | Tunda dan evaluate setelah F1-F4 | Baseline 2.403 LOC memang besar, tetapi split sebelum API stabil berisiko churn. Gate F5 memutuskan dengan data. | Split sekarang menambah lane besar dan memperlambat Fase 4. | **confirmed** |
| 4. Dokumen historis | Arsipkan atau hapus setelah plan baru | Arsipkan dulu, hapus di Fase 6 jika tidak ada nilai audit | Archive menjaga jejak keputusan selama refactor; G4 mencegah archive permanen yang tidak perlu. | Hapus sekarang menghilangkan konteks audit; pertahankan permanen menambah beban docs. | **confirmed** |
| 5. Naming moves | Semua move atau subset | Lakukan semua: headings, adeu, scripts, captions | Keempatnya memperbaiki lapisan dan menghilangkan nama menyesatkan. Tidak ada alasan kuat untuk menyisakan subset. | Subset membuat struktur target tidak konsisten dan menyisakan tech debt. | **confirmed** |

Kelima keputusan telah dikonfirmasi dan dicatat di P0.2 serta [ADR 0008](decisions/0008-refactor-boundaries.md). Setelah tag baseline, perubahan pilihan harus melalui ADR baru, bukan perubahan di tengah fase.

Keputusan tambahan yang telah dikonfirmasi:

- Zero fallback Z1-Z4 disetujui dan dijadwalkan sebelum Fase 4; Z5 sudah selesai.
- DOCX tanpa Word memakai Opsi A: TOC kosong + peringatan; docgen tidak menulis `w:updateFields`; helper `update_fields_enabled`/`strip_update_fields` yang tidak dipakai dihapus.
- Split `config.py` (F5) hanya dilakukan bila >1.500 LOC atau sulit dites; keputusan dan alasan dicatat saat gate.
- `docs/dev/archive` dihapus pada G4; riwayat tetap tersedia di git.
- Tidak ada backend PDF baru (LibreOffice/Aspose); Word tetap default karena fidelity pagination. Backend alternatif hanya lewat keputusan baru di luar plan.
