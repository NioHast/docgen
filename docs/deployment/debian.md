# Deployment Debian (native)

Panduan ini hanya memakai toolchain **Debian-native**. Build DOCX dan PDF
berjalan sepenuhnya dengan perkakas Debian; tidak ada interop lintas OS.

## Prasyarat

```bash
sudo apt update
sudo apt install -y \
  bash git python3 python3-venv python3-pip \
  pandoc poppler-utils libreoffice-writer
```

| Kebutuhan | Keterangan |
| --- | --- |
| `bash`, `git` | Shell dan checkout repo. |
| `python3`, `python3-venv`, `python3-pip` | Pipeline DOCX dan preprocessing PDF. |
| `pandoc` | Konversi Markdown ke DOCX/PDF. |
| Typst | Mesin PDF. Pasang binary native dari [typst.app](https://typst.app/) atau `cargo install typst-cli`, lalu pastikan `typst --version` berhasil. |
| `poppler-utils` | Menyediakan `pdfinfo` dan `pdftotext` untuk `scripts/docx-pagenum.py`. |
| `libreoffice-writer` | Menyediakan `soffice` untuk menghitung nomor halaman TOC DOCX. |
| ImageMagick | Opsional, untuk membersihkan alpha PNG saat build PDF. |

Microsoft Word tidak tersedia di Debian dan tidak dipasang. Finalisasi field
Word, bila diperlukan, dilakukan di Windows setelah DOCX dibawa ke sana.

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements.txt
```

## Build

```bash
bash build-docx.sh   # Laporan.docx
bash build.sh        # Laporan.pdf
```

Kedua skrip memilih Python native Linux secara berurutan:

1. `LAPORAN_PYTHON` bila diisi;
2. `.venv/bin/python` bila ada;
3. `python3`, lalu `python`, dari `PATH`.

Contoh override:

```bash
LAPORAN_PYTHON=/usr/bin/python3 bash build.sh
LAPORAN_PYTHON=/usr/bin/python3 bash build-docx.sh
```

## DOCX di Debian

- `build-docx.sh` **tidak** memanggil `tools/word_finalize.py` di Linux.
  Build mencetak warning bahwa finalisasi field Word dilewati.
- `scripts/finalize-docx.py --in-place` tetap dijalankan untuk menghapus
  `w:updateFields` dan menormalkan settings DOCX.
- Nomor halaman TOC diisi oleh `scripts/docx-pagenum.py` memakai
  LibreOffice (`soffice --headless`) dan Poppler (`pdfinfo`, `pdftotext`).
  Tanpa keduanya, cache halaman TOC tetap `0` sampai field diperbarui di
  Word atau LibreOffice.
- `tools/word_finalize.py` tetap bisa dijalankan manual di Debian; skrip itu
  mendeteksi platform, melewati Word, dan hanya membersihkan settings:

  ```bash
  .venv/bin/python tools/word_finalize.py Laporan.docx
  ```

## Batasan

- Jangan memanggil executable Windows atau path Windows dari Debian.
- Gunakan Pandoc dan Typst native dari `PATH`; `tools/env.sh` tidak mencari
  executable atau lokasi instalasi Windows.
- Word hanya boleh dipakai di Windows untuk finalisasi field. Di Debian,
  gunakan LibreOffice untuk pratinjau dan biarkan cache TOC apa adanya.

Lihat juga [windows.md](windows.md) untuk deployment Windows.
