# Format UNDIP dan Sitasi IEEE

## Preset aktif

`metadata.yml` memakai preset UNDIP:

```yaml
preset: "undip-skripsi"
```

Berkas preset: `presets/undip-skripsi.yml`.

| Kunci | Nilai |
| --- | --- |
| `preset_id` | `undip-skripsi` |
| `name` | `Universitas Diponegoro (UNDIP)` |
| `description` | `Format Skripsi & Tugas Akhir sesuai Pedoman Akademik Universitas Diponegoro (Margin 4-4-3-3).` |
| `margin_top` | `4cm` |
| `margin_bottom` | `3cm` |
| `margin_left` | `4cm` |
| `margin_right` | `3cm` |
| `font_family` | `Libertinus Serif` |
| `font_size` | `12pt` |
| `line_spacing` | `0.75em` |
| `first_line_indent` | `1.25cm` |
| `heading_chapter_prefix` | `BAB ` |
| `heading_chapter_num_format` | `roman` |
| `heading_sub_dot` | `true` |
| `heading_subsub_dot` | `false` |
| `cover_show_lecturer` | `true` |
| `cover_logo_width` | `4cm` |

Catatan pemetaan ke DOCX (lihat `docs/style-generator.md`):

- `line_spacing: 0.75em` adalah satuan Typst; generator DOCX memetakannya ke
  spasi 1,5 baris.
- `font_family` dipakai untuk Typst/PDF. Untuk DOCX, generator memakai
  Times New Roman kecuali di-override dengan `--font`.

## Gaya sitasi: IEEE

Berkas CSL aktif: `refs/ieee.csl`.

Berkas ini diunduh dari repositori resmi Citation Style Language:

```text
https://raw.githubusercontent.com/citation-style-language/styles/master/ieee.csl
```

Gaya IEEE memakai sitasi numerik dalam tanda kurung siku, misalnya `[1]`,
`[2]`, dengan daftar pustaka bernomor. Gaya ini menggantikan `apa.csl` pada
pipeline DOCX.

### Cara mengganti gaya sitasi

1. Letakkan berkas CSL baru di `refs/`, misalnya `refs/apa.csl`.
2. Ubah baris `--csl=` pada `build-docx.sh` agar menunjuk berkas tersebut:

   ```bash
   --csl="refs/apa.csl" \
   ```

3. Uji tanpa build penuh:

   ```bash
   pandoc uji.md \
     --citeproc \
     --bibliography=references.bib \
     --csl=refs/ieee.csl \
     -t plain
   ```

   Hasil yang diharapkan untuk gaya IEEE adalah sitasi `[1]`, `[2]`, bukan
   `(Nama, 2020)`.

Berkas `apa.csl` di root repositori masih ada, tetapi tidak lagi dirujuk oleh
`build-docx.sh`.

## Status nilai preset

Nilai pada `presets/undip-skripsi.yml` saat ini masih berupa nilai awal
(margin 4-4-3-3, Libertinus Serif 12pt, spasi 0.75em) dan **belum final**.
Penyesuaian akhir akan ditentukan dari reverse engineering berkas skripsi
acuan pengguna, terutama untuk margin, font, spasi, heading, dan penomoran.
Jangan menganggap nilai ini sebagai format UNDIP final sebelum proses tersebut
selesai.

## Catatan integrasi build

`build-docx.sh` menjalankan pandoc dari direktori sementara (`$TMPDIR`) dan
menyalin aset ke sana. Saat ini daftar `copy_asset` belum menyalin `refs/`,
sehingga `--csl="refs/ieee.csl"` hanya akan ditemukan bila direktori `refs/`
ikut tersedia di direktori kerja pandoc. Ini perlu diperhatikan saat build
DOCX penuh dijalankan.
