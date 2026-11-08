# Build PDF (Pandoc → Typst)

Dokumen ini menjelaskan bagaimana `Laporan.pdf` dihasilkan, peran `tools/env.sh`,
dan perbedaan mesin tata letak PDF vs DOCX.

## Ringkasan

```bash
bash build.sh          # menghasilkan Laporan.pdf di root repo
bash build.sh outdir/  # opsional: tulis Laporan.pdf ke direktori lain
```

Prasyarat PDF: **Python 3** (utamakan `.venv` proyek), `writing/istilah.tsv`,
**Pandoc**, dan **Typst**. Pipeline PDF memakai **Typst** sebagai mesin tata
letak dan menjalankan preprocessing glosarium sebelum Pandoc:

```text
cover.md + chapters/bab*.md + writing/istilah.tsv
        │
        ├── tools/istilah_markdown.py            (preprocessing glosarium)
        │        └── chapters-pre/*.md
        ├── metadata.yml
        ├── presets/<preset>.yml
        ├── references.bib + refs/undip-msi.csl   (citeproc)
        └── template.typ                     (template Pandoc → Typst)
        │
        ▼
   pandoc --pdf-engine=typst
        │
        ▼
   typst compile
        │
        ▼
   Laporan.pdf
```

Sebelum Pandoc, `build.sh` menjalankan `tools/istilah_markdown.py` dengan
Python 3 dari `.venv` (bila tersedia) atau `python3`/`python` sistem. Skrip ini
membaca `writing/istilah.tsv` dan menulis salinan bab ke `chapters-pre/` di
direktori sementara; `chapters/` asli tidak diubah. Glosarium wajib: build
berhenti bila `writing/istilah.tsv` tidak ditemukan.

Pandoc membaca Markdown hasil preprocessing dan menghasilkan sumber Typst
memakai `template.typ`. Setelah itu Pandoc memanggil Typst untuk mengompilasi
sumber tersebut menjadi PDF. Tidak ada LaTeX di pipeline ini.

## Berkas yang terlibat

| Berkas | Peran |
| --- | --- |
| `build.sh` | Orkestrasi: salin aset ke direktori sementara, preprocessing glosarium, susun urutan bab, pilih preset, panggil Pandoc + Typst, tulis `Laporan.pdf`. |
| `tools/env.sh` | Menemukan Pandoc/Typst dan menyiapkannya di `PATH` (Windows, WSL, Linux). |
| `tools/istilah_markdown.py` | Preprocessing glosarium: membungkus istilah `italic=yes` dengan `*...*` agar penulisan PDF sama dengan DOCX. |
| `writing/istilah.tsv` | Glosarium wajib berisi istilah, status italic, dan status review. |
| Python 3 / `.venv` | Runtime preprocessing glosarium; `.venv` dipakai bila tersedia, fallback ke `python3`/`python` sistem. |
| `template.typ` | Template Pandoc yang menghasilkan markup Typst (halaman, margin, heading, daftar isi, dsb.). |
| `metadata.yml` | Judul, penulis, institusi, dan nama preset. |
| `presets/*.yml` | Margin, font, spasi, dan opsi tata letak per kampus. |
| `references.bib` | Basis data sitasi. |
| `refs/undip-msi.csl` | Gaya sitasi author-date (turunan APA 7) untuk `--citeproc`. |
| `cover.md`, `chapters/bab*.md` | Isi laporan. Bab diurutkan dengan `sort -V`. |
| `gambar/` | Gambar; PNG dengan alpha dibersihkan memakai ImageMagick bila tersedia. |

`build.sh` menyalin berkas-berkas di atas ke direktori sementara (`mktemp -d`)
lalu menjalankan Pandoc dari sana. Direktori sementara dihapus otomatis saat
build selesai (trap `EXIT`). Karena itu `refs/` ikut disalin: argumen
`--csl="refs/undip-msi.csl"` diresolusikan relatif terhadap direktori kerja Pandoc.

## Kesesuaian dengan Panduan MSI UNDIP

`template.typ` menerapkan aturan Panduan Tesis MSI UNDIP Edisi 9/2022 yang
relevan untuk keluaran PDF:

| Aspek | Perilaku PDF |
| --- | --- |
| Font | Times New Roman 12 pt. Nilai `font_family` lama `Libertinus Serif` dari preset generik dipetakan ke Times New Roman; jika TNR tidak terpasang di sistem, Typst memakai Libertinus Serif sebagai fallback. |
| Heading bab | 12 pt, bold, center, kapital. Untuk proposal, `heading_chapter_prefix: ""` + `heading_chapter_num_format: "arabic"` menghasilkan `1. PENDAHULUAN` dalam satu baris, bukan `BAB I`. |
| Page break bab | Untuk tesis, setiap H1 memulai halaman baru. Mode proposal (`heading_chapter_prefix: ""` + `heading_chapter_num_format: "arabic"`) tidak memaksa page break. Set `heading_chapter_pagebreak: true`/`false` untuk override eksplisit. |
| Caption | Semua caption 12 pt. Caption tabel di atas tabel dan rapat kiri; caption gambar tetap di bawah gambar dan mengikuti perataan figure (center). |
| Nomor halaman | Sampul tidak bernomor; front matter mulai `ii`; isi mulai `1` (angka Arab). Nomor halaman berada di footer kanan (`number-align: right`). |
| Persamaan | Nomor `(bab.n)` di tepi kanan; jarak 2 kali `line_spacing` sebelum/sesudah; persamaan menjorok 1 cm dari margin kiri sebagai pendekatan "2 tabulasi". |

Catatan:

- `number-align: right` berlaku untuk semua halaman bernomor karena peralihan
  front matter ke isi dilakukan oleh blok Typst di `cover.md`, yang hanya
  menetapkan `numbering` dan mewarisi `number-align` dari template. Panduan MSI
  menempatkan nomor front matter di tengah; bila diperlukan, atur ulang di
  `cover.md`.
- Panduan menyebut persamaan "menjorok ke kanan 2 tabulasi" tanpa ukuran
  metrik. Template memakai 1 cm; nomor persamaan tetap berada di tepi kanan
  margin.
- Pemisah caption bawaan Typst masih `: ` (`Tabel 1.1: Judul`). Panduan tidak
  mengatur tanda pemisah; yang diwajibkan adalah ukuran, posisi, dan perataan.

## Cara kerja `tools/env.sh`

Masalah yang diselesaikan: installer Windows menambahkan Pandoc/Typst ke
`PATH` Windows, tetapi Git Bash (MSYS) dan WSL memiliki `PATH` sendiri. Akibatnya
`pandoc` atau `typst` tidak ditemukan walaupun aplikasinya terpasang.

`build.sh` memanggil:

```bash
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/tools/env.sh"
```

### Deteksi platform

| `uname -s` | Platform | Perlakuan |
| --- | --- | --- |
| `MINGW*`, `MSYS*`, `CYGWIN*` | `windows` | Cari `pandoc.exe`/`typst.exe` di direktori Windows, konversi path dengan `cygpath`. |
| `Linux*` + `/proc/version` mengandung `microsoft` | `wsl` | Cari executable Windows lewat `/mnt/c/...`; sediakan jembatan path POSIX → Windows. |
| `Linux*` lainnya | `linux` | Andalkan `PATH` native; tidak menambahkan direktori Windows. |

Direktori yang diperiksa (bila ada):

- `%LOCALAPPDATA%\Pandoc`
- `%LOCALAPPDATA%\Microsoft\WinGet\Links`
- `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Typst.Typst_*\*\`
- `%PROGRAMFILES%\Pandoc`
- Di WSL: padanan di atas melalui `/mnt/c/Users/<user>/AppData/...`

Direktori hanya ditambahkan bila benar-benar ada dan belum ada di `PATH`.
Sourcing ulang tidak menggandakan entri `PATH` dan tidak mengubah direktori
kerja.

### Khusus WSL

Di WSL, executable Windows tidak ditemukan oleh pencarian `PATH` Linux
(`typst` ≠ `typst.exe`). `env.sh` karena itu mengekspor dua variabel:

- `LAPORAN_TYPST`: path lengkap ke `typst.exe`.
- `LAPORAN_PANDOC`: nama fungsi pembungkus `_laporan_pandoc_windows`.

Fungsi pembungkus meneruskan argumen ke `pandoc.exe`, tetapi mengubah argumen
path absolut POSIX (`/mnt/c/...`, `/tmp/...`) menjadi path Windows memakai
`wslpath -w`, termasuk nilai `-o`/`--output`. Ini diperlukan karena Pandoc
Windows tidak memahami `/mnt/c/...`, sedangkan Pandoc Linux bawaan distro bisa
lebih lama daripada Typst yang terpasang (mis. Pandoc 3.1.3 menghasilkan
`#cite("kunci")`, sedangkan Typst 0.15 memakai `#cite(<kunci>)`).

`build.sh` memakai variabel tersebut secara eksplisit:

```bash
"${LAPORAN_PANDOC:-pandoc}" ... --pdf-engine="${LAPORAN_TYPST:-typst}"
```

Di Windows/Git Bash dan Linux native, kedua variabel tidak diset sehingga
perintah biasa `pandoc` dan `typst` yang dipakai. `build-docx.sh` memuat
`env.sh` dengan `LAPORAN_ENV_SKIP_TYPST=1` dan memakai
`"${LAPORAN_PANDOC:-pandoc}"`, sehingga build DOCX hanya membutuhkan Pandoc.

### Bila perkakas tidak ditemukan

`env.sh` mencetak pesan ke stderr lalu `exit 1`, misalnya:

```text
[env] ERROR: Typst tidak ditemukan.
[env]        Platform terdeteksi: wsl.
[env]        Instal Typst dari https://typst.app/, atau pastikan typst/typst.exe ada di PATH.
[env]        Build PDF membutuhkan Typst; build DOCX tidak.
[env]        Direktori yang diperiksa:
[env]        <tidak ada direktori Windows yang terdeteksi>
```

Karena `build.sh` memakai `set -e`, build berhenti sebelum Pandoc dipanggil.

## Verifikasi hasil

```bash
bash build.sh
ls -l Laporan.pdf
file Laporan.pdf                    # contoh: PDF document, version 1.7, 23 page(s)
pdfinfo Laporan.pdf | grep Pages    # bila poppler-utils tersedia
```

Baseline repo saat ini menghasilkan PDF 23 halaman. Jumlah halaman dapat
berubah bila isi bab, margin preset, atau metadata diubah. Yang harus tetap
benar:

- font yang tertanam adalah Times New Roman (Regular/Bold/Italic/BoldItalic),
  bukan Libertinus Serif;
- halaman pertama front matter bernomor `ii`, bukan `i`;
- halaman isi bernomor Arab mulai `1` dan berada di kanan bawah;
- heading bab 12 pt; caption 12 pt; caption tabel berada di atas tabel dan
  rapat kiri.

Pandoc 3.13 masih mencetak peringatan berikut; ini bukan error:

```text
[WARNING] Deprecated: --no-highlight. Use --syntax-highlighting=none instead.
```

Untuk menguji jalur gagal, sembunyikan Typst dari `PATH` sementara, misalnya di
WSL:

```bash
env PATH=/usr/bin:/bin bash build.sh
echo $?    # 1
```

## PDF vs DOCX: mesin tata letak berbeda

| Aspek | PDF (`build.sh`) | DOCX (`build-docx.sh`) |
| --- | --- | --- |
| Mesin | Pandoc → **Typst** | Pandoc → **WordprocessingML** |
| Tata letak | Ditentukan `template.typ` | Ditentukan `reference.docx` + gaya Word |
| Nomor halaman | `set page(numbering: ..., number-align: right)` di Typst | Properti section DOCX (`scripts/docx-pagenum.py`) |
| Font | Times New Roman 12 pt (fallback Libertinus Serif) | Times New Roman di `reference.docx`/preset |
| Preset | `presets/*.yml` dibaca sebagai metadata | `tools/build_style.py` menghasilkan `reference.docx` |
| Sitasi | `--citeproc` + `refs/undip-msi.csl` | `--citeproc` + `refs/undip-msi.csl` |
| Keluaran | `Laporan.pdf` | `Laporan.docx` |

Konsekuensinya:

- PDF dan DOCX **tidak akan identik secara piksel**. Pemenggalan baris, posisi
  gambar, dan jumlah halaman bisa berbeda karena Typst dan Word menghitung
  tata letak dengan cara masing-masing.
- Perubahan pada `template.typ` hanya memengaruhi PDF; perubahan pada
  `reference.docx`/`build_style.py` hanya memengaruhi DOCX.
- Keduanya berbagi sumber isi (`cover.md`, `chapters/`, `metadata.yml`,
  `references.bib`, `refs/undip-msi.csl`). Perubahan isi/sitasi harus diverifikasi
  di kedua keluaran.
- `build.sh` membutuhkan Python 3 dan `writing/istilah.tsv` untuk preprocessing
  glosarium, tetapi tidak membutuhkan `python-docx`; `build-docx.sh` tidak
  memerlukan Typst dan membutuhkan Python dengan `python-docx`/`lxml`.
  `tools/env.sh` dipakai bersama hanya untuk menemukan Pandoc (dan Typst bila
  build PDF).

## Troubleshooting singkat

| Gejala | Tindakan |
| --- | --- |
| `[env] ERROR: Pandoc tidak ditemukan` | Instal Pandoc, atau pastikan `pandoc.exe` ada di `%LOCALAPPDATA%\Pandoc`. |
| `[env] ERROR: Typst tidak ditemukan` | Instal Typst, atau pastikan `typst.exe` ada di `%LOCALAPPDATA%\Microsoft\WinGet\Links`. |
| Pandoc Linux terlalu lama untuk Typst baru | Jalankan lewat Git Bash, atau biarkan `env.sh` memakai Pandoc Windows di WSL. |
| `refs/undip-msi.csl` tidak ditemukan | Pastikan berkas ada; `build.sh` menyalin direktori `refs/` ke direktori kerja sementara. |
| `Glosarium writing/istilah.tsv tidak ditemukan` | Sediakan `writing/istilah.tsv`; build PDF memakainya untuk preprocessing istilah. |
| `Python 3 tidak ditemukan` | Instal Python 3 atau sediakan `.venv` proyek. |
| Peringatan `--no-highlight` | Tidak berbahaya; hanya deprecation dari Pandoc 3.13. |
