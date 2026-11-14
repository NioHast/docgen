# ADR 0011: Pembersihan F3 dan Penghapusan Legacy

- Status: diterima; pembersihan diterapkan di working tree
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L01, L02, L13, L16, L18, L20, L25
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 13.5, 16, 18.1, dan 18.12; ADR 0002, 0006, 0007-0010

## Daftar Isi

- [Konteks](#konteks)
- [Keputusan](#keputusan)
- [Prasyarat dan batas](#prasyarat-dan-batas)
- [Daftar hapus](#daftar-hapus)
- [Daftar update](#daftar-update)
- [Inventaris referensi aktif](#inventaris-referensi-aktif)
- [Urutan operasi](#urutan-operasi)
- [Rollback](#rollback)
- [Risiko dan mitigasi](#risiko-dan-mitigasi)
- [Definisi selesai dan perintah](#definisi-selesai-dan-perintah)
- [Konsekuensi](#konsekuensi)
- [Alternatif yang ditolak](#alternatif-yang-ditolak)

## Konteks

F3 adalah fase integrasi dan finalisasi. Setelah F3-ACCEPT lulus, kode lama
tidak boleh hidup berdampingan dengan AutoOffice: package `docgen`, entry point
`docgen`, tes legacy, adapter PowerShell, tool pengembang legacy, dan dokumen
yang hanya berlaku untuk `docgen` harus dihapus. F3-RENAME adalah langkah
eksternal terpisah dan tidak boleh dicampur dengan commit penghapusan.

Pengukuran pada `autooffice/f1` sebelum dokumen ini ditulis:

- `src/docgen/**`: 81 berkas tracked, termasuk 12 berkas package data.
- `tests/unit/**`: 37 berkas; 35 di antaranya mengimpor `docgen`.
- `tests/integration/**`: 7 berkas; 6 mengimpor `docgen`, 1 memakai path
  `src/docgen`.
- `tests/e2e/**`: 2 berkas; 1 mengimpor `docgen`.
- `tests/packaging/**`: 3 berkas; 1 menjalankan entry point `docgen`.
- `tools/dev/**`: 10 berkas; 6 tes root mengimpornya dan 2 modul audit
  mengimpor `docgen`.
- `scripts/**`: 3 berkas tracked; `scripts/check.ps1` sudah dihapus di working
  tree, `scripts/word.ps1` masih dipakai jalur legacy.
- `docs/dev/contracts/**`: 3 berkas kontrak internal lama yang menduplikasi
  kontrak normatif di `docs/contracts/`.
- Tidak ada `package.json`, `node_modules`, sumber JavaScript, `design-system/`,
  `decks/`, atau `.github/workflows` yang tersisa di repo ini.

Pemindaian `rg` case-sensitive di luar arsip, plan, log, dan riwayat menemukan
469 kemunculan `docgen`, 22 kemunculan `deck-studio`, dan 34 kemunculan
`word.ps1`. Angka ini mencakup identifier yang sengaja dipertahankan
(`DocgenError`, `DOCGEN_WINWORD`, `DOCGEN_PANDOC`) dan guard negatif pada tes.
Inventaris per berkas ada di bagian [Inventaris referensi aktif](#inventaris-referensi-aktif).

## Keputusan

1. Hapus total `src/docgen/**` setelah parity test terhadap baseline legacy
   lulus. Tidak ada shim, alias package, alias import, atau fallback ke
   `src/docgen`.
2. Hapus tes legacy setelah invariannya diporting ke `tests/docx/**` atau
   `tests/acceptance/**`. Fixture golden yang masih dipakai tidak dihapus.
3. Pindahkan checker yang masih dipakai dari `tools/dev/` ke `tools/quality/`
   (`check_docs`, `check_tests`, dan `check_coverage`), lalu hapus
   `tools/dev/**`. `audit_terms*.py`, `check_prose.py`, dan `rules.yml` tidak
   diporting: AutoOffice tidak menyertakan checker prosa atau audit istilah
   terpisah. Gate istilah ditangani stage `terms` dan daftar
   `.laporan/istilah-baru.txt`.
4. Hapus `scripts/word.ps1` dan `scripts/README.md`; adapter Word AutoOffice
   tetap `autooffice.pdf.word`. Tidak ada pengganti PowerShell.
5. Hapus tiga kontrak internal lama di `docs/dev/contracts/` dan arahkan
   tautan ke kontrak normatif di `docs/contracts/` serta halaman
   `docs/dev/pipeline/` dan `docs/dev/formats.md`.
6. Ubah metadata package menjadi satu package `autooffice`: nama, deskripsi,
   entry point, package-data, mypy, import-linter, dan ruff per-file ignore.
7. Bersihkan docstring, path paket, nama prog, nama logger, prefix temp, dan
   lock file runtime dari kata `docgen`. Identifier `DocgenError`, kode error
   `DOCGEN`, `DOCGEN_WINWORD`, `DOCGEN_PANDOC`, dan `LAPORAN_PANDOC`
   dipertahankan sampai ada ADR terpisah karena merupakan nama kelas, kode
   error, atau environment variable yang sudah dipakai pengguna.
8. Implementasikan `tools/quality/check_no_legacy.py` sebagai pemeriksa penuh,
   bukan lagi list-only. Pemeriksa memakai allowlist eksplisit untuk arsip,
   ADR historis, fixture golden, dan guard negatif.
9. Rename repo GitHub dan folder lokal adalah langkah F3-RENAME terpisah.
   Langkah ini membutuhkan persetujuan eksplisit pemilik dan tidak boleh
   dilakukan dalam commit penghapusan.
10. Tag `f3-cleanup-base` dan branch `backup/pre-f3-cleanup` dibuat sebelum
    perubahan apa pun. Keduanya dipertahankan sampai F3-GATE dan satu release
    selesai.

## Prasyarat dan batas

- F3-ACCEPT lulus: acceptance matrix, visual golden, live Google smoke, COM
  smoke, dan build `all` sudah memiliki bukti.
- Semua lane F2 sudah merged ke `autooffice/integration`; branch freeze aktif
  dan tidak ada worker yang menulis.
- Working tree bersih sebelum tag. Perubahan F1/F2 yang belum commit harus
  di-commit atau di-stash lebih dulu; tag tidak boleh menunjuk working tree
  kotor.
- Mesin gate adalah Windows dengan Word dan PowerPoint desktop, `uv`, Pandoc,
  dan `mmdc` tersedia.
- Tidak ada push, merge, atau rename tanpa persetujuan pemilik.
- Penghapusan tidak boleh dimulai sebelum parity test baru hijau terhadap
  baseline yang dibuat dari kode legacy.

## Daftar hapus

Jumlah di bawah adalah jumlah berkas tracked pada `autooffice/f1` saat ADR ini
ditulis. `git rm` harus dijalankan dari akar repo.

| Path | Jumlah | Alasan dan pengganti |
| --- | --- | --- |
| `src/docgen/**` | 81 | Package legacy. Pengganti: `src/autooffice/docx/**` dan `src/autooffice/cli/**` sesuai peta 16.1. |
| `src/docgen.egg-info/**` | ignored | Artefak editable install. Hapus dari working tree, bukan dari Git. |
| `tests/unit/**` | 37 | Suite legacy. Invarian golden yang masih dipakai diporting ke `tests/docx/test_command.py` dan `tests/docx/test_docx_package.py`; 35 berkas lain mengimpor `docgen`. |
| `tests/integration/**` | 7 | Port invariant golden DOCX/PDF dan pipeline ke `tests/docx/**`; sisanya dihapus. |
| `tests/e2e/**` | 2 | Pengganti acceptance ada di `tests/acceptance/**`; fixture `tests/fixtures/e2e/thesis/**` dipertahankan bila dipakai acceptance. |
| `tests/packaging/test_repo_local.py` | 1 | Diganti `tests/packaging/test_autooffice_package.py` untuk metadata package, entry point, dan package data. |
| `tests/test_audit_terms.py` | 1 | Dihapus; AutoOffice tidak menyertakan audit istilah terpisah. |
| `tests/test_check_coverage.py` | 1 | Pengganti `tests/tools/test_coverage_policy.py`. |
| `tests/test_check_docs.py` | 1 | Pengganti `tests/tools/test_quality_tools.py`. |
| `tests/test_check_tests.py` | 1 | Pengganti `tests/tools/test_quality_tools.py`. |
| `tests/test_check_prose.py` | 1 | Dihapus; checker prosa tidak dipertahankan. |
| `tests/test_check_prose_docx.py` | 1 | Dihapus; checker prosa tidak dipertahankan. |
| `tests/factories/**` | 2 | Tidak dipakai suite ported setelah `rg "tests.factories"` bersih. |
| `tools/dev/**` | 10 | Checker yang masih dipakai (`check_docs`, `check_tests`, `check_coverage`) diporting ke `tools/quality/`; `audit_terms*.py`, `check_prose.py`, dan `rules.yml` dihapus tanpa port. |
| `scripts/word.ps1` | 1 | Adapter legacy. Pengganti: `autooffice.pdf.word`. |
| `scripts/README.md` | 1 | Dokumentasi adapter legacy; tidak berlaku setelah `word.ps1` dihapus. |
| `docs/dev/contracts/config.md` | 1 | Duplikasi kontrak lama. Isi yang masih mengikat dipindahkan ke `docs/dev/formats.md` dan `docs/contracts/docx.md`. |
| `docs/dev/contracts/docx-api.md` | 1 | Duplikasi kontrak lama. Pengganti: `docs/contracts/docx.md` dan `docs/dev/docx/**`. |
| `docs/dev/contracts/stage-api.md` | 1 | Duplikasi kontrak lama. Pengganti: `docs/contracts/cli.md` dan `docs/dev/pipeline/**`. |
| `scripts/check.ps1` | 0 | Sudah berstatus deleted di working tree; pastikan deletion ikut ter-stage. |
| `package.json`, `node_modules`, sumber JS, `design-system/`, `decks/`, `src/render/`, `.github/workflows/**` | 0 | Tidak ada di repo. Verifikasi dengan `git ls-files`; jangan membuat penghapusan fiktif. |

Yang tidak boleh dihapus:

- `tests/fixtures/golden/**`, termasuk `laporan-baseline.docx`,
  `baseline-4a5b777.json`, `pdf-baseline.json`, dan baseline baru
  `tests/fixtures/golden/docx/**`.
- `tests/fixtures/docx/**`, `paragraph_ids/**`, `reconcile/**`,
  `format_figures/**`, `charts/**`, `copy/**`, `deck/**`, dan `google/**`
  selama masih dipakai suite ported.
- `tests/conftest.py`, `tests/_helpers/**`, dan `tests/test_import_contracts.py`
  setelah diupdate.
- `docs/dev/archive/**` dan `docs/dev/decisions/**`; keduanya adalah arsip
  historis dan dikecualikan dari pemindaian aktif.
- `docs/decisions/0001-0010*.md` dan `0012*.md`; ADR yang sudah diterima tidak
  diedit diam-diam.

## Daftar update

### `pyproject.toml` dan lock

| Lokasi | Sekarang | Menjadi |
| --- | --- | --- |
| `[project].name` baris 6 | `docgen` | `autooffice` |
| `[project].description` baris 8 | deskripsi design system | `Pipeline dokumen dan presentasi AutoOffice dari Markdown dan YAML.` |
| `[project.scripts]` baris 40 | `docgen = "docgen.cli:main"` | dihapus; sisakan `autooffice = "autooffice.cli.main:main"` |
| `[tool.setuptools.package-data]` baris 50 | `docgen = ["data/**/*"]` | dihapus |
| package-data `autooffice` baris 51-56 | `data/**/*` | hapus pola `data/**/*` karena `src/autooffice/data/` tidak ada; pertahankan `assets/**/*`, `design/data/**/*`, `docx/data/**/*` |
| `[tool.ruff.lint.per-file-ignores]` baris 105 | `src/docgen/docx/names.py` | dihapus; `src/autooffice/docx/package/names.py` sudah memakai `# noqa: E741` inline |
| `[tool.mypy].files` baris 110 | `["src/docgen", "src/autooffice"]` | `["src/autooffice"]` |
| override mypy `docgen`, `docgen.*` baris 127-138 | blok non-strict legacy | dihapus seluruhnya |
| `[tool.importlinter].root_packages` baris 142 | `["docgen", "autooffice"]` | `["autooffice"]` |
| kontrak importlinter baris 144-194 | lima kontrak `docgen.*` | dihapus seluruhnya |
| `uv.lock` | package `docgen` editable | jalankan `uv lock`; package menjadi `autooffice` |

### Root dan metadata

| Berkas | Perubahan |
| --- | --- |
| `LICENSE` | `Copyright (c) 2026 docgen contributors` menjadi `Copyright (c) 2026 AutoOffice contributors`. |
| `AGENTS.md` | Ganti larangan lama dengan larangan menambahkan kembali package/entry point lama; sebut bahwa arsip historis hanya boleh di `docs/dev/archive/**`. |
| `README.md` | Hapus atribusi path lama; sebut kaidah prosa diadaptasi dari proyek naskah-id. |
| `pytest.ini` | Hapus marker `e2e` yang tidak dipakai; pertahankan `unit`, `integration`, `packaging`, `word`, `windows`, dan `slow`. |

### Indeks dokumentasi

| Berkas | Perubahan |
| --- | --- |
| `docs/README.md` | Hapus baris `dev/contracts/**`; arahkan kontrak DOCX ke `contracts/docx.md`; pindahkan ADR dev lama ke bagian historis; tautkan `dev/f3-cleanup.md` dan `decisions/0011-f3-cleanup.md`. |
| `docs/dev/README.md` | Hapus bagian Kontrak yang menautkan `dev/contracts/**`; tambahkan `f3-cleanup.md`; tandai `decisions/**` sebagai historis. |
| `docs/contracts/README.md` | Ganti deskripsi `docx.md` dari "parity docgen" menjadi "parity baseline DOCX"; ubah perintah checker ke `tools/quality/check_docs.py`. |
| `docs/decisions/README.md` | Tambahkan baris ADR 0011. |
| `tests/README.md` | Tulis ulang untuk suite AutoOffice: `tests/docx`, `tests/deck`, `tests/google`, `tests/pdf`, `tests/acceptance`, `tests/packaging`, dan `tests/tools`; hapus referensi `docgen`, `tools.dev`, `e2e` lama, dan `word.ps1`. |
| `tools/README.md` | Tulis ulang: `tools/quality/**` adalah rumah checker; `tools/dev/` tidak ada; tidak ada runtime `docgen`. |

### Halaman dokumentasi aktif

| Berkas atau glob | Perubahan |
| --- | --- |
| `docs/dev/pdf.md` | Hapus seluruh bagian "Legacy docgen: PowerShell", `DOCGEN_POWERSHELL`, `DOCGEN_WORD_SCRIPT`, dan narasi `word.ps1`; sisakan jalur `autooffice.pdf.word` dan Word COM. |
| `docs/dev/com.md` | Hapus `scripts/word.ps1`; ganti lock file menjadi `autooffice-word.lock`. |
| `docs/dev/repo-map.md` | Tulis ulang pohon dan tabel untuk `src/autooffice/**`, `tests/docx/**`, `tests/acceptance/**`, `tests/packaging/**`, `tools/quality/**`; hapus `scripts/`. |
| `docs/dev/packaging.md` | Tulis ulang untuk package `autooffice`, entry point `autooffice`, package-data `assets`, `design/data`, dan `docx/data`. |
| `docs/dev/architecture.md`, `docs/dev/formats.md`, `docs/dev/glossary.md`, `docs/dev/references.md`, `docs/dev/code-style.md`, `docs/dev/contributing.md`, `docs/dev/testing.md`, `docs/dev/test-quality.md`, `docs/dev/python-315-style.md`, `docs/dev/adeu-integration.md` | Ganti `src/docgen` ke `src/autooffice/docx` (atau `src/autooffice/cli` untuk CLI), `docgen.*` ke modul `autooffice.*`, `tools/dev` ke `tools/quality`; perbarui tautan kontrak ke `docs/contracts/**`. |
| `docs/dev/docx/**` (14 berkas) | Ganti path modul dan perintah; tautkan ke `docs/contracts/docx.md`, bukan `docs/dev/contracts/docx-api.md`. |
| `docs/dev/pipeline/**` (7 berkas) | Ganti path modul dan perintah; tautkan ke `docs/contracts/cli.md` dan `docs/dev/pipeline/**`, bukan `docs/dev/contracts/stage-api.md`. |
| `docs/dev/learn/**` (8 berkas) | Ganti contoh import, perintah build/check, dan path package lama ke padanan AutoOffice; perbarui tautan kontrak. |
| `docs/dev/decisions/**` (8 berkas) | Jangan edit isi; tandai sebagai historis dan keluarkan dari indeks aktif. |
| `docs/contracts/cli.md` | Hapus pengecualian transisi `docgen`; ganti "seperti docgen" dan "aturan docgen" dengan "baseline DOCX"; nyatakan `check_no_legacy` sudah penuh. |
| `docs/contracts/docx.md` | Ganti "parity docgen" dan "aturan output docgen" dengan "parity baseline DOCX"; perbarui bukti test ke `tests/docx/test_command.py`, `test_docx_package.py`, `test_toc.py`, `test_sections.py`, dan `test_page_numbers.py`. |
| `docs/contracts/design-token.md` | Ganti provenance `deck-studio` dengan "baseline desain pra-AutoOffice" dan path `design-system/*.json` dengan `src/autooffice/design/data/*.yaml`. |
| `docs/contracts/copy.md` | Pertahankan atribusi sebagai catatan historis tanpa menyebut repo lama; jangan menautkan `deck-studio`. |
| `docs/contracts/pdf.md` | Hapus `scripts/word.ps1`; ganti lock file ke `autooffice-word.lock`. |
| `docs/contracts/ownership.md`, `docs/contracts/test-quality.md` | Ganti "migrasi docgen"/"baseline docgen" dengan "migrasi DOCX"/"baseline DOCX". |
| `docs/learn/deck-pipeline.md`, `docs/learn/design-system.md` | Ganti pernyataan nama lama dan provenance `deck-studio` dengan padanan netral. |
| `docs/user/cli.md` | Hapus alias/entry point `docgen` dari prosa; cukup nyatakan `autooffice` satu-satunya permukaan. |
| `docs/user/troubleshooting.md` | Pertahankan `DOCGEN_PANDOC` sebagai environment variable yang masih dibaca; jelaskan sebagai nama kompatibilitas, bukan entry point. |

### Source runtime `src/autooffice/**`

Ganti semua referensi lowercase `docgen` pada docstring, path, nama prog,
logger, prefix temp, dan lock file. Daftar berkas dan penggantinya:

| Berkas | Pengganti |
| --- | --- |
| `cli/outputs.py` | "perilaku docgen" menjadi "perilaku baseline DOCX". |
| `docx/__init__.py` | "diporting dari docgen" menjadi "diporting dari pipeline DOCX baseline". |
| `docx/adeu/cli.py` | `docgen`/`docgen.cli` pada docstring dan `prog` menjadi `autooffice`. |
| `docx/adeu/paragraph_ids.py` | `docgen.docx` menjadi `autooffice.docx`; `prog="docgen-adeu-add"` menjadi `autooffice-adeu-add`. |
| `docx/adeu/reconcile.py` | `prog="docgen reconcile"` menjadi `autooffice-adeu-reconcile`. |
| `docx/command.py` | "entry point CLI docgen build" menjadi "entry point build lama". |
| `docx/document.py` | `docgen check` menjadi `autooffice check`. |
| `docx/errors.py` | Docstring "untuk docgen" menjadi "untuk AutoOffice DOCX"; kelas `DocgenError` dan kode `DOCGEN` dipertahankan. |
| `docx/package/heading_numbering.py`, `io.py`, `runs.py`, `sections.py`, `tables.py` | Referensi `docgen.docx.*` menjadi `autooffice.docx.*`. |
| `docx/paths.py` | `src/docgen/data` menjadi `src/autooffice/docx/data`; docstring package `docgen` menjadi `autooffice`. |
| `docx/pipeline.py` | Modul `docgen.stages`/`docgen.pipeline` menjadi `autooffice.docx.stages`/`autooffice.docx.pipeline`; logger `docgen.pipeline` menjadi `autooffice.docx.pipeline`. |
| `docx/stages/__init__.py`, `blank_lines.py`, `captions.py`, `lists.py`, `mermaid.py`, `style_reference.py`, `validate.py` | Path dan docstring `docgen.*` menjadi `autooffice.docx.*`; prefix temp `docgen-mermaid-` menjadi `autooffice-mermaid-`. |
| `docx/terms/apply.py`, `glossary.py`, `model.py`, `verify.py` | Referensi `docgen.docx.terms` menjadi `autooffice.docx.terms`. |
| `pdf/com.py` | Lock file `docgen-word.lock` menjadi `autooffice-word.lock`; docstring `%TEMP%/docgen-word.lock` ikut berubah. |

Identifier yang tidak diubah di source: `DocgenError`, `DocgenError.default_code =
"DOCGEN"`, `DOCGEN_WINWORD`, `DOCGEN_PANDOC`, dan `LAPORAN_PANDOC`.

### Test, tool, dan checker

| Berkas | Perubahan |
| --- | --- |
| `tests/packaging/test_repo_local.py` | Ganti `docgen` menjadi `autooffice`; nama helper `_run_docgen` menjadi `_run_autooffice`; perbarui docstring. |
| `tests/test_import_contracts.py` | Docstring `docgen` menjadi `autooffice`; tetap menjalankan `lint-imports`. |
| `tests/tools/test_python_style.py` | Contoh path `src/docgen` menjadi `src/autooffice`. |
| `tests/docx/test_pipeline_edges.py` | Nama test yang memakai `docgen` diganti `base`/`legacy`; kelas `DocgenError` tetap. |
| `tests/docx/test_office.py` | Pertahankan guard negatif `word.ps1`/`docgen_powershell`; tambahkan allowlist di checker, bukan menghapus assertion. |
| `tests/cli/test_cli.py` | Pertahankan assertion `"docgen" not in output` sebagai guard regresi; allowlist di checker. |
| `tests/fixtures/golden/docx/minimal/README.md` | "kode docgen lama" menjadi "kode legacy". |
| `tools/quality/check_docs.py` | `DIREKTORI_SRC` menjadi `src/autooffice`; hapus `scripts/README.md` dari `README_MODUL`; perbarui docstring. |
| `tools/quality/check_no_legacy.py` | Implementasikan pemeriksaan penuh dan allowlist; daftar target tetap memuat `src/docgen` sebagai pola terlarang. |
| `tools/quality/gate.py` | Tidak ada perubahan perintah; pastikan langkah `no-legacy` memakai implementasi penuh. |
| `docs/dev/quality-gates.md` | Hapus status "list-only"; dokumentasikan allowlist dan kegagalan gate. |

### Contoh dan demo

| Berkas | Perubahan |
| --- | --- |
| `examples/assignment-single/document.md` | Ganti narasi, path `src/docgen/data`, perintah `docgen check/build`, dan diagram menjadi AutoOffice; jangan ubah struktur heading/tabel yang menjadi baseline tanpa rebaseline. |
| `examples/proposal-single/document.md` | Ganti narasi dan perintah `docgen` menjadi AutoOffice. |
| `examples/thesis-single/document.md` | Ganti narasi, path modul, perintah, caption tabel/gambar, dan diagram menjadi AutoOffice. Perubahan caption mewajibkan regenerasi baseline DOCX/PDF. |
| `examples/demo-deck/README.md` | Ganti provenance `deck-studio` dengan "demo desain baseline" atau atribusi netral. |
| `examples/demo-deck/deck.yaml` | Ganti `description` dan teks "Sumber: demo deck-studio AutoOffice" menjadi "Deck demo AutoOffice"; jalankan copy checker setelah perubahan. |
| `src/autooffice/design/data/tokens.yaml`, `themes.yaml` | Komentar provenance `deck-studio` menjadi "baseline desain pra-AutoOffice". |
| `src/autooffice/deck/copy/rules/banned_phrases.py` | Docstring `scripts/check-copy.js` deck-studio menjadi catatan arsip netral. |
| `tests/design/test_themes.py` | Docstring "palet deck-studio" menjadi "palet baseline". |

## Inventaris referensi aktif

Perintah pemindaian yang dipakai:

```bash
rg -n --case-sensitive -F -e 'docgen' -e 'deck-studio' -e 'word.ps1' \
  --glob '!.git/**' --glob '!.venv/**' --glob '!build/**' --glob '!dist/**' \
  --glob '!**/__pycache__/**' --glob '!*.pyc' --glob '!.mypy_cache/**' \
  --glob '!.pytest_cache/**' --glob '!.ruff_cache/**' --glob '!.hypothesis/**' \
  --glob '!.autooffice-build/**' --glob '!.laporan*/**' --glob '!acuan/**' .
```

Untuk audit identifier, jalankan varian case-insensitive:

```bash
rg -ni -e 'docgen' -e 'deck-studio' -e 'word\.ps1' \
  --glob '!.git/**' --glob '!.venv/**' --glob '!**/__pycache__/**' .
```

Jumlah pada tabel inventaris adalah kemunculan case-sensitive lowercase.
Identifier uppercase seperti `DocgenError`, `DOCGEN`, dan `DOCGEN_*` dihitung
terpisah pada bagian [Identifier yang dipertahankan](#identifier-yang-dipertahankan).

Dikecualikan dari inventaris aktif dan tidak boleh diedit tanpa keputusan
terpisah:

- `AUTO_OFFICE_PLAN.md`, `AUTO_OFFICE_EXECUTION_LOG.md`.
- `docs/dev/archive/**`, `docs/dev/decisions/**`.
- `docs/decisions/0001-0010*.md`, `docs/decisions/0011-f3-cleanup.md`,
  `docs/decisions/0012*.md`.
- `tests/fixtures/golden/**` (isi dan metadata baseline historis).
- `src/docgen/**`, `tests/unit/**`, `tests/integration/**`, `tests/e2e/**`,
  `tests/packaging/**`, `tools/dev/**`, `scripts/**`, dan
  `docs/dev/contracts/**` karena akan dihapus; rujuk tabel hapus.

### Root, metadata, dan packaging

| Berkas | Jumlah | Referensi dan pengganti |
| --- | --- | --- |
| `pyproject.toml` | 32 | Nama package, entry point, package-data, per-file ignore, mypy files/override, root import-linter, dan lima kontrak import-linter. Semua diganti seperti tabel `pyproject.toml` di atas. |
| `uv.lock` | 1 | Package editable `docgen` menjadi `autooffice` setelah `uv lock`. |
| `LICENSE` | 1 | Copyright `docgen contributors` menjadi `AutoOffice contributors`. |
| `AGENTS.md` | 1 `docgen`, 1 `deck-studio` | Larangan lama menjadi larangan menambahkan kembali nama/entry point lama. |
| `README.md` | 0 `docgen`; 1 `tools/dev` | Atribusi `tools/dev/check_prose.py` dihapus; kaidah prosa disebut sebagai adaptasi naskah-id. |
| `scripts/README.md` | 9 `docgen`, 11 `word.ps1` | Berkas dihapus. |
| `scripts/word.ps1` | 1 `docgen`, 2 `word.ps1` | Berkas dihapus. |

### Runtime `src/autooffice/**`

| Berkas | Jumlah | Pengganti |
| --- | --- | --- |
| `src/autooffice/cli/outputs.py` | 2 | "perilaku baseline DOCX". |
| `src/autooffice/docx/__init__.py` | 1 | "pipeline DOCX baseline". |
| `src/autooffice/docx/adeu/cli.py` | 5 | `autooffice`, `autooffice.cli`; `DocgenError` tetap. |
| `src/autooffice/docx/adeu/paragraph_ids.py` | 3 | `autooffice.docx`, `autooffice-adeu-add`. |
| `src/autooffice/docx/adeu/reconcile.py` | 1 | `autooffice-adeu-reconcile`. |
| `src/autooffice/docx/command.py` | 1 | "entry point build lama". |
| `src/autooffice/docx/document.py` | 1 | `autooffice check`. |
| `src/autooffice/docx/errors.py` | 1 | "AutoOffice DOCX"; `DocgenError`/`DOCGEN` tetap. |
| `src/autooffice/docx/package/heading_numbering.py`, `io.py`, `runs.py`, `sections.py`, `tables.py` | 1 masing-masing | `autooffice.docx.*`. |
| `src/autooffice/docx/paths.py` | 3 | `src/autooffice/docx/data`, package `autooffice`. |
| `src/autooffice/docx/pipeline.py` | 3 | `autooffice.docx.stages`, `autooffice.docx.pipeline`, logger `autooffice.docx.pipeline`. |
| `src/autooffice/docx/stages/__init__.py` | 2 | `autooffice.docx.pipeline`. |
| `src/autooffice/docx/stages/blank_lines.py` | 1 | `autooffice.docx.paragraphs`. |
| `src/autooffice/docx/stages/captions.py` | 2 | `autooffice.docx.captions`, `autooffice.docx.tables`. |
| `src/autooffice/docx/stages/lists.py` | 1 | `autooffice.docx.fields`. |
| `src/autooffice/docx/stages/mermaid.py` | 3 | `autooffice.docx.pipeline`, prefix `autooffice-mermaid-`. |
| `src/autooffice/docx/stages/style_reference.py` | 3 | `autooffice.docx.config`, `autooffice.docx`, `autooffice.docx.pipeline`. |
| `src/autooffice/docx/stages/validate.py` | 2 | `autooffice.docx.errors`, `autooffice check`. |
| `src/autooffice/docx/terms/apply.py`, `glossary.py`, `model.py`, `verify.py` | 1 masing-masing | `autooffice.docx.terms.*`. |
| `src/autooffice/pdf/com.py` | 2 | `autooffice-word.lock`. |

### Test, tool, dan checker

| Berkas | Jumlah | Pengganti |
| --- | --- | --- |
| `tests/README.md` | 3 | Tulis ulang untuk suite AutoOffice. |
| `tests/test_import_contracts.py` | 1 | Docstring `autooffice`. |
| `tests/tools/test_python_style.py` | 2 | Contoh path `src/autooffice`. |
| `tests/docx/test_pipeline_edges.py` | 2 | Nama test `base`/`legacy`; `DocgenError` tetap. |
| `tests/docx/test_office.py` | 1 | Guard negatif `word.ps1`/`docgen_powershell` dipertahankan dan di-allowlist. |
| `tests/cli/test_cli.py` | 1 | Guard negatif `"docgen" not in output` dipertahankan dan di-allowlist. |
| `tests/fixtures/golden/baseline-4a5b777.json` | 2 | Fixture historis; dipertahankan dan di-allowlist. |
| `tests/fixtures/golden/docx/minimal/README.md` | 1 | "kode legacy". |
| `tools/README.md` | 4 | Tulis ulang ke `tools/quality/**`. |
| `tools/quality/check_docs.py` | 2 | `src/autooffice`; hapus `scripts/README.md`. |
| `tools/quality/check_no_legacy.py` | 1 | Pola terlarang `src/docgen` dipertahankan secara sengaja. |

### Dokumentasi

| Berkas | Jumlah | Pengganti |
| --- | --- | --- |
| `docs/contracts/cli.md` | 6 `docgen`, 1 `deck-studio` | Hapus pengecualian transisi dan nama lama; gunakan "baseline DOCX". |
| `docs/contracts/docx.md` | 6 | "baseline DOCX"; bukti test baru. |
| `docs/contracts/design-token.md` | 1 `docgen`, 2 `deck-studio` | "baseline DOCX"/"baseline desain"; path YAML AutoOffice. |
| `docs/contracts/copy.md` | 2 `deck-studio` | Atribusi historis netral. |
| `docs/contracts/pdf.md` | 1 `docgen` (lock file), 2 `word.ps1` | `autooffice-word.lock`; hapus `word.ps1`. |
| `docs/contracts/README.md` | 1 | "parity baseline DOCX". |
| `docs/contracts/ownership.md` | 1 | "Migrasi DOCX". |
| `docs/contracts/test-quality.md` | 1 | "Baseline DOCX". |
| `docs/dev/README.md` | 1 | Hapus tautan `dev/contracts`; tambah `f3-cleanup.md`. |
| `docs/dev/architecture.md` | 11 | Path AutoOffice dan tautan `docs/contracts`. |
| `docs/dev/adeu-integration.md` | 11 | Path AutoOffice dan perintah `autooffice`. |
| `docs/dev/code-style.md` | 19 | Path AutoOffice; checker `tools/quality/check_docs.py`; `DocgenError` tetap sebagai identifier. |
| `docs/dev/contributing.md` | 4 | Path/tautan AutoOffice; `DocgenError` tetap. |
| `docs/dev/formats.md` | 2 | Path AutoOffice; tautan kontrak baru. |
| `docs/dev/docx/README.md` dan 13 halaman lain | 1-2 masing-masing | `autooffice.docx.*`; tautan `docs/contracts/docx.md`. |
| `docs/dev/pipeline/README.md`, `options.md`, `overview.md` dan 4 halaman lain | 1-2 masing-masing | `autooffice.docx.pipeline`; tautan `docs/contracts/cli.md`. |
| `docs/dev/learn/README.md` dan 7 halaman lain | 4-28 masing-masing | Contoh import, perintah, dan path AutoOffice. |
| `docs/dev/references.md` | 9 | Path AutoOffice; hapus `word.ps1` dan `docs/dev/contracts`. |
| `docs/dev/repo-map.md` | 16 `docgen`, 2 `word.ps1` | Tulis ulang untuk AutoOffice. |
| `docs/dev/packaging.md` | 15 | Tulis ulang untuk package `autooffice`. |
| `docs/dev/pdf.md` | 14 `docgen`, 9 `word.ps1` | Hapus bagian legacy; sisakan Word COM AutoOffice. |
| `docs/dev/com.md` | 1 `docgen`, 1 `word.ps1` | `autooffice-word.lock`; hapus `word.ps1`. |
| `docs/dev/learn/00-start-here.md` | 28 + 1 `word.ps1` | Path AutoOffice; hapus `word.ps1`. |
| `docs/dev/testing.md`, `docs/dev/test-quality.md` | 2 masing-masing | `tools/quality/**` dan path AutoOffice. |
| `docs/dev/python-315-style.md` | 2 | `src/autooffice`. |
| `docs/learn/deck-pipeline.md` | 1 `docgen`, 1 `deck-studio` | "nama package/CLI lama". |
| `docs/learn/design-system.md` | 1 `docgen`, 1 `deck-studio` | "baseline desain". |
| `docs/user/cli.md` | 2 | Hapus alias/entry point lama. |
| `docs/user/troubleshooting.md` | 1 (case-insensitive) | `DOCGEN_PANDOC` tetap; jelaskan sebagai nama kompatibilitas. |
| `docs/dev/contracts/config.md` | 12 | Dihapus; isi mengikat pindah ke `docs/dev/formats.md`/`docs/contracts/docx.md`. |
| `docs/dev/contracts/docx-api.md` | 40 | Dihapus; tautan ke `docs/contracts/docx.md` dan `docs/dev/docx/**`. |
| `docs/dev/contracts/stage-api.md` | 24 `docgen`, 2 `word.ps1` | Dihapus; tautan ke `docs/contracts/cli.md` dan `docs/dev/pipeline/**`. |

### Contoh

| Berkas | Jumlah | Keputusan |
| --- | --- | --- |
| `examples/assignment-single/document.md` | 11 | Ganti narasi/path/perintah ke AutoOffice sebelum baseline baru dibuat. |
| `examples/proposal-single/document.md` | 3 | Ganti narasi/perintah ke AutoOffice. |
| `examples/thesis-single/document.md` | 16 | Ganti narasi/path/perintah dan caption ke AutoOffice; regenerasi baseline DOCX/PDF. |
| `examples/demo-deck/README.md` | 3 `deck-studio` | Ganti dengan atribusi netral. |
| `examples/demo-deck/deck.yaml` | 7 `deck-studio` | Ganti metadata/source note; jalankan copy checker. |
| `src/autooffice/design/data/tokens.yaml` | 1 `deck-studio` | Komentar baseline. |
| `src/autooffice/design/data/themes.yaml` | 1 `deck-studio` | Komentar baseline. |
| `src/autooffice/deck/copy/rules/banned_phrases.py` | 1 `deck-studio` | Docstring netral. |
| `tests/design/test_themes.py` | 1 `deck-studio` | Docstring netral. |

### Identifier yang dipertahankan

Referensi berikut akan tetap muncul pada pemindaian case-insensitive. Semuanya
bukan package, entry point, path, atau perintah lama:

| Identifier | Lokasi | Alasan |
| --- | --- | --- |
| `DocgenError` | 31 berkas di `src/autooffice/**` dan `tests/docx/**` | Nama kelas error publik yang dipakai kontrak dan tes. Rename hanya lewat ADR baru. |
| `DOCGEN` | `src/autooffice/docx/errors.py` | Kode error default. |
| `DOCGEN_WINWORD`, `DOCGEN_PANDOC`, `LAPORAN_PANDOC` | `src/autooffice/docx/stages/*.py`, docs | Environment variable kompatibilitas yang masih dibaca. |
| Guard negatif `word.ps1`, `docgen_powershell`, dan `"docgen" not in output` | `tests/docx/test_office.py`, `tests/cli/test_cli.py` | Mencegah reintroduksi PowerShell/entry point lama. |
| `src/docgen` pada daftar no-legacy | `tools/quality/check_no_legacy.py` | Pola terlarang, bukan referensi runtime. |

## Urutan operasi

1. **Freeze dan backup.** Pastikan F3-ACCEPT lulus dan working tree bersih.
   Buat tag dan branch backup lokal:
   `git tag -a f3-cleanup-base -m "F3 cleanup base"` dan
   `git branch backup/pre-f3-cleanup f3-cleanup-base`. Buat branch kerja
   `autooffice/f3-cleanup` dari tag tersebut. Backup tambahan opsional:
   `git bundle create C:/dev/backups/docgen-pre-f3.bundle --all`. Jangan push
   tanpa persetujuan.
2. **Siapkan konten contoh dan baseline.** Ganti narasi/path/perintah contoh
   ke AutoOffice, lalu build baseline legacy sebelum `src/docgen` dihapus.
   Simpan baseline DOCX ternormalisasi untuk assignment, proposal, dan thesis
   di `tests/fixtures/golden/parity/`. Regenerasi `pdf-baseline.json` bila
   teks contoh berubah. Baseline ini adalah data uji, bukan kode runtime.
3. **Port invariant golden.** Invarian DOCX dibuktikan oleh
   `tests/docx/test_command.py`, `tests/docx/test_docx_package.py`,
   `tests/docx/test_toc.py`, `tests/docx/test_sections.py`, dan
   `tests/docx/test_page_numbers.py`. Acceptance deck diuji oleh
   `tests/acceptance/test_demo_deck.py`.
4. **Hapus kode, tes, dan script.** Jalankan `git rm` sesuai tabel
   [Daftar hapus](#daftar-hapus). Jangan hapus fixture yang dipakai langkah 3.
   Hapus juga `src/docgen.egg-info/` dan `__pycache__` dari working tree.
5. **Hapus tool lama.** Pindahkan checker yang masih dipakai
   (`check_docs`, `check_tests`, `check_coverage`) ke `tools/quality/`, lalu
   hapus `tools/dev/**`. `audit_terms*.py`, `check_prose.py`, dan `rules.yml`
   dihapus tanpa port; AutoOffice tidak menyertakan checker prosa atau audit
   istilah terpisah.
6. **Update package dan konfigurasi.** Ubah `pyproject.toml`, jalankan
   `uv lock`, perbarui `LICENSE`, `README.md`, `AGENTS.md`, `pytest.ini`,
   checker `tools/quality/**`, dan `tests/README.md`/`tools/README.md`.
7. **Update dokumentasi.** Hapus tiga kontrak lama; perbarui indeks dan semua
   halaman aktif sesuai tabel. Jangan edit ADR historis.
8. **Jalankan gate.** Jalankan gate lokal penuh dari clean tree, termasuk
   `no-legacy`, docs checker, lint-imports, mypy, pytest, dan wheel check.
9. **Audit wheel dan clean clone.** Pastikan wheel hanya memuat package
   `autooffice` beserta data/font; uji clean clone dari tag.
10. **Rename terpisah.** Setelah gate final dan persetujuan pemilik, jalankan
    F3-RENAME untuk repo GitHub dan folder lokal. Rename tidak boleh berada di
    commit atau tag yang sama dengan penghapusan.

## Rollback

- **Sebelum rename.** Tag `f3-cleanup-base` dan branch
  `backup/pre-f3-cleanup` adalah titik pulih. Bila commit cleanup belum
  di-merge, `git switch autooffice/integration` lalu buang branch kerja.
  Bila sudah di-merge, `git revert -m 1 <merge-sha>`; jangan force-push.
- **Restore berkas yang salah dihapus.**
  `git restore --source=f3-cleanup-base -- src/docgen tests/unit tests/integration tests/e2e scripts tools docs pyproject.toml uv.lock`.
  Untuk fixture yang tidak sengaja terhapus, restore path spesifik dari tag.
- **Pulihkan metadata.** Checkout `pyproject.toml`, `uv.lock`, `LICENSE`,
  `README.md`, `AGENTS.md`, dan `pytest.ini` dari tag, lalu `uv lock` dan
  `uv sync --reinstall`.
- **Setelah rename.** Rename repo GitHub dan folder lokal harus dikembalikan
  oleh pemilik; jalankan `git remote set-url` dan clean clone ulang. Tag dan
  branch backup tidak boleh dihapus sampai satu release setelah F3-GATE.
- **Bila baseline parity salah.** Jangan lanjutkan penghapusan; buang baseline
  baru, ulangi langkah 2-3, dan pertahankan `src/docgen` sampai parity benar.

## Risiko dan mitigasi

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| Masih ada tes atau tool yang mengimpor `docgen` | Koleksi pytest gagal atau import error setelah penghapusan | Jalankan `rg` inventaris, port semua tes yang tercantum, dan jalankan `pytest --collect-only` sebelum `git rm`. |
| Package data tidak lengkap | Build DOCX gagal setelah `src/docgen/data` hilang | Bandingkan `src/docgen/data` dengan `src/autooffice/docx/data`; uji wheel dan build contoh dari clean clone. |
| Root import-linter atau kontrak `docgen.*` tertinggal | `lint-imports` gagal atau mengimpor package yang sudah tidak ada | Hapus root `docgen` dan lima kontrak legacy; jalankan `uv run lint-imports` setelah `uv sync`. |
| Tautan docs ke `dev/contracts/**` rusak | Docs checker gagal | Update semua tautan ke `docs/contracts/**`, `docs/dev/pipeline/**`, dan `docs/dev/formats.md`; jalankan checker. |
| Entry point `docgen` di wheel/venv | Perintah hantu atau import error | Hapus dari `[project.scripts]`, jalankan `uv lock` dan `uv sync --reinstall`, lalu `autooffice --help`. |
| Golden baseline berubah karena teks contoh | Parity test gagal atau baseline tidak bermakna | Buat baseline baru dengan kode legacy setelah teks contoh final; normalisasi timestamp/metadata; jangan mengubah fixture historis `laporan-baseline.docx`. |
| `check_no_legacy` masih list-only | Gate tidak menangkap reintroduksi package lama | Implementasi penuh dan allowlist sudah diterapkan; gate menjalankan checker sebagai langkah blocking. |
| `DocgenError`/`DOCGEN_*` terdeteksi sebagai referensi lama | False positive pada gate | Dokumentasikan sebagai identifier yang dipertahankan; allowlist eksplisit; rename hanya lewat ADR baru. |
| Penghapusan `tools/dev` memutus tes/docs | Checker gagal atau import error | Checker quality diporting ke `tools/quality/`; alat prosa/audit istilah dihapus bersama referensinya, lalu docs dan tes diperbarui. |
| Rename repo dilakukan terlalu cepat | Remote, cache, dan clean clone rusak | Rename hanya setelah freeze, gate final, dan persetujuan; sediakan rollback tag/branch. |
| Mesin gate tidak punya Word/PowerPoint | COM/PDF acceptance tidak dapat dibuktikan | Jalankan F3-GATE di mesin Windows yang disyaratkan plan; jangan klaim gate lulus tanpa bukti. |

## Definisi selesai dan perintah

Definisi selesai F3 cleanup:

- `git ls-files` tidak memuat `src/docgen/`, `tests/unit/`, `tests/integration/`,
  `tests/e2e/`, `tests/factories/`, `tools/dev/`, `scripts/`, atau
  `docs/dev/contracts/`.
- `rg -n "from docgen|import docgen" src tests tools` kosong.
- Pemindaian aktif `docgen|deck-studio|word.ps1` kosong kecuali allowlist
  historis/identifier yang tercantum di ADR ini.
- `pyproject.toml` hanya mendefinisikan package/entry point `autooffice`;
  `uv.lock` hanya memuat package editable `autooffice`.
- Wheel hanya memuat package `autooffice`, data DOCX, token/theme, font, dan
  metadata lisensi.
- `autooffice --help` hanya menampilkan permukaan CLI kontrak.
- Docs checker, test-quality checker, no-legacy checker, lint-imports, mypy,
  pytest, dan gate lokal lulus.
- Clean clone dari repo hasil rename dapat `uv sync`, `autooffice --help`, dan
  build contoh.
- ADR ini disetujui integration owner dan dicatat di
  `AUTO_OFFICE_EXECUTION_LOG.md`.

Perintah verifikasi:

```bash
# 1. Baseline dan invariant golden
uv run autooffice build examples/thesis-single/document.md --target docx
uv run pytest -q tests/docx/test_command.py tests/docx/test_docx_package.py \
  tests/docx/test_toc.py tests/docx/test_sections.py tests/docx/test_page_numbers.py
uv run pytest -q tests/acceptance/test_demo_deck.py

# 2. Setelah penghapusan dan update
uv lock
uv sync --extra dev --extra google --extra windows
uv run python tools/quality/gate.py
uv run python tools/quality/check_no_legacy.py
uv run python tools/quality/check_docs.py
uv run lint-imports
uv run mypy src/autooffice
uv run pytest -q --cov=autooffice --cov-branch --cov-fail-under=90

# 3. Wheel dan artifact
uv build
python -m zipfile -l dist/autooffice-*.whl
uv run autooffice doctor --target all
uv run autooffice check examples/demo-deck/deck.yaml
uv run autooffice build examples/demo-deck/deck.yaml --target all --out <tmp>
uv run autooffice build examples/thesis-single/document.md --target docx,pdf --out <tmp>

# 4. Audit referensi
rg -n --case-sensitive -F -e 'docgen' -e 'deck-studio' -e 'word.ps1' \
  --glob '!.git/**' --glob '!.venv/**' --glob '!**/__pycache__/**' \
  --glob '!AUTO_OFFICE_PLAN.md' --glob '!AUTO_OFFICE_EXECUTION_LOG.md' \
  --glob '!docs/dev/archive/**' --glob '!docs/dev/decisions/**' \
  --glob '!docs/decisions/00*.md' --glob '!tests/fixtures/golden/**' .
```

## Konsekuensi

- Repo kehilangan seluruh jalur legacy dan hanya memiliki satu package, satu
  entry point, dan satu gate.
- Tes DOCX lama yang tidak diporting hilang; cakupan perilaku dibuktikan oleh
  `tests/docx/**`, `tests/acceptance/**`, `tests/packaging/**`, dan invariant
  golden yang masih disimpan.
- `tools/dev` tidak lagi menjadi rumah tool; `tools/quality` menjadi satu-
  satunya rumah checker. `audit_terms*.py`, `check_prose.py`, dan `rules.yml`
  dihapus tanpa port; AutoOffice tidak menyertakan checker prosa atau audit
  istilah terpisah.
- Environment variable `DOCGEN_WINWORD`, `DOCGEN_PANDOC`, dan `LAPORAN_PANDOC`
  tetap kompatibel sampai ada ADR yang menggantinya. Nama kelas `DocgenError`
  dan kode `DOCGEN` juga tetap.
- Dokumen historis di `docs/dev/archive/**`, `docs/dev/decisions/**`, dan ADR
  lama tetap menyebut nama lama; itu disengaja dan bukan referensi aktif.
- Rename repo tidak mengubah tag atau branch backup; rollback tetap mungkin
  sampai release berikutnya.

## Alternatif yang ditolak

- **Mempertahankan shim `autooffice.docgen` atau entry point `docgen`.** Ditolak
  oleh L01/L02 dan checklist no-dead-code.
- **Menghapus semua tes legacy tanpa porting invariant.** Ditolak karena
  parity DOCX dan PDF adalah acceptance F3.
- **Menghapus `tools/dev` sekaligus tanpa memindahkan checker quality.**
  Ditolak karena `check_docs`, `check_tests`, dan `check_coverage` masih
  dipakai gate. Alat prosa dan audit istilah dihapus tanpa port karena tidak
  menjadi bagian AutoOffice.
- **Menggabungkan rename repo dengan commit penghapusan.** Ditolak karena
  rollback remote dan clean clone menjadi tidak jelas.
- **Menyunting ADR lama dan arsip agar grep bersih.** Ditolak; arsip harus
  tetap historis dan di-allowlist.
- **Mempertahankan halaman `docs/dev/contracts/**` yang menduplikasi kontrak
  normatif.** Ditolak oleh invariant dokumentasi yang melarang duplikasi
  kontrak.
