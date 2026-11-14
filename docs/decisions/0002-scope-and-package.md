# ADR 0002: Scope dan Package

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L01, L02, L03, L13, L16, L20
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 1, 2.1, 3, 10, 16, dan 16.4

## Konteks

Repo saat ini terdiri dari `docgen` (Python, pipeline DOCX) dan
`deck-studio` (Node, model deck JSON, renderer HTML/Reveal dan PptxGenJS).
Keduanya memiliki model data, bahasa, CLI, dependency, dan quality gate yang
berbeda. Duplikasi kontrak dan dua cara berpikir tentang konten lebih mahal
daripada jumlah kode. Plan menetapkan satu proyek, satu package, satu CLI,
dan penghapusan total nama lama.

## Keputusan

1. AutoOffice adalah satu proyek dengan satu package Python importable,
   `autooffice`, dan satu entry point CLI, `autooffice`.
2. `docgen` dan `deck-studio` dihapus total. Tidak ada alias, shim, package
   kompatibilitas, entry point lama, submodule, atau dead code.
3. Python 3.15 menjadi baseline. Target pertama dan satu-satunya untuk v1
   adalah Windows. Dependency dibagi menjadi core, extra `google`, dan extra
   `dev`.
4. Permukaan CLI hanya `autooffice build`, `autooffice check`,
   `autooffice doctor`, `--version`, dan `--help`. Matriks target mengikuti
   bagian 10.2: `.md` mendukung `docx`, `pdf`, `all`; `.yaml` mendukung
   `pptx`, `pdf`, `slides`, `all`. Nilai lama `both` diganti `all`.
5. Runtime final tidak memuat HTML, Reveal.js, web preview, `package.json`,
   `node_modules`, PptxGenJS, atau renderer browser. Node hanya boleh dipakai
   sebagai external tool `mmdc`.
6. Non-goals v1: XLSX, absolute positioning di authoring, template `.pptx`
   eksternal, object animation, slide transition, dan kompatibilitas CLI lama.
7. Repo GitHub di-rename menjadi `autooffice` pada fase akhir. Rename
   dilakukan setelah semua lane selesai, gate final lulus, dan tidak ada
   branch aktif yang menyentuh file yang dihapus.
8. Tidak ada GitHub Actions. Gate dijalankan lokal.

## Konsekuensi

- `pyproject.toml`, wheel metadata, lock file, dan docs hanya menyebut
  `autooffice`. `docgen` tetap ada sementara sampai parity F1-DOCX lulus.
- `import autooffice` dan `autooffice --help` menjadi acceptance F0.
- Semua perintah dan path lama dihapus dari docs user. Plan migrasi tetap
  boleh menyebut nama lama sebagai dokumen historis sesuai A24.
- Flag lama `--no-manifest`, `--no-adeu`, `--allow-missing-word`, dan `both`
  tidak dipertahankan. `--keep` menjadi `--keep-intermediate`.
- Repo rename adalah langkah terakhir; remote, cache, dan clean clone diuji
  ulang setelah rename.
- Tidak ada merge yang mengandalkan CI.

## Alternatif yang ditolak

- Mempertahankan dua repo dan berbagi kontrak. Ditolak karena tetap ada dua
  pipeline, dua CLI, dan dua quality gate.
- Menyediakan alias `docgen` atau package shim. Ditolak oleh L02 dan
  no-dead-code.
- Mempertahankan Node/PptxGenJS sebagai renderer utama. Ditolak karena target
  satu pipeline Python dan font embedding.
- Mendukung Linux atau macOS untuk PDF dan Google Slides. Ditolak karena v1
  Windows-only dan Word/PowerPoint COM.
- Mempertahankan GitHub Actions. Ditolak karena gate final lokal dan tidak
  ada CI.

## Status

Diterima. Perubahan scope, nama package, entry point, atau target matrix
memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
