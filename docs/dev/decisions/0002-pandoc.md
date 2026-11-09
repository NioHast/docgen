# ADR 0002: Pandoc sebagai Konverter DOCX

- Status: diterima
- Tanggal: 2026-11-09

## Konteks

Markdown harus diubah menjadi DOCX yang memiliki style Word, tabel, gambar,
persamaan OMML, sitasi BibTeX, dan daftar pustaka. Menulis konverter OOXML
sendiri berarti memelihara parser Markdown, writer DOCX, citeproc, dan
penanganan persamaan sekaligus.

## Keputusan

Pandoc tetap menjadi satu-satunya konverter Markdown ke DOCX. Pipeline
memanggil Pandoc dengan `reference.docx` turunan dari `format.yml`, lalu
melakukan seluruh pascaproses pada package DOCX.

Pandoc tidak memakai filter Lua dan tidak diminta menulis TOC. TOC, daftar,
caption, section, dan penomoran heading ditulis stage Python setelah DOCX
terbentuk.

## Konsekuensi

- Dukungan tabel, gambar, persamaan, dan `--citeproc` didapat tanpa menulis
  writer sendiri.
- Perilaku Pandoc menjadi dependensi eksternal yang harus tersedia.
- Versi Pandoc perlu stabil agar keluaran konsisten.
- `reference.docx` menjadi kontrak visual antara Pandoc dan pipeline.
- Semua perilaku yang tidak dapat diwakili AST Markdown ditangani di DOCX,
  bukan di Markdown.

## Alternatif yang ditolak

- **Writer DOCX sendiri.** Ditolak karena biaya implementasi dan pemeliharaan
  terlalu besar.
- **Konverter berbasis HTML.** Ditolak karena fidelity OMML, section, dan
  field Word lebih sulit dijaga.
- **Filter Lua untuk semua pascaproses.** Ditolak karena logika Word lebih
  mudah diuji dan diisolasi dalam stage Python.
