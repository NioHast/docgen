# Halaman dan Margin

Halaman ini menjelaskan konstanta dan helper ukuran halaman. Kontrak ada di
[contracts/docx.md](../../contracts/docx.md).

`page.py` menyatukan:

- `PAGE_SIZES` untuk `A4` dan `Letter`;
- `page_size(name, orientation)`;
- `content_width(body)`;
- `PageError`.

Seluruh nilai memakai satuan twip; 1 inci = 1440 twip. Orientasi landscape
diturunkan dengan menukar lebar dan tinggi, bukan disimpan sebagai entri
terpisah. `content_width` adalah satu-satunya sumber lebar area teks: nilainya
dibaca dari `w:sectPr` terakhir dan tidak memakai lebar cadangan. Section atau
atribut wajib yang tidak lengkap menghasilkan `PageError`, bukan angka
tebakan.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [sections.md](sections.md) untuk pemakaian ukuran dan margin.
- [package.md](package.md) untuk part `word/document.xml`.
- [../formats.md](../formats.md) untuk `page` di `format.yml`.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `sections`.
