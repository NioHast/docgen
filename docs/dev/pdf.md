# Build PDF dari DOCX

Dokumen ini menjelaskan bagaimana `Laporan.pdf` dihasilkan. Sejak pipeline PDF
dipindahkan ke ekspor DOCX, PDF **selalu** diturunkan dari `<Nama>.docx` final
hasil `build-docx.sh`, bukan dari Markdown secara langsung.

## Ringkasan

```bash
bash build.sh          # menghasilkan Laporan.pdf di root repo
bash build.sh outdir/  # opsional: DOCX/PDF di direktori lain
```

Perilaku `build.sh`:

1. Menentukan `LAPORAN_METADATA`, `LAPORAN_CHAPTERS`, dan
   `LAPORAN_REPORT_NAME` (default: `metadata.yml`, `chapters`, `Laporan`).
2. Bila `<Nama>.docx` belum ada, menjalankan `build-docx.sh` lebih dulu.
   Bila DOCX sudah ada, tahap DOCX dilewati.
3. Mengekspor DOCX ke PDF melalui `tools/export_pdf.py`.

```text
cover.md + chapters/*.md + metadata.yml + references.bib
        │
        ▼
   build-docx.sh  (Pandoc + pascaproses DOCX)
        │
        ▼
   Laporan.docx
        │
        ▼
   tools/export_pdf.py
        ├── Windows  -> tools/export_pdf.ps1 -> Microsoft Word COM
        │              Fields.Update() + TablesOfContents.Update()
        │              -> ExportAsFixedFormat()
        └── Debian   -> soffice --headless --convert-to pdf
        │
        ▼
   Laporan.pdf
```

Glosarium, caption, penomoran, persamaan, dan nomor halaman sudah ditangani
pipeline DOCX. Karena itu PDF cukup mengekspor DOCX final tanpa tahap
preprocessing tambahan.

## Berkas yang terlibat

| Berkas | Peran |
| --- | --- |
| `build.sh` | Orkestrasi: bangun DOCX bila perlu, lalu ekspor PDF. |
| `build-docx.sh` | Membangun DOCX final (Pandoc, style, caption, istilah, nomor halaman, field Word). |
| `tools/export_pdf.py` | Deteksi platform dan pemanggil mesin ekspor PDF. |
| `tools/export_pdf.ps1` | Ekspor Word COM di Windows: buat snapshot DOCX, perbarui field/TOC, tulis PDF, tutup Word. |
| `Laporan.docx` | Sumber PDF. |
| `Laporan.pdf` | Keluaran ekspor. |
| `metadata.yml` | Judul, penulis, institusi, dan preset; dibaca `build-docx.sh`. |
| `presets/*.yml` | Margin, font, spasi, dan opsi tata letak DOCX. |
| `references.bib`, `refs/undip-msi.csl` | Sitasi dan daftar pustaka; diproses saat build DOCX. |
| `writing/istilah.tsv` | Glosarium; diterapkan ke DOCX oleh `tools/terms.py`. |
| `cover.md`, `chapters/bab*.md` | Isi laporan; diurutkan `sort -V` oleh `build-docx.sh`. |
| `gambar/` | Gambar yang dirujuk bab. |

## Windows: Microsoft Word COM

Prasyarat: **Microsoft Word desktop** dan PowerShell. Word dipanggil secara
tersembunyi oleh `tools/export_pdf.ps1` dan tidak menyimpan ulang DOCX.
Skrip membuat **snapshot sementara** dari DOCX, membuka snapshot itu di Word,
lalu menghapusnya setelah ekspor. DOCX sumber tidak pernah dibuka langsung
oleh Word, sehingga tetap aman bila sedang dibuka aplikasi lain dan tidak
meninggalkan owner file `~$...` di direktori proyek.

Urutan di dalam Word:

1. `Documents.Open` membuka snapshot DOCX (bukan read-only).
2. `Repaginate()` menghitung ulang layout.
3. `Fields.Update()` memperbarui seluruh field, termasuk `PAGE`, `PAGEREF`,
   dan field TOC.
4. Setiap `TableOfContents` di-update agar entri dan nomor halamannya sesuai.
5. `Repaginate()` sekali lagi agar layout final stabil.
6. `ExportAsFixedFormat(<tujuan>.pdf, wdExportFormatPDF)` menulis PDF.
7. `Close(0)` menutup dokumen tanpa menyimpan perubahan dan `Quit()` menutup
   Word.

Bila Word tidak terpasang, snapshot gagal dibuat (misalnya direktori sementara
tidak dapat ditulis), atau PDF tujuan sedang dikunci aplikasi lain, `build.sh`
berhenti dengan error dan tidak meninggalkan PDF lama.

## Debian/Linux: LibreOffice headless

Prasyarat: LibreOffice Writer yang menyediakan `soffice`.

```bash
sudo apt install libreoffice-writer
```

Perintah yang dijalankan `tools/export_pdf.py`:

```bash
soffice --headless --convert-to pdf --outdir <direktori-tujuan> <docx>
```

LibreOffice menulis `<nama-docx>.pdf` di direktori tujuan. Bila nama PDF
tujuan berbeda, `tools/export_pdf.py` memindahkan hasilnya. Set
`LAPORAN_SOFFICE` bila executable LibreOffice berada di lokasi non-standar.

LibreOffice tidak memperbarui field Word seperti Word COM. Nomor halaman TOC
mengikuti cache yang sudah diisi `scripts/docx-pagenum.py` saat
`build-docx.sh`. Karena itu, di Debian pasang juga `libreoffice-writer` dan
`poppler-utils` agar nomor halaman TOC terisi. Bila cache masih `0`, buka DOCX
di Word, perbarui field, simpan, lalu ekspor ulang.

## Override metadata, bab, dan nama laporan

```bash
LAPORAN_METADATA=proposal/metadata.yml LAPORAN_REPORT_NAME=Proposal bash build.sh
LAPORAN_METADATA=metadata-tugas.yml LAPORAN_CHAPTERS=chapters-tugas \
  LAPORAN_REPORT_NAME=Tugas bash build.sh
```

Ketiga variabel diteruskan ke `build-docx.sh` bila DOCX belum ada. Nama PDF
mengikuti `LAPORAN_REPORT_NAME`. Argumen direktori pertama (`bash build.sh
outdir/`) menentukan tempat DOCX dan PDF ditulis.

Pemilihan Python untuk `tools/export_pdf.py` mengikuti urutan:

1. `LAPORAN_PYTHON`;
2. `.venv/Scripts/python.exe` (Windows) atau `.venv/bin/python` (Linux);
3. `python`/`python3` dari `PATH`.

`tools/export_pdf.py` hanya memakai pustaka standar Python.

## Verifikasi hasil

```bash
bash build.sh
ls -l Laporan.pdf
```

Pemeriksaan isi:

```bash
.venv/Scripts/python.exe - <<'PY'
from pypdf import PdfReader

reader = PdfReader("Laporan.pdf")
texts = [page.extract_text() or "" for page in reader.pages]
print("halaman:", len(reader.pages))
print("DAFTAR ISI:", any("DAFTAR ISI" in text for text in texts))
print("contoh TOC:")
for text in texts:
    if "DAFTAR ISI" in text:
        print(text[:500])
PY
```

Yang harus benar:

- PDF berasal dari DOCX final dan jumlah halamannya setara dengan DOCX
  (baseline isi saat ini 31 halaman; minimal 23 halaman untuk laporan contoh);
- halaman `DAFTAR ISI` memuat entri dan nomor halaman, bukan `0`;
- penomoran halaman tampil (romawi pada front matter, arab pada isi);
- teks isi memakai Times New Roman 12 pt. Code memakai Courier New, persamaan
  memakai Cambria Math, dan Word dapat menyertakan font theme tambahan untuk
  spasi/glyph tak terlihat;
- caption tabel berada di atas tabel dan caption gambar di bawah gambar.

`pypdf` hanya dibutuhkan untuk pemeriksaan manual, bukan untuk build.

## Catatan historis

Pipeline PDF lama yang merender Markdown secara langsung sudah dihapus.
`build.sh` sekarang hanya menyiapkan DOCX final lalu memanggil
`tools/export_pdf.py`. `tools/env.sh` masih dipakai `build-docx.sh` untuk
menemukan Pandoc; `build.sh` tidak memuatnya karena tidak membutuhkan Pandoc
bila DOCX sudah ada.

## Troubleshooting

| Gejala | Tindakan |
| --- | --- |
| `Microsoft Word tidak terpasang atau COM Word tidak tersedia` | Pasang Word desktop; Word Online tidak menyediakan COM. |
| `Gagal membuat salinan kerja DOCX` | Pastikan direktori sementara dapat ditulis dan DOCX sumber dapat dibaca. |
| `Gagal mengekspor PDF` | Tutup PDF tujuan bila sedang dibuka, lalu ulangi. |
| `LibreOffice (soffice) tidak ditemukan` | `sudo apt install libreoffice-writer`, atau set `LAPORAN_SOFFICE`. |
| TOC berisi nomor `0` di Debian | Pasang `libreoffice-writer` + `poppler-utils`, build ulang DOCX, lalu ekspor. |
| DOCX tidak ikut diperbarui | `build.sh` hanya membangun DOCX bila belum ada; jalankan `bash build-docx.sh` lebih dulu. |
| PDF lama tetap ada setelah gagal | Ekspor menghapus PDF tujuan sebelum menulis; bila masih ada, periksa pesan error dan proses yang mengunci berkas. |
