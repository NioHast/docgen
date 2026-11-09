# ADR 0005: Satu Load dan Satu Save DOCX

- Status: diterima
- Tanggal: 2026-11-09

## Konteks

Pascaproses DOCX dapat dilakukan dengan memuat dan menyimpan package berkali-
kali, satu kali per alat. Cara itu mudah dimulai, tetapi membuat part
non-target berubah, memperlambat build, dan menyulitkan pembuktian bahwa
perubahan hanya terjadi di part yang dimaksud. Setiap alat juga dapat
menulis intermediate DOCX yang berbeda.

## Keputusan

Pipeline memuat `DocumentPackage` tepat satu kali setelah Pandoc dan menyimpan
tepat satu kali sebelum `office`. Semua stage yang memutasi DOCX bekerja pada
package di memori dan hanya menyentuh part yang dideklarasikan.

Stage tidak boleh memanggil `load` atau `save` package target. `office` dan
`pdf` berjalan setelah save dan bekerja pada berkas DOCX hasil save. Bookmark
diverifikasi setelah `office`.

## Konsekuensi

- Part non-target dapat dijamin byte-identik.
- Jumlah save dan load dapat dihitung oleh tes.
- Semua stage harus memakai API `docgen.docx`, bukan memanipulasi ZIP sendiri.
- Error di tengah pipeline tidak meninggalkan output setengah jadi.
- Stage baru tidak dapat menyimpan intermediate DOCX di direktori output.
- `--keep` menjadi satu-satunya cara mempertahankan workspace dan intermediate.

## Alternatif yang ditolak

- **Load/save per stage.** Ditolak karena mengubah part non-target dan
  memperbesar risiko regresi.
- **Menulis DOCX baru setiap tahap.** Ditolak karena sulit diaudit dan
  menghasilkan banyak artefak.
- **Menggabungkan semua tahap dalam satu fungsi besar.** Ditolak karena batas
  tanggung jawab dan pengujian menjadi kabur.
