# 04 - Model DOCX

Halaman ini menjelaskan DOCX sebagai package Open Packaging Conventions
(OPC), peta modul
`src/docgen/docx/`, helper kanonis, field Word, dan package `terms`. Setelah
membacanya, pembaca bisa memilih modul yang benar sebelum mengubah XML dan
tidak membuat helper duplikat.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. menjelaskan DOCX sebagai ZIP berisi part dan relationship;
2. memakai `DocumentPackage` sesuai aturan satu load/satu save;
3. menemukan helper paragraf, run, numbering, page, heading, field, dan terms;
4. membaca dan menulis field TOC/SEQ/PAGE dengan API yang ada;
5. menjelaskan mengapa `content_width` dan parser field tidak punya fallback.

## Prasyarat

- [03 - Tahap Pipeline](03-pipeline-stages.md).
- Mengenal XML dasar: elemen, atribut, namespace, dan teks.
- Tidak perlu membuka Word. Semua latihan dapat memakai fixture DOCX yang ada.

## Daftar isi

- [DOCX adalah package ZIP](#docx-adalah-package-zip)
- [DocumentPackage](#documentpackage)
- [Peta modul docx](#peta-modul-docx)
- [Helper kanonis](#helper-kanonis)
- [Field dan siklus Word](#field-dan-siklus-word)
- [Package terms](#package-terms)
- [Contoh konkret: membaca fixture](#contoh-konkret-membaca-fixture)
- [Zero-fallback di lapisan DOCX](#zero-fallback-di-lapisan-docx)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## DOCX adalah package ZIP

File `.docx` adalah ZIP dengan struktur Open Packaging Conventions. Part yang
sering dipakai pipeline:

| Part | Isi |
| --- | --- |
| `word/document.xml` | Body dokumen: paragraf, tabel, field, bookmark, section. |
| `word/styles.xml` | Definisi style paragraf, karakter, tabel, dan TOC. |
| `word/numbering.xml` | Definisi penomoran daftar. |
| `word/header*.xml`, `word/footer*.xml` | Header dan footer, termasuk nomor halaman. |
| `word/_rels/document.xml.rels` | Relationship ke header, footer, gambar, dan hyperlink. |
| `[Content_Types].xml` | Pemetaan ekstensi/part ke content type. |
| `docProps/core.xml`, `docProps/app.xml` | Metadata dokumen dan aplikasi. |

Satu package juga memiliki relationship di `_rels/.rels` untuk menunjuk
dokumen utama. Stage tidak membaca ZIP langsung. Semua akses lewat
`DocumentPackage`.

## DocumentPackage

`DocumentPackage` adalah satu-satunya pemilik ZIP dan cache XML di memori.
Operasi penting:

```python
package = DocumentPackage.load(path)
package.has_part("word/document.xml")
root = package.xml("word/document.xml")
package.set_xml("word/document.xml", root)
package.part_names()
package.relationships("word/document.xml")
package.save(output_path)
```

Aturan yang dipegang:

- `load` tidak mengubah file sumber.
- Stage tidak memanggil `load` atau `save` untuk package target.
- Part yang tidak dideklarasikan stage harus byte-identik.
- Perubahan `document.xml` dibandingkan dengan canonical XML dan SHA-256,
  bukan byte mentah.
- `save` menulis atomic ke direktori tujuan.
- Tidak ada intermediate DOCX di direktori output; DOCX antara hanya ada di
  workspace.

`DocumentPackage` adalah nama publik yang dipertahankan. `DocxPackage` juga
masih diekspor sebagai nama lama, tetapi kode baru memakai
`DocumentPackage`.

## Peta modul docx

| Modul | Tanggung jawab |
| --- | --- |
| `package.py` | Model package, part, relationship, load/save, validasi. |
| `io.py` | Baca/tulis ZIP dan penulisan atomic. Tidak dipakai stage langsung. |
| `xml.py` | Parse, serialisasi, c14n, hash, helper elemen, iterasi paragraf/run. |
| `names.py` | Namespace, tag, style, dan konstanta OOXML. |
| `paragraphs.py` | `document_body`, `body_children`, style/level heading, teks paragraf, hapus child, atribut integer. |
| `runs.py` | `build_run`, `make_run`, `append_text_run`, `clone_run`, `copy_rpr`, `strip_bold_from_rpr`. |
| `numbering.py` | `roman_to_int`, `chapter_number`, `to_roman`, `format_roman`. |
| `heading_numbering.py` | Iterasi heading, nomor H1/H2/H3, heading unnumbered, bookmark heading. |
| `page.py` | `PAGE_SIZES`, `page_size`, `content_width`, `PageError`. |
| `styles.py` | Style paragraf, karakter, tabel, dan page layout. |
| `sections.py` | Section break, margin, header, footer. |
| `captions.py` | Caption tabel/gambar, numbering, layout gambar. |
| `tables.py` | Tabel biasa, tabel kode, border, cell margin. |
| `layout.py` | Spasi, indentasi, perataan, bold, klasifikasi blok. |
| `fields.py` | Parser, scanner, dan builder field TOC/PAGEREF/SEQ/PAGE/NUMPAGES. |
| `bookmarks.py` | Bookmark `pNNNN` dan verifikasi. |
| `terms/` | Glosarium, model istilah, apply, verify, dan review. |

Bookmark `pNNNN` yang ditulis `bookmarks.py` adalah penghubung ke Adeu dan
manifest; alur lengkapnya ada di [Integrasi Adeu](../adeu-integration.md).

`terms/` adalah package, bukan satu modul:

| Modul | Tanggung jawab |
| --- | --- |
| `terms/glossary.py` | `load_glossary`, `merge_glossaries`, model `Glossary`. |
| `terms/model.py` | Marker `{{?…?}}`, model paragraf, style resolver, `open_docx`, review. |
| `terms/apply.py` | `apply_terms`, `transform_runs`, style istilah. |
| `terms/verify.py` | `verify_terms` dan laporan pelanggaran. |

Jangan menambah parser field kedua, helper run kedua, atau tabel Romawi kedua.
Kalau helper belum ada, cari dulu di modul kanonis di atas.

## Helper kanonis

### Paragraf dan run

```python
from docgen.docx import DocumentPackage
from docgen.docx.paragraphs import document_body, paragraph_text
from docgen.docx.runs import append_text_run
from docgen.docx.xml import iter_paragraphs

package = DocumentPackage.load("tests/fixtures/golden/laporan-baseline.docx")
body = document_body(package)
paragraph = next(iter_paragraphs(body))
print(paragraph_text(paragraph))
append_text_run(paragraph, " tambahan")
```

`document_body` memeriksa bahwa argumen adalah `DocumentPackage`, part
`word/document.xml` ada, dan root memiliki `w:body`. `paragraph_text`
mengabaikan teks field, gambar, text box, dan paragraf bersarang.
`append_text_run` memecah tab menjadi elemen `w:tab` dan menulis `w:rPr` satu
kali di awal run.

### Field

Signature `insert_field` adalah:

```python
insert_field(
    switches: Sequence[str],
    position: FieldPosition,
    result: str = "",
) -> Field
```

Contoh field `PAGE`:

```python
from docgen.docx.fields import FieldPosition, insert_field

field = insert_field(
    ["PAGE"],
    FieldPosition(paragraph=paragraph),
    "1",
)
```

`FieldPosition` memiliki `paragraph`, `before`, `end_paragraph`, dan `rpr`.
Field selalu ditulis lengkap: `begin`, `instrText`, `separate`, hasil, lalu
`end`. Pipeline tidak menulis `w:dirty` dan tidak mengarang hasil field.

Helper tipis di atasnya:

- `insert_seq(package, paragraph=..., label="Tabel")` menulis `SEQ <label>`;
- `insert_pageref(package, paragraph=..., bookmark=...)` menulis
  `PAGEREF <bookmark> \h`;
- `insert_toc(package, title=..., levels=(1, 3), caption=None,
  before=None, keep_existing=False)` menulis field TOC di dalam `w:sdt`.

### Halaman, nomor, dan heading

```python
from docgen.docx.numbering import chapter_number
from docgen.docx.page import content_width, page_size

print(chapter_number("BAB IV"))
print(page_size("A4", "portrait"))
print(content_width(document_body(package)))
```

- `chapter_number` menerima `BAB IV`, `BAB 4`, atau `4.` dan mengembalikan
  integer atau `None`.
- `page_size` mengembalikan `(lebar, tinggi)` dalam twip. Nama yang tidak
  dikenal tidak punya fallback dan menimbulkan `KeyError`.
- `content_width` menghitung lebar dari `w:sectPr`. Section atau atribut yang
  tidak lengkap menimbulkan `PageError` berkode `PAGE-WIDTH`.

Untuk heading DOCX, gunakan `heading_numbering.py`, bukan `sections.py`:

```python
from docgen.docx.heading_numbering import (
    NumberingSpec,
    apply_heading_numbering,
    iter_headings,
)

report = apply_heading_numbering(
    package,
    NumberingSpec(body="BAB_ROMAN", sub_dot=True, subsub_dot=True),
)
print(report.numbered)
print([heading.text for heading in iter_headings(package)])
```

Penomoran heading Markdown sebelum Pandoc ada di
`src/docgen/markdown/headings.py`, bukan di lapisan DOCX.

## Field dan siklus Word

Field yang ditulis pipeline:

| Field | Fungsi |
| --- | --- |
| `TOC \o "1-3" \h \z \u` | Daftar isi utama. |
| `TOC \c "Tabel"` | Daftar tabel. |
| `TOC \c "Gambar"` | Daftar gambar. |
| `SEQ Tabel \* ARABIC \s 1` | Nomor caption tabel per bab. |
| `SEQ Gambar \* ARABIC \s 1` | Nomor caption gambar per bab. |
| `PAGEREF` | Rujukan nomor halaman. |
| `PAGE` | Nomor halaman di header/footer. |
| `NUMPAGES` | Jumlah halaman bila diperlukan. |

Python menulis instruksi dan hasil cache awal. Word yang menghitung hasil
final, termasuk entri TOC dan nomor halaman. Karena itu build DOCX tanpa Word
tetap menghasilkan file, tetapi field belum final. TOC yang baru bisa tampil
kosong, dan pipeline memberi peringatan bahwa Word tidak tersedia.

`fields.py` adalah satu-satunya parser `w:fldChar`/`w:fldSimple` dan scanner
marker field. Modul stage dan DOCX lain memakai scanner ini. Jangan menulis
regex field baru di stage.

## Package terms

Fitur istilah hanya aktif dengan `--terms`. Alurnya:

1. `load_glossary` membaca `src/docgen/data/glossary/istilah.tsv`;
2. `merge_glossaries` menggabungkan `istilah.tsv` pengguna di samping
   `document.md`;
3. `collect_markdown_terms` memvalidasi marker `{{?…?}}`;
4. `apply_terms` memberi style `IstilahAsing` atau `IstilahReview`;
5. `verify_terms` memeriksa invariant;
6. review file ditulis ke `.laporan/istilah-baru.txt`.

Header glosarium wajib `term<TAB>italic`. Nilai `italic` hanya `yes` atau
`no`. Entri pengguna menimpa entri paket dengan kunci casefold yang sama.

`open_docx` adalah loader publik untuk alat terms:

```python
from docgen.docx.terms import open_docx

package = open_docx("out/Tugas.docx")
```

`open_docx` mengembalikan `DocumentPackage`, bukan tipe lain. Package target
tetap tidak boleh di-load ulang oleh stage.

## Contoh konkret: membaca fixture

Fixture golden adalah DOCX valid yang bisa diperiksa tanpa build:

```bash
uv run python -c "from docgen.docx import DocumentPackage; p = DocumentPackage.load('tests/fixtures/golden/laporan-baseline.docx'); print(len(p.part_names())); print(p.has_part('word/document.xml'))"
```

Hasil yang diharapkan adalah `51` dan `True` pada fixture saat ini. Jumlah
part dapat berubah jika fixture diperbarui, tetapi `word/document.xml` harus
selalu ada.

Hitung field TOC pada fixture:

```bash
uv run python -c "from docgen.docx import DocumentPackage; from docgen.docx.fields import FieldKind, iter_fields; p = DocumentPackage.load('tests/fixtures/golden/laporan-baseline.docx'); print(sum(f.kind is FieldKind.TOC for f in iter_fields(p)))"
```

Hasil yang diharapkan adalah `3`: TOC utama, daftar tabel, dan daftar gambar.

## Zero-fallback di lapisan DOCX

Contoh perilaku yang harus dipertahankan:

- `content_width` tidak memakai lebar cadangan. Jika `w:sectPr`, `w:pgSz`,
  `w:pgMar`, atau atributnya tidak valid, ia melempar `PageError`.
- `page_size` memakai lookup nama. Nama selain `A4` dan `Letter` tidak
  ditebak menjadi A4.
- `DocumentPackage.xml` melempar `PartNotFoundError` jika part tidak ada.
- `insert_field` menolak posisi yang bukan paragraf atau switch yang kosong.
- Parser field hanya satu. Tidak ada parser kedua yang mencoba format lain.

Saat menambah helper, pertahankan pola ini: satu fungsi, satu kontrak, error
jelas. Jangan menambahkan parameter `default=` yang menyembunyikan input
hilang.

## Latihan

### 1. Inspeksi package

Jalankan:

```bash
uv run python -c "from docgen.docx import DocumentPackage; p = DocumentPackage.load('tests/fixtures/golden/laporan-baseline.docx'); print('\n'.join(p.part_names()))"
```

Cara memeriksa: output memuat `[Content_Types].xml`, `word/document.xml`,
`word/styles.xml`, dan `word/numbering.xml`. Jika part inti tidak ada,
`DocumentPackage.load` atau `validate` akan gagal.

### 2. Jalankan tes helper kanonis

Jalankan:

```bash
uv run --extra dev pytest tests/unit/test_docx_paragraphs.py tests/unit/test_docx_runs.py tests/unit/test_docx_page.py -q
```

Cara memeriksa: semua tes lulus dan ringkasan berakhir dengan `passed`.
Tes `test_docx_page.py` memuat kasus `content_width` tanpa section dan
memastikan `PageError`, bukan lebar default.

### 3. Baca signature sebelum memakai API

Jalankan:

```bash
grep -n "def insert_field" -A 20 src/docgen/docx/fields.py
```

Cara memeriksa: signature memakai `switches: Sequence[str]`, `position:
FieldPosition`, dan `result: str = ""`. Jika kode pemanggil memakai parameter
lain, perbaiki pemanggil, bukan menambah parameter fallback.

## Halaman berikutnya

Lanjut ke [05 - Tes dan Debugging](05-testing-and-debugging.md) untuk memilih
tes yang tepat dan menelusuri error DOCX.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Indeks lapisan DOCX | [docx/README.md](../docx/README.md) |
| Peta modul dan batas helper | [docx/overview.md](../docx/overview.md) |
| Model package | [docx/package.md](../docx/package.md) |
| Helper paragraf | [docx/paragraphs.md](../docx/paragraphs.md) |
| Helper run | [docx/runs.md](../docx/runs.md) |
| Numbering dan heading | [docx/numbering.md](../docx/numbering.md) |
| Halaman dan margin | [docx/page.md](../docx/page.md) |
| Field | [docx/fields.md](../docx/fields.md) |
| Istilah dan glosarium | [docx/terms.md](../docx/terms.md) |
| Kontrak DOCX | [contracts/docx-api.md](../contracts/docx-api.md) |
| Kontrak stage | [contracts/stage-api.md](../contracts/stage-api.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `OOXML ECMA-376`, `Open XML SDK`,
`WordprocessingML API reference`, `lxml documentation`, `python-docx
documentation`, dan `ruamel.yaml documentation`. URL resminya ada di
[registry referensi](../references.md).
