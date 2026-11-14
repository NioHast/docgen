# Menulis Deck YAML

Halaman ini adalah panduan authoring `deck.yaml` untuk AutoOffice. Contoh
berjalan di seluruh halaman adalah [demo deck](../../examples/demo-deck/README.md):
24 slide, 19 layout preset, satu `custom`, dan 11 block type. Kontrak
normatifnya ada di [skema deck](../contracts/deck-schema.md),
[spesifikasi block](../contracts/block-spec.md),
[spesifikasi layout](../contracts/layout-spec.md),
[kontrak chart](../contracts/chart-contract.md),
[kontrak copy](../contracts/copy.md), dan
[kontrak transcript](../contracts/transcript.md).

## Daftar Isi

- [Berkas dan struktur](#berkas-dan-struktur)
- [meta, theme, dan defaults](#meta-theme-dan-defaults)
- [Slide](#slide)
- [Katalog layout preset](#katalog-layout-preset)
- [Custom rows dan span](#custom-rows-dan-span)
- [Tipe block](#tipe-block)
- [Chart](#chart)
- [Tabel](#tabel)
- [Gambar](#gambar)
- [Diagram](#diagram)
- [source dan notes](#source-dan-notes)
- [Aset](#aset)
- [Transkrip pembicara](#transkrip-pembicara)
- [Konfigurasi copy checker](#konfigurasi-copy-checker)
- [Check dan build](#check-dan-build)
- [Troubleshooting](#troubleshooting)

## Berkas dan struktur

Satu deck adalah satu berkas YAML. Tidak ada include, partial, atau berkas slide
terpisah. Berkas pendamping berada di folder yang sama:

```text
contoh-deck/
|-- deck.yaml          # wajib
|-- copy.yaml          # opsional
|-- transcripts.md     # opsional
|-- assets/            # gambar
`-- diagrams/          # berkas .mmd
```

Bentuk minimal:

```yaml
schema: autooffice.deck/v1

meta:
  title: "Demo Design System AutoOffice"
  author: "Tim AutoOffice"

theme:
  name: indigo

defaults:
  layout: content
  image_fit: contain
  code_language: text

slides:
  - id: s01
    layout: content
    blocks:
      - id: title
        type: text
        role: title
        text: "Kanvas Terang"
      - id: points
        type: bullets
        items:
          - "Latar netral dan kartu putih."
```

Aturan umum:

- YAML harus UTF-8 dan dibaca dengan safe loader. Tag kustom, lebih dari satu
  dokumen YAML, dan key mapping duplikat ditolak.
- Key asing ditolak di semua level. Tidak ada `extra` atau `metadata` bebas.
- Nilai yang tampil adalah string setelah inline Markdown; nilai chart adalah
  angka.
- YAML tidak boleh memuat warna, font, ukuran, margin, padding, atau koordinat.
- Semua path aset relatif terhadap direktori `deck.yaml`.
- `slides` minimal satu. Urutan array adalah urutan presentasi.

## meta, theme, dan defaults

| Field | Wajib | Aturan |
| --- | --- | --- |
| `meta.title` | ya | Judul deck dan nama presentasi. |
| `meta.author` | ya | Nama penulis atau tim. |
| `meta.subtitle` | tidak | Subjudul deck. |
| `meta.organization` | tidak | Organisasi. |
| `meta.date` | tidak | Tanggal atau tahun tampilan. |
| `meta.language` | tidak | `id-ID` atau `en-US`; dinormalisasi ke `id` atau `en`. Default `id`. |
| `meta.description` | tidak | Deskripsi internal, tidak dirender. |
| `theme.name` | tidak | `indigo` (default) atau `hitam`. |
| `defaults.layout` | tidak | Default `content` bila slide tidak menulis `layout`. |
| `defaults.image_fit` | tidak | `contain` (default) atau `cover`. |
| `defaults.code_language` | tidak | Default `text` untuk block `code`. |

`meta` tidak menyimpan token, path output, ID Google, atau state build. Theme
hanya memilih nama; warna dan ukuran hidup di design system. Lihat
[Design System AutoOffice](../learn/design-system.md).

## Slide

| Field | Wajib | Aturan |
| --- | --- | --- |
| `id` | ya | Pola `^s[0-9]{2,}$`, unik, dan tidak berubah saat reorder. |
| `layout` | tidak | Nama layout preset atau `custom`; default dari `defaults.layout`. |
| `blocks` | kondisional | Wajib untuk preset, terlarang untuk `custom`. |
| `rows` | kondisional | Wajib untuk `custom`, terlarang untuk preset. |
| `source` | tidak | Object `text` wajib; `url` opsional. |
| `notes` | tidak | Catatan pembicara, plain text. |

`blocks` dan `rows` saling eksklusif. Layout yang tidak ada di katalog ditolak;
tidak ada fallback. Setiap slide yang punya tampilan juga harus punya key yang
valid, dan key dibentuk dari ID slide serta ID block.

## Katalog layout preset

Ada 19 preset. Author hanya mengisi block dengan ID slot; geometri milik
layout. Block di luar slot ditolak, slot wajib harus ada, dan `span` dilarang
di preset.

| Layout | Fungsi | Slot wajib | Slot opsional |
| --- | --- | --- | --- |
| `cover` | Pembuka deck | `title`, `author` | `kicker`, `subtitle`, `role`, `summary` (`metric`) |
| `toc` | Daftar isi 1 sampai 3 kelompok | `title`, salah satu `group1` sampai `group3` (`bullets`) | `lead` |
| `content` | Narasi dengan daftar poin | `title`, `points` (`bullets`) | `lead`, `note` |
| `section` | Pembatas bab | `title` | `number`, `subtitle` |
| `closing` | Penutup dan kontak | `title`, `contact` | `lead`, `note` |
| `kpi` | Sampai empat metric utama | `title`, salah satu `kpi1` sampai `kpi4` (`metric`) | `lead`, `note` |
| `bars` | Chart batang native | `title`, `chart1` (`chart`) | `lead`, `note` |
| `line` | Chart garis native | `title`, `chart1` (`chart`) | `lead`, `note` |
| `donut` | Chart donat native | `title`, `chart1` (`chart`) | `lead`, `legend` (`bullets`), `note` |
| `table` | Tabel native | `title`, `table1` (`table`) | `lead`, `note` |
| `comparison` | Tabel dengan kolom disorot | `title`, `table1` (`table` dengan `emphasis_column`) | `lead`, `note` |
| `matrix` | Tabel kuadran dan legenda | `title`, `matrix1` (`table`) | `lead`, `legend` (`bullets`), `note` |
| `background` | Konteks atau latar keputusan | `title`, `point1` sampai `point3` (`text`) | `kicker`, `lead` |
| `flow` | Empat langkah proses | `title`, `step1` sampai `step4` (`text`; `heading` untuk nomor langkah) | `lead` |
| `code` | Contoh kode dan catatan | `title`, `code1` (`code`) | `lead`, `note` |
| `diagram` | Diagram Mermaid | `title`, `diagram1` (`diagram`) | `subtitle` |
| `image-split` | Gambar di samping teks | `title`, `body` (`text`), `image1` (`image`) | `lead` |
| `image-full` | Gambar besar dengan teks pendukung | `title`, `image1` (`image`) | `subtitle`, `credit` |
| `image-grid` | Tiga gambar dalam grid | `title`, `image1` sampai `image3` (`image`) | `lead` |

Nama slot adalah ID block yang harus dipakai, misalnya `kpi1`, bukan `kpi_1`.
Semua slot `text` menuntut `role` yang sama dengan role slot: `title`, `lead`,
`caption`, `body`, `kicker`, `label`, atau `display`. Slot `summary` menerima
`metric`, bukan `text`. Contoh lengkap per layout ada di
[deck demo](../../examples/demo-deck/deck.yaml): `s06` untuk `bars`, `s11`
untuk `matrix`, dan `s16` untuk `image-split`.

Slot `chart1` pada `bars`, `line`, dan `donut` mengikat block `chart` ke kind
yang sama dengan nama preset: `bars` wajib `kind: bar`, `line` wajib
`kind: line`, dan `donut` wajib `kind: donut`. Chart dengan kind berbeda
ditolak saat `autooffice check` atau build dengan `LayoutSpecError` yang
menyebut slide, block, dan slot. Layout `custom` tidak memakai slot preset,
sehingga kind chart di sana tidak dibatasi oleh nama layout.

## Custom rows dan span

`layout: custom` adalah satu-satunya layout yang memakai `rows` author. Setiap
block wajib menulis `span` 1 sampai 12. Block ditempatkan kiri ke kanan sesuai
urutan, jumlah `span` per row maksimal 12, dan tinggi row mengikuti block
tertinggi.

```yaml
- id: s19
  layout: custom
  rows:
    - blocks:
        - id: title
          type: text
          role: title
          text: "Kutipan dan Catatan"
          span: 12
    - blocks:
        - id: quote1
          type: quote
          text: "Rapat yang baik berakhir dengan keputusan."
          span: 8
        - id: insight
          type: text
          heading: "Catatan"
          text: "Kutipan menutup satu bagian."
          span: 4
```

Tidak ada nested row, nested column, offset, `col_start`, `align`, atau tinggi
absolut. Sisa kolom di kanan row boleh kosong. `divider` dan `spacer` hanya
boleh dipakai di `custom`; contohnya ada di `s19` dan `s20`. Penjelasan konsep
ada di [Sistem Layout](../learn/layout-system.md).

## Tipe block

Tepat 11 block type. Tidak ada `callout`.

| Type | Field wajib | Field opsional | Key |
| --- | --- | --- | --- |
| `text` | `text` | `heading`, `role` | `.text`, `.heading` |
| `bullets` | `items` | `ordered` | `.itemN.text` |
| `image` | `path`, `alt` | `caption`, `fit` | `.caption` |
| `table` | `columns`, `rows` | `caption`, `emphasis_column` | `.caption`, `.hN`, `.rN.cM` |
| `chart` | `kind`, `title`, `alt`, `categories`, `series` | `orientation`, `unit`, `caption` | `.title`, `.catN`, `.seriesN.name`, `.seriesN.valueN`, `.caption` |
| `code` | `code` | `language`, `filename`, `line_numbers` | `.code`, `.filename` |
| `quote` | `text` | `attribution` | `.text`, `.attribution` |
| `diagram` | `source`, `alt` | `caption` | `.caption` |
| `divider` | tidak ada | tidak ada | tidak ada |
| `spacer` | tidak ada | `size` (`sm`, `md`, `lg`) | tidak ada |
| `metric` | `label`, `value` | `caption`, `status` | `.label`, `.value`, `.caption` |

`role` hanya untuk block `text`: `display`, `title`, `lead`, `body`, `caption`,
`label`, atau `kicker`. `metric.status` hanya `neutral`, `success`, `warning`,
atau `danger`. `image.alt` dan `diagram.alt` wajib diisi. Inline Markdown hanya
`**bold**`, `` `inline code` ``, link `https`, `http`, atau `mailto`, dan escape
`\*`, `\_`, `` \` ``, `\[`, `\]`. Italic, heading Markdown, list Markdown,
gambar Markdown, tabel Markdown, HTML, dan em dash atau en dash ditolak.

## Chart

```yaml
- id: chart1
  type: chart
  kind: bar
  title: "Kunjungan per kanal"
  alt: "Diagram batang kunjungan per kanal"
  categories: ["Organik", "Referral", "Sosial", "Langsung"]
  series:
    - name: "Kunjungan"
      values: [420, 260, 180, 120]
  unit: "kunjungan"
```

- `kind` hanya `bar`, `line`, atau `donut`. `orientation` hanya untuk `bar`.
- `bar` dan `line` menerima 1 sampai 4 seri. `donut` menerima tepat satu seri
  dan 2 sampai 4 kategori berwarna.
- Jumlah `values` setiap seri harus sama dengan jumlah `categories`.
- `title`, `categories`, `series[].name`, `unit`, dan `alt` adalah plain text;
  Markdown ditolak atau diperlakukan literal.
- Chart wajib native di PPTX dan linked Sheets chart di Google Slides. Chart
  tidak pernah menjadi gambar, termasuk untuk PDF.
- Palet chart hanya punya empat slot warna. Bila butuh lebih dari empat,
  pecah menjadi beberapa chart atau sajikan sebagai tabel.
- Contoh demo: `s06` (`bar`), `s07` (`line`), dan `s08` (`donut`).

## Tabel

```yaml
- id: table1
  type: table
  columns: ["Modul", "Status", "Progres"]
  rows:
    - ["Onboarding", "Selesai", "100%"]
    - ["Dashboard", "Berjalan", "72%"]
  caption: "Status modul."
```

Jumlah sel setiap baris harus sama dengan jumlah kolom. Tidak ada merged cell,
nested table, rowspan, atau colspan. `emphasis_column` memakai indeks 1-based
dan hanya valid pada layout `comparison`. Tabel wajib menjadi table native yang
editable, bukan gambar. Contoh demo: `s09`, `s10`, dan `s11`.

## Gambar

```yaml
- id: image1
  type: image
  path: "assets/workspace.jpg"
  alt: "Meja kerja dengan laptop dan kopi"
  fit: contain
```

Format yang diterima hanya `.png`, `.jpg`, `.jpeg`, dan `.webp`. SVG dan URL
remote ditolak. `alt` wajib; `caption` adalah key teks, bukan alt. `contain`
menampilkan gambar utuh tanpa distorsi, sedangkan `cover` memenuhi frame dengan
crop proporsional, bukan regangan. `image-full` memakai satu block `image`
besar dengan title serta credit dari slot, bukan koordinat author. Contoh demo:
`s16`, `s17`, dan `s18`.

## Diagram

```yaml
- id: diagram1
  type: diagram
  source: "diagrams/01-flowchart.mmd"
  alt: "Diagram alur pengajuan cuti"
  caption: "Gambar 1. Flowchart pengajuan cuti."
```

Satu block menunjuk tepat satu berkas `.mmd`. Diagram dirender oleh `mmdc`
menjadi PNG; tidak ada node atau edge native di PPTX maupun Google Slides.
`check` memvalidasi path dan alt tanpa menjalankan `mmdc`; `build` memerlukan
`mmdc` di `PATH` atau `AUTOOFFICE_MMDC`. Lihat juga
[Panduan Mermaid](mermaid.md). Contoh demo: `s15` dan `s21`.

## source dan notes

```yaml
- id: s03
  layout: content
  notes: |
    Tekankan bahwa satu model isi dipakai untuk semua target.
  source:
    text: "Sumber: kit komponen internal AutoOffice, 2026"
    url: "https://example.com/laporan"
  blocks:
    - id: title
      type: text
      role: title
      text: "Kanvas Terang"
    - id: points
      type: bullets
      items:
        - "Latar netral dan kartu putih."
```

`source.text` wajib bila `source` ada dan menjadi key `sNN.source.text`.
`source.url` opsional, hanya `http` atau `https`, dan tidak menjadi key. Bila
ada, teks source menjadi hyperlink. Posisi source ditentukan layout.

`notes` adalah plain text, boleh multiline, menjadi key `sNN.notes`, dan
disimpan sebagai speaker notes. Notes tidak tampil di kanvas slide, tetapi ikut
push, pull, diff, dan apply teks. Notes bukan transkrip. Contoh demo: `s03` dan
`s05`.

## Aset

- Path relatif terhadap direktori YAML dan memakai `/`, bukan `\`.
- Path absolut, UNC, drive letter, `..`, dan URL remote ditolak. Symlink yang
  keluar dari root deck juga ditolak.
- Berkas harus ada saat `check` dan `build`.
- Gambar `.webp` dikonversi ke PNG di cache build.
- Semua gambar dan diagram wajib punya `alt`.
- Berkas yang tidak dipakai bukan error, tetapi dapat ditandai sebagai aset
  yatim oleh pemeriksa.
- Font tidak boleh diambil dari path pengguna; font berasal dari package.

## Transkrip pembicara

`transcripts.md` opsional. Bila ada, setiap slide wajib punya tepat satu
bagian, urutan bebas, dan mapping memakai ID slide. Contoh lengkap:
[transcripts.md demo deck](../../examples/demo-deck/transcripts.md).

```markdown
# Transkrip Demo Design System AutoOffice

## s01. Komponen Presentasi AutoOffice
**Perkiraan durasi:** 45 detik

### Indonesia
Cover ini membuka deck dengan judul Komponen Presentasi AutoOffice.

### English
This cover opens the deck with the title Komponen Presentasi AutoOffice.
```

- Heading bagian wajib `## <slide_id>. <judul slide>`, memakai titik setelah
  ID.
- `### Indonesia` wajib. `### English` opsional dan diperiksa dengan rule pack
  Inggris.
- `**Perkiraan durasi:** <detik> detik` opsional dan harus bilangan bulat
  positif.
- Transkrip bukan notes, tidak masuk PPTX notes, dan tidak disinkronkan ke
  Google Slides.
- Output berupa `<stem>.transcript.md` di direktori output yang sama dengan
  PPTX.

## Konfigurasi copy checker

`copy.yaml` opsional dan harus berada di folder deck yang sama. Tanpa berkas
ini, semua rule default berlaku. [copy.yaml demo deck](../../examples/demo-deck/copy.yaml)
hanya menulis `schema: 1`.

```yaml
schema: 1

targets:
  slides: true
  notes: true
  transcript: true

rules:
  sentence_length:
    severity: warning
    max_words: 25
  dash:
    severity: error
  banned_phrases:
    severity: error
    extra:
      id:
        - "frasa yang dilarang"

allow:
  - key: "s06.chart1.title"
    rules: [sentence_length]
    reason: "Label chart pendek"
```

Merge dilakukan per rule. `enabled: false` atau `severity: off` mematikan
rule. `allow` wajib punya `reason`; key harus ada dan `rules` harus nama rule
yang dikenal. `extra` berisi frasa literal per bahasa, bukan regex. Error
menghentikan build sebelum layout; warning dicetak dan build tetap jalan.
Tidak ada flag untuk melewati checker. Latar belakang aturan ada di
[Humanizer AutoOffice](../learn/humanizer.md).

## Check dan build

Jalankan dari akar repo:

```bash
uv run autooffice check examples/demo-deck/deck.yaml
uv run autooffice build examples/demo-deck/deck.yaml --target pptx --dry-run
uv run autooffice build examples/demo-deck/deck.yaml --target pptx
uv run autooffice build examples/demo-deck/deck.yaml --target pptx,pdf
uv run autooffice build examples/demo-deck/deck.yaml --target slides --sync diff
uv run autooffice build examples/demo-deck/deck.yaml --target all
uv run autooffice build examples/demo-deck/deck.yaml --target pptx --theme hitam
```

- `check` memvalidasi schema, coverage, layout, copy, dan transkrip tanpa
  menulis output.
- `--dry-run` mencetak rencana file dan target tanpa menulis file atau state.
- `pptx,pdf` adalah jalur offline. `slides` dan `all` memerlukan extra
  `google` serta kredensial OAuth.
- `--theme hitam` menimpa `theme.name`. `--out DIR` memindahkan artefak final.
- `--sync push` adalah default; `pull`, `diff`, dan `apply` memerlukan state
  presentasi.
- Untuk `examples/<nama>/`, output final ditulis ke `examples/<nama>/out/`:
  `deck.pptx`, `deck.pdf`, dan `deck.transcript.md` bila transkrip ada.
- State berada di `.autooffice/state/<stem>.json`; cache dan review berada di
  `.autooffice/cache/` dan `.autooffice/review/`, semuanya di samping YAML.
- Intermediate berada di `.autooffice-build/<stem>/` di samping YAML.

Rincian target, flag, dan kode keluar ada di [CLI AutoOffice](cli.md).

## Troubleshooting

| Gejala | Sebab | Tindakan |
| --- | --- | --- |
| Key asing atau field tidak dikenal | Schema strict | Hapus field; jangan menambah `extra`. |
| Block di luar slot | ID block bukan nama slot preset | Pakai ID slot yang ada di tabel layout. |
| Role tidak cocok | Slot meminta role lain | Samakan `role` block `text` dengan role slot. |
| Span ditolak di preset | Geometri preset milik layout | Hapus `span` atau pindah ke `layout: custom`. |
| Jumlah span lebih dari 12 | Row custom terlalu lebar | Pecah row atau kurangi `span`. |
| Aset tidak ditemukan | Path salah atau keluar folder | Pakai path relatif dengan `/` dan pastikan berkas ada. |
| Overflow | Teks, tabel, code, atau row tidak muat | Pendekkan isi atau pecah slide. Tidak ada shrink otomatis. |
| Chart ditolak | Seri atau kategori melewati batas | `bar`/`line` maksimal 4 seri; `donut` 1 seri dan 2 sampai 4 kategori. |
| Baris tabel ditolak | Jumlah sel tidak sama dengan kolom | Samakan panjang setiap baris. |
| Transkrip gagal | Slide hilang, duplikat, atau asing | Tulis tepat satu bagian per slide dengan ID yang cocok. |
| Copy checker error | Rule error atau frasa terlarang | Perbaiki naskah atau tambahkan `allow` dengan alasan. |
| `mmdc` gagal | Tool tidak ada atau render error | Jalankan `autooffice doctor` lalu pasang `mmdc`; lihat [troubleshooting](troubleshooting.md). |

Bila `check` dan `build` berbeda hasilnya, jalankan `--dry-run` untuk melihat
tahap yang gagal. Jangan mengakali gate dengan menghapus `alt`, memakai gambar
chart, atau menulis koordinat.
