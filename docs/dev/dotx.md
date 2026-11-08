# Template Word (`.dotx`)

Dokumen ini menjelaskan perbedaan `.docx` dan `.dotx`, cara mengekspor template
dari laporan yang sudah jadi, dan cara mendistribusikannya ke mahasiswa.

## `.docx` vs `.dotx`

Keduanya adalah paket ZIP berisi part OOXML WordprocessingML. Isi, style,
header/footer, dan tata letaknya bisa sama persis. Yang membedakan adalah
**content type part dokumen utama** di `[Content_Types].xml`:

| Jenis | Override `/word/document.xml` |
| --- | --- |
| Dokumen biasa (`.docx`) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml` |
| Template (`.dotx`) | `application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml` |

Perbedaan ini membuat Word memperlakukan berkas secara berbeda:

- **`.docx`** dibuka sebagai dokumen itu sendiri. Menyimpan akan menimpa berkas
  tersebut (atau meminta *Save As* bila diedit dari lokasi read-only).
- **`.dotx`** diperlakukan sebagai cetakan. Dobel-klik dari Explorer/File
  Manager membuka **dokumen baru tanpa judul** yang mewarisi style, margin,
  header/footer, dan pengaturan halaman template. Menyimpan akan meminta nama
  berkas `.docx` baru; template aslinya tidak berubah.

Karena itu `.dotx` cocok untuk distribusi: mahasiswa membuka template, langsung
mendapat dokumen baru, lalu menyimpannya sebagai `.docx` dengan nama mereka.

## Ekspor

Jalankan dari root repositori:

```bash
python tools/export_dotx.py --in reference.docx --out dist/template-laporan.dotx
```

Di Windows dengan virtualenv repositori ini:

```bash
.venv/Scripts/python.exe tools/export_dotx.py \
  --in reference.docx \
  --out dist/template-laporan.dotx
```

Argumen:

| Argumen | Keterangan |
| --- | --- |
| `--in` | Berkas DOCX sumber. |
| `--out` | Lokasi berkas DOTX hasil. Direktori induk dibuat bila belum ada. |

Yang dilakukan alat ini:

1. Membuka ZIP input dan menyalin **seluruh part** dengan urutan yang sama.
2. Hanya mengubah nilai `ContentType` pada Override `/word/document.xml` di
   `[Content_Types].xml`, dari content type dokumen menjadi content type
   template. Byte lain di berkas itu (deklarasi XML, kutip, urutan atribut,
   spasi) dipertahankan.
3. Menulis ke berkas sementara, lalu memvalidasi hasilnya:
   - ZIP dapat dibaca dan lolos pemeriksaan CRC;
   - content type `/word/document.xml` benar-benar template;
   - `word/document.xml` well-formed.
4. Memindahkan hasil ke `--out` hanya setelah validasi lolos. Bila gagal,
   berkas output lama tidak tersentuh.

Stempel waktu entri ZIP dibuat tetap (`1980-01-01 00:00:00`) agar hasilnya
reproducible. Konsekuensinya, mengekspor ulang berkas `.dotx` yang sudah jadi
menghasilkan byte yang sama (idempoten). Perintah pada `.dotx` yang sudah
template tidak mengubah content type lagi.

Alat ini menolak input yang tidak memiliki Override `/word/document.xml`,
content type dokumen yang tidak dikenal (misalnya `.docm` makro), atau XML
dokumen yang rusak.

## Verifikasi

Tes otomatis untuk eksportir:

```bash
.venv/Scripts/python.exe -m pytest tests/test_export_dotx.py -q
```

Tes mencakup:

- content type hasil adalah content type template;
- jumlah dan urutan part sama dengan input;
- `word/document.xml` identik byte-per-byte dengan input;
- seluruh part selain `[Content_Types].xml` identik byte-per-byte;
- hanya nilai content type dokumen yang berubah di `[Content_Types].xml`;
- ekspor dua kali menghasilkan byte yang sama;
- input tidak berubah;
- input rusak ditolak tanpa meninggalkan output.

Pemeriksaan manual content type pada hasil:

```bash
python - <<'PY'
import zipfile

with zipfile.ZipFile("dist/template-laporan.dotx") as z:
    print(z.read("[Content_Types].xml").decode())
PY
```

## Distribusi ke mahasiswa

1. Ekspor template dari `reference.docx` (atau DOCX lain yang sudah memakai
   style dan tata letak final).
2. Bagikan berkas `.dotx` melalui LMS, Google Drive, atau media lain.
3. Instruksikan mahasiswa untuk **dobel-klik** berkas template dari Explorer/
   File Manager, bukan membukanya lewat *File > Open* di Word.
4. Mahasiswa mengisi laporan, lalu memilih *Save As* dan menyimpannya sebagai
   `.docx` dengan nama berkas mereka.

Catatan distribusi:

- Template ini tidak mengunci isi dan tidak memakai proteksi form. Mahasiswa
  tetap bisa mengubah style; tujuannya menyediakan titik awal yang konsisten,
  bukan menegakkan aturan secara teknis.
- Jika ingin mencegah template asli tersunting, bagikan salinan read-only atau
  letakkan di folder yang tidak dapat ditulis. Word tetap membuat dokumen baru
  saat template dibuka lewat dobel-klik.
- Uji hasil di **Word desktop** (Windows/macOS). Perilaku aplikasi lain
  (LibreOffice, Word for the web) terhadap `.dotx` bisa berbeda.
- Hanya berlaku untuk DOCX/DOTX non-makro. Untuk template bermakro, diperlukan
  `.dotm` dengan content type berbeda; alat ini tidak mendukungnya.

## Catatan `python-docx`

`python-docx` menolak membuka `.dotx` karena content type part utamanya bukan
content type dokumen. Pesan yang muncul biasanya:

```text
ValueError: file '...' is not a Word file, content type is
'application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml'
```

Itu wajar, bukan kerusakan berkas. Untuk memeriksa atau mengedit isi template
secara programatik:

- edit DOCX sumbernya, lalu ekspor ulang; atau
- ubah content type kembali menjadi content type dokumen pada salinan berkas,
  lalu buka salinan itu dengan `python-docx`.

Jangan memaksa `python-docx` membuka `.dotx` dengan mengganti ekstensi saja;
yang menentukan adalah content type di dalam paket ZIP.
