# Lapisan DOCX

Folder ini menjelaskan lapisan `src/docgen/docx/`, model package, modul internal,
dan batas tanggung jawab setiap helper. Kontrak API lengkap ada di
[contracts/docx-api.md](../contracts/docx-api.md).

## Halaman

| Halaman | Isi |
| --- | --- |
| [overview.md](overview.md) | Posisi lapisan DOCX, peta modul, dan batas helper kanonis. |
| [package.md](package.md) | `DocumentPackage`, part, relationship, load/save, dan idempotensi. |
| [styles.md](styles.md) | Style inti dan `reference.docx`. |
| [paragraphs.md](paragraphs.md) | Helper body, style, level heading, teks, dan atribut paragraf. |
| [runs.md](runs.md) | Pembuatan, penyalinan, dan pembersihan run. |
| [numbering.md](numbering.md) | Angka Romawi, nomor bab, dan penomoran heading DOCX. |
| [page.md](page.md) | Ukuran halaman, margin, dan `content_width`. |
| [sections.md](sections.md) | Section break, margin, header, dan footer. |
| [fields.md](fields.md) | Field TOC, PAGEREF, SEQ, PAGE, dan NUMPAGES. |
| [bookmarks.md](bookmarks.md) | Bookmark `pNNNN` dan manifest Adeu. |
| [captions.md](captions.md) | Caption tabel/gambar, numbering, dan layout gambar. |
| [layout.md](layout.md) | Spasi, indentasi, perataan, bold, dan klasifikasi blok. |
| [terms.md](terms.md) | Glosarium, penanda istilah, verifikasi, dan audit. |

## Urutan baca

1. [overview.md](overview.md) untuk peta lapisan.
2. [package.md](package.md) untuk aturan global package.
3. Halaman topik sesuai modul yang sedang diubah.
4. [terms.md](terms.md) untuk fitur istilah dan glosarium.

Dokumen terkait: [pipeline](../pipeline/README.md),
[integrasi Adeu](../adeu-integration.md), dan
[kontrak konfigurasi](../contracts/config.md).
