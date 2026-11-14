# Helper Paragraf

Halaman ini menjelaskan helper kanonis untuk membaca `w:body`, child langsung,
style dan level heading, teks paragraf, penghapusan child, dan atribut integer.
Kontrak ada di [contracts/docx.md](../../contracts/docx.md).

`paragraphs.py` adalah satu tempat untuk:

- `document_body` dan `body_children`;
- `paragraph_style_id` dan `heading_level`;
- `paragraph_text`;
- `remove_direct_children`;
- `int_attribute`.

`heading_level(paragraph)` dan `paragraph_style_id(paragraph)` berada di
`paragraphs.py`, bukan `sections.py`. Semua fungsi bekerja pada elemen `lxml`
hidup dan tidak melakukan I/O package. `xml.py` tetap menjadi primitif
parse/serialisasi dan tidak boleh mengimpor modul ini.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`,
`lxml documentation`. URL resminya ada di
[registry referensi](../references.md).

## Halaman terkait

- [sections.md](sections.md) untuk pemakai helper batas section.
- [runs.md](runs.md) untuk helper isi run.
- [package.md](package.md) untuk aturan mutasi package.
- [overview.md](overview.md) untuk peta modul.
