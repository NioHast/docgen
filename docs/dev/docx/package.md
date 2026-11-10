# Model Package

Halaman ini menjelaskan `DocumentPackage`, part, relationship, dan aturan
global yang berlaku untuk semua modul DOCX. Kontrak lengkap ada di
[contracts/docx-api.md](../contracts/docx-api.md).

## Model package

`DocumentPackage` memiliki:

- daftar part dengan byte asli dan `ZipInfo`;
- XML yang sudah diparse untuk part yang dimutasi;
- relationship per part;
- operasi `load`, `save`, `xml`, `set_xml`, `has_part`, dan `relationships`.

## Aturan global

1. **Satu load dan satu save.** Pipeline memanggil `load` setelah Pandoc dan
   `save` sebelum `office`. Stage tidak boleh memanggil keduanya untuk package
   target. Model lengkap ada di
   [../pipeline/overview.md](../pipeline/overview.md#satu-load-dan-satu-save).
2. **Part non-target byte-identik.** Hanya part yang dideklarasikan stage yang
   boleh berubah. Part lain dipertahankan apa adanya, termasuk metadata ZIP.
3. **Perubahan XML diukur dengan c14n.** Dua hasil dianggap sama bila
   canonical XML dan SHA-256-nya sama.
4. **Save atomic.** Output ditulis ke file sementara di direktori tujuan, lalu
   `os.replace`.
5. **Tidak ada intermediate DOCX di direktori output.** DOCX antara hanya ada
   di workspace dan dihapus kecuali `--keep`.

## Part yang lazim berubah

| Part | Stage | Isi |
| --- | --- | --- |
| `word/document.xml` | sebagian besar stage | Isi, paragraf, tabel, field, bookmark. |
| `word/styles.xml` | `style_reference`, `terms`, `toc` | Definisi style. |
| `word/numbering.xml` | `numbering` | Definisi daftar. |
| `word/header*.xml`, `word/footer*.xml` | `page_numbers` | Field nomor halaman. |
| `word/_rels/document.xml.rels` | `page_numbers` | Relationship header/footer. |
| `[Content_Types].xml` | `page_numbers` | Content type part baru. |

Part lain tidak boleh berubah. Matriks lengkap ada di
[contracts/docx-api.md](../contracts/docx-api.md).

## Idempotensi package

Stage yang memutasi DOCX harus idempoten. Dua run dengan input sama
menghasilkan:

- hash c14n `document.xml` yang sama;
- byte part non-target yang sama;
- output akhir yang sama.

`office` dan `pdf` tidak dijamin byte-identik karena Word dapat menulis ulang
package dan PDF membawa metadata ekspor. Keduanya diuji secara semantik.
Definisi pipeline ada di
[../pipeline/overview.md](../pipeline/overview.md#idempotensi).

## Referensi resmi

Label registry yang dipakai halaman ini: `OOXML ECMA-376`, `Open XML SDK`.
URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [overview.md](overview.md) untuk peta modul.
- [../pipeline/artifacts.md](../pipeline/artifacts.md) untuk workspace.
- [fields.md](fields.md) dan [bookmarks.md](bookmarks.md) untuk part yang
  sering dimutasi.
