# Pembersihan F3

Status: rencana, belum dieksekusi. Sumber keputusan:
[ADR 0011](../decisions/0011-f3-cleanup.md). Plan migrasi:
[`AUTO_OFFICE_PLAN.md`](../../AUTO_OFFICE_PLAN.md) bagian 13.5 dan 16.

Dokumen ini adalah runbook singkat. Daftar lengkap per berkas, inventaris
referensi, risiko, dan rollback ada di ADR 0011. Jangan menjalankan langkah apa
pun sebelum F3-ACCEPT lulus dan branch freeze aktif.

## Daftar Isi

- [Prasyarat](#prasyarat)
- [1. Tag dan backup](#1-tag-dan-backup)
- [2. Parity test ke baseline](#2-parity-test-ke-baseline)
- [3. Hapus kode, tes, dan script](#3-hapus-kode-tes-dan-script)
- [4. Update konfigurasi dan dokumentasi](#4-update-konfigurasi-dan-dokumentasi)
- [5. Gate](#5-gate)
- [6. Rename repo](#6-rename-repo)
- [Rollback](#rollback)
- [Definition of done](#definition-of-done)

## Prasyarat

- F3-ACCEPT lulus dan semua lane F2 sudah merged.
- Working tree bersih; F1/F2 sudah di-commit.
- Mesin gate: Windows, Word/PowerPoint desktop, `uv`, Pandoc, dan `mmdc`.
- Persetujuan pemilik untuk tag, push, dan rename.
- Tidak ada worker lain yang menulis file.

## 1. Tag dan backup

```bash
git tag -a f3-cleanup-base -m "F3 cleanup base"
git branch backup/pre-f3-cleanup f3-cleanup-base
git switch -c autooffice/f3-cleanup f3-cleanup-base
# opsional: backup penuh di luar repo
git bundle create C:/dev/backups/docgen-pre-f3.bundle --all
```

Jangan push tag/branch tanpa persetujuan. Tag ini adalah titik rollback.

## 2. Parity test ke baseline

Baseline dibuat dari kode legacy **sebelum** `src/docgen` dihapus. Finalkan
teks contoh lebih dulu agar baseline tidak dibuat dua kali.

```bash
uv run docgen build examples/assignment-single/document.md --target both
uv run docgen build examples/proposal-single/document.md --target both
uv run docgen build examples/thesis-single/document.md --target both
```

Simpan baseline ternormalisasi di `tests/fixtures/golden/parity/`. Regenerasi
`tests/fixtures/golden/pdf-baseline.json` bila teks contoh berubah.

Port tes berikut dengan import `autooffice.*`:

| Lama | Baru |
| --- | --- |
| `tests/integration/test_golden_docx.py` | `tests/docx/test_golden_baseline.py` |
| `tests/integration/test_golden_pdf.py` | `tests/docx/test_golden_pdf.py` |
| invarian pipeline thesis/e2e | `tests/docx/**` dan `tests/acceptance/**` |
| `tests/e2e/test_thesis_e2e.py` | `tests/acceptance/**` dengan CLI `autooffice` |
| `tests/packaging/test_repo_local.py` | tulis ulang di path yang sama untuk `autooffice` |

Tambahkan `tests/docx/test_parity.py` yang membandingkan build AutoOffice
dengan baseline legacy. Jalankan sampai hijau sebelum menghapus kode lama.

## 3. Hapus kode, tes, dan script

```bash
git rm -r src/docgen
git rm -r tests/unit tests/integration tests/e2e
git rm -r tests/factories
git rm -r tools/dev
git rm -r docs/dev/contracts
git rm scripts/word.ps1 scripts/README.md
git rm tests/test_audit_terms.py
git rm tests/test_check_coverage.py tests/test_check_docs.py
git rm tests/test_check_prose.py tests/test_check_prose_docx.py
git rm tests/test_check_tests.py
```

Catatan:

- Port `tests/unit/test_golden_fixtures.py` ke `tests/docx/` lebih dulu.
- Port `audit_terms*.py`, `check_prose.py`, dan `rules.yml` ke
  `tools/quality/` sebelum `tools/dev` dihapus.
- `tests/packaging/test_repo_local.py` ditulis ulang, bukan dihapus.
- Jangan hapus `tests/fixtures/golden/**`, `tests/fixtures/docx/**`,
  `tests/fixtures/format_figures/**`, `paragraph_ids/**`, atau `reconcile/**`.
- Hapus `src/docgen.egg-info/` dan `__pycache__/` dari working tree.
- `scripts/check.ps1` sudah berstatus deleted; pastikan ikut ter-stage.

## 4. Update konfigurasi dan dokumentasi

`pyproject.toml`:

- `name`: `docgen` menjadi `autooffice`.
- `description`: deskripsi AutoOffice.
- Hapus script `docgen`; sisakan `autooffice`.
- Hapus package-data `docgen`; pertahankan `assets`, `design/data`, dan
  `docx/data`; hapus pola `data/**/*` yang tidak ada.
- Hapus per-file ignore `src/docgen/docx/names.py`.
- `mypy.files`: `["src/autooffice"]`; hapus override `docgen.*`.
- `importlinter.root_packages`: `["autooffice"]`; hapus lima kontrak
  `docgen.*`.
- Jalankan `uv lock`.

Update juga `LICENSE`, `AGENTS.md`, `README.md`, `pytest.ini`,
`docs/README.md`, `docs/dev/README.md`, `docs/contracts/README.md`,
`docs/decisions/README.md`, `tests/README.md`, dan `tools/README.md`.

Dokumentasi aktif: ganti path/perintah `docgen` ke AutoOffice; hapus bagian
legacy `word.ps1` di `docs/dev/pdf.md`; tulis ulang `repo-map.md` dan
`packaging.md`; arahkan tautan `docs/dev/contracts/**` ke `docs/contracts/**`.
Jangan edit `docs/dev/archive/**`, `docs/dev/decisions/**`, atau ADR historis.

Source runtime: bersihkan docstring, path, nama prog, logger, prefix temp, dan
lock file `docgen-word.lock` menjadi `autooffice-word.lock`. Identifier
`DocgenError`, `DOCGEN`, `DOCGEN_WINWORD`, `DOCGEN_PANDOC`, dan
`LAPORAN_PANDOC` dipertahankan; lihat ADR.

Implementasikan `tools/quality/check_no_legacy.py` sebagai pemeriksa penuh
dengan allowlist untuk arsip, ADR, fixture golden, dan guard negatif.

## 5. Gate

```bash
uv lock
uv sync --extra dev --extra google --extra windows
uv run python tools/quality/gate.py
uv run python tools/quality/check_no_legacy.py
uv run python tools/quality/check_docs.py
uv run lint-imports
uv run mypy src/autooffice
uv run pytest -q --cov=autooffice --cov-branch --cov-fail-under=90
```

Gate final juga menjalankan `uv build`, memeriksa isi wheel, `autooffice
doctor --target all`, build demo deck, build DOCX/PDF thesis, dan clean clone.
Perintah lengkap ada di ADR 0011.

## 6. Rename repo

Rename GitHub dan folder lokal adalah F3-RENAME, bukan bagian commit ini.
Lakukan hanya setelah gate final lulus, freeze merge, dan persetujuan pemilik.
Tidak ada alias URL, package, atau CLI.

## Rollback

- Sebelum merge: `git switch autooffice/integration` lalu buang branch kerja.
- Sesudah merge: `git revert -m 1 <merge-sha>`; jangan force-push.
- Restore path:
  `git restore --source=f3-cleanup-base -- <path>`.
- Setelah rename: kembalikan nama repo/folder dan `git remote set-url`; clean
  clone ulang.
- Jangan hapus tag `f3-cleanup-base` atau branch `backup/pre-f3-cleanup` sampai
  satu release setelah F3-GATE.

## Definition of done

- `git ls-files` tidak memuat `src/docgen/`, `tests/unit/`,
  `tests/integration/`, `tests/e2e/`, `tests/factories/`, `tools/dev/`,
  `scripts/`, atau `docs/dev/contracts/`.
- `rg "from docgen|import docgen" src tests tools` kosong.
- `pyproject.toml` dan `uv.lock` hanya memakai `autooffice`.
- Wheel hanya memuat package `autooffice`, data DOCX, token/theme, font, dan
  metadata lisensi.
- `autooffice --help` hanya menampilkan permukaan CLI kontrak.
- Gate, docs checker, no-legacy checker, lint-imports, mypy, pytest, dan clean
  clone lulus.
- ADR 0011 disetujui dan hasilnya dicatat di `AUTO_OFFICE_EXECUTION_LOG.md`.
