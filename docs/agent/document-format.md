# Format Dokumen

Dokumen ini menjelaskan format sumber Markdown yang diterima pipeline.
Aturan visual tidak ditulis di naskah; preset dan filter DOCX yang
menerapkannya.

## YAML front matter

Front matter wajib berada di awal berkas dan dibatasi `---`. Kunci minimal
adalah `title` dan `author`.

```yaml
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
structure: assignment
format: undip-msi
toc: false
bibliography: references.bib
---
```

| Kunci | Wajib | Keterangan |
| --- | --- | --- |
| `title` | ya | Judul laporan. |
| `author` | ya | Teks, pemetaan `{name, nim}`, atau daftar keduanya. |
| `nim` | tidak | Dipakai bila `author` berupa teks dan hanya ada satu penulis. |
| `structure` | tidak | Nama struktur di `structures/`; default `assignment`. |
| `format` | tidak | Nama format di `formats/`; default mengikuti struktur. |
| `preset` | tidak | Override preset; default `format.presets[structure]`. |
| `toc` | tidak | Default mengikuti struktur. |
| `bibliography` | tidak | Berkas `.bib` relatif; default `references.bib`. |
| `report_name` | tidak | Nama keluaran tanpa ekstensi; default `Tugas`. |
| `glossary` | tidak | Berkas glosarium relatif; default `writing/istilah.tsv`. |

Kunci lain yang lazim dipakai Pandoc dan `docx.lua` juga diteruskan, misalnya
`subtitle`, `lecturer`, `course`, `institution`, `faculty`, `year`, `date`,
`lang`, `approval`, `abstract_id`, `abstract_en`, `keywords_id`,
`keywords_en`, `daftar_gambar`, `daftar_tabel`, dan override heading. Gunakan
`lang: "id-ID"` agar istilah sitasi mengikuti bahasa Indonesia.

Mode folder memakai `metadata.yml` dan `manifest.yml`, bukan front matter.
Struktur dan format mengikuti manifest; preset dan bibliografi mengikuti
metadata serta format.

## Heading

- `#` (H1) adalah bab. Satu H1 membuka satu bab baru.
- `##` dan `###` adalah subbagian.
- Jangan menulis nomor bab manual seperti `# BAB I` atau `# 1. Pendahuluan`.
  `docx.lua` menambahkan penomoran sesuai struktur dan preset.

```markdown
# Pendahuluan

## Latar Belakang

## Rumusan Masalah
```

## Caption tabel

Setiap tabel wajib memiliki caption. Tulis baris `: Judul tabel` sebelum atau
sesudah tabel; pipeline menempatkan caption tabel di atas tabel.

```markdown
: Peran berkas dalam struktur assignment

| Urutan | Berkas | Peran |
| --- | --- | --- |
| 1 | `chapters/01-pendahuluan.md` | Pendahuluan |
| 2 | `chapters/02-pembahasan.md` | Pembahasan |
```

Jangan menulis nomor tabel manual. Nomor `Tabel bab.n` diberikan
`tools/format_figures.py` dari caption dan Heading 1.

## Caption gambar

Alt text gambar menjadi caption. Alt text harus non-kosong.

```markdown
![Diagram alur build](gambar/diagram.png)
```

Aturan:

- gambar harus berada di `gambar/` relatif terhadap `document.md` atau
  direktori proyek;
- path absolut, `..`, dan gambar di luar `gambar/` ditolak `build-file`;
- caption ditempatkan di bawah gambar;
- lebar gambar dibatasi 14 cm secara otomatis;
- jangan menulis nomor gambar manual.

## Mermaid inline

Diagram Mermaid ditulis sebagai code fence dengan atribut `{.mermaid}` dan
`caption` wajib.

````markdown
```{.mermaid caption="Diagram pipeline"}
flowchart TD
  A --> B
```
````

Renderer mengganti blok itu menjadi gambar Markdown biasa, misalnya
`![Diagram pipeline](gambar/mermaid-<hash>.png)`. Nomor gambar diberikan
pipeline caption dari alt text. Mode satu berkas merender Mermaid otomatis
saat `build-file`; mode folder menjalankan renderer lebih dulu. Rincian opsi
dan cache ada di [mermaid.md](mermaid.md).

## Sitasi dan daftar pustaka

Sitasi memakai kunci BibTeX dari `references.bib`:

```markdown
Satu sumber [@pandoc2024]. Beberapa sumber [@pandoc2024; @knuth1984].
```

- Gaya default adalah author-date alfabetis dari `refs/undip-msi.csl`.
- Jangan mengarang rujukan, penulis, tahun, atau DOI.
- Bila sumber belum tersedia, tulis `TODO-SITASI: <klaim>` dan lengkapi
  `references.bib`.
- Daftar pustaka dibentuk otomatis oleh `--citeproc`; jangan menulis daftar
  pustaka manual.
- Satu klaim cukup satu sitasi utama.

## Aturan singkat

- Tabel tanpa `: Judul` dan gambar tanpa alt text menggagalkan build.
- Jangan menulis nomor bab, tabel, atau gambar manual.
- Jangan menyisipkan HTML atau field Word di Markdown.
- Gunakan path relatif dan huruf kecil untuk nama berkas gambar.
