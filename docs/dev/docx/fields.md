# Field

Halaman ini menjelaskan field WordprocessingML yang ditulis pipeline.
Kontrak ada di [contracts/docx-api.md](../contracts/docx-api.md).

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
[../decisions/0007-seq-hybrid.md](../decisions/0007-seq-hybrid.md).

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [captions.md](captions.md) untuk caption dan `SEQ`.
- [bookmarks.md](bookmarks.md) untuk bookmark paragraf.
- [sections.md](sections.md) untuk field nomor halaman.
- [../pipeline/stages.md](../pipeline/stages.md) untuk stage `toc`,
  `page_numbers`, dan `lists`.
