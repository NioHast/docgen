# Penomoran Persamaan DOCX (`format_equations.py`)

`tools/format_equations.py` memberi nomor persamaan display OMML pada DOCX
hasil build sesuai panduan MSI: nomor `(bab.n)` di tepi kanan, persamaan
menjorok dua tabulasi, dan jarak dua kali jarak baris. Alat ini hanya menulis
ulang `word/document.xml`; seluruh part lain (header, footer, style,
numbering, media, relasi, dan section) disalin byte-per-byte dari DOCX asli.

## Pemakaian

```bash
python tools/format_equations.py --docx input.docx --out output.docx
```

`--out` boleh menunjuk file yang sama dengan `--docx`. Penulisan dilakukan
lewat file sementara lalu `os.replace`, sehingga input tidak rusak bila proses
gagal di tengah jalan.

Keluaran CLI memuat jumlah persamaan display yang ditemukan, jumlah yang
diberi nomor, dan jumlah bab yang terdeteksi. Kode keluar `0` selama dokumen
berhasil diproses, termasuk ketika tidak ada persamaan atau tidak ada Heading1.
Kesalahan input (bukan DOCX/ZIP, `word/document.xml` tidak ada, XML tidak
valid, atau file tidak dapat ditulis) menghasilkan kode keluar `1`.

## Posisi di pipeline

Alat ini dijalankan **setelah `tools/normalize_layout.py`** dan
`tools/format_code.py`:

```text
pandoc + docx.lua
  -> scripts/finalize-docx.py
  -> ...
  -> normalize_layout.py (spasi 1,5 dan justify)
  -> format_code.py      (blok kode menjadi tabel)
  -> format_equations.py (nomor persamaan OMML)
  -> ...
```

Alasannya: `normalize_layout.py` menyetel ulang `w:spacing` dan `w:jc` pada
paragraf biasa. Dengan menjalankan `format_equations.py` sesudahnya, nilai
spacing 360 twip dan `w:jc="left"` untuk paragraf persamaan tidak ditimpa.
`format_code.py` tidak menyentuh paragraf persamaan, sehingga struktur OMML
tetap stabil saat alat ini bekerja.

## Deteksi persamaan

Paragraf dianggap persamaan display bila memiliki anak langsung
`m:oMathPara`. Persamaan inline (`m:oMath` di tengah teks tanpa
`m:oMathPara`) tidak diberi nomor. Paragraf di dalam text box dilewati.

Isi OMML **tidak diubah**. Nomor ditulis sebagai run `w:r` biasa setelah
`m:oMathPara`, bukan sebagai `m:t`, sehingga tidak menjadi bagian dari objek
equation dan tidak merusak struktur matematika.

## Nomor bab dan counter

Nomor bab diambil dari Heading1 terakhir yang teksnya cocok dengan:

```text
BAB <romawi/arab>
```

Contoh yang diterima: `BAB I PENDAHULUAN`, `BAB IV`, `BAB 2`, `BAB III.`.
Romawi dikonversi ke arab (I → 1, IV → 4, XII → 12). Heading1 lain, misalnya
`DAFTAR PERSAMAAN` atau `DAFTAR PUSTAKA`, tidak mengubah nomor bab dan tidak
mereset counter.

Counter persamaan dimulai dari 1, direset setiap kali Heading1 `BAB ...`
ditemukan, dan bertambah untuk setiap paragraf `m:oMathPara`. Nomor ditulis
sebagai `(bab.n)`:

| Posisi | Nomor |
| --- | --- |
| Persamaan pertama di BAB I | `(1.1)` |
| Persamaan kedua di BAB I | `(1.2)` |
| Persamaan pertama di BAB II | `(2.1)` |

Persamaan sebelum Heading1 `BAB ...` pertama tidak diberi nomor. Bila dokumen
tidak memiliki Heading1 `BAB ...` sama sekali, seluruh penomoran dilewati dan
peringatan dicetak ke stderr; dokumen tetap diproses tanpa crash.

Paragraf persamaan yang memuat field dilewati (lihat bagian Keamanan), tetapi
tetap menempati urutan counter agar nomor persamaan berikutnya sesuai posisi
di dokumen.

## Format paragraf persamaan

Untuk setiap paragraf yang diberi nomor:

| Properti | Nilai |
| --- | --- |
| Tab stop kanan | `w:tabs/w:tab @w:val="right"`, `@w:pos` = lebar area teks |
| Indentasi kiri | `w:ind @w:left="1440"` (dua tab default) |
| Indentasi baris pertama | `w:ind @w:firstLine="0"` |
| Perataan | `w:jc @w:val="left"` |
| Spasi sebelum | `w:spacing @w:before="360"` |
| Spasi sesudah | `w:spacing @w:after="360"` |
| Run nomor | `w:r` berisi `w:tab` lalu `w:t` `(bab.n)` |

`w:pos` pada tab stop diukur dari margin kiri, bukan dari indentasi paragraf.
Karena itu tab kanan dipasang pada lebar area teks, sehingga ujung kanan nomor
berada tepat di tepi kanan area teks. Lebar area teks dihitung dari `sectPr`
terakhir:

```text
lebar halaman - margin kiri - margin kanan - gutter
```

Bila geometri section tidak terbaca, alat memakai fallback **9072 twip**
(16,0 cm). Untuk A4 dengan margin 4/3 cm, lebar area teks adalah 7937 twip,
sehingga tab stop kanan berada di 7937 twip.

Indentasi baris pertama dinolkan karena `Normal` pada laporan memakai
first-line indent 1,25 cm. Tanpa penyetelan ke nol itu, persamaan akan mulai
lebih dari dua tab dari margin.

Perataan paragraf diset `left`, bukan `both`. Justify membuat Word
meregangkan baris persamaan dan dapat menggeser posisi tab kanan serta nomor
`(bab.n)`. Dengan `left`, tab kanan tetap mengunci nomor di tepi kanan area
teks.

### Mengapa spacing 360 twip

Spasi baris body adalah 1,5 baris = 360 twip. Panduan meminta jarak persamaan
dan teks **dua kali jarak baris**. Nilai yang dipakai di sini adalah 360 twip
sebelum dan 360 twip sesudah; totalnya 720 twip = 2 × 360 twip. Dengan begitu
satu persamaan dikelilingi total dua jarak baris, sesuai permintaan tugas dan
tetap mudah diperiksa di XML. Nilai 360 dipakai eksplisit, bukan 720 di
masing-masing sisi.

## Idempotensi

Menjalankan alat dua kali tidak menambah nomor ganda:

- tab kanan pada posisi yang sama dihapus lalu ditulis ulang sebagai satu tab;
- `w:spacing` dan `w:ind` yang sudah ada dipakai ulang dan nilainya disetel
  sama;
- run nomor lama setelah persamaan dikenali lewat pola `(angka.angka)`,
  dibangun ulang dengan nomor yang benar, dan duplikatnya dihapus.

Setelah run pertama, `word/document.xml` pada run kedua identik dengan hasil
run pertama.

## Keamanan struktur

- Hanya `word/document.xml` yang diganti. Header, footer, footnote, style,
  numbering, media, dan relasi disalin apa adanya dari ZIP asli.
- `m:oMathPara`, `m:oMath`, dan seluruh `m:t` tidak diubah.
- **Field** (`w:fldChar`, `w:instrText`, `w:fldSimple`) tidak dipindahkan atau
  dihapus. Paragraf persamaan yang memuat field **dilewati seluruhnya** dan
  dilaporkan sebagai peringatan; counter tetap maju.
- **Bookmark** (`w:bookmarkStart`/`w:bookmarkEnd`) tidak dihapus. Run nomor
  disisipkan setelah `m:oMathPara`; bookmark yang mengapit persamaan tetap
  valid.
- **Section properties** (`w:sectPr`) tidak disentuh. Elemen baru pada
  `w:pPr` disisipkan mengikuti urutan schema (`w:tabs` → `w:spacing` →
  `w:ind`), sehingga `w:sectPr` dan `w:rPr` tetap pada posisinya.
- Perubahan terlacak tidak direkonstruksi; persamaan yang dibungkus `w:ins`
  atau `w:del` tidak dikenali sebagai anak langsung paragraf dan tidak
  dinomori.

## Batasan

1. **Hanya persamaan display dengan `m:oMathPara` sebagai anak langsung
   `w:p`.** Persamaan di dalam text box, atau `m:oMathPara` yang dibungkus
   tracked change (`w:ins`/`w:del`) sehingga bukan anak langsung paragraf,
   tidak diproses.
2. **Satu nomor per paragraf.** Bila satu paragraf memuat lebih dari satu
   `m:oMathPara`, nomor dipasang sekali setelah persamaan terakhir.
3. **Variabel italic tidak ditulis ulang.** Alat tidak mengubah OMML. Huruf
   miring variabel berasal dari mesin matematika Word atau authoring equation,
   bukan dari pascaproses ini.
4. **Field membuat paragraf dilewati.** Ini mencegah field `SEQ` atau field
   lain rusak. Konsekuensinya persamaan tersebut tidak mendapat nomor teks.
5. **Lebar tab mengikuti section terakhir.** Dokumen dengan beberapa section
   yang lebarnya berbeda tetap memakai satu nilai tab stop dari `sectPr`
   terakhir.
6. **Urutan pipeline wajib `normalize_layout.py` → `format_equations.py`.**
   Bila `normalize_layout.py` dijalankan lagi setelah alat ini, paragraf
   persamaan akan kembali mendapat `w:spacing @w:before/@w:after="0"` dan
   `w:jc="both"` karena belum dikecualikan oleh `normalize_layout.py`.
7. **Nomor yang sudah ada sebagai teks biasa dapat diganti.** Run setelah
   persamaan yang isinya persis `(angka.angka)` dianggap run nomor dan
   diperbarui. Teks lain tidak disentuh.
8. **Persamaan di dalam sel tabel memakai lebar section.** Tab stop dihitung
   dari geometri halaman, bukan lebar sel, sehingga persamaan display di dalam
   sel yang sempit dapat memerlukan penyesuaian manual.

## Tes

```bash
.venv/Scripts/python.exe -m pytest tests/test_format_equations.py -q
```

Fixture dibuat di direktori sementara oleh `tests/test_format_equations.py`
(tidak bergantung pada `Laporan.docx` hasil build). Cakupan tes:

1. dua bab, tiga persamaan → `(1.1)`, `(1.2)`, `(2.1)` dengan reset counter;
2. nomor berada di run terpisah, bukan di dalam OMML;
3. idempotensi: run kedua menghasilkan `word/document.xml` yang identik;
4. tanpa Heading1: tidak menomori, tidak crash, dan `pPr` tidak diubah;
5. spacing sebelum/sesudah 360 twip, indent kiri 1440 twip, tab kanan pada
   9072 twip sesuai lebar konten fixture, tab kanan 7937 twip pada A4
   bermargin 4/3 cm, serta fallback 9072 twip bila `sectPr` tidak terbaca;
6. ZIP hasil valid, dapat dibuka `python-docx`, dan part selain
   `document.xml` tidak berubah;
7. field, bookmark, dan `sectPr` tetap aman; persamaan ber-field dilewati
   dengan counter tetap maju;
8. urutan `normalize_layout.py` → `format_equations.py`: setelah normalisasi,
   `w:jc` menjadi `left` dan spacing 360 twip tidak berubah.
