# Design System AutoOffice

Halaman ini menjelaskan cara token, theme, font, dan kontras bekerja di deck
AutoOffice. Kontrak normatifnya ada di
[kontrak design token](../contracts/design-token.md); halaman ini adalah
panduan konsep dan contoh pemakaian.

## Alur token

Token adalah data package, bukan berkas kerja pengguna:

```text
src/autooffice/design/data/tokens.yaml   token dasar
src/autooffice/design/data/themes.yaml   override warna per theme
        |
        v
autooffice.design.theme.resolve_theme(name)
        |
        v
Theme immutable -> layout engine dan renderer
```

Renderer hanya menerima `Theme` yang sudah di-resolve. Renderer tidak membaca
nama theme atau nilai heksadesimal sendiri.

```python
from autooffice.design import resolve_theme

theme = resolve_theme("hitam")
print(theme.name)                 # hitam
print(theme.mode)                 # light
print(theme.colors.accent)        # #111827
print(theme.colors.background)    # #FAFAFA
print(len(theme.chart.series))    # 4
```

Nama theme yang tidak dikenal melempar `DesignTokenError` dengan daftar theme
yang tersedia. Default `resolve_theme()` adalah `indigo`.

## Token dasar

`tokens.yaml` memuat kategori berikut:

| Kategori | Isi | Contoh |
| --- | --- | --- |
| Warna | background, surface, ink, muted, border, aksen, status | `ink: #0B0B0F` |
| Tipografi | family, weight, ukuran pt, line-height, tracking | judul 30 pt, body 16.5 pt |
| Grid | 12 kolom, gutter, margin, row gap, kanvas 16:9 | 12192000 x 6858000 EMU |
| Spacing | `sm`, `md`, `lg`, padding kartu, divider | `sm_emu: 45720` |
| Radius | `sm`, `md`, `lg` | `md_emu: 91440` |
| Shadow | kartu, overlay, `none` | `0 1 2 0 rgba(17, 24, 39, 0.08)` |
| Chart | empat warna seri, grid, axis, legend, title | lihat bagian theme |
| Code | family mono, ukuran, line-height | `ui-monospace, ...`, 10.5 pt |

Ukuran memakai integer EMU supaya renderer tidak menulis angka baru. Satu
piksel kanvas sama dengan 9525 EMU. Kanvas 1280 x 720 px menjadi
12192000 x 6858000 EMU.

## Theme

Hanya ada dua theme produk. Keduanya mode `light`; `hitam` bukan dark theme.

| Theme | Aksen | Kanvas | Cover |
| --- | --- | --- | --- |
| `indigo` (default) | `#4F46E5` | `#FAFAFA` | `#4F46E5` -> `#4338CA` -> `#312E81` |
| `hitam` | `#111827` | `#FAFAFA` | `#111827` -> `#0B1220` -> `#000000` |

Theme hanya mengubah warna. Geometri grid, spacing, radius, shadow,
tipografi, dan code tetap sama di kedua theme. `hitam` tidak memakai palet
`malam`.

Warna chart memakai empat slot di kedua theme:

| Theme | `chartSeries` |
| --- | --- |
| `indigo` | `#4F46E5`, `#0F766E`, `#B45309`, `#BE123C` |
| `hitam` | `#111827`, `#374151`, `#4B5563`, `#6B7280` |

Palet kategorikal mentah `hitam` dari deck-studio memuat `#9CA3AF` dan
`#D1D5DB` yang tidak lolos 3:1 di kanvas terang. Karena itu AutoOffice memakai
turunan empat warna di atas. Batas empat slot berlaku untuk seri `bar`/`line`
dan kategori `donut`.

## Font

Deck memakai satu family: `Plus Jakarta Sans` weight 400, 600, 700, dan 800.
File TTF dan lisensi disimpan di:

```text
src/autooffice/assets/fonts/plus-jakarta-sans/
  PlusJakartaSans-Regular.ttf
  PlusJakartaSans-SemiBold.ttf
  PlusJakartaSans-Bold.ttf
  PlusJakartaSans-ExtraBold.ttf
  OFL.txt
```

`autooffice.design.fonts` mengekspos direktori font, daftar berkas, dan hash
SHA256. Test memverifikasi setiap berkas ada, magic bytes TTF valid, dan hash
cocok. Lisensi yang dipakai adalah SIL Open Font License 1.1.

DOCX tidak memakai Plus Jakarta Sans; DOCX mempertahankan font format docgen.
Google Slides memakai nama family `Plus Jakarta Sans` dari Google Fonts.

## Kontras

Aturan WCAG yang dipakai:

- teks normal minimal 4.5:1;
- teks besar minimal 3:1;
- warna seri chart minimal 3:1 terhadap permukaan chart;
- status tidak boleh dibedakan hanya lewat warna, selalu ada label.

Contoh pemeriksaan:

```python
from autooffice.design import resolve_theme
from autooffice.design.contrast import contrast_ratio

theme = resolve_theme("indigo")
assert contrast_ratio(theme.colors.ink, theme.colors.background) >= 4.5
assert contrast_ratio(theme.colors.muted, theme.colors.background) >= 4.5
assert all(
    contrast_ratio(color, theme.colors.surface) >= 3.0
    for color in theme.chart.series
)
```

`relative_luminance` dan `contrast_ratio` menerima warna heksadesimal enam
digit atau tuple RGB. Nilai kontras dipakai test, bukan dihitung ulang oleh
renderer.

## Aturan implementasi

- Warna, ukuran font, margin, gutter, radius, shadow, dan tracking hanya hidup
  di data token; modul Python di `src/autooffice` tidak menyimpan nilai
  heksadesimal.
- Deck authoring tidak menulis warna heksadesimal atau ukuran font.
- Tidak ada gradient dekoratif selain cover yang ditentukan token.
- Tidak ada glow, glass, blur dekoratif, blob 3D, atau pola acak.
- Tidak ada aksen pada body, caption, footer, atau nomor halaman.
- Theme tidak menambah zona aksen atau mengubah geometri layout.

Bukti kontrak ada di `tests/design/test_themes.py`, `test_contrast.py`, dan
`test_design_fonts.py`.
