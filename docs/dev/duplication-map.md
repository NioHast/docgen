# Peta Duplikasi DOCX

**Tanggal:** 2026-11-09
**Ruang lingkup:** `src/docgen/docx/**` dan `src/docgen/stages/**`
**Status:** sebagian sudah dipusatkan, sisanya utang.
**Sifat:** peta kerja berbasis inspeksi aktual, bukan rencana refactor yang
sudah selesai.

Dokumen ini memetakan pola `lxml`/WordprocessingML yang berulang setelah port
ke `docgen`. Tujuannya bukan menghapus semua kemiripan, tetapi menyatukan
pola yang menyentuh invariant yang sama: akses body, klasifikasi paragraf,
pembacaan field, pembuatan run, dan penomoran. Duplikasi yang hanya berupa
diagnostik lokal stage boleh tetap ada.

## 1. Ringkasan

- Sumber yang diperiksa: 14 berkas `src/docgen/docx/*.py` dan 19 berkas
  `src/docgen/stages/*.py`.
- Pusat yang sudah ada: `docx/xml.py` (parse, qn, serialize, c14n,
  `paragraph_text`, `ensure_ppr`/`ensure_rpr`, `insert_ordered`, `get_or_add`,
  `is_on`), `docx/names.py` (konstanta dan normalisasi style),
  `docx/fields.py` (parser/builder field), dan `docx/package.py` (satu
  load/save).
- Utang terbesar: akses `w:body` yang disalin di 7 tempat, pembacaan style
  paragraf di 8 tempat, parser field kedua di `docx/layout.py`, dan pembuat
  run yang tersebar di 7 modul.
- `docx/runs.py`, `docx/paragraphs.py`, dan `docx/numbering.py` belum ada.
  `docx/fields.py` sudah ada, tetapi belum menjadi satu-satunya parser field.

## 2. Yang sudah terpusat

| Komponen | Isi | Dipakai konsisten |
|---|---|---|
| `src/docgen/docx/xml.py` | `qn`, `parse_xml`, `serialize_xml`, `canonicalize_xml`, `sha256_c14n`, `iter_paragraphs`, `paragraph_text`, `ensure_ppr`, `ensure_rpr`, `insert_ordered`, `get_or_add`, `is_on` | Sebagian. Stage masih mendefinisikan konstanta `qn()` lokal dan beberapa modul menyalin pembacaan teks/style. |
| `src/docgen/docx/names.py` | Konstanta `W_*`, normalisasi style, predikat heading/caption/code/cover | Sebagian. `stages/blank_lines.py`, `stages/equations.py`, dan `stages/numbering.py` masih membuat konstanta `qn()` sendiri. |
| `src/docgen/docx/fields.py` | Parser `w:fldChar`/`w:fldSimple`, `insert_toc`, `insert_seq`, `insert_pageref` | Sebagian. `docx/layout.py` punya parser field paralel; `terms`, `captions`, `lists`, `blank_lines`, dan `page_numbers` masih membaca atau menulis field sendiri. |
| `src/docgen/docx/package.py` | Satu pemilik ZIP/OPC, load/save atomic | Ya untuk package target. |
| `src/docgen/docx/tables.py` | Border, margin, tabel kode 1x1, normalisasi tabel | Ya untuk tabel, tetapi helper run/teks di dalamnya masih lokal. |

## 3. Pola `lxml` berulang

Angka "mirip" berasal dari AST + `difflib.SequenceMatcher` pada body fungsi.
Angka ini indikatif, bukan clone detector penuh.

| # | Pola | Lokasi aktual | Bukti | Status | Komponen target | Prioritas |
|---:|---|---|---|---|---|---|
| 1 | Akses `w:body` | `_body` di `docx/bookmarks.py:77`, `docx/captions.py:257`, `docx/fields.py:322`, `docx/sections.py:133`, `stages/lists.py:74`; `document_body` di `docx/layout.py:686` dan `docx/tables.py:283` | 7 definisi, 8-11 baris; kemiripan 0,88-0,97 pada pasangan `_body` | Utang | `docx/paragraphs.py`: `document_body(package)`, `iter_body_children(body)` | P0 |
| 2 | Baca style/level paragraf | `paragraph_style_id` di `docx/bookmarks.py:94`, `docx/layout.py:269`, `docx/terms.py:401`; `_paragraph_style_id` di `docx/captions.py:279`, `docx/tables.py:304`; `_paragraph_style` di `docx/fields.py:336`, `docx/sections.py:159`; `_style` di `stages/sections.py:73` | 8 pembaca style; `captions` dan `tables` identik 1,00; pasangan lain 0,67-0,86 | Utang | `docx/paragraphs.py`: `paragraph_style_id`, `heading_level`, `is_heading` | P0 |
| 3 | Parser field paralel | `docx/fields.py:133-209`; `docx/layout.py:289-436` (`iter_field_markers`, `iter_field_instructions`, `has_field`, `has_exempt_field`, `iter_field_runs`, `is_field_run`); `docx/terms.py:444-555` (`build_paragraph_model`); `docx/captions.py:312-346` (`_field_ranges`); `stages/lists.py:94-99` dan `258-327`; `stages/blank_lines.py:187-191`; `stages/page_numbers.py:66-85` | Parser field kedua sekitar 145 baris; walker field lain sekitar 250-300 baris; field PAGE ditulis manual | Sebagian terpusat di `fields.py`, sisanya utang | `docx/fields.py`: satu parser, `field_name`, `iter_field_runs`, `insert_page_field`, helper `w:sdt` | P0 |
| 4 | Pembuatan run dan clone `rPr` | `docx/fields.py:269-293` (`_append_run`); `docx/sections.py:1043-1061` (`_run_with_text`, `_run_with_break`); `stages/lists.py:214-228` (`_new_run`, `_apply_rpr`); `docx/captions.py:421-426` (`_append_text`); `docx/terms.py:807-857`; `stages/page_numbers.py:66-85` (`_append_page_run`); `docx/tables.py:836-894` | 7 pembuat run; `deepcopy` run/`rPr` 10 kali di `sections`, `terms`, `lists`, `page_numbers` | Utang | `docx/runs.py`: `make_run`, `append_text_run`, `clone_run`, `copy_rpr`, `set_text` | P0 |
| 5 | Hapus/toggle bold | `docx/layout.py:444-515` (`_toggle_is_on`, `is_bold_run`, `has_bold_field`, `strip_bold_from_rpr`, `strip_bold_from_run`, `strip_paragraph_bold`); `stages/numbering.py:171-197` (`_strip_bold_from_rpr_local`, `_strip_paragraph_bold`); `docx/xml.py:597` (`is_on`) | Pasangan `strip_bold_from_rpr` vs `_strip_bold_from_rpr_local` mirip 0,72; aturan nilai `none` dan `0/false/off` tidak identik | Sebagian (`xml.is_on`), sisanya utang | `docx/runs.py`: `is_bold`, `strip_bold_from_rpr`, `strip_paragraph_bold` | P0 |
| 6 | Konversi Romawi dan nomor bab | `docx/captions.py:953-981` (`_roman_to_int`, `_chapter_number`); `docx/layout.py:581-607` (`roman_to_int`, `chapter_number`) | `roman_to_int` mirip 0,90; `chapter_number` punya kebutuhan berbeda tetapi sumber logika sama | Utang | `docx/numbering.py`: `roman_to_int`, `chapter_number`, `format_chapter_number` | P1 |
| 7 | Setter `pPr`: spacing, indent, tab | `stages/equations.py:191-233` (`_set_right_tab`, `_set_spacing`, `_set_indent`, `_set_justification`); `docx/layout.py:777-809` dan `preserve_tabs`; `stages/numbering.py:200-232` (`_set_indentation`, `_set_tab_stop`); `docx/styles.py` (`_spacing_patch`, `_indent_patch`) | 4 kelompok setter dengan urutan child dan pembersihan atribut yang mirip | Utang | `docx/paragraphs.py`: `set_spacing`, `set_indent`, `set_tabs`, `set_alignment` | P1 |
| 8 | Ekstraksi teks paragraf | `docx/xml.py:487` (`paragraph_text`); `docx/sections.py:177` (`_text`); `docx/fields.py:332` (`_normalized_text`); `stages/sections.py:89` (`_paragraph_text`); `docx/captions.py:308` (`_caption_text`); `docx/terms.py:444-555` (model teks) | 5-6 varian; sebagian memanggil `paragraph_text`, sebagian traversal sendiri | Sebagian | `docx/paragraphs.py`: `paragraph_text`, `normalized_text`, `iter_text_nodes` | P1 |
| 9 | Fragmen OOXML mentah | `stages/toc.py:79-176` (71 literal `<w:`); `stages/front_matter.py:48`, `106-128`, `192-215` (14 literal `<w:`); `docx/headings.py` (raw inline `<w:br/>`/`<w:tab/>`) | 85+ literal XML; style TOC ditulis sebagai string, bukan `StyleSpec` | Utang | `docx/styles.py` untuk style TOC; `docx/paragraphs.py`/`docx/xml.py` untuk page break, spacer, section break | P2 |
| 10 | Konstanta `qn()` lokal di stage | `stages/blank_lines.py` 25, `stages/equations.py` 26, `stages/numbering.py` 25, `stages/lists.py` 9 | 85 pemanggilan `qn()` di stage; `docx/names.py` sudah menyediakan konstanta | Sebagian | `docx/names.py` sebagai satu sumber konstanta | P2 |
| 11 | `_remove_direct_children` | `docx/captions.py:274`, `docx/tables.py:299` | Identik 1,00 | Utang | `docx/paragraphs.py` | P2 |
| 12 | `_int_attribute` | `docx/captions.py:586`, `docx/layout.py:889`, `docx/tables.py:741`, `stages/numbering.py:146` | 4 definisi, 8-12 baris; kemiripan 0,73-1,00 | Utang | `docx/xml.py`: `int_attribute` | P2 |
| 13 | `new_element` | `docx/layout.py:263`, `docx/tables.py:295` | 2 definisi; kemiripan 0,68 | Utang | `docx/xml.py`: `new_element` | P2 |

## 4. Kandidat komponen reusable

### 4.1 `docx/runs.py` (belum ada, P0)

Isi yang disarankan:

- `make_run(*, text: str | None = None, rpr: etree._Element | None = None)`.
- `append_text_run(paragraph, text, *, rpr=None, preserve_space=True)`.
- `clone_run(run)`, `copy_rpr(rpr)`, `set_text(run, text)`.
- `is_bold(run)`, `strip_bold_from_rpr(rpr)`, `strip_paragraph_bold(paragraph,
  *, exempt_fields=True)`.
- `iter_runs(paragraph)` boleh tetap di `docx/xml.py`; `runs.py` hanya
  membungkus pembuatan dan mutasi run.

Alasan P0: `terms`, `numbering`, `layout`, `captions`, `lists`, dan
`page_numbers` harus memakai aturan bold/`rPr` yang sama. Perbedaan kecil
pada `w:val="none"` atau `w:val="0"` bisa mengubah hasil verify istilah dan
bold field exempt.

### 4.2 `docx/paragraphs.py` (belum ada, P0)

Isi yang disarankan:

- `document_body(package)`, `iter_body_children(body)`.
- `paragraph_style_id(paragraph)`, `heading_level(paragraph)`,
  `is_heading(paragraph)`.
- `paragraph_text(paragraph)`, `normalized_text(paragraph)`.
- `new_paragraph(style=None)`.
- `remove_direct_children(parent, tag)`.
- `set_spacing`, `set_indent`, `set_tabs`, `set_alignment` (P1, boleh
  diiterasi setelah P0).

Alasan P0: akses body dan klasifikasi style adalah dasar `sections`,
`captions`, `fields`, `bookmarks`, dan `lists`. Delapan pembaca style yang
berbeda membuat aturan "Heading1", "ImageCaption", dan "SourceCode" berisiko
divergen.

### 4.3 `docx/fields.py` (ada, P0 untuk konsolidasi)

Isi yang disarankan:

- Pertahankan parser yang sudah ada (`iter_fields`, `iter_fields_in_paragraph`,
  `field_kind`, `field_result_text`).
- Pindahkan `iter_field_markers`, `iter_field_instructions`, `field_name`,
  `has_exempt_field`, `iter_field_runs`, dan `is_field_run` dari
  `docx/layout.py` ke `fields.py` atau jadikan `layout.py` memanggil
  `fields.py`.
- Tambah `insert_page_field` atau builder field generik agar
  `stages/page_numbers.py` tidak menulis `fldChar`/`instrText` manual.
- Tambah helper `w:sdt` (`sdt_gallery`, `sdt_instruction`, `set_sdt_id`) agar
  `stages/lists.py` dan `docx/fields.py` memakai satu implementasi.
- Ganti walker field di `terms.py`, `captions.py`, `blank_lines.py`, dan
  `lists.py` dengan API `fields.py` bila hasilnya setara.

Alasan P0: `layout` memakai parser field untuk menentukan bold exempt,
sedangkan `terms` memakai walker sendiri untuk melewati field. Jika keduanya
berbeda, teks yang dianggap field oleh satu stage bisa dianggap teks biasa oleh
stage lain.

### 4.4 `docx/numbering.py` (belum ada, P1)

Isi yang disarankan:

- `roman_to_int(token)`, `format_chapter_number(value, style)`.
- `chapter_number(paragraph_text)`.
- `parse_heading_level(style_id)`.
- `set_numbering_indent(ppr, left, hanging)`, `set_tab_stop(ppr, position)`.

Alasan P1: duplikasi `roman_to_int` antara `captions` dan `layout` sudah
mirip 0,90. Nomor caption dan nomor bab harus memakai konversi yang sama,
terutama untuk angka Romawi seperti `IV`/`IX` dan heading `BAB 2`.

## 5. Prioritas kerja

### P0 - invariant dan risiko perilaku

1. Buat `docx/paragraphs.py` dan migrasikan 7 akses body serta 8 pembaca
   style/level.
2. Konsolidasikan parser field ke `docx/fields.py`; hapus parser paralel di
   `docx/layout.py` setelah semua pemanggil dimigrasikan.
3. Buat `docx/runs.py` dan migrasikan pembuatan run, clone `rPr`, serta
   aturan bold.
4. Tambah guard test yang gagal jika `_body`, `paragraph_style_id`, atau
   `strip_bold_from_rpr` didefinisikan ulang di luar modul pusat.

Acceptance P0: semua tes lama lulus tanpa perubahan perilaku; tidak ada
perubahan output canonical `document.xml`; satu implementasi untuk body,
style, field, dan bold.

### P1 - konsistensi penomoran dan layout

1. Buat `docx/numbering.py`; migrasikan konversi Romawi/nomor bab.
2. Pindahkan setter `pPr` ke `docx/paragraphs.py`; `equations` dan
   `numbering` memanggil helper yang sama.
3. Satukan ekstraksi teks paragraf ke `docx/paragraphs.py`; sisakan
   `paragraph_text` di `docx/xml.py` sebagai primitif.

Acceptance P1: tidak ada definisi `roman_to_int`, `_set_spacing`, atau
`_set_indentation` di stage; tes caption/equation/numbering tetap lulus.

### P2 - kebersihan dan sumber tunggal

1. Ganti fragmen OOXML mentah di `stages/toc.py` dengan `StyleSpec`/
   `docx/styles.py`; bangun page break/spacer/section break lewat helper
   paragraf.
2. Impor konstanta dari `docx/names.py`; hapus konstanta `qn()` lokal di
   stage.
3. Pindahkan `_remove_direct_children`, `_int_attribute`, dan
   `new_element` ke `docx/xml.py`/`docx/paragraphs.py`.

Acceptance P2: tidak ada literal `<w:style` di stage; tidak ada konstanta
`W_* = qn(...)` baru di stage; tidak ada helper XML generik yang disalin.

## 6. Batas dan gap

- Belum ada clone detector formal. Angka kemiripan berasal dari AST dan
  `difflib` pada body fungsi; baris yang mirip tetapi berbeda semantik tidak
  otomatis dianggap duplikat.
- Peta ini tidak mengubah kode dan tidak menghapus duplikasi. Status
  "utang" berarti belum dikerjakan.
- `docx/runs.py`, `docx/paragraphs.py`, dan `docx/numbering.py` belum ada.
  Hanya `docx/fields.py` yang sudah ada.
- Beberapa kemiripan sengaja dipertahankan: pesan error stage, klasifikasi
  blok `blank_lines`, dan diagnostik `captions` tidak harus dipaksa masuk
  helper generik.
- Setelah refactor, ukur ulang dengan perintah di bagian 7 dan perbarui tabel
  ini. Jangan mengklaim LOC turun tanpa pengukuran baru.

## 7. Perintah inspeksi yang dipakai

```bash
grep -RIn "def _body\|def document_body" src/docgen/docx src/docgen/stages
grep -RIn "def paragraph_style_id\|def _paragraph_style\|def _style" src/docgen/docx src/docgen/stages
grep -RIn "def .*field\|W_FLDCHAR\|W_INSTRTEXT\|fldChar\|instrText" src/docgen/docx src/docgen/stages
grep -RIn "def _append_run\|def _new_run\|def _run_with_text\|def _append_page_run\|W_R\b" src/docgen/docx src/docgen/stages
grep -RIn "def .*roman\|def .*chapter_number\|def _int_attribute\|def .*strip_bold" src/docgen/docx src/docgen/stages
grep -RIn "<w:" src/docgen/stages src/docgen/docx
```

Inspeksi silang memakai skrip Python AST + `difflib` untuk membandingkan body
fungsi dengan nama yang sama atau setara. Hasilnya diringkas di tabel bagian 3.

## 8. Rujukan

- [Kontrak API DOCX](contracts/docx-api.md)
- [Kontrak Stage API](contracts/stage-api.md)
- [Arsitektur](architecture.md)
- [Panduan testing](testing.md)
- [Rencana restrukturisasi](restructure-plan.md)
