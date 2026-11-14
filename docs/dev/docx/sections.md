# Section, Header, dan Footer

Halaman ini menjelaskan section break, margin, ukuran halaman, header, dan
footer. Kontrak ada di [contracts/docx.md](../../contracts/docx.md).

`src/autooffice/docx/package/sections.py` adalah satu-satunya pintu untuk membaca dan
mengubah `w:sectPr`, format nomor halaman, serta part header/footer. Stage
tidak memakai `zipfile` atau regex terhadap `document.xml`; semua perubahan
melewati helper di modul ini.

`sections.py` memakai `heading_level` dan `paragraph_style_id` dari
`paragraphs.py` untuk mengenali heading batas section, tetapi tidak memiliki
penomoran heading. `apply_heading_numbering` dan `is_unnumbered` ada di
`heading_numbering.py`, yang tidak menyentuh section, header/footer, atau
geometri halaman.

Section pada OOXML diakhiri `w:sectPr`; section terakhir memakai `w:sectPr` di
akhir `w:body`, sedangkan section lain memakai `w:sectPr` di dalam `w:pPr`
paragraf pemutus. Model `Section` memakai indeks child langsung `w:body` agar
stabil untuk pembacaan dan penyisipan.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [page.md](page.md) untuk ukuran halaman dan `content_width`.
- [numbering.md](numbering.md) untuk penomoran heading.
- [paragraphs.md](paragraphs.md) untuk helper heading.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `sections` dan
  `page_numbers`.
