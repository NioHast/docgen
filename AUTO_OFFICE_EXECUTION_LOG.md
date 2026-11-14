# AutoOffice Execution Log

Log ini mencatat masalah yang muncul saat eksekusi plan, resolusi yang diambil, efek sampingnya, dan catatan penting. Entri ditulis oleh scribe/orchestrator setelah lane melapor.

## Format

- Tanggal:
- Fase/lane:
- Masalah:
- Resolusi:
- Efek samping:
- Catatan:
- File yang berubah:

## 2026-11-14 - F0 contract freeze dan scaffold

- Fase/lane: F0-CONTRACTS, branch `autooffice/f0-contracts`.
- Masalah:
  - Belum ada package `autooffice`, kontrak, scaffold, atau gate import.
  - Scaffold awal memakai bentuk `DeckIR`, `BlockSpec`, `LayoutSpec`, `Theme`, dan renderer protocol yang berbeda dari dokumen kontrak.
  - Theme token belum mencakup radius, shadow, code, ukuran slide, row gap, tracking, dan divider.
  - `.autooffice/**` dan `.autooffice-build/**` belum di-ignore.
  - Import-linter baru menegakkan dua kontrak, belum seluruh domain.
  - Dokumen ownership, acceptance table, dan execution log belum lengkap.
- Resolusi:
  - Bentuk kanonik dibekukan: `DeckIR(schema, meta, theme_name, slides, keys)`, `SlideIR(..., order, source)`, `BlockIR(..., span, role)`, `BlockSpec(..., allowed_in_preset)`, `LayoutSpec(..., rows berisi slot ID)`, `PlacedBlock` dengan EMU, `Theme` dengan colors/chart/typography/grid/spacing/radius/shadow/code, `RenderRequest`/`RenderResult`.
  - Mapping dibuat read-only dengan `MappingProxyType`; dataclass frozen dan slots.
  - Theme token dilengkapi: radius, shadow, code, slide width/height, row gap, tracking, divider.
  - Static layout registry dipertahankan untuk F0; discovery diserahkan ke F1-LAYOUT.
  - `docgen` entry point dipertahankan sampai parity F1-DOCX, dicatat sebagai transitional exception.
  - Import-linter diperluas menjadi 17 kontrak; `.gitignore` diperbarui; ownership dan acceptance table direkonsiliasi.
- Efek samping:
  - F1 worker wajib memakai bentuk kanonik ini; perubahan setelah F0 memerlukan ADR.
  - `docgen` dan `autooffice` hidup berdampingan sampai F1-DOCX parity.
  - Registry layout masih statis sampai F1-LAYOUT menggantinya dengan discovery.
- Catatan gate:
  - `uv run pytest tests/contract -q`: 73 passed.
  - `uv run ruff check ...`: All checks passed.
  - `uv run ruff format --check ...`: 28 files already formatted.
  - `uv run mypy src/autooffice`: Success, 26 source files.
  - `uv run lint-imports`: 17 kept, 0 broken.
  - `python tools/dev/check_docs.py`: 97 documents, 679 links, 23 TOCs, 0 broken.
  - `uv run python -c "import autooffice"`: 0.1.0.
  - `uv run autooffice --help`: exit 0.
  - `git diff --check`: clean.
- File yang berubah:
  - `AGENTS.md`, `AUTO_OFFICE_PLAN.md`, `AUTO_OFFICE_EXECUTION_LOG.md`, `.gitignore`, `pyproject.toml`, `docs/README.md`.
  - `docs/contracts/**` (18 kontrak), `docs/decisions/**` (6 ADR + index), `docs/learn/README.md`.
  - `src/autooffice/**` (scaffold package, CLI minimal, registry, model/layout/design/render contract shapes, package markers).
  - `tests/contract/**` (73 test), `tools/quality/check_no_legacy.py`.

## 2026-11-14 - F0 selesai, siap review final

- Fase/lane: F0-CONTRACTS.
- Masalah: Review awal menemukan 21 isu; review kedua menemukan 6 isu lanjutan pada Theme, order test, ownership, acceptance table, README, dan log.
- Resolusi: Semua isu ditutup; gate F0 hijau; menunggu review final sebelum commit dan merge ke `autooffice/integration`.
- Efek samping: F1 belum boleh mulai sebelum review final PASS.
- Catatan: F0 masih di branch `autooffice/f0-contracts`, belum di-commit.
  - Gate final: 74 contract test lulus; ruff check/format lulus; mypy 26 file lulus; import-linter 17 kept, 0 broken; docs 97 dokumen, 679 tautan, 23 TOC, 0 broken; `autooffice --help` exit 0.
- File yang berubah: `AUTO_OFFICE_EXECUTION_LOG.md` (entri ini), `AGENTS.md`, `.gitignore`, `AUTO_OFFICE_PLAN.md`, `docs/README.md`, `docs/learn/README.md`, `docs/contracts/README.md`, `docs/contracts/ownership.md`, `docs/contracts/design-token.md`, `docs/contracts/cli.md`, `docs/contracts/copy.md`, `docs/contracts/google-state.md`, `docs/contracts/transcript.md`, `docs/contracts/coverage.md`, `docs/contracts/test-quality.md`, `src/autooffice/design/theme.py`, `src/autooffice/deck/model/deck_ir.py`, dan `tests/contract/test_contract_shapes.py`.

## 2026-11-14 - F0 PASS, siap commit dan merge

- Fase/lane: F0-CONTRACTS.
- Masalah: Tidak ada; seluruh temuan review sudah ditutup.
- Resolusi: F0 dibekukan pada branch `autooffice/f0-contracts`, siap commit dan merge ke `autooffice/integration`.
- Efek samping: F1 boleh mulai setelah merge; bentuk kontrak kanonik tidak boleh berubah tanpa ADR.
- Catatan: Gate final hijau. `docgen` tetap hidup sampai parity F1-DOCX.
- File yang berubah: `AUTO_OFFICE_EXECUTION_LOG.md` pada entri ini.

## 2026-11-14 - F0 merged, F1 dimulai

- Fase/lane: transisi F0 ke F1.
- Masalah: Tidak ada. F0 sudah PASS dan gate hijau.
- Resolusi: F0 di-commit sebagai `3b4ab27`, merge ke `autooffice/integration` sebagai `147a4de`, dan kedua branch di-push ke origin.
- Efek samping: `autooffice` dan `docgen` hidup berdampingan. F1 mulai di branch `autooffice/f1`.
- Catatan: Lane F1 yang aktif: dependencies (python-pptx/google/windows), design token/font, model/compiler deck, dan port DOCX. Lane layout, PPTX renderer, copy checker, test infra, dan CLI menyusul setelah dependency-nya siap.
- File yang berubah: `AUTO_OFFICE_EXECUTION_LOG.md` (entri ini).

## 2026-11-14 - check.ps1 dihapus, word.ps1 menunggu F2-PDF

- Fase/lane: F1 quality/CLI transition.
- Masalah: Gate lokal masih memakai PowerShell wrapper, padahal `tools/quality/gate.py` sudah tersedia.
- Resolusi: `scripts/check.ps1` dihapus; semua referensi aktif diarahkan ke `gate.py`.
- Efek samping: `scripts/word.ps1` tetap ada sampai adapter COM Python F2-PDF selesai; menghapusnya sekarang akan memutus PDF DOCX.
- Catatan: `word.ps1` dijadwalkan dihapus setelah `src/autooffice/pdf/word.py` dan test fake COM lulus.
- File yang berubah: `scripts/check.ps1` (dihapus), `AGENTS.md`, `docs/dev/testing.md`, `docs/dev/quality-gates.md`, `scripts/README.md`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - SlotSpec span untuk preset asimetris

- Fase/lane: F1-LAYOUT / F2 preset preparation.
- Masalah: SlotSpec tidak punya span; preset hanya bisa membagi kolom rata.
- Resolusi: Tambah SlotSpec.span (default 1), validasi row sum <= 12, dan ADR 0007.
- Efek samping: Preset F2 harus mengisi span per slot; custom tetap memakai span block.
- Catatan: Perubahan kontrak pasca-F0, dicatat sebagai ADR.
- File yang berubah: `src/autooffice/deck/layout/spec.py`, `grid.py`, `slot.py`, `tests/deck/layout/**`, `docs/contracts/layout-spec.md`, `docs/decisions/0007-slot-span.md`, `docs/decisions/README.md`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - AutoOffice DOCX beralih ke Word COM Python

- Fase/lane: F2-PDF / F1-DOCX integration.
- Masalah: AutoOffice DOCX masih memanggil `scripts/word.ps1`.
- Resolusi: Stage office AutoOffice memakai `autooffice.pdf.word`; PowerShell hanya tersisa untuk docgen legacy.
- Efek samping: `word.ps1` tetap ada sampai F3 menghapus docgen.
- Catatan: Tidak ada subprocess PowerShell di AutoOffice.
- File yang berubah: `src/autooffice/docx/stages/office.py`, `tests/docx/**`, `scripts/README.md`, `docs/dev/pdf.md`, `docs/dev/com.md`, log.

## 2026-11-14 - Keputusan layout media

- Fase/lane: F2 preset layout.
- Masalah: `image-full` dan `diagram` full-width tidak bisa memakai tinggi natural 16:9 karena melebihi area konten; `LayoutSpec` juga tidak punya overlay/z-index.
- Resolusi: Media block memakai tinggi yang tersedia (contain), bukan tinggi natural tetap. `image-full` dirender sebagai gambar full-width dengan judul di atas, tanpa overlay absolut. Overlay preset ditunda; tidak ada posisi absolut dari author.
- Efek samping: Gambar bisa letterbox; visual `image-full` tidak identik dengan full-bleed deck-studio.
- Catatan: Jika overlay preset dibutuhkan, tambahkan kontrak `SlotSpec.overlay` lewat ADR, bukan absolute positioning.
- File yang berubah: `AUTO_OFFICE_EXECUTION_LOG.md` (entri ini).

## 2026-11-14 - LayoutSpec.min_one_of

- Fase/lane: F1-LAYOUT / F2 preset.
- Masalah: required per slot tidak bisa menyatakan minimal satu dari beberapa slot.
- Resolusi: Tambah LayoutSpec.min_one_of dan validasi slide; preset toc/kpi memakainya.
- Efek samping: Layout lain tidak berubah; kontrak berubah lewat ADR 0008.
- Catatan: Test F0 registry diubah dari urutan statis ke set discovery.
- File yang berubah: `src/autooffice/deck/layout/spec.py`, `slot.py`, `presets/toc.py`, `presets/kpi.py`, tests, docs, log.

## 2026-11-14 - Media contain height diterapkan

- Fase/lane: F1-LAYOUT.
- Masalah: Media block memakai tinggi natural 16:9 dan overflow pada image-full/diagram.
- Resolusi: `measure_block` menerima `max_height_emu`; media memakai tinggi tersedia (contain).
- Efek samping: Gambar bisa letterbox; tinggi media tidak lagi natural.
- Catatan: Tidak ada posisi absolut.
- File yang berubah: `measure.py`, `overflow.py`, tests, `docs/contracts/layout-spec.md`, log.

## 2026-11-14 - Riset Python 3.15 dan checker gaya

- Fase/lane: code quality.
- Masalah: 88 file memakai `from __future__ import annotations` padahal target Python 3.15; PEP 649/749 membuatnya tidak perlu.
- Resolusi: Dokumentasi anti-pattern + checker `tools/quality/check_python.py`.
- Efek samping: Checker akan gagal sampai lane pembersihan menghapus 88 import.
- Catatan: Tidak ada perubahan kode produksi pada entri ini.
- File yang berubah: `docs/dev/python-315-style.md`, `tools/quality/check_python.py`, `tests/tools/test_python_style.py`, `tools/quality/gate.py`, `tests/tools/test_quality_tools.py`, docs index, log.

## 2026-11-14 - Cleanup from __future__ import annotations

- Fase/lane: code quality / Python 3.15.
- Masalah: 108 file memakai `from __future__ import annotations` padahal target 3.15 dan PEP 649 sudah default.
- Resolusi: Hapus semua future import non-Google; aturan AGENTS.md dan step gate `python-style` ditambahkan.
- Efek samping: Anotasi sekarang memakai deferred evaluation PEP 649; tidak ada stringization PEP 563.
- Catatan: File Google dibersihkan setelah lane Google selesai; gate `python-style` baru blocking setelah itu.
- File yang berubah: `src/autooffice/**` dan `tests/**` non-Google, `AGENTS.md`, `docs/dev/quality-gates.md`, log.

## 2026-11-14 - Python 3.15 cleanup selesai, gate blocking

- Fase/lane: code quality.
- Masalah: 108 file memakai `from __future__ import annotations`; test checker saling menimpa nama modul.
- Resolusi: Semua future import dihapus; tools/dev dan tools/quality menjadi package; gate python-style blocking.
- Efek samping: Tidak ada; anotasi memakai PEP 649.
- Catatan: 0 findings check_python; full pytest harus hijau.
- File yang berubah: Google files, tools packages, tests/conftest.py, test imports, gate.py, docs, log.

## 2026-11-14 - SlideIR.rows eksplisit

- Fase/lane: F1-MODEL/F2-CUSTOM-GRID.
- Masalah: Row custom di-flatten ke blocks; batas row direkonstruksi heuristik.
- Resolusi: SlideIR.rows menyimpan block ID per row; compiler mengisi; custom planner memakainya.
- Efek samping: SlideIR berubah lewat ADR 0009; preset tetap rows=().
- Catatan: Partial row unkeyed kini deterministik.
- File yang berubah: deck_ir.py, compiler.py, custom.py, tests, docs, log.

## 2026-11-14 - Font embedding via PowerPoint COM

- Fase/lane: F1-PPTX/F2-PDF.
- Masalah: Font embedding masih deferred; PPTX hanya membawa nama font.
- Resolusi: `embed_fonts` memakai PowerPoint SaveAs/SaveCopyAs dengan EmbedTrueTypeFonts=msoTrue; CLI memanggilnya untuk PPTX/PDF.
- Efek samping: Final PPTX embedding Windows-only; Slides tetap Google Fonts.
- Catatan: Verifikasi `ppt/fonts/*.fntdata` dan `embeddedFontLst`.
- File yang berubah: `src/autooffice/pdf/powerpoint.py`, `src/autooffice/cli/build.py`, tests, docs, log.

## 2026-11-14 - Acceptance build demo deck

- Fase/lane: F2/F3 acceptance.
- Masalah: Font harus terpasang sebelum PowerPoint COM bisa embed; belum ada installer Python.
- Resolusi: `tools/install_fonts.py` per-user, doctor check, build demo PPTX+PDF.
- Efek samping: PPTX/PDF final Windows-only untuk embedding; Slides memakai Google Fonts.
- Catatan: Verifikasi `ppt/fonts/*.fntdata`, `embeddedFontLst`, 24 slide, 24 halaman PDF.
- Hasil:
  - `deck.pptx`: 24 slide, 1,636,045 bytes, 6 `ppt/fonts/*.fntdata`, `embeddedFontLst` Plus Jakarta Sans + Cascadia Mono, tanpa timing/transition.
  - `deck.pdf`: 24 halaman, 722,424 bytes.
  - `deck.transcript.md`: 13,833 bytes.
  - Font install: 4 TTF per-user, idempotent, doctor 4/4.
- File yang berubah: tools, tests, cli/doctor, docs, plan, log.

## 2026-11-14 - Risk-based coverage policy

- Fase/lane: quality.
- Masalah: target 100% global tidak realistis dan tidak menjamin correctness.
- Resolusi: global 90%, critical 100%, adapter 85%, policy checker + ADR 0010.
- Efek samping: gate tidak lagi menuntut 100% global; modul kritis tetap 100%.
- Catatan: mutation/property/visual tests menyusul.
- File yang berubah: check_coverage.py, gate.py, pyproject, coverage.md, ADR 0010, tests, log.

## 2026-11-14 - Perbaikan correctness deck core

- Fase/lane: correctness review.
- Masalah: block ID source ambigu, URL malformed, teks invisible, URL tanpa host, link `)` terpotong, symlink loop.
- Resolusi: validasi baru dan test regresi.
- Efek samping: block ID `source` ditolak; URL tanpa host ditolak; teks kontrol ditolak.
- Catatan: Tidak ada perubahan kontrak produk.
- File yang berubah: schema.py, keys.py, markdown.py, tests, log.

## 2026-11-14 - Mutation testing setup

- Fase/lane: quality.
- Masalah: line/branch coverage tidak mengukur kekuatan assertion.
- Resolusi: mutation testing pada modul kritis memakai `cosmic-ray==8.9.0`. `mutmut==3.8.1` dicoba lebih dulu tetapi gagal dipasang di Python 3.15.2 Windows karena PyYAML 6.0.3 (lewat libcst) tidak punya wheel cp315 dan build sdist membutuhkan MSVC. Target dikonfigurasi di `tools/mutation/cosmic-ray.toml`: keys, bindings, layout spec, title_case, charts spec.
- Efek samping: tidak masuk gate default karena mahal; dijalankan manual/berkala.
- Catatan: smoke run `title_case` 81 mutant: 59 killed, 22 survived, 0 incompetent, skor 72,8%, runtime 4m22s. Survivor utama: assertion offset tidak diperiksa, batas first/last token, dan `continue` yang berubah menjadi `break`; sebagian survivor adalah equivalent mutant. Tidak ada production code atau test yang diubah untuk membunuh mutant.
- File yang berubah: `pyproject.toml`, `uv.lock`, `tools/mutation/*.toml`, `docs/dev/mutation-testing.md`, `docs/dev/README.md`, `docs/dev/references.md`, `docs/dev/test-quality.md`, log.

## 2026-11-14 - Perbaikan Google sync

- Fase/lane: correctness review Google.
- Masalah: payload Sheets chart invalid, 404/403 mapping salah, reuse staging basi, apply unknown, ownership slide, table marker, chart geometry, workbook persistence.
- Resolusi: payload valid, error mapping, state/reuse checks, ownership validation, preflight ordering, persist workbook lebih awal.
- Efek samping: push/pull lebih ketat; staging basi ditolak.
- Catatan: Live smoke tetap belum dijalankan tanpa kredensial.
- File yang berubah: google/**, tests/google/**, log.

## 2026-11-14 - Renderer findings A: chart caption, bobot font, validasi aset TTF

- Fase/lane: F1-PPTX renderer hardening.
- Masalah: caption chart dibuang tetapi dihitung coverage lewat metadata; bobot 600/800 tidak pernah memilih family SemiBold/ExtraBold; validasi aset font hanya membaca 4 byte header.
- Resolusi:
  - `render_chart` merender caption sebagai text box berkey `autooffice:key:<slide>.<block>.caption`; tinggi frame chart dikurangi tinggi caption + `sm`. `.caption` dihapus dari `_chart_keys()` sehingga coverage hanya lolos bila shape caption nyata ada.
  - `apply_run_style` memetakan 400/600/700/800 ke Regular/SemiBold/Bold/ExtraBold sesuai family TTF bundled, dengan fallback family dasar + bold dan warning bila family bobot tidak tersedia.
  - `font_files_for_theme` memakai `primary_typeface` (menerima stack) dan memvalidasi setiap TTF dengan hash SHA-256 dari `autooffice.design.fonts`.
- Test: caption chart native dan placeholder Slides, coverage gagal saat shape caption dihilangkan, typeface header/display/body di XML, fallback bobot, hash valid dan byte korup, family stack.
- Efek samping: family turunan yang tidak dikenal turun ke family dasar + bold dan mengembalikan warning; tidak ada fallback senyap.
- Catatan: tidak menyentuh `table.py`, `textbox.py`, `measure.py`, `pdf/**`, atau `media/**`.
- File yang berubah: `src/autooffice/deck/render/pptx/renderer.py`, `chart.py`, `shapes.py`, `fonts.py`, `tests/deck/render/pptx/*`, log.

## 2026-11-14 - Mermaid security dan correctness

- Fase/lane: media Mermaid hardening.
- Masalah: cache hanya memvalidasi delapan byte signature; cache hit menyalin PNG korup; penyalinan memakai nama temp prediktabel; timeout hanya membunuh proses `mmdc` langsung; ukuran sumber, output, dan waktu render tidak dibatasi; cache dicek setelah `mmdc` diwajibkan.
- Resolusi: validasi PNG lengkap (`IHDR`/`IDAT`/`IEND` plus CRC) dan hapus entri cache korup; `_copy_png` memakai `tempfile.mkstemp` di direktori target, menulis lewat descriptor, `fsync`, lalu `os.replace`; `mmdc` berjalan di process group baru (POSIX `start_new_session`, Windows `CREATE_NEW_PROCESS_GROUP` plus Job Object) dan seluruh pohon proses dihentikan saat timeout; batas 1.000.000 byte sumber, 64 KiB per stream output, timeout render 180 detik; lookup cache-first lewat sidecar metadata sehingga PNG cache valid dipakai tanpa `mmdc`.
- Efek samping: cache kini memiliki sidecar `mermaid-<sha256>.json`; cache key tetap memuat versi `mmdc`; output atau waktu berlebih menjadi `MermaidError` keras; Windows memakai Job Object dengan fallback `%SystemRoot%\System32\taskkill.exe /T`.
- Catatan: test pohon proses berjalan di Windows; test symlink di-skip bila OS tidak mengizinkan symlink. Smoke `mmdc` asli lulus.
- File yang berubah: `src/autooffice/deck/media/mermaid.py`, `tests/deck/media/test_mermaid.py`, `docs/contracts/mermaid.md`, log.

## 2026-11-14 - Layout review fixes: media starvation, code/table sizing, overflow leaves

- Fase/lane: F1-LAYOUT layout review.
- Masalah:
  - Media preset/custom memakai seluruh sisa tinggi sehingga row subtitle/credit/body setelahnya starvation.
  - `_measure_code_block` tidak menghitung filename dan gap.
  - Ukuran/bobot role text tidak sama dengan renderer; caption/label/kicker belum memakai `minimum_pt`.
  - Tabel belum menghitung margin sel vertikal `2 * sm` dan gap caption.
  - Overflow selalu memakai kandidat leaf pertama; media tanpa caption memakai `.caption` yang tidak ada di manifest.
  - Code memakai wrapping kata Plus Jakarta Sans sehingga spasi hilang dan lebar tidak konservatif.
  - Span bool/float/string lolos `LayoutSpec`; `assert_no_overflow` kehilangan konteks findings.
- Resolusi:
  - Planner preset/custom mereservasi tinggi minimum row berikutnya ditambah row gap sebelum meng-cap media. `image-full` dengan title+image+subtitle/credit dan custom span-12 image+body kini muat.
  - Code mengukur filename dengan body style dan gap `sm`; code memakai advance monospace konservatif `0.62 em`, pemecahan per karakter, tab 4 kolom, dan mempertahankan spasi awal/ganda.
  - Text memakai mapping role renderer: display/title/lead/body sesuai renderer, caption/label/kicker `minimum_pt`, bobot 400/600/700/800.
  - Tabel memakai lebar sel renderer (`column_width - 2 * sm`), margin vertikal `2 * sm` per header/body row, dan gap caption `sm`.
  - `BlockMeasurement` membawa leaf overflow aktual; planner memakai leaf itu untuk width/height dan fallback block-scoped `s01.image1` untuk media tanpa caption.
  - `LayoutSpec` menolak span bool/float/string dengan `LayoutSpecError`; `assert_no_overflow` membaca findings dari cache `WeakKeyDictionary` pada `LayoutPlan` tanpa mengubah field kontrak.
- Test:
  - `uv run pytest tests/deck/layout tests/deck/model -q`: 653 passed.
  - `uv run pytest tests/deck/layout --cov=autooffice.deck.layout --cov-branch --cov-report=term-missing -q`: 296 passed; total layout 98% (measure 97%, custom 94%, overflow 98%, grid/spec 100%).
  - `uv run ruff check src/autooffice/deck/layout tests/deck/layout`: All checks passed.
  - `uv run mypy src/autooffice/deck/layout`: Success, 28 source files.
  - `uv run lint-imports`: 17 kept, 0 broken.
- Efek samping:
  - Plan media bisa lebih pendek dari sebelumnya agar row berikutnya muat.
  - Code line yang melewati slot dipecah per karakter; tinggi code bertambah, overflow horizontal hanya bila satu karakter tidak muat.
  - `LayoutPlan` sekarang memakai weakref slot internal untuk cache findings; field kontrak tidak berubah.
- Dependency table renderer (lane lain):
  - `src/autooffice/deck/render/pptx/table.py` tidak diubah. Pengukuran mengasumsikan `cell.margin_top/bottom = sm`, `cell.margin_left/right = sm`, caption di bawah dengan gap `sm`, dan font header/body `max(body_pt, minimum_pt)`.
  - Bila lane renderer mengubah margin, gap caption, atau ukuran font tabel, `_measure_table_block` harus disinkronkan.
  - Caption media di `image.py`/`diagram.py` dan caption tabel di `table.py` masih menghitung tinggi caption memakai `body_pt` mentah; theme saat ini `body_pt > minimum_pt` sehingga belum terlihat. Itu tetap milik lane renderer.
- Catatan: Tidak commit/push. Branch `autooffice/f1`.
- File yang berubah: `src/autooffice/deck/layout/measure.py`, `overflow.py`, `custom.py`, `spec.py`, `tests/deck/layout/*`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - CLI review fixes: path safety, PDF-only, doctor, dry-run, cache, sync

- Fase/lane: F1-CLI / security hardening.
- Masalah: Review CLI menemukan blocker nama stem `.`/`..`/trailing-space yang bisa membuat `rmtree` menghapus direktori sumber/output; symlink aset/state/build belum ditolak; `--out` tidak dinormalisasi; PDF-only menghapus DOCX final lama; doctor belum mencerminkan target deck/slides; dry-run belum memvalidasi API lane; cache Mermaid hilang saat workspace dibersihkan; sync-only membuat `--out` dan mengklaim artefak final; error adapter PDF DOCX tidak dibungkus; hitungan font instalasi bisa memuat weight lain; nama perangkat Windows belum ditolak.
- Resolusi:
  - `deck_outputs` mengambil stem literal setelah ekstensi, menolak stem kosong/`.`/`..`/spasi/titik, nama perangkat Windows (case-insensitive, dengan/tanpa ekstensi), dan nama >200 karakter. `build_dir` di-resolve dan wajib berada di bawah `<document_dir>/.autooffice-build`; cleanup memvalidasi ulang sebelum `rmtree`.
  - `.autooffice`, `.autooffice-build/<stem>`, `assets`, dan `diagrams` menolak symlink/junction yang keluar dari root deck; `assets`/`diagrams` tidak pernah diikuti. Containment destination dicek ulang tepat sebelum setiap salin/tulis.
  - `--out` dinormalisasi sekali dengan `resolve_output_directory` lalu diteruskan ke `build_docx` dan `docx_outputs`.
  - PDF-only Markdown membangun DOCX di `.laporan-build/`; DOCX final lama tidak disentuh. `--keep-intermediate` menyimpan dan melaporkan DOCX intermediate. Adapter Word COM dibungkus `CliError` dengan path DOCX selesai dan menangkap `OSError`/`ValueError`.
  - Doctor memisahkan aset font dan font terpasang; `pptx`/`pdf` deck mewajibkan PowerPoint COM, pywin32, dan font; PDF dokumen mewajibkan Word; `slides` mewajibkan aset font + token OAuth lokal tetapi tidak font terpasang; OAuth diperiksa tanpa jaringan.
  - Dry-run memvalidasi `PptxRenderer`, converter PDF, serta `push_deck`/`sync_deck` yang relevan sebelum menyatakan rencana; tidak ada COM/jaringan dan tidak ada tulisan.
  - Cache Mermaid disalin dari `.autooffice/cache/mermaid` ke workspace sebelum render dan dikembalikan setelah render, sehingga bertahan dari cleanup.
  - Sync `diff`/`pull`/`apply` tidak membuat `--out`, tidak menyalin transcript, dan `outcome.files` hanya berisi file review + state yang benar-benar ditulis.
  - Atomic write/copy melakukan flush + `fsync` sebelum `os.replace` dan membersihkan file sementara pada kegagalan serialisasi/write selain `OSError`.
- Kontrak/klarifikasi:
  - `--out` hanya memindahkan artefak final deck; state, cache, intermediate, dan review tetap di samping YAML agar cleanup workspace aman.
  - `doctor` tidak menerima path input. `pdf` tunggal tetap menerima Word atau PowerPoint; kombinasi `docx,pdf` menyiratkan Word dan `pptx,pdf`/`slides,pdf` menyiratkan PowerPoint. `all` mewajibkan keduanya.
- Test:
  - `uv run pytest tests/cli -q`: 279 passed.
  - `uv run pytest tests/cli --cov=autooffice.cli --cov-branch --cov-report=term-missing -q`: 279 passed; total `autooffice.cli` 95%.
  - `uv run ruff check src/autooffice/cli tests/cli`: All checks passed.
  - `uv run mypy src/autooffice/cli`: Success, 7 source files.
  - `uv run lint-imports`: 17 kept, 0 broken.
- Catatan: Tidak commit/push. Branch `autooffice/f1`.
- File yang berubah: `src/autooffice/cli/outputs.py`, `build.py`, `doctor.py`, `tests/cli/*`, `docs/contracts/cli.md`, `docs/user/cli.md`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - Hardening COM/security PDF adapter

- Fase/lane: F2-PDF correctness/security review, branch `autooffice/f1`.
- Masalah:
  - Tracker PID bisa memilih PID Office baru terendah; bila snapshot tasklist gagal atau pengguna membuka Word/PowerPoint setelah `begin`, cleanup berpotensi menghentikan proses pengguna.
  - `tasklist`/`taskkill` dipanggil lewat nama sehingga executable di CWD/PATH berpotensi dibajak.
  - Watchdog membiarkan worker daemon menulis setelah timeout dan tidak punya error cleanup ambigu.
  - `timeout_s` hanya membatasi COM; lock dan cleanup memakai batas default terpisah.
  - Verifikasi font hanya mengecek fntdata/embeddedFontLst generik, tanpa typeface Plus Jakarta Sans, regular/bold, atau pengecekan ulang timing/transition/metadata/alt.
  - `update_fields` membuka dan menyimpan DOCX sumber langsung sehingga kegagalan COM bisa menyentuh sumber.
- Resolusi:
  - Snapshot proses kini `set[int] | None`; `begin()` membatalkan operasi sebelum `DispatchEx` bila snapshot gagal.
  - PID automation diidentifikasi dari `Application.Hwnd` + `GetWindowThreadProcessId`, dicek terhadap snapshot, image, dan creation time. Tidak ada fallback ke PID baru terendah; PID ambigu berarti tanpa cleanup.
  - `terminate_owned()` membaca ulang image + creation time dan hanya menghentikan PID yang sama persis.
  - `tasklist`/`taskkill` memakai path absolut `%SystemRoot%\System32` atau `%SystemRoot%\Sysnative` untuk Python 32-bit, dengan timeout turunan.
  - Watchdog memanggil cleanup, menunggu worker berhenti, lalu melempar `WordTimeoutError`; bila worker tetap hidup, `WordCleanupError` menandai cleanup ambigu dan temp tidak dihapus.
  - Deadline diteruskan ke `com_lock`, watchdog, tasklist/taskkill, dan cleanup. `update_fields` memakai snapshot + verifikasi + `os.replace` atomik.
  - Verifikasi embedding menuntut `p:font typeface="Plus Jakarta Sans"`, `p:regular`/`p:bold` yang menunjuk dua part fntdata non-kosong, tidak ada `p:timing`/`p:transition`, marker key/alt sumber tetap ada, dan python-pptx dapat membuka paket.
- Efek samping:
  - Cleanup PID yang tidak dapat diidentifikasi secara unik sengaja tidak dilakukan; proses Office dapat tertinggal dan harus dibersihkan manual.
  - Saat cleanup ambigu, direktori kerja/temp dipertahankan agar worker tidak menulis ke path yang sudah dihapus.
- Catatan gate:
  - `uv run pytest tests/pdf tests/docx -q`: 890 passed.
  - `uv run pytest tests/pdf --cov=autooffice.pdf --cov-branch --cov-report=term-missing -q`: 114 passed, total 94%.
  - `uv run ruff check src/autooffice/pdf tests/pdf`: All checks passed.
  - `uv run mypy src/autooffice/pdf`: Success.
  - `uv run lint-imports`: Success.
- File yang berubah: `src/autooffice/pdf/com.py`, `src/autooffice/pdf/word.py`, `src/autooffice/pdf/powerpoint.py`, `src/autooffice/pdf/__init__.py`, `tests/pdf/*`, `docs/dev/com.md`, log.

## 2026-11-14 - Kind chart pada slot preset

- Fase/lane: F1-LAYOUT / F2 preset chart.
- Masalah:
  - `SlotSpec` tidak menyimpan kind chart, sehingga preset `bars`, `line`, dan
    `donut` menerima block `chart` dengan kind apa pun dan nama preset tidak
    mengikat visual.
  - Dokumentasi pengguna masih menyatakan validator kind belum ada.
- Resolusi:
  - Tambah `SlotSpec.chart_kind` (`bar`, `line`, `donut`, atau `None`), validasi
    nilai saat `LayoutSpec` dibuat, dan pemeriksaan kecocokan di `validate_slide`
    hanya untuk block bertipe `chart`.
  - `bars`, `line`, dan `donut` menetapkan `chart_kind` pada slot `chart1`.
  - Test shape, data preset, dan slot ditambah; ADR 0012 serta dokumentasi
    kontrak dan pengguna diperbarui.
- Efek samping:
  - Bentuk `SlotSpec` berubah pasca-F0; preset chart baru yang mengikat satu kind
    wajib mengisi `chart_kind`.
  - Deck dengan chart kind tidak sesuai nama layout kini gagal
    `autooffice check`/build dengan `LayoutSpecError`.
  - Layout custom tidak berubah karena tidak memakai `SlotSpec`.
- Catatan gate:
  - `uv run pytest tests/deck/layout tests/contract tests/deck/model -q`: 746 passed.
  - `uv run autooffice check examples/demo-deck/deck.yaml`: bersih (306 key, 3 chart).
  - `uv run ruff check src/autooffice/deck/layout tests/deck/layout tests/contract`: All checks passed.
  - `uv run mypy src/autooffice/deck/layout`: Success, 28 source files.
  - `uv run lint-imports`: 17 kept, 0 broken.
  - `uv run ruff format --check` pada berkas Python lane ini: 7 formatted; literal
    `_spec_with` yang sudah ada di `tests/deck/layout/test_slots.py` masih perlu
    format dan tidak diubah lane ini.
  - `uv run python tools/dev/check_docs.py`: 1 temuan lama di luar lane,
    `docs/contracts/mermaid.md` 177 baris tanpa daftar isi; dokumen yang diubah
    lane ini tidak menghasilkan tautan atau anchor rusak.
- File yang berubah:
  - `src/autooffice/deck/layout/spec.py`, `slot.py`, `presets/bars.py`,
    `presets/line.py`, `presets/donut.py`.
  - `tests/deck/layout/test_presets_data.py`, `test_slots.py`,
    `tests/contract/test_contract_shapes.py`.
  - `docs/contracts/layout-spec.md`, `docs/user/deck-authoring.md`,
    `docs/decisions/0012-chart-kind-preset.md`, `docs/decisions/README.md`.
  - `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - Renderer findings B: tinggi tabel, alignment, overflow, line-height, ignored fields

- Fase/lane: F1-PPTX renderer hardening.
- Masalah: tinggi baris tabel dibagi rata; margin dan caption gap tidak dijamin;
  regex angka menerima `1.2.3`, `1,2,3`, `nan`, dan `inf`; bullets/metric menyusutkan
  shape terakhir; line-height dirender sebagai persentase, bukan multiplier ukuran
  font; `line_numbers`, `emphasis_column`, dan `metric.status` diabaikan.
- Resolusi:
  - Table mengukur tinggi konten header/body dengan lebar sel nyata, menetapkan
    minimum `konten + 2 * sm`, lalu membagi sisa tinggi proporsional terhadap
    konten. Caption diposisikan `sm` di bawah tabel; bila konten tidak muat,
    render gagal tanpa shrink.
  - Alignment angka memakai regex ketat; versi/rentang/non-finite/string kosong
    rata kiri, angka valid rata kanan.
  - Bullets dan metric tidak lagi menyusutkan shape terakhir; overflow total
    melempar `PptxRenderError` dan semua shape tetap di dalam kotak.
  - `apply_paragraph_style` menulis `a:lnSpc/a:spcPts` sebesar
    `round(font_size_pt * line_height * 100)` untuk text, caption, bullet, quote,
    metric, code, dan sel tabel; tidak ada lagi `a:spcPct`.
  - Code dengan `line_numbers` menghasilkan text box chrome
    `chrome:code-lines:<namespace>` berisi nomor baris dan bukan key.
  - `emphasis_column` mengisi header dengan `accent_deep`, sel body dengan
    `accent_soft`, dan menaikkan bobot body ke SemiBold.
  - `metric.status` memetakan `success`/`warning`/`danger`/`neutral` ke token
    `theme.colors.status` pada run value.
- Test: tinggi baris berbeda dan tall row >= konten + margin; exact-height
  header + 2 row + caption; tabel overflow; strict numeric alignment; bullets dan
  metric overflow; `a:spcPts` eksak untuk text/table/code; chrome line numbers;
  emphasis fill/weight; status color; coverage chrome tetap bersih.
- Efek samping: fixture metric `test_blocks` dinaikkan ke tinggi natural baru
  karena shrink dihapus.
- Catatan: gutter nomor baris mengurangi lebar code box, sedangkan
  `autooffice.deck.layout.measure.measure_code_block` belum menghitung gutter;
  lane layout perlu menambahkan reservasi gutter agar pengukuran dan render code
  kembali identik. Tidak ada perubahan pada `measure.py`, `renderer.py`,
  `chart.py`, `fonts.py`, PDF, atau media.
- File yang berubah:
  - `src/autooffice/deck/render/pptx/table.py`, `textbox.py`, `shapes.py`.
  - `tests/deck/render/pptx/test_table.py`, `test_textbox_edges.py`,
    `test_shapes_edges.py`, `test_blocks.py`, `test_renderer.py`,
    `_edge_helpers.py`.
  - `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - Perbaikan correctness DOCX

- Fase/lane: correctness review DOCX.
- Masalah: word_available mengabaikan COM/pywin32; output di dalam workspace bisa terhapus; error direktori/cleanup tidak dipetakan; retry COM transient hilang; bookmark/titlePg/TOC/~ path salah.
- Resolusi: COM-aware availability, output_dir guard, OutputError mapping, cleanup chaining, one-retry COM, bookmarkEnd verification, titlePg override, TOC anchor reuse, path expansion.
- Efek samping: DOCX-only build tetap jalan tanpa Word COM; output di workspace ditolak.
- Catatan: 776 test DOCX lulus; coverage 85%.
- File yang berubah: src/autooffice/docx/**, tests/docx/**, log.


## 2026-11-14 - Perbaikan correctness copy checker dan transcript

- Fase/lane: F1-COPY correctness review, branch `autooffice/f1`.
- Masalah:
  - Markdown mentah pada judul/transkrip ikut dilint (link, URL, penanda daftar, emphasis, backtick).
  - `copy.yaml` menolak semua `..` dan tidak memeriksa containment folder deck untuk path absolut.
  - Apostrof U+2018/U+2019 dan infleksi frasa Inggris lolos; diagnostic duplikat; offset token judul berulang salah.
  - `sentence_length` menghitung penanda daftar dan tidak memecah kalimat setelah kutip tutup.
  - `targets.transcript: false` tetap memvalidasi mapping; allow entry transkrip tanpa transkrip menjadi error stale.
  - `source.text` tidak diperiksa; error prosa transkrip kosong tanpa baris heading; Title Case memaksa kapital pada skrip tanpa huruf besar; paired clause meloloskan newline+spasi; copy.yaml kosong/komentar memberi pesan salah.
- Resolusi:
  - Renderer teks tampil baru (`copy/prose.py`) dengan peta offset; dipakai semua entry checker.
  - `load_copy_config(path, deck_dir=...)` resolve path dan containment; `check_copy` menurunkan deck_dir dari `deck_file`. API mandiri tanpa deck_dir hanya resolve.
  - Normalisasi apostrof + varian infleksi eksplisit; dedupe (rule,key,offset); token judul memakai posisi regex.
  - Marker daftar diabaikan; batas kalimat mendukung kutip tutup.
  - Validasi mapping transkrip dilewati saat target off; allow transkrip inert saat transkrip absen/target off.
  - `source.text` diperiksa sebagai prosa non-display; error prosa kosong memakai `heading_line`; skrip tanpa case lolos; trailing newline+spasi ditolak; YAML kosong/komentar -> "tidak boleh kosong".
- Efek samping:
  - `copy.yaml` di luar folder deck hanya ditolak bila konteks deck tersedia (`deck_file`/`deck_dir`).
  - Allow entry transkrip bersifat inert selama transkrip tidak tersedia.
- Catatan:
  - `docs/contracts/copy.md` tidak diubah karena batas lane; kebijakan path dan allow inert didokumentasikan di docstring checker/config.
  - Gate:
    - `uv run pytest tests/deck/copy -q`: 258 passed.
    - `uv run pytest tests/deck/copy --cov=autooffice.deck.copy --cov-branch --cov-report=term-missing -q`: 258 passed, total 97%, title_case/prose 100%.
    - `uv run ruff check src/autooffice/deck/copy src/autooffice/deck/transcript tests/deck/copy`: All checks passed.
    - `uv run mypy src/autooffice/deck/copy src/autooffice/deck/transcript`: Success.
    - `uv run lint-imports`: 17 contracts kept.
- File yang berubah: `checker.py`, `config.py`, `prose.py`, `rules/banned_phrases.py`, `rules/patterns.py`, `rules/sentence_length.py`, `rules/title_case.py`, `transcript/parser.py`, `tests/deck/copy/test_copy_config.py`, `tests/deck/copy/test_copy_correctness.py`, log.

## 2026-11-14 - Batas keamanan resource ZIP, XML, dan YAML

- Fase/lane: F1 security hardening.
- Masalah: `read_zip` membaca entry tanpa batas jumlah/ukuran/rasio; helper XML PPTX memakai `etree.fromstring` default sehingga DOCTYPE/entity dapat masuk; loader deck memuat YAML tanpa batas ukuran, dokumen, alias, atau kedalaman.
- Resolusi:
  - DOCX `read_zip` memeriksa `ZipInfo.file_size`/`compress_size` sebelum `archive.read`: maksimum 4.096 entry, 256 MiB per entry, 1 GiB total, dan rasio kompresi 200:1. Pelanggaran melempar `PackageError` berkode `PKG-ZIP-LIMIT`.
  - Helper PPTX menerapkan batas yang sama untuk paket PPTX dan workbook XLSX tertanam pada `forbidden_node_paths`, `validate_package`, `normalize_embedded_workbooks`, dan `content_hash`; pelanggaran melempar `PptxRenderError` berkode `PPTX-ZIP-LIMIT`.
  - Parser XML PPTX memakai `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`, tanpa recover; DOCTYPE/internal DTD/entity ditolak dengan `PptxRenderError` berkode `PPTX-XML-UNSAFE`.
  - Loader deck membatasi 5 MiB, 1 dokumen, 100 alias, dan kedalaman 64. Ukuran diperiksa dari `stat`/panjang UTF-8, dokumen di-`islice`, alias dihitung dari event parser, kedalaman memakai `YAML.max_depth`; pelanggaran melempar `DeckLoadError` dengan saran perbaikan.
  - Fixture ZIP bom di bawah 1 KB mengklaim entry 100 MB; test memasang monkeypatch `ZipFile.read` untuk membuktikan error muncul sebelum alokasi/isi dibaca.
- Efek samping:
  - Renderer PPTX tidak mengimpor parser DOCX karena kontrak import melarangnya; konfigurasi parser aman dijaga ekuivalen dan diuji terpisah. Pemindahan ke modul bersama memerlukan perubahan kontrak import.
  - Deck dengan lebih dari 100 alias atau kedalaman efektif di atas 64 kini ditolak meskipun schema-nya valid.
- Catatan gate:
  - `uv run pytest tests/docx tests/deck/render/pptx tests/deck/model -q`: 1382 passed.
  - `uv run ruff check src/autooffice/docx/package/io.py src/autooffice/deck/render/pptx/xml.py src/autooffice/deck/model/loader.py tests/docx tests/deck/render/pptx tests/deck/model`: All checks passed.
  - `uv run mypy src/autooffice/docx src/autooffice/deck/render/pptx src/autooffice/deck/model`: Success, 85 source files.
  - `uv run lint-imports`: 17 contracts kept, 0 broken.
- File yang berubah: `src/autooffice/docx/package/io.py`, `src/autooffice/deck/render/pptx/xml.py`, `src/autooffice/deck/model/loader.py`, `tests/docx/test_package_security.py`, `tests/deck/render/pptx/test_xml_security.py`, `tests/deck/model/test_loader_limits.py`, `docs/dev/security.md`, log.

## 2026-11-14 - Final acceptance build PASS

- Fase/lane: acceptance.
- Masalah: Tidak ada; verifikasi end-to-end setelah gelombang fix.
- Resolusi: Demo deck build PPTX+PDF dan DOCX example berhasil.
- Hasil: deck.pptx 24 slide, 1.688.643 B, 8 fntdata (Plus Jakarta Sans + Cascadia Mono), tanpa timing/transition; deck.pdf 24 halaman, 758.945 B; deck.transcript.md 24 section, 13.833 B; Tugas.docx 132.463 B, title benar; 25/25 verifikasi struktural.
- Efek samping: Font embedding Windows-only; visual fidelity belum diperiksa manual.
- Catatan: Artefak di temp, tidak masuk repo.
- File yang berubah: `AUTO_OFFICE_EXECUTION_LOG.md` (entri ini).

## 2026-11-14 - Perbaikan temuan verifikasi keamanan ZIP

- Fase/lane: F1 security verification follow-up, branch `autooffice/f1`.
- Masalah:
  - Metadata `ZipInfo.file_size`/`compress_size` dipercaya untuk batas memori; central directory yang menyatakan `file_size = 0` melewati pemeriksaan, lalu `archive.read` dapat mendekompresi data jauh lebih besar.
  - Batas jumlah entry baru diperiksa setelah `ZipFile` membangun seluruh daftar `ZipInfo`; EOCD juga bisa memalsukan jumlah entry.
  - Belum ada test yang membuktikan entity eksternal XML tidak dibuka; test lama hanya memeriksa pesan error.
  - Batas kedalaman YAML belum dijamin aktif pada implementasi Python murni.
  - `load_deck` memakai `stat()` lalu `read_bytes()`, sehingga berkas dapat membesar di antara kedua operasi.
- Resolusi:
  - Helper baru `autooffice.common.zip` menjadi satu sumber batas ZIP untuk DOCX dan PPTX: 4.096 entry, 256 MiB per entry, 1 GiB total, rasio 200:1, central directory 16 MiB, dan potongan baca 1 MiB.
  - `preflight_zip` membaca EOCD/ZIP64 EOCD, memeriksa jumlah entry dan ukuran central directory, lalu memindai record central directory tanpa membuat `ZipInfo`. Jumlah entry dari EOCD dihitung ulang dari record aktual sehingga EOCD palsu tidak melewati batas.
  - `ZipReader` memakai `ZipFile.open()` dan `read(1 MiB)` berulang; batas per-entry dan total dihitung dari byte hasil dekompresi. `file_size` palsu diatasi dengan salinan `ZipInfo` yang diberi ruang baca di atas batas, tetapi output tetap diputus oleh penghitung byte aktual.
  - DOCX `read_zip`, PPTX `forbidden_node_paths`, `validate_package`, `normalize_embedded_workbooks`, `content_hash`, dan workbook XLSX tertanam semuanya memakai `ZipReader`; `validate_package` tidak lagi memakai `testzip()`.
  - Loader YAML memakai `YAML(typ="safe", pure=True)` dan membaca maksimum `MAX_DECK_BYTES + 1` byte dari handle, tanpa `stat()`/`read_bytes()`.
  - Test baru: bom deflate 2 MiB dengan central directory `file_size = 0` (fixture 2.185 B, ditolak pada 81.920 byte dengan batas 64 KiB), total byte aktual, preflight jumlah entry/central directory dengan `zipfile.ZipFile` di-monkeypatch agar tidak boleh dipanggil, EOCD palsu di komentar, ZIP64 valid, dan spy opsi `etree.XMLParser` plus sentinel file.
- Efek samping:
  - Konstanta batas ZIP sekarang berasal dari `autooffice.common.zip`; nilai yang diekspor modul DOCX/PPTX tetap sama untuk kompatibilitas.
  - `validate_package` mendekompresi setiap entry untuk verifikasi CRC dan batas aktual, bukan `testzip()`.
  - Arsip dengan EOCD yang tidak konsisten dengan central directory kini ditolak sebagai ZIP tidak valid.
- Catatan gate:
  - `uv run pytest tests/docx tests/deck/render/pptx tests/deck/model -q`: 1412 passed.
  - `uv run ruff check src/autooffice/common src/autooffice/docx/package/io.py src/autooffice/deck/render/pptx/xml.py src/autooffice/deck/model/loader.py tests/docx tests/deck/render/pptx tests/deck/model`: All checks passed.
  - `uv run mypy src/autooffice/common src/autooffice/docx src/autooffice/deck/render/pptx src/autooffice/deck/model`: Success, 87 source files.
  - `uv run lint-imports`: 17 contracts kept, 0 broken.
- File yang berubah: `src/autooffice/common/zip.py` (baru), `src/autooffice/docx/package/io.py`, `src/autooffice/deck/render/pptx/xml.py`, `src/autooffice/deck/model/loader.py`, `tests/docx/test_package_security.py`, `tests/deck/render/pptx/test_xml_security.py`, `tests/deck/model/test_loader_limits.py`, `tests/deck/model/test_loader_edges.py`, `docs/dev/security.md`, log.

## 2026-11-14 - Perbaikan temuan verifikasi renderer-B

- Fase/lane: renderer-B verification fix, branch `autooffice/f1`.
- Masalah:
  - Pengukuran tinggi baris tabel memakai bobot header/body dasar, bukan bobot kolom emphasis yang dipakai renderer (700/600), sehingga baris emphasis bisa kurang tinggi.
  - Notes memakai `paragraph.line_spacing` python-pptx yang menulis `a:spcPct`, tidak konsisten dengan `a:spcPts` eksak di renderer lain.
  - Regex angka menerima pemisah ribuan dipakai ulang sebagai pemisah desimal (`1,234,56`, `1.234.56`, `1,234,567,89`).
- Resolusi:
  - `table.py` resolve `emphasis_column` sebelum pengukuran lalu mengukur header emphasis dengan weight 700 dan body emphasis dengan weight 600; style emphasis yang sama dipakai saat render.
  - `layout/measure.py` membaca `emphasis_column` dan memakai weight 700/600 pada pengukuran header/body tabel.
  - `notes.py` memakai `apply_paragraph_style` sehingga line-height ditulis `a:lnSpc/a:spcPts` eksak, bukan `a:spcPct`.
  - Regex angka memisahkan pola ribuan koma/titik dengan desimal yang wajib memakai pemisah berbeda; angka real tetap diterima.
- Tes:
  - `uv run pytest tests/deck/render/pptx tests/deck/layout -q`: 583 passed.
  - `uv run ruff check src/autooffice/deck/render/pptx src/autooffice/deck/layout tests/deck/render/pptx tests/deck/layout`: All checks passed.
  - `uv run mypy src/autooffice/deck/render/pptx src/autooffice/deck/layout`: Success, 41 source files.
  - `uv run lint-imports`: 17 contracts kept, 0 broken.
- File yang berubah: `src/autooffice/deck/render/pptx/table.py`, `src/autooffice/deck/render/pptx/notes.py`, `src/autooffice/deck/layout/measure.py`, `tests/deck/render/pptx/test_table.py`, `tests/deck/render/pptx/test_table_edges.py`, `tests/deck/render/pptx/test_notes_edges.py`, `tests/deck/render/pptx/test_renderer.py`, `tests/deck/layout/test_measure.py`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - Rasio kompresi ZIP berdasarkan byte aktual

- Fase/lane: follow-up keamanan ZIP, branch `autooffice/f1`.
- Masalah: batas rasio 200:1 baru diperiksa dari `ZipInfo.file_size`/`compress_size`; central directory yang menyatakan `file_size = 0` melewati pemeriksaan deklarasi, sehingga payload yang sangat kompresibel lolos sampai batas per-entry.
- Resolusi:
  - `_CountingReadFile` membungkus `ZipFile.fp` sehingga `ZipReader` menghitung byte mentah yang benar-benar dibaca `ZipExtFile`.
  - Setiap chunk menghitung rasio `byte dekompresi aktual / byte compressed aktual`; entry ditolak jika melebihi 200:1. Denominator memakai minimum 64 byte agar entry sangat kecil tidak memicu rasio palsu.
  - Pemeriksaan rasio deklarasi tetap ada sebagai preflight murah, tetapi keputusan akhir memakai byte aktual.
  - Test baru di DOCX dan PPTX memakai payload 2 MiB sangat kompresibel dengan `file_size = 0`; fixture 2.187 byte, compressed size 2.049 byte, dan pembaca menolak pada rasio aktual 207:1 sebelum seluruh payload dibaca.
- Tes:
  - `uv run pytest tests/docx/test_package_security.py tests/deck/render/pptx/test_xml_security.py -q`: 33 passed.
  - `uv run pytest tests/docx tests/deck/render/pptx tests/deck/model -q`: 1436 passed.
  - `uv run ruff check src/autooffice/common src/autooffice/docx/package/io.py src/autooffice/deck/render/pptx/xml.py src/autooffice/deck/model/loader.py tests/docx tests/deck/render/pptx tests/deck/model`: All checks passed.
  - `uv run mypy src/autooffice/common src/autooffice/docx src/autooffice/deck/render/pptx src/autooffice/deck/model`: Success, 87 source files.
  - `uv run lint-imports`: 17 contracts kept, 0 broken.
- File yang berubah: `src/autooffice/common/zip.py`, `tests/docx/test_package_security.py`, `tests/deck/render/pptx/test_xml_security.py`, `docs/dev/security.md`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - Perbaikan blocker COM font dan cleanup ambigu

- Fase/lane: F2-PDF dan F1 cleanup review, branch `autooffice/f1`.
- Masalah:
  - Verifikasi font PowerPoint masih memakai fallback `unresolved`: relasi `p:regular`/`p:bold` boleh tidak terselesaikan asalkan ada dua part fntdata. Tipe relasi dan content type fntdata juga belum divalidasi.
  - `WordCleanupError` diterjemahkan menjadi timeout generik, sehingga pipeline dan CLI tetap menghapus workspace serta temp saat cleanup ambigu.
  - Timeout `tasklist`/`taskkill` memakai floor 0,1 detik yang dapat melebihi sisa budget; `SYSTEMROOT` relatif dipakai apa adanya; `limit_process_control()` berada di luar suppression; `unlink(missing_ok=True)` dapat menimpa error utama dengan `PermissionError`; dan `remaining_or_raise()` dapat mengembalikan sisa waktu negatif.
- Resolusi:
  - `powerpoint.embed_fonts` mewajibkan `p:regular` dan `p:bold` menunjuk relasi bertipe `.../font` ke dua part `ppt/fonts/*.fntdata` berbeda, ada, dan tidak kosong; `[Content_Types].xml` wajib mendeklarasikan content type fntdata yang valid. Fallback `unresolved` dihapus.
  - `WordCleanupError` membawa `cleanup_ambiguous=True`. Stage `office`/`pdf` menerjemahkannya ke kode `WORD-CLEANUP`/`PDF-CLEANUP`, pipeline melewati `Workspace.cleanup()`, `pdf/word.py` dan `pdf/powerpoint.py` tidak menghapus snapshot/temp, dan `cli/build.py` mempertahankan workspace dengan kode `CLI-FONT-CLEANUP`/`PDF-CLEANUP`.
  - Timeout proses memakai clamp `max(0, min(15, sisa_budget))`; `SYSTEMROOT`/`WINDIR` relatif diabaikan dan path absolut dicari lewat `GetSystemDirectoryW`; cleanup `limit_process_control()` disuppress terpisah; unlink temp disuppress; `remaining_or_raise()` membaca sisa waktu sekali dan melempar `WordTimeoutError` bila sudah habis.
- Efek samping:
  - Build dengan cleanup Office ambigu kini sengaja meninggalkan workspace/temp untuk inspeksi manual dan dapat melewati `timeout_s` sebesar budget cleanup terbatas.
  - Verifikasi font lebih ketat: paket hasil PowerPoint tanpa relasi font, content type fntdata, atau part regular/bold terpisah sekarang ditolak sebelum PPTX sumber diganti.
- Catatan gate:
  - `uv run pytest tests/pdf tests/cli tests/docx -q`: 1232 passed.
  - `uv run ruff check src/autooffice/pdf src/autooffice/docx src/autooffice/cli tests/pdf tests/cli tests/docx`: All checks passed.
  - `uv run mypy src/autooffice/pdf src/autooffice/docx src/autooffice/cli`: Success, 74 source files.
  - `uv run lint-imports`: 17 contracts kept, 0 broken.
- File yang berubah:
  - `src/autooffice/pdf/com.py`, `word.py`, `powerpoint.py`.
  - `src/autooffice/docx/stages/office.py`, `stages/pdf.py`, `pipeline.py`, `errors.py`.
  - `src/autooffice/cli/build.py`, `src/autooffice/cli/__init__.py`.
  - `tests/pdf/test_com.py`, `test_word.py`, `test_powerpoint.py`, `test_powerpoint_verify_edges.py`.
  - `tests/docx/test_office.py`, `test_pdf.py`, `test_pipeline_edges.py`.
  - `tests/cli/test_build_markdown.py`, `test_deck_build_errors.py`.
  - `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 cleanup legacy dan rename package

- Fase/lane: F3 cleanup, branch `autooffice/f1`.
- Masalah: package, test, tool, dan dokumen legacy `docgen` masih hidup berdampingan dengan `autooffice`; metadata package masih memakai nama `docgen`.
- Resolusi:
  - 152 berkas legacy dihapus: `src/docgen/**`; `tests/unit`, `tests/integration`, `tests/e2e`, `tests/packaging` legacy; tool/test/script yang dihapus; `docs/dev/contracts/**`.
  - Tag lokal `pre-autooffice-cleanup` dibuat di `34e472d`; tidak di-push.
  - Metadata package di `pyproject.toml` di-rename menjadi `autooffice`; `uv.lock` resolve 76 package, entri editable `docgen` hilang, `autooffice` masuk.
  - `scripts/word.ps1`, `tools/dev`, `tests/factories`, dan `tests/autooffice/conftest.py` dihapus.
- Efek samping: path, import, dan entry point lama tidak tersedia; tidak ada jalur editable `docgen` yang tersisa.
- Catatan/verifikasi: collection `3307/3315` (8 deselected); ruff, mypy (171 file), dan import-linter (12 kontrak) lulus. Ini bukan klaim gate final penuh.
- File yang berubah:
  - `src/docgen/**` (dihapus), `tests/unit/**`, `tests/integration/**`, `tests/e2e/**`, `tests/packaging/**` legacy (dihapus).
  - `scripts/word.ps1`, `tools/dev/**`, `tests/factories/**`, `tests/autooffice/conftest.py` (dihapus).
  - `docs/dev/contracts/**` (dihapus), `pyproject.toml`, `uv.lock`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 fallback layout dihapus

- Fase/lane: F3 fallback fixes, layout, branch `autooffice/f1`.
- Masalah: fallback senyap pada layout: `F0_LAYOUT_NAMES` masih ada; discovery preset kosong tidak melempar error; slide custom tanpa `rows` tidak melempar error; warning bobot font tidak sampai ke `RenderResult.warnings`.
- Resolusi: `F0_LAYOUT_NAMES` dihapus; discovery preset kosong melempar `LayoutRegistryError`; slide custom tanpa `rows` melempar `CustomLayoutError`; warning bobot font diteruskan ke `RenderResult.warnings`.
- Efek samping: konfigurasi/preset yang sebelumnya jatuh ke fallback senyap kini gagal keras; warning font terlihat pada hasil render.
- Catatan/verifikasi: `tests/deck/layout tests/deck/render/pptx` 587 passed; `tests/deck` 1487 passed, 1 deselected.
- File yang berubah: `src/autooffice/deck/layout/{registry,presets/__init__,custom,spec,overflow}.py`, `src/autooffice/deck/render/pptx/{renderer,shapes,table,textbox}.py`, `tests/deck/layout/**`, `tests/deck/render/pptx/**`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 fallback DOCX, config, dan terms dihapus

- Fase/lane: F3 fallback fixes, DOCX/config/terms, branch `autooffice/f1`.
- Masalah: fallback senyap pada DOCX/config/terms: `ctx.output_dir` hilang, `ctx.word` invalid, environment Pandoc invalid, relationship terms korup, glossary packaged hilang, guard overwrite style, dan string config kosong eksplisit.
- Resolusi: `ctx.output_dir` hilang melempar error; `ctx.word` invalid melempar error; environment Pandoc invalid melempar error; relationship terms korup dipropagasikan; glossary packaged hilang gagal; style overwrite guard fail closed; string config kosong eksplisit melempar `CFG-REQUIRED`.
- Efek samping: build gagal keras alih-alih memakai fallback; string config kosong eksplisit tidak lagi diterima.
- Catatan/verifikasi: `tests/docx` 828 passed.
- File yang berubah: `src/autooffice/docx/{pipeline,errors,document,command}.py`, `src/autooffice/docx/config/format.py`, `src/autooffice/docx/stages/**`, `src/autooffice/docx/terms/**`, `tests/docx/**`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 fallback CLI/Google terverifikasi

- Fase/lane: F3 fallback fixes, CLI/Google, branch `autooffice/f1`.
- Masalah: tiga fallback senyap dilaporkan: Google sync `None` dianggap sukses; scaffolding lane dan `CLI-LANE-*` masih ada; `convert_docx_to_pdf` masih memiliki hidden fallback.
- Resolusi: Google sync `None` tidak lagi dianggap sukses; scaffolding lane/`CLI-LANE-*` dihapus; hidden fallback `convert_docx_to_pdf` dihapus.
- Status: terverifikasi; ketiga perubahan dikonfirmasi.
- Efek samping: sync tanpa hasil eksplisit kini gagal; kode error lane tidak lagi tersedia.
- Catatan/verifikasi: `uv run pytest tests/cli tests/google -q`: 602 passed.
- File yang berubah: `src/autooffice/google/sync.py`, `src/autooffice/cli/build.py`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 check_no_legacy aktif dan blocking

- Fase/lane: F3 quality gate, branch `autooffice/f1`.
- Masalah: `check_no_legacy` belum memindai secara aktif; `*.egg-info` dan metadata fixture `docgen-golden` di `docs/dev/testing.md` memicu false positive; checker belum menjadi langkah gate blocking. Sisa pelanggaran aktif saat itu adalah docstring `pdf/com.py` yang menyebut `word.ps1`.
- Resolusi: checker kini memindai aktif, melewati `*.egg-info`, mengizinkan hanya metadata fixture `docgen-golden` di `docs/dev/testing.md`, dan menjadi langkah gate blocking.
- Efek samping: pelanggaran legacy kini menggagalkan gate, bukan hanya dilaporkan.
- Catatan/verifikasi: saat pencatatan, `check_no_legacy` melaporkan 489 berkas diperiksa dan 0 pelanggaran aktif; ini bukan gate final penuh.
- File yang berubah: `tools/quality/check_no_legacy.py`, `tools/quality/gate.py`, `tests/tools/test_no_legacy.py`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 test packaging, acceptance, dan coverage visibility

- Fase/lane: F3 tests/packaging, branch `autooffice/f1`.
- Masalah: belum ada test yang mengunci paket AutoOffice, demo deck end-to-end, dan coverage yang hanya berbasis metadata.
- Resolusi:
  - `tests/packaging/test_autooffice_package.py`: 6 test mencakup console script, font/OFL, design data, DOCX data, dan tidak ada `docgen`.
  - `tests/acceptance/test_demo_deck.py`: 1 test integration/slow; PPTX 24 slide nyata, Plus Jakarta Sans ter-embed, tanpa timing/transition; PDF 24 halaman; transcript identik.
  - Meta-test `tests/contract/test_coverage_visibility.py`: 2 test; menolak key coverage yang hanya metadata.
  - Pruning test: model/copy/charts 767 passed; deck/media/design/performance/visual/contract 306 passed.
- Efek samping: test acceptance bergantung pada PowerPoint COM/Windows dan aset font; test lambat ditandai integration/slow.
- Catatan/verifikasi: angka di atas adalah hasil lane test, bukan gate final penuh.
- File yang berubah: `tests/packaging/test_autooffice_package.py`, `tests/acceptance/test_demo_deck.py`, `tests/contract/test_coverage_visibility.py`, `tests/tools/test_no_legacy.py`, test yang dipangkas di `tests/deck/**` dan `tests/contract/**`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 audit COM: tasklist/taskkill dipertahankan

- Fase/lane: F3 COM audit, branch `autooffice/f1`.
- Masalah: perlu keputusan apakah kontrol proses Office berbasis `tasklist`/`taskkill` diganti pywin32/Job Object.
- Resolusi: untuk v1, `tasklist`/`taskkill` dipertahankan; rewrite ke pywin32/Job Object tidak dilakukan sekarang. Alasan: pywin32 tidak memperbaiki kepemilikan `Application.Hwnd` maupun `Quit` PowerPoint bersama; `KILL_ON_JOB_CLOSE` lebih destruktif bila kepemilikan salah.
- Prototipe:
  - A (`tasklist`/`taskkill` absolut) dan B (`win32process` + Job Object `KILL_ON_JOB_CLOSE`) diuji pada process tree dummy yang tidak berbahaya, bukan Office.
  - A membunuh tree, tetapi `taskkill` mengembalikan exit code nonzero pada 4/10 iterasi cleanup meskipun tree sudah mati; A tidak dapat membunuh orphan setelah root exit.
  - B membunuh tree saat job close dan child tetap tercakup setelah root exit, tetapi assignment root yang sudah berjalan tidak menangkap child yang dibuat sebelum assignment; stale handle ditolak dengan aman.
  - Assignment B berhasil lewat `HWND -> PID -> OpenProcess -> AssignProcessToJobObject` di Windows 11, termasuk nested job.
  - Ukuran: A 243 baris fisik/198 baris kode, 4 Win32 API + `tasklist`/`taskkill`; B 225 baris fisik/146 baris kode, 12 Win32 API. Waktu assignment B ~0,16 ms, job close <0,2 ms; cleanup A ~0,7–1,2 s median.
- Temuan:
  - P0: `Quit` PowerPoint tanpa syarat dapat menutup instance pengguna; `Application.Hwnd` tidak terdokumentasi.
  - P1: cleanup watchdog memakai deadline yang sudah habis sehingga `taskkill` tidak pernah berjalan.
  - Bug deterministik terkonfirmasi: deadline habis -> `limit_process_control(..., 0)` -> `image_name()` None -> `terminate()` False -> tidak ada kill. Perbaikan ditangani terpisah.
- Rekomendasi: secara teknis hybrid B-primary (Job Object plus fallback `taskkill /T /F`) lebih robust, tetapi jangan rewrite sekarang bila AutoOffice pindah ke LibreOffice; perbaiki bug deadline/ownership lebih dulu.
- Efek samping: risiko P0/P1 tetap ada sampai probe/fix selesai; prototipe tidak mengubah kode produksi.
- Catatan/verifikasi: Job Object belum diimplementasikan dan tidak ada klaim perubahan kode. Belum diuji: topologi child Word/PowerPoint nyata, Windows localized (non-Inggris), dan PID reuse nyata. Probe/fix sedang berjalan; belum diklaim fixed.
- Tindak lanjut: probe/fix final dan verifikasi ada di entri `F3 COM final`.
- File yang berubah: tidak ada perubahan kode dari audit/prototipe ini; catatan terkait di `docs/dev/com.md`.

## 2026-11-14 - F3 dokumentasi AutoOffice dan invariant AGENTS

- Fase/lane: F3 docs, branch `autooffice/f1`.
- Masalah: dokumentasi, README, kontrak, dan halaman dev masih memakai path/istilah `docgen`; invariant engineering belum tercatat di `AGENTS.md`.
- Resolusi: invariant engineering ditambahkan ke `AGENTS.md`; `docs/README.md`, `docs/contracts/**`, dan `docs/dev/**` diperbarui ke path AutoOffice.
- Efek samping: tidak ada perubahan perilaku; dokumentasi mengikuti struktur AutoOffice.
- Catatan/verifikasi: `check_docs.py`: 110 dokumen, 763 tautan, 28 TOC, 63 entri registry, 0 broken.
- File yang berubah: `AGENTS.md`, `docs/README.md`, `docs/contracts/**`, `docs/dev/**`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 COM final: ownership probe dan P0/P1 fix

- Fase/lane: F3 COM final, branch `autooffice/f1`.
- Masalah: probe Office nyata membuktikan `Application.Hwnd` Word tidak ada; `ActiveWindow.Hwnd` hanya tersedia setelah dokumen dibuka. Pada PowerPoint, `Application.Hwnd` tidak dapat dipakai, `DispatchEx` menempel ke instance PowerPoint bersama, dan `Quit` menutup presentasi pengguna.
- Resolusi:
  - P0: Word claim memakai PID baru + enumerasi window `OpusApp`; PowerPoint preflight fail-fast bila `POWERPNT.EXE` sudah berjalan; claim memakai PID baru; `Quit` hanya untuk instance milik AutoOffice; tanpa Job Object.
  - P1: budget cleanup tetap 5 detik; `taskkill` exit code nonzero + PID hilang dianggap sukses; `WordCleanupError` bukan lagi subclass `WordTimeoutError`.
- Efek samping: instance Office pengguna tidak disentuh; build gagal cepat bila PowerPoint sudah terbuka; cleanup ambigu tetap meninggalkan proses untuk inspeksi manual.
- Catatan/verifikasi:
  - `uv run pytest tests/pdf tests/docx -q`: 988 passed.
  - Smoke COM nyata Word/PowerPoint: tidak ada proses tersisa.
  - Timeout paksa: cleanup selesai sekitar 0,5 detik.
- File yang berubah: `src/autooffice/pdf/{__init__,com,word,powerpoint}.py`, `tests/pdf/**`, `tests/docx/test_pdf.py`, `docs/dev/com.md`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 acceptance dan packaging final PASS

- Fase/lane: F3 acceptance/packaging, branch `autooffice/f1`.
- Masalah: verifikasi end-to-end demo deck, wheel, dan build Word penuh belum final.
- Resolusi:
  - `tests/acceptance/test_demo_deck.py`: 1 passed dalam 24,98 detik; PPTX 24 slide, PDF 24 halaman, transcript, Plus Jakarta Sans ter-embed, tanpa timing/transition.
  - `tests/packaging/test_wheel_contents.py -m slow`: 1 passed; wheel bersih, 0 entri `docgen`.
  - Build Word `examples/assignment-single/document.md --target docx,pdf`: PDF 6 halaman, teks, DAFTAR ISI, font ter-embed; tidak ada Word/PowerPoint tersisa.
  - Wheel: 196 entri, 0 `docgen`; `include = ["autooffice*"]`.
  - `check_identifiers.py` dan `check_source_style.py` menjadi langkah gate blocking dan hijau.
- Efek samping: acceptance tetap membutuhkan Windows, PowerPoint COM, dan aset font.
- Catatan/verifikasi: tidak ada klaim visual layer deck-studio.
- File yang berubah: `tests/acceptance/test_demo_deck.py`, `tests/packaging/test_wheel_contents.py`, `tools/quality/check_identifiers.py`, `tools/quality/check_source_style.py`, `tools/quality/gate.py`, `pyproject.toml`, `AUTO_OFFICE_EXECUTION_LOG.md`.

## 2026-11-14 - F3 final gate PASS

- Fase/lane: F3 final gate, branch `autooffice/f1`.
- Masalah: gate final penuh belum dijalankan setelah seluruh lane F3.
- Resolusi: `uv run python tools/quality/gate.py` PASS.
- Hasil:
  - 3.482 passed, 10 deselected.
  - Coverage global 90,61% (line 92,54%, branch 85,48%); modul kritis 8/8 pada 100%.
  - Adapter: google 89,35%, pdf 90,90%, cli 94,35%, docx 86,08%.
  - Docs: 110 dokumen, 763 tautan, 0 broken.
  - test-quality: 0 pelanggaran (2.618 test function).
  - no-legacy 0; python-style 0; identifiers/source-style 0.
  - ruff, mypy, import-linter, dan lock lulus.
- Efek samping: tidak ada; gate final menjadi bukti kelayakan F3.
- Catatan/verifikasi: fallback CLI/Google sudah terverifikasi (602 test). F3 belum di-commit/merge/push.
- File yang berubah: `AUTO_OFFICE_EXECUTION_LOG.md` (entri ini).

## 2026-11-14 - F3 sisa lingkup dan status commit

- Fase/lane: F3 penutup, branch `autooffice/f1`.
- Masalah: belum seluruh lingkup F3 selesai; beberapa item menunggu eksternal.
- Resolusi/sisa:
  - Visual layer deck-studio belum dimulai.
  - Google live smoke membutuhkan OAuth.
  - Rename repo GitHub menunggu persetujuan.
  - Belum ada commit/merge/push; perubahan F3 masih uncommitted.
- Efek samping: F3 belum boleh dianggap selesai penuh atau di-merge.
- Catatan/verifikasi: tidak ada klaim visual layer atau Google live selesai.
- File yang berubah: `AUTO_OFFICE_EXECUTION_LOG.md` (entri ini).
