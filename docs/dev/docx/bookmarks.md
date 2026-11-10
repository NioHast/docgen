# Bookmark dan Manifest

Halaman ini menjelaskan bookmark `pNNNN` dan manifest Adeu. Kontrak ada di
[contracts/docx-api.md](../contracts/docx-api.md). Alur Adeu lengkap ada di
[../adeu-integration.md](../adeu-integration.md).

Setiap paragraf body mendapat bookmark `pNNNN`, misalnya `p0001`. Bookmark
dipakai Adeu dan `reconcile` untuk mencocokkan paragraf DOCX dengan manifest.
Nama bookmark hanya boleh cocok dengan pola `p` diikuti minimal empat digit.

Manifest menyimpan:

- `version`, `docx`, dan daftar `paragraphs`;
- `id`, `index`, `kind`, `heading_path`;
- `text`, `text_sha256`;
- `protected`, `protected_reason`;
- `source_file`, `source_line` bila source scan aktif.

Manifest ditulis deterministik tanpa timestamp.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [../adeu-integration.md](../adeu-integration.md) untuk source scan dan
  reconcile.
- [../pipeline/overview.md](../pipeline/overview.md#adeu-hook) untuk posisi
  hook di pipeline.
- [../pipeline/outputs.md](../pipeline/outputs.md) untuk lokasi
  `.laporan/manifest.json`.
