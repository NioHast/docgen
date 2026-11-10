# Lapisan DOCX

`src/docgen/docx/` adalah satu-satunya lapisan yang membaca dan menulis paket
DOCX. Stage tidak menyentuh ZIP secara langsung. Semua mutasi terjadi pada
`DocumentPackage` di memori, lalu pipeline menyimpan satu kali.

Kontrak API lengkap ada di [contracts/docx-api.md](contracts/docx-api.md).

## Model package

`DocumentPackage` memiliki:

- daftar part dengan byte asli dan `ZipInfo`;
- XML yang sudah diparse untuk part yang dimutasi;
- relationship per part;
- operasi `load`, `save`, `xml`, `set_xml`, `has_part`, dan `relationships`.

Aturan global:

1. **Satu load dan satu save.** Pipeline memanggil `load` setelah Pandoc dan
   `save` sebelum `office`. Stage tidak boleh memanggil keduanya untuk package
   target.
2. **Part non-target byte-identik.** Hanya part yang dideklarasikan stage yang
   boleh berubah. Part lain dipertahankan apa adanya, termasuk metadata ZIP.
3. **Perubahan XML diukur dengan c14n.** Dua hasil dianggap sama bila
   canonical XML dan SHA-256-nya sama.
4. **Save atomic.** Output ditulis ke file sementara di direktori tujuan, lalu
   `os.replace`.
5. **Tidak ada intermediate DOCX di direktori output.** DOCX antara hanya ada
   di workspace dan dihapus kecuali `--keep`.

## Modul

| Modul | Tanggung jawab |
| --- | --- |
| `package.py` | Model package, part, relationship, load/save. |
| `io.py` | Baca/tulis ZIP dan penulisan atomic. |
| `xml.py` | Parse, serialisasi, c14n, hash, helper elemen. |
| `names.py` | Namespace, tag, style, dan konstanta lain. |
| `paragraphs.py` | Akses `w:body`, child langsung, style dan level heading, teks paragraf, hapus child, atribut integer. |
| `runs.py` | Pembuatan, penyalinan, dan pembersihan `w:r`/`w:rPr`. |
| `numbering.py` | Konversi angka Romawi dan nomor bab. |
| `page.py` | Konstanta dan helper ukuran halaman. |
| `styles.py` | Style paragraf, karakter, tabel, dan page layout. |
| `sections.py` | Section break, margin, ukuran halaman, header/footer. |
| `captions.py` | Caption tabel/gambar, numbering, layout gambar. |
| `tables.py` | Tabel biasa, tabel kode, border, cell margin. |
| `layout.py` | Spasi, indentasi, perataan, bold, dan klasifikasi blok. |
| `fields.py` | TOC, PAGEREF, SEQ, PAGE, NUMPAGES. |
| `bookmarks.py` | Bookmark `pNNNN` dan verifikasi. |
| `terms.py` | Glosarium, style istilah, transformasi run, verifikasi. |

`heading_level(paragraph)` dan `paragraph_style_id(paragraph)` berada di
`paragraphs.py`, bukan `sections.py`. `sections.py` memakai helper tersebut untuk
mengenali heading batas section.

Penomoran heading Markdown sebelum Pandoc bukan tanggung jawab lapisan DOCX;
modulnya ada di `src/docgen/markdown/headings.py`.

## Part yang lazim berubah

| Part | Stage | Isi |
| --- | --- | --- |
| `word/document.xml` | sebagian besar stage | Isi, paragraf, tabel, field, bookmark. |
| `word/styles.xml` | `style_reference`, `terms`, `toc` | Definisi style. |
| `word/numbering.xml` | `numbering` | Definisi daftar. |
| `word/header*.xml`, `word/footer*.xml` | `page_numbers` | Field nomor halaman. |
| `word/_rels/document.xml.rels` | `page_numbers` | Relationship header/footer. |
| `[Content_Types].xml` | `page_numbers` | Content type part baru. |

Part lain tidak boleh berubah.

## Style

Style inti yang dipakai pipeline:

- `Normal`, `Heading1` sampai `Heading9`;
- `TOCHeading`, `TOC1`, `TOC2`, `TOC3`;
- `Caption`, `TableCaption`, `ImageCaption`, `Figure`;
- `Bibliography`, `SourceCode`, `VerbatimChar`, `HTMLCode`,
  `HTMLPreformatted`;
- `IstilahAsing`, `IstilahReview`;
- style sampul seperti `CoverTitle`, `CoverSubtitle`, `CoverName`,
  `CoverInstitution`, dan `CoverImage`.

`style_reference` menghasilkan `reference.docx` turunan dari `format.yml`.
Sumber `reference.docx` di `src/docgen/data/` tidak pernah ditimpa.

## Field

`fields.py` menulis field kompleks lengkap: `begin`, `instrText`, `separate`,
hasil, dan `end`. Pipeline tidak menulis cache nomor halaman palsu. Word atau
aplikasi yang membuka dokumen mengisi hasil field.

| Field | Dipakai untuk |
| --- | --- |
| `TOC \o "1-3" \h \z \u` | Daftar isi native di dalam `w:sdt`. |
| `TOC \c "Tabel"` | Daftar tabel. |
| `TOC \c "Gambar"` | Daftar gambar. |
| `SEQ Tabel \* ARABIC \s 1` | Nomor urut caption tabel per bab. |
| `SEQ Gambar \* ARABIC \s 1` | Nomor urut caption gambar per bab. |
| `PAGEREF` | Rujukan halaman bila diperlukan. |
| `PAGE` | Nomor halaman di header/footer. |
| `NUMPAGES` | Jumlah halaman bila diperlukan. |

Daftar tabel/gambar memakai hybrid: prefix bab literal dari caption, lalu field
`SEQ`. Detail keputusan ada di
[decisions/0007-seq-hybrid.md](decisions/0007-seq-hybrid.md).

## Bookmark dan manifest

Setiap paragraf body mendapat bookmark `pNNNN`, misalnya `p0001`. Bookmark
dipakai Adeu dan `reconcile` untuk mencocokkan paragraf DOCX dengan manifest.
Nama bookmark hanya boleh cocok dengan pola `p` diikuti minimal empat digit.

Manifest menyimpan:

- `version`, `docx`, dan daftar `paragraphs`;
- `id`, `index`, `kind`, `heading_path`;
- `text`, `text_sha256`;
- `protected`, `protected_reason`;
- `source_file`, `source_line` bila source scan aktif.

Manifest ditulis deterministik tanpa timestamp. Rincian ada di
[adeu-integration.md](adeu-integration.md).

## Caption dan tabel

- Tabel biasa diberi caption `Tabel bab.n` di atas tabel.
- Gambar diberi caption `Gambar bab.n` di bawah gambar.
- Alt text gambar menjadi sumber caption.
- Lebar gambar dibatasi 14 cm.
- Blok kode menjadi tabel 1x1 dengan border penuh.
- Caption wajib ada; tabel tanpa caption menggagalkan stage.

## Istilah

`terms.py` menyediakan:

- `load_glossary` dan `merge_glossaries`;
- `apply_terms` untuk style `IstilahAsing` dan `IstilahReview`;
- `verify_terms` untuk memeriksa invariant;
- `write_review_file` untuk `.laporan/istilah-baru.txt`.

Stage `terms` hanya berjalan dengan `--terms`. Rincian ada di
[terms.md](terms.md).

## Idempotensi

Stage yang memutasi DOCX harus idempoten. Dua run dengan input sama
menghasilkan:

- hash c14n `document.xml` yang sama;
- byte part non-target yang sama;
- output akhir yang sama.

`office` dan `pdf` tidak dijamin byte-identik karena Word dapat menulis ulang
package dan PDF membawa metadata ekspor. Keduanya diuji secara semantik.
