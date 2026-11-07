# Generator `reference.docx` dari Preset

`build-docx.sh` tidak lagi memakai `reference.docx` statis secara langsung.
Setelah preset dipilih dari `metadata.yml` (`preset: "..."`), build menjalankan:

```bash
python tools/build_style.py \
  --preset presets/skripsi-4433.yml \
  --out "$TMPDIR/reference-generated.docx"
```

Hasil generate itulah yang diberikan ke pandoc lewat `--reference-doc`.
Jika generator gagal, build berhenti dengan error; build tidak diam-diam
kembali memakai `reference.docx` lama.

## Kenapa `reference.docx` digenerate?

`reference.docx` menyimpan seluruh definisi style Word (`Normal`, `BodyText`,
`Heading1`, `ImageCaption`, `TableCaption`, `TOCHeading`, dan lainnya).
Membangun DOCX dari nol berisiko kehilangan style tersebut. Karena itu
`tools/build_style.py` hanya membuka zip `reference.docx` yang sudah ada,
mengubah nilai yang diperlukan di `word/styles.xml` dan `word/document.xml`,
lalu menyalin semua bagian zip lainnya apa adanya.

Nilai preset yang dipetakan ke DOCX:

| Preset | Lokasi DOCX | Konversi |
| --- | --- | --- |
| `margin_top`, `margin_bottom`, `margin_left`, `margin_right` | `w:pgMar` pada `w:sectPr` | cm/mm/in/pt ke twip (1 cm = 566.929 twip) |
| `font_size` | `w:sz` dan `w:szCs` | pt ke setengah poin (12pt -> 24) |
| `first_line_indent` | `w:ind/@w:firstLine` pada `BodyText` dan `FirstParagraph` | cm/mm/in/pt ke twip |
| `line_spacing` | `w:spacing` pada `Normal`, `BodyText`, `FirstParagraph` | selalu spasi 1,5 baris (`w:line="360"`) |

`line_spacing: 0.75em` adalah satuan Typst yang tidak setara langsung dengan
satuan Word. Pemetaan ke spasi 1,5 baris adalah keputusan yang disengaja agar
tampilan DOCX konsisten dengan PDF laporan.

Generator juga menambahkan dua character style jika belum ada:

- `IstilahAsing`: italic + `w:lang="en-US"`
- `IstilahReview`: highlight kuning

## Font DOCX vs font Typst

Preset memakai `font_family: "Libertinus Serif"`, yaitu font untuk mesin
Typst/PDF. Font tersebut umumnya tidak terpasang di Windows, sehingga Word
akan menggantinya secara diam-diam dan hasil DOCX tidak dapat diprediksi.
Karena itu generator **tidak memakai `font_family` preset untuk DOCX**.
Default font DOCX adalah **Times New Roman**. Override bila perlu:

```bash
python tools/build_style.py \
  --preset presets/skripsi-4433.yml \
  --out /tmp/reference-generated.docx \
  --font "Cambria"
```

Blok kode (font monospace seperti Consolas/DejaVu Sans Mono) tidak ikut
diubah oleh opsi `--font`.

## Cara mengubah preset

1. Pilih preset di `metadata.yml`, misalnya:

   ```yaml
   preset: "skripsi-4433"
   ```

   Nama harus sama dengan nama berkas di `presets/` tanpa `.yml`.

2. Atau jalankan generator langsung untuk mencoba satu preset:

   ```bash
   python tools/build_style.py \
     --preset presets/ui-skripsi.yml \
     --out /tmp/reference-ui.docx
   ```

3. Setelah itu jalankan `bash build-docx.sh`. Berkas
   `reference-generated.docx` dibuat di direktori sementara build dan tidak
   menimpa `reference.docx` di repositori.

Preset yang tersedia dapat dilihat di direktori `presets/`. Jangan mengubah
`reference.docx` secara manual untuk urusan margin/typografi; ubah preset
agar perubahan tercatat dan dapat direproduksi.
