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
- Jangan menambahkan kembali nama package, entry point, path, atau alat lama.
  Permukaan resmi hanya `autooffice`, `tools/quality/`, `tools/install_fonts.py`,
  `tools/visual/`, dan `tools/mutation/`.

## Definition of done

- Jalankan `uv run python tools/quality/gate.py`.
- Jangan commit atau push jika gate gagal.
- Perbarui test dan docs yang terdampak.
- Jangan mengubah file di luar scope tanpa izin.

## Invarian engineering

Aturan berikut berlaku untuk semua perubahan kode dan test. Aturan eksekusi dan
log AutoOffice di bawah tetap berlaku.

1. **Identifier Inggris.** Nama variabel, fungsi, kelas, parameter, field, dan
   nama test wajib ditulis dalam bahasa Inggris. Komentar, docstring, output
   CLI, dan prosa fixture boleh memakai bahasa Indonesia.
2. **Komentar hanya perilaku saat ini.** Komentar dan docstring menjelaskan
   perilaku kode sekarang. Jangan menyebut fase atau tiket rencana (`F0`, `F1`,
   `P1`, `Plan 1`, `Rencana`, `Tahap`, `Fix`, `Step`, `Milestone`, `Sprint`,
   `Iterasi`) maupun `legacy`. Riwayat keputusan dan alasan perubahan masuk ADR
   atau `AUTO_OFFICE_EXECUTION_LOG.md`, bukan komentar kode.
3. **Input wajib gagal keras.** Tidak boleh ada fallback diam-diam untuk input
   wajib. Input yang hilang, kosong, atau tidak valid harus melempar error
   domain atau keluar dengan kode bukan nol; jangan memakai nilai default, `or`,
   `get(..., default)`, atau jalur alternatif tersembunyi. Fallback hanya boleh
   untuk kondisi opsional, dan harus eksplisit, terdokumentasi, serta diuji.
4. **Coverage key harus terlihat.** Setiap coverage key wajib memetakan ke
   elemen yang benar-benar dirender dan terlihat di artefak akhir. Key yang
   hanya ada di metadata, notes, YAML, model internal, atau bookkeeping renderer
   dilarang. Coverage harus diekstrak ulang secara independen dari artefak final
   (DOCX, PPTX, atau PDF), bukan dari maksud build atau state renderer. Key
   hilang, key asing, key duplikat, atau teks terlihat tanpa key adalah
   kegagalan.
5. **Test di boundary, fake lebih dulu.** Patch hanya di boundary eksternal
   (COM, Google, subprocess, jaringan, waktu); jangan mem-patch kolaborator
   internal. Utamakan fake yang menjaga perilaku nyata di atas mock yang
   memeriksa koreografi panggilan. Setiap test perbaikan bug wajib gagal bila
   perbaikan produksi dikembalikan; buktikan dengan revert sementara, lalu
   pulihkan perbaikan.
6. **Golden visual dan mutation untuk modul kritis.** Perubahan yang menyentuh
   output visual wajib punya golden test visual untuk artefak final (DOCX,
   PPTX, PDF). Modul kritis wajib tercakup konfigurasi mutation testing di
   `tools/mutation/` dan dijalankan saat modul itu berubah atau pada gate akhir.
   Mutant yang bertahan harus ditutup dengan assertion baru atau didokumentasikan
   sebagai equivalent mutant.
7. **Gate sebelum commit.** Sebelum commit, jalankan
   `uv run python tools/quality/gate.py`. Jangan commit atau push bila gate
   gagal.

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
