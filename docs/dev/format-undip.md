# Format UNDIP dan Sitasi Author-Date (Turunan APA 7)

Dokumen ini menjelaskan format target UNDIP yang dipakai pipeline DOCX. PDF
mewarisi format DOCX karena diekspor dari dokumen final, bukan dirender ulang
dari Markdown.
Sumber kebenaran nilai format adalah `presets/undip-skripsi.yml`. Nilai pada
preset tersebut sudah final dan dipakai oleh build; pemetaan gayanya ke DOCX
diverifikasi oleh `tests/test_build_style.py`, sedangkan penomoran heading
diverifikasi oleh `tests/test_heading_numbering.py`.

## Preset aktif

`metadata.yml` memakai preset UNDIP:

```yaml
preset: "undip-skripsi"
```

Berkas preset: `presets/undip-skripsi.yml`. `build-docx.sh` membaca nama preset
dari `metadata.yml`, menyalin `presets/` ke direktori sementara, lalu
menjalankan `tools/build_style.py` untuk menghasilkan `reference.docx` sesuai
preset. `build.sh` mengekspor DOCX yang dihasilkan dengan preset tersebut,
sehingga PDF memakai margin, font, dan spasi yang sama.

### Nilai kunci

Margin halaman adalah **4/3/4/3 cm**: atas 4 cm, bawah 3 cm, kiri 4 cm, dan
kanan 3 cm.

| Kunci | Nilai | Catatan |
| --- | --- | --- |
| `preset_id` | `undip-skripsi` | ID preset. |
| `name` | `Universitas Diponegoro (UNDIP)` | Nama tampilan. |
| `description` | `Format Skripsi & Tugas Akhir sesuai Pedoman Akademik Universitas Diponegoro (Margin 4-4-3-3).` | Deskripsi preset. |
| `margin_top` | `4cm` | Margin atas. |
| `margin_bottom` | `3cm` | Margin bawah. |
| `margin_left` | `4cm` | Margin kiri. |
| `margin_right` | `3cm` | Margin kanan. |
| `font_family` | `Times New Roman` | Font teks DOCX dan PDF. Nilai lama `Libertinus Serif` dipetakan ke Times New Roman. |
| `font_size` | `12pt` | Ukuran teks isi. |
| `line_spacing` | `0.75em` | Nilai lama; DOCX memetakannya ke 1,5 baris dan PDF mengikuti DOCX. |
| `first_line_indent` | `1.25cm` | Indentasi baris pertama. |
| `heading_chapter_prefix` | `BAB ` | Prefiks heading bab. |
| `heading_chapter_num_format` | `roman` | Angka romawi untuk bab. |
| `heading_sub_dot` | `true` | Titik akhir nomor subbab (contoh `1.1.`). |
| `heading_subsub_dot` | `true` | Titik akhir nomor sub-subbab (contoh `1.1.1.`). |
| `cover_show_lecturer` | `true` | Menampilkan dosen pengampu di sampul. |
| `cover_logo_width` | `4.88cm` | Lebar logo sampul. |

### Gaya DOCX

Nilai berikut diterapkan `tools/build_style.py` dari kunci `<prefix>_<field>`
pada preset. Semua nilai dapat dioverride lewat preset.

| Style | Nilai final |
| --- | --- |
| `Normal` | Times New Roman 12 pt, spasi 1,5 baris (`w:line="360"`), before/after 0, justify, indentasi baris pertama 1,25 cm. |
| `Heading1` | Times New Roman 12 pt bold hitam, center, 0/0, indentasi baris pertama 0, keep next/keep lines. |
| `Heading2` | Times New Roman 12 pt bold hitam, justify, before/after 0 (jarak memakai paragraf kosong fisik), indent kiri 1,25 cm dan hanging 1,25 cm. |
| `Heading3` | Times New Roman 12 pt bold hitam, justify, before/after 0 (jarak memakai paragraf kosong fisik), indent kiri 1,25 cm dan hanging 1,25 cm. |
| `TOCHeading` | Times New Roman 12 pt bold hitam, center, 0/0. |
| `ImageCaption` | Times New Roman 10 pt tegak, center, 0/0, spasi 1,0 baris. |
| `TableCaption` | Times New Roman 10 pt tegak, rata kiri, 0/0, spasi 1,0 baris, keep next. |
| `SourceCode` | Courier New 10 pt, spasi 1,0 baris, 0/0, tanpa shading, rata kiri. |
| `Bibliography` | Times New Roman 12 pt, spasi 1,5 baris, 0/0, indent kiri 1,27 cm dan hanging 1,27 cm. |
| `Figure` | Center, 0/0, indentasi baris pertama 0. |

Caption bersifat wajib. Tabel Markdown harus memakai caption Pandoc
`: Judul tabel`; gambar harus memiliki alt text non-kosong. Build DOCX
berhenti dengan daftar temuan bila salah satunya tidak ada (lihat
`format-figures.md`).

Catatan pemetaan:

- `line_spacing: 0.75em` adalah nilai lama dari pipeline sebelumnya dan tidak
  punya padanan langsung di Word. DOCX selalu memakai spasi 1,5 baris; PDF
  mewarisi hasil DOCX sehingga nilai em tidak dikonversi secara matematis.
- `font_family` dipakai untuk DOCX; PDF mewarisi font yang sama. Nilai lama
  `Libertinus Serif` dari preset dipetakan ke Times New Roman. Untuk DOCX,
  generator memakai Times New Roman pada style teks; font monospace tetap
  Courier New. Override font DOCX hanya lewat opsi `--font` pada
  `tools/build_style.py`.
- `reference.docx` di repositori hanya dipakai sebagai basis style. Salinan
  sesuai preset dibuat di direktori sementara build; `reference.docx` tidak
  ditimpa dan tidak boleh diedit manual untuk urusan margin/typografi.

## Penomoran heading

`docx.lua` membaca `heading_chapter_prefix`, `heading_chapter_num_format`,
`heading_sub_dot`, dan `heading_subsub_dot` dari metadata preset:

- **Heading 1**: `BAB ` + angka romawi + baris baru + judul kapital, misalnya
  `BAB I` lalu `PENDAHULUAN`.
- **Heading 2**: nomor bab arab + nomor subbab + titik + TAB + judul, misalnya
  `1.1.` + TAB + `Latar Belakang`.
- **Heading 3**: nomor bab + nomor subbab + nomor sub-subbab + titik + TAB +
  judul, misalnya `1.1.1.` + TAB + `Sub Pertama`.

Karena `heading_sub_dot` dan `heading_subsub_dot` bernilai `true`, nomor subbab
dan sub-subbab berakhir dengan titik. Tab dan hanging indent 1,25 cm berasal
dari style `Heading2`/`Heading3`, bukan dari filter Lua. Heading dengan kelas
`{-}` (unnumbered) dilewati tanpa penomoran.

## Gaya sitasi: author-date alfabetis (turunan APA 7)

Berkas CSL aktif: `refs/undip-msi.csl`, turunan **APA Style 7th edition**.
Gaya ini menghasilkan sitasi author-date `(Nama, tahun)` dan daftar pustaka
alfabetis tanpa nomor, sesuai panduan MSI UNDIP.

Aturan utama:

- Satu penulis: `(Nama, 2020)`.
- Dua penulis: `Nama dan Nama, 2020` di dalam teks/kurung.
- Tiga penulis atau lebih: `Nama, dkk., 2020`.
- Daftar pustaka: alfabetis menurut nama belakang penulis pertama, tanpa label
  `[1]`; ampersand (`&`) dipertahankan sesuai `contoh-dp.txt`.

`metadata.yml` menetapkan `lang: "id-ID"`, dan CSL turunan juga memakai
`default-locale="id-ID"`. Istilah `dan`/`dkk.` berasal dari locale Indonesia;
`&` di daftar pustaka berasal dari aturan APA 7 yang tidak diubah.

Kedua skrip build membaca kunci `csl:` dari preset aktif (default
`refs/undip-msi.csl`):

```bash
--citeproc \
--bibliography="references.bib" \
--csl="$CSL_PATH" \
--metadata=reference-section-title="DAFTAR PUSTAKA"
```

Sumber entri pustaka adalah `references.bib`; judul bagian daftar pustaka
adalah `DAFTAR PUSTAKA`.

### Penyalinan `refs/` saat build

`build-docx.sh` menyalin seluruh direktori `refs/` ke `$TMPDIR` lewat
`copy_asset "refs" "$TMPDIR"`. Setelah itu build memeriksa keberadaan berkas
CSL yang dipilih preset; bila tidak ada, build berhenti dengan error. Karena
Pandoc dijalankan dari `$TMPDIR`, opsi `--csl="refs/undip-msi.csl"` menunjuk
berkas yang sudah tersalin. PDF memakai sitasi dan daftar pustaka yang sama
karena diekspor dari DOCX final.

### Cara mengganti gaya sitasi

1. Letakkan berkas CSL baru di `refs/`, misalnya `refs/nama-gaya.csl`.
   Direktori `refs/` disalin utuh ke direktori sementara build.
2. Ubah kunci `csl:` di preset aktif, misalnya
   `presets/undip-skripsi.yml`:

   ```yaml
   csl: "refs/nama-gaya.csl"
   ```

   Kedua skrip build membaca kunci ini; bila kunci tidak ada, default-nya
   `refs/undip-msi.csl`.
3. Pemeriksaan berkas di `build-docx.sh` mengikuti nilai `csl:` tersebut:

   ```bash
   CSL_FILE="$TMPDIR/$CSL_PATH"
   if [ ! -f "$CSL_FILE" ]; then
   ```

   Jika nilai `csl:` menunjuk berkas yang tidak ikut tersalin ke `refs/`,
   build akan berhenti.
4. Uji sitasi tanpa build penuh:

   ```bash
   pandoc uji.md \
     --citeproc \
     --bibliography=references.bib \
     --csl=refs/nama-gaya.csl \
     --metadata=lang=id-ID \
     -t plain
   ```

   Hasil yang diharapkan untuk gaya aktif adalah `(Nama, 2020)`,
   `Nama dan Nama, 2020`, dan `Nama, dkk., 2020` untuk tiga penulis atau
   lebih, bukan `[1]`, `[2]`.
5. Jalankan `bash build-docx.sh` untuk DOCX dan `bash build.sh` bila PDF juga
   memakai gaya baru.

### Cara mengganti preset

1. Ubah `metadata.yml`:

   ```yaml
   preset: "undip-skripsi"
   ```

   Nama harus sama dengan nama berkas di `presets/` tanpa akhiran `.yml`.
2. Pastikan berkas `presets/<nama-preset>.yml` tersedia. Untuk preset baru,
   salin preset yang ada lalu sesuaikan nilainya. `tools/build_style.py`
   mewajibkan empat kunci margin (`margin_top`, `margin_bottom`, `margin_left`,
   `margin_right`); kunci gaya lain punya default yang dapat dioverride dengan
   pola `<prefix>_<field>`, misalnya `heading1_font_size`.
3. Jalankan `bash build-docx.sh` untuk DOCX dan `bash build.sh` untuk PDF.
   Keduanya membaca preset yang sama dari `metadata.yml`.
4. Untuk mencoba satu preset tanpa build penuh, jalankan generator secara
   langsung:

   ```bash
   python tools/build_style.py \
     --preset presets/undip-skripsi.yml \
     --out /tmp/reference-generated.docx
   ```

Jika kunci `preset`/`margin_preset` berisi nama yang tidak ada di `presets/`,
build berhenti dengan error (exit 1); tidak ada fallback ke preset lain.
Fallback hanya berlaku bila kunci preset kosong atau tidak ada, yaitu memakai
preset yang ada di `presets/`. Periksa ejaan nama preset sebelum build.
