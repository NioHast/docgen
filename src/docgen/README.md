# Paket `docgen`

## Tujuan

`src/docgen/` adalah paket Python yang mengubah satu `document.md` menjadi
DOCX dan, di Windows dengan Microsoft Word, PDF. Folder ini memuat CLI,
loader konfigurasi dan dokumen, orkestrasi pipeline, stage, API DOCX, fitur
Adeu, serta data paket. Semua kode runtime berada di sini; contoh dan alat
pengembang tidak boleh menjadi dependensi runtime.

## Ownership

- Perubahan API publik, urutan stage, dan struktur folder harus mengikuti
  [rencana refactor](../../docs/dev/archive/refactor-plan.md) dan kontrak di
  `docs/dev/contracts/`.
- `pipeline.py` dan `cli.py` dimiliki pemilik orkestrasi. Folder `docx/`,
  `stages/`, `markdown/`, `adeu/`, dan `data/` memiliki README serta kontrak
  sendiri; jangan mengubah area itu tanpa koordinasi dengan pemiliknya.
- Sumber kebenaran: [arsitektur](../../docs/dev/architecture.md) untuk batas
  lapisan, [kontrak stage](../../docs/dev/contracts/stage-api.md) untuk
  pipeline dan stage, [kontrak config](../../docs/dev/contracts/config.md)
  untuk data, dan [kontrak DOCX](../../docs/dev/contracts/docx-api.md) untuk
  package DOCX. README ini hanya ringkasan.
- API publik subpackage harus diekspor dari `__init__.py` yang sesuai; root
  `__init__.py` hanya memuat versi. Jangan menambah alias tanpa pemakaian.

## API publik dan entry point

- CLI: `docgen.cli.main` (entry point `docgen`) dan `python -m docgen`.
- Perintah: `docgen check`, `docgen build`, `docgen doctor`, dan
  `docgen reconcile`.
- Pipeline: `pipeline.Pipeline`, `BuildOptions`, `StageContext`,
  `BuildResult`, `StageName`, dan `CANONICAL_ORDER`.
- Loader: `document.load_project`, `document.parse_document`,
  `config.load_format`, `config.load_structure`, `metadata.normalize_metadata`,
  dan `assets.resolve_assets`.
- Path dan error: `paths.package_root`, `paths.data_root`,
  `paths.output_directory`, `paths.safe_relative_path`, serta
  `errors.DocgenError` dan subclass-nya.
- Subpackage: [docx](docx/README.md), [stages](stages/README.md),
  [markdown](markdown/README.md), [adeu](adeu/README.md), dan
  [data](data/README.md).

## Larangan

- Jangan menaruh logika transformasi stage di `pipeline.py`, atau logika
  orkestrasi di modul stage. Urutan stage hanya di `pipeline.py`.
- Jangan memakai `zipfile`, `python-docx`, atau parser XML langsung di stage;
  semua akses DOCX melewati `docx/`.
- Jangan menambah fallback diam-diam, jalur kedua, alias mati, atau workaround.
  Satu input harus menghasilkan satu perilaku yang dapat diprediksi.
- Jangan menyimpan teks naskah, nilai format, atau data struktur di modul
  Python. Nilai tersebut milik `data/`.
- Jangan mengimpor `tools/` atau `tests/` dari kode runtime.
- Jangan menambah dependency tanpa memperbarui `pyproject.toml` dan lock yang
  berlaku.

## Tautan

- [Rencana refactor](../../docs/dev/archive/refactor-plan.md)
- [Arsitektur](../../docs/dev/architecture.md)
- [Kontrak stage](../../docs/dev/contracts/stage-api.md)
- [Kontrak config](../../docs/dev/contracts/config.md)
- [Kontrak DOCX](../../docs/dev/contracts/docx-api.md)
- [Peta repo](../../docs/dev/repo-map.md)
- [Registry referensi](../../docs/dev/references.md)
- [Dokumentasi developer](../../docs/dev/README.md)
- [Indeks dokumentasi](../../docs/README.md)
