# Artefak dan Workspace

Halaman ini menjelaskan artefak antara, workspace build, dan cara output
ditulis. Kontrak CLI ada di [contracts/cli.md](../../contracts/cli.md).
Artefak pengguna ada di [outputs.md](outputs.md).

## Workspace DOCX

Workspace default adalah `.laporan-build/` di samping `document.md`. Isinya
antara lain Markdown hasil `front_matter`, PNG Mermaid, `reference.docx`
turunan, dan DOCX intermediate untuk target PDF. Tanpa
`--keep-intermediate`, workspace dihapus di blok `finally`, termasuk saat
build gagal.

Untuk target `pdf` tanpa DOCX final, DOCX intermediate ditulis di workspace
dan tidak pernah disalin ke direktori output. Dengan `--keep-intermediate`,
workspace dan DOCX intermediate dipertahankan untuk diperiksa.

## Workspace deck

Workspace deck default adalah `.autooffice-build/<stem>/` di samping
`deck.yaml`. Renderer menulis staging PPTX dan aset Mermaid di sana. Cache
Mermaid persisten berada di `.autooffice/cache/`, sedangkan state dan review
berada di `.autooffice/state/` dan `.autooffice/review/`.

Dengan `--keep-intermediate`, staging `slides` dan PPTX intermediate untuk
target PDF dipertahankan kecuali memang dipublikasikan sebagai output final.

## Penulisan atomic

Penulisan output memakai file sementara di direktori tujuan dan `os.replace`.
DOCX/PPTX intermediate hanya berada di workspace dan tidak pernah ditulis ke
direktori output sebagai deliverable.

## Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc manual`, `Mermaid CLI`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [outputs.md](outputs.md) untuk daftar artefak pengguna.
- [options.md](options.md) untuk `--keep-intermediate`.
- [stages.md](stages.md) untuk stage yang memakai workspace.
- [../docx/package.md](../docx/package.md) untuk aturan byte part.
