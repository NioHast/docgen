# Gambaran Lapisan DOCX

Halaman ini menjelaskan posisi lapisan DOCX dan peta modulnya. Kontrak API
lengkap ada di [contracts/docx-api.md](../contracts/docx-api.md).

`src/docgen/docx/` adalah satu-satunya lapisan yang membaca dan menulis paket
DOCX. Stage tidak menyentuh ZIP secara langsung. Semua mutasi terjadi pada
`DocumentPackage` di memori, lalu pipeline menyimpan satu kali.

## Peta modul

| Modul | Tanggung jawab |
| --- | --- |
| `package.py` | Model package, part, relationship, load/save. |
| `io.py` | Baca/tulis ZIP dan penulisan atomic. |
| `xml.py` | Parse, serialisasi, c14n, hash, helper elemen. |
| `names.py` | Namespace, tag, style, dan konstanta lain. |
| `paragraphs.py` | Akses `w:body`, child langsung, style dan level heading, teks paragraf, hapus child, atribut integer. |
| `runs.py` | Pembuatan, penyalinan, dan pembersihan `w:r`/`w:rPr`. |
| `numbering.py` | Konversi angka Romawi dan nomor bab. |
| `heading_numbering.py` | Penomoran heading DOCX: iterasi, nomor H1/H2/H3, unnumbered, nama bookmark. |
| `page.py` | Konstanta/helper ukuran halaman, `content_width`, dan `PageError`. |
| `styles.py` | Style paragraf, karakter, tabel, dan page layout. |
| `sections.py` | Section break, margin, ukuran halaman, header/footer. |
| `captions.py` | Caption tabel/gambar, numbering, layout gambar. |
| `tables.py` | Tabel biasa, tabel kode, border, cell margin. |
| `layout.py` | Spasi, indentasi, perataan, bold, dan klasifikasi blok. |
| `fields.py` | TOC, PAGEREF, SEQ, PAGE, NUMPAGES. |
| `bookmarks.py` | Bookmark `pNNNN` dan verifikasi. |
| `terms.py` | Glosarium, style istilah, transformasi run, verifikasi. |

## Batas helper kanonis

`heading_level(paragraph)` dan `paragraph_style_id(paragraph)` berada di
`paragraphs.py`, bukan `sections.py`. `sections.py` memakai helper tersebut untuk
mengenali heading batas section, tetapi tidak memiliki penomoran heading:
`apply_heading_numbering` dan `is_unnumbered` ada di `heading_numbering.py`.
Modul itu memakai `numbering.py` untuk angka Romawi dan tidak menyentuh
section, header/footer, atau geometri halaman. Rincian ada di
[paragraphs.md](paragraphs.md), [sections.md](sections.md), dan
[numbering.md](numbering.md).

Penomoran heading Markdown sebelum Pandoc bukan tanggung jawab lapisan DOCX;
modulnya ada di `src/docgen/markdown/headings.py`.

## Referensi resmi

Label registry yang dipakai halaman ini: `OOXML ECMA-376`, `Open XML SDK`,
`WordprocessingML API reference`. URL resminya ada di
[registry referensi](../references.md).

## Halaman topik

- [package.md](package.md) untuk model package dan aturan global.
- [styles.md](styles.md), [layout.md](layout.md), dan
  [captions.md](captions.md) untuk pemformatan isi.
- [fields.md](fields.md), [bookmarks.md](bookmarks.md), dan
  [terms.md](terms.md) untuk fitur Word.
- [paragraphs.md](paragraphs.md), [runs.md](runs.md), [numbering.md](numbering.md),
  [page.md](page.md), dan [sections.md](sections.md) untuk helper kanonis.
