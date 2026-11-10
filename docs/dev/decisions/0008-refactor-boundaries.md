# ADR 0008: Batas Refactor docgen

- Status: diterima
- Tanggal: 2026-11-10

## Konteks

Refactor docgen memakai baseline commit `4a5b777` dan target struktur di
[refactor-plan.md](../archive/refactor-plan.md). Pada P0.2, sebelum tag baseline
`baseline-4a5b777` (P0.3), lima keputusan di bagian 6 plan masih terbuka:
adapter Word, future import, split `config.py`, dokumen historis, dan naming
moves. Keputusan ini memengaruhi dependency, packaging, batas modul, dan
dokumentasi. P0.2 mencatat konfirmasi di plan dan ADR ini agar tabel keputusan,
target struktur, dan acceptance tidak bertentangan.

## Keputusan

1. **Adapter Word: pertahankan PowerShell.** `scripts/word.ps1` tetap menjadi
   adapter Microsoft Word. Tidak ada migrasi ke `pywin32` atau COM pada refactor
   ini.
2. **Future import: hapus.** Seluruh `from __future__ import annotations`
   dihapus dari `src`, `tests`, dan `tools` pada S2.
3. **Split `config.py`: tunda dan evaluate.** `config.py` tetap satu file sampai
   F1-F4 selesai. F5 menjalankan decision gate dan hanya memecahnya jika tetap
   lebih dari 1.500 LOC atau sulit dites.
4. **Dokumen historis: arsipkan dulu.** `duplication-map.md` dan
   `restructure-plan.md` dipindahkan ke `docs/dev/archive/` dengan status
   superseded pada L4.1, lalu dihapus di Fase 6 (G4) jika tidak ada nilai audit.
5. **Naming moves: semua.** Jalankan seluruh move: `docx/headings.py` ke
   `markdown/headings.py` dengan rename `HeadingError` menjadi
   `MarkdownHeadingError`, `features/adeu/` ke `adeu/`, `resources/` ke
   `scripts/`, dan `captions/figures` ke `captions`.

## Alasan ringkas

- **Adapter Word.** Script PowerShell kecil, sudah menjadi kontrak, dan tidak
  menambah dependency Python. Migrasi COM menambah risiko platform, test
  Windows, packaging, dan error handling baru.
- **Future import.** Target Python 3.15 dengan PEP 649 sudah memberi anotasi
  lazy. Import future hanya noise dan menyalahi target code style.
- **Split `config.py`.** Baseline 2.403 LOC memang besar, tetapi split sebelum
  API stabil berisiko churn dan menambah lane besar di Fase 4. Gate F5
  memutuskan dengan data LOC dan kemudahan tes.
- **Dokumen historis.** Archive menjaga jejak keputusan selama refactor,
  sedangkan G4 mencegah archive permanen yang tidak perlu. Menghapus sekarang
  menghilangkan konteks audit.
- **Naming moves.** Keempat move memperbaiki lapisan dan menghilangkan nama
  menyesatkan. Subset akan membuat struktur target tidak konsisten dan
  menyisakan tech debt.

## Konsekuensi

- Tidak ada dependency Python baru; `pywin32` tidak ditambahkan. Adapter Word
  tetap PowerShell dan hanya berjalan di Windows dengan Microsoft Word. Jika
  standalone wheel dibutuhkan, `word.ps1` harus dimasukkan sebagai package-data.
- S2 dapat menghapus future import tanpa mengubah perilaku; seluruh modul wajib
  lolos `compileall` dan full suite minimal 475 pass.
- `config.py` tetap menjadi satu sumber sampai F5. Jika gate memutuskan split,
  file diganti package `config/__init__.py`, `config/models.py`,
  `config/common.py`, `config/format.py`, `config/structure.py`, dan
  `config/validation.py`; API publik tetap. Jika tidak, `config.py`
  dipertahankan.
- `docs/dev/archive/restructure-plan.md` dan `docs/dev/archive/duplication-map.md`
  tidak lagi menjadi acuan aktif; keduanya berstatus superseded di archive. G4
  wajib memutuskan hapus atau pertahankan dengan status archived yang jelas.
- Target struktur final memuat `markdown/headings.py`, `adeu/`,
  `scripts/word.ps1`, dan stage `captions`; `docx/headings.py`, `features/`,
  `resources/`, dan `captions/figures` tidak boleh tersisa di kode aktif.
- Perubahan salah satu keputusan setelah baseline harus melalui ADR baru dan
  tidak boleh dilakukan di tengah fase.
- P0.2 selesai; P0.3 dapat dijalankan setelah P0.1 dan P0.4 memenuhi gate.

## Rujukan

- [refactor-plan.md](../archive/refactor-plan.md), bagian 1 dan 6.
- [refactor-plan.md](../archive/refactor-plan.md), P0.2 dan P0.3.
