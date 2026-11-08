# design-system-format-laporan

## Apa ini

Design system dan pipeline laporan akademik berbasis Markdown untuk skripsi
UNDIP. Sumber isi adalah `cover.md` dan `chapters/bab*.md`. Dari sumber yang
sama dihasilkan dua keluaran:

- **PDF** melalui Pandoc dan Typst (`template.typ`);
- **DOCX** melalui Pandoc dan `reference.docx` yang digenerate dari preset,
  lalu diproses untuk section, caption, istilah, nomor halaman, dan ID
  paragraf.

Preset aktif adalah `undip-skripsi` di `metadata.yml`. Aturan penulisan yang
mengikat agent ada di `writing/panduan.md`, pola larangan di
`writing/larangan.txt`, dan glosarium istilah di `writing/istilah.tsv`.
Build DOCX juga menulis `build/manifest.json`: setiap paragraf body mendapat
bookmark `pNNNN` agar dapat diedit di Word/Adeu dan direkonsiliasi kembali ke
Markdown.

## Prasyarat

- **Python 3.12** untuk DOCX dan PDF. Build PDF memakai Python untuk
  preprocessing glosarium Markdown; `.venv` proyek dipakai bila tersedia.
- **Git Bash** di Windows untuk build DOCX. **`bash` WSL tidak didukung**
  untuk `build-docx.sh`: venv Windows tidak dapat dipanggil dari WSL dan path
  `/mnt/c` memicu `WinError 5` pada python-docx. Build PDF dapat dijalankan di
  Git Bash, WSL, atau Linux/macOS.
- **Pandoc** dengan `--citeproc`.
- **Typst** untuk build PDF.
- **Microsoft Word desktop** (opsional) untuk finalisasi field otomatis oleh
  `tools/word_finalize.py` saat `build-docx.sh`; tanpa Word, build tetap
  berjalan dengan peringatan.
- **LibreOffice** dan utilitas **Poppler** (`pdftotext`, `pdfinfo`) (opsional)
  untuk mengisi nomor halaman daftar isi saat build DOCX.
- **ImageMagick** (opsional) untuk membersihkan alpha PNG saat build PDF.

## Instalasi

Dari akar repo, di Git Bash:

```bash
python -m venv .venv
.venv/Scripts/pip install -r tools/requirements.txt
```

Di Linux/macOS/WSL:

```bash
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
```

`tools/requirements.txt` memasang `python-docx`, `lxml`, dan `pytest`.

Pandoc dan Typst tidak dipasang oleh perintah di atas. Pasang keduanya dan
pastikan dapat dipanggil dari shell. `build.sh` dan `build-docx.sh` memuat
`tools/env.sh` untuk mencari Pandoc/Typst di lokasi instalasi Windows, WinGet,
dan WSL. `build-docx.sh` melewati syarat Typst karena build DOCX hanya
membutuhkan Pandoc.

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
| `Laporan.pdf` | PDF dari Pandoc + Typst. |
| `build/manifest.json` | Manifest paragraf, bookmark `pNNNN`, dan status `protected`. |

`build-docx.sh` juga menulis `review/istilah-baru.txt` dan berhenti bila masih
ada penanda `{{?istilah?}}` yang belum diputuskan atau `python-docx`/`lxml`
belum tersedia. `reference.docx` tidak ditimpa: versi sesuai preset dibuat di
direktori sementara. Urutan pascaprosesnya adalah `scripts/finalize-docx.py`,
`tools/format_figures.py`, `tools/normalize_layout.py`, `tools/format_code.py`,
`tools/format_equations.py`, `tools/istilah.py apply/verify`,
`scripts/docx-pagenum.py`, `tools/word_finalize.py`, lalu
`tools/add_paragraph_ids.py`.

Build PDF membutuhkan Python 3, glosarium `writing/istilah.tsv`, Pandoc, dan
Typst. `build.sh` memakai `.venv` proyek bila tersedia (Windows atau
Linux/macOS); bila tidak, ia memakai `python3`/`python` sistem. Sebelum Pandoc,
`build.sh` menjalankan `tools/istilah_markdown.py` untuk preprocessing istilah
glosarium ke direktori sementara, lalu menyalin aset, memilih preset dari
`metadata.yml`, memproses sitasi dengan `refs/undip-msi.csl`, dan menjalankan
Pandoc dengan `--pdf-engine=typst`. `logo.jpg` wajib ada karena template sampul
selalu merujuknya; build berhenti dengan error bila aset itu hilang.

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
`.venv/bin/python` di Linux/macOS.

| Keperluan | Perintah |
| --- | --- |
| Build DOCX | `bash build-docx.sh` |
| Build PDF | `bash build.sh` |
| Lint prosa | `make lint-prosa` |
| Verifikasi istilah | `$PY tools/istilah.py verify Laporan.docx --glossary writing/istilah.tsv` |
| Tambah ID paragraf | `$PY tools/add_paragraph_ids.py Laporan.docx --out-docx Laporan-ids.docx --manifest build/manifest.json --source-dir chapters` |
| Rekonsiliasi edit Word | `$PY tools/reconcile.py --docx Laporan-edited.docx --manifest build/manifest.json --chapters chapters --out review/manual-edits.md` |
| Format caption, gambar, tabel | `$PY tools/format_figures.py --docx Laporan.docx --out Laporan.docx` |
| Ekspor template `.dotx` | `$PY tools/export_dotx.py --in reference.docx --out dist/template-laporan.dotx` |

Generator `reference.docx`, format caption, istilah, nomor halaman, finalisasi
field Word, dan ID paragraf sudah dijalankan otomatis oleh `build-docx.sh`.
Perintah manual di tabel dipakai untuk memeriksa atau mengulang satu tahap
tanpa build penuh. `make lint-prosa` hanya membaca `chapters/*.md` dan tidak
dipanggil oleh build.

## Struktur folder

| Path | Isi |
| --- | --- |
| `chapters/` | Markdown bab (`bab*.md`), diurutkan dengan `sort -V`. |
| `cover.md` | Kata Pengantar dan arahan daftar isi/gambar/tabel. |
| `metadata.yml` | Judul, penulis, institusi, dan preset aktif. |
| `presets/` | Preset format kampus; yang aktif adalah `undip-skripsi.yml`. |
| `template.typ` | Template Pandoc ke Typst untuk PDF. |
| `docx.lua` | Filter Lua untuk penomoran bab dan sampul DOCX. |
| `reference.docx` | Basis style DOCX; dibaca `tools/build_style.py` untuk membuat salinan sesuai preset, jangan diedit manual. |
| `tools/` | Generator style, istilah, caption, ID paragraf, rekonsiliasi, ekspor DOTX, pemeriksa prosa, dan `env.sh`. |
| `scripts/` | Finalisasi section, nomor halaman DOCX, pembuat reference, dan utilitas laporan. |
| `refs/` | `undip-msi.csl` (turunan APA 7: author-date, `dan`/`dkk.`, daftar pustaka alfabetis). |
| `writing/` | `istilah.tsv`, `larangan.txt`, dan `panduan.md` untuk penulisan. |
| `tests/` | Tes pytest dan fixture. |
| `build/` | `manifest.json` hasil build (gitignored). |
| `review/` | Laporan review dan daftar istilah baru (gitignored). |
| `gambar/` | Gambar yang dirujuk bab. |
| `docs/` | Dokumentasi rinci; indeksnya di `docs/README.md`. |
| `acuan/` | Bahan acuan lokal dan hasil reverse engineering; tidak dibaca otomatis oleh build. |

## Alur kerja agent

1. Baca `writing/panduan.md` dan `docs/README.md`. Tulis atau ubah isi di
   `chapters/*.md`, `cover.md`, dan `metadata.yml`; jangan menjadikan DOCX
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
7. Build ulang. Untuk rilis Word, cukup `bash build-docx.sh`; Word dijalankan
   otomatis oleh `tools/word_finalize.py` bila tersedia. Untuk distribusi
   template, ekspor `.dotx` dari DOCX yang sudah final.

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
- **Caption belum ada di dokumen contoh.** `chapters/*.md` belum memuat gambar
  atau caption bernomor. `tools/format_figures.py` sudah tersedia dan
  dijalankan build, tetapi efek penomoran caption belum terlihat pada
  `Laporan.docx` contoh.
- **`.dotx` tidak bisa dibuka `python-docx`.** Content type part utamanya
  adalah template, bukan dokumen. Edit DOCX sumbernya lalu ekspor ulang.
- **Edit di Word tidak otomatis masuk ke Markdown.** `reconcile.py` hanya
  menulis laporan `review/manual-edits.md`; penerapan ke `chapters/*.md`
  dilakukan manual. Tanpa rekonsiliasi, build berikutnya akan menimpa edit
  Word.
- **PDF dan DOCX tidak identik secara piksel.** Typst dan Word menghitung
  tata letak, font, serta nomor halaman dengan cara berbeda. Periksa kedua
  keluaran bila isi atau format berubah.
- **Nilai preset UNDIP sudah final dan diuji.** Sumber kebenarannya adalah
  `presets/undip-skripsi.yml`; pemetaan DOCX diverifikasi oleh
  `tests/test_build_style.py` dan penomoran heading oleh
  `tests/test_heading_numbering.py`. Lihat `docs/format-undip.md`.

## Lisensi dan atribusi

Proyek ini turunan `laporan-generator` yang berlisensi MIT. Komponen
pemeriksa prosa `tools/periksa_prosa.py` berasal dari
[naskah-id](https://github.com/nothinx/naskah-id) (MIT, Copyright (c) 2026
nothinx); teks lisensinya disertakan di `docs/prosa.md`.

Repo ini tidak memuat berkas `LICENSE` tersendiri di root. Jika kode
digunakan ulang, pertahankan atribusi dan lisensi komponen asal.
