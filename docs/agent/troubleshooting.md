# Troubleshooting

## Caption tabel atau gambar

Gejala:

```text
chapters/bab2.md:14: tabel tanpa caption; tambahkan baris ': Judul tabel'
chapters/bab2.md:22: gambar tanpa alt text; tulis ![deskripsi gambar](path)
```

Tindakan:

1. Tambahkan baris `: Judul tabel` sebelum atau sesudah tabel.
2. Ganti `![](gambar/x.png)` menjadi `![Deskripsi gambar](gambar/x.png)`.
3. Jalankan ulang `python tools/check_captions.py document.md`.
4. Build ulang. `build-docx.sh` menjalankan pemeriksaan yang sama sebelum
   Pandoc, dan `tools/format_figures.py` memeriksa ulang DOCX.

Jangan menambahkan caption kosong atau nomor manual. Nomor caption dibuat
otomatis dari Heading 1.

## `mmdc` tidak ditemukan atau gagal render

Gejala:

```text
Blok Mermaid ditemukan, tetapi mmdc tidak ditemukan di PATH.
```

Tindakan:

```bash
node --version
npm install -g @mermaid-js/mermaid-cli
mmdc --version
```

Jika `mmdc` tidak ada di `PATH`, berikan path eksplisit:

```bash
python src/laporan/mermaid.py --src chapters --out-dir . \
  --mmdc "%APPDATA%\npm\mmdc.cmd"
```

Di Windows, path umumnya `%APPDATA%\npm\mmdc.cmd`. Pastikan Node.js sudah
terpasang. Bila render gagal, tidak ada Markdown atau PNG yang ditulis.
Nama PNG mengikuti hash isi diagram dan opsi render, jadi perubahan diagram
akan menghasilkan berkas baru. Hapus `gambar/mermaid-*.png` lama hanya untuk
membersihkan berkas yatim.

## Word atau LibreOffice

Periksa perkakas lebih dulu:

```bash
python -m laporan doctor
```

Gejala di Windows:

- `Microsoft Word tidak terpasang atau COM Word tidak tersedia`: pasang Word
  desktop. Word Online tidak menyediakan COM.
- `Gagal mengekspor PDF`: tutup PDF tujuan yang sedang dibuka, lalu ulangi.
- Field dan nomor halaman daftar isi masih `0`: buka DOCX di Word, perbarui
  field, simpan, lalu ekspor ulang.

Gejala di Debian/Linux:

- `LibreOffice (soffice) tidak ditemukan`: pasang
  `sudo apt install libreoffice-writer`.
- TOC berisi `0`: pasang juga `poppler-utils`, build ulang DOCX, lalu ekspor.
- `soffice` berada di lokasi non-standar: set `LAPORAN_SOFFICE` ke executable
  tersebut.

Tanpa Word di Windows, DOCX tetap dapat dibangun tetapi PDF tidak dapat
diekspor. Di Debian, PDF memakai LibreOffice dan tidak membutuhkan Word.

## `ruamel.yaml`

Gejala:

- `ModuleNotFoundError: No module named 'ruamel'`;
- pesan `YAML tidak valid` pada front matter atau `metadata.yml`;
- nilai bersarang atau daftar terbaca sebagai teks.

Tindakan:

```bash
python -m pip install -r requirements.txt
```

Atau dengan `uv`:

```bash
uv sync
```

`ruamel.yaml` adalah dependensi runtime di `pyproject.toml` dan dipakai
`src/laporan/manifest.py`, `src/laporan/singlefile.py`, serta
`tools/build_style.py`. Bila paket itu tidak tersedia, pipeline tetap berjalan
dengan pembaca subset bawaan, tetapi kemampuannya terbatas: `manifest.py` dan
`singlefile.py` menangani skalar, daftar inline/blok, dan peta bersarang,
sedangkan `tools/build_style.py` hanya membaca pasangan `key: value` datar.
Fitur YAML kompleks seperti anchor, merge key, blok literal/folded, tag, atau
beberapa dokumen dalam satu berkas tidak didukung fallback. Untuk YAML yang
kompleks, pasang `ruamel.yaml`.

Pastikan berkas ditulis UTF-8 dan memakai indentasi spasi, bukan tab. Untuk
front matter, `---` harus berada di baris pertama.

## Path dan aset

- Jalankan perintah dari akar repositori agar `structures/`, `formats/`,
  `presets/`, dan `tools/` ditemukan.
- Di mode satu berkas, gambar harus berada di `gambar/` relatif terhadap
  `document.md`. Path absolut dan `..` ditolak.
- Berkas bibliografi harus berada di folder sumber atau subfoldernya dan
  ditulis relatif, misalnya `bibliography: references.bib`.
- Glosarium default `writing/istilah.tsv` disalin ke workspace. Glosarium
  khusus harus berada di folder sumber dan ditulis relatif.
- Gunakan garis miring `/` di YAML dan Markdown, termasuk di Windows.
- Bungkus path berspasi dengan tanda kutip di shell.
- Workspace `.laporan-build/` dibuat di folder sumber dan dihapus setelah
  build. Gunakan `--keep` untuk mempertahankannya saat mencari masalah.

## Build gagal atau berkas terkunci

- `Berkas tidak ditemukan`: periksa nama bab di `manifest.yml` atau
  `chapters` pada front matter.
- `Direktori tujuan sudah berisi berkas`: gunakan `--force` hanya bila isi
  direktori memang boleh ditimpa.
- `report_name tidak boleh memuat karakter path`: hapus `/`, `\`, `:`, atau
  karakter path lain dari `report_name`.
- `Permission denied` atau `file is being used by another process`: tutup
  Word, LibreOffice, atau PDF viewer yang membuka `Laporan.docx` atau
  `Laporan.pdf`, lalu build ulang.
- `Berkas sumber harus UTF-8`: simpan ulang Markdown sebagai UTF-8 tanpa BOM
  ganda.

Untuk diagnosis, jalankan `python -m laporan build <dir> --dry-run` agar
environment dan perintah yang akan dipakai terlihat tanpa menjalankan build.
