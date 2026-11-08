# METODOLOGI

## Arsitektur Sistem dan Alur Kerja Pipeline

Pengembangan sistem **Laporan Generator** dirancang dengan prinsip modularitas tinggi dan pemisahan lapisan tugas (*separation of concerns*). Arsitektur sistem dibagi menjadi tiga lapisan utama: Lapisan Masukan (*Input Layer*), Lapisan Pemrosesan (*Processing Layer*), dan Lapisan Keluaran (*Output Layer*).

```
+-------------------------------------------------------------------------+
|                              INPUT LAYER                                |
|  chapters/bab*.md  |  cover.md        |  metadata.yml  |  presets/*.yml |
|  references.bib    |  refs/undip-msi.csl    |  logo.jpg      |  gambar/*      |
+-------------------------------------------------------------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
+---------------------------------------+ +-------------------------------+
|       PIPELINE 1: TYPST (PDF)         | |   PIPELINE 2: DOCX MULTI-PASS |
|                                       | |                               |
| 1. ImageMagick Alpha Normalization    | | 1. Pandoc + docx.lua Filter   |
| 2. Preset Metadata Extraction         | | 2. Base reference.docx Styling|
| 3. Pandoc AST + Citeproc Processing   | | 3. finalize-docx.py (3 Sect)  |
| 4. Typst Typesetting Engine Render    | | 4. docx-pagenum.py (Page Inj) |
+---------------------------------------+ +-------------------------------+
            |                                               |
            v                                               v
+---------------------------------------+ +-------------------------------+
|             Laporan.pdf               | |          Laporan.docx         |
| (Clean Vector, Author-Date, Typst)    | | (Roman Front, Arabic Body)    |
+---------------------------------------+ +-------------------------------+
```

## Perancangan Template Visual Typst (`template.typ`)

Template visual Typst berfungsi sebagai pengatur tata letak halaman, tipografi, dan penomoran dokumen PDF. Template dirancang fleksibel untuk mendukung preset margin dinamis dan penomoran otomatis.

### Pengaturan Geometri Halaman dan Margin

Geometri halaman diatur secara adaptif melalui blok evaluasi kondisi Typst:

```typst
#set page(
  paper: "a4",
  margin: doc-margin,
  numbering: none,
)
```

Variabel `doc-margin` dievaluasi dari berkas konfigurasi preset (`margin_top`, `margin_bottom`, `margin_left`, `margin_right`) yang diinjeksikan oleh Pandoc pada saat kompilasi.

### Penomoran Heading Bertingkat

Penomoran judul bab dan sub-bab ditangani melalui fungsi callback `#set heading()`:

```typst
#set heading(numbering: (..ns) => {
  if ns.len() == 1 {
    "BAB " + numbering("I", ns.at(0))
  } else if ns.len() == 2 {
    numbering("1.1.", ..ns)
  } else {
    numbering("1.1.1", ..ns)
  }
})
```

Penanganan khusus diimplementasikan pada `#show heading.where(level: 1)` untuk menghasilkan jeda halaman otomatis (*pagebreak*) dan meletakkan nomor bab ("BAB I") di atas judul bab dengan gaya huruf kapital tebal 12 pt di tengah halaman.

### Algoritma Keseimbangan Judul Sampul (*Balanced Title Splitting*)

Untuk mencegah terjadinya fenomena kata menggantung sendirian di baris bawah (*orphan words*), template mengintegrasikan fungsi pembagi judul berbasis Dynamic Programming (`balance-split`). Algoritma ini mengevaluasi jumlah karakter per baris dan meminimalisir fungsi biaya (*cost function*) agar panjang tiap baris judul sampul depan simetris menyerupai bentuk piramida terbalik.

## Perancangan Pipeline Dokumen Microsoft Word (DOCX)

Penyusunan dokumen DOCX resmi memerlukan integrasi tiga komponen pemrosesan berurutan:

### Filter Lua docx.lua
Filter Lua mengintersepsi pohon sintaks abstrak (AST) Pandoc. Fungsi `Header(el)` menghitung indeks bab dan sub-bab serta menyusun entri Daftar Isi ber-hyperlink. Fungsi `Pandoc(doc)` membangun halaman sampul formal menggantikan title block bawaan Pandoc.

### Partisi Tiga Seksi Dokumen finalize-docx.py
Skrip Python memanipulasi struktur OpenXML berkas `word/document.xml` dengan membagi dokumen ke dalam tiga penanda seksi (`w:sectPr`):
- **Seksi 1 (Sampul)**: Menghapus elemen `<w:footerReference>` sehingga nomor halaman tidak tampil pada sampul luar.
- **Seksi 2 (Front Matter)**: Menginjeksikan `<w:pgNumType w:fmt="lowerRoman" w:start="1"/>` agar halaman KATA PENGANTAR dan DAFTAR ISI diberi nomor *i, ii, iii*.
- **Seksi 3 (Main Body)**: Menginjeksikan `<w:pgNumType w:fmt="decimal" w:start="1"/>` sebelum judul BAB I agar penomoran dimulai ulang dari angka 1, 2, 3.

### Sinkronisasi Nomor Halaman Aktual docx-pagenum.py
Untuk memastikan Daftar Isi pada dokumen DOCX menampilkan nomor halaman yang akurat di seluruh aplikasi pengolah kata, skrip `docx-pagenum.py` melakukan:
1. Render headless berkas DOCX menjadi PDF temporer menggunakan LibreOffice (`soffice --headless`).
2. Ekstraksi teks per halaman menggunakan utilitas `pdftotext`.
3. Pencocokan teks heading dengan footer halaman aktual.
4. Pengisian nilai cache pada field OpenXML `<w:instrText>PAGEREF</w:instrText>`.

## Sistem Preset Kampus Deklaratif

Untuk memfasilitasi keberagaman pedoman penulisan skripsi di berbagai perguruan tinggi di Indonesia, arsitektur preset deklaratif (`presets/*.yml`) dibangun dengan skema standar:

| Kategori Parameter | Kunci Konfigurasi | Contoh Nilai | Keterangan |
|:---|:---|:---|:---|
| **Identitas** | `preset_id`, `name` | `undip-skripsi`, `undip-msi-proposal` | Identifikasi unik dan nama institusi |
| **Geometri Margin** | `margin_top`, `margin_left` | `4cm`, `3cm`, `2.5cm` | Batas tepi kertas A4 |
| **Tipografi** | `font_family`, `font_size` | `Times New Roman`, `12pt` | Jenis font dan ukuran teks isi (PDF) |
| **Spasi & Indentasi** | `line_spacing`, `first_line_indent` | `0.75em`, `1.25cm` | Spasi 1.5 dan indent alinea |
| **Sampul (Cover)** | `cover_show_lecturer` | `true` / `false` | Pengaturan tampilan dosen pembimbing |

Sistem ini dijalankan langsung oleh `build.sh` dan `build-docx.sh`: keduanya membaca nama preset dari `metadata.yml`, memuat `presets/<nama-preset>.yml`, lalu menyerahkannya ke `tools/build_style.py` untuk DOCX atau ke template Typst untuk PDF. Bila nama preset tidak ditemukan, build berhenti dengan error dan tidak memakai preset kampus lain secara diam-diam.

## Metodologi Pengujian dan Verifikasi

Keandalan seluruh komponen pipeline diuji menggunakan suite pytest yang terbagi dalam modul-modul terpisah untuk setiap area pengujian di direktori `tests/`. Pengujian memverifikasi:
1. Kesesuaian gaya `reference.docx` dengan spesifikasi acuan dan override preset.
2. Penomoran heading, caption/gambar/tabel, serta struktur penomoran halaman DOCX.
3. Ekspor DOCX ke DOTX, injeksi ID paragraf, dan validitas manifest paragraf.
4. Penerapan istilah asing, integrasi dengan Pandoc, dan verifikasi laporan penuh.
5. Rekonsiliasi edit manual DOCX ke Markdown serta pemeriksaan prosa.

Selain suite pytest, verifikasi integrasi dilakukan melalui `bash build.sh` untuk PDF dan `bash build-docx.sh` untuk DOCX. Kedua skrip memeriksa ketersediaan dependensi dan menghasilkan berkas keluaran; `build-docx.sh` juga menjalankan pascaproses seksi, caption, istilah, nomor halaman, dan ID paragraf. Laporan ini tidak mencantumkan jumlah kasus uji atau persentase kelulusan tetap karena angka tersebut berubah setiap kali suite diperbarui.
