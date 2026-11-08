# Field DOCX dan Nomor Halaman Daftar Isi

Dokumen ini menjelaskan mengapa daftar isi (TOC) pada `Laporan.docx` bisa
menampilkan nomor halaman `0`, bagaimana `build-docx.sh` menangani field
tersebut, dan batasannya.

## Ringkasan

Nomor halaman daftar isi di DOCX bukan teks biasa. Pandoc menulis field
`PAGEREF` di dalam field `TOC`, dan setiap `PAGEREF` menyimpan **nilai cache**
(nilai terakhir yang dihitung Word). Saat DOCX dibuat, belum ada mesin tata
letak yang tahu nomor halaman final, sehingga cache tersebut diisi `0` atau
nilai sementara.

Pipeline build mengisi cache itu lewat `scripts/docx-pagenum.py`, yang
membutuhkan LibreOffice (`soffice`) dan `pdftotext`. Bila keduanya tidak
tersedia, atau render LibreOffice gagal/timeout, skrip hanya menyalin DOCX apa
adanya. Setelah itu `tools/word_finalize.py` menjalankan Microsoft Word bila
tersedia untuk memperbarui seluruh field dan daftar isi, lalu selalu
menjalankan `scripts/finalize-docx.py --in-place`. Langkah ini sudah menjadi
bagian `build-docx.sh`; tidak ada finalisasi manual setelah build.

## Mengapa TOC bisa berisi 0

Alur pascaproses DOCX secara ringkas:

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
    ├── tools/terms.py             (konsistensi istilah)
    ├── scripts/docx-pagenum.py    (cache PAGEREF via LibreOffice)
    ├── tools/word_finalize.py     (field Word, lalu finalize-docx.py)
    └── tools/add_paragraph_ids.py (bookmark pNNNN + manifest)
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
membiarkan cache bernilai `0`. Nilai itu kemudian diperbarui oleh Word lewat
`tools/word_finalize.py` bila Word tersedia.

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

Karena itu `build-docx.sh` menjalankan Word secara otomatis di akhir
pascaproses. `tools/word_finalize.py` memanggil `tools/update_fields.ps1`
lebih dulu, lalu `scripts/finalize-docx.py --in-place` menghapus
`w:updateFields` agar Word tidak menampilkan prompt saat dokumen dibuka. Bila
Word tidak tersedia, langkah pembaruan field dilewati dengan peringatan dan
cache terakhir tetap dipakai.

## Urutan finalisasi di `build-docx.sh`

Tiga tahap yang berkaitan dengan field dan ID paragraf dijalankan berurutan:

1. `scripts/docx-pagenum.py` mengisi cache `PAGEREF` dari render LibreOffice.
2. `tools/word_finalize.py` membuka Word bila tersedia untuk memperbarui
   field, lalu menjalankan `scripts/finalize-docx.py --in-place`.
3. `tools/add_paragraph_ids.py` menambahkan bookmark `pNNNN` dan menulis
   `build/manifest.json`.

Word dijalankan **sebelum** `add_paragraph_ids.py` agar manifest mencerminkan
DOCX final. Untuk rilis, cukup jalankan:

```bash
bash build-docx.sh
```

Tidak ada perintah finalisasi Word terpisah setelah build. Di Linux/CI tanpa
Microsoft Word, tahap Word dilewati dan build tetap selesai dengan peringatan;
`docx-pagenum.py` menjadi jalur pengisian nomor halaman yang tersedia.

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

Setelah `bash build-docx.sh` selesai, periksa bahwa field TOC sudah berisi
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
.venv\Scripts\python.exe cek_toc.py Laporan.docx
```

Nilai harus berupa angka Arab/Huruf Romawi (misalnya `i`, `1`, `21`), bukan
`0`. Bila Word tidak tersedia saat build, nilai `0` dapat tetap muncul; itu
sesuai batasan di bawah. Jumlah halaman dokumen juga tidak boleh berubah hanya
karena pembaruan field; bila berubah, periksa apakah ada heading/gambar yang
bergeser karena font atau layout berbeda.

## Batasan

- **Hanya Windows + Microsoft Word desktop untuk tahap Word.** COM
  `Word.Application` tidak tersedia di Debian/Linux, macOS, atau runner CI
  standar. Di lingkungan tersebut `word_finalize.py` melewati pembaruan field
  dengan peringatan.
- **Bukan pengganti `docx-pagenum.py` di Debian/Linux.** Build Debian tetap
  memakai `docx-pagenum.py` sebagai jalur utama pengisian nomor halaman.
- **Butuh Word yang tidak diblokir dialog.** Bila Word menampilkan dialog
  tersembunyi (misalnya file sedang dikunci atau ada add-in bermasalah),
  proses dapat menggantung. `word_finalize.py` memakai batas waktu 300 detik
  secara default; opsi `-Visible` pada `update_fields.ps1` berguna untuk
  men-debug.
- **Nomor halaman mengikuti layout mesin ekspor.** Di Windows PDF diekspor
  Word sehingga nomor halaman sama dengan hasil field Word; di Debian
  LibreOffice dapat menghasilkan pemenggalan baris yang sedikit berbeda.
- **File harus bisa ditulis.** Skrip menyimpan ke path yang sama; buat salinan
  bila ingin membandingkan hasil sebelum dan sesudah.
- **Word dapat menormalkan isi TOC.** Setelah `TablesOfContents.Update()`,
  Word dapat menyesuaikan pemisah nomor/tab pada entri TOC sesuai gayanya.
  Teks isi bab di badan dokumen tidak diubah.
- **Sudah menjadi bagian `build-docx.sh`.** `tools/word_finalize.py` dipanggil
  otomatis setelah `docx-pagenum.py` dan sebelum `add_paragraph_ids.py`, jadi
  tidak perlu langkah finalisasi manual untuk rilis.
