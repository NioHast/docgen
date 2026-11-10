# Layout Paragraf

Halaman ini menjelaskan helper layout untuk stage `normalize` dan stage DOCX
lain. Kontrak ada di [contracts/docx-api.md](../contracts/docx-api.md).

`layout.py` adalah satu tempat untuk:

- urutan child `w:pPr`/`w:rPr` dan helper `get_or_add`;
- traversal paragraf/run yang aman terhadap text box dan tracked changes;
- pemakaian scanner field dari `fields.py`;
- penghapusan bold langsung dengan pengecualian run field;
- pembacaan/penulisan `word/document.xml` melalui `DocumentPackage`;
- deteksi `ChapterTitle`/Heading1 sebagai paragraf bab.

Tidak ada I/O ZIP di modul ini. Semua mutasi part dilakukan lewat
`DocumentPackage` agar aturan satu load/satu save tetap berlaku.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`,
`lxml documentation`. URL resminya ada di
[registry referensi](../references.md).

## Halaman terkait

- [paragraphs.md](paragraphs.md) untuk helper paragraf.
- [runs.md](runs.md) untuk helper run.
- [fields.md](fields.md) untuk scanner field.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `normalize`.
