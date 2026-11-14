# Demo Deck AutoOffice

Deck demo penerimaan AutoOffice yang diporting dari demo `deck-studio`. Deck
ini menjadi contoh authoring lengkap untuk schema `autooffice.deck/v1`: 24
slide, 20 layout, 11 block type, chart native, tabel, gambar, diagram Mermaid,
kutipan, divider, dan spacer.

`theme.name` di `deck.yaml` adalah `indigo`. Deck yang sama juga dibangun
dengan `--theme hitam`; tidak ada token, warna, atau font yang ditulis di YAML.

## Cakupan

### Layout

| Layout | Slide | Catatan |
| --- | --- | --- |
| `cover` | s01 | Pembuka dengan metric ringkasan |
| `toc` | s02 | Tiga kelompok bullet |
| `content` | s03, s23 | Narasi dan bukti penerimaan |
| `section` | s04 | Pembatas kelompok data |
| `kpi` | s05 | Empat metric |
| `bars` | s06 | Chart batang native |
| `line` | s07 | Chart garis native |
| `donut` | s08 | Chart donat native dan legenda |
| `table` | s09 | Tabel native lima kolom |
| `comparison` | s10 | Tabel dengan `emphasis_column` |
| `matrix` | s11 | Tabel kuadran dan legenda |
| `background` | s12 | Tiga poin konteks |
| `flow` | s13 | Empat langkah proses |
| `code` | s14 | Blok kode SQL |
| `diagram` | s15, s21 | Diagram Mermaid dari berkas `.mmd` |
| `image-split` | s16, s22 | Teks dan gambar |
| `image-full` | s17 | Gambar penuh dengan caption |
| `image-grid` | s18 | Tiga gambar |
| `closing` | s24 | Penutup dan kontak |
| `custom` | s19, s20 | Grid 12 kolom dengan `rows` dan `span` |

### Block

| Block | Slide | Catatan |
| --- | --- | --- |
| `text` | semua | Termasuk `role` display, title, lead, body, caption, label, kicker |
| `bullets` | s02, s03, s08, s11, s20, s23 | Beberapa layout memakai bullet sebagai legenda |
| `image` | s16, s17, s18, s22 | Empat gambar JPG |
| `table` | s09, s10, s11 | Jumlah kolom konsisten dan tanpa merged cell |
| `chart` | s06, s07, s08 | Bar, line, dan donut |
| `code` | s14 | SQL dengan nomor baris |
| `quote` | s19 | Hanya di layout `custom` |
| `diagram` | s15, s21 | Dua berkas `.mmd` |
| `divider` | s19 | Hanya di layout `custom` |
| `spacer` | s19 | Hanya di layout `custom` |
| `metric` | s01, s05, s20 | Status metric memakai token |

Tidak ada block di luar 11 tipe resmi. Tidak ada posisi absolut: preset memakai
slot, dan `custom` hanya memakai `rows` dan `span`.

Batas chart yang dipakai:

- `bars` s06: satu seri, empat kategori.
- `line` s07: dua seri, delapan kategori.
- `donut` s08: tepat satu seri, empat kategori berwarna.

## Berkas pendamping

- `copy.yaml` memakai default copy checker. Tidak ada allowlist karena tidak ada
  label chart atau judul pendek yang memicu warning.
- `transcripts.md` memetakan seluruh 24 slide dengan heading
  `## sNN. Judul`. Setiap bagian punya `### Indonesia`; `### English` disertakan
  sebagai versi opsional.

## Build

Jalankan dari akar repo. Semua perintah memakai Python dan dependency yang
sudah dikunci di `uv.lock`.

Check schema, layout, copy, dan transkrip:

```bash
uv run autooffice check examples/demo-deck/deck.yaml
```

Rencana build PPTX tanpa menulis artefak:

```bash
uv run autooffice build examples/demo-deck/deck.yaml --target pptx --dry-run
```

Build PPTX native:

```bash
uv run autooffice build examples/demo-deck/deck.yaml --target pptx
```

Build PDF memakai konversi PowerPoint COM:

```bash
uv run autooffice build examples/demo-deck/deck.yaml --target pdf
```

Build staging PPTX dan push ke Google Slides:

```bash
uv run autooffice build examples/demo-deck/deck.yaml --target slides --sync push
```

Target `slides` memerlukan dependency Google dan state OAuth. Mode review
`--sync pull`, `--sync diff`, dan `--sync apply` menulis berkas di
`.autooffice/review/`.

Build ketiga target sekaligus:

```bash
uv run autooffice build examples/demo-deck/deck.yaml --target all
```

Uji theme kedua:

```bash
uv run autooffice build examples/demo-deck/deck.yaml --target pptx --theme hitam
```

Output final ditulis ke `examples/demo-deck/out/`:

- `deck.pptx`
- `deck.pdf`
- `deck.transcript.md`
- `deck.slides-upload.pptx` untuk staging Google Slides

## Aset

Gambar di `assets/` berasal dari demo `deck-studio` dan memakai foto Unsplash
melalui Lorem Picsum. Hanya gambar yang dipakai di deck yang disalin.

| Berkas | Subjek | Sumber |
| --- | --- | --- |
| `assets/workspace.jpg` | Meja kerja dengan laptop dan kopi | Unsplash via Lorem Picsum, id 0 |
| `assets/nature.jpg` | Danau dan hutan hijau | Unsplash via Lorem Picsum, id 10 |
| `assets/city.jpg` | Rumah putih di lereng bukit | Unsplash via Lorem Picsum, id 49 |
| `assets/architecture.jpg` | Istana di atas lembah hutan | Unsplash via Lorem Picsum, id 1040 |

Diagram di `diagrams/` berasal dari demo `deck-studio`:

| Berkas | Slide |
| --- | --- |
| `diagrams/01-flowchart.mmd` | s15 |
| `diagrams/05-sequence.mmd` | s21 |

Mermaid tidak ditulis inline di YAML. Setiap block `diagram` hanya menunjuk
berkas `.mmd` dan menyertakan alt text.

## Status

Deck ini mencakup 24 slide, termasuk dua slide `custom` (s19 dan s20) serta dua
slide `diagram` (s15 dan s21). Custom grid, render Mermaid, dan penyalinan aset
ke workspace build sudah tersedia; tidak ada slide yang ditunda. Validasi
schema, layout, copy, dan transkrip berlaku untuk seluruh 24 slide.
