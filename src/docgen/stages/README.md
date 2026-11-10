# Stage pipeline (`src/docgen/stages`)

## Tujuan

Setiap modul di folder ini adalah satu stage kanonik yang mengubah satu
concern pada `StageContext`; urutan dan lifecycle dimiliki `pipeline.py`.
Stage bekerja pada `DocumentPackage` di memori dan hanya boleh memutasi part
yang dideklarasikan. Folder ini tidak menyimpan naskah, konfigurasi, atau
data format.

## Ownership

- [Kontrak stage](../../../docs/dev/contracts/stage-api.md) adalah sumber
  kebenaran protokol, urutan, `mutates`, dan guard.
- `pipeline.py` memiliki `StageName`, `CANONICAL_ORDER`, dan urutan eksekusi.
  `stages/__init__.py` hanya mendaftarkan kelas stage lewat `default_stages()`.
- Satu stage dimiliki oleh satu concern; perubahan yang menyentuh beberapa
  stage harus dikoordinasikan dengan pemilik pipeline. Jangan mengimpor stage
  lain.
- Stage baru harus terdaftar di `StageName`, `CANONICAL_ORDER`, dan
  `default_stages()`, serta dijelaskan di kontrak.

## API publik

API utama folder ini adalah `default_stages()`. Setiap modul mengekspor
kelas `*Stage` dan fungsi transformasi utamanya:

| Modul | Stage | API transformasi utama |
| --- | --- | --- |
| `validate.py` | `validate` | `check_markdown`, `validate_markdown`, `validate_body` |
| `mermaid.py` | `mermaid` | `extract_blocks`, `render_blocks` |
| `style_reference.py` | `style_reference` | `style_specs_for_format`, `build_reference_docx`, `verify_reference_docx` |
| `front_matter.py` | `front_matter` | `render_front_matter`, `render_template` |
| `pandoc.py` | `pandoc` | `build_pandoc_command`, `run_pandoc` |
| `sections.py` | `sections` | `SectionsStage` |
| `code.py` | `code` | `apply_code` |
| `captions.py` | `captions` | `apply_captions` |
| `normalize.py` | `normalize` | `NormalizeStage` |
| `equations.py` | `equations` | `format_equations` |
| `numbering.py` | `numbering` | `format_numbering` |
| `blank_lines.py` | `blank_lines` | `insert_blank_lines` |
| `terms.py` | `terms` | `resolve_glossary` |
| `toc.py` | `toc` | `ensure_toc_styles`, `tab_position` |
| `page_numbers.py` | `page_numbers` | `page_part`, `empty_part` |
| `lists.py` | `lists` | `ListsStage` |
| `office.py` | `office` | `update_fields`, `export_pdf` |
| `pdf.py` | `pdf` | `PdfStage` |

## Larangan

- Jangan memanggil `DocumentPackage.load()` atau `save()` untuk dokumen
  target; pipeline yang melakukannya sekali.
- Jangan membuka atau menulis ZIP, memakai `python-docx`, atau mem-parse XML
  dari byte sendiri. Gunakan API `docgen.docx`.
- Jangan mengimpor stage lain atau mengubah urutan stage; orkestrasi hanya di
  `pipeline.py`.
- Jangan menulis ke luar `ctx.workspace`, `ctx.output_dir`, atau
  `.laporan/`; jangan menyentuh file input pengguna.
- Jangan menaruh aturan visual di stage sebagai angka ajaib; ambil dari
  `ctx.format` atau `ctx.structure` yang sudah dinormalisasi.
- Jangan membuat stage kedua untuk concern yang sudah punya modul.

## Tautan

- [Kontrak stage](../../../docs/dev/contracts/stage-api.md)
- [Arsitektur](../../../docs/dev/architecture.md)
- [Kontrak DOCX](../../../docs/dev/contracts/docx-api.md)
- [Rencana refactor](../../../docs/dev/archive/refactor-plan.md)
- [README paket](../README.md)
- [README DOCX](../docx/README.md)
