# Post-process Caption, Gambar, dan Tabel (`format_figures.py`)

Alat ini menyiapkan DOCX hasil build agar caption bernomor per bab, gambar
tidak melewati lebar teks, dan tabel memakai border/margin yang seragam.
Alat hanya menulis ulang `word/document.xml`; seluruh part lain disalin
byte-per-byte dari DOCX asli.

## Pemakaian

```bash
python tools/format_figures.py --docx input.docx --out output.docx
```

`--out` boleh menunjuk file yang sama dengan `--docx`. Penulisan dilakukan
lewat file sementara lalu `os.replace`, sehingga input tidak rusak bila proses
gagal di tengah jalan.

Keluaran CLI memuat jumlah caption yang diberi nomor, gambar yang dirapikan,
tabel yang diformat, dan peringatan bila ada bagian yang dilewati. Kode keluar
`0` selama dokumen berhasil diproses, termasuk ketika tidak ada Heading1.
Kesalahan input (bukan DOCX/ZIP, `word/document.xml` tidak ada, atau file tidak
dapat ditulis) menghasilkan kode keluar `1`.

## 1. Penomoran caption

### Deteksi caption

- `ImageCaption` → caption gambar.
- `TableCaption` → caption tabel.
- `Caption` → caption hanya jika teksnya berawalan `Gambar` atau `Tabel`.

Perbandingan `styleId` tidak peka huruf besar/kecil, spasi, garis bawah, atau
tanda hubung. Jadi `ImageCaption`, `Image Caption`, dan `image_caption`
dianggap sama. `FigureCaption` **bukan** style caption.

### Nomor bab

Nomor bab diambil dari `Heading1` terakhir yang teksnya cocok dengan:

```text
BAB <romawi/arab>
```

Contoh yang diterima: `BAB I PENDAHULUAN`, `BAB IV`, `BAB 2`, `BAB III.`.
Romawi dikonversi ke arab (I → 1, IV → 4, XII → 12). Heading1 lain, misalnya
`DAFTAR GAMBAR` atau `DAFTAR PUSTAKA`, tidak mengubah nomor bab dan tidak
mereset counter.

Counter gambar dan tabel terpisah, dimulai dari 1, dan direset setiap kali
Heading1 `BAB ...` ditemukan. Caption sebelum bab pertama tidak diberi nomor.
Bila dokumen tidak memiliki Heading1 `BAB ...` sama sekali, penomoran caption
dilewati dan peringatan dicetak ke stderr; gambar dan tabel tetap diproses.

### Penggantian prefix

Prefix lama yang cocok dengan pola berikut dihapus lebih dulu:

```regex
^\s*(Gambar|Tabel)\s+\d+(?:\.\d+)?\.?\s*
```

Setelah itu dipasang prefix baru `Gambar <bab>.<n>` atau `Tabel <bab>.<n>`
diikuti satu spasi. Contoh:

| Sebelum | Sesudah |
| --- | --- |
| `Gambar 1. Diagram alur` | `Gambar 1.1 Diagram alur` |
| `Gambar 1.2 Foto hasil` | `Gambar 1.2 Foto hasil` |
| `Tabel 2. Data` (di bab II) | `Tabel 2.1 Data` |

Teks caption lainnya, `w:pStyle`, dan `rPr` setiap run tidak diubah. Prefix
lama yang terpecah ke beberapa run tetap dihapus; prefix baru disisipkan ke
run pertama agar formatting label tidak hilang. Karena prefix lama selalu
dihapus sebelum nomor baru ditulis, menjalankan alat dua kali tidak membuat
nomor dobel.

### Caption yang memuat field

Jika prefix nomor caption memuat field (`w:fldSimple` atau pasangan
`w:fldChar`), caption tersebut **dilewati** dan field dibiarkan utuh. Ini
mencegah field `SEQ` yang rusak atau hasilnya dobel saat Word memperbarui
field. Counter tetap maju agar caption sesudahnya mendapat nomor urut
berikutnya. Jumlah caption yang dilewati dilaporkan sebagai peringatan.

## 2. Gambar

Setiap paragraf yang mengandung `w:drawing`:

- `w:jc` diset `center`;
- `w:spacing/@w:before` dan `@w:after` diset `0` (termasuk `beforeLines`,
  `afterLines`, dan autospacing bila atribut itu ada);
- line spacing, indent, dan properti lain tidak diubah.

Untuk setiap `wp:inline` (dan `wp:anchor` bila ada), lebar efektif
`wp:extent/@cx` dibatasi maksimum **14,0 cm = 5.040.000 EMU**. Bila lebih
besar, `cx` diset tepat 5.040.000 dan `cy` diskalakan dengan rasio yang sama.
`a:ext` di dalam `pic:spPr/a:xfrm` juga diskalakan agar transformasi gambar
tetap sebanding. Gambar yang sudah ≤ 14,0 cm tidak diubah.

## 3. Tabel

Berlaku untuk semua `w:tbl` di body, termasuk tabel bersarang. Tabel kode
1x1 yang dihasilkan `format_code.py` juga memakai border ilmiah yang sama,
tetapi padding atas/bawahnya tetap 108 twip (bukan 0) dan tidak diberi border
bawah header.

### Border

Tabel memakai gaya ilmiah: garis atas/bawah 1 pt, garis bawah header 0,5 pt,
tanpa garis vertikal, dan tanpa garis horizontal antarbaris body.

`w:tblBorders` lama diganti dengan enam border baru:

| Sisi | `w:val` | `w:sz` | `w:color` |
| --- | --- | --- | --- |
| `top` | `single` | `8` | `000000` |
| `left` | `nil` | — | `000000` |
| `bottom` | `single` | `8` | `000000` |
| `right` | `nil` | — | `000000` |
| `insideH` | `nil` | — | `000000` |
| `insideV` | `nil` | — | `000000` |

`w:sz="8"` berarti 1 pt. Elemen border dibuat baru sehingga atribut tema
(`w:themeColor`, `w:themeTint`, dan sejenisnya) dari border lama tidak
tersisa.

### Header tabel

Baris header dideteksi dari `w:tblHeader` pada `w:trPr`. Bila penanda itu
tidak ada, baris pertama tabel multi-baris dianggap header. Pada baris header:

- `w:b` dan `w:bCs` setiap run diset `w:val="0"` agar teks header tidak bold;
- sel header terakhir sebelum body mendapat `w:tcBorders/w:bottom`
  `single`, `w:sz="4"`, `w:color="000000"`.

Border bawah header ditulis per sel agar hanya berlaku di bawah header, bukan
di antara semua baris body.

### Shading

`w:shd` langsung di bawah `w:tblPr`, `w:trPr`, `w:tcPr`, dan `w:tblPrEx`
dihapus. Shading pada `w:rPr` atau `w:pPr` tidak disentuh karena berada di
level run/paragraf, bukan tabel/baris/sel.

### Cell margin

`w:tblCellMar` di `w:tblPr` diset:

| Sisi | Nilai |
| --- | --- |
| `top` | `0` |
| `bottom` | `0` |
| `left` | `108` twip |
| `right` | `108` twip |

Khusus tabel kode 1x1, `top` dan `bottom` juga 108 twip. `w:tcMar` per sel dan
`w:tblCellMar` di `w:tblPrEx` dihapus agar margin tabel
benar-benar berlaku seragam. `w:tcBorders` per sel dan `w:tblBorders` di
`w:tblPrEx` juga dihapus agar tidak menimpa border tabel; satu-satunya
pengecualian adalah border bawah sel header. Isi sel, lebar kolom
(`w:tblGrid`, `w:tcW`), `w:jc` tabel, dan alignment paragraf di dalam sel
tidak diubah.

## Keamanan dan idempotensi

- Hanya `word/document.xml` yang diganti. Header, footer, footnote, style,
  numbering, media, dan relasi disalin apa adanya dari ZIP asli.
- Tidak ada field, `sectPr`, atau bookmark yang dihapus. Caption yang prefix
  nomornya memuat field dilewati (lihat §1).
- Operasi XML memakai elemen yang sudah ada bila mungkin dan menyisipkan
  elemen baru pada urutan schema yang benar.
- Menjalankan alat dua kali menghasilkan `word/document.xml` yang identik
  (sudah diuji), jadi nomor caption tidak dobel dan border/margin tidak
  berubah lagi.

## Keputusan desain dan batasan

1. **Style dipercaya sebagai penanda caption.** Sesuai spesifikasi, semua
   paragraf `ImageCaption`/`TableCaption` dianggap caption tanpa melihat
   polanya. Untuk `Caption` saja, pola awal `Gambar`/`Tabel` dipakai agar
   paragraf bergaya `Caption` yang bukan caption tidak ikut berubah. Karena
   itu alat ini ditujukan untuk DOCX hasil build; dokumen acuan mentah yang
   memakai `TableCaption` untuk teks isi tidak boleh diproses dengan alat ini.
2. **Caption dengan field dilewati, bukan dipaksa menjadi teks literal.**
   Field yang berada di prefix nomor tidak dapat dihapus sebagian tanpa
   merusak struktur field. Melewatinya lebih aman daripada menghasilkan field
   setengah jadi.
3. **Tidak ada Heading1 `BAB ...` berarti tidak ada penomoran.** Caption
   dibiarkan apa adanya; peringatan dilaporkan. Proses gambar dan tabel tetap
   berjalan.
4. **Shading level style tidak diubah.** Yang dihapus hanya `w:shd` langsung
   pada tabel/baris/sel. Mengubah `word/styles.xml` akan berdampak ke seluruh
   dokumen dan berada di luar cakupan alat ini.
5. **`tcBorders`, `tcMar`, dan `tblPrEx` dinormalisasi.** Tanpa menghapus
   override per sel/baris, border dan margin tabel tidak akan seragam.
6. **Gambar anchor ikut diproses.** Meskipun acuan memakai `wp:inline`,
   `wp:anchor` dengan `wp:extent` juga di-clamp agar tidak melewati margin.

## Tes

```bash
.venv/Scripts/python.exe -m pytest tests/test_format_figures.py -q
```

Fixture dibuat ulang di direktori sementara oleh
`tests/fixtures/format_figures/make_fixture.py`; tes tidak bergantung pada
`Laporan.docx` hasil build. Cakupan tes:

1. nomor caption per bab dan reset counter;
2. penghapusan prefix lama serta idempotensi dua kali jalan;
3. clamp gambar 20 cm → 14 cm dengan tinggi proporsional;
4. border ilmiah (atas/bawah 1 pt, vertikal `nil`), border bawah header
   0,5 pt, header tidak bold, tanpa shading, margin sel, serta
   isi/lebar/alignment tetap;
5. dokumen tanpa Heading1 tidak dinomori dan tidak crash;
6. ZIP hasil valid dan dapat dibuka python-docx;
7. part selain `document.xml` tidak berubah;
8. bookmark, field, caption `Caption` generik, dan caption ber-field tetap
   aman.
