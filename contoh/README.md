# Contoh Paket Laporan

Folder ini berisi contoh keluaran pipeline, bukan naskah skripsi sungguhan.

## Isi

| Berkas | Keterangan |
| --- | --- |
| `contoh-skripsi.docx` | Hasil build dari `chapters/`, disalin apa adanya dari `Laporan.docx`. |
| `template.dotx` | Template style Word, diekspor dari `reference.docx` hasil preset `undip-skripsi`. |

### `contoh-skripsi.docx`

Berkas ini adalah hasil build dari isi `chapters/*.md` (ditambah `cover.md` dan
`metadata.yml`) menggunakan `bash build-docx.sh`, lalu disalin tanpa perubahan
dari `Laporan.docx` di root repositori. Isinya adalah contoh/dokumentasi
pipeline, **bukan skripsi sungguhan** dan bukan naskah akademik yang siap
dikumpulkan. Jangan menganggap teks, sitasi, atau datanya sebagai karya nyata.

Sumber kebenaran tetap Markdown di `chapters/`, bukan DOCX ini. Jika perlu
mengubah isi contoh, ubah `chapters/` lalu build ulang dan salin hasilnya.

Build terbaru `Laporan.docx` memiliki:

- 370 bookmark ID paragraf (`pNNNN`) dan 370 paragraf manifest;
- sitasi author-date APA 7, misalnya `(Nama, tahun)`;
- 8 tabel: 3 tabel data dan 5 tabel kode berukuran 1×1;
- 0 karakter em dash pada teks isi.

Jumlah itu dapat berubah bila naskah di `chapters/` berubah. Setelah build,
regenerasi salinan contoh dengan `cp Laporan.docx contoh/contoh-skripsi.docx`.
Salinan lama di folder ini tidak otomatis mengikuti build terbaru.

### `template.dotx`

Template ini dibuat dari `reference.docx` yang digenerate ulang dengan preset
`presets/undip-skripsi.yml`, bukan dari `reference.docx` statis di root
repositori. Generator memakai `reference.docx` hanya sebagai basis style, lalu
menerapkan margin UNDIP (atas/kiri 4 cm, bawah/kanan 3 cm) dan Heading 1
12 pt. Isinya placeholder style (Title, Heading 1–9, Body Text, Table Caption,
Image Caption, dan seterusnya), bukan naskah laporan. Style, margin,
header/footer, dan pengaturan halaman di dalamnya bisa dipakai sebagai titik
awal dokumen baru.

Dobel-klik `template.dotx` dari Explorer/File Manager akan membuka **dokumen
baru tanpa judul** di Word yang mewarisi style template. Saat disimpan, Word
meminta nama berkas `.docx` baru; berkas template aslinya tidak berubah.
Perbedaan `.docx` dan `.dotx` hanya pada content type part dokumen utama di
dalam paket ZIP, bukan pada tampilan atau isinya.

## Membuat ulang

Jalankan dari root repositori (bukan dari dalam `contoh/`):

```bash
# 1. Build DOCX terbaru dari chapters/
bash build-docx.sh

# 2. Salin hasil build sebagai contoh, byte-identik
cp Laporan.docx contoh/contoh-skripsi.docx

# 3. Generate reference DOCX dari preset UNDIP
.venv/Scripts/python.exe tools/build_style.py \
  --preset presets/undip-skripsi.yml \
  --out /tmp/reference-undip.docx

# 4. Ekspor template style dari reference hasil preset
.venv/Scripts/python.exe tools/export_dotx.py \
  --in /tmp/reference-undip.docx \
  --out contoh/template.dotx
```

Di Linux/macOS, ganti `.venv/Scripts/python.exe` dengan `.venv/bin/python`.
Langkah 1 menulis `Laporan.docx` di root repositori; jangan menjalankan build
di dalam folder `contoh/`.

## Peringatan

**`contoh-skripsi.docx` harus disalin dari `Laporan.docx` setelah build.**
Jalankan `bash build-docx.sh` di root repositori, lalu salin hasilnya dengan
`cp Laporan.docx contoh/contoh-skripsi.docx`. Salinan lama tidak otomatis
mengikuti build terbaru.

**Jangan mengedit `contoh-skripsi.docx` secara manual.** Sumber kebenaran tetap
Markdown di `chapters/`. Jika isi contoh perlu berubah, ubah `chapters/`, build
ulang, lalu salin lagi hasilnya.

**Finalisasi Word sudah otomatis.** `build-docx.sh` menjalankan finalisasi field
Word melalui `tools/word_finalize.py` sebelum manifest dibuat, jadi tidak ada
langkah tambahan yang perlu dijalankan.

## Yang belum ada di contoh

- **Caption dan gambar isi.** `chapters/*.md` belum memuat gambar bernomor
  atau caption. `tools/format_figures.py` sudah tersedia dan dijalankan saat
  build, tetapi belum ada caption/gambar isi yang bisa ditampilkan di contoh.
- **Halaman pengesahan dan pernyataan.** `cover.md` hanya memuat Kata
  Pengantar dan arahan daftar isi; build tidak membuat halaman pengesahan,
  pernyataan, atau lembar tanda tangan.

## Verifikasi singkat

```bash
.venv/Scripts/python.exe - <<'PY'
import re, zipfile
from docx import Document

path = "contoh/contoh-skripsi.docx"
with zipfile.ZipFile(path) as z:
    assert z.testzip() is None
    xml = z.read("word/document.xml")
ids = re.findall(rb'<w:bookmarkStart\b[^>]*w:name="p\d+"', xml)
print("paragraf:", len(Document(path).paragraphs))
print("bookmark ID paragraf:", len(ids))

with zipfile.ZipFile("contoh/template.dotx") as z:
    assert z.testzip() is None
    ct = z.read("[Content_Types].xml").decode()
assert "wordprocessingml.template.main+xml" in ct
print("template.dotx: content type template, ZIP valid")
PY
```

Setelah `contoh-skripsi.docx` diregenerasi dari build terbaru, berkas itu
memiliki 370 bookmark ID paragraf (`pNNNN`) dan 370 paragraf manifest. Jumlah
ini dapat berubah bila naskah berubah. Bila seluruh bookmark lain (anchor
heading dan sitasi) ikut dihitung, build terbaru memiliki 469 elemen
`w:bookmarkStart`.
