# Caption dan Tabel

Halaman ini menjelaskan caption tabel/gambar dan perlakuan tabel. Kontrak ada
di [contracts/docx.md](../../contracts/docx.md).

- Tabel biasa diberi caption `Tabel bab.n` di atas tabel.
- Gambar diberi caption `Gambar bab.n` di bawah gambar.
- Alt text gambar menjadi sumber caption.
- Lebar gambar dibatasi 14 cm.
- Blok kode menjadi tabel 1x1 dengan border penuh.
- Caption wajib ada; tabel tanpa caption menggagalkan stage.

Nomor bab pada caption dibaca lewat helper di `numbering.py`. Field `SEQ`
ditulis oleh `fields.py`, dan daftar tabel/gambar memakai hybrid prefix bab
literal ditambah field `SEQ`.
Detail keputusan ada di [../decisions/0007-seq-hybrid.md](../decisions/0007-seq-hybrid.md).

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [fields.md](fields.md) untuk field `SEQ` dan `TOC \c`.
- [numbering.md](numbering.md) untuk nomor bab.
- [layout.md](layout.md) untuk normalisasi paragraf.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `captions`,
  `code`, dan `lists`.
