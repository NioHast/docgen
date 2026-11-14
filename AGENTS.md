# AGENTS.md

## DOCX authoring

- Sumber kebenaran: `document.md`, `references.bib`, `istilah.tsv`, dan `gambar/`;
  DOCX dan PDF adalah artefak build.
- Satu dokumen adalah satu `document.md`; tidak ada mode folder atau file bab
  terpisah. Setiap Heading 1 harus cocok dengan urutan `body` pada
  `structure.yml`.
- Jangan menulis nomor bab, tabel, gambar, atau persamaan secara manual.
- Tabel wajib memiliki baris `: Judul tabel`. Gambar wajib memiliki alt text
  non-kosong.
- Jangan mengarang sitasi. Tulis `TODO-SITASI: <klaim>`.
- Jangan menebak istilah. Tulis `{{?istilah?}}` sampai diputuskan.
- Jangan memakai em dash.
- Output ditulis di samping `document.md`. Jangan menyunting output build.

## Deck authoring

- Sumber kebenaran: `deck.yaml`, `copy.yaml`, `transcripts.md`, `assets/`, dan
  `diagrams/`; PPTX, PDF, dan Slides adalah artefak build.
- Satu deck adalah satu `deck.yaml`; tidak ada include, partial, atau file slide
  terpisah.
- Jangan memakai absolute positioning atau koordinat. Geometri berasal dari
  layout preset atau `layout: custom` dengan `rows` dan `span` pada grid 12
  kolom.
- Jangan memakai `callout`. Block type resmi tepat 11: `text`, `bullets`,
  `image`, `table`, `chart`, `code`, `quote`, `diagram`, `divider`, `spacer`,
  dan `metric`.
- Tabel dan chart wajib native di PPTX dan Google Slides, bukan gambar. Chart
  hanya `bar`, `line`, atau `donut`; tabel tidak boleh memakai merged cell.
- ID slide wajib stabil, unik, dan berpola `^s[0-9]{2,}$`. Jangan mengubah ID
  saat reorder; key dibentuk dari ID slide dan ID block.
- Transkrip dan copy adalah konfigurasi sumber: `transcripts.md` memuat tepat
  satu bagian per slide, dan `copy.yaml` mengatur rule checker. Error copy atau
  transkrip menghentikan build.
- Jangan menulis warna, font, ukuran, margin, padding, atau path absolut di
  YAML. Semua path aset relatif terhadap `deck.yaml` dan memakai `/`.
- `notes` adalah plain text dan bukan transkrip.

## Permukaan edit

- DOCX: `document.md`, `references.bib`, `istilah.tsv`, dan `gambar/`.
- Deck: `deck.yaml`, `copy.yaml`, `transcripts.md`, `assets/`, dan `diagrams/`.
- Output build (`.laporan/`, `.laporan-build/`, `.autooffice/`,
  `.autooffice-build/`, `out/`, DOCX, PDF, dan PPTX) tidak boleh disunting.

## Perintah

```bash
uv run autooffice check document.md
uv run autooffice build document.md --target docx
uv run autooffice build document.md --target docx,pdf
uv run autooffice check examples/demo-deck/deck.yaml
uv run autooffice build examples/demo-deck/deck.yaml --target pptx,pdf
uv run autooffice doctor
```

`pdf` memerlukan Word/PowerPoint di Windows. `slides` memerlukan extra `google`
dan kredensial OAuth. Tambahkan `--terms` untuk gate glosarium DOCX,
`--dry-run` untuk validasi tanpa output, dan `--keep-intermediate` untuk
menyimpan intermediate.

## Larangan

- Jangan mengubah `src/**`, `tests/**`, `pyproject.toml`, `tools/**`, atau
  `docs/contracts/**` saat tugasnya hanya menulis naskah atau deck.
- Jangan mengubah output build atau state Google.
- Jangan memperbaiki naskah dengan menyunting DOCX atau PPTX. Perbaiki Markdown
  atau YAML lalu build ulang.
- Jangan menghapus `docgen` atau `deck-studio` sebelum parity/acceptance lulus.

## Definition of done

- Jalankan `uv run python tools/quality/gate.py`.
- Jangan commit atau push jika gate gagal.
- Perbarui test dan docs yang terdampak.
- Jangan mengubah file di luar scope tanpa izin.

## Dokumentasi

- [docs/user/quickstart.md](docs/user/quickstart.md),
  [docs/user/document-format.md](docs/user/document-format.md)
- [docs/user/deck-authoring.md](docs/user/deck-authoring.md),
  [docs/user/cli.md](docs/user/cli.md)
- [docs/dev/README.md](docs/dev/README.md),
  [docs/learn/README.md](docs/learn/README.md)
- [docs/contracts/README.md](docs/contracts/README.md),
  [docs/decisions/README.md](docs/decisions/README.md)

## Peta audiens dokumentasi

- `AGENTS.md` (root): instruksi untuk AI agent.
- `docs/user/`: panduan pengguna dan penulis `document.md` serta `deck.yaml`.
- `docs/dev/`: dokumentasi teknis yang mencakup arsitektur, kontrak, pipeline,
  dan detail implementasi.
- `docs/learn/`: materi konsep DeckIR, layout, design system, dan copy.
- `docs/contracts/`: kontrak normatif.
- `docs/decisions/`: ADR.

## AutoOffice execution

- Sumber rencana: `AUTO_OFFICE_PLAN.md`. Jangan menyimpang dari plan tanpa ADR.
- Eksekusi end-to-end F0 sampai F3. Jangan berhenti di F0 tanpa alasan yang dicatat.
- Maksimalkan paralelisme file-disjoint. Satu owner per file atau glob.
- Contracts before code. Tidak ada lane fitur sebelum F0 lulus.
- Setiap masalah yang diselesaikan saat eksekusi dicatat di
  `AUTO_OFFICE_EXECUTION_LOG.md`.
- Log ditulis oleh scribe/orchestrator, bukan oleh lane yang sedang bekerja.
- Format entri log: tanggal, fase/lane, masalah, resolusi, efek samping, catatan,
  file yang berubah.
- Keputusan yang mengubah kontrak wajib punya ADR di `docs/decisions/`.
- Jangan commit atau push bila gate lane gagal.
- Bahasa: prosa Indonesia, identifier dan kode Inggris.

## Python 3.15 style

- Target minimum Python 3.15; jangan menulis jalur kompatibilitas untuk versi
  lama.
- Jangan memakai `from __future__ import annotations`. PEP 649/749 membuat
  anotasi dievaluasi secara deferred secara default.
- Jangan memakai alias typing warisan (`List`, `Dict`, `Optional`, `Union`,
  `Type`, `Callable`, dan sejenisnya). Gunakan builtin, `collections.abc`, serta
  `X | None` dan `X | Y`.
- Gunakan `datetime.now(UTC)`, bukan `datetime.utcnow()`.
- Jalankan `uv run python tools/quality/gate.py` sebelum commit.
