# design-system-format-laporan

Template dan pipeline pembuatan laporan akademik berbasis Markdown, Pandoc,
Typst (PDF), dan DOCX.

## Build

```bash
bash build.sh       # Laporan.pdf
bash build-docx.sh  # Laporan.docx
```

## Dependensi modul istilah DOCX

Build DOCX memakai `tools/istilah.py` untuk memberi style istilah asing dan
memproses penanda `{{?istilah?}}`. Modul ini memerlukan `python-docx` dan
`lxml`.

Pasang dependensinya dari akar proyek:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r tools\requirements.txt
```

Di Linux/macOS gunakan `.venv/bin/python`. `build-docx.sh` otomatis memakai
`.venv/Scripts/python.exe` bila ada; jika tidak, ia memakai `python`.

Kalau dependensi belum terpasang, `build-docx.sh` berhenti sebelum Pandoc
dengan pesan yang meminta:

```bash
pip install -r tools/requirements.txt
```

Dokumentasi lengkap modul ada di [`docs/istilah.md`](docs/istilah.md).
