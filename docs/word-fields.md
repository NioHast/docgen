# Field DOCX dan Nomor Halaman Daftar Isi

Dokumen ini menjelaskan mengapa daftar isi (TOC) pada `Laporan.docx` bisa
menampilkan nomor halaman `0`, kapan harus menjalankan `make finalize-word`,
dan batasan langkah tersebut.

## Ringkasan

Nomor halaman daftar isi di DOCX bukan teks biasa. Pandoc menulis field
`PAGEREF` di dalam field `TOC`, dan setiap `PAGEREF` menyimpan **nilai cache**
(nilai terakhir yang dihitung Word). Saat DOCX dibuat, belum ada mesin tata
letak yang tahu nomor halaman final, sehingga cache tersebut diisi `0` atau
nilai sementara.

Pipeline build sudah mencoba mengisi cache itu lewat
`scripts/docx-pagenum.py`, tetapi skrip tersebut membutuhkan LibreOffice
(`soffice`) dan `pdftotext`. Bila keduanya tidak tersedia, atau render
LibreOffice gagal/timeout, skrip hanya menyalin DOCX apa adanya. Hasilnya,
daftar isi tetap menampilkan `0` walaupun isi dokumen sudah benar.

`make finalize-word` menyelesaikan masalah itu dengan membuka DOCX langsung di
Microsoft Word, meminta Word memperbarui seluruh field dan daftar isi, lalu
menyimpannya kembali. Setelah langkah ini, nilai cache `PAGEREF` di dalam file
sudah berisi nomor halaman sebenarnya, bukan `0`.

## Mengapa TOC bisa berisi 0

Alur build DOCX secara ringkas:

```text
chapters/*.md
    │
    ▼
pandoc + docx.lua + reference.docx
    │
    ▼
Laporan.docx
    │
    ├── scripts/finalize-docx.py   (section, page numbering)
    ├── tools/format_figures.py    (caption, gambar, tabel)
    ├── tools/istilah.py           (konsistensi istilah)
    └── scripts/docx-pagenum.py    (cache PAGEREF via LibreOffice)
    │
    ▼
Laporan.docx final
```

Pandoc menghasilkan field TOC seperti ini (disederhanakan):

```xml
<w:instrText> TOC \o "1-3" \h \z \u </w:instrText>
...
<w:instrText> PAGEREF _Toc123456 \h </w:instrText>
<w:fldChar w:fldCharType="separate"/>
<w:t>0</w:t>
```

Angka `0` adalah nilai cache. Word akan menampilkannya sampai field
diperbarui. `scripts/docx-pagenum.py` mengisi nilai itu dengan cara:

1. Merender DOCX ke PDF memakai `soffice --headless`.
2. Membaca teks tiap halaman dengan `pdftotext`.
3. Mencocokkan heading dengan nomor halaman di footer.
4. Menulis ulang nilai cache `PAGEREF` di `word/document.xml`.

Bila langkah 1 atau 2 tidak bisa dijalankan, skrip mencetak peringatan dan
membiarkan cache bernilai `0`. Ini yang terjadi pada mesin tanpa LibreOffice.

### Peran `updateFields`

`word/settings.xml` biasanya berisi:

```xml
<w:updateFields w:val="true"/>
```

Dengan pengaturan itu, Word akan memperbarui field saat dokumen dibuka. Namun
`updateFields` bukan solusi untuk semua keadaan:

- file di disk masih berisi `0` sampai ada aplikasi yang menyimpan ulang;
- pembaca selain Word (misalnya konverter DOCX ke PDF, preview, atau pipeline
  CI) dapat menampilkan nilai cache `0`;
- hasil build tidak deterministik karena bergantung pada aplikasi yang membuka
  dokumen.

Karena itu, untuk rilis final di Windows, jalankan `make finalize-word` agar
nilai cache sudah benar di dalam file.

## Kapan menjalankan `make finalize-word`

Jalankan setelah DOCX selesai dibangun dan sebelum dokumen dibagikan:

```bash
make docx              # atau: ./build-docx.sh
make finalize-word
```

Contoh situasi yang memerlukannya:

- `make docx` mencetak peringatan `docx-pagenum: soffice/pdftotext tidak ada`;
- daftar isi di `Laporan.docx` menampilkan `0` untuk semua entri;
- dokumen akan dikirim ke dosen, diunggah, atau diarsipkan sebagai Word final;
- dokumen akan dibuka di aplikasi selain Microsoft Word yang tidak otomatis
  memperbarui field.

Tidak perlu menjalankannya pada setiap perubahan Markdown bila build DOCX
berikutnya akan dijalankan lagi; langkah ini adalah finalisasi tahap akhir.
Jangan menjalankannya sebagai bagian dari `build-docx.sh`, karena build DOCX
harus tetap bisa berjalan di Linux/CI tanpa Word.

## Cara menjalankan

Dari akar repo, di Windows yang memiliki Microsoft Word desktop:

```powershell
make finalize-word
```

Target tersebut menjalankan:

```powershell
powershell -ExecutionPolicy Bypass -File tools/update_fields.ps1 -DocxPath Laporan.docx
```

Untuk melihat jendela Word saat proses berjalan (berguna ketika ada dialog
yang tidak terlihat), tambahkan `-Visible`:

```powershell
powershell -ExecutionPolicy Bypass -File tools/update_fields.ps1 -DocxPath Laporan.docx -Visible
```

Untuk menguji pada salinan tanpa menyentuh `Laporan.docx`:

```powershell
Copy-Item Laporan.docx "$env:TEMP\uji-fields.docx"
powershell -ExecutionPolicy Bypass -File tools/update_fields.ps1 -DocxPath "$env:TEMP\uji-fields.docx"
```

## Apa yang dilakukan `tools/update_fields.ps1`

1. Memvalidasi path DOCX (gagal dengan pesan jelas bila file tidak ada).
2. Membuat instance Word melalui COM:
   `New-Object -ComObject Word.Application`.
3. Menyembunyikan Word (`Visible = $false`) kecuali opsi `-Visible` dipakai.
4. Membuka dokumen tanpa menambahkannya ke daftar file terakhir.
5. Memanggil `Repaginate()` agar Word menghitung ulang tata letak.
6. Memanggil `Fields.Update()` untuk seluruh field di badan dokumen.
7. Memanggil `TablesOfContents.Update()` untuk setiap daftar isi.
8. Memanggil `Repaginate()` sekali lagi agar layout final stabil.
9. Menyimpan dokumen (`Save()`), menutup dokumen, lalu `Quit()` Word.
10. Melepas objek COM dan memanggil garbage collector.

Skrip tidak menulis teks, mengubah style, atau menyusun ulang struktur
dokumen secara sengaja. Perubahan yang terlihat adalah hasil perhitungan field
oleh Word, terutama nomor halaman TOC. Word tetap menyimpan ulang seluruh
paket DOCX, sehingga detail internal seperti nama part header/footer yang
identik dapat digabung dan media dapat diberi nama ulang; isi dan tampilan
dokumen tidak diubah oleh skrip. Word juga dapat menghapus atribut XML yang
redundan (misalnya `w:fmt="decimal"` atau `w:sz` eksplisit) karena nilainya
diwarisi dari style/docDefaults. Tampilan tetap sama, tetapi pemeriksaan yang
mewajibkan atribut eksplisit dapat gagal pada DOCX hasil finalisasi.

## Verifikasi

Setelah menjalankan skrip pada salinan, periksa bahwa field TOC sudah berisi
nomor halaman. Contoh pemeriksaan dengan Python:

```python
# cek_toc.py
import re
import sys
import zipfile

path = sys.argv[1]
with zipfile.ZipFile(path) as z:
    xml = z.read("word/document.xml").decode("utf-8")

values = []
for match in re.finditer(r"<w:instrText[^>]*>\s*PAGEREF\s+\S+", xml):
    rest = xml[match.end():]
    sep = rest.find('<w:fldChar w:fldCharType="separate"/>')
    end = rest.find('<w:fldChar w:fldCharType="end"/>', sep)
    if sep < 0 or end < 0:
        continue
    text = rest[sep:end]
    values.append("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", text)))

print(values)
```

Jalankan:

```powershell
.venv\Scripts\python.exe cek_toc.py "$env:TEMP\uji-fields.docx"
```

Nilai harus berupa angka Arab/Huruf Romawi (misalnya `i`, `1`, `21`), bukan
`0`. Jumlah halaman dokumen juga tidak boleh berubah hanya karena pembaruan
field; bila berubah, periksa apakah ada heading/gambar yang bergeser karena
font atau layout berbeda.

## Batasan

- **Hanya Windows + Microsoft Word desktop.** COM `Word.Application` tidak
  tersedia di Linux, macOS, WSL tanpa Word, atau runner CI standar.
- **Bukan pengganti `docx-pagenum.py` di CI.** Build lintas platform tetap
  memakai `docx-pagenum.py`; `finalize-word` adalah langkah manual di mesin
  Windows.
- **Butuh Word yang tidak diblokir dialog.** Bila Word menampilkan dialog
  tersembunyi (misalnya file sedang dikunci atau ada add-in bermasalah),
  proses dapat menggantung. Gunakan `-Visible` untuk men-debug.
- **Nomor halaman mengikuti layout Word.** Nomor bisa berbeda dari
  `Laporan.pdf` (Typst) atau render LibreOffice karena mesin tata letak dan
  font yang tersedia berbeda.
- **File harus bisa ditulis.** Skrip menyimpan ke path yang sama; buat salinan
  bila ingin membandingkan hasil sebelum dan sesudah.
- **Word dapat menormalkan isi TOC.** Setelah `TablesOfContents.Update()`,
  Word dapat menyesuaikan pemisah nomor/tab pada entri TOC sesuai gayanya.
  Teks isi bab di badan dokumen tidak diubah.
- **Bukan bagian dari `build-docx.sh`.** Skrip ini tidak dipanggil otomatis
  oleh build agar pipeline tetap jalan di Linux/CI.
