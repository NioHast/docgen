# Kontrak Konfigurasi (P0.2)

**Status:** beku untuk Fase 0.
**Ruang lingkup:** `format.yml`, `structure.yml`, dan front matter `document.md`.
**Pemilik kontrak:** WS0. **Pemilik implementasi:** WS1 (data dan schema), WS2 (`config.py`, `document.py`).
**Rujukan:** `docs/dev/archive/restructure-plan.md` v0.13, bagian P0.2, 2.3, dan WS1.

Kontrak ini menetapkan satu sumber kebenaran untuk setiap nilai. Tidak ada
nilai visual di `structure.yml`, tidak ada urutan bab di `format.yml`, dan
tidak ada nilai format di front matter `document.md`.

## 1. Prinsip

### 1.1 Tiga lapis

| Lapis | Berkas | Mengatur | Tidak boleh mengatur |
|---|---|---|---|
| Format | `src/docgen/data/formats/<format>/format.yml` | Margin, font, style heading/caption/code, CSL, logo, `reference.docx` | Urutan bab, teks legal, isi abstrak |
| Struktur | `src/docgen/data/structures/<structure>/structure.yml` | Front/back matter, urutan bab, penomoran, TOC, daftar gambar/tabel | Margin, font, isi naskah |
| Dokumen | `document.md` | Judul, penulis, NIM, abstrak, kata pengantar, bab, gambar, `.bib` | Margin, font, urutan bab, template legal |

`format` dan `structure` adalah ID, bukan path. ID wajib cocok dengan nama
direktori data dan memakai pola `[a-z0-9][a-z0-9-]*`.

### 1.2 Empat aturan yang tidak bisa dinegosiasikan

1. **Format wajib ada.** `formats/<format>/format.yml` harus ada, terbaca,
   dan valid sebelum dokumen boleh dibangun.
2. **Struktur wajib ada.** `structures/<structure>/structure.yml` harus ada,
   terbaca, dan valid sebelum dokumen boleh dibangun.
3. **Template wajib ada.** Setiap `front_matter` dengan `source: template`
   harus menunjuk berkas yang benar-benar ada di
   `structures/<structure>/templates/`.
4. **Tidak ada key mati.** Skema bersifat tertutup: key yang tidak dikenal
   ditolak, dan setiap key yang dikenal wajib punya konsumen di kode. Key
   yang hanya disimpan tetapi tidak pernah dibaca adalah bug kontrak dan
   harus dihapus atau diimplementasikan.

### 1.3 Resolusi path

- Path di `format.yml` untuk aset format (`csl`, `logo`,
  `reference_docx`) relatif terhadap direktori format.
- Path di `structure.yml` untuk template relatif terhadap
  `structures/<structure>/templates/`.
- Path di `document.md` (`bibliography`) relatif terhadap direktori
  `document.md`.
- Path wajib relatif, memakai `/`, tidak boleh absolut, tidak boleh memuat
  `..`, dan tidak boleh keluar dari direktori basisnya.
- Path yang tidak ada adalah error, bukan warning.
- Perbandingan path peka huruf besar/kecil secara logis. Di Windows,
  benturan nama berkas yang hanya berbeda kapitalisasi adalah error.

### 1.4 Tipe dan satuan

| Tipe | Format | Contoh |
|---|---|---|
| Dimensi | angka + satuan `cm`, `mm`, `in`, `pt`, `twip` | `4cm`, `720twip` |
| Font size | angka + `pt` | `12pt` |
| Line spacing | angka pengali tanpa satuan | `1.5`, `1.0` |
| Warna | `RRGGBB` heksadesimal | `000000` |
| Boolean | `true` / `false` YAML | `true` |
| Alignment | `left`, `right`, `center`, `justify`, `both` | `justify` |

API DOCX memakai twip untuk panjang dan setengah poin untuk ukuran font.
Konversi satuan dilakukan sekali di `config.py`, bukan di stage.

### 1.5 Urutan presedensi

1. Nilai eksplisit di `document.md` mengalahkan default format hanya untuk
   field yang memang milik dokumen: `bibliography`, `lang`, `report_name`.
   `document.format` juga mengalahkan `structure.format`; `structure.format`
   adalah default dan perbedaan dicatat sebagai warning.
2. `structure.yml` mengalahkan `document.md` untuk urutan, TOC, daftar, dan
   penomoran. Dokumen tidak boleh menimpa nilai tersebut.
3. `format.yml` mengalahkan default bawaan kode untuk semua nilai visual.
4. Default kode hanya berlaku bila key opsional tidak ditulis.

---

## 2. `format.yml`

### 2.1 Lokasi dan identitas

```text
src/docgen/data/formats/undip-msi/format.yml
src/docgen/data/formats/undip-msi/logo.jpg
src/docgen/data/formats/undip-msi/reference.docx
src/docgen/data/formats/undip-msi/citation.csl
```

Key `format` wajib sama dengan nama direktori. Key `presets`, `preset`, dan
`margin_preset` tidak lagi dikenal dan harus menghasilkan error dengan pesan
migrasi.

### 2.2 Contoh lengkap

```yaml
format: undip-msi
name: "Universitas Diponegoro - Magister Sistem Informasi"
description: "Margin 4/3/4/3 cm, Times New Roman 12 pt, spasi 1,5, sitasi author-date UNDIP MSI."

page:
  size: A4
  orientation: portrait
  margins:
    top: 4cm
    bottom: 3cm
    left: 4cm
    right: 3cm
  header_distance: 1.27cm
  footer_distance: 1.27cm
  gutter: 0cm

font:
  body:
    family: "Times New Roman"
    size: 12pt
    color: "000000"
    line_spacing: 1.5
    space_before: 0pt
    space_after: 0pt
    alignment: justify
    first_line_indent: 1.25cm
  monospace:
    family: "Courier New"
    size: 10pt

headings:
  styles:
    heading1:
      font_family: "Times New Roman"
      font_size: 12pt
      bold: true
      color: "000000"
      alignment: center
      space_before: 0pt
      space_after: 0pt
      line_spacing: 1.5
      keep_next: true
      keep_lines: true
      outline_level: 0
      first_line_indent: 0cm
      indent_left: 0cm
      indent_hanging: 0cm
    heading2:
      font_family: "Times New Roman"
      font_size: 12pt
      bold: true
      color: "000000"
      alignment: justify
      space_before: 0pt
      space_after: 0pt
      line_spacing: 1.5
      keep_next: true
      keep_lines: true
      outline_level: 1
      first_line_indent: 0cm
      indent_left: 1.25cm
      indent_hanging: 1.25cm
    heading3:
      font_family: "Times New Roman"
      font_size: 12pt
      bold: true
      color: "000000"
      alignment: justify
      space_before: 0pt
      space_after: 0pt
      line_spacing: 1.5
      keep_next: true
      keep_lines: true
      outline_level: 2
      first_line_indent: 0cm
      indent_left: 1.25cm
      indent_hanging: 1.25cm

captions:
  figure:
    label: "Gambar"
    separator: " "
    font:
      family: "Times New Roman"
      size: 10pt
      bold: false
      italic: false
      color: "000000"
      space_before: 0pt
      space_after: 0pt
      line_spacing: 1.0
  table:
    label: "Tabel"
    separator: " "
    keep_next: true
    font:
      family: "Times New Roman"
      size: 10pt
      bold: false
      italic: false
      color: "000000"
      alignment: left
      space_before: 0pt
      space_after: 0pt
      line_spacing: 1.0

figures:
  caption_alignment: center
  image_alignment: center
  numbering: chapter
  space_before: 0pt
  space_after: 0pt
  first_line_indent: 0cm

code:
  style: SourceCode
  font:
    family: "Courier New"
    size: 10pt
    color: "000000"
  alignment: left
  line_spacing: 1.0
  space_before: 0pt
  space_after: 0pt
  shading: none
  border:
    style: single
    width: 1pt
    color: "000000"
  table:
    width: 100%
    cell_margin: 108twip
  detect_styles:
    - "Source Code"
    - "Verbatim Char"
    - "HTML Code"
    - "HTML Preformatted"

bibliography_style:
  heading: "DAFTAR PUSTAKA"
  font: "Times New Roman"
  size: 12pt
  line_spacing: 1.5
  space_before: 0pt
  space_after: 0pt
  indent_left: 1.27cm
  indent_hanging: 1.27cm

toc_heading:
  heading_style: "TOCHeading"
  font: "Times New Roman"
  size: 12pt
  bold: true
  color: "000000"
  alignment: center
  space_before: 0pt
  space_after: 0pt
  line_spacing: 1.5
  first_line_indent: 0cm

citation:
  csl: "citation.csl"
  bibliography: "references.bib"
  locale: "id-ID"

assets:
  logo: "logo.jpg"
  reference_docx: "reference.docx"
```

### 2.3 `page`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `page.size` | enum `A4`, `Letter` | tidak | `A4` | Ukuran halaman yang didukung Word |
| `page.orientation` | enum `portrait`, `landscape` | tidak | `portrait` | Harus konsisten dengan `size` |
| `page.margins.top` | dimensi | ya | - | > 0 |
| `page.margins.bottom` | dimensi | ya | - | > 0 |
| `page.margins.left` | dimensi | ya | - | > 0 |
| `page.margins.right` | dimensi | ya | - | > 0 |
| `page.header_distance` | dimensi | tidak | `1.27cm` | >= 0 |
| `page.footer_distance` | dimensi | tidak | `1.27cm` | >= 0 |
| `page.gutter` | dimensi | tidak | `0cm` | >= 0 |

Margin wajib ditulis keempatnya. Tidak ada fallback ke margin preset lama.

### 2.4 `font`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `font.body.family` | teks | ya | - | Tidak kosong; font harus tersedia di sistem build |
| `font.body.size` | dimensi `pt` | ya | - | 6-72 pt |
| `font.body.color` | warna | tidak | `000000` | Heksadesimal 6 digit |
| `font.body.line_spacing` | angka | tidak | `1.5` | 0.5-3.0 |
| `font.body.space_before` | dimensi | tidak | `0pt` | >= 0 |
| `font.body.space_after` | dimensi | tidak | `0pt` | >= 0 |
| `font.body.alignment` | enum alignment | tidak | `justify` | `left`, `right`, `center`, `justify`, `both` |
| `font.body.first_line_indent` | dimensi | tidak | `1.25cm` | >= 0 |
| `font.monospace.family` | teks | tidak | `Courier New` | Tidak kosong |
| `font.monospace.size` | dimensi `pt` | tidak | `10pt` | 6-72 pt |

`font.body` menjadi default untuk style `Normal`, `BodyText`, dan
`FirstParagraph`. `font.monospace` menjadi default untuk inline code dan blok
kode yang tidak punya override di `code`.

### 2.5 `headings`

`headings.styles` wajib memuat `heading1`, `heading2`, dan `heading3`. Semua
key di bawah boleh ditulis pada ketiga style; default berbeda per level.

| Key | Tipe | Default H1 | Default H2/H3 | Validasi |
|---|---|---:|---:|---|
| `font_family` | teks | `font.body.family` | `font.body.family` | Tidak kosong |
| `font_size` | dimensi `pt` | `font.body.size` | `font.body.size` | 6-72 pt |
| `bold` | boolean | `true` | `true` | - |
| `color` | warna | `000000` | `000000` | 6 digit |
| `alignment` | enum alignment | `center` | `justify` | Lihat 2.4 |
| `space_before` | dimensi | `0pt` | `0pt` | >= 0 |
| `space_after` | dimensi | `0pt` | `0pt` | >= 0 |
| `line_spacing` | angka | `font.body.line_spacing` | `font.body.line_spacing` | 0.5-3.0 |
| `keep_next` | boolean | `true` | `true` | - |
| `keep_lines` | boolean | `true` | `true` | - |
| `outline_level` | integer | `0` | `1`/`2` | 0-8; harus cocok level |
| `first_line_indent` | dimensi | `0cm` | `0cm` | >= 0 |
| `indent_left` | dimensi | `0cm` | `1.25cm` | >= 0 |
| `indent_hanging` | dimensi | `0cm` | `1.25cm` | >= 0 |

Aturan yang tidak dapat dikonfigurasi:

- Heading 1, 2, dan 3 adalah satu-satunya level yang diklasifikasikan dan
  dinomori.
- Heading 4-9 tidak dinomori, tidak mengubah counter bab, dan tidak memakai
  aturan jarak otomatis. Jika muncul, paragraf dipertahankan sebagai body
  dan stage `sections` mencatat warning.
- Nomor bab, prefix, dan format angka berasal dari `structure.yml`, bukan dari
  `format.yml`.

### 2.6 `captions`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `captions.figure.label` | teks | tidak | `Gambar` | Tidak kosong |
| `captions.figure.separator` | teks | tidak | satu spasi | Tidak boleh memuat newline |
| `captions.figure.font.family` | teks | tidak | `font.body.family` | Tidak kosong |
| `captions.figure.font.size` | dimensi `pt` | tidak | `10pt` | 6-72 pt |
| `captions.figure.font.bold` | boolean | tidak | `false` | - |
| `captions.figure.font.italic` | boolean | tidak | `false` | - |
| `captions.figure.font.color` | warna | tidak | `000000` | 6 digit |
| `captions.figure.font.space_before` | dimensi | tidak | `0pt` | >= 0 |
| `captions.figure.font.space_after` | dimensi | tidak | `0pt` | >= 0 |
| `captions.figure.font.line_spacing` | angka | tidak | `1.0` | 0.5-3.0 |
| `captions.table.label` | teks | tidak | `Tabel` | Tidak kosong |
| `captions.table.separator` | teks | tidak | satu spasi | Tidak boleh memuat newline |
| `captions.table.keep_next` | boolean | tidak | `true` | Harus `true` |
| `captions.table.font.*` | sama dengan gambar | tidak | alignment `left` | Lihat 2.4 |

Perataan caption gambar berasal dari `format.figures.caption_alignment`, bukan
dari `captions.figure.font`. Perataan caption tabel tetap memakai
`captions.table.font.alignment`.

Posisi caption tidak dapat dikonfigurasi:

- Caption tabel selalu **tepat di atas** tabel.
- Caption gambar selalu **tepat di bawah** gambar.
- Caption wajib ada. Tabel tanpa caption atau gambar tanpa alt text
  menghasilkan error sebelum Pandoc.
- Tabel kode bukan tabel data dan tidak boleh diberi caption tabel.

### 2.7 `code`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `code.style` | teks | tidak | `SourceCode` | Style wajib ada di `reference.docx` |
| `code.font.family` | teks | tidak | `font.monospace.family` | Tidak kosong |
| `code.font.size` | dimensi `pt` | tidak | `font.monospace.size` | 6-72 pt |
| `code.font.color` | warna | tidak | `000000` | 6 digit |
| `code.alignment` | enum alignment | tidak | `left` | `left`, `center`, `right`, `justify` |
| `code.line_spacing` | angka | tidak | `1.0` | 0.5-3.0 |
| `code.space_before` | dimensi | tidak | `0pt` | >= 0 |
| `code.space_after` | dimensi | tidak | `0pt` | >= 0 |
| `code.shading` | teks | tidak | `none` | Hanya `none` |
| `code.border.style` | enum | tidak | `single` | Harus `single` |
| `code.border.width` | dimensi | tidak | `1pt` | > 0 |
| `code.border.color` | warna | tidak | `000000` | 6 digit |
| `code.table.width` | persentase | tidak | `100%` | Harus `100%` |
| `code.table.cell_margin` | dimensi | tidak | `108twip` | >= 0 |
| `code.detect_styles` | daftar teks | tidak | lihat contoh | Minimal satu style; tidak duplikat |

Aturan kode:

- Blok kode selalu menjadi tabel 1x1 dengan border penuh.
- Tidak ada border dalam (`insideH`/`insideV`).
- Tidak ada numbering, caption tabel, atau shading.
- Kode inline (`Verbatim Char`) tidak diubah menjadi tabel.
- Nama style dibandingkan tanpa membedakan kapitalisasi, spasi, garis bawah,
  dan tanda hubung.

### 2.8 `citation`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `citation.csl` | path relatif | ya | - | `.csl`, ada, XML valid |
| `citation.bibliography` | path relatif | tidak | `references.bib` | `.bib`; default untuk `document.md` |
| `citation.locale` | BCP-47 | tidak | `id-ID` | Locale valid |

`citation.csl` dan `citation.bibliography` tidak boleh memakai path absolut.
`document.md` boleh menimpa `bibliography`; `csl` hanya boleh berasal dari
format. Judul bagian daftar pustaka berada di
`format.bibliography_style.heading`, bukan di `citation.section_title`.
`citation.bibliography` tetap berupa path `.bib` dan tidak berubah menjadi
gaya.

### 2.9 `assets`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `assets.logo` | path relatif | tidak | `logo.jpg` | Ada; `.jpg`, `.jpeg`, atau `.png`; gambar valid |
| `assets.reference_docx` | path relatif | tidak | `reference.docx` | Ada; ZIP valid; `word/styles.xml` ada |

`logo_width`, `show_lecturer`, dan `title_split` bukan milik `format.yml`.
Ketiganya berada di `structure.cover` (lihat 3.7). Path logo tetap di
`format.assets.logo`; ukuran dan visibilitasnya diatur struktur.

`assets.reference_docx` adalah **source asset**. Stage `style_reference`
hanya membacanya dan menulis derived reference ke workspace/cache. File
source tidak boleh ditimpa.

### 2.10 `toc_heading`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `toc_heading.heading_style` | teks | tidak | `TOCHeading` | Style wajib ada di `reference.docx` |
| `toc_heading.font` | teks | tidak | `font.body.family` | Tidak kosong |
| `toc_heading.size` | dimensi `pt` | tidak | `font.body.size` | 6-72 pt |
| `toc_heading.bold` | boolean | tidak | `true` | - |
| `toc_heading.color` | warna | tidak | `000000` | Heksadesimal 6 digit |
| `toc_heading.alignment` | enum alignment | tidak | `center` | Lihat 2.4 |
| `toc_heading.space_before` | dimensi | tidak | `0pt` | >= 0 |
| `toc_heading.space_after` | dimensi | tidak | `0pt` | >= 0 |
| `toc_heading.line_spacing` | angka | tidak | `font.body.line_spacing` | 0.5-3.0 |
| `toc_heading.first_line_indent` | dimensi | tidak | `0cm` | >= 0 |

`format.toc_heading` hanya mengatur rupa judul daftar isi. Nilai `font`,
`size`, `bold`, `color`, `alignment`, spacing, dan `first_line_indent`
diterapkan ke style `toc_heading.heading_style` (default `TOCHeading`).
Keberadaan daftar isi tetap ditentukan `structure.toc` (boolean) dan entri
`front_matter` `{id: toc}`. `format.toc_heading` tidak boleh dipakai untuk
menyalakan atau mematikan TOC.

### 2.11 `bibliography_style`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `bibliography_style.heading` | teks | tidak | `DAFTAR PUSTAKA` | Tidak kosong |
| `bibliography_style.font` | teks | tidak | `font.body.family` | Tidak kosong |
| `bibliography_style.size` | dimensi `pt` | tidak | `font.body.size` | 6-72 pt |
| `bibliography_style.line_spacing` | angka | tidak | `font.body.line_spacing` | 0.5-3.0 |
| `bibliography_style.space_before` | dimensi | tidak | `0pt` | >= 0 |
| `bibliography_style.space_after` | dimensi | tidak | `0pt` | >= 0 |
| `bibliography_style.indent_left` | dimensi | tidak | `1.27cm` | >= 0 |
| `bibliography_style.indent_hanging` | dimensi | tidak | `1.27cm` | >= 0 |

`bibliography_style.heading` menggantikan key lama `citation.section_title`.
Nilai font/size/line spacing/spacing dan indent kiri/hanging diterapkan ke
style `Bibliography`. `citation.bibliography` tetap path `.bib`;
`bibliography_style` tidak menentukan file bibliografi.

### 2.12 `figures`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `figures.caption_alignment` | enum alignment | tidak | `center` | Lihat 2.4 |
| `figures.image_alignment` | enum alignment | tidak | `center` | Lihat 2.4 |
| `figures.numbering` | enum `chapter`, `document` | tidak | `chapter` | `chapter` reset per Heading1 `BAB ...`; `document` meneruskan counter |
| `figures.space_before` | dimensi | tidak | `0pt` | >= 0 |
| `figures.space_after` | dimensi | tidak | `0pt` | >= 0 |
| `figures.first_line_indent` | dimensi | tidak | `0cm` | >= 0 |

`figures.numbering` mengatur counter caption gambar dan tabel. Perataan
caption gambar memakai `figures.caption_alignment`; perataan caption tabel
tetap memakai `captions.table.font.alignment`. Spacing dan indentasi gambar
memakai `figures.space_before`, `figures.space_after`, dan
`figures.first_line_indent`.

### 2.13 Validasi `format.yml`

- Semua key di luar daftar 2.3-2.12 adalah error `CFG-UNKNOWN-KEY`.
- `format` wajib sama dengan nama direktori; key `id` tidak dikenal.
- `page.margins` wajib lengkap. `page.size`, `page.orientation`,
  `page.header_distance`, `page.footer_distance`, dan `page.gutter` memakai
  default di 2.3.
- `toc_heading.heading_style` wajib ada di `reference.docx`;
  `toc_heading` tidak boleh memuat toggle `toc`.
- `toc_heading.color` wajib heksadesimal 6 digit; `toc_heading.alignment`
  wajib enum alignment; `toc_heading.first_line_indent` wajib >= 0.
- `bibliography_style.heading` tidak boleh kosong; grup ini tidak boleh
  memuat path `.bib`; `indent_left` dan `indent_hanging` wajib >= 0.
- `figures.numbering` hanya `chapter` atau `document`;
  `figures.space_before`, `figures.space_after`, dan
  `figures.first_line_indent` wajib >= 0.
- `code.alignment` hanya enum alignment yang didukung.
- Semua aset wajib ada dan bertipe benar.
- `reference.docx` wajib dapat dibuka sebagai ZIP dan memiliki
  `[Content_Types].xml`, `word/document.xml`, dan `word/styles.xml`.
- `citation.csl` wajib dapat diparse sebagai XML.
- `format.yml` tidak boleh memuat `cover`, `assets.cover`, atau
  `assets.logo_width`; nilai itu milik `structure.cover`.
- Tidak ada fallback ke `presets/` atau `reference.docx` root lama.

---

## 3. `structure.yml`

### 3.1 Lokasi dan identitas

```text
src/docgen/data/structures/thesis/structure.yml
src/docgen/data/structures/thesis/templates/approval.md
src/docgen/data/structures/thesis/templates/statement.md
```

ID struktur adalah nama direktori. Key `structure` dan `chapters` dari skema
lama tidak dikenal di target single-file.

### 3.2 Contoh lengkap

```yaml
format: undip-msi

cover:
  show_lecturer: true
  logo_width: 4.88cm
  title_split: true

front_matter:
  - {id: cover, source: generated}
  - {id: approval, source: template, template: approval.md}
  - {id: statement, source: template, template: statement.md}
  - {id: preface, source: document}
  - {id: abstract_id, source: document}
  - {id: abstract_en, source: document}
  - {id: toc, source: generated}
  - {id: list_of_tables, source: generated}
  - {id: list_of_figures, source: generated}

body:
  - {id: pendahuluan, title: "Pendahuluan"}
  - {id: tinjauan-pustaka, title: "Tinjauan Pustaka"}
  - {id: metodologi, title: "Metodologi"}
  - {id: hasil-dan-pembahasan, title: "Hasil dan Pembahasan"}
  - {id: penutup, title: "Penutup"}

back_matter:
  - {id: bibliography, source: generated}
  - {id: appendices, source: document}

toc: true

numbering:
  body: BAB_ROMAN
  sub_dot: true
  subsub_dot: true

lists:
  figures: true
  tables: true
```

### 3.3 `front_matter`

`front_matter` adalah daftar berurutan. Urutan deklarasi adalah urutan
render. Setiap entri wajib memiliki `id` dan `source`.

```yaml
- {id: approval, source: template, template: approval.md}
- {id: abstract_id, source: document}
- {id: cover, source: generated}
```

| Key | Tipe | Wajib | Validasi |
|---|---|---:|---|
| `id` | enum | ya | Lihat tabel 3.4; unik dalam satu struktur |
| `source` | enum `template`, `document`, `generated` | ya | Lihat tabel 3.4 |
| `template` | path relatif | kondisional | Wajib hanya untuk `source: template`; dilarang untuk source lain |

Aturan `source`:

- `template`: render berkas Markdown di
  `structures/<structure>/templates/<template>`. Berkas wajib ada, berekstensi
  `.md`, dan tidak boleh keluar dari direktori template.
- `document`: ambil isi dari key front matter `document.md` dengan `id` yang
  sama. Key tersebut wajib ada dan tidak boleh kosong.
- `generated`: dibuat oleh stage dari data dokumen/format. Tidak boleh punya
  key `template`.

### 3.4 ID front matter yang didukung

| ID | Source yang diizinkan | Isi |
|---|---|---|
| `cover` | `generated` | Sampul dari title, author, institusi, logo |
| `approval` | `template` | Lembar pengesahan |
| `statement` | `template` | Pernyataan keaslian |
| `preface` | `document` | Kata pengantar dari front matter `preface` |
| `abstract_id` | `document` | Abstrak Indonesia dari `abstract_id` |
| `abstract_en` | `document` | Abstract Inggris dari `abstract_en` |
| `toc` | `generated` | Field TOC native Word |
| `list_of_tables` | `generated` | Field `TOC \c "Tabel"` |
| `list_of_figures` | `generated` | Field `TOC \c "Gambar"` |

ID lain adalah error `CFG-UNKNOWN-FRONT-MATTER`.

Aturan konsistensi:

- `cover` wajib ada.
- `toc` wajib ada jika `toc: true`; wajib tidak ada jika `toc: false`.
- `list_of_tables` wajib ada jika `lists.tables: true`; wajib tidak ada
  jika `lists.tables: false`.
- `list_of_figures` wajib ada jika `lists.figures: true`; wajib tidak ada
  jika `lists.figures: false`.
- `approval` dan `statement` wajib memakai template yang ada.
- `preface`, `abstract_id`, dan `abstract_en` wajib memiliki key yang sesuai
  di `document.md`.

### 3.5 `body`

`body` adalah daftar bab logis, bukan daftar path berkas. Target single-file
tidak memiliki direktori `chapters/`.

```yaml
body:
  - {id: pendahuluan, title: "Pendahuluan"}
```

| Key | Tipe | Wajib | Validasi |
|---|---|---:|---|
| `id` | teks | ya | `[a-z][a-z0-9-]*`; unik |
| `title` | teks | ya | Tidak kosong; unik setelah normalisasi |

Aturan body:

- Minimal satu bab.
- Setiap entri menghasilkan tepat satu Heading 1 di `document.md`.
- Heading 1 ditulis **tanpa nomor** di `document.md`; stage `sections`
  menambahkan nomor sesuai `numbering.body`.
- Heading 1 wajib muncul dalam urutan yang sama dengan daftar `body`.
- Teks Heading 1 dibandingkan case-insensitive setelah spasi dirapatkan.
  Tanda baca dianggap signifikan.
- Heading 1 tambahan yang tidak ada di `body` adalah error, kecuali
  `# Lampiran` yang dipakai `back_matter`.
- Heading 2 dan Heading 3 bebas di dalam setiap bab; strukturnya tidak
  diatur oleh `body`.

### 3.6 `back_matter`

`back_matter` adalah daftar berurutan dengan bentuk entri `{id, source}`.

| ID | Source yang diizinkan | Isi |
|---|---|---|
| `bibliography` | `generated` | Daftar pustaka dari CSL dan `.bib` |
| `appendices` | `document` | Bagian `# Lampiran` di akhir `document.md` |

Aturan:

- `id` unik.
- `source: template` tidak didukung untuk back matter.
- Jika `appendices` ada, `document.md` wajib memiliki tepat satu Heading 1
  `# Lampiran` setelah bab terakhir.
- Jika `bibliography` ada, `document.md` wajib memiliki `bibliography` yang
  dapat dibaca.

### 3.7 `cover`

`cover` adalah mapping opsional. Jika tidak ditulis, ketiga default di bawah
dipakai.

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `cover.show_lecturer` | boolean | tidak | `true` | Harus `true`/`false` |
| `cover.logo_width` | dimensi | tidak | `4.88cm` | > 0; hanya dipakai jika `assets.logo` ada |
| `cover.title_split` | boolean | tidak | `true` | Jika `true`, judul sampul dipecah menjadi baris seimbang; jika `false`, judul ditulis satu blok |

Aturan cover:

- `cover` hanya berada di `structure.yml`; tidak boleh ada di `format.yml`.
- `cover.show_lecturer` mengatur tampil/tidaknya dosen pengampu di sampul.
- `cover.logo_width` mengatur lebar logo sampul; path logo tetap di
  `format.assets.logo`.
- `cover.title_split` mempertahankan perilaku `balance_title` lama saat
  `true`; `false` menonaktifkan pemecahan baris.
- Key lain di dalam `cover` adalah error `CFG-UNKNOWN-KEY`.

### 3.8 `toc`

`toc` adalah boolean wajib.

- `true`: stage `toc` menulis field TOC native di dalam `w:sdt`.
- `false`: tidak ada field TOC.
- Nilai ini tidak boleh ditimpa oleh front matter `document.md`.

### 3.9 `numbering`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `numbering.body` | enum `BAB_ROMAN`, `ARABIC_DOTTED` | ya | - | Lihat tabel di bawah |
| `numbering.sub_dot` | boolean | tidak | `true` | - |
| `numbering.subsub_dot` | boolean | tidak | `true` | - |

| Nilai | Heading 1 | Heading 2 | Heading 3 |
|---|---|---|---|
| `BAB_ROMAN` | `BAB I` + line break + judul kapital | `1.1.` + tab + judul | `1.1.1.` + tab + judul |
| `ARABIC_DOTTED` | `1.` + spasi + judul kapital | `1.1.` + tab + judul | `1.1.1.` + tab + judul |

`sub_dot` dan `subsub_dot` hanya mengatur titik akhir nomor. Nomor bab selalu
memakai format yang ditentukan `numbering.body`.

### 3.10 `lists`

| Key | Tipe | Wajib | Default | Validasi |
|---|---|---:|---|---|
| `lists.figures` | boolean | ya | - | Harus konsisten dengan `front_matter` |
| `lists.tables` | boolean | ya | - | Harus konsisten dengan `front_matter` |

Jika `true`, daftar memakai field `TOC \c "Gambar"` atau `TOC \c "Tabel"`.
Caption sumber memakai `SEQ Gambar` dan `SEQ Tabel`.

### 3.11 Validasi `structure.yml`

- Semua key di luar 3.3-3.10 adalah error `CFG-UNKNOWN-KEY`.
- `format` wajib ada; nilainya menjadi default jika `document.format`
  berbeda. Perbedaan menghasilkan warning `CFG-FORMAT-OVERRIDE`, bukan
  error, selama format yang dipilih ada.
- `front_matter` minimal satu entri dan wajib memuat `cover`.
- `body` minimal satu entri.
- `cover` hanya berisi `show_lecturer`, `logo_width`, dan `title_split`.
- `cover.logo_width` wajib dimensi valid dan > 0.
- `cover.title_split` wajib boolean jika ditulis.
- Semua template wajib ada.
- Semua ID unik.
- Semua kombinasi `id`/`source` sesuai tabel 3.4 dan 3.6.
- `toc` dan `lists` konsisten dengan `front_matter`.
- `numbering.body` harus salah satu enum yang didukung.

---

## 4. Front matter `document.md`

### 4.1 Bentuk berkas

- Berkas UTF-8; BOM di awal diterima dan dibuang.
- Baris pertama wajib `---`.
- Front matter ditutup `---` atau `...`.
- Isi front matter wajib pemetaan YAML, bukan daftar atau skalar.
- Duplikat key YAML adalah error.
- Body Markdown setelah penutup wajib tidak kosong.
- Hanya tipe YAML aman yang diterima: string, number, boolean, list, mapping.
  Tag kustom dan alias jangkar ditolak.

### 4.2 Contoh lengkap

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
structure: thesis
format: undip-msi
bibliography: references.bib
report_name: "Tugas"
abstract_id: |
  Ringkasan penelitian dalam Bahasa Indonesia.
keywords:
  - "pipeline"
  - "DOCX"
abstract_en: |
  Research summary in English.
keywords_en:
  - "pipeline"
  - "DOCX"
preface: |
  Ucapan terima kasih dan pengantar laporan.
---
```

Body setelah front matter:

```markdown
# Pendahuluan

...
```

### 4.3 Field wajib

| Key | Tipe | Validasi |
|---|---|---|
| `title` | teks | Tidak kosong |
| `author` | teks, mapping, atau daftar | Minimal satu; setiap entri punya `name` |
| `structure` | ID | Direktori struktur harus ada |
| `format` | ID | Direktori format harus ada; mengalahkan `structure.format`; perbedaan menghasilkan warning |
| `report_name` | teks | Wajib, tidak kosong; tanpa karakter path; aman untuk nama berkas |

### 4.4 Field opsional

| Key | Tipe | Default | Validasi |
|---|---|---|---|
| `nim` | teks | - | Hanya boleh untuk satu author; tidak boleh bertentangan dengan `author[].nim` |
| `subtitle` | teks | - | - |
| `lecturer` | teks | - | - |
| `lecturer_label` | teks | `Dosen Pengampu:` | - |
| `course` | teks | - | - |
| `institution` | teks | - | - |
| `faculty` | teks | - | - |
| `year` | teks | - | - |
| `date` | teks | - | - |
| `lang` | BCP-47 | `id-ID` | Locale valid |
| `bibliography` | path relatif | `format.citation.bibliography` | `.bib`, ada, tidak keluar dari direktori dokumen |
| `preface` | teks Markdown | - | Wajib jika struktur mendeklarasikan `preface` |
| `abstract_id` | teks Markdown | - | Wajib jika struktur mendeklarasikan `abstract_id` |
| `abstract_en` | teks Markdown | - | Wajib jika struktur mendeklarasikan `abstract_en` |
| `keywords` | daftar teks atau teks | - | Hanya boleh jika `abstract_id` ada |
| `keywords_en` | daftar teks atau teks | - | Hanya boleh jika `abstract_en` ada |

`keywords` dan `keywords_en` berupa string diterima sebagai **satu** kata
kunci, bukan dipecah per karakter. Bentuk daftar lebih disarankan.

Nilai multiline `abstract_id`, `abstract_en`, dan `preface` dipertahankan
sebagai Markdown. Baris kosong di dalam nilai menjadi paragraf baru; stage
`sections` tidak boleh meruntuhkan seluruh abstrak menjadi satu paragraf.

### 4.5 Skema `author`

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

Aturan:

- `name` wajib, tidak kosong.
- `nim` opsional, tidak kosong jika ada.
- Key lain di dalam author adalah error.
- `author` berupa string adalah shorthand untuk `{name: <string>}`.
- `nim` tingkat atas hanya boleh dipakai jika tepat satu author.
- Jika `author` lebih dari satu, setiap NIM harus ditulis di entri
  masing-masing.

### 4.6 Field lama ditolak

Field berikut bukan bagian dari kontrak target. Skema front matter bersifat
tertutup, sehingga semuanya menghasilkan error `CFG-UNKNOWN-KEY`. Dokumen baru
tidak boleh menulis field ini.

| Field lama | Alasan | Pengganti |
|---|---|---|
| `preset` | Format sudah menjadi `format.yml` | `format` |
| `margin_preset` | Format sudah menjadi `format.yml` | `format` |
| `toc` | Daftar isi milik struktur | `structure.yml` `toc` |
| `daftar_gambar` | Daftar milik struktur | `structure.yml` `lists.figures` |
| `daftar_tabel` | Daftar milik struktur | `structure.yml` `lists.tables` |
| `keywords_id` | Nama tidak konsisten | `keywords` |
| `approval` | Teks legal milik struktur | Template `approval.md` |
| `statement` | Teks legal milik struktur | Template `statement.md` |
| `references` | Bibliografi embedded tidak didukung | `bibliography` |
| `csl` | CSL milik format | `format.yml` `citation.csl` |
| `reference-doc` | Reference milik format | `format.yml` `assets.reference_docx` |
| `template` | Template milik struktur | `structure.yml` `front_matter` |
| `cover` | Sampul dihasilkan | `format.yml` `assets.cover` |

### 4.7 Hubungan body dan struktur

- Setiap Heading 1 di body harus cocok dengan satu entri `body` kecuali
  `# Lampiran`.
- Heading 1 tidak boleh berurutan ganda.
- Heading 2 dan Heading 3 tidak boleh melompati level (H2 sebelum H1 adalah
  error).
- `# Lampiran` hanya boleh muncul sekali, setelah bab terakhir, dan hanya
  jika `back_matter` memuat `appendices`.
- Isi `preface`, `abstract_id`, dan `abstract_en` berasal dari front matter,
  bukan dari Heading 1.

---

## 5. Validasi lintas berkas

| Kode | Aturan | Level |
|---|---|---|
| `CFG-FORMAT-MISSING` | `formats/<format>/format.yml` tidak ada | error |
| `CFG-STRUCTURE-MISSING` | `structures/<structure>/structure.yml` tidak ada | error |
| `CFG-TEMPLATE-MISSING` | Template `source: template` tidak ada | error |
| `CFG-UNKNOWN-KEY` | Key tidak ada di skema tertutup | error |
| `CFG-REQUIRED` | Field wajib kosong/tidak ada | error |
| `CFG-TYPE` | Tipe/enum/satuan salah | error |
| `CFG-DUPLICATE` | ID, title, atau path duplikat | error |
| `CFG-PATH-ESCAPE` | Path absolut atau keluar direktori | error |
| `CFG-ASSET-MISSING` | Aset format/dokumen tidak ada | error |
| `CFG-FORMAT-OVERRIDE` | `document.format` != `structure.format` | warning |
| `CFG-CONDITIONAL` | Key kondisional tidak sesuai `source` | error |
| `CFG-BODY-ORDER` | Heading 1 tidak cocok urutan `body` | error |
| `CFG-YAML-DUPLICATE` | Duplikat key YAML | error |

Semua error menyebut path berkas dan key yang bermasalah. Contoh:

```text
document.md: front matter: kunci 'structure' wajib diisi (CFG-REQUIRED)
structure 'thesis': template 'approval.md' tidak ditemukan di
  src/docgen/data/structures/thesis/templates (CFG-TEMPLATE-MISSING)
format 'undip-msi': kunci 'presets' tidak dikenal (CFG-UNKNOWN-KEY)
```

`docgen check` dan `docgen build` mengembalikan exit code `1` untuk semua
error konfigurasi. Exit code `2` hanya untuk kesalahan pemakaian CLI.

### 5.1 Tidak ada key mati

Kontrak ini memakai skema tertutup: validator menolak key yang tidak ada di
dokumen ini. Key baru hanya boleh ditambahkan setelah ada entri skema,
konsumen nyata, dan tes positif/negatif.

---

## 6. Migrasi dari skema lama

- `presets/` dihapus. Kedua preset lama digabung ke satu `format.yml`;
  perbedaan penomoran/urutan dipindah ke `structure.yml`.
- Key lama `csl:` dan `bibliography:` di `format.yml` pindah ke
  `citation.csl` dan `citation.bibliography`.
- Key lama `presets:` dihapus; tidak ada pemetaan struktur -> preset.
- `reference.docx`, `logo.jpg`, dan CSL root lama pindah ke aset format:
  `assets.reference_docx`, `assets.logo`, dan `citation.csl`.
- `cover_show_lecturer` dan `cover_logo_width` dari preset lama pindah ke
  `structure.cover.show_lecturer` dan `structure.cover.logo_width`.
  `assets.cover` dan `assets.logo_width` di `format.yml` dihapus.
- `metadata.yml` dan `cover.md` tidak lagi menjadi input. Semua metadata
  pindah ke front matter `document.md`; sampul dihasilkan dari metadata
  dokumen dan `structure.cover`.
- `structures/*.yml` lama dengan `chapters:` berupa path berkas dimigrasikan
  menjadi `body:` berisi `{id, title}`. Path `chapters/*.md` tidak lagi
  dikenali.
- `front_matter` lama berupa daftar string (`[cover, approval]`) harus
  dimigrasikan menjadi entri `{id, source, template}`.
- `toc`, `daftar_gambar`, dan `daftar_tabel` di front matter dokumen harus
  dihapus; nilainya pindah ke `structure.yml`.
- `preset:` di mana pun adalah error, bukan fallback.

---

## 7. Acceptance

- `docgen check examples/assignment-single/document.md`,
  `examples/thesis-single/document.md`, dan
  `examples/proposal-single/document.md` lulus.
- `tests/unit/test_config.py` mencakup schema format/structure, key tidak
  dikenal, margin wajib, template hilang, konsistensi TOC/lists, cover, dan
  path escape.
- `tests/unit/test_document.py` mencakup author scalar/list, NIM,
  abstract/keywords kondisional, body order, duplikat YAML, dan path escape.
- Validator menolak `preset`, `margin_preset`, `daftar_gambar`,
  `daftar_tabel`, `keywords_id`, `approval`, `statement`, `references`,
  `csl`, `reference-doc`, `template`, `cover`, dan `toc` di front matter
  dokumen sebagai `CFG-UNKNOWN-KEY`.
- Path `chapters/` tidak dikenali.
