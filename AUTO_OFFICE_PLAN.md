# AutoOffice: Rencana Refactor

> Status: draft source of truth.
> Versi: 1.0-draft.
> Tanggal: 2026-11-14.
> Lokasi awal: `C:\dev\apps\docgen\AUTO_OFFICE_PLAN.md`.
> Implementasi: belum ada. Dokumen ini tidak mengubah kode, tidak membuat commit, dan tidak melakukan rename repo.

Dokumen ini adalah rencana kerja tunggal untuk menggabungkan `docgen` dan `deck-studio` menjadi satu proyek **AutoOffice**. Semua lane, kontrak, acceptance test, dan gate harus merujuk ke dokumen ini. Bila dokumen ini bertentangan dengan keputusan terkunci di Bagian 2, keputusan terkunci menang. Bila detail teknis di Bagian 4 sampai 12 berubah, perubahan harus melalui kontrak Fase 0 dan ADR, bukan lewat improvisasi saat implementasi.

## 0. Cara Membaca Dokumen Ini

Dokumen ini ditulis untuk tiga pembaca:

- **Programmer awam**: mulai dari Bagian 1, 3, 4, dan 10. Bagian 4 memberi contoh YAML yang bisa dibaca tanpa mengetahui isi kode. Bagian 10 memberi perintah yang bisa dijalankan.
- **AI agent**: baca seluruh dokumen, terutama Bagian 13, 14, dan 15. Bagian itu menentukan file mana yang boleh disentuh, kapan boleh mulai, dan kapan pekerjaan dianggap selesai.
- **Maintainer**: baca Bagian 2, 3, 12, 17, dan 18. Bagian itu memuat keputusan, gate, risiko, dan acceptance final.

Kata kunci normatif:

- **HARUS** berarti syarat wajib. Pekerjaan tidak boleh di-merge bila syarat ini tidak terpenuhi.
- **TIDAK BOLEH** berarti larangan keras.
- **SEBAIKNYA** berarti default yang dianjurkan; penyimpangan harus dicatat di ADR.
- **BOLEH** berarti opsional dan tidak boleh menambah kompleksitas tanpa alasan.

Istilah:

- **Keputusan terkunci** adalah keputusan produk/arsitektur yang sudah ditetapkan di Bagian 2.1 dan tidak boleh diubah tanpa persetujuan eksplisit pemilik proyek.
- **Usulan kontrak** adalah detail nama field, signature, atau bentuk file yang diperlukan agar keputusan terkunci bisa dieksekusi. Usulan ini dibekukan di Fase 0.
- **Asumsi** adalah hal yang belum diputuskan dan wajib dikonfirmasi sebelum Fase 0 selesai. Semua asumsi ada di Bagian 19.
- **Lane** adalah unit kerja paralel dengan kepemilikan file yang jelas.
- **Gate** adalah kumpulan pemeriksaan yang harus lulus sebelum merge atau sebelum fase berikutnya.
- **Key** adalah identifier datar stabil untuk satu nilai teks, misalnya `s03.kpi1.value`.
- **IR** atau **Deck IR** adalah representasi deck yang sudah divalidasi dan dinormalisasi, siap dipakai layout engine dan renderer.

Aturan interpretasi:

1. Jangan menambah fitur baru hanya karena mudah dikerjakan.
2. Jangan membuat kompatibilitas mundur untuk `docgen` atau `deck-studio`.
3. Jangan membuat fallback diam-diam. Semua kegagalan harus terlihat.
4. Jangan mengubah file milik lane lain.
5. Jangan merge tanpa verifikasi.
6. Jangan memakai workaround, monkey patch, dead code, atau alias lama untuk menyelesaikan masalah kontrak.

---

## 1. Ringkasan, Tujuan, Non-Goals, dan Definisi Selesai

### 1.1 Kondisi Saat Ini

Repo sumber:

- `C:\dev\apps\docgen`: Python 3.15, sekitar 27k LOC, pipeline DOCX berbasis Markdown dan Pandoc, finalisasi Word, PDF lewat Word COM, tes dan disiplin dokumen yang kuat.
- `C:\dev\apps\deck-studio`: Node/JavaScript, sekitar 24k LOC dengan sekitar 7k LOC tes, model deck JSON, renderer HTML/Reveal dan PPTX memakai PptxGenJS, sinkronisasi Google Slides, dan design system.

Dua repo memiliki tujuan yang tumpang tindih tetapi model data, bahasa, CLI, dan quality gate yang berbeda. Biaya utama bukan jumlah kode, tetapi duplikasi kontrak, dua cara berpikir tentang konten, dan dua pipeline kualitas.

### 1.2 Tujuan

Tujuan AutoOffice:

1. Menjadi **satu proyek**, satu package Python `autooffice`, dan satu CLI `autooffice`.
2. Menghapus total `docgen` dan `deck-studio`, termasuk nama package, entry point, folder, dokumentasi lama, dan dependensi Node untuk renderer utama. Tidak ada alias dan tidak ada dead code.
3. Mempertahankan kualitas pipeline DOCX yang sudah dimiliki `docgen`, tanpa perubahan perilaku dokumen.
4. Mengganti model deck JSON dan renderer HTML/Reveal dengan satu model YAML per deck dan satu pipeline deck yang mengarah ke PPTX, PDF, dan Google Slides.
5. Menjadikan key datar yang stabil sebagai kontrak tunggal untuk renderer, coverage, dan sinkronisasi teks Google Slides.
6. Memakai design system deck-studio sebagai sumber visual, tetapi menghasilkan presentasi dari token desain, bukan dari template `.pptx` eksternal.
7. Memakai chart native yang dapat diedit di PowerPoint dan linked chart native di Google Slides.
8. Menjaga pengalaman Windows-only yang eksplisit: Word COM untuk DOCX ke PDF, PowerPoint COM untuk PPTX ke PDF, `mmdc` eksternal untuk Mermaid.
9. Menegakkan kualitas melalui gate lokal yang ketat, bukan GitHub Actions.

### 1.3 Non-Goals

Hal-hal berikut TIDAK BOLEH menjadi bagian dari v1:

- HTML, Reveal.js, web preview, atau output browser.
- XLSX.
- Object animation dan slide transition.
- Absolute positioning di authoring. Authoring tidak boleh memakai `x`, `y`, `left`, `top`, `width`, `height`, `position`, `anchor`, atau koordinat absolut lainnya.
- Template `.pptx` eksternal atau base deck yang diunggah pengguna.
- Block `callout`. Block types yang diizinkan hanya yang tercantum di Bagian 2 dan Bagian 4.
- Native Mermaid shapes. Mermaid selalu menjadi gambar.
- Chart dua arah. Data chart hanya mengalir dari YAML ke Sheets.
- Sinkronisasi format kaya dua arah. Sinkronisasi teks bersifat teks, bukan model gaya.
- Dukungan Linux atau macOS untuk PDF dan Google Slides. Windows adalah target pertama dan satu-satunya untuk v1.
- Lebih dari dua theme produk: `indigo` dan `hitam`.
- Semua 21 layout deck-studio. Hanya layout yang tercantum di Bagian 6 yang didukung.
- Tutorial per fitur. Dokumentasi v1 berisi quickstart, model authoring, CLI, konsep, kontrak, dan troubleshooting.
- Kompatibilitas CLI lama `docgen` atau `deck-studio`.
- Service account Google. File dimiliki akun uploader.

### 1.4 Definisi Selesai

AutoOffice dinyatakan selesai bila seluruh kondisi berikut benar:

- Hanya ada satu package importable, yaitu `autooffice`.
- Hanya ada satu entry point CLI yang didokumentasikan, yaitu `autooffice`.
- Tidak ada package `docgen`, tidak ada entry point `docgen`, dan tidak ada alias `docgen`.
- Tidak ada kode sumber `deck-studio`, `PptxGenJS`, HTML/Reveal, `package.json`, atau `node_modules` di repo final.
- `autooffice build` mendukung matriks target di Bagian 10 untuk `.md` dan `.yaml`.
- Pipeline DOCX menghasilkan output yang setara dengan `docgen` untuk fixture yang sama, termasuk manifest dan istilah.
- Pipeline YAML menghasilkan PPTX dengan chart native, table native, notes, alt text, dan font tertanam.
- Pipeline Slides menghasilkan presentasi Google Slides dengan linked Sheets chart, table native, satu spreadsheet per deck, satu tab per chart, dan sinkronisasi teks penuh.
- Copy checker berjalan pada teks slide, notes, dan transkrip; error menghentikan build, warning dicetak.
- Bila `transcripts.md` ada, transkrip tervalidasi, tersalin ke output, dan ikut diperiksa.
- PDF DOCX dan PPTX dihasilkan melalui Word COM dan PowerPoint COM di Windows.
- Mermaid dirender oleh `mmdc` menjadi gambar, baik di PPTX maupun Google Slides.
- Demo deck berisi minimal satu slide untuk setiap layout yang didukung dan minimal satu contoh untuk setiap block type.
- Gate final lulus: ruff, mypy ketat, import-linter, pytest, coverage 100%, docs checker, test-quality checker, dan no-legacy checker.
- Repo GitHub sudah di-rename menjadi `autooffice` dan tidak ada referensi runtime/user ke nama lama. Dokumen migrasi ini boleh tetap ada sebagai catatan historis, tetapi bukan dokumentasi user.
- Clean clone di Windows dapat menjalankan quickstart tanpa langkah tersembunyi.

---

## 2. Keputusan Terkunci dan Asumsi

### 2.1 Keputusan Terkunci

Keputusan berikut bersifat final untuk plan ini.

| ID | Keputusan |
| --- | --- |
| L01 | Satu proyek bernama **AutoOffice**. Satu package Python `autooffice`. Satu CLI `autooffice`. |
| L02 | `docgen` dan `deck-studio` dihapus total. Tidak ada alias, shim, package kompatibilitas, atau dead code. |
| L03 | Python 3.15. Target pertama Windows-only. `python-pptx` adalah core renderer PPTX. Extras: `google` dan `dev`. |
| L04 | Satu file YAML per deck. Authoring memakai struktur bertingkat `meta` dan `slides`, lalu compiler menghasilkan key datar yang stabil untuk renderer, coverage, dan sinkronisasi. |
| L05 | Template dan desain deck dihasilkan dari design system deck-studio. Tidak ada base `.pptx` eksternal. |
| L06 | Layout memakai catalog preset dan custom grid composition level 2: 12 kolom, `rows` eksplisit, `span` 1 sampai 12, tanpa x/y absolut, tinggi mengikuti isi, dan gutter dari design token. |
| L07 | Block types v1: `text`, `bullets`, `image`, `table`, `chart`, `code`, `quote`, `diagram`, `divider`, `spacer`, `metric`. Tidak ada `callout`. |
| L08 | Chart PPTX memakai native PowerPoint chart melalui `python-pptx`. |
| L09 | Chart Google Slides memakai linked Google Sheets chart melalui `createSheetsChart`. Satu spreadsheet per deck, satu tab per chart, dimiliki akun uploader, mode linked, data satu arah dari YAML ke Sheets. |
| L10 | Mermaid tetap memakai `mmdc` atau Node sebagai external tool. Hasil Mermaid adalah gambar, bukan native shape, termasuk di Google Slides. |
| L11 | Google Slides: upload PPTX, ganti chart placeholder dengan linked Sheets chart, lalu sinkronisasi teks penuh push/pull/diff/apply. |
| L12 | Tanpa object animation dan tanpa slide transition. |
| L13 | Tanpa HTML/Reveal, XLSX, absolute positioning, atau template PPTX eksternal. |
| L14 | PDF DOCX memakai Word COM. PDF PPTX memakai PowerPoint COM. Keduanya Windows-only dan diserialisasi. |
| L15 | Theme produk hanya `indigo` sebagai default dan `hitam` sebagai theme aksen hitam di kanvas terang, mengikuti palet `hitam` deck-studio. Font Plus Jakarta Sans, dibundel untuk build dan test, ditanam di PPTX, dan memakai Google Fonts di Google Slides. |
| L16 | CLI build: `autooffice build <input> --target ...`. Input `.md`: `docx`, `pdf`, `all` (docx+pdf). Input `.yaml`: `pptx`, `pdf`, `slides`, `all` (pptx+pdf+slides). Target boleh comma-separated. `pdf` diturunkan dari DOCX atau PPTX sesuai input. Ada `autooffice check` dan `autooffice doctor`. |
| L17 | Gate final lokal: ruff, mypy lebih ketat dari docgen, import-linter, pytest, coverage 100%, docs checker, dan test-quality checker. Tanpa GitHub Actions. |
| L18 | Dokumentasi berada di `docs/user`, `docs/dev`, `docs/learn`, `docs/contracts`, dan `docs/decisions`. Tidak ada tutorial per fitur untuk saat ini. |
| L19 | Acceptance memakai demo deck-studio sebagai deck contoh, minimal satu slide per layout yang didukung, dan satu contoh setiap block type. |
| L20 | Repo GitHub di-rename menjadi `autooffice` pada fase akhir. Tidak ada referensi lama di runtime, package, README, atau docs user. |
| L21 | Prinsip kerja: contracts before code; no two owners on one file; no merge without verification; file-disjoint parallel lanes; tests as executable contracts; docs navigable; no pragmatic shortcut yang merusak maintainability. |
| L22 | Table harus native di PPTX dan Google Slides. Tabel tidak boleh menjadi gambar. Bila konversi impor Google Slides menghasilkan image atau kumpulan shape, push gagal; tidak ada fallback rebuild otomatis di v1. |
| L23 | Copy checker deterministik adalah stage first-class untuk deck. Aturan diporting dari deck-studio; tidak memanggil LLM atau layanan jaringan saat build. Berlaku untuk teks slide, notes, dan transkrip. DOCX tidak memakai humanizer dan tetap memakai `--terms`. |
| L24 | Transkrip adalah berkas pendamping opsional `transcripts.md` di folder deck. Transkrip tidak disimpan di YAML, disalin ke output sebagai `<stem>.transcript.md`, dan diperiksa copy checker. |
| L25 | Konfigurasi copy memakai `copy.yaml` di folder deck. Tanpa config, default bawaan berlaku. Config dapat mengubah severity, menambah frasa terlarang, mematikan rule, dan mendaftarkan allowlist dengan alasan. Build gagal pada error; warning dicetak. |

### 2.2 Status Detail Teknis

Bagian 3 sampai 18 memuat usulan kontrak yang lebih rinci. Usulan ini bukan keputusan produk baru. Usulan ini wajib dibekukan di Fase 0 sebelum lane fitur mulai. Bila detail di usulan mengubah perilaku produk atau bertentangan dengan keputusan terkunci, detail itu masuk ke Bagian 19 untuk dikonfirmasi.

### 2.3 Ringkasan Asumsi

Asumsi yang wajib dikonfirmasi sebelum Fase 0 selesai:

- ID slide ditulis eksplisit dan stabil, bukan diturunkan dari posisi array.
- Preset layout memiliki baris internal; hanya `layout: custom` yang menulis `rows` eksplisit.
- Surface CLI untuk pull/diff/apply adalah `build --target slides --sync ...`.
- Format output dan state file mengikuti usulan Bagian 10.
- `hitam` memakai palet `hitam` deck-studio: kanvas terang dengan aksen hitam, bukan dark theme dan bukan palet `malam`.
- Format gambar, font, dan mekanisme placeholder chart.
- Cakupan sinkronisasi teks dan perilaku apply.
- Layout deck-studio yang tidak masuk v1.
- Perlakuan flag lama `docgen`.
- Definisi exclusion coverage dan konfigurasi mypy.
- Siklus hidup presentasi Google Slides saat push berulang.

Detail lengkap ada di Bagian 19.

---

## 3. Arsitektur Target dan Struktur Package

### 3.1 Prinsip Arsitektur

1. **Satu sumber kebenaran per input.** `.md` adalah sumber dokumen. `.yaml` adalah sumber deck. Tidak ada sumber kedua di PPTX, DOCX, PDF, atau Google Slides.
2. **Compiler adalah satu-satunya pembaca YAML.** Renderer tidak membaca YAML langsung.
3. **Design system adalah satu-satunya sumber visual deck.** Renderer tidak boleh menulis angka warna, font, margin, atau radius baru.
4. **Flat key adalah kontrak lintas target.** Key yang sama dipakai untuk PPTX, coverage, dan sinkronisasi Slides.
5. **Renderer tidak menciptakan copy.** Semua teks berasal dari YAML atau dari chrome yang diizinkan dan terdaftar.
6. **Satu arah data untuk chart.** YAML ke Sheets, bukan sebaliknya.
7. **Gagal keras.** Tidak ada fallback ke HTML, LibreOffice, screenshot chart, shrink text, atau template eksternal.
8. **Windows eksplisit.** COM dan path Windows adalah bagian dari kontrak, bukan tambahan opsional.

### 3.2 Lapisan

| Lapisan | Lokasi usulan | Tanggung jawab | Tidak boleh berisi |
| --- | --- | --- | --- |
| CLI | `src/autooffice/cli/` | Parsing argumen, target matrix, orkestrasi, exit code, pesan error | Logika layout, akses Google langsung, XML |
| Common | `src/autooffice/common/` | Path, atomic write, hashing, workspace, error dasar | Domain deck, DOCX, atau Google |
| Design | `src/autooffice/design/` | Token, theme, font, kontras, resolusi token | Renderer atau keputusan konten |
| DOCX | `src/autooffice/docx/` | Validasi Markdown, Pandoc, stage DOCX, manifest | Deck, Google, PPTX |
| Deck model | `src/autooffice/deck/model/` | Schema, YAML loader, compiler, Deck IR, key registry, coverage manifest | Renderer, file output, Google |
| Deck blocks | `src/autooffice/deck/blocks/` | Spec dan validasi 11 block type | Layout geometri |
| Deck layout | `src/autooffice/deck/layout/` | Grid 12 kolom, rows, slot preset, measurement, overflow | Membaca YAML, menulis PPTX |
| Deck charts | `src/autooffice/deck/charts/` | Spec chart, placeholder contract, chart native PPTX | Google API langsung |
| PPTX renderer | `src/autooffice/deck/render/pptx/` | Menggambar Deck IR dan LayoutPlan menjadi PPTX | Membaca YAML, akses Google |
| Google | `src/autooffice/google/` | OAuth, Drive, Sheets, Slides, sync, state | Renderer PPTX atau DOCX |
| PDF | `src/autooffice/pdf/` | Word COM dan PowerPoint COM, serialisasi | Logika dokumen atau deck |
| Assets | `src/autooffice/assets/` | Font dan data package | Konten pengguna |
| Tools | `tools/quality/` | Gate lokal, docs checker, test-quality checker, no-legacy checker | Kode runtime |

### 3.3 Struktur File Usulan

```text
autooffice/                              # root repo setelah rename
  pyproject.toml
  uv.lock
  README.md
  AGENTS.md
  LICENSE
  src/
    autooffice/
      __init__.py
      __main__.py
      errors.py
      cli/
        __init__.py
        main.py
        build.py
        check.py
        doctor.py
        targets.py
        outputs.py
      common/
        paths.py
        workspace.py
        hashing.py
        atomic.py
        text.py
      design/
        __init__.py
        tokens.py
        theme.py
        fonts.py
        contrast.py
        data/
          tokens.yaml
          themes.yaml
      docx/
        __init__.py
        command.py
        validate.py
        pipeline.py
        stages/
        package/
        config/
        adeu/
        terms/
        data/
          formats/
          structures/
          glossary/
          reference/
      deck/
        __init__.py
        model/
          schema.py
          loader.py
          keys.py
          bindings.py
          compiler.py
          deck_ir.py
          coverage.py
          markdown.py
        blocks/
          registry.py
          specs.py
          text.py
          bullets.py
          image.py
          table.py
          chart.py
          code.py
          quote.py
          diagram.py
          divider.py
          spacer.py
          metric.py
        copy/
          __init__.py
          config.py
          diagnostics.py
          checker.py
          rules/
            banned_phrases.py
            title_case.py
            dash.py
            sentence_length.py
            patterns.py
        transcript/
          __init__.py
          parser.py
          model.py
        layout/
          registry.py
          grid.py
          measure.py
          slot.py
          overflow.py
          presets/
            cover.py
            toc.py
            content.py
            section.py
            closing.py
            kpi.py
            bars.py
            line.py
            donut.py
            table.py
            comparison.py
            matrix.py
            background.py
            flow.py
            code.py
            diagram.py
            image_split.py
            image_full.py
            image_grid.py
          custom.py
        charts/
          spec.py
          native.py
          placeholder.py
          colors.py
        render/
          __init__.py
          pptx/
            __init__.py
            renderer.py
            shapes.py
            textbox.py
            table.py
            image.py
            notes.py
            coverage.py
            fonts.py
            theme.py
            xml.py
      google/
        __init__.py
        auth.py
        drive.py
        sheets.py
        slides.py
        charts.py
        sync.py
        state.py
        extract.py
        fake.py
      pdf/
        __init__.py
        word.py
        powerpoint.py
        com.py
      assets/
        fonts/
          plus-jakarta-sans/
            OFL.txt
            PlusJakartaSans-Regular.ttf
            PlusJakartaSans-SemiBold.ttf
            PlusJakartaSans-Bold.ttf
            PlusJakartaSans-ExtraBold.ttf
  tests/
    conftest.py
    unit/
    contract/
    golden/
    visual/
    integration/
    smoke/
    fixtures/
  examples/
    docx/
      assignment-single/
      proposal-single/
      thesis-single/
    demo-deck/
      deck.yaml
      copy.yaml
      transcripts.md
      assets/
      diagrams/
  docs/
    README.md
    user/
    dev/
    learn/
    contracts/
    decisions/
  tools/
    quality/
      gate.py
      check_docs.py
      check_tests.py
      check_no_legacy.py
  scripts/
    install-font.ps1
```

Catatan struktur:

- Ini struktur konseptual. Nama modul boleh berubah di Fase 0 bila kontrak tetap.
- `docgen` tidak dipertahankan sebagai subpackage. Kode DOCX dipindahkan ke `autooffice.docx`.
- `deck-studio` tidak dipertahankan sebagai submodule. Kode yang relevan diporting ke `autooffice.deck`.
- Font TTF adalah aset package, bukan file runtime pengguna.
- `tests/fixtures/` boleh berisi YAML, gambar kecil, XML, dan respons Google palsu. File biner besar tidak boleh menjadi satu-satunya bukti kontrak.
- `examples/demo-deck/` adalah deck acceptance, bukan fixture unit test. Fixture unit test harus kecil dan spesifik.

### 3.4 Alur Data

```text
document.md
  -> validasi front matter dan aset
  -> Pandoc
  -> stage DOCX
  -> manifest dan istilah
  -> DOCX
  -> Word COM -> PDF

deck.yaml + transcripts.md
  -> YAML loader strict
  -> compiler
  -> Deck IR + KeyManifest + KeyBinding
  -> transcript parser -> Transcript IR
  -> copy checker (slide/notes/transcript)
  -> layout engine (12-column grid / preset slots)
  -> LayoutPlan
  -> PPTX renderer -> native PPTX
       -> PowerPoint COM -> PDF
       -> staging PPTX -> Google Slides upload
                         -> table preflight
                         -> chart placeholder replacement
                         -> linked Sheets charts
                         -> text sync push/pull/diff/apply
  -> coverage report
```

Aturan alur:

- Tidak ada renderer yang membaca YAML.
- Tidak ada renderer yang membaca token langsung dari disk. Theme yang sudah di-resolve diinjeksi oleh pipeline.
- Tidak ada Google code yang dipanggil saat target tidak meminta Slides.
- Tidak ada COM yang dipanggil saat target tidak meminta PDF atau visual test.
- Semua output ditulis atomik. File sementara tidak boleh menjadi output final.
- Semua error menyebut input, slide ID, block ID, key, dan target bila relevan.

### 3.5 Invariant

1. Satu file YAML per deck, satu file Markdown per dokumen.
2. Satu Deck IR per build deck.
3. Satu KeyManifest per build deck.
4. Satu layout plan per build.
5. Satu renderer PPTX yang dipakai untuk PPTX, PDF PPTX, dan staging Slides.
6. Satu spreadsheet per deck untuk chart.
7. Satu tab Sheets per chart.
8. Satu chart native di PPTX per chart block.
9. Satu linked chart di Google Slides per chart block.
10. Satu sumber teks: YAML atau Markdown.
11. Tidak ada text shrink otomatis.
12. Tidak ada animasi dan transisi.
13. Tidak ada absolute positioning dari authoring.
14. Tidak ada output yang dianggap sukses bila coverage gagal.
15. Satu Transcript IR per build deck bila `transcripts.md` ada.
16. Copy checker tidak memanggil jaringan, LLM, atau Office.

---

## 4. Draft Skema YAML

Bagian ini adalah draft kontrak authoring. Nama field dan slot adalah usulan yang harus dibekukan di Fase 0.

### 4.1 Prinsip Skema

- Satu file YAML per deck. Tidak ada include, partial, atau file slide terpisah.
- YAML harus UTF-8.
- Loader memakai safe loader. Tag YAML kustom, object Python, dan eksekusi kode ditolak.
- Key yang tidak dikenal ditolak. Tidak ada `extra` atau `metadata` bebas.
- Nilai teks tidak boleh kosong atau hanya spasi, kecuali field yang memang opsional dan tidak ditulis.
- Semua nilai yang tampil adalah string setelah inline Markdown diproses. Chart values adalah angka.
- YAML tidak boleh mendefinisikan warna, font, ukuran, margin, atau koordinat.
- Semua path aset relatif terhadap direktori file YAML.
- Semua ID stabil. Reorder slide atau block tidak boleh mengubah key.
- `slides` minimal satu.
- `layout` default `content` bila tidak ditulis, tetapi setiap slide acceptance sebaiknya menulisnya eksplisit.

### 4.2 Top-Level

| Field | Tipe | Wajib | Aturan |
| --- | --- | --- | --- |
| `schema` | string | ya | Harus `autooffice.deck/v1`. |
| `meta` | object | ya | Metadata deck. Strict. |
| `theme` | object | tidak | Default `indigo`. Hanya nama theme yang boleh. |
| `defaults` | object | tidak | Default authoring yang tidak mengubah desain. |
| `slides` | array | ya | Minimal satu slide. Urutan array adalah urutan presentasi. |

Tidak ada field top-level lain.

### 4.3 `meta`

| Field | Tipe | Wajib | Aturan |
| --- | --- | --- | --- |
| `title` | string | ya | Judul deck dan nama presentasi. Tidak boleh kosong. |
| `subtitle` | string | tidak | Subjudul deck. |
| `author` | string | ya | Nama penulis atau tim. |
| `organization` | string | tidak | Organisasi. |
| `date` | string | tidak | Tanggal atau tahun tampilan. |
| `language` | string | tidak | Default `id-ID`. Nilai BCP 47 sederhana. |
| `description` | string | tidak | Deskripsi internal, tidak dirender ke slide. |

`meta` tidak boleh berisi token, path output, ID Google, atau state build. Semua state runtime disimpan di state file (Bagian 10), bukan di YAML.

### 4.4 `theme`

```yaml
theme:
  name: indigo
```

| Field | Tipe | Wajib | Aturan |
| --- | --- | --- | --- |
| `name` | string | ya jika `theme` ada | `indigo` atau `hitam`. Default `indigo`. |

Tidak ada override token, warna aksen, atau font di YAML. Design system memiliki nilai visual.

### 4.5 `defaults`

| Field | Tipe | Wajib | Aturan |
| --- | --- | --- | --- |
| `layout` | string | tidak | Default `content`. Dipakai hanya bila slide tidak menulis `layout`. |
| `image_fit` | string | tidak | `contain` atau `cover`. Default `contain`. |
| `code_language` | string | tidak | Default `text`. Dipakai bila block code tidak menulis `language`. |

Tidak ada default warna, spacing, atau ukuran.

### 4.6 Slide

```yaml
slides:
  - id: s03
    layout: kpi
    notes: |
      Catatan pembicara.
    source:
      text: "Sumber: data internal AutoOffice, 2026"
      url: "https://example.com/data"
    blocks:
      - id: title
        type: text
        role: title
        text: "Metrik utama"
```

| Field | Tipe | Wajib | Aturan |
| --- | --- | --- | --- |
| `id` | string | ya | Pola `^s[0-9]{2,}$`. Unik. Tidak di-renumber saat reorder. |
| `layout` | string | tidak | Salah satu layout di Bagian 6. Default dari `defaults.layout`. |
| `notes` | string | tidak | Catatan pembicara. Plain text. Disinkronkan sebagai teks. |
| `source` | object | tidak | Sumber slide. `text` wajib bila object ada. `url` opsional. |
| `blocks` | array | kondisional | Wajib untuk preset layout. Terlarang untuk `layout: custom`. |
| `rows` | array | kondisional | Wajib untuk `layout: custom`. Terlarang untuk preset layout. |

Aturan tambahan:

- `blocks` dan `rows` saling eksklusif.
- `source.text` adalah satu key. `source.url` bukan key karena tidak tampil sebagai teks.
- `notes` bukan bagian dari visual slide, tetapi tetap content key dan ikut sinkronisasi teks.
- `layout: custom` tidak memakai slot preset.
- Preset layout tidak menerima `span`; geometri milik preset.

### 4.7 Block Umum

Setiap block memiliki:

| Field | Tipe | Wajib | Aturan |
| --- | --- | --- | --- |
| `id` | string | ya | Pola `^[a-z][a-z0-9_]*$`, maksimal 32 karakter, unik per slide. |
| `type` | string | ya | Salah satu dari 11 block type. |
| `span` | integer | hanya custom | 1 sampai 12. Wajib di custom, terlarang di preset. |

Block tidak memiliki `x`, `y`, `left`, `top`, `width`, `height`, `z`, atau `position`.

Aturan `role`:

- Pada preset layout, role visual ditentukan slot. Bila block `text` menulis `role`, nilainya harus sama dengan role slot. Perbedaan ditolak.
- Pada `custom`, `role` menentukan tipografi block. Default `body`.
- `role` tidak mengubah geometri, hanya skala tipografi dari design system.

### 4.8 Semua Block Type

#### `text`

```yaml
- id: q1
  type: text
  heading: "Prioritas"
  text: "Perbaiki kontrak **key** lebih dulu."
  role: body
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `heading` | tidak | Inline Markdown satu baris. Menghasilkan key `.heading`. |
| `text` | ya | Inline Markdown, boleh beberapa paragraf. Menghasilkan key `.text`. |
| `role` | tidak | `display`, `title`, `lead`, `body`, `caption`, `label`, atau `kicker`. Default `body`. Slot preset dapat menetapkan role. |

#### `bullets`

```yaml
- id: agenda
  type: bullets
  items:
    - "Satu sumber kebenaran."
    - "Key datar yang stabil."
  ordered: false
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `items` | ya | Minimal satu string. Setiap item inline Markdown satu paragraf. |
| `ordered` | tidak | Boolean. Default `false`. |

Key item: `<slide>.<block>.item1.text`, `<slide>.<block>.item2.text`, dan seterusnya.

#### `image`

```yaml
- id: hero
  type: image
  path: "assets/hero.png"
  alt: "Tim sedang meninjau arsitektur AutoOffice"
  caption: "Sesi desain, 2026"
  fit: contain
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `path` | ya | Path relatif. Format `.png`, `.jpg`, `.jpeg`, `.webp`. SVG tidak diterima. |
| `alt` | ya | Alt text manusia. Bukan key teks, tetapi wajib untuk coverage aksesibilitas. |
| `caption` | tidak | Key `.caption`. |
| `fit` | tidak | `contain` atau `cover`. Default dari `defaults.image_fit`. |

`cover` tidak boleh meregangkan gambar. Crop memakai crop native, bukan resize non-proposional.

#### `table`

```yaml
- id: budget
  type: table
  columns:
    - "Lane"
    - "Deliverable"
    - "Status"
  rows:
    - ["Model", "Skema dan compiler", "Selesai"]
    - ["PPTX", "Native chart", "Berjalan"]
  caption: "Status lane per minggu"
  emphasis_column: 3
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `columns` | ya | Minimal satu header. Inline Markdown sederhana. |
| `rows` | ya | Minimal satu baris. Jumlah sel setiap baris harus sama dengan jumlah kolom. |
| `caption` | tidak | Key `.caption`. |
| `emphasis_column` | tidak | 1-based. Hanya valid untuk layout `comparison`. |

Table v1 tidak mendukung merged cell, nested table, atau rowspan/colspan.

Table wajib dirender sebagai native table di PPTX dan Google Slides. Di PPTX dibuat dengan `shapes.add_table`; di Google Slides harus menjadi page element `table` yang editable. Tabel tidak boleh menjadi gambar. Bila konversi impor menghasilkan image atau kumpulan shape, build/push gagal.

#### `chart`

```yaml
- id: adoption
  type: chart
  kind: line
  title: "Adopsi per kuartal"
  alt: "Grafik garis adopsi 2025 dan 2026 naik setiap kuartal"
  categories: ["Q1", "Q2", "Q3", "Q4"]
  series:
    - name: "2025"
      values: [12, 18, 27, 35]
    - name: "2026"
      values: [20, 29, 41, 52]
  unit: "persen"
  caption: "Target internal, 2026"
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `kind` | ya | `bar`, `line`, atau `donut`. |
| `orientation` | tidak | `vertical` atau `horizontal`. Hanya untuk `bar`. Default `vertical`. |
| `title` | ya | Plain text, bukan inline Markdown. |
| `alt` | ya | Deskripsi aksesibilitas. |
| `categories` | ya | Minimal dua label. `donut` maksimal empat kategori berwarna. Plain text. |
| `series` | ya | 1-4 seri. `donut` tepat satu seri. |
| `series[].name` | ya | Plain text. |
| `series[].values` | ya | Angka. Jumlah nilai sama dengan jumlah categories. |
| `unit` | tidak | Label unit yang tampil. Plain text. |
| `caption` | tidak | Key `.caption`. |

Jumlah slot warna per chart maksimal empat: jumlah seri untuk `bar` dan `line`, jumlah kategori untuk `donut`. Batas ini berlaku untuk semua theme karena palet chart AutoOffice hanya memiliki empat warna; dengan begitu pergantian theme tidak mengubah validitas deck. Bila membutuhkan lebih dari empat slot warna, penulis dapat memecahnya menjadi beberapa chart atau menyajikannya sebagai tabel; ini panduan authoring, bukan transformasi otomatis.

Chart TIDAK BOLEH menjadi gambar. Di PPTX harus native chart. Di Google Slides harus linked Sheets chart.

#### `code`

```yaml
- id: snippet
  type: code
  language: python
  filename: "keys.py"
  line_numbers: true
  code: |
    def key(slide_id: str, block_id: str) -> str:
        return f"{slide_id}.{block_id}.text"
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `language` | tidak | Default dari `defaults.code_language`. |
| `filename` | tidak | Key `.filename` bila dirender. |
| `line_numbers` | tidak | Boolean. Default `true`. Nomor baris adalah chrome. |
| `code` | ya | Plain text literal. Boleh banyak baris. Tidak diparse sebagai Markdown. |

Key utama: `.code`. Code tidak boleh di-shrink agar muat. Bila tidak muat, build gagal.

#### `quote`

```yaml
- id: quote1
  type: quote
  text: "Kontrak lebih murah daripada perbaikan setelah integrasi."
  attribution: "Prinsip tim AutoOffice"
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `text` | ya | Inline Markdown. |
| `attribution` | tidak | Inline Markdown satu baris. |

#### `diagram`

```yaml
- id: process
  type: diagram
  source: "diagrams/process.mmd"
  alt: "Diagram alur build dari YAML sampai PPTX"
  caption: "Alur build deck"
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `source` | ya | Path relatif ke file `.mmd`. Satu file satu diagram. |
| `alt` | ya | Alt text manusia. |
| `caption` | tidak | Key `.caption`. |

Diagram dirender oleh `mmdc` menjadi gambar. Tidak ada node atau edge native di PPTX maupun Google Slides.

#### `divider`

```yaml
- id: line1
  type: divider
```

Tidak punya field teks. Tidak punya key. Ketebalan dan warna dari token.

#### `spacer`

```yaml
- id: gap1
  type: spacer
  size: md
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `size` | tidak | `sm`, `md`, atau `lg`. Default `md`. Nilai berasal dari token. |

Tidak punya key. Spacer bukan tinggi absolut.

#### `metric`

```yaml
- id: kpi1
  type: metric
  label: "Coverage"
  value: "100%"
  caption: "Gate final"
  status: success
```

| Field | Wajib | Aturan |
| --- | --- | --- |
| `label` | ya | Inline Markdown satu baris. |
| `value` | ya | Inline Markdown satu baris. |
| `caption` | tidak | Inline Markdown satu baris. |
| `status` | tidak | `neutral`, `success`, `warning`, `danger`. Default `neutral`. |

Key: `.label`, `.value`, `.caption`.

### 4.9 `source`

```yaml
source:
  text: "Sumber: laporan internal AutoOffice, 2026"
  url: "https://example.com/laporan"
```

Aturan:

- `text` wajib bila `source` ada.
- `text` adalah plain text, bukan Markdown.
- `url` opsional. Hanya `https://` atau `http://`.
- `source.text` adalah key `sNN.source.text`.
- Posisi source diatur layout; author tidak boleh mengatur posisi.
- Bila `url` ada, teks source menjadi hyperlink. URL bukan key.

### 4.10 `notes`

`notes` adalah plain text, boleh multiline.

```yaml
notes: |
  Jelaskan bahwa key yang sama dipakai oleh PPTX dan Google Slides.
  Jangan membahas detail implementasi di slide.
```

Aturan:

- Key: `sNN.notes`.
- Tidak dirender ke slide.
- Ikut push/pull/diff/apply.
- Whitespace dinormalisasi dengan aturan preserve-newline (Bagian 5.7).

### 4.11 Inline Markdown

Inline Markdown hanya berlaku pada field yang dinyatakan boleh.

Sintaks yang diizinkan:

- `**bold**`
- `` `inline code` ``
- `[label](https://example.com)` dengan skema `https`, `http`, atau `mailto`
- Escape `\*`, `\_`, `\``, `\[`, dan `\]`

Italic `*...*` TIDAK didukung di v1. Ini menjaga font embedding dan pemetaan run tetap deterministik tanpa menambah varian italic yang tidak ada di design system. Bila nanti italic dibutuhkan, tambahkan font italic resmi, token, test, dan ADR terlebih dahulu.

Sintaks yang ditolak:

- Heading `#`.
- List Markdown. Daftar harus memakai block `bullets`.
- Gambar Markdown.
- Table Markdown.
- Blockquote Markdown.
- HTML mentah.
- Footnote.
- Referensi berbasis identifier.
- Link relatif atau `file://`.

Aturan render:

- Format rich text dipetakan ke run PPTX dan text style Google Slides saat upload. Sinkronisasi teks setelahnya bersifat plain text.
- Tag format tidak boleh mengubah nilai plain text. Contoh: `**Halo**` memiliki plain text `Halo`.
- Link menampilkan label, bukan URL mentah.
- Field `chart.title`, `chart.categories`, `chart.series[].name`, `chart.unit`, `notes`, `code`, `source.text`, dan `image.alt` adalah plain text. Markdown pada field itu ditolak atau diperlakukan literal sesuai kontrak Fase 0.
- Teks tidak boleh memakai em dash (U+2014) atau en dash (U+2013). Gunakan tanda hubung biasa, titik dua, atau tanda kurung. Aturan ini diwarisi dari disiplin naskah deck-studio.

### 4.12 Path Aset

- Path relatif terhadap direktori YAML.
- Gunakan `/`, bukan `\`.
- Path absolut, UNC, drive letter, `..`, dan URL remote ditolak.
- Symlink yang keluar dari root deck ditolak.
- File harus ada saat `check` dan `build`.
- Gambar yang diterima: `.png`, `.jpg`, `.jpeg`, `.webp`. WebP dikonversi ke PNG di cache build.
- Mermaid: `.mmd`.
- SVG tidak diterima sebagai gambar input.
- File font tidak boleh diambil dari path pengguna. Font hanya dari package.
- Semua gambar dan diagram wajib punya `alt`.
- File yang tidak dipakai tidak dianggap error, tetapi docs checker atau test acceptance boleh menandainya sebagai aset yatim.

### 4.13 Contoh Deck Beberapa Slide

Contoh ini menunjukkan cover, content, kpi, line chart, table, image-grid, dan custom grid. Contoh block lain ada di Bagian 4.8.

```yaml
schema: autooffice.deck/v1

meta:
  title: "Dari Dokumen ke Deck"
  subtitle: "Satu model isi, tiga target"
  author: "Tim AutoOffice"
  organization: "AutoOffice"
  date: "2026"
  language: "id-ID"

theme:
  name: indigo

defaults:
  layout: content
  image_fit: contain
  code_language: text

slides:
  - id: s01
    layout: cover
    notes: |
      Buka dengan alasan konsolidasi: satu model konten, satu key, satu quality gate.
    blocks:
      - id: kicker
        type: text
        role: kicker
        text: "AUTOOFFICE"
      - id: title
        type: text
        role: display
        text: "Dari dokumen ke deck"
      - id: subtitle
        type: text
        role: lead
        text: "Satu model isi untuk DOCX, PPTX, PDF, dan Google Slides."
      - id: author
        type: text
        role: label
        text: "Tim AutoOffice"
      - id: summary
        type: metric
        label: "Layout"
        value: "19 + custom"
        caption: "preset tervalidasi"

  - id: s02
    layout: content
    source:
      text: "Sumber: dokumen desain internal AutoOffice, 2026"
    blocks:
      - id: title
        type: text
        role: title
        text: "Yang berubah"
      - id: agenda
        type: bullets
        items:
          - "Satu berkas YAML per deck."
          - "Key datar yang stabil dipakai renderer dan sync."
          - "Chart native, bukan gambar chart."
          - "Quality gate lokal yang ketat."
      - id: note
        type: text
        role: caption
        text: "Tidak ada HTML, XLSX, animasi, atau absolute positioning."

  - id: s03
    layout: kpi
    blocks:
      - id: title
        type: text
        role: title
        text: "Target kualitas"
      - id: kpi1
        type: metric
        label: "Coverage"
        value: "100%"
        caption: "baris dan branch"
        status: success
      - id: kpi2
        type: metric
        label: "Package"
        value: "1"
        caption: "autooffice"
      - id: kpi3
        type: metric
        label: "Theme"
        value: "2"
        caption: "indigo dan hitam"
      - id: kpi4
        type: metric
        label: "CI"
        value: "0"
        caption: "gate lokal"

  - id: s04
    layout: line
    source:
      text: "Sumber: metrik internal, 2026"
    blocks:
      - id: title
        type: text
        role: title
        text: "Adopsi per kuartal"
      - id: chart1
        type: chart
        kind: line
        title: "Pengguna aktif"
        alt: "Grafik garis pengguna aktif 2025 dan 2026 naik setiap kuartal"
        categories: ["Q1", "Q2", "Q3", "Q4"]
        series:
          - name: "2025"
            values: [12, 18, 27, 35]
          - name: "2026"
            values: [20, 29, 41, 52]
        unit: "persen"

  - id: s05
    layout: table
    blocks:
      - id: title
        type: text
        role: title
        text: "Status lane"
      - id: table1
        type: table
        columns: ["Lane", "Deliverable", "Status"]
        rows:
          - ["DOCX", "Parity docgen", "Wajib"]
          - ["Deck", "YAML dan key", "Wajib"]
          - ["Slides", "Linked chart", "Wajib"]
        caption: "Ringkasan dependency"

  - id: s06
    layout: image-grid
    source:
      text: "Sumber: dokumentasi internal AutoOffice"
    blocks:
      - id: title
        type: text
        role: title
        text: "Tiga permukaan"
      - id: image1
        type: image
        path: "assets/docx.png"
        alt: "Contoh halaman DOCX"
        caption: "DOCX"
      - id: image2
        type: image
        path: "assets/pptx.png"
        alt: "Contoh slide PPTX"
        caption: "PPTX"
      - id: image3
        type: image
        path: "assets/slides.png"
        alt: "Contoh presentasi Google Slides"
        caption: "Slides"

  - id: s07
    layout: custom
    notes: |
      Layout custom dipakai hanya bila preset tidak cukup.
    source:
      text: "Sumber: data internal, 2026"
    rows:
      - blocks:
          - id: eyebrow
            type: text
            role: kicker
            text: "STUDI KASUS"
            span: 12
          - id: title
            type: text
            role: title
            text: "Komposisi grid 12 kolom"
            span: 7
          - id: lead
            type: text
            role: lead
            text: "Tinggi mengikuti isi. Tidak ada koordinat absolut."
            span: 5
      - blocks:
          - id: chart1
            type: chart
            kind: bar
            title: "Waktu build"
            alt: "Diagram batang waktu build per target"
            categories: ["DOCX", "PPTX", "Slides"]
            series:
              - name: "Detik"
                values: [4, 9, 14]
            span: 7
          - id: insight
            type: text
            role: body
            heading: "Catatan"
            text: "Chart tetap native di PPTX dan linked di Google Slides."
            span: 5
```

### 4.14 Batas Skema yang Disengaja

- Tidak ada `if` atau ekspresi di YAML.
- Tidak ada perhitungan angka di YAML.
- Tidak ada style inline.
- Tidak ada `font_size`, `color`, `margin`, atau `padding` per block.
- Tidak ada posisi absolut.
- Tidak ada multi-column di dalam block.
- Tidak ada nested row.
- Tidak ada block `callout`.
- Tidak ada chart dua arah.
- Tidak ada Mermaid inline.
- Tidak ada gambar remote.
- Tidak ada HTML di teks.
- Tidak ada template PPTX.

### 4.15 Berkas Pendamping: `transcripts.md`

Transkrip adalah naskah pembicara, bukan teks slide dan bukan notes. Transkrip disimpan sebagai berkas Markdown terpisah di folder deck:

```text
examples/demo-deck/
  deck.yaml
  copy.yaml
  transcripts.md
```

Aturan:

- Opsional. Bila tidak ada, tidak ada output transkrip dan tidak ada error.
- UTF-8, newline LF.
- Judul dokumen H1 bebas.
- Satu bagian per slide dengan heading `## <slide_id>. <judul slide>`.
- `<slide_id>` harus cocok dengan slide di YAML. Tidak boleh duplikat, tidak boleh slide asing.
- Bila `transcripts.md` ada, semua slide harus punya satu bagian. Urutan bagian bebas; mapping memakai ID, bukan posisi.
- `### Indonesia` wajib. `### English` opsional. Bila ada, diperiksa dengan rule pack Inggris.
- `**Perkiraan durasi:** <detik> detik` opsional; bila ada, bilangan bulat positif.
- Isi bagian adalah prosa Markdown biasa; tidak ada key YAML.
- Transkrip tidak disinkronkan ke Google Slides dan tidak masuk PPTX notes.
- Output: `<stem>.transcript.md` di direktori output yang sama dengan PPTX.

Heading memakai titik setelah slide ID, bukan em dash atau en dash, agar tidak melanggar aturan dash.

### 4.16 Berkas Pendamping: `copy.yaml`

`copy.yaml` opsional di folder deck. Tanpa file ini, default bawaan berlaku. Contoh:

```yaml
schema: 1

targets:
  slides: true
  notes: true
  transcript: true

rules:
  banned_phrases:
    severity: error
    extra:
      id:
        - "frasa yang dilarang"
      en:
        - "phrase to ban"
  title_case:
    severity: error
  dash:
    severity: error
  sentence_length:
    severity: warning
    max_words: 25
  negative_parallelism:
    severity: error
  contrast_pattern:
    severity: error
  forced_triad:
    severity: warning
  one_line_closer:
    severity: warning
  paired_clause_label:
    severity: warning

allow:
  - key: "s05.chart.title"
    rules: [sentence_length]
    reason: "Label chart pendek"
```

Aturan:

- File opsional; default bawaan tetap berlaku.
- Default `targets`: `slides: true`, `notes: true`, `transcript: true`. Bila blok `targets` tidak ditulis, ketiganya berlaku.
- Schema strict; key unknown ditolak.
- Merge per rule: key yang tidak ditulis memakai default. `enabled: false` atau `severity: off` mematikan rule.
- `allow` wajib punya `reason`, `key` harus ada, dan `rules` harus nama rule yang dikenal.
- `allow` hanya menekan diagnostic yang cocok; tidak menekan error schema atau kegagalan transcript.
- `extra` adalah map per bahasa (`id`, `en`) berisi frasa literal, bukan regex. Frasa `id` hanya diperiksa pada teks Indonesia; frasa `en` hanya pada teks Inggris. Regex tidak diterima.
- `copy.yaml` harus berada di folder deck yang sama dengan YAML; path traversal ditolak.
- Tidak ada target DOCX. File `.md` tidak membaca `copy.yaml`.
- Bila `targets.transcript: true` tetapi `transcripts.md` tidak ada, tidak ada error; transcript tetap opsional.

---

## 5. Key Grammar dan Compiler

### 5.1 Tujuan Compiler

Compiler mengubah YAML bertingkat menjadi:

1. `DeckIR`: model yang sudah tervalidasi, siap dilayout.
2. `KeyManifest`: daftar semua key, nilai tampilan, nilai plain text, dan kelas sinkronisasi.
3. `KeyBinding`: pemetaan dua arah antara key dan path YAML, untuk pull/apply.
4. `CoveragePlan`: daftar key yang wajib muncul di setiap target.
5. `LayoutPlan`: hasil layout engine, berisi posisi yang dihitung dari grid, bukan dari YAML.

Renderer hanya menerima `DeckIR`, `LayoutPlan`, dan `Theme`. Renderer tidak menerima path YAML.

### 5.2 Bentuk Key

Key datar:

```text
<slide_id>.<block_id>.<leaf>
```

Untuk key milik slide sendiri:

```text
<slide_id>.<leaf>
```

Contoh:

```text
s01.title.text
s01.notes
s01.source.text
s03.kpi1.value
s03.kpi1.caption
s04.chart1.series1.value3
s05.table1.r2.c3
s07.insight.text
```

### 5.3 Aturan ID

Slide:

- Pola `^s[0-9]{2,}$`.
- Wajib ditulis eksplisit.
- Unik dalam deck.
- Tidak di-renumber saat slide dipindahkan.
- Nomor halaman adalah posisi tampilan, bukan ID.
- Menghapus atau mengganti ID adalah perubahan kontrak yang memerlukan migrasi key.

Block:

- Pola `^[a-z][a-z0-9_]*$`.
- Maksimal 32 karakter.
- Unik dalam satu slide.
- Tidak boleh mengandung titik.
- Block boleh dipindahkan di dalam slide tanpa mengubah key.
- Mengganti ID block adalah perubahan kontrak yang memerlukan migrasi key.

Leaf:

- Nama field dari block.
- Indeks selalu 1-based.
- Bentuk indeks yang diizinkan: `itemN`, `catN`, `seriesN`, `valueN`, `rN`, `cN`, `hN`.
- Segmen hanya huruf kecil, angka, dan underscore. Tidak ada spasi, tanda hubung, atau titik di dalam satu segmen.
- Panjang key maksimal 160 karakter. Bila lebih, schema harus disederhanakan, bukan dipotong diam-diam.

#### 5.3.1 Konsekuensi ID Stabil

- Urutan ID tidak mencerminkan urutan tampil. Setelah reorder, urutan boleh menjadi `s03`, `s01`, `s02`; ini disengaja, bukan error.
- Menyisipkan slide memerlukan ID baru yang belum dipakai (misalnya `s25`), bukan menggeser ID slide lain.
- ID duplikat ditolak validator dengan pesan yang menyebut kedua slide.
- Mengganti ID memerlukan migrasi key dan memutus mapping sync Google Slides lama; ini dicatat di dokumentasi migrasi.
- Nomor halaman, nomor slide di UI, dan urutan array tetap mengikuti posisi, bukan ID.

### 5.4 Grammar Formal

```text
key            = slide_id "." path
path           = block_path | slide_path
block_path     = block_id "." leaf_path
slide_path     = "notes" | "source" "." "text"
slide_id       = "s" 2*DIGIT
block_id       = LOWER *(LOWER / DIGIT / "_")
leaf_path      = leaf_segment *("." leaf_segment)
leaf_segment   = LOWER *(LOWER / DIGIT / "_")
```

Aturan semantik:

- `slide_id` harus cocok dengan slide yang memiliki block.
- `block_path` harus cocok dengan block yang ada.
- `leaf_path` harus cocok dengan schema block type.
- Indeks 1-based dan tidak boleh nol.
- Key tidak boleh duplikat.
- Key tidak boleh kosong.
- Key harus stabil lintas reorder.

### 5.5 Mapping Nested YAML ke Flat Key

| Lokasi YAML | Key |
| --- | --- |
| `slides[id=s03].blocks[id=title].text` | `s03.title.text` |
| `slides[id=s03].blocks[id=title].heading` | `s03.title.heading` |
| `slides[id=s03].blocks[id=kpi1].value` | `s03.kpi1.value` |
| `slides[id=s03].blocks[id=agenda].items[0]` | `s03.agenda.item1.text` |
| `slides[id=s03].blocks[id=table1].columns[1]` | `s03.table1.h2` |
| `slides[id=s03].blocks[id=table1].rows[2][3]` | `s03.table1.r3.c4` |
| `slides[id=s03].blocks[id=chart1].categories[1]` | `s03.chart1.cat2` |
| `slides[id=s03].blocks[id=chart1].series[0].name` | `s03.chart1.series1.name` |
| `slides[id=s03].blocks[id=chart1].series[0].values[2]` | `s03.chart1.series1.value3` |
| `slides[id=s03].blocks[id=img1].caption` | `s03.img1.caption` |
| `slides[id=s03].notes` | `s03.notes` |
| `slides[id=s03].source.text` | `s03.source.text` |

Mapping ini adalah kontrak. Compiler tidak boleh mengubah nama leaf tanpa ADR.

### 5.6 KeyBinding

Setiap key harus punya binding:

```json
{
  "key": "s03.kpi1.value",
  "slide_id": "s03",
  "block_id": "kpi1",
  "leaf": "value",
  "kind": "text",
  "sync": true,
  "yaml_path": ["slides", 2, "blocks", 1, "value"],
  "value": "100%",
  "plain_text": "100%"
}
```

Aturan:

- `yaml_path` disimpan oleh compiler. Pull/apply memakai `yaml_path`, bukan menebak dari string key.
- `value` adalah string sumber untuk teks atau angka untuk data chart.
- `plain_text` adalah nilai tampilan setelah inline Markdown dan normalisasi.
- `kind` adalah `text`, `data`, `notes`, `source`, atau `media_text`.
- `sync` menunjukkan apakah key termasuk sinkronisasi teks Google Slides.
- Binding tidak boleh memiliki key duplikat.
- Binding harus deterministik. Compiler tidak boleh memakai hash acak atau urutan dictionary yang tidak stabil.

### 5.7 Normalisasi Nilai

Dua mode normalisasi:

1. **Inline text** untuk `text`, `heading`, `bullets`, `table`, `quote`, `metric`, `caption`, dan `source`:
   - konversi CRLF ke LF;
   - parse inline Markdown;
   - buang penanda format;
   - pertahankan teks label link;
   - ubah whitespace berulang di dalam baris menjadi satu spasi;
   - trim awal dan akhir;
   - nilainya tidak boleh kosong.
2. **Preserve newline** untuk `notes` dan `code`:
   - konversi CRLF ke LF;
   - trim baris kosong di awal dan akhir;
   - pertahankan baris baru internal;
   - jangan mengubah spasi di dalam baris.

Chart labels memakai normalisasi 1, tanpa inline Markdown. Chart values adalah angka dan tidak dinormalisasi sebagai teks.

Nilai pulled dari Google Slides dinormalisasi dengan mode yang sama. Diff membandingkan `plain_text`, bukan YAML mentah.

### 5.8 Key Coverage

Coverage memeriksa:

- Setiap key yang dideklarasikan muncul tepat satu kali di output.
- Tidak ada key asing yang tidak dideklarasikan.
- Key berada di slide yang benar.
- Key tidak kosong.
- Table cell key hanya dihitung bila sel benar-benar ada di tabel native.
- Chart data key diverifikasi dari chart spec atau chart XML, bukan dari teks bebas.
- Notes key diverifikasi dari notes slide.
- Alt text gambar, diagram, dan chart tidak kosong.
- Teks yang terlihat tetapi tidak punya key gagal, kecuali chrome yang terdaftar.

Chrome yang diizinkan:

- Nomor halaman.
- Nomor ordinal yang dihasilkan layout.
- Nomor baris code.
- Label dekoratif yang tidak dapat diedit author dan namanya diawali `chrome:`.

Chrome tidak boleh berisi naskah yang seharusnya berasal dari YAML. Bila ragu, jadikan key.

### 5.9 Coverage Report

Format report minimal:

```json
{
  "schema": "autooffice.coverage/v1",
  "deck_id": "demo-deck",
  "declared": 128,
  "rendered": 128,
  "missing": [],
  "extra": [],
  "duplicate": [],
  "unkeyed_visible": [],
  "missing_alt": [],
  "charts": [
    {"chart_id": "s04.chart1", "native": true, "key": "s04.chart1"}
  ]
}
```

Aturan:

- `missing`, `extra`, `duplicate`, `unkeyed_visible`, dan `missing_alt` harus kosong untuk build sukses.
- Report ditulis ke workspace build.
- `check` boleh mencetak report tanpa menulis file final.
- Report tidak boleh memuat timestamp yang membuat golden test tidak stabil.

### 5.10 Key Stability dan Migrasi

- Reorder slide tidak mengubah key.
- Reorder block dalam satu slide tidak mengubah key.
- Menambah slide dengan ID baru hanya menambah key baru.
- Menghapus slide menghapus key slide itu. Sync harus mendeteksi key hilang di remote dan gagal atau melaporkan konflik.
- Rename slide ID atau block ID adalah breaking change. Perubahan harus disertai:
  - update YAML;
  - update fixture dan golden;
  - catatan migrasi;
  - pemeriksaan bahwa tidak ada remote key lama yang tertinggal.
- Compiler harus menyimpan map key lama ke key baru hanya bila fitur migrasi eksplisit ditambahkan. v1 tidak punya alias key.
- Apply dari Google Slides tidak boleh membuat ID baru. Bila remote punya key yang tidak ada di YAML, apply harus menolak key itu dengan pesan jelas.

---

## 6. Katalog Layout

### 6.1 Prinsip Layout

- Ada 19 preset layout dan satu `custom`.
- Preset memiliki slot dan geometri internal. Author hanya mengisi block yang sesuai.
- Custom memakai `rows` eksplisit dan `span`.
- Layout tidak boleh bercabang berdasarkan nama deck, path input, atau theme.
- Renderer memilih layout hanya dari field `layout`.
- Layout tidak menciptakan teks. Semua teks berasal dari block atau key slide.
- Layout tidak boleh menambah `callout`.
- Layout yang tidak ada di katalog ditolak. Tidak ada fallback layout.

### 6.2 Daftar Layout

| Layout | Asal | Fungsi | Slot wajib | Slot opsional |
| --- | --- | --- | --- | --- |
| `cover` | deck-studio neutral/demo | Pembuka deck | `title`, `author` | `kicker`, `subtitle`, `role`, `summary` (`metric`) |
| `toc` | deck-studio neutral/demo | Daftar isi dalam 1 sampai 3 kelompok | `title`, minimal satu `group1` sampai `group3` (`bullets`) | `lead` |
| `content` | deck-studio Scite, diadaptasi | Halaman narasi dengan daftar poin | `title`, `points` (`bullets`) | `lead`, `note` |
| `section` | **core baru** | Pembatas bab | `title` | `number`, `subtitle` |
| `closing` | deck-studio neutral/demo | Penutup dan kontak | `title`, `contact` | `lead`, `note` |
| `kpi` | deck-studio neutral/demo | Sampai empat metric utama | `title`, minimal satu `kpi1` sampai `kpi4` (`metric`) | `lead` |
| `bars` | deck-studio neutral/demo | Chart batang native | `title`, `chart1` (`chart`, `kind: bar`) | `lead`, `takeaway` |
| `line` | deck-studio neutral/demo | Chart garis native | `title`, `chart1` (`chart`, `kind: line`) | `lead`, `takeaway` |
| `donut` | deck-studio neutral/demo | Chart donat native | `title`, `chart1` (`chart`, `kind: donut`) | `lead`, `takeaway` |
| `table` | deck-studio neutral/demo | Tabel native | `title`, `table1` (`table`) | `lead`, `note` |
| `comparison` | deck-studio neutral/demo | Tabel perbandingan dengan kolom disorot | `title`, `table1` (`table` dengan `emphasis_column`) | `lead`, `note` |
| `matrix` | deck-studio neutral/demo | Empat kuadran | `title`, `q1` sampai `q4` (`text` dengan heading) | `lead`, `check` (`bullets`) |
| `background` | deck-studio neutral/demo | Konteks atau latar keputusan | `title`, `point1` sampai `point3` (`text`) | `kicker`, `lead` |
| `flow` | deck-studio neutral/demo | Empat langkah proses | `title`, `step1` sampai `step4` (`text` dengan heading) | `lead` |
| `code` | deck-studio neutral/demo | Contoh kode dengan catatan | `title`, `code1` (`code`) | `lead`, `note` |
| `diagram` | deck-studio diagrams/demo | Gambar Mermaid | `title`, `diagram1` (`diagram`) | `subtitle` |
| `image-split` | deck-studio demo | Gambar di samping teks | `title`, `body` (`text`), `image1` (`image`) | `lead` |
| `image-full` | deck-studio demo | Gambar penuh kanvas dengan overlay | `title`, `image1` (`image`) | `subtitle`, `credit` (`text`) |
| `image-grid` | deck-studio demo | Tiga gambar dalam grid | `title`, `image1` sampai `image3` (`image`) | `lead` |
| `custom` | **core baru** | Komposisi grid 12 kolom | `rows` minimal satu, setiap row minimal satu block | tidak ada |

Catatan slot:

- Nama slot adalah ID block yang harus dipakai. Contoh: `kpi1`, bukan `kpi_1`.
- Block dengan ID di luar slot preset ditolak.
- Slot opsional boleh tidak ada.
- Slot wajib harus ada.
- `source` adalah field slide, bukan slot. Semua layout yang mendukung source merender source di area footer atau overlay sesuai desain.
- `notes` bukan slot.
- `divider` dan `spacer` tidak dipakai di preset v1 kecuali di `custom`.

### 6.3 Layout deck-studio yang Tidak Didukung v1

Deck-studio memiliki 21 layout. AutoOffice mendukung 18 layout deck-studio, menambahkan `section`, dan menambahkan `custom`. Tiga layout deck-studio berikut **tidak** didukung:

| Layout lama | Alasan | Pengganti v1 |
| --- | --- | --- |
| `image-annotated` | Memakai marks dengan koordinat persen dan overlay yang rumit. Bertentangan dengan target absolute positioning yang minimal. | `image-split`, `image-full`, atau `custom` dengan text dan image. |
| `image-figure` | Terlalu dekat dengan `image-split` dan `image-full`; belum ada kebutuhan acceptance. | `image-split` atau `image-full`. |
| `table-long` | Tabel panjang dapat memakai `table` dengan lebih banyak baris. Layout terpisah tidak menambah kontrak baru. | `table` atau `custom`. |

AutoOffice tidak boleh mengklaim mendukung 21 layout deck-studio. Yang didukung adalah 19 preset di tabel 6.2.

### 6.4 Layout Preset dan Rows

- Preset layout memiliki rows internal yang tidak ditulis author. Ini menjaga desain konsisten dan mencegah author membuat variasi yang tidak terkontrol.
- `custom` adalah satu-satunya layout yang memakai `rows` author.
- Bila maintainer menghendaki `rows` eksplisit untuk semua layout, itu perubahan kontrak dan harus dicatat di Bagian 19. Plan ini memakai interpretasi preset memilikinya sendiri.
- `layout: custom` tidak boleh memiliki slot atau dekorasi preset. Semua isi berasal dari rows.
- `layout: cover` dan layout lain tetap boleh menerima `source` dan `notes`.

### 6.5 Acceptance per Layout

Setiap layout harus memiliki:

1. Fixture YAML minimal.
2. Contract test slot wajib dan slot opsional.
3. Golden layout PPTX yang memeriksa posisi slot, span, key, dan alt.
4. Visual test indigo.
5. Build minimal di hitam.
6. Tidak ada overflow.
7. Tidak ada key asing.

---

## 7. Model Layout

### 7.1 Kanvas dan Grid

- Kanvas 16:9, 13.333 inci x 7.5 inci, ekivalen 1280 x 720 px dan 960 x 540 pt.
- Grid 12 kolom.
- Margin dan gutter berasal dari token desain.
- Kolom dihitung dari lebar konten:

```text
content_width = slide_width - margin_left - margin_right
column_width = (content_width - 11 * gutter) / 12
span_width(span) = span * column_width + (span - 1) * gutter
```

- Angka di atas adalah rumus internal layout engine. Author tidak menulis angka.
- Posisi horizontal block dihitung dari urutan block dalam row dan `span`.
- Tidak ada offset. Sisa kolom di kanan row dibiarkan kosong.
- Tidak ada x/y absolut di YAML.
- Renderer boleh menulis koordinat ke PPTX setelah layout engine menghitungnya. Larangan absolute positioning berlaku pada authoring, bukan pada output XML.

### 7.2 Rows

Custom:

```yaml
rows:
  - blocks:
      - id: title
        type: text
        role: title
        text: "..."
        span: 12
      - id: chart1
        type: chart
        span: 7
        # ...
      - id: insight
        type: text
        span: 5
        # ...
```

Aturan:

- `rows` minimal satu.
- Setiap row minimal satu block.
- Jumlah `span` dalam satu row maksimal 12.
- `span` bilangan bulat 1 sampai 12.
- Block dirender dari kiri ke kanan sesuai urutan array.
- Tidak ada row nesting.
- Tidak ada column nesting.
- Tidak ada row gap override.
- Tinggi row mengikuti konten tertinggi di row itu.
- Block yang lebih pendek tidak boleh memaksa tinggi absolut.
- Row boleh memiliki sisa kolom kosong.
- Tidak ada `offset`, `start`, `col_start`, atau `align` horizontal di v1.

Preset:

- Row dan slot sudah ditentukan layout.
- Author hanya mengisi block dengan ID slot.
- Urutan block di YAML tidak menentukan posisi; layout menempatkan berdasarkan slot.
- `span` pada block preset ditolak.

### 7.3 Tinggi dan Overflow

Kebijakan v1: **fail atau flag, bukan shrink**.

- Text tidak boleh memakai autofit, shrink, atau font size yang diperkecil diam-diam.
- Layout engine mengukur teks dengan metrik font Plus Jakarta Sans yang dibundel.
- Pengukuran memakai lebar slot, padding, dan line-height dari token.
- Bila teks tidak muat di area konten layout, `check` melaporkan error dan `build` gagal.
- Bila tabel tumbuh melebihi area, build gagal.
- Bila code block tidak muat, build gagal.
- Bila row custom tumbuh melebihi area konten slide, build gagal.
- Tidak ada ellipsis otomatis.
- Tidak ada pemotongan teks tanpa peringatan.
- Pesan error harus menyebut slide, block, key, dan perkiraan overflow.

Pengukuran harus deterministik. Jangan memakai browser, PowerPoint COM, atau Google Slides untuk mengukur pada `check`.

### 7.4 Spacing dan Token

- Gutter, padding, margin, radius, shadow, font size, dan line-height berasal dari design token.
- Renderer tidak boleh menulis angka baru.
- Author tidak boleh menulis spacing.
- `spacer.size` hanya memilih token `sm`, `md`, atau `lg`.
- `divider` memakai token garis dan warna.
- Layout preset boleh memiliki padding internal khusus, tetapi nilainya harus token, bukan angka lokal.

### 7.5 Gambar

- `contain`: gambar utuh, tanpa distorsi, area kosong boleh ada.
- `cover`: gambar memenuhi frame, crop proporsional, tidak meregang.
- Crop PPTX memakai crop native.
- Gambar tidak boleh menjadi background tanpa block image.
- `image-full` memakai image block yang menempati kanvas dan overlay teks dari token.
- Alt text wajib.
- Caption adalah key, bukan alt.
- Tidak ada gambar remote.

### 7.6 Table dan Chart

- Table native di PPTX. Header adalah baris pertama tabel native.
- Table tidak mendukung merged cell.
- Lebar kolom dihitung dari isi dan batas layout, bukan dari absolute width.
- Chart native mengisi slot chart. Chart tidak boleh menjadi gambar.
- Chart tidak boleh menutupi teks.
- Chart label minimum mengikuti token tipografi chart.
- Chart legend dan gridline berasal dari token.

### 7.7 Larangan Absolute

Schema harus menolak field berikut di semua objek authoring:

```text
x, y, left, top, right, bottom, width, height,
position, absolute, anchor, translate, rotate, z, z_index
```

Pengecualian hanya untuk field non-geometri yang namanya kebetulan sama, dan harus disetujui di Fase 0. Default: tolak semua.

### 7.8 Custom Grid Level 2

Level 2 berarti:

- Satu tingkat rows, bukan nested grid.
- Setiap row berisi block horizontal.
- Block tidak bisa membuat row sendiri.
- Block tidak bisa mengatur posisi vertical.
- Span hanya horizontal.
- Tinggi mengikuti isi.
- Tidak ada fixed height.
- Tidak ada area overlay di luar block.

Fitur level 3 seperti nested grid, overlay, absolute, dan fixed frame bukan bagian v1.

---

## 8. Renderer

### 8.1 Kontrak Renderer

Setiap renderer menerima:

- `DeckIR`
- `LayoutPlan`
- `Theme`
- `OutputTarget`
- `Workspace`

Setiap renderer mengembalikan:

- path artefak;
- `CoverageReport`;
- daftar warning;
- hash konten;
- metadata target.

Aturan:

- Renderer tidak membaca YAML.
- Renderer tidak membaca file token.
- Renderer tidak menciptakan teks.
- Renderer tidak menulis output final sebelum coverage lulus.
- Renderer tidak boleh menelan error.
- Renderer harus deterministik untuk input yang sama, kecuali timestamp yang dapat dinormalisasi.
- Renderer tidak boleh memakai template eksternal.

### 8.2 DOCX: Migrasi docgen Tanpa Perubahan Perilaku

Tujuan: memindahkan pipeline DOCX yang ada ke `autooffice.docx` tanpa mengubah perilaku.

Yang dipertahankan:

- Satu `document.md` sebagai sumber.
- Front matter.
- Format dan structure YAML dari docgen.
- Pandoc dan `--citeproc`.
- Urutan stage yang sama.
- Satu load dan satu save `DocumentPackage`.
- Part non-target byte-identik.
- Manifest Adeu deterministik.
- Bookmark `pNNNN`.
- TOC, daftar, caption, tabel, code, equation, numbering, page numbers.
- Istilah dan `--terms`.
- Output di samping dokumen, termasuk aturan contoh `examples/*/out/`.
- `report_name` wajib.
- Word COM untuk finalisasi field dan PDF.

Yang berubah hanya:

- Namespace package.
- Entry point CLI.
- Nama flag `--keep` menjadi `--keep-intermediate`.
- Lokasi kode.
- Dokumentasi.

Yang tidak boleh berubah:

- Visual DOCX.
- Byte part yang tidak disentuh.
- Urutan stage.
- Nama file output pengguna.
- Format front matter.
- Perilaku manifest.
- Perilaku istilah.
- Tidak boleh menerapkan design system deck ke DOCX.
- Tidak boleh mengganti font DOCX menjadi Plus Jakarta Sans.

Parity diuji dengan fixture baseline yang dibuat sebelum kode lama dihapus.

### 8.3 PPTX: python-pptx

Spesifikasi:

- Ukuran 16:9, 13.333 x 7.5 inci.
- Dibangun dengan `python-pptx`.
- Semua master, theme color, theme font, dan layout visual dihasilkan dari design token.
- Tidak ada base `.pptx` yang disimpan di repo atau diterima dari user. Presentasi kosong dari library hanyalah container teknis; tidak boleh membawa desain eksternal.
- Slide background dari token.
- Text box, shape, table, chart, image, notes, dan alt text dibuat native.
- Table native.
- Image crop native.
- Chart native.
- Notes native.
- Font Plus Jakarta Sans ditanam di PPTX.
- Tidak ada animasi.
- Tidak ada transisi.
- Tidak ada SmartArt.
- Tidak ada video atau audio.
- Tidak ada placeholder layout yang tidak dipakai.

Text:

- Word wrap aktif.
- Auto-size dimatikan.
- Tidak ada shrink.
- Spasi paragraf dan line-height dari token.
- Teks yang overflow gagal sebelum render atau saat verifikasi layout.
- Minimum font size mengikuti token. Tidak ada teks di bawah 10 pt.

Table:

- Header baris pertama.
- Dibuat dengan `shapes.add_table`, bukan kumpulan shape atau gambar.
- Tanpa merged cell.
- Border dan fill dari token.
- Angka rata kanan, teks rata kiri, ditentukan secara deterministik.
- Key header dan sel ditulis sesuai Bagian 5.
- Frame table membawa key namespace block.
- Cell tidak bisa membawa alt sendiri; coverage membaca tabel nyata.
- Frame table membawa key block dan alt text; cell text dibaca dari XML table native.
- Table tidak boleh diubah menjadi gambar untuk PDF.

Chart:

- `bar` menjadi native bar/column chart.
- `line` menjadi native line chart dengan marker.
- `donut` menjadi native doughnut chart.
- Warna seri dan kategori donut dari `chartSeries` yang lolos kontras 3:1.
- Legend, gridline, axis, dan font dari token.
- Chart title native.
- Data chart native, bukan shape.
- Chart alt text di `descr` dan key chart di metadata yang disepakati.
- Chart tidak boleh diubah menjadi gambar untuk PDF.
- PDF dari PPTX memakai chart native yang sama.

Image:

- Alt text di `descr`.
- Caption sebagai text box berkey.
- Crop proporsional.
- Format WebP dinormalisasi ke PNG sebelum embed.

Notes:

- Notes slide dibuat untuk slide yang punya `notes`.
- Key `sNN.notes`.
- Teks notes tidak tampil di slide.
- Notes disinkronkan ke Google Slides.

Alt text dan key:

- Shape teks berkey memiliki `name` yang memuat key dan alt `title` berisi key yang sama. `description` berisi teks manusia atau deskripsi aksesibilitas.
- Chrome memiliki nama `chrome:*` dan tidak dianggap key.
- Image/diagram memiliki alt manusia dan metadata aset.
- Coverage memeriksa key shape, key table cell, chart, notes, dan alt.

Font embedding:

- TTF Plus Jakarta Sans disertakan dalam package.
- Renderer menambahkan font parts ke OOXML setelah `python-pptx` menyimpan.
- Font yang ditanam: Regular, SemiBold, Bold, ExtraBold.
- Font family harus sama dengan Google Fonts: `Plus Jakarta Sans`.
- Bila font embedding gagal atau menghasilkan PPTX yang tidak valid, build HARUS gagal. Tidak boleh diam-diam mengirim PPTX tanpa font.
- File PPTX harus bisa dibuka PowerPoint tanpa prompt repair.
- Test font embedding memeriksa content type, relationship, dan `embeddedFontLst`.
- Visual test memeriksa fallback font pada mesin bersih bila memungkinkan.

Tanpa animasi/transisi:

- Renderer tidak menulis node timing.
- Renderer tidak menulis transition.
- Test memeriksa tidak ada `<p:timing>` dan tidak ada `<p:transition>`.

Staging Slides:

- `--target slides` membuat staging PPTX internal.
- Staging memakai layout dan teks yang sama.
- Chart diganti placeholder shape, bukan native chart.
- Placeholder punya nama dan alt yang deterministik: `autooffice:chart:<chart_id>`.
- Staging tidak menjadi deliverable kecuali `--keep-intermediate`.
- `pptx` yang menjadi deliverable tetap memakai native chart.

### 8.4 Google Slides

Alur push:

1. Compile YAML.
2. Bangun staging PPTX dengan placeholder chart.
3. Validasi placeholder lengkap.
4. Siapkan spreadsheet dan linked charts di Sheets.
5. Upload staging PPTX ke Drive sebagai Google Slides. Konversi memakai metadata `application/vnd.google-apps.presentation`.
6. Ambil presentation ID baru.
7. Preflight: cari semua placeholder chart dan verifikasi setiap block table sudah menjadi page element `table` native dengan jumlah baris/kolom yang benar.
8. Hapus placeholder dan buat linked chart dengan `createSheetsChart` pada posisi dan ukuran placeholder.
9. Verifikasi jumlah dan ID linked chart.
10. Push teks dan notes.
11. Verifikasi coverage remote.
12. Simpan state.

Aturan presentasi:

- Satu presentation aktif per deck dicatat di state.
- Setiap push membuat presentasi baru dari staging PPTX dan mencatat ID baru. Presentasi lama tidak dihapus otomatis untuk menghindari kehilangan data.
- Ini adalah asumsi operasional yang harus dikonfirmasi. Bila maintainer menghendaki update file yang sama, kontrak Drive harus diuji di Fase 0/2.
- `pull`, `diff`, dan `apply` selalu memakai presentation ID aktif di state.
- Bila state tidak ada, `pull/diff/apply` gagal dengan pesan agar push dilakukan lebih dulu.

Identitas key:

- Teks shape: alt `title` berisi key persis. `description` boleh berisi JSON `{"key":"..."}` sebagai fallback.
- Table: frame membawa key block. Table harus native, bukan image atau kumpulan shape. Cell diturunkan dari posisi tabel. Header baris pertama menjadi `hN`; body menjadi `rN.cM`.
- Notes: dipetakan berdasarkan urutan slide karena notes tidak punya alt per paragraf. Slide order harus sama dengan YAML.
- Chart placeholder: alt `title` berisi `autooffice:chart:<chart_id>`.
- Linked chart setelah replacement tidak dianggap text key.
- Image/diagram tidak disinkronkan sebagai teks; alt tetap diperiksa saat push.

Table native:

- Staging PPTX memuat table native.
- Preflight table berjalan sebelum placeholder chart dihapus; kegagalan table tidak boleh meninggalkan presentasi yang sudah dimutasi.
- Setelah upload, preflight mencari page element `table` untuk setiap block table.
- Elemen harus memiliki `table`, bukan `image` atau kumpulan shape.
- Jumlah baris dan kolom remote harus sama dengan YAML.
- Bila table hilang, menjadi image, menjadi shape group, atau dimensinya berbeda, push gagal dengan slide ID dan block ID.
- Cell text push/pull memakai posisi baris/kolom. Header baris pertama; tanpa merged cell.
- `CreateTableRequest` tersedia sebagai fallback masa depan, tetapi tidak dipakai otomatis di v1.

Sync teks:

- Push menulis nilai lokal ke presentasi.
- Pull membaca nilai remote dan menulis snapshot, bukan langsung menimpa YAML.
- Diff membandingkan snapshot remote dengan YAML.
- Apply menulis perubahan ke file YAML baru setelah validasi.
- Format kaya tidak dijamin round-trip. Remote edit menghasilkan plain text. Bila author mengubah format di Slides, perubahan itu tidak kembali ke YAML.
- Chart data, chart title, dan chart labels tidak ikut pull/diff/apply teks. Chart adalah linked object.
- Image, diagram, dan media tidak ikut pull.
- Notes ikut sync.
- Source ikut sync.
- Chrome tidak ikut sync.

Font:

- Google Slides memakai Google Fonts `Plus Jakarta Sans`.
- Font yang ditanam di PPTX tidak dipakai Google Slides.
- Bila Google Fonts tidak tersedia atau berbeda metrik, build warning harus muncul; live smoke harus memeriksa overflow.
- Tidak ada upload font ke Google Drive untuk v1.

### 8.5 PDF

DOCX ke PDF:

- Word COM di Windows.
- Word membuka salinan DOCX, memperbarui field, mengekspor PDF.
- Word harus menutup dokumen dan proses.
- File input tidak boleh diubah.
- PDF diverifikasi ada dan non-zero.

PPTX ke PDF:

- PowerPoint COM di Windows.
- PowerPoint membuka salinan PPTX native, mengekspor PDF.
- Chart native tetap chart.
- Font embedding dan font terpasang harus konsisten.
- PowerPoint harus menutup presentasi dan proses.

Serialisasi:

- Hanya satu operasi COM Word/PowerPoint pada satu waktu.
- PDF lane memakai lock global.
- Visual test yang juga memakai PowerPoint COM masuk antrean lock yang sama.
- Tidak ada dua worker yang menjalankan COM bersamaan.
- Timeout wajib. Proses yang hang harus dilaporkan dan dibersihkan tanpa merusak output lain.

### 8.6 Mermaid

- `mmdc` adalah external tool. Tidak ada implementasi Mermaid di Python.
- `doctor` memeriksa Node, `mmdc`, dan versi minimum.
- Satu file `.mmd` untuk satu diagram.
- Path relatif, tanpa `..`.
- Theme Mermaid disuntikkan dari token.
- Output berupa PNG resolusi tinggi, bukan SVG native.
- Cache key: hash source + hash theme + versi `mmdc` + flag render + font.
- Cache disimpan di `.autooffice/cache/mermaid/`.
- Hasil Mermaid di PPTX dan Google Slides adalah gambar.
- `alt` dan `caption` wajib/diizinkan sesuai schema.
- Bila `mmdc` gagal, build gagal. Tidak ada fallback teks atau shape manual.
- Tidak ada pemanggilan `mmdc` saat target tidak memakai diagram.

### 8.7 Copy Checker dan Transcript

Copy checker adalah stage deterministik sebelum layout. Input: Deck IR, Transcript IR, dan `copy.yaml`. Output: daftar diagnostic. Tidak ada LLM, tidak ada jaringan.

Tabel rule:

| Rule | Severity default | Cakupan | Perilaku |
| --- | --- | --- | --- |
| `banned_phrases` | error | semua prosa | Frasa literal dari daftar Indonesia/Inggris |
| `title_case` | error | slide title | Title Case per bahasa, tanpa titik akhir, tanpa koma |
| `dash` | error | semua prosa | Menolak U+2014 dan U+2013 |
| `negative_parallelism` | error | semua prosa | Menolak `bukan hanya ... tetapi juga`, `tidak hanya ... tetapi juga`, `bukan hanya ... tapi juga`, `tidak hanya ... tapi juga`, `bukan hanya ... melainkan juga`, `tidak hanya ... melainkan juga` dalam jarak 200 karakter |
| `contrast_pattern` | error | semua prosa | Menolak pola ", bukan " |
| `sentence_length` | warning | semua prosa | Kalimat lebih dari `max_words` (default 25) |
| `forced_triad` | warning | semua prosa | Regex `[^\s,.;:!?][^,.;:!?]*,\s*[^,.;:!?]+,\s*dan\s+[^,.;:!?]+` dalam satu kalimat |
| `one_line_closer` | warning | body/text keys | Untuk grup key body/text dengan minimal 3 item; regex di bawah tabel |
| `paired_clause_label` | warning | teks tampil | Dua fragmen dipisah satu koma, masing-masing tanpa verba dan total maksimal 8 kata |

Regex `one_line_closer`:

```text
^(.*)\.((?:[A-Za-z]+)?\d+)\.(body|text)$
```

Kelompok dengan minimal 3 item; item berindeks tertinggi dianggap closer bila kurang dari 6 kata. Contoh key yang cocok: `s07.points.item3.text`.

`paired_clause_label` mengikuti kontrak deck-studio:

- Tepat satu koma.
- Tidak diakhiri titik, tanda tanya, tanda seru, titik dua, titik koma, atau newline.
- Maksimal 8 kata.
- Setiap fragmen memuat kata minimal 3 huruf.
- Tidak ada verba di kedua fragmen.
- Verba dideteksi dari `KNOWN_VERBS` dan awalan `me`, `men`, `mem`, `meng`, `meny`, `menge`, `di`, `ber`, `ter` yang diikuti minimal dua huruf.

Algoritma `title_case`:

- Tokenisasi per whitespace; strip tanda baca di tepi token sebelum memeriksa huruf.
- Kata pertama dan terakhir selalu kapital.
- Kata fungsi di tengah ditulis lowercase. Daftar `id` memakai `LOWERCASE_WORDS` deck-studio. Daftar `en`: a, an, and, as, at, but, by, for, from, in, nor, of, on, or, per, the, to, via, vs.
- Kata lain ditulis kapital.
- Akronim dan istilah teknis yang sudah seluruhnya kapital dipertahankan.
- Angka diizinkan.
- Tidak boleh ada titik akhir atau koma.
- `title_case` tidak berlaku untuk notes atau transkrip.

Regex dan heuristik final dibekukan di `docs/contracts/copy.md`. `forced_triad`, `one_line_closer`, dan `paired_clause_label` adalah warning; tidak menghentikan build.

`one_line_closer` hanya berlaku untuk grup key block `body`/`text`; notes dan transkrip tidak memakai rule ini.

Aturan bahasa:

- `meta.language` dinormalisasi: lowercase, ambil subtag utama (`id-ID` menjadi `id`, `en-US` menjadi `en`). Nilai di luar `id` dan `en` ditolak dengan error schema; tidak ada fallback diam-diam.
- Teks slide dan notes memakai bahasa utama dari `meta.language`.
- `id`: semua rule.
- `en`: `banned_phrases` versi Inggris, `dash`, `sentence_length`, `negative_parallelism`. `title_case` hanya berlaku untuk slide title berbahasa Inggris, bukan prosa Inggris.
- Transkrip memilih rule pack dari heading `### Indonesia` atau `### English`.

Diagnostic:

- Wajib memuat `rule`, `severity`, `key`, `file`, `line` bila tersedia, `message`, dan `hint`.
- Key slide: `sNN.title`, `sNN.notes`, atau key block.
- Key transkrip: `sNN.transcript.id` atau `sNN.transcript.en`.
- Error menghentikan build sebelum layout. Warning dicetak dan build tetap jalan.
- `autooffice check` menjalankan schema, transcript validation, copy checker, dan coverage plan.
- Tidak ada flag untuk melewati copy checker. Escape hatch hanya `copy.yaml` (severity, disable, allowlist).

Rule yang tidak bisa di-lint (klaim samar, kata stok tanpa bukti, irama) tetap menjadi checklist editorial di `docs/learn/humanizer.md`; tidak masuk gate.

---

## 9. Arsitektur Google Sheets Chart

### 9.1 Prinsip

- Satu spreadsheet per deck.
- Satu tab per chart.
- Satu chart object per tab.
- Spreadsheet dan presentasi dimiliki akun OAuth uploader.
- Mode linked.
- Data satu arah: YAML ke Sheets.
- Tidak ada pull chart.
- Tidak ada edit chart dari Slides ke YAML.

### 9.2 Identitas Chart

- `chart_id` logis: `<slide_id>.<block_id>`, misalnya `s04.chart1`.
- `chart_id` unik per deck.
- `tab_name`: `chart_id` bila aman dan tidak bentrok. Bila lebih dari 100 karakter, potong dan tambah hash 8 karakter.
- Nama spreadsheet: `AutoOffice Charts - <meta.title>`.
- Nama tab stabil. Rename tab tidak boleh mengubah `chart_id`.
- State menyimpan `chart_id`, `tab_name`, `sheet_id`, dan `embedded_chart_id`.

### 9.3 Layout Tab

Untuk chart kategori dan seri:

```text
A1: Category      B1: Seri 1      C1: Seri 2
A2: Q1            B2: 12          C2: 20
A3: Q2            B3: 18          C3: 29
A4: Q3            B4: 27          C4: 41
A5: Q4            B5: 35          C5: 52
```

Untuk donut:

```text
A1: Label         B1: Nilai
A2: Langsung      B2: 42
A3: Referral      B3: 28
```

Aturan:

- Baris 1 adalah header.
- Kolom A adalah kategori.
- Kolom B dan seterusnya adalah seri.
- Tidak ada formula.
- Tidak ada data dua arah.
- Format angka boleh diterapkan dari token.
- Chart object diletakkan di area yang tidak menutupi data, misalnya mulai baris 8.
- Satu tab hanya berisi satu chart.

### 9.4 Chart Object

- `bar`: `COLUMN` atau `BAR` sesuai orientation.
- `line`: `LINE`.
- `donut`: `DOUGHNUT`.
- Warna dari token theme.
- Font chart `Plus Jakarta Sans`.
- Legend dan title mengikuti spec YAML.
- `embedded_chart_id` disimpan di state.
- Bila spec berubah, gunakan update chart spec agar `embedded_chart_id` tetap dan link Slides tidak putus.
- Bila tab atau chart hilang, buat ulang dan tandai link lama rusak. Jangan menebak.

### 9.5 Sinkronisasi ke Slides

- Staging PPTX berisi placeholder di posisi chart.
- Setelah upload, cari placeholder berdasarkan alt title dan nama shape.
- Preflight semua placeholder sebelum menghapus satu pun.
- Hapus placeholder dengan `deleteObject`.
- Buat linked chart dengan `createSheetsChart`, `spreadsheetId`, `chartId`, `linkingMode: LINKED`.
- Posisi dan ukuran diambil dari placeholder.
- Bila sudah ada linked chart untuk `chart_id`, jangan membuat duplikat. Verifikasi link dan update data saja.
- Bila ada linked chart dengan `chart_id` lain di posisi yang sama, gagal.
- Bila placeholder tidak ditemukan atau ganda, gagal.
- Bila replacement gagal di tengah, state harus mencatat progress dan rerun harus idempoten.

### 9.6 State

Lokasi usulan: `.autooffice/state/<deck-stem>.json` di samping YAML.

```json
{
  "schema": "autooffice.state/v1",
  "deck_path": "deck.yaml",
  "deck_sha256": "...",
  "presentation_id": "...",
  "presentation_url": "...",
  "spreadsheet_id": "...",
  "spreadsheet_url": "...",
  "last_pulled_revision_id": "...",
  "last_pushed_at": "2026-11-14T00:00:00Z",
  "charts": {
    "s04.chart1": {
      "tab_name": "s04.chart1",
      "sheet_id": 123,
      "embedded_chart_id": 456,
      "last_data_sha256": "..."
    }
  }
}
```

Aturan:

- State bukan source of truth konten.
- State tidak boleh menyimpan token OAuth.
- State boleh dihapus; push berikutnya membuat ulang spreadsheet dan presentasi.
- State ditulis atomik.
- State diperiksa terhadap `deck_sha256`; perbedaan bukan error, hanya memicu perencanaan sync.
- State tidak boleh masuk Git.

### 9.7 Ownership dan OAuth

- OAuth user flow, bukan service account.
- File dimiliki akun yang memberi consent.
- Scope usulan:
  - `https://www.googleapis.com/auth/drive.file`
  - `https://www.googleapis.com/auth/presentations`
  - `https://www.googleapis.com/auth/spreadsheets`
- Client secret tidak boleh ada di repo.
- Token cache disimpan di direktori user, bukan repo.
- Bila akun berganti dan state menunjuk file yang tidak bisa diakses, error harus jelas: minta login akun yang sama atau reset state.
- Scopes harus diuji dengan akun bersih sebelum acceptance.

### 9.8 Kegagalan

- Spreadsheet gagal dibuat: tidak ada presentation upload.
- Tab gagal dibuat: state tidak mencatat chart.
- Data gagal ditulis: chart tidak boleh di-link.
- Chart object gagal dibuat: tidak ada replacement.
- Placeholder tidak lengkap: tidak ada penghapusan.
- Table preflight gagal: tidak ada placeholder dihapus, tidak ada linked chart dibuat, dan state tidak ditulis.
- Slides replacement gagal: state mencatat chart yang sudah siap; rerun melanjutkan.
- Kuota API: retry terbatas dengan backoff, lalu gagal.
- Jangan menghapus spreadsheet atau presentasi user secara otomatis.
- Jangan membuat spreadsheet kedua bila state masih valid.
- Bila spreadsheet dihapus user, buat ulang dan tandai presentasi lama tidak sinkron.

---

## 10. CLI

### 10.1 Permukaan Perintah

```text
autooffice build <input> --target <targets> [opsi]
autooffice check <input> [opsi]
autooffice doctor [opsi]
autooffice --version
autooffice --help
```

Tidak ada perintah `docgen` atau `deck-studio`. Tidak ada alias.

### 10.2 Matriks Target

| Input | `docx` | `pdf` | `pptx` | `slides` | `all` |
| --- | --- | --- | --- | --- | --- |
| `.md` | ya | ya, lewat DOCX | tidak | tidak | DOCX + PDF |
| `.yaml` | tidak | ya, lewat PPTX | ya | ya | PPTX + PDF + Slides |

Aturan:

- Target dipisahkan koma, boleh ada spasi setelah koma.
- Duplikat dihapus, urutan kanonik dipertahankan.
- `all` tidak boleh digabung dengan target lain.
- `pdf` untuk `.md` membangun DOCX terlebih dahulu.
- `pdf` untuk `.yaml` membangun PPTX terlebih dahulu.
- `slides` hanya untuk `.yaml` dan memerlukan extra `google` serta kredensial.
- `all` untuk `.yaml` memerlukan Google; `all` bukan mode offline.
- `pptx,pdf` adalah cara offline menghasilkan PPTX dan PDF.
- Input selain `.md` dan `.yaml` ditolak.
- `--target` wajib untuk `build`.

### 10.3 Flag

| Flag | Berlaku | Aturan |
| --- | --- | --- |
| `--out DIR` | semua | Direktori output. Dibuat bila belum ada. Tidak boleh menunjuk file. |
| `--theme NAME` | `.yaml` | `indigo` atau `hitam`. Menimpa `theme.name`. Error untuk `.md`. |
| `--terms` | `.md` | Menulis daftar istilah baru seperti docgen. Error untuk `.yaml`. |
| `--dry-run` | semua | Validasi penuh, rencanakan output dan aksi remote, tidak menulis file final, tidak memanggil COM, tidak menulis ke Google. |
| `--keep-intermediate` | semua | Menyimpan intermediate DOCX/PPTX/staging/Mermaid di lokasi yang didokumentasikan. |
| `--sync MODE` | `.yaml` + `slides` | `push` (default), `pull`, `diff`, `apply`. |
| `--version` | global | Menampilkan versi package. |
| `--help` | global | Menampilkan bantuan. |

`--sync` adalah usulan perluasan untuk memenuhi kontrak push/pull/diff/apply tanpa menambah perintah build kedua. Alternatif `autooffice slides ...` tidak dipakai dalam plan ini. Asumsi A3.

### 10.4 Output Naming

Input `.md`:

- Output default mengikuti perilaku `docgen`.
- Nama file dari `report_name` di front matter: `<report_name>.docx` dan `<report_name>.pdf`.
- Manifest: `.laporan/manifest.json`.
- Istilah: `.laporan/istilah-baru.txt`.
- Intermediate: `.laporan-build/`.
- Untuk `examples/<name>/document.md`, output default ke `examples/<name>/out/` seperti docgen.
- `--out DIR` menimpa direktori output. Lokasi manifest dan intermediate mengikuti aturan yang sama dengan docgen.

Input `.yaml`:

- Output default di samping YAML, kecuali input berada di `examples/<name>/`, yang memakai `examples/<name>/out/`.
- `<stem>.pptx`
- `<stem>.transcript.md` bila `transcripts.md` ada.
- `<stem>.pdf`
- Staging Slides internal: `<stem>.slides-upload.pptx`, tidak menjadi deliverable.
- State: `.autooffice/state/<stem>.json` di samping YAML.
- Cache: `.autooffice/cache/` di samping YAML.
- Intermediate: `.autooffice-build/<stem>/` di samping YAML atau di `--out` bila `--out` diberikan.
- Laporan sync: `.autooffice/review/`.
- `--out DIR` mengubah direktori artefak final, bukan state identity.

Contoh nama presentasi Google Slides: `meta.title`. Contoh nama spreadsheet: `AutoOffice Charts - <meta.title>`.

### 10.5 `--dry-run`

`--dry-run` HARUS:

- memvalidasi YAML/Markdown dan aset;
- menjalankan copy checker dan transcript validation;
- menjalankan compiler, layout measurement, dan coverage plan;
- mencetak daftar file yang akan ditulis;
- mencetak target yang akan dijalankan;
- mencetak aksi Google yang direncanakan;
- mencetak diff untuk `--sync push` atau `--sync diff`;
- tidak menulis file output;
- tidak menulis state;
- tidak memanggil Word/PowerPoint COM;
- tidak menjalankan `mmdc` untuk output final;
- tidak menulis ke Drive, Sheets, atau Slides.

Bila `--dry-run` menemukan overflow, key hilang, atau kredensial Google tidak ada saat target Slides, exit code harus nonzero.

### 10.6 `--keep-intermediate`

- Menyimpan DOCX intermediate saat target PDF dari `.md`.
- Menyimpan PPTX intermediate saat target PDF dari `.yaml`.
- Menyimpan staging PPTX saat target Slides.
- Menyimpan hasil Mermaid dan konfigurasi sementara.
- Tidak menyimpan token OAuth.
- Tidak mengubah output final.
- Untuk `.md`, memetakan perilaku `--keep` docgen.
- Untuk `.yaml`, intermediate berada di `.autooffice-build/<stem>/` dan diabaikan Git.

### 10.7 `--sync`

- `push`: build penuh untuk Slides, siapkan spreadsheet, upload, ganti chart, push teks. Ini default.
- `pull`: membaca remote, menulis snapshot YAML ke `.autooffice/review/<stem>.pulled.yaml` dan report. Tidak mengubah YAML sumber.
- `diff`: membaca remote dan membandingkan dengan YAML. Menulis `.autooffice/review/<stem>.diff.json` dan mencetak ringkasan.
- `apply`: menerapkan perubahan remote ke YAML baru `.autooffice/review/<stem>.applied.yaml`, bukan menimpa sumber. Perubahan harus lolos schema dan coverage sebelum ditulis.
- `--dry-run` dengan `push` sama dengan `diff`.
- `--sync` hanya valid bila target berisi `slides`.
- `pull`, `diff`, dan `apply` memerlukan state dengan `presentation_id`.
- `apply` tidak boleh membuat key baru di luar key yang sudah ada, kecuali key tersebut berasal dari slide/block yang ditambahkan di YAML setelah pull. Konflik harus dilaporkan.

### 10.8 `check`

`autooffice check <input> [--target ...] [--theme ...]`

- Untuk `.md`: validasi front matter, format, struktur, aset, caption, dan urutan heading. Tidak memanggil Pandoc atau Word.
- Untuk `.yaml`: validasi schema, aset, key, layout slot, measurement, overflow, chart spec, placeholder plan, transcript validation, copy checker, dan coverage plan.
- `--target` opsional. Bila tidak ada, semua target yang valid untuk input diperiksa.
- Tidak menulis output final.
- Tidak memanggil COM.
- Tidak memanggil Google.
- Exit 0 bila bersih, 1 bila ada temuan.

### 10.9 `doctor`

`autooffice doctor [--target ...]`

Memeriksa:

- Python 3.15.
- Package `autooffice` importable.
- Font TTF dan lisensi.
- Izin tulis workspace.
- Pandoc dan `--citeproc`.
- Node dan `mmdc`.
- Word COM.
- PowerPoint COM.
- Extra `google` dan kredensial OAuth.
- Akses ke Google Fonts tidak diperiksa secara network kecuali `--target slides` dengan mode live.

Aturan:

- `doctor` tidak mengubah file.
- Exit 1 bila dependency wajib untuk target yang diminta tidak tersedia.
- Default tanpa `--target` memeriksa dependency inti dan memberi status per fitur.
- Pesan harus memberi tindakan: install, login, atau jalankan target lain.

### 10.10 Exit Code dan Error

| Kode | Arti |
| --- | --- |
| 0 | Sukses. `diff` dengan perbedaan tetap 0 karena operasi diff berhasil. |
| 1 | Validasi, build, coverage, dependency, COM, atau Google gagal. |
| 2 | Argumen CLI salah, target tidak valid, atau kombinasi flag salah. |

Aturan error:

- Error validasi menyebut input, slide, block, key, dan field.
- Error aset menyebut path relatif dan path absolut hasil resolusi.
- Error Google menyebut operasi, file, dan langkah yang gagal.
- Error COM menyebut aplikasi, file, dan target.
- Tidak ada traceback panjang kecuali environment debug eksplisit.
- Tidak ada fallback diam-diam.
- Output yang sudah selesai tidak dihapus saat target lain gagal, tetapi exit code nonzero dan ringkasan diberikan.
- File final ditulis atomik.

### 10.11 Contoh Perintah

```bash
# DOCX dari Markdown
autooffice build examples/docx/assignment-single/document.md --target docx

# DOCX dan PDF dari Markdown
autooffice build examples/docx/thesis-single/document.md --target docx,pdf

# Deck PPTX dan PDF tanpa Google
autooffice build examples/demo-deck/deck.yaml --target pptx,pdf

# Deck lengkap, termasuk Google Slides
autooffice build examples/demo-deck/deck.yaml --target all

# Theme hitam
autooffice build examples/demo-deck/deck.yaml --target pptx --theme hitam

# Dry run seluruh target
autooffice build examples/demo-deck/deck.yaml --target all --dry-run

# Cek sebelum build
autooffice check examples/demo-deck/deck.yaml

# Istilah untuk dokumen
autooffice build document.md --target docx --terms

# Simpan intermediate PDF
autooffice build deck.yaml --target pdf --keep-intermediate

# Sinkronisasi teks
autooffice build deck.yaml --target slides --sync diff
autooffice build deck.yaml --target slides --sync pull
autooffice build deck.yaml --target slides --sync apply

# Diagnostik
autooffice doctor --target all
```

---

## 11. Design System

### 11.1 Sumber Token

Design token diporting dari deck-studio ke `autooffice.design.data`. Token adalah data package, bukan file kerja pengguna.

Kategori token minimal:

- Warna: background, surface, ink, muted, border, accent, status, chart.
- Tipografi: family, weight, size px dan pt, line-height, tracking.
- Slide: width/height, margin, top, bottom, side.
- Grid: columns 12, gutter, row gap.
- Spacing: `sm`, `md`, `lg`, padding card.
- Radius.
- Shadow.
- Chart: `chartSeries`, grid, axis, legend, title.
- Code: font mono, size, line-height.

Semua renderer membaca token yang sudah di-resolve. Tidak ada hardcode hex, ukuran, atau margin di renderer.

### 11.2 Theme

Theme v1:

Palet `indigo` dan `hitam` diambil dari `design-system/themes.json` deck-studio, lalu digabung dengan neutrals `design-system/tokens.json`. `hitam` menimpa aksen, cover, dan token chart; background tetap terang. `themes.json` adalah sumber otoritatif. `dist/themes/hitam.html` adalah artefak preview dan harus di-regenerasi sebelum verifikasi; artefak lama masih memuat palet kategorikal default dan tidak boleh dipakai sebagai bukti warna. Bentuk, sumber, dan aturan token dibekukan di Fase 0; nilai final dibekukan setelah audit kontras di F1-DESIGN.

| Theme | Mode | Status | Catatan |
| --- | --- | --- | --- |
| `indigo` | light | default | Palet indigo deck-studio. |
| `hitam` | light | opsi | Palet `hitam` deck-studio: kanvas terang, aksen `#111827`, cover gradient `#111827` → `#0B1220` → `#000000`. Warna chart memakai `chartSeries` turunan yang lolos 3:1. Bukan dark theme. |

Palet kategorikal mentah `hitam` dari `themes.json` adalah `#111827`, `#4B5563`, `#9CA3AF`, `#D1D5DB`. Dua warna terakhir tidak memenuhi kontras 3:1 terhadap background terang. AutoOffice karena itu memakai token turunan `chartSeries` dengan empat warna yang lolos 3:1: `hitam` `#111827`, `#374151`, `#4B5563`, `#6B7280`; `indigo` `#4F46E5`, `#0F766E`, `#B45309`, `#BE123C`. Palet aksen dan cover tetap persis `themes.json`; hanya warna chart yang disesuaikan untuk aksesibilitas.

Aturan:

- Hanya dua theme.
- `hitam` adalah theme terang dengan aksen hitam. Dark mode tidak termasuk v1; palet `malam` tidak dipakai.
- Nilai awal diambil dari token deck-studio. Nilai final dibekukan setelah audit kontras.
- Theme mengubah warna, bukan geometri layout, font family, atau ukuran.
- Theme tidak menambah zona aksen.
- Warna chart kategorikal harus punya kontras minimal 3:1 terhadap background chart.
- Palet `chartSeries` berisi empat warna di kedua theme. Karena itu chart dibatasi empat slot warna (seri untuk `bar`/`line`, kategori untuk `donut`) di semua theme.
- Teks normal minimal 4.5:1.
- Teks besar minimal 3:1.
- Status tidak boleh menjadi satu-satunya pembeda; selalu ada label.

### 11.3 Tipografi

- Family: `Plus Jakarta Sans`.
- Weight: 400, 600, 700, 800.
- Ukuran mengikuti token deck-studio dalam pt untuk PPTX.
- Judul 40 px / 30 pt.
- Body 22 px / 16.5 pt.
- Minimal teks 10 pt.
- Mono: system mono stack untuk code.
- Tidak ada font family lain di deck.
- Google Slides memakai family name `Plus Jakarta Sans`.
- DOCX mempertahankan font format docgen dan tidak memakai Plus Jakarta Sans.

### 11.4 Font Bundling dan Embedding

- TTF Plus Jakarta Sans disimpan di `src/autooffice/assets/fonts/plus-jakarta-sans/`.
- Lisensi SIL Open Font License 1.1 disertakan.
- TTF yang sama dipakai test dan visual test.
- PPTX embed font lewat post-processing OOXML.
- Google Slides mengandalkan Google Fonts, bukan file TTF.
- Bila Google Slides tidak dapat memakai family yang sama, build warning dan live smoke wajib.
- Font WOFF2 tidak cukup untuk PPTX. TTF adalah format utama.
- Font weight yang tidak dipakai tidak perlu ditanam, tetapi set minimal harus lengkap agar bold tidak jatuh ke fallback. Italic tidak dipakai di v1.

### 11.5 Larangan Desain

- Tidak ada gradient dekoratif selain cover yang ditentukan token.
- Tidak ada glow, glass, blur dekoratif, blob 3D, atau pola acak.
- Tidak ada aksen pada body, caption, footer, atau nomor halaman.
- Tidak ada warna hex di YAML.
- Tidak ada ukuran font di YAML.
- Tidak ada layout yang membuat zona aksen baru.
- Tidak ada font di luar design system.

### 11.6 Kontras dan Aksesibilitas

- Test kontras otomatis untuk setiap theme.
- Alt text wajib untuk image, diagram, chart.
- Notes tidak menggantikan alt.
- Teks tidak boleh disampaikan hanya lewat warna.
- Chart harus punya label kategori yang jelas.
- Table header harus semantik.
- Reading order shape harus masuk akal.
- Page number dan chrome tidak mengganggu screen reader.

---

## 12. Testing dan Quality

### 12.1 Prinsip

- Test adalah kontrak yang dapat dieksekusi.
- Test tidak boleh bergantung pada network.
- COM dan Google memakai fake di unit/contract test.
- Final gate menjalankan smoke test nyata di Windows.
- Golden test harus deterministik.
- Tidak ada `assert True`, test kosong, atau test yang hanya memanggil fungsi tanpa asersi perilaku.
- Tidak ada `time.sleep` untuk menunggu; gunakan fake clock.
- Tidak ada test yang menulis ke path repo selain `tmp_path`.
- Tidak ada pengecualian coverage tanpa alasan tertulis.

### 12.2 Jenis Test

| Jenis | Tujuan | Network/Office | Contoh |
| --- | --- | --- | --- |
| Unit | Logika murni | tidak | key grammar, grid math, parser Markdown |
| Contract | Kontrak schema, layout, block, renderer | tidak | slot layout, coverage, alt text |
| Golden | Perubahan output terdeteksi | tidak | XML PPTX ternormalisasi, DOCX parts |
| Visual | Kesetiaan tampilan | PowerPoint COM | PNG per layout dan theme |
| Integration | Alur lokal antar-modul | tidak | YAML ke PPTX, DOCX ke PDF fake |
| Smoke | Dependency nyata | ya | Word/PowerPoint/Google live |
| Test-quality | Kualitas test | tidak | AST checker |
| Copy | Aturan naskah deterministik | tidak | banned phrase, Title Case, transcript mapping |

### 12.3 Coverage 100%

Definisi:

- Coverage dihitung untuk `src/autooffice` saja, bukan test.
- Line coverage dan branch coverage harus 100%.
- Threshold `--cov-fail-under=100`.
- Report HTML dan terminal dihasilkan.
- Tidak ada `omit` global untuk modul bisnis.
- Tidak ada `# pragma: no cover` tanpa alasan.
- Pengecualian default hanya:
  - blok `if TYPE_CHECKING:`;
  - deklarasi `@overload`;
  - baris yang tidak dapat dieksekusi oleh Python karena deklarasi tipe.
- Pengecualian tambahan harus didaftarkan di `docs/contracts/coverage.md` dengan file, baris/fungsi, alasan, dan approver.
- COM dan Google wrapper diuji dengan fake. Final smoke menjalankan jalur nyata. Bila jalur nyata tidak tercakup unit test, harus ada integration test yang dijalankan di final gate.
- Jangan mengecualikan seluruh file `cli/main.py`, `google/*`, atau `pdf/*`.
- Jangan memakai `coverage` combine untuk menutupi modul yang tidak pernah dijalankan.

### 12.4 Mypy Ketat

Baseline docgen saat ini non-strict. AutoOffice harus lebih ketat.

Target awal:

```toml
[tool.mypy]
python_version = "3.15"
strict = true
warn_unreachable = true
warn_unused_ignores = true
warn_redundant_casts = true
no_implicit_reexport = true
disallow_untyped_decorators = true
disallow_incomplete_defs = true
check_untyped_defs = true
```

Aturan:

- Public function harus punya annotation.
- `Any` tidak boleh bocor ke public API.
- Third-party yang tidak punya stub dibungkus adapter tipis.
- `ignore_missing_imports` hanya untuk modul third-party, bukan untuk modul internal.
- Tidak ada `# type: ignore` tanpa kode error.
- Mypy harus lulus untuk `src/autooffice` dan, bila feasible, `tools/quality`.
- Konfigurasi final dibekukan di Fase 0 setelah audit stub `python-pptx`, `googleapiclient`, dan `pywin32`.

### 12.5 Import Contracts

Kontrak import minimal:

- `design` tidak boleh mengimpor domain deck, docx, google, pdf, atau cli.
- `common` tidak boleh mengimpor domain tinggi.
- `deck.model` tidak boleh mengimpor renderer, google, docx, atau cli.
- `deck.layout` boleh mengimpor `deck.model` dan `design`, tidak boleh mengimpor renderer atau google.
- `deck.render.pptx` boleh mengimpor `deck.model`, `deck.layout`, `deck.charts`, dan `design`, tidak boleh mengimpor google atau docx.
- `deck.charts` tidak boleh mengimpor google.
- `google` boleh mengimpor `deck.model`, `design`, dan kontrak chart, tidak boleh mengimpor renderer PPTX.
- `docx` tidak boleh mengimpor deck, google, atau cli.
- `pdf` tidak boleh mengimpor google atau renderer internal selain kontrak file.
- `cli` boleh mengimpor semua, tetapi tidak ada modul domain yang mengimpor `cli`.

Import-linter harus menegakkan kontrak ini di gate.

### 12.6 Golden Test

DOCX:

- Bandingkan part DOCX yang relevan setelah normalisasi timestamp dan metadata.
- Fixture baseline dibuat dari docgen sebelum penghapusan.
- Perbedaan part non-target harus nol.

PPTX:

- Buka ZIP, normalisasi timestamp, relationship ID yang tidak stabil, dan whitespace XML.
- Periksa slide count, shape name, alt key, table cell, chart XML, notes, font embedding, dan geometry.
- Jangan membandingkan binary penuh tanpa normalisasi.
- Golden update hanya dengan flag eksplisit dan review integration owner.

Layout:

- Satu golden semantic per preset.
- Satu golden semantic untuk custom.
- Satu golden visual per layout untuk indigo.
- Full deck hitam untuk acceptance.
- Golden tidak boleh menyembunyikan overflow.

### 12.7 Visual Test

- Render PPTX ke PNG melalui PowerPoint COM.
- Bandingkan dengan golden PNG.
- Threshold pixel dan mask area harus eksplisit.
- Perbedaan font atau versi PowerPoint harus dilaporkan, bukan diabaikan.
- Visual test memakai lock COM yang sama dengan PDF.
- Visual test dijalankan di Windows dengan font terpasang dan Office versi yang didukung.
- Bila environment tidak memenuhi, test gagal, bukan skip diam-diam.

### 12.8 Google Fake

Fake Google harus meniru:

- Drive create/upload.
- Slides presentation get dan batchUpdate.
- Sheets create, addSheet, values update, addChart/updateChartSpec.
- `createSheetsChart`.
- Native table page elements: `table`, `image`, dan shape group.
- Trace `CreateTableRequest` untuk memastikan push normal tidak memanggilnya.
- Error 401, 403, 404, 429, 500.
- Revision ID.
- File ownership.

Fake disimpan di `src/autooffice/google/fake.py` atau `tests/fixtures/google/`, dengan kontrak yang jelas. Test tidak memakai network.

Live smoke:

- Satu akun uji.
- Satu deck kecil.
- Push, pull, diff, apply.
- Verifikasi spreadsheet, tab, linked chart, font, overflow.
- Tidak dijalankan paralel.
- Hasil dicatat di acceptance report.

### 12.9 Docs Checker

Docs checker memeriksa:

- `docs/README.md` ada dan menjadi indeks.
- Semua halaman di `docs/user`, `docs/dev`, `docs/learn`, `docs/contracts`, `docs/decisions` terdaftar.
- Link internal valid.
- Tidak ada link ke `docgen` atau `deck-studio` di docs user.
- Setiap halaman punya judul level 1.
- Setiap code fence punya language.
- Perintah `autooffice` yang didokumentasikan ada di CLI.
- Tidak ada tutorial per fitur.
- Kontrak di `docs/contracts` tidak diduplikasi di docs lain.
- Halaman yang usang ditandai atau dihapus.

### 12.10 Test-Quality Checker

Memeriksa:

- Tidak ada test tanpa assertion.
- Tidak ada `assert True` atau `assert 1 == 1`.
- Tidak ada `pytest.mark.skip` tanpa alasan dan batas waktu.
- Tidak ada `time.sleep`.
- Tidak ada akses network langsung.
- Tidak ada penulisan ke luar `tmp_path`.
- Tidak ada fixture yang mengubah state global tanpa cleanup.
- Tidak ada test yang bergantung pada urutan eksekusi.
- Nama test menjelaskan perilaku.
- Fixture besar punya alasan dan tidak menggantikan assertion semantik.

### 12.11 Gate Lokal

Tidak ada GitHub Actions. Gate dijalankan lokal:

```bash
uv sync --extra dev --extra google
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest --cov=autooffice --cov-branch --cov-fail-under=100
uv run python tools/quality/check_docs.py
uv run python tools/quality/check_tests.py
uv run python tools/quality/check_no_legacy.py
```

Final gate juga menjalankan:

```bash
uv build
uv run autooffice doctor --target all
uv run autooffice check examples/demo-deck/deck.yaml
uv run autooffice build examples/demo-deck/deck.yaml --target all --out <tmp>
uv run autooffice build examples/docx/thesis-single/document.md --target docx,pdf --out <tmp>
```

Aturan:

- Gate final harus lulus dari clean clone.
- Gate final harus dijalankan pada Windows dengan Word dan PowerPoint.
- Smoke Google live adalah gate manual yang wajib sebelum tanda tangan final.
- Tidak ada merge yang mengandalkan CI.

### 12.12 Quality Non-Goals

- Tidak mengejar 100% mutation testing.
- Tidak menambah performance benchmark sebelum ada masalah nyata.
- Tidak menambah property-based testing di luar schema/key parser kecuali dibutuhkan.
- Tidak menambah test yang hanya menguji mock.
- Tidak menambah CI.

### 12.13 Copy dan Transcript

- Unit test per rule: positif, negatif, dan batas.
- Config merge: default, override severity, disable rule, allowlist dengan alasan.
- Config merge: blok `targets` yang tidak ditulis memakai default `slides/notes/transcript: true`.
- `extra.id` tidak diperiksa pada teks Inggris; `extra.en` tidak diperiksa pada teks Indonesia.
- Normalisasi bahasa: `id-ID` menjadi `id`, `en-US` menjadi `en`, dan bahasa lain ditolak.
- Title Case `id` dan `en` memakai daftar kata fungsi masing-masing.
- `forced_triad` dan `one_line_closer` punya fixture batas sesuai regex/heuristik kontrak.
- `one_line_closer` memakai key valid seperti `s07.points.item3.text`; regex tidak salah membaca `item3` sebagai angka tanpa awalan.
- `paired_clause_label` menguji tepat satu koma, terminal punctuation, batas 8 kata, kata kurang dari 3 huruf, dan deteksi verba.
- `targets.transcript: true` tanpa `transcripts.md` tidak menghasilkan error.
- Transcript parser: heading ID, duplicate, missing slide, unknown slide, urutan bebas, section bahasa.
- Diagnostic memuat key, file, line, rule, severity.
- Bilingual: `id` dan `en` memakai rule pack masing-masing.
- Integration: `build` gagal pada error; warning tidak menggagalkan build.
- `check` menjalankan copy checker tanpa network, LLM, atau Office.
- Golden diagnostic untuk demo deck.
- Tidak ada test yang memanggil layanan jaringan.

---

## 13. Rencana Eksekusi Paralel

### 13.1 Aturan Umum

- Contracts before code. Fase 0 adalah hard barrier.
- No two owners on one file.
- No merge without verification.
- File-disjoint parallel lanes.
- Rolling pipeline, bukan batch barrier.
- Satu lane tidak menunggu sibling yang tidak relevan.
- Lane yang selesai diverifikasi dan di-merge akan membuka dependent.
- Shared file hanya integration owner.
- Setiap lane memiliki acceptance test yang tertulis.
- Setiap merge menjalankan ulang test yang terdampak.
- Golden update dan COM adalah resource eksklusif.

### 13.2 Fase 0: Contract Freeze dan Scaffold (Hard Barrier)

#### F0-CONTRACTS

- **Owner:** integration owner.
- **Files/glob:** `docs/contracts/**`, `docs/decisions/**`, `pyproject.toml`, `uv.lock`, `src/autooffice/__init__.py`, `src/autooffice/__main__.py`, `src/autooffice/cli/main.py`, `src/autooffice/errors.py`, `src/autooffice/deck/layout/registry.py`, `src/autooffice/deck/blocks/registry.py`, `src/autooffice/deck/model/deck_ir.py`, `src/autooffice/deck/blocks/spec.py`, `src/autooffice/deck/layout/spec.py`, `src/autooffice/design/theme.py`, `src/autooffice/deck/render/protocol.py`, `src/autooffice/**/__init__.py`, `tools/quality/**`, `tests/contract/**`, `docs/README.md`, `docs/learn/README.md`, `AGENTS.md`, `AUTO_OFFICE_EXECUTION_LOG.md`, `.gitignore`.
- **Dependencies:** tidak ada, tetapi wajib menunggu penutupan Bagian 19 melalui ADR 0001.
- **Deliverables:**
  - Kontrak schema deck.
  - Kontrak key grammar dan KeyBinding.
  - Kontrak Deck IR.
  - Kontrak LayoutSpec, SlotSpec, BlockSpec.
  - Kontrak renderer PPTX.
  - Kontrak placeholder chart dan linked chart.
  - Kontrak state Google.
  - Kontrak CLI, target, output, exit code.
  - Kontrak DOCX API dan parity.
  - Kontrak design token.
  - Kontrak coverage dan exclusion.
  - Kontrak test-quality dan docs.
  - ADR untuk keputusan terkunci L01-L25.
  - Scaffold package minimal yang bisa di-import dan `autooffice --help`.
  - Registry discovery skeleton untuk layout dan block, dimiliki integration owner.
  - Kontrak file ownership dan lane map.
  - Bentuk Python kontrak (DeckIR, BlockSpec, LayoutSpec, Theme, RenderRequest/Result) dibekukan di F0 dan diserahkan ke owner domain di F1/F2.
- **Acceptance tests:**
  - `uv run autooffice --help` berhasil.
  - `uv run python -c "import autooffice"` berhasil.
  - Semua kontrak punya versi dan contoh.
  - Import-linter config ada.
  - `check_no_legacy` belum diwajibkan, tetapi daftar target no-legacy ada.
  - Semua asumsi A1-A25 di Bagian 19 sudah dijawab atau ditutup.
- **Hard barrier:**
  - Tidak ada lane fitur yang boleh menulis kode produksi sebelum F0 lulus.
  - Tidak ada perubahan schema setelah F0 tanpa ADR.
  - Tidak ada merge ke integration branch sebelum kontrak direview integration owner.

### 13.3 Fase 1: Foundation Lanes

#### F1-DOCX

- **Owner:** DOCX migration owner.
- **Files/glob:** `src/autooffice/docx/**`, `tests/docx/**`, `tests/fixtures/docx/**`, `examples/docx/**`, `docs/contracts/docx.md`, `docs/dev/docx.md`.
- **Dependencies:** F0.
- **Deliverables:**
  - Seluruh pipeline docgen diporting.
  - API `build_docx(input, out, terms, keep_intermediate)`.
  - API finalisasi Word dan PDF.
  - Manifest dan istilah.
  - Package data format/structure.
  - Golden baseline.
- **Acceptance tests:**
  - Seluruh test docgen yang relevan lulus di namespace baru.
  - DOCX fixture lama dan baru setara setelah normalisasi.
  - `report_name` output benar.
  - `--terms` menghasilkan file yang sama.
  - Tidak ada import `autooffice.deck` atau `autooffice.google`.
- **Hard barrier:** jangan hapus `docgen` sebelum parity diterima.

#### F1-MODEL

- **Owner:** model/compiler owner.
- **Files/glob:** `src/autooffice/deck/model/**`, `src/autooffice/deck/blocks/**` kecuali `registry.py`, `tests/deck/model/**`, `tests/fixtures/deck/**`, `docs/contracts/deck-schema.md`, `docs/contracts/key-grammar.md`.
- **Dependencies:** F0.
- **Deliverables:**
  - Loader YAML strict.
  - Schema validation.
  - Inline Markdown parser.
  - Deck IR.
  - Key registry, KeyManifest, KeyBinding.
  - Compiler.
  - Coverage plan.
  - Contoh parse untuk semua block type.
- **Acceptance tests:**
  - Semua field unknown ditolak.
  - Duplicate slide ID, block ID, dan key ditolak.
  - Reorder slide/block tidak mengubah key.
  - `bar`/`line` menerima 1-4 seri dan menolak 5 seri; `donut` menerima tepat satu seri dengan 2-4 kategori berwarna dan menolak 5 kategori.
  - Mapping key sesuai Bagian 5.
  - Inline Markdown valid dan invalid.
  - Path traversal ditolak.
  - `yaml_path` dapat dipakai untuk apply.
- **Hard barrier:** renderer tidak boleh mulai sebelum Deck IR dan key manifest stabil.

#### F1-COPY

- **Owner:** copy/humanizer owner.
- **Files/glob:** `src/autooffice/deck/copy/**`, `src/autooffice/deck/transcript/**`, `tests/deck/copy/**`, `tests/fixtures/copy/**`, `docs/contracts/copy.md`, `docs/contracts/transcript.md`, `docs/learn/humanizer.md`.
- **Dependencies:** F0, F1-MODEL.
- **Deliverables:**
  - `copy.yaml` schema dan merge default.
  - Rule deterministik untuk Indonesia dan Inggris.
  - Transcript parser dan model.
  - Diagnostic.
  - API checker untuk CLI.
- **Acceptance tests:**
  - Semua rule punya test positif dan negatif.
  - Config merge, disable, dan allowlist.
  - Transcript mapping berdasarkan slide ID.
  - Error vs warning.
  - Tidak ada network atau LLM.
- **Hard barrier:** CLI wiring dimiliki integration owner; lane ini tidak mengedit `src/autooffice/cli/**`.

#### F1-LAYOUT

- **Owner:** layout engine owner.
- **Files/glob:** `src/autooffice/deck/layout/grid.py`, `src/autooffice/deck/layout/measure.py`, `src/autooffice/deck/layout/slot.py`, `src/autooffice/deck/layout/overflow.py`, `src/autooffice/deck/layout/presets/__init__.py`, `tests/deck/layout/test_grid.py`, `tests/deck/layout/test_measure.py`, `tests/deck/layout/test_slots.py`, `docs/contracts/layout-spec.md`.
- **Dependencies:** F0, F1-MODEL, F1-DESIGN.
- **Deliverables:**
  - 12-column geometry.
  - Row engine primitive.
  - Slot contract.
  - Text measurement.
  - Overflow fail/flag.
  - Layout plan serialization.
  - Konsumsi kontrak registry discovery milik integration owner.
- **Acceptance tests:**
  - Rumus span.
  - Row sum >12 ditolak.
  - Span 0/13 ditolak.
  - Absolute fields ditolak.
  - Overflow terdeteksi.
  - Row engine menghasilkan posisi deterministik.
  - Preset slot validation.
- **Hard barrier:** preset lane tidak boleh menambah layout tanpa kontrak slot dan tanpa registry discovery dari integration owner. Layout `custom` penuh dimiliki F2-CUSTOM-GRID, bukan lane ini.

#### F1-PPTX

- **Owner:** PPTX primitives owner.
- **Files/glob:** `src/autooffice/deck/render/pptx/shapes.py`, `textbox.py`, `table.py`, `image.py`, `notes.py`, `coverage.py`, `fonts.py`, `theme.py`, `xml.py`, `renderer.py`, `tests/deck/render/pptx/**`, `docs/contracts/pptx-renderer.md`.
- **Dependencies:** F0, F1-MODEL, F1-LAYOUT, F1-DESIGN.
- **Deliverables:**
  - Slide canvas.
  - Textbox tanpa autofit.
  - Table native.
  - Image native.
  - Notes.
  - Alt/key metadata.
  - Coverage extractor.
  - Font embedding post-processor.
  - Slide renderer protocol.
  - Chart placeholder protocol, bukan chart implementation.
- **Acceptance tests:**
  - PPTX dapat dibuka.
  - Tidak ada text autofit/shrink.
  - Alt key sesuai.
  - Table key sesuai.
  - Table native, bukan image atau kumpulan shape.
  - Notes key sesuai.
  - Font parts valid.
  - Tidak ada timing/transition.
  - Coverage gagal pada key hilang.
- **Hard barrier:** chart lane tidak boleh mengedit file primitives; chart lane memakai kontrak chart renderer.

#### F1-DESIGN

- **Owner:** design system owner.
- **Files/glob:** `src/autooffice/design/**`, `src/autooffice/assets/fonts/**`, `tests/design/**`, `docs/contracts/design-token.md`, `docs/learn/design-system.md`.
- **Dependencies:** F0.
- **Deliverables:**
  - Token YAML.
  - Theme indigo dan hitam.
  - Font TTF dan lisensi.
  - Contrast checker.
  - Resolver token.
  - Dokumentasi token.
- **Acceptance tests:**
  - Semua token wajib ada.
  - Tidak ada referensi ke 12 theme lama.
  - Kontras lulus.
  - Font file hash, lisensi, dan family benar.
  - Theme tidak mengubah geometri.
  - `hitam` memakai kanvas terang dan aksen hitam sesuai palet deck-studio.
- **Hard barrier:** layout dan PPTX tidak boleh hardcode warna/ukuran sebelum token stabil.

#### F1-TEST

- **Owner:** test infrastructure owner.
- **Files/glob:** `tests/conftest.py`, `tests/fixtures/**` (kecuali fixture domain yang sudah dimiliki lane lain), `tools/quality/check_docs.py`, `tools/quality/check_tests.py`, `tools/quality/gate.py`, `docs/dev/testing.md`, `docs/dev/quality-gates.md`.
- **Dependencies:** F0.
- **Deliverables:**
  - Fixture isolation.
  - Fake clock, fake filesystem helpers, fake COM.
  - Fake Google skeleton.
  - Golden normalizer.
  - Gate runner.
  - Docs/test-quality checker.
- **Acceptance tests:**
  - Unit tests offline.
  - Tidak ada test menulis ke repo.
  - Coverage config.
  - Checker mendeteksi pelanggaran contoh.
  - Gate dapat dijalankan dari clean clone.
- **Hard barrier:** golden baseline dan COM lock harus siap sebelum visual test.

#### F1-CLI

- **Owner:** integration owner.
- **Files/glob:** `src/autooffice/cli/**`, `src/autooffice/errors.py`, `tests/cli/**`, `docs/contracts/cli.md`, `docs/user/cli.md`.
- **Dependencies:** F0, F1-MODEL, F1-DOCX, interfaces F1.
- **Deliverables:**
  - Parsing target.
  - Validasi input.
  - Orkestrasi DOCX.
  - Orkestrasi deck ke PPTX.
  - Output naming.
  - Dry-run.
  - Exit code.
  - Error rendering.
- **Acceptance tests:**
  - Matriks target.
  - `--out`.
  - `--theme` hanya YAML.
  - `--terms` hanya MD.
  - `--dry-run` tidak menulis.
  - Error code.
  - Help.
- **Hard barrier:** CLI tidak boleh mengimpor Google secara eager; extra `google` harus lazy.

### 13.4 Fase 2: Feature Lanes

Fase 2 boleh berjalan maksimal 7 feature worker bersamaan, dengan layout cap 4. Sheets dan Slides sync berada dalam satu lane `F2-GOOGLE` karena berbagi OAuth, state, dan kontrak linked chart. Memecahnya menjadi dua owner akan menciptakan dua pemilik pada area yang sama; pemisahan hanya boleh dilakukan setelah F0 memecah file dan kontraknya secara eksplisit.

#### F2-LAYOUT-CORE

- **Owner:** layout core owner.
- **Files/glob:** `src/autooffice/deck/layout/presets/cover.py`, `toc.py`, `content.py`, `section.py`, `closing.py`, `background.py`; `tests/deck/layout/test_core/**`; fixture unik per layout.
- **Dependencies:** F1-LAYOUT, F1-PPTX, F1-MODEL, F1-DESIGN.
- **Deliverables:** 6 preset layout, slot validation, golden semantic, visual indigo, hitam smoke.
- **Acceptance tests:** satu fixture per layout; key coverage; overflow fail; tidak ada teks default.
- **Hard barrier:** tidak boleh mengedit registry; discovery harus menemukan file baru.

#### F2-LAYOUT-DATA

- **Owner:** layout data owner.
- **Files/glob:** `src/autooffice/deck/layout/presets/kpi.py`, `bars.py`, `line.py`, `donut.py`, `table.py`, `comparison.py`; `tests/deck/layout/test_data/**`; fixture unik.
- **Dependencies:** F1-LAYOUT, F1-PPTX, kontrak chart F0.
- **Deliverables:** 6 preset layout, slot validation, table emphasis, chart slot validation.
- **Acceptance tests:** native chart slot, table keys, comparison emphasis, golden, overflow.
- **Hard barrier:** chart fake port dari kontrak F0 harus stabil sebelum lane selesai.

#### F2-LAYOUT-STRUCT

- **Owner:** layout structure owner.
- **Files/glob:** `src/autooffice/deck/layout/presets/matrix.py`, `flow.py`, `code.py`; `tests/deck/layout/test_structure/**`; fixture unik.
- **Dependencies:** F1-LAYOUT, F1-PPTX.
- **Deliverables:** 3 preset layout, heading/body cards, code overflow.
- **Acceptance tests:** slot validation, code no shrink, golden, visual.
- **Hard barrier:** code rendering memakai primitives F1, bukan menulis renderer baru.

#### F2-LAYOUT-MEDIA

- **Owner:** layout media owner.
- **Files/glob:** `src/autooffice/deck/layout/presets/diagram.py`, `image_split.py`, `image_full.py`, `image_grid.py`; `tests/deck/layout/test_media/**`; fixture unik.
- **Dependencies:** F1-LAYOUT, F1-PPTX, Mermaid contract.
- **Deliverables:** 4 preset layout, image fit/crop, alt coverage, diagram image.
- **Acceptance tests:** 3-image grid, full-bleed overlay, missing alt fails, Mermaid image only.
- **Hard barrier:** `mmdc` dijalankan di test melalui fake, live smoke terpisah.

#### F2-CUSTOM-GRID

- **Owner:** custom grid owner.
- **Files/glob:** `src/autooffice/deck/layout/custom.py`, `tests/deck/layout/test_custom.py`, `tests/fixtures/layouts/custom.yaml`.
- **Dependencies:** F1-LAYOUT, F1-PPTX, F1-MODEL.
- **Deliverables:**
  - Layout `custom` penuh.
  - Validasi `rows` dan `span`.
  - Tinggi row mengikuti isi.
  - Penempatan source dan chrome.
  - Contoh dua row atau lebih.
- **Acceptance tests:**
  - Row sum >12 ditolak.
  - Span 0/13 ditolak.
  - Tidak ada field absolute.
  - Tinggi mengikuti isi.
  - Overflow terdeteksi.
  - Key block custom stabil.
  - Golden semantic dan visual.
- **Hard barrier:** hanya menambah `custom.py` dan test unik; tidak mengedit registry atau preset.

#### F2-CHARTS

- **Owner:** charts owner.
- **Files/glob:** `src/autooffice/deck/charts/**`, `src/autooffice/deck/render/pptx/chart.py`, `tests/deck/charts/**`, `docs/contracts/chart-contract.md`.
- **Dependencies:** F1-PPTX, F1-MODEL, F1-DESIGN, kontrak chart F0.
- **Deliverables:**
  - Chart spec.
  - Native PPTX bar/line/donut.
  - Theme colors.
  - Chart XML validation.
  - Chart key coverage.
  - Placeholder generator.
- **Acceptance tests:** native chart parts, no image chart, data match, `chartSeries` color token, contrast 3:1 in both themes, `bar`/`line` 1-4 series pass and 5 fail; `donut` 1 series with 2-4 colored categories pass and 5 categories fail, placeholder marker, donut single series.
- **Hard barrier:** placeholder contract beku sebelum Google lane mulai.

#### F2-GOOGLE

- **Owner:** Google and sync owner.
- **Files/glob:** `src/autooffice/google/**`, `tests/google/**`, `tests/fixtures/google/**`, `docs/contracts/google-state.md`.
- **Dependencies:** F2-CHARTS, F1-PPTX, F1-MODEL, F1-CLI interfaces.
- **Deliverables:**
  - OAuth.
  - Drive upload.
  - Sheets workbook/tab/chart.
  - Linked chart replacement.
  - State.
  - Push/pull/diff/apply.
  - Fake.
  - Native table preflight.
- **Acceptance tests:** one spreadsheet per deck, one tab per chart, linked mode, placeholder replacement, native table (not image or shape group), table cell coverage, text coverage, scopes, failure recovery; missing table, image, shape group, or wrong row/column count must fail with slide ID and block ID; normal push must not call `CreateTableRequest`.
- **Hard barrier:** live Google smoke serial dan memakai akun uji; tidak paralel.

#### F2-PDF

- **Owner:** PDF/COM owner.
- **Files/glob:** `src/autooffice/pdf/**`, `tests/pdf/**`, `docs/contracts/pdf.md`, `docs/dev/com.md`.
- **Dependencies:** F1-DOCX, F1-PPTX, F1-TEST.
- **Deliverables:** Word COM, PowerPoint COM, lock, timeout, cleanup, PDF verification.
- **Acceptance tests:** fake COM sequence, timeout, one process at a time, real smoke DOCX/PPTX.
- **Hard barrier:** hanya satu worker COM; visual test berbagi lock.

#### F2-DEMO-DECK

- **Owner:** demo deck owner.
- **Files/glob:** `examples/demo-deck/**`, `tests/fixtures/demo/**`, `docs/learn/demo-deck.md`.
- **Dependencies:** F1-COPY, katalog layout beku, F2-LAYOUT-CORE, F2-LAYOUT-DATA, F2-LAYOUT-STRUCT, F2-LAYOUT-MEDIA, F2-CUSTOM-GRID, F2-CHARTS, F2-PDF.
- **Deliverables:**
  - Demo deck 20+ slide.
  - Aset gambar dan Mermaid.
  - Satu contoh setiap block type.
  - Deck dapat dibangun di kedua theme.
  - `copy.yaml` dan `transcripts.md` yang diporting.
- **Acceptance tests:** `check` bersih termasuk copy dan transcript, `build --target pptx,pdf` bersih, semua layout/block ada, tidak ada aset hilang.
- **Hard barrier:** tidak boleh mengklaim layout yang belum di-merge, dan tidak boleh mengedit `docs/user` milik F2-DOCS.

#### F2-DOCS

- **Owner:** docs owner.
- **Files/glob:** `docs/user/**` (kecuali `cli.md`), `docs/learn/**` (kecuali `demo-deck.md`, `design-system.md`, dan halaman kontrak), `docs/user/quickstart.md`, `docs/user/deck-authoring.md`, `docs/user/google-slides.md`.
- **Dependencies:** F0, katalog layout beku, kontrak CLI, F2-GOOGLE, minimal satu deck demo yang dapat dibangun.
- **Deliverables:**
  - Quickstart.
  - Panduan authoring deck.
  - Panduan dokumen DOCX.
  - Panduan Google Slides.
  - Halaman learn.
  - Troubleshooting.
- **Acceptance tests:** docs checker, link valid, perintah valid, tidak ada tutorial per fitur, tidak ada klaim layout yang belum ada.
- **Hard barrier:** dokumen kontrak dimiliki lane kontrak; F2-DOCS tidak boleh menduplikasi kontrak.

#### F2-CLI-INTEGRATION

- **Owner:** integration owner.
- **Files/glob:** `src/autooffice/cli/build.py`, `targets.py`, `outputs.py`, `docs/user/cli.md`.
- **Dependencies:** semua API lane sudah merged atau kontraknya stabil.
- **Deliverables:** wiring chart, Google, PDF, demo; wiring copy checker dan output transcript.
- **Acceptance tests:** end-to-end all targets, dry-run, errors, check/build copy error dan warning.
- **Hard barrier:** hanya integration owner yang mengedit CLI.

### 13.5 Fase 3: Integrasi dan Finalisasi

#### F3-ACCEPT

- **Owner:** integration owner + test infrastructure owner.
- **Files/glob:** `tests/acceptance/**`, `tests/golden/**` (existing golden updates only), `docs/decisions/**`, acceptance report.
- **Dependencies:** semua Fase 2 merged.
- **Deliverables:** acceptance matrix, visual goldens, live Google smoke, COM smoke, build all.
- **Acceptance tests:** Bagian 18.
- **Hard barrier:** tidak ada lane yang masih menulis file; branch freeze.

#### F3-DELETE

- **Owner:** integration owner.
- **Files/glob:** `src/docgen/**`, `tests/docx` lama yang tidak dipakai, `package.json`, `node_modules`, `src/` JavaScript, `design-system/` lama yang tidak dipakai, `decks/` lama yang tidak dipakai, `src/render/` lama, `.github/workflows`.
- **Dependencies:** F3-ACCEPT.
- **Deliverables:** hapus kode lama, update `.gitignore`, `pyproject`, docs index.
- **Acceptance tests:** `git ls-files` tidak memuat kode lama; `rg "docgen|deck-studio|PptxGenJS|Reveal"` bersih di runtime/docs user; package wheel bersih.
- **Hard barrier:** jangan hapus sebelum acceptance lulus. Jangan archive/rename di commit yang sama dengan deletion.

#### F3-RENAME

- **Owner:** integration owner.
- **Files/glob:** root folder, GitHub remote, `pyproject.toml`, `README.md`, docs, package metadata.
- **Dependencies:** F3-DELETE.
- **Deliverables:** repo GitHub `autooffice`, folder lokal `autooffice`, remote URL, docs URL.
- **Acceptance tests:** clean clone dari URL baru, `uv sync`, `autooffice --help`, build demo, tidak ada referensi lama.
- **Hard barrier:** rename hanya setelah final code freeze. Setelah rename, tidak ada merge dari branch lama tanpa rebase.

#### F3-GATE

- **Owner:** integration owner + test infrastructure owner.
- **Files/glob:** `tools/quality/gate.py`, `docs/dev/quality-gates.md`, release checklist.
- **Dependencies:** F3-RENAME.
- **Deliverables:** final gate run, artifact checks, wheel/sdist, clean clone.
- **Acceptance tests:** semua gate Bagian 12.11 dan acceptance Bagian 18.
- **Hard barrier:** no commit/tag/approval sampai seluruh gate lulus.

---

## 14. Matriks Ownership dan Aturan Anti-Konflik

### 14.1 Matriks Ownership

Untuk F0, `docs/contracts/ownership.md` adalah sumber otoritatif; tabel ini adalah ringkasan lane.

| Path/glob | Owner | Fase | Catatan |
| --- | --- | --- | --- |
| `pyproject.toml`, `uv.lock` | integration owner | 0-3 | Hanya integration owner. Dependency request lewat lane card. |
| `src/autooffice/__init__.py`, `__main__.py` | integration owner | 0-3 | Shared entry point. |
| `src/autooffice/cli/**` | integration owner | 0-3 | Satu-satunya pemilik CLI. |
| `src/autooffice/common/**` | integration owner | 0-3 | Shared utility. |
| `src/autooffice/errors.py` | integration owner | 0-3 | Error taxonomy. |
| `src/autooffice/design/**` | design owner | 1-3 | Token dan theme. |
| `src/autooffice/assets/fonts/**` | design owner | 1-3 | Font dan lisensi. |
| `src/autooffice/docx/**` | DOCX owner | 1-3 | Migrasi docgen. |
| `src/autooffice/deck/model/**` | model owner | 1-3 | Schema, compiler, key. |
| `src/autooffice/deck/blocks/**` kecuali `registry.py` | model owner | 1-3 | 11 block spec. |
| `src/autooffice/deck/blocks/registry.py` | integration owner | 0-3 | Shared registry. |
| `src/autooffice/deck/layout/**` kecuali presets, `custom.py`, dan `registry.py` | layout owner | 1-2 | Grid, measure, rows. |
| `src/autooffice/deck/layout/registry.py` | integration owner | 0-3 | Discovery dan validasi katalog. |
| `src/autooffice/deck/layout/custom.py` | custom grid owner | 2 | Custom composition. |
| `src/autooffice/deck/layout/presets/*.py` | layout lane sesuai grup | 2 | Satu owner per file. |
| `src/autooffice/deck/charts/**` | charts owner | 2-3 | Spec dan native chart. |
| `src/autooffice/deck/copy/**` | copy owner | 1-3 | Rule copy dan config. |
| `src/autooffice/deck/transcript/**` | copy owner | 1-3 | Parser dan model transkrip. |
| `src/autooffice/deck/render/pptx/chart.py` | charts owner | 2-3 | Transfer ownership setelah F1. |
| `src/autooffice/deck/render/pptx/**` selain chart | PPTX owner | 1-3 | Primitives dan coverage. |
| `src/autooffice/google/**` | Google owner | 2-3 | Satu owner untuk seluruh Google. |
| `src/autooffice/pdf/**` | PDF owner | 2-3 | COM. |
| `examples/docx/**` | DOCX owner | 1-3 | Contoh lama. |
| `examples/demo-deck/**` | demo deck owner | 2-3 | Demo acceptance. |
| `examples/demo-deck/transcripts.md` dan `copy.yaml` | demo deck owner | 2-3 | Transkrip dan config copy demo. |
| `tests/fixtures/demo/**` | demo deck owner | 2-3 | Fixture demo. |
| `tests/conftest.py` | test infrastructure owner | 1-3 | Shared fixture. |
| `tests/fixtures/**` | test infrastructure owner; fixture domain dapat dimiliki lane | 1-3 | File fixture unik boleh ditambah lane; existing tidak diedit. |
| `tests/contract/**` | test infrastructure owner + integration | 0-3 | Kontrak. |
| `tests/deck/model/**` | model owner | 1-2 | Test domain. |
| `tests/deck/layout/**` | layout owner atau layout lane | 1-2 | File unik per layout. |
| `tests/deck/render/pptx/**` | PPTX owner | 1-2 | Test primitives. |
| `tests/deck/charts/**` | charts owner | 2-3 | Test chart. |
| `tests/deck/copy/**` | copy owner | 1-2 | Test copy dan transcript. |
| `tests/fixtures/copy/**` | copy owner/test infrastructure | 1-2 | Fixture copy dan transcript. |
| `tests/google/**` | Google owner | 2-3 | Fake dan contract. |
| `tests/pdf/**` | PDF owner | 2-3 | COM fake. |
| `tests/acceptance/**` | integration owner | 0-3 | Acceptance. |
| `tests/golden/**` | test infrastructure owner + integration; lane boleh menambah file golden unik miliknya | 1-3 | Update golden existing serial. |
| `docs/contracts/deck-schema.md`, `key-grammar.md` | model owner | F0 integration owner, handoff ke model owner di F1-MODEL | Setelah freeze, perubahan lewat ADR. |
| `docs/contracts/layout-spec.md` | layout owner | 0-2 | Setelah freeze, perubahan lewat ADR. |
| `docs/contracts/pptx-renderer.md` | PPTX owner | 0-2 | Kontrak renderer. |
| `docs/contracts/chart-contract.md` | charts owner | 2-3 | Kontrak chart. |
| `docs/contracts/copy.md` dan `transcript.md` | copy owner | 0-2 | Kontrak copy dan transcript. |
| `docs/contracts/google-state.md` | Google owner | 2-3 | Kontrak Google. |
| `docs/contracts/cli.md` | integration owner | 0-3 | Kontrak CLI. |
| `docs/contracts/coverage.md` | integration owner | 0-3 | Exclusion policy. |
| `docs/user/**` | docs owner; `cli.md` integration owner | 2-3 | User-facing. |
| `docs/learn/**` | docs owner; `demo-deck.md` demo deck owner | 2-3 | Konsep. |
| `docs/learn/humanizer.md` | docs owner; copy owner menyediakan isi | 2-3 | Checklist editorial di luar gate. |
| `docs/dev/**` | integration owner + test infrastructure owner | 0-3 | Developer docs. |
| `docs/decisions/**` | integration owner | 0-3 | ADR. |
| `docs/README.md` | integration owner | 0-3 | Navigasi. |
| `README.md`, `AGENTS.md` | integration owner | 0-3 | Root docs. |
| `tools/quality/**` | test infrastructure owner | 0-3 | Gate. |
| `.github/workflows/**` | integration owner | 3 | Dihapus. Tidak ada CI. |

### 14.2 Aturan Anti-Konflik

1. Satu file hanya satu owner aktif.
2. Satu glob hanya satu owner aktif.
3. Integration owner satu-satunya yang boleh mengedit file shared.
4. Layout lane hanya menambah file preset dan test unik. Custom grid lane hanya menambah `custom.py` dan test unik. Tidak ada layout lane yang mengedit registry.
5. Registry layout memakai discovery deterministik. Menambah file preset harus cukup untuk registrasi. Bila registry perlu diubah, integration owner yang mengubah.
6. Block registry bersifat tetap untuk 11 block type. Block type baru memerlukan ADR.
7. `pyproject.toml` dan `uv.lock` tidak boleh diedit lane. Dependency request ditulis di lane card dan dieksekusi integration owner.
8. `docs/contracts/layout-spec.md` adalah kontrak layout beku. Lane tidak boleh mengeditnya tanpa ADR.
9. File golden existing hanya diperbarui oleh golden owner dengan flag update eksplisit. Lane boleh menambah file golden baru di path unik miliknya, tetapi tidak boleh mengubah golden milik lane lain.
10. File fixture existing tidak boleh diedit lane. Lane boleh menambah file baru dengan nama unik.
11. Lane tidak boleh mengedit test lane lain. Bila perlu, ajukan perubahan ke owner.
12. Dua branch yang menyentuh file yang sama tidak boleh di-merge tanpa integration step.
13. Konflik merge dianggap pelanggaran ownership. Pekerjaan dihentikan, file dipetakan ulang, lalu dijadwalkan serial.
14. Lane yang blocked tetap memegang lock hanya bila pekerjaan aktif. Lane yang parkir harus melepas slot.
15. Tidak ada workaround lintas lane untuk menghindari kontrak.

---

## 15. Strategi Paralelisme Maksimal

### 15.1 Kapasitas Worker

- Total worker aktif maksimum: **8**, terdiri dari 1 integration owner dan 7 feature worker.
- Fase 0: 1 worker (integration owner) karena hard barrier.
- Fase 1: maksimum 6 feature worker, karena dependency design dan model belum siap untuk semua lane.
- Fase 2: maksimum 7 feature worker, dengan layout cap 4 (termasuk `F2-CUSTOM-GRID`).
- Fase 3: maksimum 2 worker (integration + test), karena acceptance, deletion, rename, dan gate bersifat serial.

Kapasitas ini dipilih karena:

- 4 layout lane sudah cukup untuk memakai core layout dan renderer secara paralel.
- Charts, Google, dan PDF adalah lane berat yang tidak boleh dipecah ke banyak owner karena shared contract.
- COM, Google live, golden, dan rename adalah resource eksklusif.
- 8 worker menghindari contention pada review dan merge.

### 15.2 Kapan Worker Boleh Mulai

Worker hanya boleh mulai bila semua benar:

1. Lane card memiliki owner tunggal.
2. File/glob tidak overlap dengan lane aktif.
3. Dependency lane sudah merged dan gate-nya lulus.
4. Kontrak yang dipakai sudah dibekukan di Fase 0.
5. Fixture/acceptance criteria tersedia.
6. Integration branch bersih.
7. Tidak ada hard barrier yang aktif.

Worker tidak boleh mulai hanya karena "sudah bisa dikerjakan". Harus ada dependency dan file lock yang jelas.

### 15.3 Queue Prioritas

Urutan queue:

1. F0 contract freeze.
2. F1-DESIGN dan F1-MODEL (critical path).
3. F1-COPY (setelah F1-MODEL).
4. F1-LAYOUT dan F1-PPTX.
5. F1-DOCX (independen, boleh paralel).
6. F1-TEST dan F1-CLI.
7. F2-LAYOUT-CORE/DATA/STRUCT/MEDIA dan F2-CUSTOM-GRID (maksimal 4 layout-related worker aktif).
8. F2-CHARTS.
9. F2-GOOGLE.
10. F2-PDF.
11. F2-DEMO-DECK dan F2-DOCS.
12. F3-ACCEPT.
13. F3-DELETE.
14. F3-RENAME.
15. F3-GATE.

Queue bukan batch barrier. Bila slot bebas, ambil task berikutnya yang ready.

### 15.4 Resource Eksklusif

| Resource | Aturan |
| --- | --- |
| Word COM | Hanya satu operasi aktif. Queue global. |
| PowerPoint COM | Hanya satu operasi aktif. Queue global. |
| Visual golden render | Memakai lock PowerPoint yang sama. |
| Google live smoke | Satu akun dan satu operator. Tidak paralel dengan push lain. |
| Golden fixture update | Satu worker, review integration owner. |
| `pyproject.toml`/`uv.lock` | Integration owner saja. |
| Repo rename | Freeze merge dan worker. |
| Font installation | Satu langkah environment, sebelum visual test. |
| Shared integration branch | Hanya integration owner merge. |

### 15.5 Predictive Branching

Diizinkan hanya bila:

- kontrak sudah beku;
- file disjoint dari dependency;
- maksimal satu dependency hop;
- tidak menyentuh migration, schema global, pyproject, atau golden existing;
- dapat diuji dengan fake atau contract boundary.

Aturan:

- Branch dari integration base, bukan dari branch dependency yang belum merged.
- Mock dependency di boundary.
- Tulis contract test untuk kedua sisi.
- Setelah dependency merge, rebase dan jalankan ulang test.
- Bila kontrak berubah, buang branch, jangan paksa merge.
- Branch prediktif yang selesai lebih awal diparkir dan melepas worker slot.

### 15.6 Merge Protocol

1. Worker menyelesaikan lane.
2. Worker menjalankan targeted test dan melaporkan diff.
3. Integration owner memeriksa diff aktual, bukan hanya ringkasan.
4. Integration owner menjalankan ulang test yang terdampak.
5. Bila lulus, merge ke integration branch.
6. Setelah merge, jalankan test integrasi yang terdampak.
7. Update status lane.
8. Buka dependent lane.
9. Isi slot worker dengan task ready berikutnya.

Tidak ada merge tanpa verifikasi. Tidak ada merge langsung ke main. Tidak ada merge dua branch yang menyentuh area yang sama tanpa integration step.

### 15.7 Stop Rules

Hentikan lane dan eskalasi bila:

- kontrak berubah;
- file overlap;
- dependency belum merged tetapi bukan predictive branch;
- test flaky;
- coverage turun;
- golden berubah tanpa review;
- COM hang;
- Google API mengembalikan error yang tidak bisa dipulihkan;
- keputusan produk baru diperlukan.

---

## 16. Migrasi dan Penghapusan

### 16.1 Peta docgen ke AutoOffice

| Sumber docgen | Tujuan AutoOffice | Perlakuan |
| --- | --- | --- |
| `src/docgen/cli.py` | `src/autooffice/cli/` + `src/autooffice/docx/command.py` | Porting dan wiring baru. |
| `src/docgen/pipeline.py` | `src/autooffice/docx/pipeline.py` | Porting tanpa perubahan urutan. |
| `src/docgen/stages/` | `src/autooffice/docx/stages/` | Porting. |
| `src/docgen/docx/` | `src/autooffice/docx/package/` | Porting. |
| `src/docgen/config/` | `src/autooffice/docx/config/` | Porting. |
| `src/docgen/adeu/` | `src/autooffice/docx/adeu/` | Porting. |
| `src/docgen/terms/` | `src/autooffice/docx/terms/` | Porting. |
| `src/docgen/data/formats/` | `src/autooffice/docx/data/formats/` | Package data. |
| `src/docgen/data/structures/` | `src/autooffice/docx/data/structures/` | Package data. |
| `scripts/word.ps1` | `src/autooffice/pdf/word.py` | Ganti adaptor PowerShell dengan COM Python dengan perilaku setara. |
| `tests/` docgen | `tests/docx/` | Porting dan golden baseline. |
| `examples/*-single/` | `examples/docx/*-single/` | Porting path. |
| `tools/dev/` | `tools/quality/` | Porting dan perluasan. |

Yang dipertahankan:

- Semua aturan format dan struktur.
- Semua stage dan invariant.
- Semua output pengguna.
- Manifest dan istilah.
- Golden fixture.

Yang dihapus:

- Namespace `docgen`.
- Entry point `docgen`.
- Dokumentasi yang hanya berlaku untuk `docgen`.
- Nama package di lock, metadata, dan docs.
- Flag lama yang tidak punya padanan dan tidak disetujui di Bagian 19.
- Nilai target lama `both` diganti `all`.
- Flag lama `--keep` diganti `--keep-intermediate` sesuai keputusan CLI baru.

### 16.2 Peta deck-studio ke AutoOffice

| Sumber deck-studio | Tujuan AutoOffice | Perlakuan |
| --- | --- | --- |
| `src/core/schema.js` | `src/autooffice/deck/model/` | Ditulis ulang di Python. |
| `src/core/contract.js`, `REQUIRED_KEYS` | `KeyManifest`, `CoveragePlan` | Diganti compiler. |
| `src/app/coverage.js` | `src/autooffice/deck/model/coverage.py` + `render/pptx/coverage.py` | Semantik key dipertahankan, implementasi Python. |
| `src/render/html.js` | tidak ada | Dihapus. |
| `src/render/pptx.js` | `src/autooffice/deck/render/pptx/` | Ditulis ulang dengan `python-pptx`. |
| `src/render/mermaid/` | `src/autooffice/deck/layout` + external `mmdc` | Cache dan output gambar dipertahankan. |
| `src/google/` | `src/autooffice/google/` | Porting OAuth/upload/pull, ditambah Sheets. |
| `src/sync/` | `src/autooffice/google/sync.py` | Porting push/pull/diff/apply. |
| `design-system/tokens.json` | `src/autooffice/design/data/tokens.yaml` | Porting. |
| `design-system/themes.json` | `src/autooffice/design/data/themes.yaml` | Dikurangi menjadi indigo dan hitam. |
| `design-system/styles/` | token/layout Python | CSS tidak diporting. |
| `design-system/vendor/reveal/` | tidak ada | Dihapus. |
| `decks/demo/` | `examples/demo-deck/` | Konten dan aset diporting ke YAML. |
| `decks/diagrams/` | `examples/demo-deck/diagrams/` atau fixture | Konten dan `.mmd` diporting. |
| `tests/` Node | `tests/deck/**`, `tests/google/**` | Semantik dipertahankan, implementasi Python. |
| `docs/authoring-guide.md` | `docs/learn/humanizer.md` + `docs/contracts/copy.md` | Aturan naskah diadaptasi, bukan disalin verbatim. |
| `scripts/check-copy.js` | `src/autooffice/deck/copy/` | Ditulis ulang di Python dengan config. |
| `decks/demo/transcripts.md` | `examples/demo-deck/transcripts.md` | Format heading memakai slide ID. |
| `docs/humanizer-sources/` | atribusi di `docs/contracts/copy.md` | Arsip verbatim tidak menjadi runtime. |
| `package.json`, `node_modules` | tidak ada | Dihapus. |

Yang dipertahankan:

- Design token dan visual language.
- Demo content yang relevan.
- Diagram Mermaid.
- Fixture gambar.
- Aturan kontras.
- Aturan naskah dan copy checker diporting sebagai kontrak.
- Semantik key dan alt text.

Yang dihapus:

- HTML, Reveal, CSS, dan aset browser.
- PptxGenJS.
- 12 theme, kecuali token yang diperlukan indigo dan hitam.
- Layout `image-annotated`, `image-figure`, `table-long` dari katalog v1.
- Animasi dan transition.
- JSON deck model.
- Node test runner.
- Script demo yang hanya menghasilkan HTML.

### 16.3 Daftar No-Dead-Code

Checklist final:

- [ ] `git ls-files` tidak memuat `src/docgen/`.
- [ ] `git ls-files` tidak memuat `package.json`, `package-lock.json`, `node_modules/`, `.js`, `.mjs`, atau `.cjs` sumber.
- [ ] Tidak ada package `docgen` di `pyproject.toml`.
- [ ] Tidak ada entry point `docgen`.
- [ ] Tidak ada entry point `deck-studio`.
- [ ] Tidak ada import `docgen` atau `deck-studio`.
- [ ] Tidak ada alias atau shim `autooffice.docgen`.
- [ ] Tidak ada `PptxGenJS`, `Reveal`, `zod`, atau `playwright-core` di dependency.
- [ ] Tidak ada layout yang tidak terdaftar di katalog.
- [ ] Tidak ada block `callout`.
- [ ] Tidak ada animasi atau transition di renderer.
- [ ] Tidak ada template PPTX eksternal di repo.
- [ ] Tidak ada file output, cache, state, atau token OAuth yang di-track Git.
- [ ] Tidak ada docs user yang menautkan repo lama.
- [ ] Tidak ada `check-copy.js` atau aturan copy hardcoded di JavaScript.
- [ ] `transcripts.md` demo ada dan tervalidasi.
- [ ] `autooffice --help` hanya menampilkan perintah yang didukung.
- [ ] Wheel hanya berisi package `autooffice`, data, font, dan metadata.
- [ ] Clean clone dapat build tanpa file di luar repo selain dependency eksternal yang didokumentasikan.
- [ ] Repo GitHub bernama `autooffice`.
- [ ] Remote lama tidak dipakai.
- [ ] Dokumen migrasi ini ditandai historis dan bukan bagian docs user.

### 16.4 Repo Rename

Urutan:

1. Semua lane selesai, gate final lulus.
2. Freeze merge.
3. Pastikan tidak ada branch aktif yang menyentuh file yang akan dihapus.
4. Hapus kode lama.
5. Update `pyproject.toml`, package metadata, remote URL, README, docs, dan lock.
6. Rename repository GitHub dari `docgen` menjadi `autooffice`.
7. Rename folder lokal dari `C:\dev\apps\docgen` menjadi `C:\dev\apps\autooffice`.
8. Update remote lokal.
9. Clean clone dari URL baru.
10. Jalankan gate final lagi.
11. Baru boleh membuat tag/release.
12. `deck-studio` diarsipkan atau dihapus sesuai keputusan pemilik setelah semua konten dan fixture diporting. Tidak boleh ada submodule atau referensi ke repo itu.

Tidak ada alias URL, package, atau CLI.

---

## 17. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi | Gate |
| --- | --- | --- | --- |
| `python-pptx` tidak mendukung font embedding secara high-level | PPTX tanpa font, layout berubah, PowerPoint repair | Post-processor OOXML, validasi OPC, buka di PowerPoint, golden visual, gagal keras bila tidak valid | F1-PPTX, F3-ACCEPT |
| Native chart PPTX berbeda dari chart shape deck-studio | Tampilan berubah, data tidak cocok | Chart spec kecil dan eksplisit, golden chart XML, visual test per kind, warna token | F2-CHARTS |
| Linked chart Google Sheets tidak bisa menggantikan placeholder dengan andal | Slides tanpa chart atau chart ganda | Placeholder shape dengan alt deterministik, preflight, batch replacement, fake API, live smoke | F2-GOOGLE |
| API Google berubah, kuota, atau scope ditolak | Push/pull gagal | Adapter tipis, fake, error jelas, backoff terbatas, uji akun bersih | F2-GOOGLE |
| OAuth user owns file, state menunjuk file akun lain | File tidak bisa diakses | State menyimpan email? Minimal error jelas, reset state, login ulang. Jangan service account | F2-GOOGLE |
| Word/PowerPoint COM hang atau dialog modal | Build macet, file lock | Serialisasi, timeout, salinan temp, watchdog, cleanup, test fake | F2-PDF |
| Text measurement di Python berbeda dari PowerPoint/Google Slides | Overflow atau layout tidak rapi | Ukur dengan font TTF yang sama, safety margin, no shrink, visual test, live slides check | F1-LAYOUT, F2-GOOGLE |
| 100% coverage mendorong test palsu atau exclusion longgar | Gate tidak bermakna | Exclusion policy, test-quality checker, fakes, review coverage report, no global omit | F1-TEST, F3-GATE |
| Key tidak stabil saat edit YAML | Sync salah, kehilangan teks | ID eksplisit, compiler binding, duplicate fail, reorder test, migration note | F1-MODEL |
| Migrasi DOCX mengubah output | Regresi dokumen akademik | Golden baseline, porting tanpa refactor perilaku, bandingkan part, test Word | F1-DOCX |
| Mermaid `mmdc` tidak tersedia atau output berubah | Diagram gagal atau tidak konsisten | Pin versi, cache hash, doctor, fake test, live smoke, fail keras | F2-LAYOUT-MEDIA |
| Font Plus Jakarta Sans tidak tersedia di Google Slides | Fallback font, overflow | Google Fonts, warning, live smoke, cek overflow setelah upload | F2-GOOGLE |
| Theme `hitam` disalahartikan sebagai dark theme | Visual tidak sesuai palet deck-studio | Ambil aksen/cover dari `themes.json` + `tokens.json`; chart dari `chartSeries`; `dist/themes/hitam.html` hanya referensi visual aksen/cover setelah di-regenerasi; kontras test, visual review | F1-DESIGN |
| Table PPTX diimpor sebagai gambar atau shape group di Google Slides | Table tidak editable dan sync cell gagal | Preflight page element `table`, cek jumlah baris/kolom, fail keras, live smoke; fallback `CreateTableRequest` ditunda | F2-GOOGLE |
| Repo rename memutus remote, docs, atau cache | Build clean clone gagal | Freeze, rename terakhir, clean clone, rg no legacy, gate ulang | F3-RENAME |
| Lisensi font atau aset demo | Tidak boleh didistribusikan | OFL untuk font, audit lisensi gambar demo, dokumentasi atribusi | F1-DESIGN, F3-ACCEPT |
| Layout preset terlalu kaku untuk demo | Demo tidak bisa diporting | Porting konten ke block, bukan memaksa pixel parity, custom untuk kasus khusus | F2-DEMO-DECK |
| Runtime lambat karena full strict gate dan visual COM | Iterasi lambat | Test minimum saat coding, gate penuh hanya final/merge besar, cache Mermaid, parallel lane | F3-GATE |
| Copy checker menghasilkan false positive | Build gagal pada naskah yang sah | Rule fixture, warning untuk rule rapuh, allowlist dengan alasan, review config | F1-COPY |
| Aturan Indonesia diterapkan ke teks Inggris | False positive pada transkrip bilingual | Rule pack per bahasa, test bilingual | F1-COPY |
| Humanizer dianggap bisa sepenuhnya otomatis | Gate terlalu percaya diri | Hanya rule mekanis di gate; checklist editorial di docs | F1-COPY |
| Transkrip melenceng dari deck | Transkrip tidak cocok dengan slide | Heading memakai slide ID, validasi semua slide, check saat build | F1-COPY, F2-DEMO-DECK |

Risiko tinggi yang harus di-spike sebelum Fase 2 selesai:

1. Font embedding PPTX.
2. Linked chart replacement di Google Slides.
3. Upload dan conversion PPTX ke Google Slides.
4. Word/PowerPoint COM di mesin target.
5. Google Fonts vs embedded font di Slides.
6. 100% coverage pada adapter Google dan COM.

---

## 18. Acceptance Criteria Final

### 18.1 Struktur dan Packaging

- [ ] Satu package `autooffice` dapat di-install dari wheel.
- [ ] Satu CLI `autooffice`.
- [ ] Tidak ada package, entry point, atau alias `docgen` atau `deck-studio`.
- [ ] Dependency core hanya yang disetujui: `python-pptx`, `lxml`, `ruamel.yaml`, `Pillow`, `pywin32` (Windows), dan dependency kecil lain yang disetujui.
- [ ] Extra `google` dan `dev` berfungsi.
- [ ] `uv sync --extra dev` berhasil.
- [ ] `uv build` menghasilkan wheel dan sdist bersih.
- [ ] Wheel memuat token, font, data format DOCX, dan lisensi.

### 18.2 DOCX

- [ ] Fixture assignment, proposal, thesis menghasilkan DOCX yang setara dengan baseline docgen.
- [ ] Manifest deterministik.
- [ ] Istilah dan `--terms` setara.
- [ ] TOC/field finalization lewat Word.
- [ ] PDF DOCX dihasilkan via Word COM.
- [ ] Output naming dan `report_name` setara.
- [ ] Tidak ada design token deck di DOCX.

### 18.3 Deck YAML dan Compiler

- [ ] `check` menerima demo deck.
- [ ] Semua field unknown ditolak.
- [ ] Key stabil setelah reorder slide dan block.
- [ ] Duplicate key, duplicate slide ID, duplicate block ID ditolak.
- [ ] Inline Markdown sesuai kontrak.
- [ ] Path traversal ditolak.
- [ ] Semua block type muncul di demo.
- [ ] Semua layout didukung muncul di demo.
- [ ] Custom grid memakai rows dan span valid.
- [ ] Tidak ada absolute positioning.

### 18.4 PPTX

- [ ] PPTX dapat dibuka PowerPoint tanpa repair.
- [ ] 20 slide acceptance memakai layout dan block yang benar.
- [ ] Chart native untuk bar, line, donut.
- [ ] Batas chart diuji: `bar`/`line` 1-4 seri lolos dan 5 seri gagal; `donut` 2-4 kategori berwarna lolos dan 5 kategori gagal.
- [ ] Palet `chartSeries` lolos kontras 3:1 di indigo dan hitam.
- [ ] Table native.
- [ ] Image native dengan crop proporsional.
- [ ] Notes ada dan benar.
- [ ] Alt text lengkap.
- [ ] Key coverage 100%.
- [ ] Font Plus Jakarta Sans tertanam.
- [ ] Tidak ada animasi.
- [ ] Tidak ada transition.
- [ ] Tidak ada text shrink.
- [ ] Tidak ada overflow.
- [ ] Golden semantic PPTX lulus.
- [ ] Visual golden indigo lulus.
- [ ] Deck hitam lulus dengan kanvas terang dan aksen hitam sesuai palet deck-studio.

### 18.5 Google Slides

- [ ] Push membuat presentasi Google Slides.
- [ ] Chart placeholder diganti linked chart.
- [ ] Satu spreadsheet per deck.
- [ ] Satu tab per chart.
- [ ] Linked mode benar.
- [ ] Data satu arah YAML ke Sheets.
- [ ] Chart native di Slides.
- [ ] Table native di Slides, bukan image atau shape group.
- [ ] Jumlah baris/kolom dan cell text table sesuai YAML.
- [ ] Table cell text ikut push/pull/diff.
- [ ] Table hilang, image, shape group, atau jumlah baris/kolom salah menggagalkan push dengan slide ID dan block ID.
- [ ] Push normal tidak memanggil `CreateTableRequest`.
- [ ] Diagram tetap gambar.
- [ ] Teks, notes, dan source bisa push.
- [ ] Pull menghasilkan snapshot.
- [ ] Diff mendeteksi perubahan.
- [ ] Apply menghasilkan YAML baru yang valid.
- [ ] Format kaya tidak diklaim round-trip.
- [ ] Scope OAuth benar.
- [ ] File dimiliki akun uploader.
- [ ] Failure recovery tidak membuat spreadsheet duplikat.
- [ ] Live smoke dengan akun uji lulus.

### 18.6 PDF

- [ ] DOCX ke PDF via Word COM.
- [ ] PPTX ke PDF via PowerPoint COM.
- [ ] Chart PDF tetap native.
- [ ] COM serial.
- [ ] Timeout.
- [ ] File PDF valid dan dapat dibuka.
- [ ] Tidak ada fallback LibreOffice atau HTML.

### 18.7 Mermaid

- [ ] `mmdc` menghasilkan PNG.
- [ ] Cache bekerja.
- [ ] Diagram muncul di PPTX sebagai gambar.
- [ ] Diagram muncul di Google Slides sebagai gambar.
- [ ] Tidak ada node native.
- [ ] Alt dan caption benar.
- [ ] Gagal keras bila `mmdc` tidak ada.

### 18.8 CLI

- [ ] Matriks target Bagian 10.2 lulus.
- [ ] `--out` lulus.
- [ ] `--theme` lulus dan hanya YAML.
- [ ] `--terms` lulus dan hanya MD.
- [ ] `--dry-run` tidak menulis file/remote.
- [ ] `--keep-intermediate` menyimpan intermediate.
- [ ] `--sync push/pull/diff/apply` lulus.
- [ ] Exit code 0/1/2 sesuai.
- [ ] `check` tidak memanggil Office/Google.
- [ ] `doctor` memberi diagnosis yang dapat ditindaklanjuti.

### 18.9 Quality Gate

- [ ] Ruff lulus.
- [ ] Mypy ketat lulus.
- [ ] Import-linter lulus.
- [ ] Pytest lulus.
- [ ] Coverage 100% line dan branch.
- [ ] Semua exclusion tercatat di `docs/contracts/coverage.md`.
- [ ] Docs checker lulus.
- [ ] Test-quality checker lulus.
- [ ] No-legacy checker lulus.
- [ ] Tidak ada GitHub Actions.
- [ ] Clean clone lulus gate.

### 18.10 Demo Deck

`examples/demo-deck/deck.yaml` harus memenuhi:

- [ ] Berasal dari konten demo deck-studio yang diporting.
- [ ] Minimal 20 slide: 19 preset dan 1 custom.
- [ ] Minimal satu slide untuk setiap layout di Bagian 6.2.
- [ ] Minimal satu contoh setiap block type: `text`, `bullets`, `image`, `table`, `chart`, `code`, `quote`, `diagram`, `divider`, `spacer`, `metric`.
- [ ] Tidak ada `callout`.
- [ ] Ada chart bar, line, dan donut.
- [ ] Ada tabel.
- [ ] Ada gambar split, full, dan grid.
- [ ] Ada diagram Mermaid.
- [ ] Ada code.
- [ ] Ada quote.
- [ ] Ada divider dan spacer.
- [ ] Ada custom grid dengan minimal dua row.
- [ ] Berjalan di indigo dan hitam.
- [ ] Source dan notes dipakai minimal di beberapa slide.
- [ ] Semua aset ada dan berlisensi.
- [ ] `check` bersih.
- [ ] `build --target all` sukses di environment acceptance.
- [ ] Golden PPTX dan PDF lulus.

### 18.11 Dokumentasi

- [ ] `docs/README.md` adalah indeks navigasi.
- [ ] `docs/user` berisi quickstart, authoring deck, dokumen DOCX, CLI, Google Slides, troubleshooting.
- [ ] `docs/dev` berisi arsitektur, renderer, testing, gate, contributing.
- [ ] `docs/learn` berisi konsep model deck, key, grid, native vs image, sync.
- [ ] `docs/contracts` berisi semua kontrak.
- [ ] `docs/decisions` berisi ADR keputusan terkunci dan perubahan kontrak.
- [ ] Tidak ada tutorial per fitur.
- [ ] Tidak ada link ke repo lama di docs user.
- [ ] Semua contoh perintah valid.
- [ ] Tidak ada duplikasi kontrak di banyak halaman.

### 18.12 Repo dan Kebersihan

- [ ] Repo GitHub bernama `autooffice`.
- [ ] Folder lokal bernama `autooffice`.
- [ ] Remote lama tidak ada.
- [ ] Tidak ada kode Node.
- [ ] Tidak ada `node_modules`.
- [ ] Tidak ada `src/docgen`.
- [ ] Tidak ada `PptxGenJS`, `Reveal`, `zod`, `playwright-core`.
- [ ] Tidak ada file cache/state/token di Git.
- [ ] `.gitignore` benar.
- [ ] Dokumen migrasi ini ditandai historis atau diarsipkan sesuai keputusan pemilik.
- [ ] `rg` untuk nama lama bersih di runtime, package, README, docs user, dan config.
- [ ] Clean clone dari URL baru lulus quickstart.

### 18.13 Copy dan Transcript

- [ ] `copy.yaml` valid; tanpa config default berlaku.
- [ ] Teks slide, notes, dan transkrip diperiksa.
- [ ] Error menghentikan build; warning tidak.
- [ ] Bila `transcripts.md` ada, semua slide punya bagian transkrip; tidak ada duplikat atau slide asing.
- [ ] Bila `transcripts.md` ada, transkrip tersalin ke output sebagai `<stem>.transcript.md`.
- [ ] `targets.transcript: true` tanpa `transcripts.md` tidak menghasilkan error.
- [ ] DOCX tidak terpengaruh; `--terms` tetap berlaku.
- [ ] Tidak ada network, LLM, atau Office di copy checker.
- [ ] Demo deck lulus copy checker.

### 18.14 Syarat Tanda Tangan Final

Final hanya boleh ditandatangani bila:

1. Semua acceptance di Bagian 18.1 sampai 18.13 lulus.
2. Tidak ada open question kritis yang tersisa.
3. Tidak ada lane aktif.
4. COM smoke dan Google live smoke dicatat.
5. Gate final dijalankan dari clean clone.
6. Repo sudah di-rename.
7. Tidak ada commit yang belum di-review.

---

## 19. Open Questions dan Asumsi yang Harus Dikonfirmasi

Semua asumsi berikut harus ditutup sebelum Fase 0 selesai. Bila tidak, Fase 0 tidak boleh lulus.

Status per 2026-11-14: A1, A5, dan A25 sudah dikonfirmasi. A2-A4 dan A6-A24 ditutup dengan default plan melalui ADR 0001. Tidak ada asumsi yang masih menjadi gate F0.

| ID | Asumsi | Default bila tidak dijawab | Dampak bila salah |
| --- | --- | --- | --- |
| A1 | ID slide ditulis eksplisit (`s03`) dan tidak di-renumber saat reorder. Konsekuensi: urutan ID tidak lagi mencerminkan urutan tampil; validator menolak duplikat; mengganti ID memerlukan migrasi key. | ID wajib dan stabil. | Key berubah saat reorder, sync salah. |
| A2 | Preset layout memiliki rows internal; hanya `custom` memakai `rows` eksplisit. | Pakai model plan 6.4. | Schema dan layout engine harus diubah besar. |
| A3 | Sync Google diekspos sebagai `build --target slides --sync` dengan mode `push`, `pull`, `diff`, dan `apply`. | Pakai `--sync`. | Perlu command/flag baru dan docs ulang. |
| A4 | Format output, state, cache, dan review mengikuti Bagian 10.4. | Pakai usulan. | Docs, tests, dan perilaku user berubah. |
| A5 | `hitam` memakai palet `hitam` deck-studio: kanvas terang, aksen hitam `#111827`, cover gradient `#111827` → `#0B1220` → `#000000`. Warna chart memakai `chartSeries` turunan yang lolos 3:1. Bukan dark theme dan bukan palet `malam`. | Pakai palet `hitam` deck-studio untuk aksen/cover dan `chartSeries` untuk chart. | Visual, kontras, dan acceptance berubah. |
| A6 | Font TTF Plus Jakarta Sans Regular/SemiBold/Bold/ExtraBold dibundel dan ditanam di PPTX. Italic tidak didukung v1. | Pakai 4 weight tanpa italic. | Ukuran file, layout, dan font fallback berubah. |
| A7 | Gambar input `.png`, `.jpg`, `.jpeg`, `.webp`; WebP dikonversi ke PNG. SVG tidak diterima. | Pakai daftar ini. | Perlu converter atau dukungan format baru. |
| A8 | Slides memakai staging PPTX dengan placeholder shape, bukan native chart yang diganti. | Pakai staging placeholder. | Mekanisme replacement dan file staging berubah. |
| A9 | Spreadsheet dan presentasi dimiliki akun OAuth uploader; scopes `drive.file`, `presentations`, `spreadsheets`. | Pakai scopes ini. | Consent, akses file, dan state berubah. |
| A10 | Sinkronisasi teks mencakup teks slide, table cell, notes, dan source; tidak mencakup chart data, image, diagram, atau format kaya. | Pakai cakupan ini. | Ekspektasi user dan apply berubah. |
| A11 | Layout deck-studio yang tidak didukung v1: `image-annotated`, `image-figure`, `table-long`. | Keluarkan dari v1. | Acceptance dan katalog berubah. |
| A12 | Flag lama docgen `--no-manifest`, `--no-adeu`, `--allow-missing-word` tidak dipertahankan; hanya perilaku dokumen, output, `--terms`, dan `--keep-intermediate` yang dipertahankan. | Hapus flag lama. | Perlu tambahan flag/contracts dan docs. |
| A13 | Coverage 100% line dan branch dengan exclusion hanya `TYPE_CHECKING`, `@overload`, dan daftar tertulis. | Pakai definisi ini. | Gate bisa terlalu ketat atau terlalu longgar. |
| A14 | `background` adalah layout naratif konteks dengan tiga poin, bukan preview resep latar deck-studio. | Pakai definisi 6.2. | Layout dan fixture berubah. |
| A15 | Setiap push Slides membuat presentasi baru dan menyimpan ID aktif; presentasi lama tidak dihapus otomatis. | Pakai perilaku ini. | Perlu update in-place atau strategi cleanup. |
| A16 | `source` hanya di level slide, bukan per block. | Pakai level slide. | Schema block dan key berubah. |
| A17 | Nama field dan slot di Bagian 4 dan 6 adalah draft yang dibekukan di Fase 0. | Bekukan apa adanya. | Perubahan setelah Fase 0 memerlukan ADR dan rebase lane. |
| A18 | Mypy exact flags dan import-linter contracts dibekukan di Fase 0 setelah audit stub. | Pakai baseline Bagian 12.4. | Gate mypy/import bisa berubah. |
| A19 | Apply sync menulis YAML baru `.autooffice/review/<stem>.applied.yaml`, tidak menimpa sumber. | Pakai file baru. | Perilaku user dan alat review berubah. |
| A20 | `source.url` adalah hyperlink dan bukan key teks. | Pakai hyperlink. | Coverage dan sync berubah. |
| A21 | `table` memakai header native baris pertama dan tidak mendukung merged cell. | Pakai header native. | Layout table dan extraction berubah. |
| A22 | `review` dan `state` tidak di-track Git; `.autooffice/**` di-ignore. | Pakai ignore. | Risiko membocorkan state/token. |
| A23 | Repo `deck-studio` diarsipkan/dihapus setelah porting; repo `docgen` di-rename menjadi `autooffice`. | Pakai urutan ini. | Sejarah repo dan remote berubah. |
| A24 | Dokumen migrasi ini boleh tetap sebagai dokumen historis meskipun memuat nama lama; larangan referensi lama berlaku untuk runtime, package, README, dan docs user. | Pakai pengecualian historis. | No-legacy checker dan docs checker perlu aturan khusus. |
| A25 | Chart memakai maksimal empat slot warna (seri untuk `bar`/`line`, kategori untuk `donut`) dan palet turunan `chartSeries` empat warna yang lolos kontras 3:1: `hitam` `#111827`/`#374151`/`#4B5563`/`#6B7280`, `indigo` `#4F46E5`/`#0F766E`/`#B45309`/`#BE123C`. Palet aksen dan cover tetap persis `themes.json`. Berlaku untuk semua theme. | Pakai batas empat slot dan palet chart-safe. | Schema, validasi, kontras, dan acceptance chart berubah. |

### 19.1 Pertanyaan yang Wajib Dijawab Sebelum F0 Lulus

Pertanyaan 2-4 dan 6-24 ditutup dengan default plan melalui ADR 0001.

1. Apakah ID slide wajib eksplisit dan tidak di-renumber? (A1) (sudah dikonfirmasi)
2. Apakah preset layout memiliki rows internal, atau semua layout harus memakai rows? (A2)
3. Apakah `--sync` adalah surface resmi pull/diff/apply? (A3)
4. Apakah output naming dan state Bagian 10.4 disetujui? (A4)
5. Apakah `hitam` memakai palet `hitam` deck-studio (kanvas terang, aksen hitam)? (A5) (sudah dikonfirmasi)
6. Apakah font TTF dan daftar weight disetujui? (A6)
7. Apakah WebP didukung dengan konversi dan SVG ditolak? (A7)
8. Apakah mekanisme staging placeholder chart disetujui? (A8)
9. Apakah scopes dan ownership Google disetujui? (A9)
10. Apakah cakupan sync teks disetujui? (A10)
11. Apakah tiga layout deck-studio yang dihapus disetujui? (A11)
12. Apakah flag lama docgen boleh dihapus? (A12)
13. Apakah definisi coverage 100% disetujui? (A13)
14. Apakah semantik `background` disetujui? (A14)
15. Apakah presentasi baru per push disetujui? (A15)
16. Apakah `source` level slide disetujui? (A16)
17. Apakah draft schema/slot dibekukan apa adanya? (A17)
18. Apakah baseline mypy/import-linter disetujui? (A18)
19. Apakah apply menulis file baru? (A19)
20. Apakah `source.url` bukan key? (A20)
21. Apakah table memakai header native? (A21)
22. Apakah `.autooffice/**` di-ignore? (A22)
23. Apakah urutan rename/arsip repo disetujui? (A23)
24. Apakah dokumen migrasi ini dikecualikan dari no-legacy checker? (A24)
25. Apakah batas empat slot warna dan palet chart-safe `chartSeries` disetujui? (A25) (sudah dikonfirmasi)

### 19.2 Aturan Penutupan Asumsi

- Setiap jawaban dicatat di `docs/decisions/` sebagai ADR.
- Plan ini diperbarui bila jawaban mengubah kontrak.
- Lane tidak boleh mulai sebelum asumsi yang menjadi dependency-nya ditutup.
- Bila pemilik tidak menjawab, default plan dipakai dan dicatat sebagai keputusan sementara. Keputusan sementara tidak boleh menjadi alasan untuk melewati gate.
- Asumsi yang memengaruhi acceptance tidak boleh diselesaikan hanya dengan asumsi implisit.

---

## Lampiran A: Ringkasan Perubahan dari Repo Saat Ini

| Area | docgen | deck-studio | AutoOffice |
| --- | --- | --- | --- |
| Bahasa | Python | Node/JS | Python |
| Input | Markdown | JSON | Markdown dan YAML |
| Output | DOCX/PDF | HTML/PPTX/Slides | DOCX/PPTX/PDF/Slides |
| Renderer visual | Word | HTML/Reveal, PptxGenJS | python-pptx |
| Chart | tidak ada | shape chart | native PPTX, linked Sheets di Slides |
| Desain | format akademik | design system | design system deck + format docgen terpisah |
| Sync | manifest Adeu | Google Slides | Google Slides + Sheets |
| CLI | `docgen` | `node src/cli.js` | `autooffice` |
| Dokumentasi | docs docgen | docs deck-studio | docs AutoOffice |
| CI | tidak ada | tidak ada | tidak ada; gate lokal |

## Lampiran B: Checklist Review Satu Halaman

Sebelum merge:

- [ ] Lane card lengkap.
- [ ] File ownership tidak overlap.
- [ ] Kontrak tidak berubah tanpa ADR.
- [ ] Targeted test lulus.
- [ ] Diff aktual diperiksa.
- [ ] Coverage tidak turun.
- [ ] Docs diperbarui.
- [ ] Tidak ada workaround.
- [ ] Tidak ada nama lama baru.
- [ ] Tidak ada file generated yang di-commit tanpa alasan.

Sebelum final:

- [ ] Semua asumsi ditutup.
- [ ] Semua lane merged.
- [ ] Semua acceptance lulus.
- [ ] Kode lama dihapus.
- [ ] Repo di-rename.
- [ ] Clean clone lulus.
- [ ] Gate penuh lulus.
- [ ] Tidak ada commit, push, atau approval yang dilakukan oleh worker tanpa instruksi.
