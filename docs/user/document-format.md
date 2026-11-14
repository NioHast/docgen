# Format Dokumen

Sumber naskah adalah satu `document.md` berisi YAML front matter dan body
Markdown. Aturan visual tidak ditulis di naskah. Format dan struktur membacanya
dari `src/autooffice/docx/data/`.

## Daftar isi

- [Front matter](#front-matter)
- [Heading](#heading)
- [Caption tabel](#caption-tabel)
- [Caption gambar](#caption-gambar)
- [Mermaid](#mermaid)
- [Blok kode](#blok-kode)
- [Daftar](#daftar)
- [Persamaan](#persamaan)
- [Sitasi dan daftar pustaka](#sitasi-dan-daftar-pustaka)
- [Lampiran](#lampiran)
- [Aturan singkat](#aturan-singkat)

## Front matter

Front matter wajib berada di baris pertama, dibuka dan ditutup `---`. Isinya
harus pemetaan YAML. Duplikat kunci, alias, anchor, dan tag kustom ditolak.

```yaml
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
subtitle: "Laporan Dokumentasi Pipeline"
author:
  - name: "Nama Mahasiswa 1"
    nim: "30000000000001"
  - name: "Nama Mahasiswa 2"
    nim: "30000000000002"
lecturer: "Dr. Nama Dosen Pengampu, M.Kom."
lecturer_label: "Dosen Pengampu:"
course: "Penulisan Laporan Akademik"
institution: "Universitas Diponegoro"
faculty: "Program Studi Magister Sistem Informasi"
year: "2026"
date: "Agustus 2026"
lang: "id-ID"
structure: assignment
format: undip-msi
bibliography: references.bib
report_name: "Tugas"
---
```

### Kunci wajib

| Kunci | Tipe | Keterangan |
| --- | --- | --- |
| `title` | teks | Tidak kosong. |
| `author` | teks, mapping, atau daftar | Minimal satu; setiap entri punya `name`. |
| `report_name` | teks | Tidak kosong; nama berkas output tanpa ekstensi. |
| `structure` | ID | `assignment`, `proposal`, atau `thesis`. |
| `format` | ID | Saat ini hanya `undip-msi`. |

### Kunci opsional

| Kunci | Tipe | Default | Keterangan |
| --- | --- | --- | --- |
| `nim` | teks | - | Hanya untuk satu author dan tidak boleh bertentangan dengan `author[].nim`. |
| `subtitle` | teks | - | Subjudul sampul. |
| `lecturer` | teks | - | Nama dosen. |
| `lecturer_label` | teks | `Dosen Pengampu:` | Label dosen. |
| `course` | teks | - | Nama mata kuliah. |
| `institution` | teks | - | Institusi. |
| `faculty` | teks | - | Fakultas atau program studi. |
| `year` | teks | - | Tahun. |
| `date` | teks | - | Bulan atau tanggal. |
| `lang` | BCP-47 | `id-ID` | Locale sitasi. |
| `bibliography` | path relatif | `references.bib` | Harus berekstensi `.bib` dan ada. |
| `preface` | Markdown | - | Wajib untuk struktur `thesis`. |
| `abstract_id` | Markdown | - | Wajib untuk struktur `thesis`. |
| `abstract_en` | Markdown | - | Wajib untuk struktur `thesis`. |
| `keywords` | daftar atau teks | - | Hanya boleh jika `abstract_id` ada. |
| `keywords_en` | daftar atau teks | - | Hanya boleh jika `abstract_en` ada. |

`report_name` wajib dan tidak memiliki nilai default. Nilai kosong atau hanya
whitespace ditolak dengan `CFG-REQUIRED`. DOCX dan PDF memakai stem yang sama;
tidak ada flag CLI `--report-name`, jadi ubah nilainya di front matter.

`author` menerima tiga bentuk:

```yaml
author: "Nama Tunggal"
```

```yaml
author:
  name: "Nama Tunggal"
  nim: "30000000000001"
```

```yaml
author:
  - name: "Nama 1"
    nim: "30000000000001"
  - name: "Nama 2"
    nim: "30000000000002"
```

Jangan menambahkan `daftar_gambar`, `daftar_tabel`, `preset`, `margin_preset`,
`approval`, `statement`, `references`, `csl`, `reference-doc`, `template`, atau
`cover` ke front matter. Kunci itu sudah dihapus dan menghasilkan error
migrasi. Kunci `toc` di front matter juga ditolak sebagai kunci tidak dikenal
(`CFG-UNKNOWN-KEY`); daftar isi dikendalikan oleh `toc` di `structure.yml`,
bukan oleh naskah.

## Heading

- `#` adalah Heading 1 dan menandai satu bab.
- `##` adalah Heading 2 dan `###` adalah Heading 3.
- Heading 1 harus sama dengan urutan `body` pada struktur, tanpa nomor.
- Jangan menulis `# BAB I` atau `# 1. Pendahuluan`; pipeline menambahkan nomor.
- Heading 2 dan Heading 3 tidak boleh melompati level.

```markdown
# Pendahuluan

## Latar Belakang

## Rumusan Masalah
```

## Caption tabel

Setiap tabel wajib memiliki caption berupa baris `: Judul tabel` sebelum atau
sesudah tabel. Pipeline memindahkan caption tabel ke atas tabel.

```markdown
: Peran berkas dalam struktur assignment

| Urutan | Berkas | Peran |
| --- | --- | --- |
| 1 | `document.md` | Naskah |
| 2 | `references.bib` | Bibliografi |
```

Jangan menulis nomor tabel manual. Nomor `Tabel bab.n` dibuat dari Heading 1
dan urutan tabel.

## Caption gambar

Alt text gambar menjadi caption. Alt text wajib non-kosong dan caption
ditempatkan di bawah gambar.

```markdown
![Diagram alur build](gambar/diagram.png)
```

Aturan gambar:

- letakkan gambar di `gambar/` relatif terhadap `document.md`;
- gunakan pemisah `/`, bukan `\`;
- path absolut, `..`, URL, dan data URI ditolak;
- berkas harus ada saat `check`;
- lebar gambar dibatasi 14 cm secara otomatis;
- jangan menulis nomor gambar manual.

## Mermaid

Diagram Mermaid ditulis sebagai code fence dengan `caption` wajib. Stage
`mermaid` menggantinya menjadi PNG sebelum Pandoc berjalan.

````markdown
```{.mermaid caption="Diagram pipeline"}
flowchart LR
  A[document.md] --> B[DOCX]
```
````

Gambar hasil render ditulis ke `gambar/mermaid-<hash>.png`. Rincian ada di
[mermaid.md](mermaid.md).

## Blok kode

Blok kode berpagar menjadi tabel 1x1 dengan border penuh. Gunakan bahasa
pemrograman pada pembuka fence bila perlu.

````markdown
```python
print("contoh")
```
````

Jangan memakai tabel Markdown untuk kode. Stage `code` mengenali blok kode dari
style Pandoc.

## Daftar

Daftar berurut dan tidak berurut memakai sintaks Markdown biasa. Pipeline
menyeragamkan indentasi dan tab stop, tetapi tidak mengubah format angka yang
dipilih Pandoc. Jangan menulis nomor daftar manual di dalam teks paragraf.

```markdown
1. Langkah pertama.
2. Langkah kedua.

- Butir pertama.
- Butir kedua.
```

## Persamaan

Persamaan display ditulis dengan LaTeX. Pandoc mengubahnya menjadi OMML, lalu
stage `equations` memberi nomor `(bab.n)`.

```markdown
$$
P = \frac{N_{\text{sama}}}{N_{\text{total}}} \times 100\%
$$
```

Jangan menulis nomor persamaan manual.

## Sitasi dan daftar pustaka

Sitasi memakai kunci BibTeX dari `references.bib`:

```markdown
Satu sumber [@pandoc2024]. Beberapa sumber [@pandoc2024; @knuth1984].
```

- Daftar pustaka dibentuk otomatis oleh `--citeproc`.
- Jangan menulis daftar pustaka manual.
- Jangan mengarang penulis, tahun, jurnal, atau DOI.
- Bila sumber belum tersedia, tulis `TODO-SITASI: <klaim>` lalu lengkapi
  `references.bib`.
- Gaya sitasi mengikuti `citation.csl` pada format `undip-msi`.

## Lampiran

Struktur `thesis` memiliki lampiran. Tulis tepat satu Heading 1 `# Lampiran`
setelah bab terakhir. Struktur `assignment` dan `proposal` tidak memiliki
lampiran; Heading 1 `# Lampiran` ditolak.

```markdown
# Lampiran

## Berkas Pendukung

- `gambar/arsitektur.png`
```

## Aturan singkat

- Tabel tanpa caption dan gambar tanpa alt text menggagalkan `check`.
- Jangan menulis nomor bab, tabel, gambar, atau persamaan.
- Jangan menyisipkan field Word manual.
- Jangan memakai em dash.
- Gunakan path relatif dan nama berkas yang stabil.
