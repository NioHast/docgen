# Format dan Struktur

Format mengatur rupa dokumen. Struktur mengatur urutan bagian, front matter,
penomoran, dan daftar. Keduanya adalah data paket di `src/docgen/data/` dengan
skema tertutup. Kontrak lengkap ada di
[contracts/config.md](contracts/config.md).

## Lokasi

```text
src/docgen/data/
|-- formats/
|   `-- undip-msi/
|       |-- format.yml
|       |-- citation.csl
|       |-- logo.jpg
|       `-- reference.docx
|-- structures/
|   |-- assignment/structure.yml
|   |-- proposal/
|   |   |-- structure.yml
|   |   `-- templates/approval.md
|   `-- thesis/
|       |-- structure.yml
|       `-- templates/
|           |-- approval.md
|           `-- statement.md
`-- glossary/istilah.tsv
```

ID adalah nama direktori. `format` di `format.yml` dan `structure.yml` harus
sama dengan nama direktori.

## `format.yml`

Top-level key:

| Key | Isi |
| --- | --- |
| `format` | ID format. |
| `name`, `description` | Nama dan deskripsi tampilan. |
| `page` | Ukuran, orientasi, margin, jarak header/footer, gutter. |
| `font` | Font body dan monospace. |
| `headings` | Style `heading1`, `heading2`, `heading3`. |
| `toc_heading` | Style judul daftar isi. |
| `captions` | Label, separator, font, dan keep-next caption gambar/tabel. |
| `figures` | Perataan caption/gambar, numbering, spacing. |
| `code` | Font, border, shading, tabel kode, style deteksi. |
| `bibliography_style` | Judul dan format daftar pustaka. |
| `citation` | `csl`, `bibliography`, dan `locale`. |
| `assets` | `logo` dan `reference_docx`. |

Semua dimensi memakai satuan `cm`, `mm`, `in`, `pt`, atau `twip`. Semua warna
memakai enam digit heksadesimal. Key `presets`, `preset`, dan `margin_preset`
tidak dikenal dan menghasilkan error migrasi.

### Format `undip-msi`

Nilai final:

- Halaman A4 portrait, margin atas 4 cm, bawah 3 cm, kiri 4 cm, kanan 3 cm.
- Body Times New Roman 12 pt, spasi 1,5, justify, first line indent 1,25 cm.
- Heading 1 rata tengah, bold, 12 pt. Heading 2 dan 3 bold, 12 pt, indent
  gantung 1,25 cm.
- Caption gambar dan tabel Times New Roman 10 pt, spasi 1,0.
- Kode Courier New 10 pt dalam tabel 1x1 dengan border penuh.
- Sitasi memakai `citation.csl` dan `references.bib`.
- Aset memakai `logo.jpg` dan `reference.docx`.

## `structure.yml`

Top-level key:

| Key | Isi |
| --- | --- |
| `format` | Format default untuk struktur ini. |
| `front_matter` | Daftar berurutan bagian sebelum body. |
| `body` | Daftar bab logis. |
| `back_matter` | Daftar bagian setelah body. |
| `toc` | Boolean wajib. |
| `numbering` | Format nomor Heading 1/2/3. |
| `lists` | Boolean daftar gambar dan tabel. |
| `cover` | Tampilan sampul. |

Key lain adalah error. `front_matter` minimal memuat `cover`. `body` minimal
satu entri.

### `front_matter`

Setiap entri memiliki `id`, `source`, dan `template` bila diperlukan.

| ID | Source | Isi |
| --- | --- | --- |
| `cover` | `generated` | Sampul dari metadata, cover, dan logo. |
| `approval` | `template` | Lembar pengesahan dari `templates/approval.md`. |
| `statement` | `template` | Pernyataan dari `templates/statement.md`. |
| `preface` | `document` | Kata pengantar dari front matter `preface`. |
| `abstract_id` | `document` | Abstrak dari `abstract_id`. |
| `abstract_en` | `document` | Abstract dari `abstract_en`. |
| `toc` | `generated` | Field TOC native. |
| `list_of_tables` | `generated` | Field `TOC \c "Tabel"`. |
| `list_of_figures` | `generated` | Field `TOC \c "Gambar"`. |

Konsistensi wajib:

- `toc: true` berarti `front_matter` memuat `toc`; `toc: false` berarti tidak.
- `lists.tables: true` berarti `front_matter` memuat `list_of_tables`.
- `lists.figures: true` berarti `front_matter` memuat `list_of_figures`.
- `preface`, `abstract_id`, dan `abstract_en` mewajibkan key yang sama di
  `document.md`.

Template hanya boleh memakai placeholder `{{ key }}` yang dikenal. Placeholder
tidak dikenal adalah error.

### `body`

`body` adalah urutan bab logis, bukan path berkas. Setiap entri menghasilkan
tepat satu Heading 1. Judul entri dibandingkan case-insensitive setelah spasi
dirapatkan; tanda baca signifikan.

```yaml
body:
  - {id: pendahuluan, title: "Pendahuluan"}
  - {id: tinjauan-pustaka, title: "Tinjauan Pustaka"}
```

Heading 1 tambahan ditolak, kecuali `# Lampiran` yang dideklarasikan
`back_matter`.

### `back_matter`

| ID | Source | Isi |
| --- | --- | --- |
| `bibliography` | `generated` | Daftar pustaka dari CSL dan `.bib`. |
| `appendices` | `document` | Bagian `# Lampiran` di akhir dokumen. |

Jika `appendices` ada, `document.md` wajib memuat tepat satu `# Lampiran`
setelah bab terakhir. Jika `bibliography` ada, berkas `.bib` wajib ada.

### `numbering`

| Nilai `body` | Heading 1 | Heading 2 | Heading 3 |
| --- | --- | --- | --- |
| `BAB_ROMAN` | `BAB I` + baris baru + judul kapital | `1.1.` + tab + judul | `1.1.1.` + tab + judul |
| `ARABIC_DOTTED` | `1.` + spasi + judul kapital | `1.1.` + tab + judul | `1.1.1.` + tab + judul |

`sub_dot` dan `subsub_dot` mengatur titik akhir nomor subbab. Nomor bab selalu
mengikuti `numbering.body`.

### `lists`

`lists.figures` dan `lists.tables` wajib boolean dan konsisten dengan
`front_matter`. Jika aktif, daftar memakai field `TOC \c` dan caption memakai
field `SEQ`.

### `cover`

| Key | Default | Isi |
| --- | --- | --- |
| `show_lecturer` | `true` | Tampilkan dosen di sampul. |
| `logo_width` | `4.88cm` | Lebar logo; hanya dipakai jika `assets.logo` ada. |
| `title_split` | `true` | Pecah judul menjadi baris seimbang. |

`cover` hanya berada di `structure.yml`, bukan `format.yml`.

## Struktur yang tersedia

### `assignment`

- Front matter: `cover`.
- Body: Pendahuluan, Pembahasan, Penutup.
- Back matter: bibliography.
- `toc: false`, `lists` tabel/gambar: false.
- Numbering: `ARABIC_DOTTED`.
- Cover: dosen tidak tampil, logo 4,7 cm.

### `proposal`

- Front matter: cover, approval, toc.
- Body: Pendahuluan, Tinjauan Pustaka, Metode Penelitian, Jadwal Penelitian.
- Back matter: bibliography.
- `toc: true`, `lists` tabel/gambar: false.
- Numbering: `ARABIC_DOTTED`.
- Cover: dosen tidak tampil, logo 4,7 cm.

### `thesis`

- Front matter: cover, approval, statement, preface, abstract_id, abstract_en,
  toc, list_of_tables, list_of_figures.
- Body: Pendahuluan, Tinjauan Pustaka, Metodologi, Hasil dan Pembahasan,
  Penutup.
- Back matter: bibliography, appendices.
- `toc: true`, `lists` tabel/gambar: true.
- Numbering: `BAB_ROMAN`.
- Cover: dosen tampil, logo 4,88 cm.

## Front matter `document.md`

Kunci wajib: `title`, `author`, `structure`, `format`. Kunci opsional mencakup
identitas, abstrak, kata pengantar, kata kunci, `bibliography`, `report_name`,
dan `lang`. Daftar lengkap ada di
[contracts/config.md](contracts/config.md) bagian 4 dan di
[docs/agent/document-format.md](../agent/document-format.md).

Kunci lama seperti `preset`, `daftar_gambar`, `daftar_tabel`, `approval`,
`statement`, `references`, `csl`, `reference-doc`, `template`, dan `cover`
ditolak dengan pesan migrasi. `toc` diterima hanya bila nilainya sama dengan
`structure.toc`, tetapi menghasilkan peringatan.

## Validasi

`load_project` memvalidasi:

- front matter dan tipe YAML;
- keberadaan format dan struktur;
- template yang dirujuk;
- aset gambar, bibliografi, dan glosarium;
- urutan Heading 1 terhadap `body`;
- lampiran terhadap `back_matter`;
- caption Markdown.

Error menyebut path dan key. `check` mengembalikan exit code 1 untuk semua
error konfigurasi.
