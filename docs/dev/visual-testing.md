# Visual Testing PPTX

Harness ini adalah smoke test visual untuk renderer PPTX. Tujuannya membuktikan
bahwa PowerPoint dapat membuka PPTX hasil `PptxRenderer` dan mengekspor setiap
slide menjadi PNG. Pixel diff terhadap golden image belum dilakukan di tahap
ini.

## Prasyarat

- Windows dengan Microsoft PowerPoint desktop terpasang.
- `pywin32` tersedia di environment, misalnya lewat `uv sync --extra windows`.
- Font Plus Jakarta Sans terpasang agar hasil visual mendekati artefak final.

Di non-Windows, tanpa `pywin32`, atau tanpa PowerPoint, `render_slides`
melempar `PdfUnavailableError`. Test menangkap error itu dan melakukan skip
dengan alasan eksplisit, bukan skip diam-diam. Gate visual final dapat
menaikkan perilaku ini menjadi gagal.

## API

`tools/visual/render_pptx.py` menyediakan:

```python
from pathlib import Path

from tools.visual.render_pptx import render_slides

pngs = render_slides(Path("deck.pptx"), Path("out"), width=1280, height=720)
```

Perilaku `render_slides(pptx, out_dir, *, width=1280, height=720)`:

- validasi path PPTX dan direktori output;
- membuka PPTX secara read-only lewat COM PowerPoint;
- mengekspor setiap slide dengan `Slide.Export` ke `slide-001.png`,
  `slide-002.png`, dan seterusnya;
- menutup presentasi, quit PowerPoint, lalu membersihkan PID PowerPoint yang
  dibuat automation;
- mengembalikan tuple path PNG absolut setelah memastikan setiap berkas ada
  dan tidak kosong.

Harness memakai ulang `com_lock`, `com_apartment`, watchdog, dan
`PowerPointProcessTracker` dari `autooffice.pdf.com`. Lock COM sama dengan
ekspor PDF, sehingga Word dan PowerPoint tidak berjalan bersamaan. Detail
guard ada di [COM Word dan PowerPoint](com.md).

## Test

```bash
uv run pytest tests/visual -q
```

Test membangun deck dua slide lewat `PptxRenderer`, merender PNG 1280x720,
lalu memeriksa:

- jumlah PNG sama dengan jumlah slide;
- ukuran setiap PNG 1280x720;
- berkas PNG tidak kosong;
- piksel tidak seragam, memakai Pillow.

## Batas smoke test

- Belum membandingkan gambar dengan golden PNG.
- Pixel diff, threshold, dan mask area adalah langkah berikutnya.
- Perbedaan versi PowerPoint atau font harus dilaporkan saat pixel diff
  ditambahkan, bukan diabaikan.
- Harness tidak memakai jaringan dan tidak menambahkan jeda tidur.
- Renderer produksi tidak diubah oleh harness ini.

## Verifikasi tambahan

```bash
uv run ruff check tools/visual tests/visual
uv run mypy tools/visual tests/visual
python tools/quality/check_docs.py
```
