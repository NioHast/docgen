# Formatter Blok Kode (`format_code.py`)

Alat ini mengubah blok kode pada DOCX hasil build menjadi **tabel 1x1
bergaris**. Pandoc menulis blok kode sebagai paragraf polos berstyle
`Source Code`; tanpa tabel, batas blok kode tidak terlihat di Word dan kode
mudah menyatu secara visual dengan paragraf sekitarnya.

Hanya `word/document.xml` yang ditulis ulang. Part lain (header, footer, style,
numbering, media, relasi, dan section) disalin byte-per-byte dari DOCX asli.

## Pemakaian

```bash
python tools/format_code.py --docx input.docx --out output.docx
```

`--out` boleh menunjuk file yang sama dengan `--docx`. Penulisan dilakukan lewat
file sementara lalu `os.replace`, sehingga input tidak rusak bila proses gagal
di tengah jalan.

Keluaran CLI memuat jumlah blok kode yang menjadi tabel, jumlah paragraf kode
yang digabung, dan jumlah baris kode di dalam sel. Kode keluar `0` selama
dokumen berhasil diproses, termasuk ketika tidak ada blok kode. Kesalahan input
(bukan DOCX/ZIP, `word/document.xml` tidak ada, atau file tidak dapat ditulis)
menghasilkan kode keluar `1`.

## Posisi di pipeline

Jalankan alat ini **setelah `normalize_layout.py`**:

```text
pandoc + docx.lua
  -> scripts/finalize-docx.py
  -> normalize_layout.py
  -> tools/format_code.py
  -> ...
```

`normalize_layout.py` merapikan layout paragraf lebih dulu; `format_code.py`
bekerja pada paragraf `Source Code` yang sudah stabil, lalu menggantinya dengan
tabel. Alat ini tidak mengubah isi paragraf biasa dan tidak bergantung pada
caption, nomor halaman, atau daftar isi.

## Deteksi blok kode

Paragraf dianggap bagian blok kode bila **style paragrafnya** (`w:pStyle`)
cocok dengan salah satu nama berikut:

- `Source Code`
- `Verbatim Char`
- `HTML Code`
- `HTML Preformatted`

Perbandingan `styleId` tidak peka huruf besar/kecil, spasi, garis bawah, atau
tanda hubung. Jadi `SourceCode`, `Source Code`, `source_code`, dan
`HTMLPreformatted` diperlakukan sama.

Beberapa paragraf yang berurutan dan semuanya berstyle kode digabung menjadi
**satu** tabel. Deretan berhenti pada paragraf non-kode, tabel, atau elemen
blok lain. Penanda bookmark/comment di level body tidak memutus deretan.

Pandoc biasanya menulis satu blok kode sebagai satu paragraf dengan
`<w:br/>` antarbaris. Formatter ini memecah `<w:br/>`/`<w:cr>` menjadi baris
terpisah, dan juga menggabungkan beberapa paragraf kode berurutan. Setiap baris
kode menjadi satu paragraf di dalam sel.

## Bentuk tabel

Tabel yang dihasilkan selalu 1 baris x 1 kolom:

| Properti | Nilai |
| --- | --- |
| Lebar tabel | 100% lebar konten (`w:tblW` `w:type="pct"`, `w:w="5000"`) |
| Border atas/bawah/kiri/kanan | `single`, `w:sz="4"` (0,5 pt), `w:color="000000"` |
| Cell margin atas/bawah | 108 twip (`w:type="dxa"`) |
| Cell margin kiri/kanan | 108 twip (`w:type="dxa"`) |
| Shading | tidak ada (`w:shd` tidak ditulis) |
| Numbering/bullet | tidak ada (`w:numPr` tidak ditulis) |

Cell margin ditulis di `w:tblCellMar` dan `w:tcMar` agar nilai yang sama tetap
berlaku bila tabel disalin ke dokumen lain. `w:gridCol` dan `w:tcW` dihitung
dari lebar halaman dikurangi margin kiri/kanan section; lebar tampilan tetap
mengikuti 100% lebar konten.

## Format isi sel

Setiap paragraf kode di dalam sel memakai format langsung berikut, sehingga
tidak bergantung pada definisi style di `styles.xml`:

- font **Courier New 10 pt** (`w:sz="20"` dan `w:szCs="20"`)
- warna **hitam** (`w:color w:val="000000"`)
- **tidak bold** dan **tidak italic** (`w:b`, `w:bCs`, `w:i`, `w:iCs` = `0`)
- line spacing **1,0** (`w:line="240"`, `w:lineRule="auto"`)
- spasi sebelum/sesudah **0** (`w:before="0"`, `w:after="0"`)
- indentasi paragraf kiri/kanan/first-line **0**
- indentasi spasi dipertahankan: setiap `w:t` diberi
  `xml:space="preserve"`, dan tab dipertahankan sebagai `<w:tab/>`

Style paragraf asal (mis. `SourceCode`) tetap dipertahankan pada paragraf di
dalam sel agar struktur dokumen tetap terbaca. Format langsung di atas
mengalahkan properti yang diwarisi dari style.

## Kode inline tidak diubah

Alat ini hanya melihat **style paragraf**. Run dengan gaya karakter
`Verbatim Char` di tengah paragraf biasa (kode inline) tidak disentuh, baik teks
maupun `rPr`-nya. Konversi tabel hanya terjadi bila seluruh paragraf berstyle
kode.

## Idempoten

Setelah dijalankan sekali, paragraf kode sudah berada di dalam sel tabel,
bukan lagi di level body. Menjalankan alat untuk kedua kalinya tidak menemukan
blok kode baru, sehingga tidak membuat tabel ganda dan tidak mengubah
`word/document.xml`. Hasilnya byte-identik dengan hasil pertama.

## Keamanan struktur

- **Bookmark** (`w:bookmarkStart`/`w:bookmarkEnd`) di dalam paragraf kode ikut
  dipindahkan ke paragraf sel yang sesuai; `w:id` dan `w:name` tidak berubah.
- **Field**, **section break** (`w:sectPr`), **objek/gambar**, dan **perubahan
  terlacak** (`w:ins`/`w:del`) tidak direkonstruksi. Paragraf kode yang memuat
  elemen tersebut **dilewati** dan dibiarkan utuh; alat mencetak peringatan ke
  stderr. Paragraf itu juga menjadi batas deretan blok kode.
- **Section** di akhir body dan section break pada paragraf lain tidak
  tersentuh.
- Seluruh part ZIP selain `word/document.xml` disalin tanpa parsing ulang.

## Batasan

- Hanya paragraf kode di level body yang dikonversi. Blok kode di dalam sel
  tabel lain, text box, atau content control tidak diubah.
- Deteksi memakai style paragraf; paragraf yang mewarisi style kode secara
  tidak langsung (mis. style turunan tanpa `w:pStyle` kode) tidak dikenali.
- Syntax highlighting dari Pandoc dibuang karena semua teks dipaksa hitam
  dengan format langsung. Ini disengaja agar tampilan kode seragam.
- Alat tidak memberi caption, nomor kode, atau daftar kode.
- Paragraf kode yang memuat field/section/objek/perubahan terlacak dilewati
  (lihat bagian Keamanan struktur), sehingga blok tersebut tetap berupa
  paragraf polos.
