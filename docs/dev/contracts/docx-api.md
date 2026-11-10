# Kontrak API DOCX (P0.2)

**Status:** beku untuk Fase 0.
**Ruang lingkup:** `src/docgen/docx/` dan aturan pemakaiannya oleh stage.
**Pemilik kontrak:** WS0. **Pemilik implementasi:** WS3 (fondasi), WS4, WS5, WS6, WS7, WS10 (helper domain).
**Rujukan:** `docs/dev/archive/restructure-plan.md` v0.13, bagian P0.2, 2.2, WS3, dan Batas ownership.

Kontrak ini menetapkan satu pintu untuk membaca, mengubah, dan menulis DOCX.
Stage tidak boleh memakai `zipfile`, `python-docx`, atau traversal `lxml`
sendiri. Semua perubahan XML melewati `docgen/docx/`.

## 1. Aturan global

### 1.1 Satu package, satu load, satu save

- `pipeline.py` melakukan **satu** `DocumentPackage.load()` untuk dokumen
  target setelah Pandoc.
- Semua stage postprocess (`sections` sampai `lists`) menerima objek
  `DocumentPackage` yang sama dan memutasi isinya di memori.
- `pipeline.py` melakukan **satu** `DocumentPackage.save()` setelah stage
  terakhir yang memutasi package.
- Tidak ada stage yang memanggil `load()` atau `save()` sendiri.
- `style_reference` adalah pengecualian yang sah: ia memuat dan menyimpan
  **reference.docx**, bukan dokumen target. File source tidak ditimpa.
- `office` adalah pengecualian eksternal: Microsoft Word boleh menyimpan
  ulang package. Aturan byte identity tidak berlaku untuk output Word; yang
  berlaku adalah semantic equivalence `document.xml`.

Aturan ini disebut **satu load/save** dan diuji oleh
`tests/integration/test_pipeline_python.py` dan
`tests/integration/test_thesis_pipeline.py`.

### 1.2 Part non-target byte-identik

Untuk setiap stage, stage mendeklarasikan `mutates: frozenset[str]` berisi
nama part yang boleh berubah. Semua part lain wajib memenuhi:

- payload tidak terkompresi (`ZipFile.read(name)`) byte-identik dengan input;
- `ZipInfo` asli dipertahankan: nama, `date_time`, `compress_type`,
  `external_attr`, `create_system`, dan komentar;
- tidak ada part baru, part hilang, atau perubahan `[Content_Types].xml`
  kecuali dideklarasikan.

`word/document.xml` adalah part khusus: perubahan isinya tidak dibandingkan
byte-per-byte, tetapi memakai canonical XML + SHA-256 (lihat 1.3).

### 1.3 `document.xml` semantic-equivalent via c14n + sha256

```text
semantic_equal(a, b) := sha256_c14n(a) == sha256_c14n(b)
```

`canonicalize_xml()` memakai C14N 1.0 tanpa komentar. Profil `docx`
menambahkan normalisasi terbatas untuk artefak non-semantik Word:

- menghapus atribut `w:rsid*`;
- menghapus elemen `w:proofErr`;
- menghapus elemen `w:lastRenderedPageBreak`.

Profil ini dipakai untuk perbandingan golden dan idempotensi. Tidak ada
normalisasi lain. Menambah normalisasi baru wajib mengubah kontrak ini dan
`docs/dev/testing.md`.

Perbandingan dilakukan pada dua tingkat:

1. **Golden**: output pipeline baru vs output baseline P0.1. Part non-target
   byte-identik; `document.xml` `semantic_equal` terhadap golden.
2. **Idempotensi**: hasil run pertama vs run kedua stage yang sama.
   `document.xml` `semantic_equal`; part non-target byte-identik.

### 1.4 Satuan dan tipe

API DOCX tidak menerima string `"4cm"` atau `"12pt"`. Konversi dilakukan di
`config.py`:

| Nilai | Tipe API |
|---|---|
| Panjang, margin, indent, tab stop | integer twip |
| Font size | integer setengah poin (12 pt -> 24) |
| Warna | string `RRGGBB` |
| Boolean OOXML | `True`/`False` eksplisit |
| Level heading | integer 1-9 |

### 1.5 Dependensi

- `docx/*` boleh bergantung pada `docgen.config` untuk tipe data, tetapi
  tidak boleh mengimpor `stages/*`, `pipeline.py`, atau `cli.py`.
- `docx/*` tidak membaca `format.yml`; caller memberikan spesifikasi yang
  sudah dinormalisasi.
- Semua modul memakai `docx/xml.py` untuk parsing/serialization. Tidak ada
  `lxml.etree.fromstring` langsung di stage.
- Semua kesalahan dibungkus `DocxError` atau subclass-nya.

---

## 2. Model data

```python
@dataclass(frozen=True)
class Relationship:
    rel_id: str
    rel_type: str
    target: str
    target_mode: str | None = None

@dataclass(frozen=True)
class PartInfo:
    name: str
    size: int
    content_type: str | None

class DocumentPackage:
    ...
```

`DocumentPackage` adalah satu-satunya pemilik ZIP. `PartInfo` hanya metadata;
payload diakses lewat `part()`.

---

## 3. `docgen/docx/package.py`

### 3.1 Signature

```python
class DocumentPackage:
    @classmethod
    def load(cls, path: str | Path, *, validate: bool = True) -> "DocumentPackage": ...

    def save(self, path: str | Path, *, atomic: bool = True) -> None: ...

    def part(self, name: str) -> bytes: ...
    def xml(self, name: str) -> etree._Element: ...
    def set_part(self, name: str, data: bytes, *,
                 content_type: str | None = None) -> None: ...
    def set_xml(self, name: str, root: etree._Element) -> None: ...

    def has_part(self, name: str) -> bool: ...
    def remove_part(self, name: str) -> None: ...
    def part_names(self) -> tuple[str, ...]: ...
    def part_info(self, name: str) -> PartInfo: ...

    def relationships(self, source: str) -> tuple[Relationship, ...]: ...
    def add_relationship(self, source: str, rel: Relationship) -> None: ...
    def remove_relationship(self, source: str, rel_id: str) -> None: ...
    def ensure_content_type(self, part: str, content_type: str) -> None: ...

    def validate(self) -> None: ...
```

### 3.2 Input/output

| Operasi | Input | Output | Efek |
|---|---|---|---|
| `load` | path DOCX | `DocumentPackage` | Membaca ZIP; tidak memparse XML kecuali `validate=True` |
| `save` | path tujuan | - | Menulis ZIP; atomic default |
| `part` | nama part | bytes | Tidak mengubah apa pun |
| `set_part` | bytes | - | Mengganti payload; menandai part kotor |
| `set_xml` | element | - | Serialize dengan `xml.serialize_xml` |
| `add_relationship` | source + rel | - | Memperbarui `.rels` dan content type bila perlu |
| `validate` | - | - | Memeriksa struktur OPC |

### 3.3 Invariant

- `load()` tidak mengubah file sumber.
- `save()` menulis ke file sementara di direktori tujuan, lalu
  `os.replace`. Jika gagal, file tujuan lama tidak rusak.
- Part yang tidak disentuh disalin dari payload asli, bukan diserialisasi
  ulang.
- Urutan part di ZIP dipertahankan; part baru ditambahkan di akhir.
- `[Content_Types].xml` wajib ada dan memuat default/override untuk setiap
  part.
- `_rels/.rels` dan relasi part wajib menunjuk target yang ada.
- Tidak ada nama part absolut, `..`, backslash, atau duplikat.
- `save()` memanggil `validate()` terlebih dahulu; package tidak valid tidak
  pernah ditulis.

### 3.4 Error

| Error | Kapan |
|---|---|
| `PackageError` | ZIP tidak valid, CRC gagal, part wajib hilang |
| `PartNotFoundError` | `part()`, `xml()`, atau `remove_part()` pada nama yang tidak ada |
| `PartExistsError` | `add_relationship()`/part baru bentrok |
| `InvalidPackageError` | `validate()` gagal |
| `SaveError` | Gagal menulis file sementara atau `os.replace` |

---

## 4. `docgen/docx/io.py`

Modul internal untuk package. Stage **tidak boleh** memakainya langsung.

```python
@dataclass(frozen=True)
class ZipEntry:
    name: str
    data: bytes
    info: zipfile.ZipInfo

def read_zip(path: str | Path) -> tuple[ZipEntry, ...]: ...
def write_zip_atomic(path: str | Path,
                     entries: Sequence[ZipEntry],
                     *,
                     compression: int = zipfile.ZIP_DEFLATED) -> None: ...
```

**Input/output.** `read_zip` menerima path DOCX dan mengembalikan seluruh
entry; `write_zip_atomic` menerima daftar entry dan menulis DOCX baru.

Invariant: `read_zip` mempertahankan `ZipInfo`; `write_zip_atomic` menulis
entry dengan metadata asli untuk entry yang tidak dimodifikasi. Error:
`PackageError`, `SaveError`.

---

## 5. `docgen/docx/xml.py`

### 5.1 Signature

```python
W_NS: str
R_NS: str
WP_NS: str
A_NS: str

def qn(tag: str) -> str: ...
def parse_xml(data: bytes) -> etree._Element: ...
def serialize_xml(root: etree._Element,
                  *,
                  xml_declaration: bool = True) -> bytes: ...
def canonicalize_xml(data: bytes | etree._Element,
                     *,
                     profile: Literal["c14n", "docx"] = "docx") -> bytes: ...
def sha256_c14n(data: bytes | etree._Element,
                *,
                profile: Literal["c14n", "docx"] = "docx") -> str: ...

def iter_paragraphs(root: etree._Element,
                    *,
                    include_tables: bool = True) -> Iterator[etree._Element]: ...
def paragraph_text(paragraph: etree._Element,
                   *,
                   include_fields: bool = False) -> str: ...
def iter_runs(paragraph: etree._Element) -> Iterator[etree._Element]: ...
def run_text(run: etree._Element) -> str: ...

def ensure_ppr(paragraph: etree._Element) -> etree._Element: ...
def ensure_rpr(run: etree._Element) -> etree._Element: ...
def get_or_add(parent: etree._Element, tag: str,
               order: Sequence[str]) -> etree._Element: ...
def insert_ordered(parent: etree._Element, child: etree._Element,
                   order: Sequence[str]) -> None: ...
def is_on(element: etree._Element) -> bool: ...
```

### 5.2 Input/output

Fungsi murni menerima bytes/element dan mengembalikan bytes, element, teks,
hash, atau iterator. `get_or_add` dan `insert_ordered` memutasi parent yang
diberikan dan mengembalikan child yang disisipkan.

### 5.3 Perilaku

- `parse_xml`: parser aman (`resolve_entities=False`, `no_network=True`),
  tidak menghapus komentar/PI, tidak mengubah whitespace.
- `serialize_xml`: UTF-8, deklarasi XML, tanpa pretty-print.
- `paragraph_text`: teks `w:t`; tab menjadi `\t`, line break menjadi `\n`;
  `w:instrText` tidak disertakan kecuali `include_fields=True`.
- `iter_paragraphs`: urutan dokumen; `include_tables=False` melewati isi
  `w:tbl`; text box tidak dianggap paragraf body kecuali diminta eksplisit.
- `get_or_add`/`insert_ordered`: menyisipkan child pada urutan skema OOXML
  yang benar (`w:pPr`, `w:rPr`, `w:sectPr`, `w:tblPr`, `w:tcPr`).

### 5.4 Invariant

- Canonical XML deterministik untuk input yang sama.
- `sha256_c14n` mengembalikan 64 karakter heksadesimal huruf kecil.
- Tidak ada namespace prefix yang bocor ke output canonical.
- `serialize_xml` tidak mengubah isi part yang tidak dimodifikasi; part
  tersebut tidak pernah melewati serializer.

### 5.5 Error

`XmlError` untuk XML tidak well-formed, entity, atau namespace yang tidak
didukung.

---

## 6. `docgen/docx/names.py`

```python
def local_name(tag: str) -> str: ...
def normalize_style_id(value: str) -> str: ...
def is_style(style_id: str | None, *names: str) -> bool: ...
def is_heading_style(style_id: str | None) -> bool: ...
def is_caption_style(style_id: str | None) -> bool: ...
def is_code_style(style_id: str | None) -> bool: ...
def is_cover_style(style_id: str | None) -> bool: ...
```

**Input/output.** Semua fungsi menerima `style_id`/tag dan mengembalikan
string, boolean, atau nama lokal; tidak ada mutasi package.

`normalize_style_id` membuang kapitalisasi, spasi, garis bawah, dan tanda
hubung. `Image Caption`, `image_caption`, dan `ImageCaption` dianggap sama.
`FigureCaption` bukan caption. Error: tidak ada; fungsi murni.

---

## 7. `docgen/docx/styles.py`

### 7.1 Signature

```python
@dataclass(frozen=True)
class StyleSpec:
    style_id: str
    style_type: Literal["paragraph", "character", "table", "numbering"]
    based_on: str | None = None
    ppr: Mapping[str, object] = field(default_factory=dict)
    rpr: Mapping[str, object] = field(default_factory=dict)
    name: str | None = None

def read_style_ids(package: DocumentPackage) -> frozenset[str]: ...
def style_exists(package: DocumentPackage, style_id: str) -> bool: ...
def patch_style(package: DocumentPackage,
                style_id: str,
                *,
                ppr: Sequence[tuple[str, Mapping[str, str]]] = (),
                rpr: Sequence[tuple[str, Mapping[str, str]]] = (),
                drops: Sequence[str] = ()) -> None: ...
def apply_style_specs(package: DocumentPackage,
                      specs: Mapping[str, StyleSpec]) -> None: ...
def ensure_character_style(package: DocumentPackage,
                           style_id: str,
                           name: str,
                           *,
                           rpr_xml: str) -> bool: ...
def verify_style_contract(package: DocumentPackage,
                          expected: Mapping[str, StyleSpec]) -> None: ...
```

**Input/output.** Menerima `DocumentPackage` dan style ID/spec; output berupa
mutasi `word/styles.xml` atau `None`/boolean. `verify_style_contract`
mengembalikan `None` atau melempar error.

### 7.2 Invariant

- Hanya `word/styles.xml` yang berubah; `document.xml` tidak disentuh.
- Style ID yang sudah ada tidak dihapus.
- Style baru hanya ditambahkan jika dideklarasikan; jumlah style sebelum +
  style baru = jumlah sesudah.
- `w:basedOn` menunjuk style yang ada.
- Urutan child `w:pPr`/`w:rPr` valid.
- `Normal`, `Heading1`, `Heading2`, `Heading3`, `TOCHeading`, `ImageCaption`,
  `TableCaption`, `SourceCode`, `Bibliography`, dan `Figure` wajib ada di
  `reference.docx` source.

### 7.3 Error

`StyleError` untuk style tidak ditemukan, duplikat, atau nilai tidak valid.
`StyleContractError` untuk pelanggaran invariant.

---

## 8. `docgen/docx/sections.py`

### 8.1 Signature

```python
@dataclass(frozen=True)
class Section:
    index: int
    start: int
    end: int
    sect_pr: etree._Element
    kind: Literal["cover", "front_matter", "body", "back_matter"]

@dataclass(frozen=True)
class HeaderFooterRefs:
    header: str | None
    footer: str | None
    first_page_header: str | None
    first_page_footer: str | None

def iter_sections(package: DocumentPackage) -> tuple[Section, ...]: ...
def section_at(package: DocumentPackage, paragraph_index: int) -> Section: ...
def set_page_size(section: Section, *,
                  width: int, height: int,
                  orientation: Literal["portrait", "landscape"]) -> None: ...
def set_margins(section: Section, *,
                top: int, right: int, bottom: int, left: int,
                header: int, footer: int, gutter: int) -> None: ...
def set_page_number_format(section: Section, *,
                           fmt: Literal["decimal", "lowerRoman",
                                        "upperRoman", "lowerLetter",
                                        "upperLetter"],
                           start: int | None = None) -> None: ...
def set_title_page(section: Section, value: bool) -> None: ...
def set_section_type(section: Section,
                     value: Literal["nextPage", "continuous",
                                    "evenPage", "oddPage"]) -> None: ...
def add_section_break(package: DocumentPackage, *,
                      before: etree._Element,
                      kind: Literal["nextPage", "continuous"]) -> Section: ...
def remove_empty_sections(package: DocumentPackage) -> int: ...
def section_header_footer(section: Section) -> HeaderFooterRefs: ...
```

**Input/output.** Menerima `DocumentPackage`/`Section` dan nilai twip; output
berupa mutasi `word/document.xml`, part header/footer, atau `Section` baru.
Fungsi baca mengembalikan tuple `Section`/`HeaderFooterRefs`.

### 8.2 Invariant

- Setiap section memiliki tepat satu `w:sectPr`.
- `w:sectPr` terakhir berada di body; section break lain berada di `w:pPr`.
- Cover tidak menampilkan nomor halaman.
- Front matter memakai Romawi kecil; body memakai Arab.
- Tidak ada halaman kosong akibat section break ganda.
- Margin berasal dari `format.yml` dan diterapkan ke semua section.
- Header/footer relationship yang sudah ada dipertahankan; part baru hanya
  dibuat jika diminta.
- Operasi idempoten: menjalankan ulang tidak menambah section atau mengubah
  hasil canonical.

### 8.3 Error

`SectionError` untuk section tidak ditemukan, `sectPr` ganda, atau format
nomor halaman tidak valid.

---

## 9. Heading

API heading DOCX (iterasi, level, penomoran `BAB I`/`1.1.`/`1.1.1.`) berada di
`docgen/docx/sections.py` milik WS6. Modul terpisah `docgen/docx/headings.py`
menangani penomoran heading Markdown sebelum Pandoc (`number_markdown`,
`balance_title`, `HeadingNumberer`) dan tidak menyentuh package DOCX. Kedua
modul ada di target tree v0.13; signature API DOCX di bawah tidak berubah.

### 9.1 Signature

```python
@dataclass(frozen=True)
class Heading:
    level: int
    paragraph: etree._Element
    text: str
    number: str | None
    unnumbered: bool

@dataclass(frozen=True)
class NumberingSpec:
    body: Literal["BAB_ROMAN", "ARABIC_DOTTED"]
    sub_dot: bool = True
    subsub_dot: bool = True

def iter_headings(package: DocumentPackage) -> tuple[Heading, ...]: ...
def heading_level(paragraph: etree._Element) -> int | None: ...
def heading_text(paragraph: etree._Element,
                 *, include_number: bool = True) -> str: ...
def is_unnumbered(paragraph: etree._Element) -> bool: ...
def apply_heading_numbering(package: DocumentPackage,
                            spec: NumberingSpec) -> HeadingReport: ...
def heading_bookmark_name(heading: Heading) -> str: ...
```

**Input/output.** Menerima package/paragraf dan `NumberingSpec`; output berupa
tuple `Heading`, string nomor, `HeadingReport`, atau mutasi teks heading.
Tidak mengubah run non-heading.

### 9.2 Invariant

- H1 `BAB_ROMAN`: `BAB I` + line break + judul kapital.
- H1 `ARABIC_DOTTED`: `1.` + spasi + judul kapital.
- H2: `1.1.` + tab + judul; H3: `1.1.1.` + tab + judul.
- H4-H9 tidak dinomori dan tidak mengubah counter.
- Heading dengan kelas `{-}`/unnumbered tidak dinomori dan tidak mereset
  counter.
- Format inline (bold/italic/code) di dalam heading dipertahankan.
- Prefix nomor lama dihapus sebelum nomor baru ditulis; idempoten.
- Tab stop dan hanging indent berasal dari style, bukan run.

### 9.3 Error

`HeadingError` untuk heading tidak valid atau level tidak didukung.

---

## 10. `docgen/docx/captions.py`

### 10.1 Signature

```python
class CaptionKind(Enum):
    FIGURE = "figure"
    TABLE = "table"

@dataclass(frozen=True)
class Caption:
    kind: CaptionKind
    paragraph: etree._Element
    anchor: etree._Element
    number: str
    text: str

def iter_captions(package: DocumentPackage) -> tuple[Caption, ...]: ...
def ensure_caption(package: DocumentPackage, *,
                   kind: CaptionKind,
                   anchor: etree._Element,
                   text: str) -> Caption: ...
def set_caption(package: DocumentPackage, caption: Caption, *,
                text: str, number: str) -> None: ...
def renumber_captions(package: DocumentPackage, *,
                      scope: Literal["chapter", "document"] = "chapter") -> CaptionReport: ...
def caption_style(kind: CaptionKind) -> str: ...
def is_caption_paragraph(paragraph: etree._Element,
                         kind: CaptionKind | None = None) -> bool: ...
```

**Input/output.** Menerima package, `CaptionKind`, anchor, dan teks; output
berupa `Caption`, `CaptionReport`, atau mutasi paragraf caption. Anchor tidak
boleh berupa tabel kode.

### 10.2 Invariant

- Caption tabel tepat di atas tabel; caption gambar tepat di bawah gambar.
- Style `TableCaption`/`ImageCaption` diterapkan langsung dan konsisten.
- Nomor `bab.n` mengikuti Heading1 `BAB ...`; counter terpisah untuk gambar
  dan tabel; reset per bab.
- Prefix lama dihapus; tidak ada nomor ganda.
- Caption yang memuat field dilewati, bukan ditimpa.
- Tabel kode tidak diberi caption.
- Paragraf kosong antara caption dan objek dihapus.
- Idempoten: run kedua tidak mengubah `document.xml` canonical.

### 10.3 Error

`CaptionError` untuk caption hilang, anchor tidak valid, atau konflik nomor.

---

## 11. `docgen/docx/tables.py`

### 11.1 Signature

```python
@dataclass(frozen=True)
class TableInfo:
    element: etree._Element
    is_code: bool
    has_caption: bool
    rows: int
    columns: int

def iter_tables(package: DocumentPackage) -> tuple[TableInfo, ...]: ...
def is_code_table(table: etree._Element) -> bool: ...
def format_code_table(package: DocumentPackage,
                      table: etree._Element) -> bool: ...
def normalize_table(package: DocumentPackage,
                    table: etree._Element,
                    spec: TableSpec) -> None: ...
def make_code_table(package: DocumentPackage,
                    paragraphs: Sequence[etree._Element]) -> etree._Element: ...
def set_borders(table: etree._Element, spec: BorderSpec) -> None: ...
def set_cell_margins(table: etree._Element, twips: int) -> None: ...
def set_table_width(table: etree._Element, percent: int) -> None: ...
```

**Input/output.** Menerima package/tabel dan spec; output berupa
`TableInfo`, tabel baru, boolean perubahan, atau mutasi `w:tblPr`/`w:tcPr`.
Tidak mengubah tabel data menjadi tabel kode.

### 11.2 Invariant

- Tabel kode selalu 1 baris x 1 kolom.
- Lebar 100% lebar konten; border luar `single` 1 pt; border dalam `nil`.
- Tidak ada shading, numbering, atau caption tabel data.
- Cell margin 108 twip kiri/kanan/atas/bawah.
- Paragraf kode dalam sel mempertahankan style asal dan format langsung
  Courier New 10 pt.
- Tabel data tidak diubah menjadi tabel kode.
- Idempoten: tabel kode yang sudah ada dinormalisasi ke bentuk yang sama.

### 11.3 Error

`TableError` untuk struktur tabel tidak valid atau operasi yang melanggar
invariant.

---

## 12. `docgen/docx/layout.py`

### 12.1 Signature

```python
@dataclass(frozen=True)
class LayoutReport:
    checked: int
    normalized: int
    skipped: int
    fields_preserved: int

def normalize_layout(package: DocumentPackage, *,
                     spec: LayoutSpec) -> LayoutReport: ...
def normalize_paragraph(paragraph: etree._Element,
                        spec: LayoutSpec) -> bool: ...
def is_exempt(paragraph: etree._Element) -> bool: ...
def has_bold_field(paragraph: etree._Element) -> bool: ...
def preserve_tabs(paragraph: etree._Element,
                  old_ppr: etree._Element | None) -> None: ...
```

**Input/output.** Menerima package/paragraf dan `LayoutSpec`; output berupa
`LayoutReport`, boolean perubahan, atau mutasi `w:pPr`/`w:rPr`. Teks tidak
diubah.

### 12.2 Invariant

- Spacing before/after 0; line 1.5 (`w:line=360`, `lineRule=auto`);
  alignment justify; right alignment dipertahankan.
- Bold langsung dihapus dari body/daftar, tetapi **tidak** dari run field
  (`TOC`, `PAGEREF`, `SEQ`, `PAGE`), heading, atau `CoverTitle`.
- Tab stop kustom dipertahankan.
- Text box, header, footer, dan footnote tidak disentuh.
- H4-H9 tidak mendapat aturan gap baru.
- Idempoten.

### 12.3 Error

`LayoutError` untuk spec tidak valid atau struktur paragraf rusak.

---

## 13. `docgen/docx/fields.py`

### 13.1 Signature

```python
class FieldKind(Enum):
    TOC = "TOC"
    PAGEREF = "PAGEREF"
    SEQ = "SEQ"
    PAGE = "PAGE"
    NUMPAGES = "NUMPAGES"
    OTHER = "OTHER"

@dataclass(frozen=True)
class Field:
    kind: FieldKind
    instruction: str
    paragraph: etree._Element
    begin: etree._Element
    separate: etree._Element | None
    end: etree._Element
    nested: tuple["Field", ...]

def iter_fields(package: DocumentPackage) -> tuple[Field, ...]: ...
def field_kind(instruction: str) -> FieldKind: ...
def field_instruction(field: Field) -> str: ...
def insert_toc(package: DocumentPackage, *,
               title: str,
               levels: tuple[int, int] = (1, 3),
               caption: str | None = None) -> Field: ...
def insert_seq(package: DocumentPackage, *,
               paragraph: etree._Element,
               label: str) -> Field: ...
def insert_pageref(package: DocumentPackage, *,
                   paragraph: etree._Element,
                   bookmark: str) -> Field: ...
def is_bold_exempt(field: Field) -> bool: ...
def strip_update_fields(package: DocumentPackage) -> bool: ...
```

**Input/output.** Menerima package/paragraf dan parameter field; output
berupa `Field`, tuple `Field`, string instruksi, atau boolean. Fungsi insert
memutasi `word/document.xml` dan mengembalikan field baru.

### 13.2 Invariant

- Field kompleks selalu memiliki `begin`, `separate`, dan `end`; field
  bersarang dilacak.
- `fldSimple` dikenali sebagai field.
- TOC ditulis di dalam `w:sdt` dengan `docPartGallery "Table of Contents"`.
- Daftar gambar/tabel memakai `TOC \c "Gambar"`/`TOC \c "Tabel"`.
- Caption memakai `SEQ Gambar`/`SEQ Tabel`.
- Run field tidak pernah kehilangan bold karena normalisasi layout.
- Tidak ada TOC ganda; insert ulang mengganti field lama, bukan menambah.
- `strip_update_fields` hanya menghapus `w:updateFields`; tidak mengubah
  field.

### 13.3 Error

`FieldError` untuk field tidak lengkap, instruksi tidak valid, atau konflik
field.

---

## 14. `docgen/docx/terms.py`

### 14.1 Signature

```python
@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    italic: bool

@dataclass(frozen=True)
class Glossary:
    entries: Mapping[str, GlossaryEntry]
    source: Path

@dataclass(frozen=True)
class TermMatch:
    start: int
    end: int
    entry: GlossaryEntry

@dataclass(frozen=True)
class TermsReport:
    applied: int
    skipped_bibliography: int
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class TermsVerifyReport:
    violations: tuple[str, ...]
    warnings: tuple[str, ...]

def load_glossary(path: str | Path) -> Glossary: ...
def match_terms(text: str, glossary: Glossary) -> tuple[TermMatch, ...]: ...
def apply_terms(package: DocumentPackage,
                glossary: Glossary,
                *,
                review_path: Path | None = None) -> TermsReport: ...
def verify_terms(package: DocumentPackage,
                 glossary: Glossary) -> TermsVerifyReport: ...
def resolve_style(package: DocumentPackage, style_id: str) -> StyleResolution: ...
```

**Input/output.** Menerima path TSV, package, dan `Glossary`; output berupa
`Glossary`, tuple `TermMatch`, `TermsReport`, `TermsVerifyReport`, atau
mutasi run/style. `review_path` hanya menentukan lokasi laporan.

### 14.2 Invariant

- Frasa terpanjang menang; batas kata; case-insensitive; teks asli
  dipertahankan.
- Lintas run didukung.
- Field, `w:instrText`, dan hyperlink eksternal tidak disentuh.
- Paragraf `Bibliography` dilewati.
- `IstilahAsing` selalu efektif italic dan `w:lang="en-US"`.
- `IstilahReview` tidak pernah dipromosikan menjadi `IstilahAsing`.
- Direct formatting lain dipertahankan.
- Apply idempoten: run kedua tidak menambah span/style baru.
- Review file deterministik (urut, tanpa timestamp).

### 14.3 Error

`GlossaryError` untuk TSV tidak valid, duplikat, atau nilai kolom salah.
`TermsError` untuk pelanggaran verify.

---

## 15. `docgen/docx/bookmarks.py`

### 15.1 Signature

```python
@dataclass(frozen=True)
class Bookmark:
    name: str
    bookmark_id: int
    start: etree._Element
    end: etree._Element

@dataclass(frozen=True)
class ParagraphBookmark:
    name: str
    paragraph_index: int
    kind: str
    text: str

def iter_bookmarks(package: DocumentPackage) -> tuple[Bookmark, ...]: ...
def remove_paragraph_bookmarks(package: DocumentPackage) -> int: ...
def add_paragraph_ids(package: DocumentPackage) -> tuple[ParagraphBookmark, ...]: ...
def next_bookmark_id(package: DocumentPackage) -> int: ...
def bookmark_wraps_content(bookmark: Bookmark) -> bool: ...
```

**Input/output.** Menerima package dan mengembalikan tuple `Bookmark`,
tuple `ParagraphBookmark`, integer ID, atau mutasi `w:bookmarkStart`/
`w:bookmarkEnd` di `word/document.xml`.

### 15.2 Invariant

- Nama bookmark `p0001`, `p0002`, dst.; minimal empat digit.
- Bookmark hanya untuk paragraf body, termasuk tabel dan text box; header,
  footer, dan footnote tidak dihitung.
- `w:bookmarkStart` tepat setelah `w:pPr`; `w:bookmarkEnd` menjadi child
  terakhir paragraf.
- `w:id` baru dimulai di atas ID bookmark yang ada.
- Bookmark `pNNNN` lama dihapus sebelum injeksi; tidak ada duplikat.
- Teks, run, style, field, section, dan urutan elemen tidak berubah.
- Idempoten: nama, urutan, dan `w:id` stabil.
- Hanya `word/document.xml` yang berubah.

### 15.3 Error

`BookmarkError` untuk nama duplikat, `w:id` tidak valid, atau struktur
bookmark rusak.

---

## 17. Matriks part yang boleh berubah

| Stage | `mutates` | Catatan |
|---|---|---|
| `sections` | `word/document.xml` | Cover, front matter, section, heading |
| `code` | `word/document.xml` | Blok kode menjadi tabel 1x1 |
| `captions` | `word/document.xml` | Caption, gambar, tabel data |
| `normalize` | `word/document.xml` | Spacing, alignment, bold |
| `equations` | `word/document.xml` | Nomor persamaan OMML |
| `numbering` | `word/document.xml`, `word/numbering.xml` | Indentasi dan bold list |
| `blank_lines` | `word/document.xml` | Paragraf kosong fisik |
| `terms` | `word/document.xml`, `word/styles.xml` | Style istilah |
| `toc` | `word/document.xml`, `word/styles.xml` | Field TOC dan style TOC |
| `page_numbers` | `word/document.xml`, `word/header*.xml`, `word/footer*.xml`, `word/_rels/document.xml.rels`, `[Content_Types].xml` | Nomor halaman |
| `lists` | `word/document.xml` | Field daftar gambar/tabel |
| `bookmarks` (Adeu, dalam pass yang sama) | `word/document.xml` | Bookmark `pNNNN` |
| `office` | seluruh package | Word boleh menyimpan ulang; dikecualikan dari byte identity |
| `pdf` | tidak ada | Hanya membaca DOCX |

Stage yang tidak ada di tabel tidak boleh mengubah part apa pun.

---

## 18. Idempotensi

Definisi:

```text
run_stage(input) -> output1
run_stage(output1) -> output2
assert sha256_c14n(output1.document_xml) == sha256_c14n(output2.document_xml)
assert bytes(output1.part) == bytes(output2.part) untuk semua part non-target
```

Aturan per stage:

| Stage | Idempoten | Catatan |
|---|---|---|
| `sections` | ya | Tidak menambah section/heading ganda |
| `code` | ya | Tabel kode yang sudah ada dinormalisasi, bukan diduplikasi |
| `captions` | ya | Prefix lama dihapus |
| `normalize` | ya | Nilai akhir sama |
| `equations` | ya | Nomor lama diganti |
| `numbering` | ya | Indent/tab sama |
| `blank_lines` | ya | Tidak menambah paragraf kosong ganda |
| `terms` | ya | Span/style stabil |
| `toc` | ya | Field TOC diganti, bukan ditambah |
| `page_numbers` | ya | Format section stabil |
| `lists` | ya | Field daftar diganti, bukan ditambah |
| `bookmarks` | ya | Nama dan ID stabil |
| `office` | semantik | Word dapat menulis ulang package |
| `pdf` | semantik | Output PDF tidak dijamin byte-identik |

---

## 19. Error dan pemetaan CLI

| Error | Arti | Exit CLI |
|---|---|---|
| `DocxError` | Kesalahan umum DOCX | 1 |
| `PackageError` | ZIP/OPC rusak | 1 |
| `PartNotFoundError` | Part tidak ada | 1 |
| `InvalidPackageError` | Package tidak valid | 1 |
| `XmlError` | XML tidak valid | 1 |
| `StyleError`/`StyleContractError` | Style rusak | 1 |
| `SectionError` | Section rusak | 1 |
| `HeadingError` | Heading rusak | 1 |
| `CaptionError` | Caption rusak | 1 |
| `TableError` | Tabel rusak | 1 |
| `LayoutError` | Layout rusak | 1 |
| `FieldError` | Field rusak | 1 |
| `GlossaryError`/`TermsError` | Istilah rusak | 1 |
| `BookmarkError` | Bookmark rusak | 1 |
| `SaveError` | Gagal menulis | 1 |

Semua error menyebut part, paragraf (jika ada), dan aksi yang gagal.

---

## 20. Acceptance

- `tests/unit/test_docx_package.py`: load/save, part identity, atomic save,
  content types, rels.
- `tests/unit/test_docx_xml.py`: c14n determinisme, `sha256_c14n`, urutan
  child.
- `tests/unit/test_style_reference.py`: style count, style contract,
  `patch_style`, dan `verify_style_contract`.
- `tests/unit/test_sections.py`: section, margin, page numbering, tidak ada
  halaman kosong, dan `apply_heading_numbering`.
- `tests/unit/test_docx_headings.py`: penomoran heading Markdown `BAB I`,
  `1.1.`, `1.1.1.`, unnumbered, inline formatting, dan `balance_title`.
- `tests/unit/test_stages_captions.py`: posisi caption, prefix, dan
  idempotensi.
- `tests/unit/test_stages_code.py` dan `tests/unit/test_stages_captions.py`:
  tabel kode 1x1, border, dan bukan caption tabel data.
- `tests/unit/test_stages_layout.py`: bold field exempt dan tab stop.
- `tests/unit/test_toc.py`, `tests/unit/test_lists.py`, dan
  `tests/unit/test_page_numbers.py`: begin/separate/end, TOC/SEQ/PAGEREF,
  dan field PAGE.
- `tests/unit/test_stages_terms.py`: longest match, skip Bibliography,
  verify.
- `tests/unit/test_adeu_paragraph_ids.py`: `pNNNN`, id stabil, hanya
  `document.xml`.
- Part non-target byte-identik dan `document.xml` c14n+sha256 diuji di
  `tests/unit/test_docx_package.py` serta tes part per stage:
  `test_stages_code.py`, `test_stages_captions.py`,
  `test_stages_layout.py`, `test_stages_equations.py`, dan
  `test_stages_numbering.py`.
- `tests/integration/test_pipeline_python.py` dan
  `tests/integration/test_thesis_pipeline.py`: load/save package target
  masing-masing tepat satu kali.
