# TINJAUAN PUSTAKA

## Markdown dan Standardisasi Dokumen Teks

### Sejarah dan Filosofi Markdown

Markdown pertama kali diciptakan oleh John Gruber pada tahun 2004 sebagai format penulisan berbasis teks polos (*plain text*) yang dirancang agar mudah dibaca dan ditulis oleh manusia tanpa perlu proses kompilasi visual [@gruber2004markdown]. Filosofi dasar Markdown menempatkan keterbacaan (*human-readability*) sebagai prioritas tertinggi, di mana markup struktural tidak boleh mengaburkan arti teks substantif.

Seiring meluasnya penggunaan Markdown dalam ekosistem rekayasa perangkat lunak, inisiatif standardisasi melahirkan spesifikasi formal CommonMark [@commonmark2021]. Varian Pandoc Markdown memperluas spesifikasi ini dengan mendukung sintaks akademik tingkat lanjut seperti tabel bergaya *pipe*, blok kode beranotasi, catatan kaki (*footnotes*), persamaan matematika LaTeX inline maupun display, metadata berbasis YAML front matter, dan sitasi bibliografi terintegrasi [@pandoc2024].

### Sintaks Penulisan Akademik dalam Markdown

Tabel berikut merangkum pemetaan sintaks Markdown yang digunakan dalam pipeline penyusunan laporan akademik:

| Elemen Struktur | Sintaks Markdown | Contoh Penulisan | Representasi Keluaran |
|:---|:---|:---|:---|
| Judul Bab (Level 1) | `# Judul` | `# PENDAHULUAN` | BAB I PENDAHULUAN |
| Sub-Bab (Level 2) | `## Sub Judul` | `## Latar Belakang` | 1.1. Latar Belakang |
| Sub-Sub-Bab (Level 3) | `### Rincian` | `### Identifikasi Masalah` | 1.1.1 Rincian Masalah |
| Sitasi Bibliografi | `[@citekey]` | `[@typst2024]` | Sitasi author-date, misalnya `(Mädje dan Haug, 2024)` |
| Tabel Akademik | Pipe & Header Syntax | `| Kolom 1 | Kolom 2 |` | Tabel formal bergaris 0.5pt |
| Gambar / Diagram | `![Keterangan](path)` | `![Arsitektur](gambar/flow.png)` | Gambar terpusat ber-caption |
| Persamaan Matematika | `$...$` / `$$...$$` | `$E = m c^2$` | Notasi rumus terformat presisi |

Persamaan display ditulis pada baris tersendiri di antara sepasang tanda dolar ganda. Sebagai contoh, metrik akurasi untuk mengevaluasi hasil klasifikasi dirumuskan sebagai berikut:

$$Accuracy = \frac{TP + TN}{TP + TN + FP + FN}$$

Dengan: TP adalah jumlah positif benar (*true positive*); TN adalah jumlah negatif benar (*true negative*); FP adalah jumlah positif palsu (*false positive*); dan FN adalah jumlah negatif palsu (*false negative*). Pada keluaran DOCX, pipeline mengubah notasi LaTeX tersebut menjadi persamaan OMML dan memberi nomor persamaan secara otomatis.

## Sistem Typesetting Modern: Typst

### Arsitektur dan Prinsip Kerja Typst

Typst adalah sistem typesetting berbasis markup yang dapat diprogram (*programmable markup-based typesetting system*) yang dikembangkan oleh Laurenz Mädje dan Martin Haug [@typst2024]. Typst dirancang sebagai respons terhadap keterbatasan sistem typesetting klasik seperti TeX dan LaTeX [@knuth1984texbook; @lamport1994latex] yang memiliki waktu kompilasi lambat, pesan galat yang sulit diurai, serta sintaks makro yang kompleks.

Typst mengadopsi model kompilasi inkremental modern berbasis bahasa pemrograman Rust. Karakteristik utama Typst mencakup:

1. **Kecepatan Kompilasi Tinggi**: Typst mampu mengompilasi puluhan halaman dokumen dalam hitungan milidetik, memungkinkan pengalaman pratinjau langsung (*live reload*) yang sangat responsif.
2. **Binary Ringan dan Mandiri**: Ukuran binary Typst hanya berkisar 25 MB dan tidak membutuhkan dependensi eksternal dari repositori paket yang besar.
3. **Tipografi Bawaan yang Portabel**: Typst menyertakan font berkualitas tinggi seperti Libertinus Serif dan DejaVu Sans Mono langsung di dalam binary, sehingga menjamin konsistensi render di semua platform tanpa isu font hilang (*missing fonts*).
4. **Model Tata Letak Deklaratif**: Pengaturan margin halaman, penomoran heading bertingkat, dan aturan jeda halaman (*pagebreak*) dikonfigurasi melalui fungsi bawaan yang elegan seperti `#set page()`, `#set heading()`, dan `#show heading()`.

## Pandoc dan Pemrosesan Dokumen Abstrak

### Universal Document Converter

Pandoc adalah perangkat lunak konversi dokumen universal yang dikembangkan oleh John MacFarlane [@pandoc2024]. Pandoc bekerja dengan membaca format masukan (seperti Markdown), mengonversinya ke dalam struktur pohon sintaks abstrak internal yang disebut *Abstract Syntax Tree* (AST), lalu mengekspor AST tersebut ke berbagai format target, termasuk Typst, HTML, EPUB, dan Microsoft Word (DOCX).

### Filter Lua dan Ekstensibilitas AST

Sejak versi 2.0, Pandoc menyediakan mesin scripting tertanam berbasis bahasa pemrograman Lua yang memungkinkan manipulasi AST sebelum proses penulisan dokumen akhir dilakukan [@krewinkel2020pandoc]. Dalam proyek ini, berkas `docx.lua` berperan penting dalam:

1. Mendeteksi elemen heading level 1, 2, dan 3 untuk menambahkan penomoran otomatis berformat Romawi (`BAB I`) dan Arab (`1.1.`, `1.1.1`).
2. Menghasilkan struktur XML untuk halaman sampul formal dan Daftar Isi yang terhubung dengan tautan hiperteks internal (*hyperlink anchor*).
3. Mencegah penomoran ganda pada bagian khusus seperti KATA PENGANTAR dan DAFTAR PUSTAKA.

## Arsitektur Dokumen Office Open XML (DOCX)

Standar internasional ISO/IEC 29500 mendefinisikan Office Open XML (OpenXML) sebagai representasi berkas dokumen teks berbasis arsip ZIP yang berisi serangkaian berkas XML dan relasi strukturalnya [@iso2021openxml]. Berkas utama `word/document.xml` menyimpan seluruh elemen paragraf (`<w:p>`), teks (`<w:t>`), dan properti seksi (`<w:sectPr>`).

Pengaturan *section break* (`<w:sectPr>`) menentukan perilaku penomoran halaman pada setiap bagian dokumen. Agar mematuhi kaidah akademik Indonesia, dokumen DOCX dibagi menjadi tiga seksi:
1. **Seksi Sampul**: Referensi footer dihapus sehingga halaman pertama bersih tanpa nomor.
2. **Seksi Front Matter**: Properti penomoran diset ke format Romawi kecil (`w:fmt="lowerRoman"` dan `w:start="1"`).
3. **Seksi Main Body (BAB I)**: Properti penomoran di-reset menjadi format angka Arab (`w:fmt="decimal"` dan `w:start="1"`).

## Pemrosesan Citra Digital dengan ImageMagick

ImageMagick adalah rangkaian perangkat lunak untuk manipulasi citra digital via baris perintah [@imagemagick2024]. Pada pipeline dokumen ilmiah, diagram dan tangkapan layar sering kali berformat PNG dengan saluran transparansi (*alpha channel*). Saluran alfa yang tidak diatur dapat menimbulkan artefak visual seperti latar belakang hitam atau distorsi warna pada saat citra dirender ke dalam dokumen PDF. Pipeline menggunakan perintah normalisasi:

```bash
convert input.png -alpha off output.png
```

Perintah ini secara rekursif menonaktifkan transparansi dan menggantinya dengan latar belakang putih pekat, menjamin gambar tampil bersih pada media cetak.

## Reproducibility dan Lingkungan Pengembangan

### Manajemen Dependensi dengan Python Virtual Environment

Dependensi Python untuk pengolahan DOCX dan pengujian, yaitu `python-docx`, `lxml`, dan `pytest`, dipasang di dalam virtual environment `.venv` sesuai daftar versi pada `tools/requirements.txt`. Isolasi ini mencegah konflik dengan paket Python sistem dan membuat lingkungan pengujian dapat direproduksi pada mesin pengembang. Lingkungan dibuat dari akar repositori dengan `python -m venv .venv`, lalu dependensi dipasang memakai `.venv/Scripts/pip install -r tools/requirements.txt` pada Windows atau `.venv/bin/pip install -r tools/requirements.txt` pada Linux dan macOS.

### Dukungan Lingkungan Build Lintas Platform

Build dijalankan melalui Git Bash di Windows atau shell Bash pada Linux dan macOS. Pandoc menangani konversi Markdown, pemrosesan sitasi, dan keluaran DOCX, sedangkan Typst menghasilkan PDF. Kedua perkakas dipanggil melalui `tools/env.sh` yang membantu menemukan instalasi Pandoc dan Typst pada PATH Windows, WinGet, maupun WSL. Build DOCX memerlukan Git Bash di Windows karena venv Windows tidak dapat dipanggil dari WSL dan path `/mnt/c` memicu `WinError 5` pada `python-docx`; build PDF dapat dijalankan di Git Bash, WSL, Linux, maupun macOS.

## Standar Sitasi Akademik Author-Date

Karya ilmiah dan laporan akademik pada pipeline ini menggunakan standar pengutipan author-date. Setiap sumber dikutip dengan nama penulis dan tahun terbit di dalam tanda kurung, misalnya `(Nama, tahun)`. Sitasi dua penulis ditulis `(Nama dan Nama, tahun)`, sedangkan sitasi lebih dari dua penulis ditulis `(Nama dkk., tahun)`. Daftar pustaka disusun alfabetis menurut nama belakang penulis pertama dan tidak memakai nomor, sehingga setiap sitasi dalam teks merujuk langsung ke entri yang sesuai di DAFTAR PUSTAKA. Pemrosesan sitasi dijalankan secara otomatis oleh `pandoc --citeproc` menggunakan berkas definisi gaya `refs/undip-msi.csl` dan basis data pustaka BibTeX `references.bib`.
