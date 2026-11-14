# ADR 0005: Google Sheets dan PDF

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L09, L11, L14, L22
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 8.4, 8.5, 9, dan 18.5-18.6

## Konteks

Google Slides harus menampilkan chart yang dapat diedit dan terhubung ke
data, bukan gambar. Data hanya mengalir satu arah dari YAML ke Sheets, lalu
ke Slides. Table harus tetap native di Slides agar cell dapat disinkronkan.
PDF DOCX dan PPTX harus dihasilkan di Windows dengan Word COM dan PowerPoint
COM, dengan satu lock global agar dua worker tidak menjalankan Office
bersamaan.

## Keputusan

1. Push Slides memakai alur: compile YAML, bangun staging PPTX dengan
   placeholder chart, validasi placeholder, siapkan spreadsheet dan chart,
   upload/convert ke Google Slides, preflight placeholder dan table,
   replacement linked chart, push teks, verifikasi coverage, simpan state.
2. Satu spreadsheet per deck, satu tab per chart, satu chart object per tab.
   Data satu arah dari YAML ke Sheets. Tidak ada pull chart atau edit chart
   dari Slides ke YAML.
3. Chart memakai `createSheetsChart` dengan `linkingMode: LINKED`. Bila
   linked chart untuk `chart_id` sudah ada, jangan membuat duplikat.
4. Spreadsheet dan presentasi dimiliki akun OAuth uploader, bukan service
   account. Scope: `drive.file`, `presentations`, `spreadsheets`. Client
   secret tidak boleh ada di repo.
5. Setiap push membuat presentasi baru dan menyimpan ID aktif. Presentasi
   lama tidak dihapus otomatis.
6. State berada di `.autooffice/state/<stem>.json`, memakai schema
   `autooffice.state/v1`, ditulis atomik, tidak menyimpan token OAuth, dan
   tidak masuk Git.
7. Table wajib native. Preflight memastikan page element `table` dengan
   jumlah baris dan kolom yang benar. Image, shape group, atau dimensi
   berbeda menggagalkan push. `CreateTableRequest` tidak dipakai otomatis di
   v1.
8. PDF DOCX memakai Word COM; PDF PPTX memakai PowerPoint COM. Keduanya
   Windows-only, memakai salinan file, menutup dokumen dan proses, memberi
   timeout, dan diserialisasi dengan lock global. Visual test memakai lock
   yang sama.
9. Kegagalan mengikuti urutan bagian 9.8: tidak ada mutasi remote sebelum
   preflight selesai, state mencatat progress, dan rerun harus idempoten.

## Konsekuensi

- State bukan source of truth konten. Menghapus state memaksa push membuat
  ulang spreadsheet dan presentasi.
- `pull`, `diff`, dan `apply` memerlukan `presentation_id` di state.
- `apply` menulis YAML baru di `.autooffice/review/`, bukan menimpa sumber.
- Table yang diimpor sebagai gambar atau shape group menggagalkan push tanpa
  fallback rebuild otomatis.
- Kuota API memakai retry terbatas dengan backoff, lalu gagal.
- Tidak ada penghapusan otomatis spreadsheet atau presentasi user.
- File yang dimiliki akun lain menghasilkan error yang meminta login akun
  yang sama atau reset state.
- PDF gagal keras bila Word atau PowerPoint tidak tersedia pada target yang
  meminta PDF.

## Alternatif yang ditolak

- Service account. Ditolak karena file harus dimiliki akun uploader.
- Update presentasi yang sama pada setiap push. Ditolak untuk v1 karena
  risiko kehilangan data dan lifecycle belum diuji.
- Chart sebagai gambar. Ditolak karena chart harus editable dan linked.
- Fallback otomatis `CreateTableRequest`. Ditunda; v1 gagal keras pada table
  non-native.
- Satu spreadsheet per chart. Ditolak karena kontrak satu spreadsheet per
  deck.
- LibreOffice atau Linux untuk PDF. Ditolak karena v1 Windows-only dan
  kualitas Word/PowerPoint COM.
- COM paralel. Ditolak karena lock global dan risiko hang.

## Status

Diterima. Perubahan alur Google, ownership, state, preflight table, atau
mekanisme PDF memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
