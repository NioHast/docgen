# Kontrak Design Token

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 11 (11.1-11.6), 6, dan keputusan L15.
Pemilik kontrak: design owner.

## Tujuan

Kontrak ini membekukan token desain sebagai satu-satunya sumber warna,
tipografi, jarak, radius, shadow, grid, dan chart untuk renderer deck. Token
adalah data package `autooffice.design`, bukan berkas kerja pengguna.

## Invarian

1. Token minimal mencakup warna, tipografi, slide, grid, spacing, radius,
   shadow, chart (`chartSeries`, grid, axis, legend, title), dan code.
2. Semua renderer membaca token yang sudah di-resolve. Renderer tidak boleh
   memuat hex, ukuran font, margin, gutter, radius, shadow, tracking, divider,
   atau line-height hardcoded.
3. Hanya ada dua theme produk:
   - `indigo`, mode light, default.
   - `hitam`, mode light dengan aksen hitam, bukan dark theme.
4. `hitam` memakai kanvas terang, aksen `#111827`, dan cover gradient
   `#111827` -> `#0B1220` -> `#000000`. Palet `malam` tidak dipakai.
5. Pergantian theme hanya mengubah nilai warna. Objek `Theme` yang sudah
   di-resolve tetap membawa tipografi, grid, spacing, radius, shadow, dan code.
6. `chartSeries` berisi tepat empat warna dan wajib lolos kontras minimal 3:1
   terhadap background chart:
   - `indigo`: `#4F46E5`, `#0F766E`, `#B45309`, `#BE123C`.
   - `hitam`: `#111827`, `#374151`, `#4B5563`, `#6B7280`.
7. Palet aksen dan cover tetap persis token deck-studio. Hanya warna chart
   yang memakai turunan `chartSeries` untuk aksesibilitas.
8. Chart dibatasi empat slot warna: seri untuk `bar`/`line`, kategori untuk
   `donut`.
9. Tipografi deck memakai `Plus Jakarta Sans` weight 400, 600, 700, dan 800.
   Judul 40 px / 30 pt, body 22 px / 16.5 pt, minimal teks 10 pt. Mono
   memakai system mono stack
   `ui-monospace, 'Cascadia Mono', Consolas, monospace`. Tidak ada font
   family lain di deck.
10. DOCX mempertahankan font format docgen dan tidak memakai Plus Jakarta
    Sans.
11. Kontras teks normal minimal 4.5:1, teks besar minimal 3:1. Status tidak
    boleh menjadi satu-satunya pembeda; selalu ada label.
12. Dilarang gradient dekoratif selain cover, glow, glass, blur, blob 3D,
    pola acak, aksen pada body/caption/footer/page number, hex atau ukuran
    font di YAML, dan font di luar design system.
13. F0 membekukan bentuk, sumber, dan aturan token, bukan nilai akhir. Nilai
    final dibekukan setelah audit kontras pada F1-DESIGN; perubahan nilai
    memerlukan ADR dan pembaruan golden visual.

## Bentuk theme

F0 membekukan bentuk dan aturan token, bukan nilai akhir. Nilai final
dibekukan setelah audit kontras pada F1-DESIGN. Theme terdiri dari sub-dataclass
immutable `ThemeColors`, `ChartPalette`, `Typography`, `GridTokens`,
`SpacingTokens`, `RadiusTokens`, `ShadowTokens`, dan `CodeTokens`.

```python
Theme(name: str, mode: Literal["light"], colors: ThemeColors,
      chart: ChartPalette, typography: Typography, grid: GridTokens,
      spacing: SpacingTokens, radius: RadiusTokens, shadow: ShadowTokens,
      code: CodeTokens)
ThemeColors(background, surface, surface_alt, ink, ink_secondary, muted,
            border, accent, accent_deep, accent_soft, accent_line, accent_ink,
            status: Mapping[str, str])
ChartPalette(series: tuple[str, str, str, str], grid, axis, legend, title)
Typography(family, weights: tuple[int, int, int, int], title_pt, body_pt,
           minimum_pt, line_height, tracking_em)
GridTokens(columns, gutter_emu, margin_left_emu, margin_right_emu,
           margin_top_emu, margin_bottom_emu, row_gap_emu,
           slide_width_emu, slide_height_emu)
SpacingTokens(sm_emu, md_emu, lg_emu, card_padding_emu, divider_emu)
RadiusTokens(sm_emu, md_emu, lg_emu)
ShadowTokens(card, overlay, none)
CodeTokens(family, size_pt, line_height)
```

Semua objek theme immutable dan `status` bersifat read-only. Field `emu`
memakai integer English Metric Units agar renderer tidak menulis angka baru.

Nilai warna lain, spacing, grid, dan tipografi bersumber dari
`design-system/tokens.json` dan `design-system/themes.json` deck-studio, lalu
diport ke `src/autooffice/design/data/` oleh F1-DESIGN.

## Contoh konstruksi

```python
theme = Theme(
    name="hitam",
    mode="light",
    colors=ThemeColors(
        background="#FFFFFF", surface="#F8FAFC", surface_alt="#F1F5F9",
        ink="#111827", ink_secondary="#374151", muted="#6B7280",
        border="#E5E7EB", accent="#111827", accent_deep="#0B1220",
        accent_soft="#F3F4F6", accent_line="#D1D5DB", accent_ink="#FFFFFF",
        status={"success": "#0F766E", "warning": "#B45309"},
    ),
    chart=ChartPalette(
        series=("#111827", "#374151", "#4B5563", "#6B7280"),
        grid="#E5E7EB", axis="#6B7280", legend="#374151", title="#111827",
    ),
    typography=Typography(
        family="Plus Jakarta Sans", weights=(400, 600, 700, 800),
        title_pt=30, body_pt=16.5, minimum_pt=10, line_height=1.2,
        tracking_em=-0.01,
    ),
    grid=GridTokens(
        columns=12, gutter_emu=91440, margin_left_emu=914400,
        margin_right_emu=914400, margin_top_emu=609600,
        margin_bottom_emu=609600, row_gap_emu=182880,
        slide_width_emu=12192000, slide_height_emu=6858000,
    ),
    spacing=SpacingTokens(
        sm_emu=45720, md_emu=91440, lg_emu=137160, card_padding_emu=182880,
        divider_emu=12700,
    ),
    radius=RadiusTokens(sm_emu=45720, md_emu=91440, lg_emu=182880),
    shadow=ShadowTokens(
        card="0 1 2 0 rgba(17, 24, 39, 0.08)",
        overlay="0 8 24 0 rgba(17, 24, 39, 0.16)",
        none="none",
    ),
    code=CodeTokens(family="ui-monospace, 'Cascadia Mono', Consolas, monospace",
                    size_pt=10.5, line_height=1.35),
)
assert theme.mode == "light"
assert theme.colors.accent == "#111827"
assert len(theme.chart.series) == 4
assert theme.grid.slide_width_emu == 12192000
```

Renderer menerima `theme` hasil resolusi; ia tidak membaca nama theme atau
nilai hex langsung. Resolver token (`resolve_theme`) adalah deliverable
F1-DESIGN; kontrak F0 hanya menetapkan bentuk, sumber nilai, dan aturan.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Dua theme dan mode light | `tests/design/test_themes.py` (planned); golden visual `hitam`. |
| `chartSeries` empat warna dan kontras 3:1 | `tests/design/test_contrast.py` (planned); F2-CHARTS. |
| Tidak ada hex di renderer | Contract test scan `deck/render/**`; review F1-DESIGN. |
| Font dan embedding | `tests/design/test_fonts.py` (planned); `tests/deck/render/pptx/test_fonts.py` (planned). |
| Tipografi dan ukuran minimum | Golden PPTX dan visual test; bagian 18.4. |
| Larangan desain | Contract test dan review golden; bagian 11.5. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
