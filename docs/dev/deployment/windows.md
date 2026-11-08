# Deployment Windows (Git Bash)

Panduan ini hanya memakai toolchain **Windows-native**. Git Bash dari
[Git for Windows](https://gitforwindows.org/) dipakai sebagai shell build;
Pandoc dan Word yang dipanggil juga versi Windows-native.

## Prasyarat

| Kebutuhan | Keterangan |
| --- | --- |
| Windows 10/11 | Arsitektur 64-bit. |
| Python 3.15 | Instal dari [python.org](https://www.python.org/downloads/windows/) dan centang *Add python.exe to PATH*. |
| Git for Windows | Menyediakan `bash`, `cygpath`, dan `git` untuk build. |
| Pandoc | `winget install JohnMacFarlane.Pandoc` atau installer dari [pandoc.org](https://pandoc.org/installing.html). |
| Microsoft Word desktop | Wajib untuk ekspor PDF dan dipakai `tools/word_finalize.py` untuk memperbarui field TOC/PAGEREF. Word Online tidak menyediakan COM. |
| LibreOffice + Poppler | Opsional. Dipakai `scripts/docx-pagenum.py` untuk mengisi nomor halaman TOC DOCX. |

Pastikan perintah berikut berhasil dari **Git Bash**:

```bash
python --version
pandoc --version
bash --version    # harus Git Bash dari Git for Windows
```

`tools/env.sh` menambahkan lokasi instalasi Pandoc Windows berikut ke `PATH`
bila perkakas belum ditemukan:

- `%LOCALAPPDATA%\Pandoc`
- `%LOCALAPPDATA%\Microsoft\WinGet\Links`
- `%PROGRAMFILES%\Pandoc`

## Instalasi

Dari akar repo, di Git Bash:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
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

## Ekspor PDF dengan Word

`bash build.sh` mengekspor DOCX final ke PDF. Bila `Laporan.docx` belum ada,
`build.sh` memanggil `build-docx.sh` lebih dulu; bila sudah ada, DOCX dipakai
apa adanya. Ekspor dijalankan `tools/export_pdf.py` melalui
`tools/export_pdf.ps1`:

1. Word membuka snapshot DOCX secara tersembunyi.
2. `Fields.Update()` dan setiap `TablesOfContents.Update()` dijalankan.
3. `ExportAsFixedFormat` menulis PDF.
4. Word ditutup tanpa menyimpan DOCX; snapshot dihapus.

Microsoft Word desktop wajib tersedia. Word Online, LibreOffice, atau Word
yang tidak terpasang membuat ekspor gagal dengan pesan yang dapat ditindaklanjuti.
Lihat [../pdf.md](../pdf.md) untuk detail dan troubleshooting.

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

- Jalankan `build-docx.sh` dan `build.sh` hanya dari Git Bash. Venv dan path
  yang dipakai build adalah milik Windows.
- Jangan mencampur perkakas Debian dengan venv Windows; tidak ada interop
  lintas OS.
- Tanpa Microsoft Word, DOCX tetap dapat dibangun tetapi `build.sh` gagal
  mengekspor PDF.
- `word_finalize.py` hanya berfungsi penuh di Windows. Di Debian skrip itu
  melewati Word dan hanya membersihkan settings DOCX.

Lihat juga [debian.md](debian.md) untuk deployment Linux/Debian.
