# ADR 0006: Quality, Migrasi, dan Humanizer

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L17, L18, L19, L21, L23, L24, L25
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 12, 13, 16, dan 18.9-18.13

## Konteks

docgen memiliki tes dan disiplin dokumentasi yang kuat, tetapi mypy belum
strict. deck-studio memiliki aturan naskah dan copy checker di JavaScript,
serta quality gate Node yang terpisah. AutoOffice membutuhkan satu gate
lokal yang ketat, copy checker deterministik tanpa LLM, transkrip tervalidasi,
dokumentasi navigable, dan migrasi tanpa dead code. Tidak ada CI yang boleh
menjadi tempat bergantung.

## Keputusan

1. Gate final dijalankan lokal: ruff check, ruff format check, mypy strict,
   import-linter, pytest, coverage 100% line dan branch, docs checker,
   test-quality checker, dan no-legacy checker. Tidak ada GitHub Actions.
2. Coverage hanya untuk `src/autooffice`, tanpa omit global. Exclusion default
   hanya `TYPE_CHECKING`, `@overload`, dan baris deklarasi tipe. Exclusion
   tambahan wajib terdaftar di `docs/contracts/coverage.md`.
3. Copy checker adalah stage deterministik first-class sebelum layout. Tidak
   ada LLM, network, atau Office saat build. Input: Deck IR, Transcript IR,
   dan `copy.yaml`.
4. `copy.yaml` opsional di folder deck. Tanpa file, default berlaku. Config
   dapat mengubah severity, menambah frasa terlarang, mematikan rule, dan
   mendaftarkan allowlist dengan alasan. Build gagal pada error; warning
   dicetak.
5. Rule pack dipisah untuk `id` dan `en`. `meta.language` dinormalisasi ke
   `id` atau `en`; bahasa lain ditolak. DOCX tidak memakai humanizer dan
   tetap memakai `--terms`.
6. `transcripts.md` adalah berkas pendamping opsional, tidak disimpan di
   YAML, disalin ke `<stem>.transcript.md`, dan diperiksa copy checker.
7. Dokumentasi berada di `docs/user`, `docs/dev`, `docs/learn`,
   `docs/contracts`, dan `docs/decisions`. `docs/README.md` menjadi indeks.
   Tidak ada tutorial per fitur untuk v1.
8. Acceptance memakai demo deck dengan minimal satu slide untuk setiap layout
   yang didukung dan satu contoh setiap block type. `transcripts.md` dan
   `copy.yaml` demo wajib ada dan tervalidasi.
9. Migrasi mempertahankan perilaku DOCX, manifest, istilah, dan golden
   baseline sampai parity lulus. Penghapusan `docgen` dan `deck-studio`
   dilakukan setelah parity, bukan sebelumnya.
10. Prinsip kerja: contracts before code, satu owner per file, tidak ada merge
    tanpa verifikasi, lane file-disjoint, test sebagai kontrak, docs
    navigable, dan tidak ada shortcut yang merusak maintainability.

## Konsekuensi

- Lane tidak boleh menurunkan threshold, menambah exclusion tanpa entri, atau
  mengganti test dengan mock-only test.
- COM dan Google memakai fake di unit/contract test. Jalur nyata hanya smoke
  final.
- Copy checker tidak dapat dilewati dengan flag. Satu-satunya escape hatch
  adalah `copy.yaml` dengan alasan.
- Transkrip yang hilang tidak error bila opsional, tetapi transkrip yang ada
  wajib mencakup semua slide dan lolos validasi.
- Docs user tidak menautkan repo lama. Plan migrasi tetap boleh historis
  sesuai A24.
- Demo deck menjadi bukti acceptance, bukan sekadar contoh.
- Penghapusan kode lama dan rename repo adalah langkah akhir F3.

## Alternatif yang ditolak

- Mengandalkan GitHub Actions. Ditolak karena gate final lokal dan tidak ada
  CI.
- Menurunkan coverage atau mengecualikan seluruh file adapter. Ditolak karena
  gate menjadi tidak bermakna.
- Humanizer berbasis LLM atau layanan jaringan. Ditolak karena build harus
  deterministik dan offline.
- Menyimpan transkrip di YAML. Ditolak karena transkrip bukan model deck dan
  tidak disinkronkan ke Slides.
- Menulis tutorial per fitur. Ditolak untuk v1; fokus pada quickstart, model
  authoring, CLI, konsep, kontrak, dan troubleshooting.
- Mempertahankan test Node atau shim lama. Ditolak oleh no-dead-code.

## Status

Diterima. Perubahan gate, definisi coverage, aturan copy, format transkrip,
atau urutan migrasi memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
