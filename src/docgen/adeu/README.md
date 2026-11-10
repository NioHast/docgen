# Adeu (`src/docgen/adeu`)

## Tujuan

Folder ini menangani bookmark paragraf `pNNNN`, manifest Adeu, pemindaian
sumber Markdown, dan rekonsiliasi edit manual DOCX dengan manifest. Fitur ini
membantu memetakan paragraf DOCX ke blok sumber tanpa mengubah naskah. Hook
pipeline dijalankan setelah stage `lists` dan sebelum save; urutan itu dimiliki
`pipeline.py`, bukan folder ini.

## Ownership

- [Integrasi Adeu](../../../docs/dev/adeu-integration.md) adalah sumber
  kebenaran perilaku manifest, bookmark, dan reconcile.
- `adeu/__init__.py` adalah daftar API publik; `cli.py` hanya mendaftarkan
  subperintah `reconcile`. Hook pemanggilan di `pipeline.py` dimiliki pemilik
  pipeline.
- Perubahan format manifest harus memperbarui `MANIFEST_VERSION`, tes Adeu,
  dan dokumen integrasi. Manifest harus deterministik: tanpa timestamp.
- Modul baru harus berada di area manifest, paragraph ID, atau reconcile;
  jangan mencampur orkestrasi stage.

## API publik

- Manifest: `Manifest`, `ManifestParagraph`, `load_manifest`,
  `validate_manifest`, `dump_manifest`, `manifest_to_dict`,
  `manifest_from_dict`, `default_manifest_path`, dan `sha256_text`.
- Paragraph ID: `prepare_manifest`, `write_prepared_manifest`,
  `add_paragraph_ids`, `run_docx`, `resolve_options`, dan
  `analyze_manifest`.
- Reconcile: `run`, `build_report`, `extract_bookmarks`, `find_source`,
  `DocxSnapshot`, `ReconcileResult`, dan `SourceMatch`.
- CLI: `adeu.cli.register_reconcile`, `command_reconcile`, dan `main`;
  entry point `python -m docgen.adeu.cli`.
- Error domain: `ManifestError` dan `ReconcileError` dari `docgen.errors`.

## Larangan

- Jangan mengimpor `docgen.pipeline` atau `docgen.stages`; hook pipeline
  adalah tanggung jawab pemilik pipeline.
- Jangan mengubah urutan stage atau memanggil pipeline dari folder ini.
- Jangan mengubah DOCX, manifest, atau Markdown saat reconcile; reconcile
  hanya membaca dan menulis laporan tinjauan.
- Jangan menambah parser Markdown kedua; gunakan `docgen.markdown`.
- Jangan menulis timestamp atau urutan non-deterministik ke manifest.
- Jangan membuka ZIP atau mem-parse XML dari byte sendiri; gunakan
  `DocumentPackage.xml()` dan API `docgen.docx`.

## Tautan

- [Integrasi Adeu](../../../docs/dev/adeu-integration.md)
- [Kontrak DOCX](../../../docs/dev/contracts/docx-api.md)
- [Kontrak stage](../../../docs/dev/contracts/stage-api.md)
- [Peta repo](../../../docs/dev/repo-map.md)
- [Rencana refactor](../../../docs/dev/refactor-plan.md)
- [README paket](../README.md)
