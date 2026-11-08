# AGENTS.md

## Apa repo ini

Repositori ini adalah design system dan pipeline laporan akademik berbasis
Markdown untuk format UNDIP. Naskah ditulis di Markdown, lalu dibangun menjadi
DOCX dan PDF. Sumber kebenaran adalah Markdown, metadata, preset, dan
referensi, bukan DOCX hasil build.

## Pilih struktur

| Kebutuhan | Struktur | Penomoran |
| --- | --- | --- |
| Tesis atau skripsi, lima bab | `thesis` | `BAB_ROMAN` |
| Proposal tesis, empat bab | `proposal` | `ARABIC_DOTTED` |
| Tugas kuliah, tiga bab | `assignment` | `ARABIC_DOTTED` |

Struktur menentukan urutan bab. Format `undip-msi` menentukan preset dan gaya
sitasi.

## Alur kerja

Jalankan dari akar repositori. Pasang sekali dengan `uv tool install .` lalu
pakai `laporan`, atau langsung pakai `python -m laporan` tanpa instalasi.

```bash
python -m laporan list
python -m laporan new assignment --format undip-msi --out tugas
python -m laporan check tugas
python -m laporan build tugas --target docx
python -m laporan doctor
```

Mode satu berkas:

```bash
python -m laporan build-file document.md --target both
```

Dengan `uv tool install .`, ganti `python -m laporan` dengan `laporan`.

## Aturan edit

- Edit hanya konten: `chapters/*.md`, `cover.md`, `metadata.yml`,
  `references.bib`, `gambar/`, atau `document.md` pada mode satu berkas.
- Jangan mengubah `structures/`, `formats/`, `presets/`, `tools/`, `scripts/`,
  `docx.lua`, `reference.docx`, atau tes kecuali tugasnya memang di sana.
- Jangan mengubah kode atau build untuk memperbaiki naskah. Perbaiki Markdown.
- Jangan mengarang sitasi. Tulis `TODO-SITASI: <klaim>`.
- Jangan menebak istilah. Tulis `{{?istilah?}}` sampai diputuskan.
- Jangan memakai em dash.
- Jalankan `check` sebelum `build`. Perbaiki bab yang hilang, bukan
  menghapusnya dari struktur.

## Jangan edit artefak

Artefak build tidak boleh disunting manual: `Laporan.docx`, `Laporan.pdf`,
`build/`, `review/`, `acuan/`, `.laporan-build/`, dan keluaran contoh di
`examples/*/`. Build berikutnya akan menimpa perubahan itu.

## Dokumentasi

- [docs/agent/quickstart.md](docs/agent/quickstart.md)
- [docs/agent/document-format.md](docs/agent/document-format.md)
- [docs/agent/writing-rules.md](docs/agent/writing-rules.md)
- [docs/agent/troubleshooting.md](docs/agent/troubleshooting.md)
- [writing/guide.md](writing/guide.md)

Detail implementasi ada di `docs/dev/`. Jangan menyalin detail itu ke panduan
agent.
