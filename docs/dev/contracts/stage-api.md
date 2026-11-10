# Kontrak Stage API (P0.2)

**Status:** beku untuk Fase 0.
**Ruang lingkup:** protokol `Stage.run(ctx)`, urutan kanonik, pipeline,
lifecycle workspace, dan CLI `docgen`.
**Pemilik kontrak:** WS0. **Pemilik implementasi:** WS2 (pipeline Fase 1),
WS15 (pipeline Fase 3), lane stage masing-masing.
**Rujukan:** `docs/dev/archive/restructure-plan.md` v0.13, bagian P0.2, 2.2, 2.4, 2.5,
WS2, WS15, dan 14.

## Daftar isi

- [1. Prinsip](#1-prinsip)
- [2. Protokol `Stage`](#2-protokol-stage)
- [3. Urutan kanonik](#3-urutan-kanonik)
- [4. `StageContext`](#4-stagecontext)
- [5. Daftar stage dan tanggung jawab](#5-daftar-stage-dan-tanggung-jawab)
- [6. Pipeline](#6-pipeline)
- [7. Error](#7-error)
- [8. Idempotensi](#8-idempotensi)
- [9. Logging](#9-logging)
- [10. Side effect](#10-side-effect)
- [11. CLI contract](#11-cli-contract)
- [12. Acceptance](#12-acceptance)

## 1. Prinsip

- Satu orchestrator: `docgen.pipeline.Pipeline`.
- Satu urutan kanonik; stage tidak boleh mengubah urutan.
- Satu `DocumentPackage` untuk seluruh postprocess.
- Stage hanya mengedit file miliknya; `pipeline.py` hanya dimiliki WS2
  (Fase 1) lalu WS15 (Fase 3).
- Stage tidak memanggil stage lain. Orchestrasi hanya di `pipeline.py`.
- Stage tidak menulis ke folder konten selain output, workspace, dan
  `.laporan/`.
- Semua stage wajib idempoten atau mendeklarasikan pengecualiannya.

---

## 2. Protokol `Stage`

```python
class BaseStage(ABC):
    name: ClassVar[str]
    order: ClassVar[int]
    requires: ClassVar[tuple[str, ...]] = ()
    mutates: ClassVar[frozenset[str]] = frozenset()
    idempotent: ClassVar[bool] = True

    def enabled(self, ctx: "StageContext") -> bool:
        return True

    @abstractmethod
    def run(self, ctx: "StageContext") -> "StageResult":
        ...
```

Kontrak stage ditegakkan oleh `BaseStage`. Pipeline hanya memanggil
`Stage.run(ctx)`, dan semua stage nyata wajib mewarisi `BaseStage` agar
`pipeline.py` dapat memeriksa metadata tanpa menjalankan stage.

### 2.1 Aturan metadata

| Atribut | Arti | Validasi |
|---|---|---|
| `name` | ID stage, unik | Harus salah satu `StageName` di 2.2 |
| `order` | Urutan eksekusi | Unik, naik, sesuai 3.1 |
| `requires` | Stage yang harus sudah selesai | Harus prefix dari urutan kanonik |
| `mutates` | Part DOCX yang boleh berubah | Harus subset part yang dikenal |
| `idempotent` | Stage aman dijalankan dua kali | `False` hanya untuk office/pdf |
| `enabled(ctx)` | Stage aktif untuk opsi ini | Tidak boleh mengubah urutan |

### 2.2 `StageName`

```python
class StageName(StrEnum):
    VALIDATE = "validate"
    MERMAID = "mermaid"
    STYLE_REFERENCE = "style_reference"
    FRONT_MATTER = "front_matter"
    PANDOC = "pandoc"
    SECTIONS = "sections"
    CODE = "code"
    CAPTIONS = "captions"
    NORMALIZE = "normalize"
    EQUATIONS = "equations"
    NUMBERING = "numbering"
    BLANK_LINES = "blank_lines"
    TERMS = "terms"
    TOC = "toc"
    PAGE_NUMBERS = "page_numbers"
    LISTS = "lists"
    OFFICE = "office"
    PDF = "pdf"
```

Nama modul `stages/captions.py`; nama stage publik
`captions` mengikuti daftar kanonik.

### 2.3 `StageResult`

```python
@dataclass(frozen=True)
class StageResult:
    stage: str
    status: Literal["ok", "skipped"]
    changed: bool
    duration_ms: int
    metrics: Mapping[str, int | float | str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    artifacts: tuple[Path, ...] = ()
```

- `status="skipped"` hanya untuk stage yang `enabled(ctx)` false (mis. `terms`
  tanpa `--terms` atau `toc: false`) atau precondition opsional tidak ada.
- Error tidak dikembalikan sebagai `StageResult`; error dilempar sebagai
  `StageError`.
- `changed=False` wajib benar untuk run kedua stage idempoten.

---

## 3. Urutan kanonik

### 3.1 Daftar lengkap

| # | `order` | Stage | Modul | Pemilik | `mutates` | Idempoten |
|---:|---:|---|---|---|---|---|
| 1 | 10 | `validate` | `stages/validate.py` | WS4 | - | ya |
| 2 | 20 | `mermaid` | `stages/mermaid.py` | WS9 | workspace | ya (cache) |
| 3 | 30 | `style_reference` | `stages/style_reference.py` | WS7 | workspace/cache | ya |
| 4 | 35 | `front_matter` | `stages/front_matter.py` | WS6 | workspace | ya |
| 5 | 40 | `pandoc` | `stages/pandoc.py` | WS2 | package baru | semantik |
| 6 | 50 | `sections` | `stages/sections.py` | WS6 | `word/document.xml` | ya |
| 7 | 60 | `code` | `stages/code.py` | WS4 | `word/document.xml` | ya |
| 8 | 70 | `captions` | `stages/captions.py` | WS4 | `word/document.xml` | ya |
| 9 | 80 | `normalize` | `stages/normalize.py` | WS5 | `word/document.xml` | ya |
| 10 | 90 | `equations` | `stages/equations.py` | WS5 | `word/document.xml` | ya |
| 11 | 100 | `numbering` | `stages/numbering.py` | WS5 | `word/document.xml`, `word/numbering.xml` | ya |
| 12 | 110 | `blank_lines` | `stages/blank_lines.py` | WS5 | `word/document.xml` | ya |
| 13 | 120 | `terms` | `stages/terms.py` | WS7 | `word/document.xml`, `word/styles.xml` | ya |
| 14 | 130 | `toc` | `stages/toc.py` | WS6 | `word/document.xml`, `word/styles.xml` | ya |
| 15 | 140 | `page_numbers` | `stages/page_numbers.py` | WS6 | `word/document.xml`, header/footer, rels, content types | ya |
| 16 | 150 | `lists` | `stages/lists.py` | WS11 | `word/document.xml` | ya |
| 17 | 160 | `office` | `stages/office.py` | WS8 | seluruh package | semantik |
| 18 | 170 | `pdf` | `stages/pdf.py` | WS8 | - | semantik |

Urutan teks yang sama:

```text
validate
-> mermaid
-> style_reference
-> front_matter
-> pandoc
-> sections
-> code
-> captions
-> normalize
-> equations
-> numbering
-> blank_lines
-> terms
-> toc
-> page_numbers
-> lists
-> office
-> pdf
```

### 3.2 Guard yang wajib ditegakkan

`pipeline.py` wajib gagal dengan `StageOrderError` jika salah satu kondisi
berikut tidak benar:

1. `style_reference` sebelum `front_matter` sebelum `pandoc`.
2. `sections` sebelum `code` sebelum `captions` sebelum `normalize`.
3. `normalize` sebelum `equations` sebelum `blank_lines`.
4. `terms` sebelum `toc` sebelum `page_numbers` sebelum `lists`.
5. `office` sebelum `pdf`.
6. Semua stage kanonik ada tepat satu kali; tidak ada stage tambahan.
7. `requires` setiap stage adalah prefix dari urutan kanonik.

Guard ini tidak boleh diserahkan ke stage. Stage tidak boleh mengubah urutan
atau memanggil stage lain.

### 3.3 Alasan urutan

- `validate` pertama: tidak ada build yang dimulai dengan input tidak valid.
- `mermaid` sebelum `pandoc`: gambar harus sudah ada saat Pandoc membaca
  Markdown.
- `style_reference` sebelum `pandoc`: `--reference-doc` harus derived dari
  `format.yml`, bukan `reference.docx` source.
- `front_matter` sebelum `pandoc`: cover, template legal, abstract, dan
  penomoran heading harus sudah materialized di Markdown sebelum konversi.
- `sections` sebelum `code`/`captions`: heading, section, dan nomor bab harus
  stabil sebelum caption dan tabel kode diproses.
- `code` sebelum `captions`: tabel kode harus sudah berbentuk tabel
  1x1 agar tidak dianggap tabel data dan tidak diberi caption.
- `captions` sebelum `normalize`: caption dan gambar diberi format
  langsung, lalu layout paragraf dinormalisasi.
- `normalize` sebelum `equations`: spacing/justify direset lebih dulu;
  equations menulis spacing final.
- `equations` sebelum `numbering`: nomor persamaan tidak boleh dianggap
  list.
- `numbering` sebelum `blank_lines`: indentasi list stabil sebelum paragraf
  kosong disisipkan.
- `blank_lines` sebelum `terms`: italic istilah dapat mengubah lebar teks;
  jarak fisik sudah final.
- `terms` sebelum `toc`/`page_numbers`: italic memengaruhi paginasi dan
  nomor halaman.
- `toc` sebelum `page_numbers`: field TOC dan PAGEREF sudah ada sebelum
  format nomor halaman.
- `page_numbers` sebelum `lists`: section Romawi/Arab sudah final.
- `lists` sebelum `office`: field daftar gambar/tabel siap diperbarui Word.
- `office` sebelum `pdf`: PDF diekspor dari DOCX final Word.

### 3.4 Ownership file di luar stage

| File/area | Pemilik | Aturan |
|---|---|---|
| `src/docgen/pipeline.py` | WS2 Fase 1; WS15 Fase 3 | Handoff eksplisit; tidak ada editor lain |
| `src/docgen/cli.py` | WS2 | Hanya WS2 mendaftarkan command |
| `src/docgen/config.py`, `document.py`, `metadata.py`, `assets.py`, `errors.py`, `paths.py` | WS2 | Loader dan model inti |
| `src/docgen/docx/**` | WS3/WS4/WS5/WS6/WS7/WS10 | Lihat `docs/dev/contracts/docx-api.md` |
| `src/docgen/adeu/**` | WS10 | Manifest, paragraph ID, reconcile |
| `scripts/word.ps1` | WS8 | Satu adapter Word; aset repo-local, bukan package-data wheel |
| `tests/_helpers`, `tests/factories`, `tests/packaging`, `tests/e2e`, harness `tests/integration` | WS12 | Shared infrastructure |
| Tes domain per lane | lane masing-masing | Sesuai tabel plan v0.13 |

---

## 4. `StageContext`

```python
@dataclass
class BuildOptions:
    target: Literal["docx", "pdf", "both"] = "both"
    keep: bool = False
    terms: bool = False
    manifest: bool = True
    adeu: bool = True
    allow_missing_word: bool = False

@dataclass
class StageContext:
    document: Document
    structure: Structure
    format: Format
    options: BuildOptions

    repo_root: Path
    package_root: Path
    output_dir: Path
    workspace: Workspace

    package: DocumentPackage | None
    artifacts: ArtifactStore
    logger: logging.LoggerAdapter
    report: BuildReport

    reference_docx: Path | None
    glossary: Glossary | None
    word: WordAdapter | None
    pandoc: PandocAdapter | None

    dry_run: bool = False
```

### 4.1 Field

| Field | Tipe | Diisi oleh | Mutasi |
|---|---|---|---|
| `document` | `Document` | `document.py` | immutable |
| `structure` | `Structure` | `config.py` | immutable |
| `format` | `Format` | `config.py` | immutable |
| `options` | `BuildOptions` | CLI | immutable |
| `repo_root` | `Path` | pipeline | immutable |
| `package_root` | `Path` | pipeline | immutable |
| `output_dir` | `Path` | pipeline | immutable |
| `workspace` | `Workspace` | pipeline | lifecycle |
| `package` | `DocumentPackage \| None` | pandoc | hanya pandoc boleh set |
| `artifacts` | `ArtifactStore` | pipeline/stage | mutable |
| `logger` | `LoggerAdapter` | pipeline | immutable |
| `report` | `BuildReport` | pipeline | mutable |
| `reference_docx` | `Path \| None` | style_reference | immutable setelah set |
| `glossary` | `Glossary \| None` | pipeline | immutable |
| `word` | `WordAdapter \| None` | pipeline | immutable |
| `pandoc` | `PandocAdapter \| None` | pipeline | immutable |

Aturan:

- Sebelum `pandoc`, `ctx.package is None`.
- `pandoc` menetapkan `ctx.package` tepat satu kali.
- Stage setelah `pandoc` tidak boleh mengganti objek package; hanya
  memutasi isinya.
- `ctx.document.front_matter` tidak boleh diubah stage.
- `ctx.options` tidak boleh diubah stage.
- Stage boleh menambah artifact dengan nama unik; artifact lama tidak
  ditimpa tanpa deklarasi.

### 4.2 `Workspace`

```python
@dataclass
class Workspace:
    root: Path                  # <document.parent>/.laporan-build
    keep: bool

    def ensure(self) -> Path: ...
    def path(self, name: str) -> Path: ...
    def intermediate(self, name: str) -> Path: ...
    def cleanup(self) -> None: ...
```

- `ensure()` hanya membuat direktori saat benar-benar dibutuhkan
  (Mermaid, intermediate DOCX, cache).
- Tanpa `--keep`, `cleanup()` menghapus seluruh workspace di `finally`,
  termasuk saat build gagal.
- Dengan `--keep`, workspace dipertahankan dan path-nya dicetak.
- Intermediate DOCX hanya disimpan jika `--keep`; tanpa `--keep`, file
  antara dihapus dan tidak ada intermediate DOCX di output.
- Workspace tidak boleh berada di luar direktori dokumen.

### 4.3 `ArtifactStore`

```python
class ArtifactStore:
    def put(self, key: str, path: Path) -> None: ...
    def get(self, key: str) -> Path: ...
    def require(self, key: str) -> Path: ...
    def keys(self) -> tuple[str, ...]: ...
```

Key baku: `markdown`, `reference_docx`, `pandoc_docx`, `manifest`,
`terms_review`, `docx`, `pdf`. Key berprefix nama stage juga sah; kontrak ini
memakai `mermaid.markdown` sebagai input body `front_matter`.

---

## 5. Daftar stage dan tanggung jawab

### 5.1 `validate` (WS4, `stages/validate.py`)

- Memvalidasi front matter `document.md` dan aset yang dirujuk.
- Memvalidasi caption Markdown: tabel wajib punya `: Judul`, gambar wajib
  punya alt text non-kosong.
- Tidak membuka package dan tidak menulis file.
- Error: `ValidationError`, exit 1.

### 5.2 `mermaid` (MermaidStage, WS9, `stages/mermaid.py`)

- Mengekstrak blok `mermaid`, merender dengan `mmdc`, mengganti blok dengan
  gambar di Markdown materialized.
- Cache berdasarkan hash blok + versi `mmdc`; render kedua tidak memanggil
  `mmdc`.
- Stage selalu `status="ok"` dan selalu menulis `mermaid.md` serta memasang
  artifact `mermaid.markdown`, termasuk bila tidak ada diagram. Metrik
  `blocks=0` dan Markdown disalin tanpa perubahan.
- Jika `mmdc` hilang, `ToolMissingError` dengan pesan instalasi.
- Menulis hanya ke workspace/cache.

### 5.3 `style_reference` (WS7, `stages/style_reference.py`)

- Membaca `format.yml` dan `assets.reference_docx`.
- Menghasilkan derived `reference.docx` di workspace/cache.
- Wajib berjalan **sebelum** `front_matter` dan `pandoc`.
- File source tidak pernah ditimpa.
- Deterministik: input format sama -> payload derived sama.
- Error: `StyleError`; exit 1.

### 5.4 `front_matter` (FrontMatterStage, WS6, `stages/front_matter.py`)

- Input **wajib** artifact `mermaid.markdown` dari stage `mermaid`. Body tidak
  dibaca dari `ctx.document.body`, dan artifact `markdown` lama tidak diterima
  sebagai sumber. Artifact yang tidak ada atau tidak terbaca menghasilkan
  `FrontMatterError` berkode `FRONT-MATTER-INPUT`; tidak ada fallback.
- Mematerialisasi cover, template legal approval/statement, preface, abstract
  ID/EN, dan kata kunci menjadi Markdown sebelum Pandoc.
- Menomori Heading 1/2/3 body; `# Lampiran` dan turunannya tetap unnumbered
  karena mengikuti `structure.back_matter.appendices`.
- Menulis page break/section break front matter ke workspace.
- TOC dan daftar tabel/gambar **tidak** ditulis di sini; keduanya milik stage
  post-Pandoc.
- Output: `front_matter.md` di workspace dan artifact `markdown` untuk Pandoc.
- Error: `FrontMatterError`; exit 1.

### 5.5 `pandoc` (WS2, `stages/pandoc.py`)

- Input Markdown **wajib** artifact `markdown` dari `front_matter`. Tidak ada
  fallback ke `workspace/front_matter.md` atau file workspace lain; artifact
  yang tidak ada menghasilkan `PandocError` berkode `PANDOC-INPUT`.
- Menjalankan Pandoc dengan:
  - Markdown materialized dari artifact `markdown` (sudah memuat hasil
    `mermaid` dan `front_matter`);
  - metadata front matter;
  - `--reference-doc` dari `style_reference`;
  - `--citeproc`, `--bibliography`, `--csl`;
  - `--top-level-division=chapter`;
  - output DOCX sementara.
- Memuat hasil ke `DocumentPackage` dan menetapkan `ctx.package`.
- Tidak memakai `docx.lua`; perilaku Lua sudah diport ke stage.
- Error: `PandocError`; exit 1.
- Stub `style_reference` di `stages/pandoc.py` hanya boleh ada selama Fase 1
  dan wajib dihapus WS2 setelah WS7 menyatakan stage siap.

### 5.6 `sections` (WS6, `stages/sections.py`)

- Membangun cover, template approval/statement, preface, abstract.
- Membuat section break, margin, page size, title page.
- Menomori heading H1/H2/H3 sesuai `structure.numbering`.
- Mempertahankan inline formatting heading.
- Tidak menulis TOC; itu milik `toc`.
- Error: `SectionError`, `HeadingError`; exit 1.

### 5.7 `code` (WS4, `stages/code.py`)

- Mendeteksi blok kode berdasarkan style.
- Menggabungkan paragraf kode berurutan menjadi tabel 1x1.
- Menormalisasi tabel kode lama.
- Tidak memberi caption tabel data.
- Error: `TableError`; exit 1.

### 5.8 `captions` (WS4, `stages/captions.py`)

- Memberi nomor caption tabel/gambar per bab.
- Memindahkan caption tabel ke atas dan caption gambar ke bawah.
- Menyisipkan `SEQ Gambar`/`SEQ Tabel` pada caption.
- Menyesuaikan lebar gambar agar tidak melewati teks.
- Menyeragamkan border/margin tabel data.
- Error: `CaptionError`, `TableError`; exit 1.

### 5.9 `normalize` (WS5, `stages/normalize.py`)

- Menyetel spacing before/after 0, line 1.5, justify.
- Menghapus bold langsung body/daftar, tetapi mempertahankan bold field,
  heading, dan `CoverTitle`.
- Mempertahankan tab stop kustom.
- Error: `LayoutError`; exit 1.

### 5.10 `equations` (WS5, `stages/equations.py`)

- Menomori persamaan display OMML `(bab.n)`.
- Menulis nomor sebagai run biasa, bukan `m:t`.
- Tidak mengubah isi OMML.
- Error: `EquationError`; exit 1.

### 5.11 `numbering` (WS5, `stages/numbering.py`)

- Menyeragamkan indentasi, hanging, tab stop daftar.
- Menghapus bold pada run list.
- Tidak mengubah `w:numFmt`/`w:lvlText`.
- Error: `NumberingError`; exit 1.

### 5.12 `blank_lines` (WS5, `stages/blank_lines.py`)

- Menyisipkan paragraf kosong fisik sesuai aturan jarak.
- Tidak memutus `w:ins`/`w:del`.
- H4-H9 tidak mendapat aturan gap baru.
- Error: `BlankLineError`; exit 1.

### 5.13 `terms` (WS7, `stages/terms.py`)

- `enabled(ctx)` hanya jika `ctx.options.terms` true.
- Tanpa `--terms`: `status="skipped"`; tidak ada auto-italic, tidak ada
  gate, tidak ada review file.
- Dengan `--terms`: check Markdown, apply `IstilahAsing`/`IstilahReview`,
  verify, dan tulis `.laporan/istilah-baru.txt`.
- Glosarium package default + override `istilah.tsv` di samping
  `document.md`.
- Error: `GlossaryError`, `TermsError`; exit 1.

### 5.14 `toc` (WS6, `stages/toc.py`)

- Menulis field TOC native di dalam `w:sdt`.
- Menulis `TOCHeading` dan style `TOC1`/`TOC2`/`TOC3`.
- Tidak memperbarui cache field; Word yang melakukannya di `office`.
- `toc: false` -> `status="skipped"`, tidak ada field.
- Error: `FieldError`; exit 1.

### 5.15 `page_numbers` (WS6, `stages/page_numbers.py`)

- Menetapkan Romawi untuk front matter dan Arab untuk body.
- Mengatur header/footer dan field `PAGE`.
- Menghapus `w:updateFields` dari settings setelah field final.
- Error: `SectionError`, `FieldError`; exit 1.

### 5.16 `lists` (WS11, `stages/lists.py`)

- Menulis field `TOC \c "Tabel"` dan `TOC \c "Gambar"`.
- Memakai `docx/fields.py` milik WS6 tanpa mengedit modul tersebut.
- Caption `SEQ` sudah disisipkan `captions`.
- Gate `SEQ` diputuskan sebelum implementasi; fallback daftar statis harus
  tercatat di ADR.
- Error: `FieldError`; exit 1.

### 5.17 `office` (WS8, `stages/office.py`)

- Membuka DOCX final dengan Microsoft Word.
- Memperbarui seluruh field dan TOC; `Repaginate()`.
- Menyimpan DOCX.
- Gagal Word berarti error dan exit nonzero, bukan warning.
- Di Windows, stage aktif jika Word tersedia.
- Di Debian, stage `skipped` dengan warning; DOCX tetap dihasilkan.
- Jika target hanya `docx` dan Word tidak tersedia, stage `skipped` dengan
  warning; DOCX tetap dihasilkan dan exit 0.
- Jika target mencakup PDF dan Word tidak tersedia:
  - tanpa `--allow-missing-word`: `ToolMissingError`, exit 1;
  - dengan `--allow-missing-word`: PDF dilewati, DOCX tetap, exit 0
    (kecuali `--target pdf` saja; lihat 5.17).
- Error: `WordError`; exit 1.

### 5.18 `pdf` (WS8, `stages/pdf.py`)

- Mengekspor DOCX final ke PDF memakai Word.
- Hanya Word; tidak ada LibreOffice, `soffice`, atau Poppler.
- `enabled(ctx)` hanya jika target `pdf` atau `both`.
- Jika Word tidak tersedia dan `--allow-missing-word` tidak diberikan:
  `ToolMissingError`, exit 1.
- Jika Word tidak tersedia, `--allow-missing-word` diberikan, dan target
  `both`: PDF `status="skipped"`, DOCX tetap dihasilkan, exit 0.
- Jika `--target pdf` saja dan Word tidak tersedia: selalu exit 1, karena
  tidak ada output yang bisa dihasilkan, termasuk dengan
  `--allow-missing-word`.
- Error: `PdfError`; exit 1.
- `scripts/word.ps1` adalah aset repo-local, bukan package-data wheel.
  `pyproject.toml` hanya memuat `docgen/data/**/*`; skrip ini ditemukan dari
  root repo. Standalone wheel memerlukan keputusan packaging terpisah dan
  tidak dijanjikan oleh kontrak ini.

---

## 6. Pipeline

```python
class Pipeline:
    def __init__(self, stages: Sequence[type[BaseStage]] | None = None): ...
    def run(self, document_path: str | Path,
            options: BuildOptions) -> BuildResult: ...
```

### 6.1 Langkah

1. Parse `document.md` dan validasi front matter.
2. Muat `format` dan `structure`.
3. Susun `StageContext`.
4. Jalankan stage sesuai urutan kanonik:
   - panggil `enabled(ctx)`; jika false, catat `skipped`;
   - panggil `run(ctx)`;
   - catat `StageResult` di `BuildReport`;
   - bila `changed`, perbarui invariant counters.
5. Setelah `lists`, jalankan Adeu hook (lihat 6.3).
6. Simpan package satu kali.
7. Jalankan `office`.
8. Jalankan `pdf` jika diminta.
9. Tulis output ke samping `document.md` secara atomic.
10. Tulis manifest dan review file bila diaktifkan.
11. Cleanup workspace di `finally` kecuali `--keep`.

### 6.2 `BuildResult`

```python
@dataclass(frozen=True)
class BuildResult:
    document: Path
    docx: Path | None
    pdf: Path | None
    manifest: Path | None
    warnings: tuple[str, ...]
    stages: tuple[StageResult, ...]
    kept_workspace: Path | None
```

### 6.3 Adeu hook (bukan stage kanonik)

Plan v0.13 tidak memasukkan Adeu ke daftar stage kanonik, tetapi build target
tetap menulis bookmark `pNNNN` dan manifest default. Kontrak menempatkan
Adeu sebagai hook di dalam pass package yang sama:

- Setelah `lists`, sebelum `save`:
  - `adeu/paragraph_ids.py` memanggil `docx/bookmarks.py`
    (`add_paragraph_ids`);
  - data manifest disiapkan di memori.
- Setelah `save`:
  - `adeu/manifest.py` menulis `.laporan/manifest.json` secara
    atomic.
- `office` berjalan setelah manifest; Word wajib mempertahankan bookmark.
  Pipeline memverifikasi bookmark masih ada setelah `office`; jika hilang,
  `BookmarkError`.
- `--no-manifest`: bookmark tetap ditambahkan; manifest dan source scan
  dimatikan.
- `--no-adeu`: bookmark, manifest, dan source scan dimatikan.
- Manifest deterministik: tanpa `built_at`, urutan paragraf stabil, dan
  `text_sha256` dihitung dari teks final yang terlihat.

Karena hook ini berada di dalam pass package, aturan satu load/save tetap
berlaku.

### 6.4 Satu load/save

- `pipeline.py` memanggil `DocumentPackage.load` tepat satu kali setelah
  Pandoc.
- `pipeline.py` memanggil `DocumentPackage.save` tepat satu kali setelah
  Adeu hook.
- Stage tidak boleh memanggil `load`/`save` target.
- `style_reference` boleh memuat/menyimpan `reference.docx` karena objeknya
  berbeda.
- `tests/integration/test_pipeline_python.py` dan
  `tests/integration/test_thesis_pipeline.py` menghitung panggilan
  `load`/`save` package target dan gagal jika lebih dari satu.

---

## 7. Error

### 7.1 Hierarki

```python
class DocgenError(Exception):
    exit_code: int = 1

class ConfigError(DocgenError): ...
class DocumentError(DocgenError): ...
class ValidationError(DocgenError): ...
class StageError(DocgenError):
    stage: str
    cause: BaseException | None
class StageOrderError(DocgenError): ...
class ToolMissingError(DocgenError):
    tool: str
class ExternalToolError(DocgenError): ...
class WordError(ExternalToolError): ...
class PdfError(ExternalToolError): ...
class IdempotencyError(DocgenError): ...
class OutputError(DocgenError): ...
class ManifestError(DocgenError): ...
class ReconcileError(DocgenError): ...
```

### 7.2 Aturan

- Stage hanya melempar subclass `DocgenError`; exception tak dikenal
  dibungkus `StageError`.
- `StageError` wajib memuat nama stage, path dokumen, dan cause.
- Error tidak boleh ditelan menjadi warning, kecuali dinyatakan eksplisit
  (`--allow-missing-word`).
- Error Word/PDF adalah fatal dan exit nonzero.
- `--terms` gate adalah fatal; tanpa `--terms` stage tidak berjalan.
- Pesan error menyebut tindakan perbaikan.

### 7.3 Pemetaan exit

| Exit | Arti |
|---:|---|
| 0 | Sukses; untuk `reconcile` berarti tidak ada perubahan |
| 1 | Error input, konfigurasi, stage, tool, output, atau Word/PDF |
| 2 | Kesalahan pemakaian CLI (argparse) |
| 3 | `reconcile`: ada perubahan manual yang perlu ditinjau |
| 4 | `reconcile`: ada pelanggaran paragraf terlindungi |
| 130 | Dibatalkan pengguna (`KeyboardInterrupt`) |

---

## 8. Idempotensi

### 8.1 Definisi

Stage idempoten jika:

```text
run(input) -> output1
run(output1) -> output2
sha256_c14n(output1.document_xml) == sha256_c14n(output2.document_xml)
bytes(output1.part) == bytes(output2.part) untuk semua part non-target
```

Untuk stage yang tidak memutasi package, idempotensi berarti artifact dan
output tidak berubah.

### 8.2 Matriks

| Stage | Idempoten | Catatan |
|---|---|---|
| `validate` | ya | Tidak menulis |
| `mermaid` | ya | Cache hash + versi |
| `style_reference` | ya | Deterministik dari format |
| `front_matter` | ya | Artifact Markdown deterministik |
| `pandoc` | semantik | Versi Pandoc sama; metadata sama |
| `sections` | ya | Tidak menambah section ganda |
| `code` | ya | Tabel kode dinormalisasi |
| `captions` | ya | Prefix lama dihapus |
| `normalize` | ya | Nilai akhir sama |
| `equations` | ya | Nomor diganti |
| `numbering` | ya | Indent/tab sama |
| `blank_lines` | ya | Tidak menambah paragraf ganda |
| `terms` | ya | Span/style stabil |
| `toc` | ya | Field diganti, bukan ditambah |
| `page_numbers` | ya | Format section stabil |
| `lists` | ya | Field diganti, bukan ditambah |
| Adeu hook | ya | Bookmark/ID stabil |
| `office` | semantik | Word boleh menulis ulang package |
| `pdf` | semantik | PDF tidak dijamin byte-identik |

Stage yang gagal idempotensi adalah bug dan harus menggagalkan tes
idempotensi per stage. Tes aktual tersebar di `tests/unit/test_stages_code.py`,
`test_stages_captions.py`, `test_stages_layout.py`,
`test_stages_equations.py`, `test_stages_numbering.py`, `test_toc.py`,
`test_lists.py`, `test_front_matter.py`, dan `test_adeu_paragraph_ids.py`.

---

## 9. Logging

- Logger pipeline: `docgen.pipeline`.
- Logger stage: `docgen.stage.<name>`.
- Stage tidak boleh memakai `print`; stdout/stderr hanya milik CLI.
- Level:
  - `INFO`: mulai/selesai stage, ringkasan metrik, path output;
  - `WARNING`: fallback yang diizinkan, stage skipped, Word tidak tersedia;
  - `ERROR`: error fatal;
  - `DEBUG`: hitungan XML, part yang berubah, detail matching.
- Format pesan stabil dan tidak mengandung timestamp di manifest/artifact.
- Setiap stage mencatat `duration_ms`, `changed`, dan metrik utama.
- Log tidak boleh memuat seluruh isi dokumen atau data pribadi.

---

## 10. Side effect

### 10.1 Boleh ditulis

| Lokasi | Penulis | Isi |
|---|---|---|
| `<document.parent>/.laporan-build/` | pipeline/stage | Workspace sementara |
| `<document.parent>/<report_name>.docx` | pipeline | Output DOCX (kecuali contoh, lihat 11.4) |
| `<document.parent>/<report_name>.pdf` | pipeline | Output PDF (kecuali contoh, lihat 11.4) |
| `<document.parent>/.laporan/manifest.json` | Adeu | Manifest default |
| `<document.parent>/.laporan/istilah-baru.txt` | `terms` | Review istilah |
| `<document.parent>/.laporan/reconcile.md` | `reconcile` | Laporan rekonsiliasi |

### 10.2 Dilarang ditulis

- `document.md`, `references.bib`, gambar, dan aset konten lain.
- `src/docgen/data/**` (format, struktur, glosarium package).
- `reference.docx` source.
- File di luar direktori dokumen, kecuali cache sistem yang dikelola
  pipeline dan dibersihkan.
- File sementara Pandoc di luar workspace harus dibersihkan oleh adapter.

### 10.3 Output atomic

- DOCX/PDF ditulis ke file sementara di direktori tujuan, lalu
  `os.replace`.
- Manifest dan review file memakai pola yang sama.
- Kegagalan tidak boleh meninggalkan output setengah jadi.

### 10.4 `--keep`

- Default `false`.
- Tanpa `--keep`: workspace dihapus di `finally`; tidak ada intermediate
  DOCX.
- Dengan `--keep`: workspace `.laporan-build/` dan intermediate DOCX
  dipertahankan; path dicetak.
- `--keep` tidak mengubah isi output final.

---

## 11. CLI contract

### 11.1 Perintah

```text
docgen check <file>
docgen build <file> [opsi]
docgen doctor
docgen reconcile <file>
```

Global: `docgen --version` mencetak versi dan exit 0.

### 11.3 `docgen check`

```text
docgen check <file>
```

- Memvalidasi front matter, format, struktur, template, aset, body/chapter,
  caption Markdown, dan bibliografi.
- Tidak menjalankan Pandoc/Word dan tidak menulis file.
- Exit 0 valid; 1 tidak valid; 2 usage.

### 11.4 `docgen build`

```text
docgen build <file>
  [--target docx|pdf|both]
  [--keep]
  [--terms]
  [--no-manifest]
  [--no-adeu]
  [--allow-missing-word]
```

| Flag | Default | Arti |
|---|---|---|
| `--target` | `both` | `docx`, `pdf`, atau `both` |
| `--keep` | `false` | Pertahankan `.laporan-build/` dan intermediate DOCX |
| `--terms` | `false` | Aktifkan check + apply + verify + gate istilah |
| `--no-manifest` | `false` | Matikan manifest dan source scan |
| `--no-adeu` | `false` | Matikan bookmark + manifest + source scan |
| `--allow-missing-word` | `false` | Izinkan PDF dilewati jika Word tidak ada |

Aturan `--target`:

- `docx`: hanya DOCX; Word tidak wajib.
- `pdf`: hanya PDF; Word wajib.
- `both`: DOCX + PDF; di Windows dijalankan berurutan.
- Di Debian/Linux, `both` tidak didukung. Tanpa `--allow-missing-word`,
  build berhenti dengan `ToolMissingError` sebelum output. Dengan
  `--allow-missing-word`, DOCX dihasilkan, PDF dilewati dengan warning,
  exit 0.
- `--target pdf` dengan Word tidak tersedia selalu exit 1, bahkan dengan
  `--allow-missing-word`, karena tidak ada output yang diminta.

Aturan `--keep`:

- Tanpa `--keep`: workspace dan intermediate DOCX dihapus; output tetap di
  samping `document.md`.
- Dengan `--keep`: workspace `.laporan-build/` dan intermediate DOCX
  dipertahankan.
- `--target pdf` tetap membuat DOCX intermediate; hanya disimpan jika
  `--keep`.

Aturan `--terms`:

- Off: tidak ada check istilah, tidak ada auto-italic, tidak ada verify,
  tidak ada review file.
- On: check Markdown, apply, verify, gate; kegagalan exit 1.
- Glosarium: package default + override `istilah.tsv` di samping
  `document.md`; precedence user > package.

Aturan manifest/Adeu:

| Flag | Bookmark `pNNNN` | `.laporan/manifest.json` | Source scan |
|---|---|---|---|
| default | ya | ya | ya |
| `--no-manifest` | ya | tidak | tidak |
| `--no-adeu` | tidak | tidak | tidak |
| `--no-manifest --no-adeu` | tidak | tidak | tidak |

`--no-adeu` menyiratkan `--no-manifest`. `--no-manifest` tidak mematikan
bookmark.

Output:

- `report_name` wajib di front matter; tidak ada nama default. Nilai kosong
  atau whitespace menghasilkan `CFG-REQUIRED`.
- DOCX dan PDF memakai stem yang sama: `<report_name>.docx` dan
  `<report_name>.pdf`.
- Tidak ada flag CLI `--report-name`.
- Untuk dokumen pengguna, output ditulis di samping `document.md`.
- Untuk dokumen di `examples/<name>/document.md`, output ditulis ke
  `examples/<name>/out/` dan direktori `out/` dibuat bila belum ada.
  Direktori ini di-ignore oleh Git.
- Tidak ada output di `build/` atau `review/`.

### 11.5 `docgen doctor`

- Memeriksa Python (>=3.15), Pandoc, Word, dan `mmdc`.
- Tidak memeriksa LibreOffice (tidak didukung).
- Exit 0 jika Python dan Pandoc tersedia; 1 jika tidak.
- Word/mmdc yang tidak ada adalah warning dengan status PDF/Mermaid.

### 11.6 `docgen reconcile`

```text
docgen reconcile <file>
  [--docx <path>]
  [--manifest <path>]
  [--out <path>]
```

- `<file>` adalah `document.md`.
- Default `--docx` dihitung oleh `docgen.paths.output_directory()`:
  `examples/<nama>/document.md` -> `<folder>/out/<report_name>.docx`;
  dokumen lain -> `<folder-dokumen>/<report_name>.docx`. `--docx` eksplisit
  selalu menang.
- Jika DOCX tidak ada, `reconcile` melempar `ReconcileError` berkode
  `RECONCILE-INPUT` dengan path yang diharapkan; tidak ada fallback.
- Default `--manifest` = `.laporan/manifest.json` di samping dokumen.
- Default `--out` = `.laporan/reconcile.md`.
- Membaca manifest, DOCX, dan sumber Markdown; menulis laporan Markdown.
- Tidak mengubah DOCX, manifest, atau `document.md`.
- Exit 0 tidak ada perubahan; 3 ada perubahan; 4 pelanggaran paragraf
  terlindungi; 1 error; 2 usage.

### 11.7 Exit code

| Exit | Arti umum | `reconcile` |
|---:|---|---|
| 0 | Sukses | Tidak ada perubahan |
| 1 | Error input/konfigurasi/stage/tool/output | Error |
| 2 | Usage/argparse | Usage |
| 3 | - | Ada perubahan manual |
| 4 | - | Pelanggaran paragraf terlindungi |
| 130 | Dibatalkan pengguna | Dibatalkan |

`check` dan `build` tidak pernah mengembalikan 3/4. `doctor` hanya 0/1
(plus 2 usage).

---

## 12. Acceptance

- `tests/unit/test_pipeline.py`: `StageName` lengkap, urutan kanonik unik dan
  naik, `requires` selalu prefix, guard urutan, dan setiap stage terdaftar
  tepat satu kali.
- `tests/unit/test_stages_layout.py::test_urutan_stage_normalize_equations_numbering_blank_lines`:
  guard `normalize < equations < numbering < blank_lines`.
- `tests/unit/test_pipeline.py` juga memeriksa metadata stage, `mutates`
  subset part, dan penolakan kelas stage tidak lengkap.
- Idempotensi per stage: `tests/unit/test_stages_code.py`,
  `test_stages_captions.py`, `test_stages_layout.py`,
  `test_stages_equations.py`, `test_stages_numbering.py`, `test_toc.py`,
  `test_lists.py`, `test_front_matter.py`, dan `test_adeu_paragraph_ids.py`.
- `tests/unit/test_cli.py`: default `--target both`, `--keep`, `--terms`,
  `--no-manifest`, `--no-adeu`, `--allow-missing-word`, penolakan
  `--report-name`, dan exit code.
- `tests/unit/test_metadata.py`: `report_name` hilang, kosong, atau whitespace
  menghasilkan `CFG-REQUIRED`; `DEFAULT_REPORT_NAME` dan `normalize_author`
  tidak ada.
- `tests/integration/test_pipeline_python.py` dan
  `tests/integration/test_thesis_pipeline.py`: `load`/`save` package target
  masing-masing satu kali, stage dijalankan sesuai urutan, dan stage
  disabled tercatat `skipped`.
- `tests/e2e/test_thesis_e2e.py`: `check` dan `build` contoh tesis; tes
  `reconcile` ada di `tests/unit/test_adeu_reconcile.py`; `doctor` di
  `tests/unit/test_cli.py`.
- Manual Word spike untuk `office`/`pdf`; mock bukan bukti.
