# ADR 0010: Kebijakan Coverage Berbasis Risiko

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L17
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 12.3, 12.11, dan 18.9;
  [ADR 0006](0006-quality-migration-and-humanizer.md); dan
  [kontrak coverage](../contracts/coverage.md)

## Konteks

Kontrak coverage F0 mewajibkan 100% line dan branch untuk seluruh
`src/autooffice`. Target itu mahal dan tidak cost-effective: mengejar baris
terakhir di adapter COM, Google, CLI, dan DOCX menghabiskan waktu yang lebih
baik dialokasikan ke modul berisiko tinggi. Target global yang terlalu ketat
juga mendorong exclusion seluruh file, test yang hanya memanggil fungsi tanpa
assertion, atau pengejaran angka yang tidak menambah keyakinan.

Coverage hanya mengukur eksekusi, bukan correctness. Google Testing Blog,
*Code Coverage Best Practices*, menempatkan coverage sebagai alat menemukan
area yang belum diuji, bukan tujuan akhir. CMU SEI, *Don't Play Developer
Testing Roulette: How to Use Test Coverage*, menunjukkan bahwa partial
coverage adalah risiko dan harus dipasangkan dengan test yang efektif.
Mutation testing seperti `mutmut` melengkapi sinyal ini dengan menguji kekuatan
assertion. Label referensi tersedia di
[registry referensi](../dev/references.md#registry).

Modul kritis memilih jalur yang mengikat kontrak dan mahal bila salah: key,
binding, grid, layout spec, aturan copy, chart spec, dan transcript parser.
Modul adapter memilih boundary yang sulit diuji penuh tanpa COM atau layanan
Google live.

## Keputusan

1. Global line+branch minimal 90.0%.
2. Modul kritis tetap 100.0%. Daftar awalnya:
   `autooffice.deck.model.keys`, `autooffice.deck.model.bindings`,
   `autooffice.deck.layout.grid`, `autooffice.deck.layout.spec`,
   `autooffice.deck.copy.rules.title_case`,
   `autooffice.deck.copy.rules.patterns`, `autooffice.deck.charts.spec`, dan
   `autooffice.deck.transcript.parser`.
3. Modul adapter minimal 85.0% untuk `autooffice.google.*`,
   `autooffice.pdf.*`, `autooffice.cli.*`, dan `autooffice.docx.*`.
4. Kode baru per commit ditargetkan 95-99% sebagai target review, bukan ambang
   gate terpisah.
5. `tools/quality/check_coverage.py` membaca `.coverage` lewat API `coverage`,
   menerapkan tiga ambang di atas, mendukung `--format text|json` dan
   `--list`, serta keluar 1 bila kebijakan gagal. Keluaran kegagalan mencetak
   baris dan branch yang hilang.
6. Step gate `tests` memakai `--cov-fail-under=90`; step `coverage-policy`
   berjalan setelah `tests` dan tetap memblokir.
7. Exclusion yang sudah tercatat di kontrak coverage dipertahankan. Tidak ada
   whole-file omit baru untuk modul bisnis atau adapter.
8. Property test memakai `hypothesis` pada dev dependency. Mutation test,
   property test yang lebih luas, dan visual test menyusul; ketiganya bukan
   pengganti gate coverage.

## Konsekuensi

- Gate tidak lagi menuntut 100% global; suite yang sehat tetap harus menjaga
  minimal 90% line+branch.
- Modul kritis tetap 100% dan tetap memblokir merge. Regresi di sana tidak
  boleh dikompensasi oleh coverage global yang tinggi.
- Adapter memiliki ruang 15% untuk cabang platform yang sulit diuji, tetapi
  bukan izin untuk melewatkan error path penting.
- Checker membutuhkan data branch; `.coverage` tanpa arc branch ditolak agar
  target branch tidak lolos secara semu.
- Coverage tetap alat risiko, bukan jaminan correctness. Assertion yang lemah
  dan mutan yang bertahan harus ditangkap review, test-quality checker, atau
  mutation testing.
- Klausa 100% global di ADR 0006 diamendemen oleh ADR ini. Semangat ADR 0006
  tentang gate lokal dan test perilaku tetap berlaku.

## Alternatif yang ditolak

- Mempertahankan 100% global. Ditolak karena mahal, memberi diminishing
  returns, dan mendorong exclusion atau test tanpa assertion.
- Menurunkan semua modul ke 90%. Ditolak karena modul kritis membutuhkan
  jaminan eksekusi penuh untuk jalur kontraknya.
- Hanya memakai satu angka global. Ditolak karena modul kritis dan adapter bisa
  tertutup oleh modul lain yang coverage-nya tinggi.
- Menghapus gate coverage. Ditolak karena kehilangan sinyal murah untuk
  menemukan jalur yang tidak pernah dieksekusi.
- Mengandalkan mutation testing saja. Ditolak karena biayanya tinggi untuk
  seluruh repo dan belum menjadi bagian gate.
- Mengecualikan seluruh file adapter. Ditolak karena menyembunyikan kode yang
  justru berisiko dan melanggar kontrak exclusion.

## Status

Diterima. Perubahan daftar modul kritis, ambang, atau cara gate membaca
coverage memerlukan ADR baru. Mutation testing dan visual test tetap menjadi
pekerjaan lanjutan sesuai kontrak coverage.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
