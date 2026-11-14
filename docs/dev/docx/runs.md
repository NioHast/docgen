# Helper Run

Halaman ini menjelaskan helper kanonis pembuatan, penyalinan, dan pembersihan
run WordprocessingML. Kontrak ada di
[contracts/docx.md](../../contracts/docx.md).

`runs.py` menyatukan:

- `build_run` dan `make_run`;
- `append_text_run`;
- `clone_run` dan `copy_rpr`;
- `strip_bold_from_rpr`.

Modul DOCX dan stage memakai API ini agar struktur `w:r`/`w:rPr` konsisten,
tanpa bergantung pada `python-docx` atau traversal lxml milik masing-masing
pemanggil. Semua fungsi memutasi elemen lxml yang diberikan; tidak ada akses
package atau berkas di sini.

## Referensi resmi

Label registry yang dipakai halaman ini: `WordprocessingML API reference`,
`python-docx documentation`. URL resminya ada di
[registry referensi](../references.md).

## Halaman terkait

- [paragraphs.md](paragraphs.md) untuk helper paragraf.
- [fields.md](fields.md) untuk run di dalam field.
- [captions.md](captions.md) untuk run caption.
- [package.md](package.md) untuk aturan mutasi package.
