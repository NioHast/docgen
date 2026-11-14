# AutoOffice

AutoOffice adalah pipeline dokumen dan presentasi dari satu sumber teks:
**DOCX dari Markdown** dan **PPTX/Slides dari YAML**. Pipeline DOCX memakai
Pandoc lalu merapikan package Word; pipeline deck memakai DeckIR, layout grid
12 kolom, serta tabel dan chart native di PowerPoint dan Google Slides. Deck
dapat disinkronkan ke Google Slides, sedangkan PDF diekspor lewat Microsoft
Word atau PowerPoint di Windows.

## Prasyarat

- **Python 3.15** dan **uv**. Jalankan `uv sync --extra dev` sekali dari akar
  repo. Tambahkan `--extra google` untuk target Slides dan `--extra windows`
  untuk artefak final PPTX/PDF lewat COM.
- **Pandoc** dengan `--citeproc` untuk DOCX dari Markdown.
- **Mermaid CLI (`mmdc`)** bila dokumen atau deck memakai diagram Mermaid.
  Pasang Node.js lalu jalankan `npm install -g @mermaid-js/mermaid-cli`.
- **Windows dengan Microsoft PowerPoint desktop** untuk final `pptx` dan
  `pdf` dari deck. Final `pptx` menanam font Plus Jakarta Sans lewat
  PowerPoint COM; `pdf` diekspor lewat PowerPoint COM. PDF dari Markdown
  memakai Microsoft Word desktop. Semua jalur COM membutuhkan `pywin32` dari
  `uv sync --extra windows`. Word Online atau PowerPoint Online tidak
  menyediakan COM.
- **Google credentials** dan OAuth untuk target `slides`: extra `google`,
  client OAuth, dan izin Drive/Sheets/Slides.
- **Linux/macOS**: `check` dan build DOCX dapat dijalankan selama Python,
  Pandoc, dan `mmdc` tersedia. Final PPTX dan PDF memerlukan Windows karena
  penanaman font dan ekspor memakai Office COM.

## Quickstart

DOCX dari Markdown. Siapkan `document.md` dengan front matter. Di Windows
dengan Word terpasang:

```bash
uv run autooffice build document.md --target docx,pdf
```

`pdf` memerlukan Word COM di Windows. Tanpa Word, termasuk di Linux/macOS,
gunakan `--target docx`. Rincian front matter ada di
[docs/user/document-format.md](docs/user/document-format.md).

Deck dari YAML. Contoh demo sudah berisi 24 slide. `check` berjalan di semua
platform; final `pptx` dan `pdf` memerlukan Windows dengan Microsoft PowerPoint
desktop dan `pywin32` (`uv sync --extra windows`). Final `pptx` menanam font
lewat PowerPoint COM.

```bash
uv run autooffice check examples/demo-deck/deck.yaml
uv run autooffice build examples/demo-deck/deck.yaml --target pptx,pdf
```

Hasil ditulis ke `examples/demo-deck/out/`. Target `slides` memerlukan extra
`google` dan kredensial OAuth. Langkah lengkap ada di
[docs/user/quickstart.md](docs/user/quickstart.md).

## Peta repo

| Path | Isi |
| --- | --- |
| `src/autooffice/docx/` | Pipeline DOCX: loader, stage, API package, dan terms. |
| `src/autooffice/deck/` | Model DeckIR, compiler, layout, renderer PPTX, chart, copy, dan transcript. |
| `src/autooffice/design/` | Token, theme, font, dan kontras. |
| `src/autooffice/google/` | Sinkronisasi Sheets/Slides dan state Google. |
| `src/autooffice/pdf/` | Ekspor PDF lewat Word/PowerPoint COM. |
| `src/autooffice/cli/` | Entry point `autooffice`, target, check, doctor, dan output. |
| `examples/` | Contoh DOCX dan `demo-deck`. |
| `docs/` | Panduan pengguna, developer, learn, kontrak, dan ADR. |
| `tools/` | Quality gate, checker, installer font, dan smoke visual. |

## Kualitas

```bash
uv run python tools/quality/gate.py
python tools/quality/check_docs.py
python tools/quality/check_python.py
```

`gate.py` menjalankan format, lint, type check, import contracts, test,
coverage, lock, docs, test quality, no-legacy, dan Python style. Ketiga perintah
di atas tidak memanggil Word/PowerPoint COM atau Google.

## Dokumentasi

- [docs/user/quickstart.md](docs/user/quickstart.md): alur DOCX dan deck.
- [docs/user/deck-authoring.md](docs/user/deck-authoring.md): authoring `deck.yaml`.
- [docs/dev/README.md](docs/dev/README.md): arsitektur, pipeline, testing, gate.
- [docs/learn/README.md](docs/learn/README.md): konsep DeckIR, layout, design system.
- [docs/contracts/README.md](docs/contracts/README.md): kontrak normatif F0.
- [docs/decisions/README.md](docs/decisions/README.md): ADR keputusan.
- [docs/README.md](docs/README.md): indeks seluruh dokumentasi.

## Lisensi

MIT. Sebagian kaidah prosa dalam panduan berasal dari proyek naskah-id (MIT,
Copyright (c) 2026 nothinx). Teks lisensi lengkap ada di [`LICENSE`](LICENSE).
