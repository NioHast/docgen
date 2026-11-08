# Deployment Windows (Git Bash)

Panduan ini hanya memakai toolchain **Windows-native**. Git Bash dari
[Git for Windows](https://gitforwindows.org/) dipakai sebagai shell build;
Pandoc, Typst, dan Word yang dipanggil juga versi Windows-native.

## Prasyarat

| Kebutuhan | Keterangan |
| --- | --- |
| Windows 10/11 | Arsitektur 64-bit. |
| Python 3.12 | Instal dari [python.org](https://www.python.org/downloads/windows/) dan centang *Add python.exe to PATH*. |
| Git for Windows | Menyediakan `bash`, `cygpath`, dan `git` untuk build. |
| Pandoc | `winget install JohnMacFarlane.Pandoc` atau installer dari [pandoc.org](https://pandoc.org/installing.html). |
| Typst | `winget install Typst.Typst` atau unduh dari [typst.app](https://typst.app/). Hanya dibutuhkan build PDF. |
| Microsoft Word desktop | Opsional. Dipakai `tools/word_finalize.py` untuk memperbarui field TOC/PAGEREF. |
| LibreOffice + Poppler | Opsional. Dipakai `scripts/docx-pagenum.py` untuk mengisi nomor halaman TOC DOCX. |
| ImageMagick | Opsional. Dipakai build PDF untuk membersihkan alpha PNG. |

Pastikan perintah berikut berhasil dari **Git Bash**:

```bash
python --version
pandoc --version
typst --version   # hanya untuk build PDF
bash --version    # harus Git Bash dari Git for Windows
```

`tools/env.sh` menambahkan lokasi instalasi Windows berikut ke `PATH` bila
perkakas belum ditemukan:

- `%LOCALAPPDATA%\Pandoc`
- `%LOCALAPPDATA%\Microsoft\WinGet\Links`
- `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Typst.Typst_*`
- `%PROGRAMFILES%\Pandoc`
- `%USERPROFILE%\.cargo\bin`

## Instalasi

Dari akar repo, di Git Bash:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r tools/requirements.txt
```

## Build

```bash
bash build-docx.sh   # Laporan.docx
bash build.sh        # Laporan.pdf
```

Kedua skrip memilih Python native Windows secara berurutan:

1. `LAPORAN_PYTHON` bila diisi;
2. `.venv/Scripts/python.exe` bila ada;
3. `python` dari `PATH`.

Contoh override:

```bash
LAPORAN_PYTHON="C:/dev/venv-laporan/Scripts/python.exe" bash build.sh
LAPORAN_PYTHON="C:/dev/venv-laporan/Scripts/python.exe" bash build-docx.sh
```

`build-docx.sh` menjalankan `tools/word_finalize.py` karena platform adalah
Windows. Skrip itu membuka Word lewat PowerShell untuk memperbarui field,
lalu membersihkan `w:updateFields` dan `compatibilityMode` lewat
`scripts/finalize-docx.py --in-place`.

## Finalisasi field dengan Word

- Tutup `Laporan.docx` di Word sebelum build agar file tidak terkunci.
- Bila Word tidak tersedia, build tetap berjalan: field TOC memakai cache
  terakhir dan `updateFields` tetap dibersihkan agar Word tidak menampilkan
  prompt pembaruan field.
- Finalisasi manual dapat diulang dengan:

  ```bash
  .venv/Scripts/python.exe tools/word_finalize.py Laporan.docx
  ```

- Untuk melewati Word secara eksplisit:

  ```bash
  .venv/Scripts/python.exe tools/word_finalize.py --skip-word Laporan.docx
  ```

## Batasan

- Jalankan `build-docx.sh` hanya dari Git Bash. Venv dan path yang dipakai
  build adalah milik Windows.
- Jangan mencampur perkakas Debian dengan venv Windows; tidak ada interop
  lintas OS.
- `word_finalize.py` hanya berfungsi penuh di Windows. Di Debian skrip itu
  melewati Word dan hanya membersihkan settings DOCX.

Lihat juga [debian.md](debian.md) untuk deployment Linux/Debian.
