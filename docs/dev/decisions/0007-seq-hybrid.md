# ADR 0007: Hybrid `SEQ` untuk Daftar Tabel dan Gambar

- Status: diterima
- Tanggal: 2026-11-09

## Konteks

Field `TOC \c "Tabel"` dan `TOC \c "Gambar"` hanya mengisi daftar bila caption
memiliki field yang dapat dihitung Word. Filter Lua lama sudah menulis field
`TOC \c`, tetapi tidak menulis `SEQ`, sehingga daftar kosong.

Spike Microsoft Word 16.0 di Windows menunjukkan:

- `STYLEREF 1 \s` menghasilkan `0` karena heading memakai nomor literal, bukan
  numbering Word;
- `STYLEREF "Heading 1"` menghasilkan seluruh teks heading, misalnya `BAB II`;
- hybrid prefix bab literal ditambah `SEQ Tabel \* ARABIC \s 1` menghasilkan
  `Tabel 2.1` dan mengisi daftar.

## Keputusan

Caption tabel dan gambar memakai hybrid:

1. Stage `captions/figures` menulis nomor bab literal dan nomor urut, misalnya
   `Tabel 2.1`.
2. Stage `lists` mengganti angka urut terakhir dengan field
   `SEQ <Label> \* ARABIC \s 1`.
3. Prefix bab tetap literal, misalnya `Tabel 2.`.
4. Daftar memakai field `TOC \c "Tabel"` atau `TOC \c "Gambar"`.

Untuk format dengan `figures.numbering: document`, field `SEQ` tidak memakai
`\s 1` dan tidak ada prefix bab.

## Konsekuensi

- Daftar tabel dan gambar dapat diisi Word tanpa numbering heading Word.
- Nomor caption tetap benar meskipun heading memakai nomor literal.
- Word wajib memperbarui field untuk mengisi daftar.
- Caption harus ada sebelum stage `lists` berjalan.
- Perubahan label caption harus konsisten antara `format.yml`, caption, dan
  field `TOC \c`.
- Debian dapat membangun DOCX, tetapi daftar belum terisi tanpa Word.

## Alternatif yang ditolak

- **`STYLEREF`.** Ditolak karena menghasilkan `0` atau seluruh teks heading.
- **Daftar statis.** Ditolak karena tidak ikut berubah saat nomor caption
  berubah.
- **Numbering heading Word.** Ditolak karena mengubah perilaku heading dan
  tidak kompatibel dengan format `BAB I` literal.
- **Hanya `TOC \c` tanpa `SEQ`.** Ditolak karena daftar kosong.
