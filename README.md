# design-system-format-laporan

## Apa ini

Design system dan pipeline laporan akademik berbasis Markdown untuk skripsi
UNDIP. Sumber isi adalah `cover.md` dan `chapters/bab*.md`. Dari sumber yang
sama dihasilkan dua keluaran:

- **PDF** melalui ekspor DOCX final (Microsoft Word COM di Windows,
  LibreOffice headless di Debian/Linux);
- **DOCX** melalui Pandoc dan `reference.docx` yang digenerate dari preset,
  lalu diproses untuk section, caption, istilah, nomor halaman, dan ID
  paragraf.

Preset aktif adalah `undip-skripsi` di `metadata.yml`. Aturan penulisan yang
mengikat agent ada di `writing/guide.md`, sumber aturan pemeriksa di
`writing/rules.yml`, dan glosarium istilah di `writing/istilah.tsv`.
Build DOCX juga menulis `build/manifest.json`: setiap paragraf body mendapat
bookmark `pNNNN` agar dapat diedit di Word/Adeu dan direkonsiliasi kembali ke
Markdown.

## Dokumentasi

- [docs/agent/quickstart.md](docs/agent/quickstart.md): lima langkah memilih
  struktur, menulis, check, build, dan output.
- [docs/agent/document-format.md](docs/agent/document-format.md): front matter,
  heading, caption, gambar, Mermaid, dan sitasi.
- [docs/agent/writing-rules.md](docs/agent/writing-rules.md): ringkasan aturan
  prosa dan cara menjalankan checker.
- [docs/agent/troubleshooting.md](docs/agent/troubleshooting.md): masalah
  caption, `mmdc`, Word/LibreOffice, `ruamel.yaml`, dan path.
- [docs/dev/architecture.md](docs/dev/architecture.md): arsitektur pipeline
  untuk pengembang.
- [docs/README.md](docs/README.md): indeks lengkap `docs/dev/` dan
  `docs/agent/`.

## Prasyarat

- **Python 3.15** untuk DOCX dan ekspor PDF. Pipeline DOCX memakai `.venv`
  proyek bila tersedia; `tools/export_pdf.py` hanya memakai pustaka standar.
- **Windows**: Git for Windows (Git Bash) dengan Pandoc dan Microsoft Word
  native. Word wajib untuk build PDF dan dipakai finalisasi field DOCX. Semua
  build dijalankan dari Git Bash. Lihat
  [docs/dev/deployment/windows.md](docs/dev/deployment/windows.md).
- **Debian/Linux**: bash dengan Pandoc dan LibreOffice native. LibreOffice
  (`soffice`) wajib untuk ekspor PDF. Word tidak tersedia; finalisasi field
  Word dilakukan di Windows. Lihat
  [docs/dev/deployment/debian.md](docs/dev/deployment/debian.md).
- **Pandoc** dengan `--citeproc` untuk build DOCX.
- **Microsoft Word desktop** (Windows) untuk ekspor PDF dan finalisasi field
  otomatis oleh `tools/word_finalize.py`. Tanpa Word, DOCX tetap dapat
  dibangun, tetapi PDF tidak dapat diekspor di Windows.
- **LibreOffice** dan utilitas **Poppler** (`pdftotext`, `pdfinfo`) di
  Debian/Linux untuk ekspor PDF dan pengisian nomor halaman daftar isi DOCX.

## Instalasi

Dari akar repo, di Git Bash:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

Di Debian/Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` memasang `python-docx`, `lxml`, dan `ruamel.yaml`. Untuk tes,
pasang `requirements-dev.txt` dengan perintah yang sama. Alternatifnya,
`uv sync` membaca `pyproject.toml` dan memasang dependensi runtime.

Pandoc tidak dipasang oleh perintah di atas. Pasang Pandoc dan pastikan dapat
dipanggil dari shell. `build-docx.sh` memuat `tools/env.sh`: di Windows skrip
itu mencari Pandoc di lokasi instalasi Windows, sedangkan di Debian/Linux
hanya memakai executable native dari `PATH`. `build.sh` tidak membutuhkan
Pandoc bila DOCX sudah ada; bila DOCX belum ada, `build.sh` memanggil
`build-docx.sh` yang menyiapkan Pandoc.

## Build

Jalankan dari akar repo:

```bash
bash build-docx.sh   # Laporan.docx
bash build.sh        # Laporan.pdf
```

Keluaran utama:

| Berkas | Keterangan |
| --- | --- |
| `Laporan.docx` | Dokumen Word final hasil build dan pascaproses. |
| `Laporan.pdf` | PDF hasil ekspor `Laporan.docx` melalui Word/LibreOffice. |
| `build/manifest.json` | Manifest paragraf, bookmark `pNNNN`, dan status `protected`. |

`build-docx.sh` juga menulis `review/istilah-baru.txt` dan berhenti bila masih
ada penanda `{{?istilah?}}` yang belum diputuskan atau `python-docx`/`lxml`
belum tersedia. `reference.docx` tidak ditimpa: versi sesuai preset dibuat di
direktori sementara. Urutan pascaprosesnya adalah `scripts/finalize-docx.py`,
`tools/format_figures.py`, `tools/normalize_layout.py`, `tools/format_code.py`,
`tools/format_equations.py`, `tools/terms.py apply/verify`,
`scripts/docx-pagenum.py`, `tools/word_finalize.py`, lalu
`tools/add_paragraph_ids.py`.

Build PDF mengekspor DOCX final, bukan menjalankan ulang Pandoc. Bila
`Laporan.docx` belum ada, `build.sh` memanggil `build-docx.sh` lebih dulu;
bila sudah ada, tahap DOCX dilewati. Setelah itu `tools/export_pdf.py`
mengekspor PDF dengan Microsoft Word COM di Windows (field dan TOC
diperbarui sebelum `ExportAsFixedFormat`) atau LibreOffice headless
(`soffice --headless --convert-to pdf`) di Debian/Linux. Glosarium sudah
diterapkan ke DOCX oleh `tools/terms.py`; PDF mengekspor DOCX final tanpa
tahap preprocessing terpisah. `LAPORAN_PYTHON` dapat menimpa pilihan Python.

Gaya sitasi default adalah **author-date alfabetis** dari
`refs/undip-msi.csl` (turunan APA 7): dua penulis memakai `dan`, tiga penulis
atau lebih memakai `dkk.`, dan daftar pustaka diurutkan alfabetis tanpa nomor.
`metadata.yml` menetapkan `lang: "id-ID"` untuk istilah sitasi Indonesia.

Metadata dan nama keluaran dapat dioverride tanpa menyalin skrip:

```bash
LAPORAN_METADATA=metadata-proposal.yml LAPORAN_REPORT_NAME=Proposal bash build-docx.sh
LAPORAN_METADATA=metadata-proposal.yml LAPORAN_REPORT_NAME=Proposal bash build.sh
```

## Perintah penting

`PY` di bawah adalah `.venv/Scripts/python.exe` di Windows/Git Bash atau
`.venv/bin/python` di Debian/Linux.

| Keperluan | Perintah |
| --- | --- |
| Build DOCX | `bash build-docx.sh` |
| Build PDF | `bash build.sh` |
| Lint prosa | `make lint-prosa` atau `$PY tools/check_prose.py chapters/*.md` |
| Periksa caption tabel/gambar | `$PY tools/check_captions.py chapters/*.md` |
| Verifikasi istilah | `$PY tools/terms.py verify Laporan.docx --glossary writing/istilah.tsv` |
| Ekspor PDF dari DOCX | `$PY tools/export_pdf.py Laporan.docx --output Laporan.pdf` |
| Tambah ID paragraf | `$PY tools/add_paragraph_ids.py Laporan.docx --out-docx Laporan-ids.docx --manifest build/manifest.json --source-dir chapters` |
| Rekonsiliasi edit Word | `$PY tools/reconcile.py --docx Laporan-edited.docx --manifest build/manifest.json --chapters chapters --out review/manual-edits.md` |
| Format caption, gambar, tabel | `$PY tools/format_figures.py --docx Laporan.docx --out Laporan.docx` |
| Ekspor template `.dotx` | `$PY tools/export_dotx.py --in reference.docx --out dist/template-laporan.dotx` |

Generator `reference.docx`, format caption, istilah, nomor halaman, finalisasi
field Word, dan ID paragraf sudah dijalankan otomatis oleh `build-docx.sh`.
Perintah manual di tabel dipakai untuk memeriksa atau mengulang satu tahap
tanpa build penuh. `make lint-prosa` memanggil `tools/check_prose.py`, sedangkan
`make lint-captions` memanggil `tools/check_captions.py`. Keduanya hanya
membaca `chapters/*.md`; pemeriksaan caption juga dipanggil otomatis oleh
`build-docx.sh` sebelum Pandoc.

## Struktur folder

| Path | Isi |
| --- | --- |
| `chapters/` | Markdown bab (`bab*.md`), diurutkan dengan `sort -V`. |
| `cover.md` | Kata Pengantar dan arahan daftar isi/gambar/tabel. |
| `metadata.yml` | Judul, penulis, institusi, dan preset aktif. |
| `presets/` | Preset format kampus: `undip-skripsi.yml` dan `undip-msi-proposal.yml`. Metadata wajib menyebut preset yang ada. |
| `docx.lua` | Filter Lua untuk penomoran bab dan sampul DOCX. |
| `reference.docx` | Basis style DOCX; dibaca `tools/build_style.py` untuk membuat salinan sesuai preset, jangan diedit manual. |
| `tools/` | `terms.py`, `check_prose.py`, `check_captions.py`, `export_pdf.py`, generator style, format DOCX, ID paragraf, rekonsiliasi, ekspor DOTX, dan `env.sh`. |
| `scripts/` | Finalisasi section, nomor halaman DOCX, dan pembuat `reference.docx`. |
| `refs/` | `undip-msi.csl` (turunan APA 7: author-date, `dan`/`dkk.`, daftar pustaka alfabetis). |
| `writing/` | `istilah.tsv`, `rules.yml`, dan `guide.md` untuk penulisan. |
| `tests/` | Tes pytest dan fixture. |
| `build/` | `manifest.json` hasil build (gitignored). |
| `review/` | Laporan review dan daftar istilah baru (gitignored). |
| `gambar/` | Gambar yang dirujuk bab. |
| `docs/` | Dokumentasi rinci: `docs/dev/` untuk implementasi dan `docs/agent/` untuk panduan pemakai; indeksnya di `docs/README.md`. |
| `acuan/` | Bahan acuan lokal dan hasil reverse engineering; tidak dibaca otomatis oleh build. |

## Alur kerja agent

1. Baca `writing/guide.md` dan `docs/agent/quickstart.md`. Tulis atau ubah isi
   di `chapters/*.md`, `cover.md`, dan `metadata.yml`; jangan menjadikan DOCX
   sebagai sumber.
2. Tandai istilah asing dengan `*...*` bila sudah yakin, atau `{{?istilah?}}`
   bila perlu keputusan. Jangan mengarang sitasi; gunakan `TODO-SITASI:` dan
   lengkapi `references.bib`.
3. Jalankan `bash build-docx.sh` untuk DOCX dan `bash build.sh` bila PDF juga
   berubah.
4. Periksa kegagalan build, `make lint-prosa`, dan `review/istilah-baru.txt`.
   Perbaiki Markdown, bukan hasil DOCX.
5. Untuk review di Word, buka `Laporan.docx`, aktifkan Track Changes, dan
   edit hanya paragraf yang tidak `protected`. Jangan mengedit caption, TOC,
   section break, daftar pustaka, sampul, atau field.
6. Jalankan `tools/reconcile.py` untuk menghasilkan
   `review/manual-edits.md`. Baca saran, lalu terapkan sendiri ke
   `chapters/*.md`; alat ini tidak menulis Markdown.
7. Build ulang. Untuk rilis Word, cukup `bash build-docx.sh`; di Windows Word
   dijalankan otomatis oleh `tools/word_finalize.py` bila tersedia. Di
   Debian/Linux tahap itu dilewati dengan warning dan field difinalkan di
   Windows. Untuk distribusi template, ekspor `.dotx` dari DOCX yang sudah
   final.

Artefak `Laporan.docx`, `Laporan.pdf`, `build/`, dan `review/` tidak dilacak
Git. Yang perlu dipertahankan adalah Markdown, metadata, preset, referensi,
dan dokumentasi.

## Keterbatasan yang diketahui

- **Halaman pengesahan/pernyataan belum digenerate.** `cover.md` hanya berisi
  Kata Pengantar dan arahan daftar isi; build tidak membuat isi halaman
  pengesahan atau pernyataan. `scripts/finalize-docx.py` hanya menata section
  bila heading tersebut sudah ada di sumber.
- **Nomor halaman TOC bisa `0`.** Cache `PAGEREF` hanya diisi bila LibreOffice
  dan utilitas Poppler (`pdftotext`, `pdfinfo`) tersedia saat build. Tanpa
  keduanya, file di disk tetap menampilkan `0` sampai Word tersedia saat build
  (dijalankan `tools/word_finalize.py`) atau aplikasi lain yang menghitung
  ulang field.
- **`word_finalize.py` menormalkan XML dan bisa mengubah hasil.** Word menyimpan
  ulang seluruh paket DOCX: part header/footer yang identik dapat digabung,
  media dapat dinamai ulang, dan atribut XML redundan dapat dihapus. Tampilan
  tidak diubah secara sengaja, tetapi pemeriksaan yang menuntut XML identik
  bisa gagal pada hasil finalisasi.
- **Caption tabel/gambar wajib.** Setiap tabel Markdown harus memiliki
  `: Judul tabel` dan setiap gambar harus memiliki alt text non-kosong.
  `tools/check_captions.py` memeriksa sumber sebelum Pandoc, dan
  `tools/format_figures.py` menolak DOCX yang masih memiliki tabel/gambar
  tanpa caption. Build berhenti dengan daftar temuan sampai caption
  ditambahkan.
- **`.dotx` tidak bisa dibuka `python-docx`.** Content type part utamanya
  adalah template, bukan dokumen. Edit DOCX sumbernya lalu ekspor ulang.
- **Edit di Word tidak otomatis masuk ke Markdown.** `reconcile.py` hanya
  menulis laporan `review/manual-edits.md`; penerapan ke `chapters/*.md`
  dilakukan manual. Tanpa rekonsiliasi, build berikutnya akan menimpa edit
  Word.
- **PDF dan DOCX memakai layout yang sama, tetapi mesin ekspor bisa berbeda.**
  Di Windows PDF diekspor oleh Word, di Debian oleh LibreOffice. Perbedaan
  kecil pada pemenggalan baris atau font pengganti mungkin muncul bila font
  tidak tersedia; periksa PDF pada platform rilis.
- **Nilai preset UNDIP sudah final dan diuji.** Sumber kebenarannya adalah
  `presets/undip-skripsi.yml`; pemetaan DOCX diverifikasi oleh
  `tests/test_build_style.py` dan penomoran heading oleh
  `tests/test_heading_numbering.py`. Lihat `docs/dev/format-undip.md`.

## Lisensi dan atribusi

Proyek ini turunan `laporan-generator` yang berlisensi MIT. Komponen
pemeriksa prosa `tools/check_prose.py` berasal dari
[naskah-id](https://github.com/nothinx/naskah-id) (MIT, Copyright (c) 2026
nothinx); teks lisensinya disertakan di `docs/dev/prosa.md`.

Repo ini tidak memuat berkas `LICENSE` tersendiri di root. Jika kode
digunakan ulang, pertahankan atribusi dan lisensi komponen asal.
