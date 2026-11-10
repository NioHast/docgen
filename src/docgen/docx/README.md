# Lapisan DOCX (`src/docgen/docx`)

## Tujuan

Folder ini adalah satu-satunya pemilik ZIP/OPC, XML Word, package DOCX,
style, section, field, caption, tabel, layout, dan bookmark. Stage menerima
satu `DocumentPackage` di memori dari pipeline, lalu memutasi part yang
dideklarasikan; hanya pipeline yang memanggil `load()` dan `save()`. Tujuan
utamanya adalah satu load, satu save, dan part non-target tetap byte-identik.

## Ownership

- [Kontrak DOCX](../../../docs/dev/contracts/docx-api.md) adalah sumber
  kebenaran API dan invariant. README ini tidak menggantikan kontrak.
- Nama publik diekspor dari `docx/__init__.py`; untuk istilah, dari
  `docx/terms/__init__.py`. Menambah export berarti memperbarui kontrak dan
  tes.
- Helper kanonis tidak boleh diduplikasi: `paragraphs.py` untuk traversal
  paragraf, `runs.py` untuk run, `numbering.py` untuk Romawi/nomor bab, dan
  `page.py` untuk ukuran halaman.
- Perubahan pada `xml.py`, `io.py`, atau `package.py` menyentuh seluruh
  pipeline dan harus dikoordinasikan dengan pemilik area DOCX.

## API publik

- Package: `DocumentPackage` (alias publik `DocxPackage`), `PartInfo`,
  `Relationship`, dan operasi `load`, `save`, `part`, `xml`, `set_part`,
  `set_xml`, `remove_part`.
- Error: `DocxError`, `PackageError`, `PartNotFoundError`,
  `PartExistsError`, `InvalidPackageError`, `SaveError`, dan `XmlError`.
- XML: `parse_xml`, `serialize_xml`, `canonicalize_xml`, `sha256_c14n`, `qn`,
  `iter_paragraphs`, dan `iter_runs`.
- Paragraf dan run: `document_body`, `body_children`, `paragraph_style_id`,
  `heading_level`, `paragraph_text`, `make_run`, `append_text_run`,
  `clone_run`, `copy_rpr`, dan `strip_bold_from_rpr`.
- Nomor dan halaman: `roman_to_int`, `to_roman`, `chapter_number`,
  `PAGE_SIZES`, `page_size`, dan `content_width`.
- Field, style, section, caption, tabel, layout, dan bookmark tersedia dari
  modul masing-masing dan diekspor ulang di `docx/__init__.py`.
- Istilah: `open_docx`, `apply_terms`, `verify_terms`, `load_glossary`,
  `merge_glossaries`, `TermsReport`, dan `TermsVerifyReport`.

## Larangan

- Jangan memakai `python-docx`, membuka/menulis ZIP langsung di luar `io.py`,
  atau menambah parser XML kedua. `python-docx` hanya untuk tes dan factory.
- Jangan membaca `format.yml`, `structure.yml`, Markdown, atau `document.md`;
  caller memberikan spesifikasi yang sudah dinormalisasi.
- Jangan mengimpor `stages/`, `pipeline.py`, `cli.py`, atau `adeu/`.
- Jangan memanggil `load()` atau `save()` package target dari stage.
- Jangan mengubah part yang tidak tercantum di `mutates`; jangan menambah
  normalisasi di luar profil c14n kontrak.
- Jangan menyembunyikan error XML; bungkus sebagai `DocxError` atau subclass.

## Tautan

- [Kontrak DOCX](../../../docs/dev/contracts/docx-api.md)
- [Arsitektur](../../../docs/dev/architecture.md)
- [Peta repo](../../../docs/dev/repo-map.md)
- [Testing](../../../docs/dev/testing.md)
- [Rencana refactor](../../../docs/dev/archive/refactor-plan.md)
- [README paket](../README.md)
