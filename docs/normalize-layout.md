# Normalisasi Layout Paragraf (`normalize_layout.py`)

`tools/normalize_layout.py` menyeragamkan layout paragraf DOCX hasil build:
spasi sebelum/sesudah paragraf menjadi 0, jarak antarbaris 1,5, dan paragraf
dirata kanan-kiri (justify).

Alat ini hanya menulis ulang `word/document.xml`. Semua part lain (styles,
numbering, header, footer, media, relasi, dan properti dokumen) disalin
byte-per-byte dari DOCX asli.

## Alasan

Pandoc dan `reference.docx` tidak selalu menghasilkan paragraf yang konsisten.
Paragraf body dapat memakai spacing 1,0, perataan kiri, serta spacing
`before`/`after` dari style atau direct formatting. Untuk laporan tugas,
variasi itu mengganggu keseragaman halaman dan tampilan daftar isi.

Menetapkan properti langsung di setiap paragraf lebih aman daripada mengubah
`styles.xml`:

- style yang dipakai bersama (mis. `Normal`, `BodyText`, `Compact`) tidak
  berubah untuk keperluan lain;
- paragraf yang dikecualikan tetap mempertahankan format aslinya;
- teks, run, style, section, field, dan bookmark tidak tersentuh.

## Pemakaian

```bash
python tools/normalize_layout.py --docx input.docx --out output.docx
```

`--out` boleh menunjuk file yang sama dengan `--docx`. Penulisan dilakukan
lewat file sementara lalu `os.replace`, sehingga input tidak rusak bila proses
gagal di tengah jalan.

Kode keluar `0` bila dokumen berhasil diproses. Kesalahan input (file tidak
ada, bukan DOCX/ZIP valid, `word/document.xml` tidak ada, XML tidak valid, atau
file tidak dapat ditulis) menghasilkan kode keluar `1` dan pesan di stderr.

Ringkasan yang dicetak mencakup jumlah paragraf yang diperiksa,
dinormalisasi, sudah sesuai, serta yang dilewati karena style atau field.

## Aturan normalisasi

Untuk setiap paragraf body dan sel tabel yang **tidak** masuk pengecualian:

| Properti | Nilai |
| --- | --- |
| `w:spacing/@w:before` | `0` |
| `w:spacing/@w:after` | `0` |
| `w:spacing/@w:line` | `360` |
| `w:spacing/@w:lineRule` | `auto` |
| `w:jc/@w:val` | `both` |

`w:line="360"` dengan `w:lineRule="auto"` sama dengan 1,5 baris
(1,5 × 240 twip).

Direct formatting lama ditimpa, bukan ditambahkan sebagai elemen kedua:

- `w:spacing` dan `w:jc` yang sudah ada dipakai ulang dan nilainya diganti;
- bila belum ada, elemen baru disisipkan pada urutan `w:pPr` yang benar
  (`w:spacing` sebelum `w:ind`/`w:jc`, `w:jc` sebelum `w:rPr`/`w:sectPr`);
- atribut `w:beforeLines`, `w:afterLines`, `w:beforeAutospacing`, dan
  `w:afterAutospacing` dihapus karena dapat menimpa `before`/`after`;
- atribut lain pada `w:spacing` maupun `w:jc` tidak ditambahkan.

Paragraf di dalam text box tidak diproses karena bukan bagian alur body atau
sel tabel. Header, footer, dan footnote juga tidak diproses karena berada di
part XML lain.

## Pengecualian

Paragraf berikut tidak diubah sama sekali, termasuk `w:pPr`-nya:

| Kelompok | Style / kondisi |
| --- | --- |
| Blok kode | `Source Code`, `Verbatim Char`, `HTML Code`, `HTML Preformatted` |
| Caption | `ImageCaption`, `TableCaption` |
| Gambar | `Figure`, `CaptionedFigure`, `FigureCaption` |
| Daftar isi | `TOC1`–`TOC9`, `TOCHeading` |
| Cover | style yang diawali `Cover` (mis. `CoverTitle`, `CoverName`) |
| Judul | `Title` |
| Field | paragraf yang memuat field `TOC`, `PAGEREF`, atau `SEQ` |

Perbandingan style memakai `w:pStyle/@w:val` yang dinormalisasi: huruf kecil,
tanpa spasi, tanda hubung, atau garis bawah. Karena itu `SourceCode`,
`Source Code`, dan `source_code` dianggap sama. `TOC1`–`TOC9` dicocokkan
persis setelah normalisasi, sedangkan `Cover*` memakai awalan `cover`.

Deteksi field mencakup dua bentuk OOXML:

- field sederhana `w:fldSimple/@w:instr`;
- field kompleks yang ditandai `w:fldChar` (`begin`/`separate`/`end`) dengan
  instruksi di `w:instrText`, termasuk instruksi yang terpecah ke beberapa
  run.

Nama field diambil dari kata pertama instruksi dan dibandingkan tanpa peka
huruf besar/kecil. Jika satu paragraf memuat salah satu field di atas,
seluruh paragraf dilewati. Field `PAGE`, `REF`, `HYPERLINK`, dan field lain di
luar daftar tidak membuat paragraf dikecualikan, sehingga layoutnya tetap
dinormalisasi.

Pengecualian ini mencegah hal berikut:

- blok kode ikut justify dan berjarak 1,5 baris;
- caption kehilangan format khusus dan nomor `SEQ`-nya;
- paragraf gambar kehilangan posisi center dan spasi 0/0 dari
  `format_figures.py`;
- entri TOC berubah sebelum Word memperbarui field;
- halaman cover dan judul ikut dijustify;
- field TOC/PAGEREF/SEQ rusak atau berubah saat dokumen dibuka Word.

## Idempotensi

Menjalankan alat dua kali menghasilkan `word/document.xml` yang identik.
Setelah run pertama, semua paragraf sasaran sudah memiliki nilai yang sama;
run kedua tidak menambah elemen atau atribut baru. Karena itu alat aman
dipanggil ulang pada DOCX yang sudah dinormalisasi.

## Posisi di pipeline

Tahap ini dimaksudkan berjalan **setelah `tools/format_figures.py`** dan
**sebelum `tools/add_paragraph_ids.py`**:

```text
... finalize DOCX
    -> format_figures.py   (caption, gambar, tabel)
    -> normalize_layout.py (spacing 1,5 dan justify)
    -> ... istilah/pagenum
    -> add_paragraph_ids.py (bookmark pNNNN + manifest)
```

Alasannya:

- `format_figures.py` sudah menyelesaikan caption, gambar, dan tabel; alat ini
  tidak perlu menebak paragraf mana yang caption karena style-nya sudah final.
- `add_paragraph_ids.py` membaca struktur paragraf dan menaruh bookmark
  setelah `w:pPr`. Menjalankan normalisasi sesudahnya akan mengubah `w:pPr`
  tetapi tidak boleh menggeser bookmark; menjalankannya sebelum lebih aman dan
  menjaga urutan tahap pascaproses tetap sederhana.
- Normalisasi tidak menyentuh field, jadi finalisasi nomor halaman/TOC tetap
  dapat dilakukan sebelum atau sesudahnya tanpa mengubah hasil layout.

Saat ini `build-docx.sh` belum memanggil alat ini secara otomatis; pemanggilan
manual di atas dapat dipakai untuk mencoba atau mengulang tahap normalisasi.

## Tes

```bash
.venv/Scripts/python.exe -m pytest tests/test_normalize_layout.py -q
```

Di Linux/macOS gunakan `.venv/bin/python`. Fixture DOCX dibuat di dalam tes
(tidak disimpan di `tests/fixtures`), sehingga tes tidak bergantung pada file
biner tambahan. Cakupan tes: paragraf Normal, blok kode, caption, paragraf
gambar (`Figure`, `CaptionedFigure`, `FigureCaption`), sel tabel, field
TOC/PAGEREF/SEQ, field biasa, idempotensi, validitas ZIP, pembukaan dengan
`python-docx`, serta tidak berubahnya teks/run/style/section/field/bookmark
dan part selain `word/document.xml`.
