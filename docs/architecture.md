# Arsitektur Modular Laporan

Dokumen ini menjelaskan fondasi empat lapis yang membungkus pipeline lama.
Fondasi ini tidak menggantikan `build-docx.sh`, `build.sh`, `docx.lua`, atau
`tools/`; ia hanya menyediakan cara memilih format, memilih struktur, membuat
konten, dan memvalidasi kontrak sebelum build dijalankan.

## Empat lapis

| Lapis | Lokasi | Tanggung jawab | Tidak boleh berisi |
| --- | --- | --- | --- |
| Format | `formats/<nama>/format.yml` | Rupa dokumen, preset lama, CSL, nama tampilan | Teks bab, urutan bab |
| Struktur | `structures/<nama>.yml` | Urutan bagian, penomoran, front/back matter | Teks naskah, margin/font |
| Konten | proyek hasil `new`, `content/examples/` | Metadata, bab Markdown, gambar, `references.bib` | Logika build, salinan preset |
| Platform | `src/laporan/`, `laporan.py` | Deteksi OS/shell, CLI, pembacaan YAML, pemanggilan build | Format visual, isi laporan |

### 1. Format

`formats/undip-msi/format.yml` memetakan struktur ke preset lama:

```yaml
format: undip-msi
name: "Universitas Diponegoro - Magister Sistem Informasi"
csl: "refs/undip-msi.csl"
bibliography: "references.bib"
presets:
  default: "undip-skripsi"
  thesis: "undip-skripsi"
  proposal: "undip-msi-proposal"
  assignment: "undip-msi-proposal"
```

Pipeline lama tetap membaca kunci `preset:` dari `metadata.yml`. Karena itu
`new` menulis preset hasil pemetaan ke metadata proyek. Format baru cukup
menambah direktori `formats/<nama>/format.yml`; tidak perlu mengubah CLI.

### 2. Struktur

Struktur hanya mengatur urutan dan penomoran. Contoh `structures/assignment.yml`:

```yaml
structure: assignment
format: undip-msi
front_matter: [cover]
body_numbering: ARABIC_DOTTED
chapters: [chapters/01-pendahuluan.md, chapters/02-pembahasan.md, chapters/03-penutup.md]
back_matter: [bibliography]
toc: false
blank_line: before_heading_only
```

`thesis` memakai `BAB_ROMAN`, front matter lengkap, lima bab, dan `toc: true`.
`proposal` memakai `ARABIC_DOTTED`, empat bab, dan `toc: true`. Nama berkas bab
di struktur adalah path relatif terhadap akar proyek konten.

### 3. Konten

Proyek konten adalah direktori mandiri:

```text
tugas/
|-- manifest.yml
|-- metadata.yml
|-- cover.md
|-- chapters/
|   |-- 01-pendahuluan.md
|   |-- 02-pembahasan.md
|   `-- 03-penutup.md
|-- references.bib
`-- gambar/
```

`manifest.yml` menunjuk lapis lain dan mencatat daftar bab proyek:

```yaml
manifest: 1
structure: assignment
format: undip-msi
metadata: metadata.yml
report_name: "Tugas"
chapters:
  - chapters/01-pendahuluan.md
  - chapters/02-pembahasan.md
  - chapters/03-penutup.md
```

Bila kunci `chapters` tidak ada, daftar bab diambil dari struktur. Bila ada,
daftar tersebut menjadi snapshot proyek; `check` memastikan setiap berkasnya
ada dan memperingatkan berkas `*.md` tambahan di direktori bab.

`metadata.yml` tetap memakai skema Pandoc/pipeline lama (judul, penulis,
institusi, `preset`, `lang`). `cover.md` disediakan agar build tidak memakai
sampul/kata pengantar proyek lain. Contoh lengkap ada di
`content/examples/assignment/`.

### 4. Platform

`src/laporan/` berisi:

| Modul | Isi |
| --- | --- |
| `manifest.py` | Pembaca YAML (PyYAML atau fallback subset), model struktur/format, validasi, dan pembuatan proyek. |
| `platform.py` | Deteksi Windows/Linux, pencarian Git Bash di Windows, serta Pandoc, Typst, Word, dan LibreOffice native. |
| `cli.py` | Perintah `list`, `new`, `check`, `build`, `doctor`. |
| `__main__.py` | Titik masuk bila `src/` berada di `sys.path`. |

`laporan.py` di akar repo adalah shim tipis agar `python -m laporan` langsung
berjalan tanpa langkah instalasi. Ia menambahkan `src/` ke `sys.path`, lalu
mendelegasikan ke `laporan.cli:main`.

## Alur perintah

```text
list   -> baca structures/*.yml dan formats/*/format.yml
new    -> muat struktur + format -> tulis manifest, metadata, cover, bab, bib, gambar
check  -> muat manifest -> cek struktur, format, metadata, dan tiap berkas bab
build  -> check -> set environment -> panggil build-docx.sh / build.sh
doctor -> deteksi Python, bash, Pandoc, Typst, Word/LibreOffice
```

### Kontrak build

`build` tidak menyalin logika pipeline. Ia menjalankan skrip lama dari akar
repo dengan environment berikut:

```text
LAPORAN_METADATA=<absolute path metadata.yml>
LAPORAN_CHAPTERS=<absolute path direktori chapters>
LAPORAN_REPORT_NAME=<nama keluaran dari manifest>
```

Path dikonversi ke bentuk POSIX (`C:/...`) agar dapat dibaca Git Bash di
Windows maupun bash Debian. Skrip dijalankan dari akar repo dengan direktori
konten sebagai argumen keluaran (`build-docx.sh <konten>`), sehingga aset
konten (`references.bib`, `cover.md`, `gambar/`) dipakai lebih dulu dan aset
wajib repo (`reference.docx`, `docx.lua`, `presets/`, `scripts/`, `tools/`,
`logo.jpg`) tetap ditemukan lewat fallback pipeline lama. Keluaran ditulis ke
direktori konten dengan nama `<LAPORAN_REPORT_NAME>.docx` atau `.pdf`.

Satu pengecualian: `build-docx.sh` mencari `writing/istilah.tsv` relatif
terhadap OUTDIR tanpa fallback. Bila proyek konten belum memilikinya, `build`
menyalin `writing/istilah.tsv` dari akar repo ke `<konten>/writing/` sebelum
menjalankan DOCX. Ini penyediaan aset, bukan duplikasi logika build.

Target `--target docx` memakai `build-docx.sh`; `--target pdf` memakai
`build.sh`; `--target both` menjalankan keduanya berurutan. `--dry-run`
menampilkan environment dan perintah tanpa menjalankan build.

## Batas dan gap integrasi

Kontrak `toc` sudah diterapkan: `docx.lua` dan `template.typ` mengikuti
metadata `toc` (default true untuk proyek lama), `new` menuliskannya ke
`metadata.yml`, dan `build` meneruskannya lewat `LAPORAN_TOC`.

Gap yang masih terbuka:

1. **Front matter terstruktur belum dirender.** `approval`, `statement`,
   `abstract_id`, dan `abstract_en` baru berupa daftar di struktur. Pipeline
   lama membangun komponen ini dari metadata dan `cover.md`, bukan dari
   `front_matter`.
2. **`body_numbering` belum diteruskan sebagai metadata.** Penomoran tetap
   mengikuti preset (`undip-skripsi` untuk `BAB_ROMAN`,
   `undip-msi-proposal` untuk `ARABIC_DOTTED`). Struktur dan preset harus
   dijaga konsisten.
3. **`blank_line` belum ditegakkan.** Nilai disimpan dan divalidasi sebagai
   teks, tetapi belum ada linter yang menolak baris kosong di posisi terlarang.
4. **Glosarium DOCX disediakan saat build.** `build-docx.sh` tidak memakai
   fallback untuk `writing/istilah.tsv`. `build` menyalin glosarium repo ke
   proyek konten bila belum ada. Bila glosarium repo juga tidak ada, DOCX gagal
   dengan pesan dari pipeline lama.
5. **Format baru belum tentu punya preset lama.** `format.yml` hanya memetakan
   ke berkas di `presets/`. Format kampus baru memerlukan preset dan CSL yang
   sesuai agar build dapat berjalan. Kunci `csl`/`bibliography` di `format.yml`
   belum diteruskan ke pipeline; build tetap membaca `csl:` dari preset atau
   memakai `refs/undip-msi.csl`.
6. **Urutan bab mengikuti nama berkas, bukan daftar manifest.** Pipeline lama
   menyalin semua `*.md` di `LAPORAN_CHAPTERS` lalu mengurutkannya dengan
   `sort -V`. Daftar `chapters` pada manifest/struktur dipakai `check` untuk
   memastikan berkas ada, tetapi berkas tambahan di direktori yang sama tetap
   ikut terbangun. Jaga nama berkas agar urutannya sesuai.
