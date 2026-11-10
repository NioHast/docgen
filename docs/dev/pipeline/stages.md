# Urutan Stage

Halaman ini memuat urutan kanonik stage dan guard yang wajib ditegakkan.
Kontrak stage ada di [contracts/stage-api.md](../contracts/stage-api.md).

## Urutan stage

| Order | Stage | Modul | Memutasi | Catatan |
| ---: | --- | --- | --- | --- |
| 10 | `validate` | `stages/validate.py` | - | Caption tabel dan alt text gambar. |
| 20 | `mermaid` | `stages/mermaid.py` | workspace | Blok Mermaid menjadi PNG. |
| 30 | `style_reference` | `stages/style_reference.py` | workspace, cache | `reference.docx` turunan dari `format.yml`. |
| 35 | `front_matter` | `stages/front_matter.py` | workspace | Sampul, template, abstrak, nomor heading. |
| 40 | `pandoc` | `stages/pandoc.py` | package | Markdown menjadi DOCX. |
| 50 | `sections` | `stages/sections.py` | `word/document.xml` | Section break, margin, ukuran halaman, nomor heading DOCX. |
| 60 | `code` | `stages/code.py` | `word/document.xml` | Blok kode menjadi tabel 1x1. |
| 70 | `captions` | `stages/captions.py` | `word/document.xml` | Caption wajib, nomor bab, layout gambar. |
| 80 | `normalize` | `stages/normalize.py` | `word/document.xml` | Spasi 1,5, justify, hapus bold body. |
| 90 | `equations` | `stages/equations.py` | `word/document.xml` | Nomor persamaan `(bab.n)`. |
| 100 | `numbering` | `stages/numbering.py` | `word/document.xml`, `word/numbering.xml` | Indentasi daftar. |
| 110 | `blank_lines` | `stages/blank_lines.py` | `word/document.xml` | Paragraf kosong sesuai aturan layout. |
| 120 | `terms` | `stages/terms.py` | `word/document.xml`, `word/styles.xml` | Hanya aktif dengan `--terms`. |
| 130 | `toc` | `stages/toc.py` | `word/document.xml`, `word/styles.xml` | Field TOC native bila `structure.toc`. |
| 140 | `page_numbers` | `stages/page_numbers.py` | document, header/footer, rels, content types | Romawi front matter, Arab body. |
| 150 | `lists` | `stages/lists.py` | `word/document.xml` | Daftar tabel/gambar dan field `SEQ`. |
| 160 | `office` | `stages/office.py` | package | Word memperbarui field dan menyimpan DOCX. |
| 170 | `pdf` | `stages/pdf.py` | - | Word mengekspor PDF, Windows only. |

## Guard

- `style_reference` sebelum `front_matter`;
- `front_matter` sebelum `pandoc`;
- `sections` sebelum `code`, lalu `captions`, `normalize`, `equations`;
- `terms` sebelum `toc`, `toc` sebelum `page_numbers`, `page_numbers` sebelum
  `lists`;
- `office` sebelum `pdf`.

Stage yang salah urutan, duplikat, atau memutasi part tidak dikenal
menggagalkan `validate_stage_order`.

## Batas stage

Stage tidak boleh memanggil `load` atau `save` package target. Model satu load
dan satu save dijelaskan di [overview.md](overview.md#satu-load-dan-satu-save).
Opsi yang mengaktifkan stage tertentu ada di [options.md](options.md).

## Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc manual`, `Mermaid CLI`,
`Word COM object model (VBA reference)`. URL resminya ada di
[registry referensi](../references.md).
