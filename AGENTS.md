# AGENTS.md

## Invariant

- Sumber kebenaran: `document.md`, `references.bib`, `istilah.tsv`, dan `gambar/`; DOCX dan PDF adalah artefak build.
- Satu dokumen adalah satu `document.md`; tidak ada mode folder atau file bab
  terpisah. Setiap Heading 1 harus cocok dengan urutan `body` pada
  `structure.yml`.
- Jangan menulis nomor bab, tabel, gambar, atau persamaan secara manual.
- Tabel wajib memiliki baris `: Judul tabel`. Gambar wajib memiliki alt text
  non-kosong.
- Jangan mengarang sitasi. Tulis `TODO-SITASI: <klaim>`.
- Jangan menebak istilah. Tulis `{{?istilah?}}` sampai diputuskan.
- Jangan memakai em dash.
- Output ditulis di samping `document.md`. Jangan menyunting output build.

## Permukaan edit

- `document.md`: front matter dan seluruh naskah.
- `references.bib`: entri BibTeX untuk sitasi.
- `istilah.tsv`: glosarium tambahan di samping `document.md`, opsional.
- `gambar/`: gambar dan hasil render Mermaid.

## Perintah

```bash
uv run --project <repo> docgen check document.md
uv run --project <repo> docgen build document.md --target docx
uv run --project <repo> docgen build document.md --target both
uv run --project <repo> docgen doctor
uv run --project <repo> docgen reconcile document.md
```

`--target both` hanya untuk Windows dengan Microsoft Word. Di Debian gunakan
`--target docx`. Tambahkan `--terms` bila ingin gate glosarium aktif.

## Larangan

- Jangan mengubah `src/docgen/data/**`, `src/docgen/**`, `tests/**`,
  `pyproject.toml`, `resources/**`, atau `docs/dev/contracts/**` saat tugasnya
  hanya menulis naskah.
- Jangan mengubah `.laporan/`, `.laporan-build/`, DOCX, atau PDF hasil build.
- Jangan memperbaiki naskah dengan menyunting DOCX. Perbaiki Markdown lalu
  build ulang.

## Dokumentasi

- [docs/agent/quickstart.md](docs/agent/quickstart.md), [docs/agent/document-format.md](docs/agent/document-format.md)
- [docs/agent/single-file.md](docs/agent/single-file.md), [docs/agent/writing-rules.md](docs/agent/writing-rules.md)
- Detail implementasi ada di [docs/dev/architecture.md](docs/dev/architecture.md).
