# Parser Markdown (`src/docgen/markdown`)

## Tujuan

Folder ini menyediakan parser blok Markdown dan penomoran heading yang dipakai
fitur non-Pandoc: Adeu, validasi caption, stage front matter, dan alat dev.
Implementasinya murni: menerima teks atau path dan mengembalikan model atau
teks, tanpa menyentuh DOCX. Tidak ada parser Markdown kedua di fitur Adeu.

## Ownership

- [Kontrak stage](../../../docs/dev/contracts/stage-api.md) mengatur batas
  integrasi stage; [arsitektur](../../../docs/dev/architecture.md) menetapkan
  folder ini bebas `lxml` dan `docx`.
- Nama publik diekspor dari `markdown/__init__.py`; modul baru harus punya
  satu alasan dan tidak menduplikasi `blocks.py` atau `headings.py`.
- `blocks.py` memiliki parsing blok; `headings.py` memiliki penomoran heading.
  Perubahan perilaku keduanya memengaruhi Adeu dan front matter, jadi
  koordinasikan dengan pemilik fitur tersebut.
- Sumber kebenaran perilaku: `markdown/__init__.py` dan tes
  `tests/unit/test_markdown_headings.py` serta tes Adeu terkait.

## API publik

- Blok: `MarkdownBlock`, `load_markdown_blocks`, `parse_markdown_blocks`,
  `load_markdown_directory`, `iter_candidate_texts`, `clean_text`,
  `normalize_inline`, `normalize_for_match`, `normalize_heading`,
  `normalize_path`, dan `MarkdownError`.
- Heading: `MarkdownHeading`, `HeadingNumberer`, `Heading`, `NumberingSpec`,
  `MarkdownHeadingError`, `parse_heading`, `render_heading`, `heading_level`,
  `number_markdown`, `number_markdown_headings`, `balance_title`,
  `format_chapter_number`, `is_unnumbered`, `roman`, dan
  `uppercase_markdown`.

## Larangan

- Jangan mengimpor `lxml`, `python-docx`, `docgen.docx`, `docgen.stages`,
  `docgen.pipeline`, atau `docgen.adeu`.
- Jangan membaca atau menulis ZIP/DOCX; folder ini hanya bekerja pada teks
  Markdown dan path.
- Jangan menambah parser blok kedua di Adeu atau stage; gunakan API di sini.
- Jangan menerapkan aturan visual Word di parser; parser hanya menormalisasi
  teks dan nomor heading.
- Jangan menulis file output; pemanggil yang menyimpan hasil.

## Tautan

- [Arsitektur](../../../docs/dev/architecture.md)
- [Kontrak stage](../../../docs/dev/contracts/stage-api.md)
- [Rencana refactor](../../../docs/dev/refactor-plan.md)
- [README paket](../README.md)
- [README Adeu](../adeu/README.md)
