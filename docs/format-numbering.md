# Format Numbering Daftar (`format_numbering.py`)

`tools/format_numbering.py` menyeragamkan daftar bernomor pada DOCX hasil
Pandoc untuk tiga format Markdown:

| Markdown | Format DOCX | Tampilan |
| --- | --- | --- |
| `1. item` | `w:numFmt="decimal"`, `w:lvlText="%1."` | `1.` |
| `a. item` | `w:numFmt="lowerLetter"`, `w:lvlText="%1."` | `a.` |
| `a) item` | `w:numFmt="lowerLetter"`, `w:lvlText="%1)"` | `a)` |

Alat ini **tidak** memilih format dari teks paragraf. Format tetap ditentukan
oleh sintaks Markdown dan dipetakan oleh Pandoc; alat hanya merapikan
indentasi, tab stop, dan bold.

## Hasil probe Pandoc 3.13

Probe dijalankan dengan `pandoc 3.13` (Lua 5.4) pada Markdown berikut:

```markdown
1. Langkah satu
2. Langkah dua

a. Enumerasi satu
b. Enumerasi dua

a) Sub-poin satu
b) Sub-poin dua
```

Pandoc sudah menghasilkan format yang benar. Ketiga daftar memakai
`abstractNum` dan `numId` terpisah:

| Markdown | `w:numFmt` | `w:lvlText` |
| --- | --- | --- |
| `1.` | `decimal` | `%1.` |
| `a.` | `lowerLetter` | `%1.` |
| `a)` | `lowerLetter` | `%1)` |

Masalahnya ada pada indentasi. Sebelum diproses, level 0 ditulis Pandoc
sebagai:

```xml
<w:lvl w:ilvl="0">
  <w:start w:val="1"/>
  <w:numFmt w:val="decimal"/>
  <w:lvlText w:val="%1."/>
  <w:lvlJc w:val="left"/>
  <w:pPr>
    <w:ind w:left="720" w:hanging="360"/>
  </w:pPr>
</w:lvl>
```

`document.xml` tidak memiliki `w:ind` langsung; indentasi hanya diwarisi dari
level numbering:

```xml
<w:p>
  <w:pPr>
    <w:pStyle w:val="Compact"/>
    <w:numPr>
      <w:ilvl w:val="0"/>
      <w:numId w:val="1001"/>
    </w:numPr>
  </w:pPr>
  <w:r><w:t>Langkah satu</w:t></w:r>
</w:p>
```

Setelah `format_numbering.py`:

```xml
<w:lvl w:ilvl="0">
  <w:start w:val="1"/>
  <w:numFmt w:val="decimal"/>
  <w:suff w:val="tab"/>
  <w:lvlText w:val="%1."/>
  <w:lvlJc w:val="left"/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="left" w:pos="720"/>
    </w:tabs>
    <w:ind w:left="720" w:hanging="720"/>
  </w:pPr>
</w:lvl>
```

```xml
<w:p>
  <w:pPr>
    <w:pStyle w:val="Compact"/>
    <w:numPr>
      <w:ilvl w:val="0"/>
      <w:numId w:val="1001"/>
    </w:numPr>
    <w:tabs>
      <w:tab w:val="left" w:pos="720"/>
    </w:tabs>
    <w:ind w:left="720" w:hanging="720"/>
  </w:pPr>
  <w:r><w:t>Langkah satu</w:t></w:r>
</w:p>
```

Perubahan pada `document.xml` kecil: `w:pStyle` dan `w:numPr` tidak berubah,
hanya ditambah `w:tabs` dan `w:ind`. Format numbering tidak disentuh.

## Aturan normalisasi

Untuk setiap paragraf yang memiliki `w:numPr` dan level numbering berformat
`decimal` atau `lowerLetter`:

| Properti | Nilai |
| --- | --- |
| `w:ind/@w:left` | `720 × (ilvl + 1)` |
| `w:ind/@w:hanging` | `720` |
| `w:tabs/w:tab/@w:val` | `left` |
| `w:tabs/w:tab/@w:pos` | sama dengan `w:ind/@w:left` |
| `w:suff/@w:val` (level numbering) | `tab` |
| `w:b`, `w:bCs` pada run list | dihapus |

Untuk level teratas (`ilvl=0`) hasilnya adalah indent efektif 720 twip,
hanging 720 twip, dan tab stop 720 twip. Dengan hanging 720, nomor dimulai di
margin kiri, tab membawa teks ke posisi 720, sehingga jarak nomor ke teks
selalu satu tab.

Level yang lebih dalam mengikuti pola yang sama:

| `ilvl` | `w:left` | `w:hanging` | Tab stop |
| --- | --- | --- | --- |
| 0 | 720 | 720 | 720 |
| 1 | 1440 | 720 | 1440 |
| 2 | 2160 | 720 | 2160 |

Atribut indent lama yang dapat menimpa nilai baru (`w:firstLine`,
`w:firstLineChars`, `w:hangingChars`, `w:leftChars`, `w:start`,
`w:startChars`) dihapus dari `w:ind`.

Bold dihapus dari seluruh run paragraf list, termasuk bold pada teks isi.
Paragraf non-list tidak disentuh, jadi bold di luar daftar tetap
dipertahankan. Daftar bullet dan format numbering lain (misalnya
`upperRoman`) juga tidak diubah.

## Kapan memakai tiap format

### `1.` untuk langkah prosedur

Pakai angka Arab bertitik untuk urutan yang wajib diikuti atau memiliki
kronologi: langkah kerja, tahapan penelitian, prosedur pengujian, dan
instruksi.

```markdown
1. Siapkan berkas Markdown.
2. Jalankan build DOCX.
3. Periksa hasil di Word.
```

### `a.` untuk enumerasi

Pakai huruf kecil bertitik untuk rincian yang setara dan tidak menekankan
urutan: faktor, komponen, pertimbangan, atau daftar pilihan. Format ini
menjadi alternatif formal dari bullet.

```markdown
Komponen yang diuji meliputi:

a. metadata dokumen;
b. format sitasi;
c. penomoran halaman.
```

### `a)` untuk sub-poin

Pakai huruf kecil dengan tanda kurung tutup untuk turunan dari `1.` atau
`a.`. Format ini memberi kedalaman kedua tanpa kembali memakai angka Arab.

```markdown
1. Siapkan lingkungan build.
   a. Pasang Pandoc.
   b. Pasang dependensi Python.
2. Jalankan build.
   a) Build DOCX;
   b) Build PDF.
```

Hindari memakai `a)` sebagai daftar tingkat pertama bila dokumen juga
memakai `a.`; keduanya sama-sama `lowerLetter` dan hanya berbeda pada
`w:lvlText`, sehingga pembaca bisa bingung membedakan tingkatannya.

## Pemakaian

```bash
python tools/format_numbering.py --docx input.docx --out output.docx
```

`--out` boleh menunjuk file yang sama dengan `--docx`. Penulisan memakai file
sementara lalu `os.replace`, sehingga input tidak rusak bila proses gagal.

Keluaran CLI memuat jumlah paragraf list yang diperiksa, paragraf yang
dirapikan, level numbering yang dirapikan, elemen bold yang dihapus, dan
sebaran format yang dikenali.

Kode keluar `0` bila dokumen berhasil diproses. Kesalahan input (file tidak
ada, bukan DOCX/ZIP valid, `word/document.xml` tidak ada, XML tidak valid,
atau file tidak dapat ditulis) menghasilkan kode keluar `1` dan pesan di
stderr.

## Batasan

- Hanya `word/document.xml` dan `word/numbering.xml` yang ditulis ulang.
  Part lain (styles, header, footer, media, relasi) disalin byte-per-byte.
- Format numbering tidak diubah. Bila Pandoc kelak memetakan `1.`, `a.`, atau
  `a)` secara berbeda, perbaikan harus dilakukan di sumber Markdown atau di
  tahap pemetaan, bukan di alat ini.
- Paragraf dengan `w:numId` bernilai `0` dianggap bukan list dan tidak
  disentuh.
- Paragraf list yang tidak memiliki definisi numbering lengkap tetap
  dirapikan indentasinya, tetapi `w:suff` tidak dapat ditetapkan.
- Alat ini idempoten: menjalankan dua kali menghasilkan part XML yang sama.
- `build-docx.sh` belum memanggil alat ini; pada perubahan ini alat
  disediakan sebagai post-process mandiri agar berkas build tidak berubah.

## Verifikasi

```bash
pytest tests/test_format_numbering.py -q
```

Tes mencakup tiga format, indent/hanging/tab stop 720, idempotensi, paragraf
non-list yang tidak berubah, penghapusan bold pada list, bullet yang tidak
disentuh, dan integrasi Pandoc untuk ketiga sintaks Markdown.
