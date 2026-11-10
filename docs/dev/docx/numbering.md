# Numbering dan Heading

Halaman ini menjelaskan dua modul penomoran yang berbeda: `numbering.py` untuk
angka Romawi dan nomor bab, serta `heading_numbering.py` untuk penomoran
heading DOCX. Kontrak ada di
[contracts/docx-api.md](../contracts/docx-api.md).

## `numbering.py`

`numbering.py` adalah satu sumber untuk:

- konversi token angka Romawi menjadi bilangan bulat;
- pembacaan nomor bab dari teks `BAB IV`, `BAB 4`, atau `4.`;
- pemformatan bilangan bulat menjadi angka Romawi kapital.

Modul ini murni dan tidak bergantung pada lapisan Markdown, XML, maupun
package DOCX.

## `heading_numbering.py`

`heading_numbering.py` menangani iterasi heading, nomor H1/H2/H3, heading
unnumbered, dan nama bookmark. `apply_heading_numbering` dan `is_unnumbered`
ada di modul ini, bukan di `sections.py`. Modul ini memakai `numbering.py`
untuk angka Romawi dan tidak menyentuh section, header/footer, atau geometri
halaman.

Penomoran heading Markdown sebelum Pandoc bukan tanggung jawab lapisan DOCX;
modulnya ada di `src/docgen/markdown/headings.py`.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [sections.md](sections.md) untuk batas section.
- [paragraphs.md](paragraphs.md) untuk helper level heading.
- [captions.md](captions.md) untuk nomor bab pada caption.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `numbering`.
