# Artefak dan Workspace

Halaman ini menjelaskan artefak antara, workspace build, dan cara output
ditulis. Kontrak side effect ada di
[contracts/stage-api.md](../contracts/stage-api.md). Artefak pengguna ada di
[outputs.md](outputs.md).

## Workspace

Workspace default adalah `.laporan-build/` di samping `document.md`. Isinya
antara lain Markdown hasil `front_matter`, PNG Mermaid, `reference.docx`
turunan, dan DOCX intermediate untuk target PDF. Tanpa `--keep`, workspace
dihapus di blok `finally`, termasuk saat build gagal.

## Penulisan atomic

Penulisan output memakai file sementara di direktori tujuan dan `os.replace`.
DOCX intermediate hanya berada di workspace dan tidak pernah ditulis ke
direktori output.

## Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc manual`, `Mermaid CLI`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [outputs.md](outputs.md) untuk daftar artefak pengguna.
- [options.md](options.md) untuk `--keep`.
- [stages.md](stages.md) untuk stage yang memakai workspace.
- [../docx/package.md](../docx/package.md) untuk aturan byte part.
