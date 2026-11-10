# Arsitektur

`docgen` memisahkan naskah, aturan tampilan, urutan struktur, dan orkestrasi.
Satu `document.md` adalah sumber konten. Format dan struktur adalah data paket
yang dibaca saat runtime. Pipeline Python mengubah Markdown menjadi DOCX dalam
satu pass package, lalu opsional mengekspor PDF lewat Word.

## Lapisan

| Lapisan | Lokasi | Tanggung jawab | Tidak boleh berisi |
| --- | --- | --- | --- |
| Konten | `document.md`, `references.bib`, `istilah.tsv`, `gambar/` | Teks, sitasi, glosarium tambahan, dan aset | Aturan margin, urutan bab, field Word |
| Struktur | `src/docgen/data/structures/<id>/structure.yml` | Urutan front matter, body, back matter, penomoran, TOC, daftar, cover | Nilai margin, font, CSL |
| Format | `src/docgen/data/formats/<id>/format.yml` | Halaman, font, heading, caption, kode, sitasi, aset visual | Teks naskah, urutan bab |
| Pipeline | `src/docgen/` | Validasi, orkestrasi stage, mutasi DOCX, output, manifest | Teks naskah, salinan aturan format |

ID format dan struktur adalah nama direktori. Skema keduanya tertutup: kunci
yang tidak dikenal ditolak dengan pesan error.

## Data flow

```text
document.md
  |
  +-- validate             front matter, aset, caption Markdown
  +-- mermaid              blok Mermaid menjadi PNG di workspace
  +-- style_reference      reference.docx turunan dari format.yml
  +-- front_matter         sampul, template, abstrak, nomor heading
  +-- pandoc               Markdown menjadi DOCX
  |
  +-- package DOCX di memori
  |     +-- sections
  |     +-- code
  |     +-- captions
  |     +-- normalize
  |     +-- equations
  |     +-- numbering
  |     +-- blank_lines
  |     +-- terms
  |     +-- toc
  |     +-- page_numbers
  |     +-- lists
  |     +-- Adeu hook
  |
  +-- save satu kali
  +-- office               Word memperbarui field dan menyimpan DOCX
  +-- pdf                  Word mengekspor PDF, Windows only
```

Urutan stage ditegakkan oleh `pipeline.py`. Stage tidak boleh memanggil
`load` atau `save` package target. Detail kontrak ada di
[contracts/stage-api.md](contracts/stage-api.md).

## Invariant utama

1. **Satu sumber konten.** Hanya `document.md` dan asetnya yang menjadi
   sumber. DOCX dan PDF adalah artefak.
2. **Satu load dan satu save.** `DocumentPackage` dimuat sekali setelah Pandoc
   dan disimpan sekali sebelum `office`. Semua stage bekerja pada package di
   memori.
3. **Urutan kanonik.** Stage berjalan dengan urutan tetap dan guard keras.
   Stage yang salah urutan menggagalkan pipeline.
4. **Part non-target byte-identik.** Stage hanya memutasi part yang
   dideklarasikan. Part lain tidak berubah.
5. **Output di samping dokumen.** Output pengguna ditulis di direktori
   `document.md`. Contoh repo memakai `examples/<name>/out/`. Tidak ada
   `build/` atau `review/`.
6. **Manifest deterministik.** Manifest Adeu tidak memuat timestamp dan
   diurutkan stabil. `text_sha256` dihitung dari teks final.
7. **Data paket mandiri.** `src/docgen/paths.py` membaca data dari paket dan
   tidak memiliki fallback ke direktori kerja.

## Package DOCX

`src/docgen/docx/` adalah satu-satunya pemilik ZIP dan XML Word:

- `package.py`: model `DocumentPackage`, load, save, part, relationship.
- `io.py`: baca dan tulis ZIP secara atomic.
- `xml.py`: parse, serialisasi, c14n, hash, helper XML.
- `names.py`: konstanta namespace dan style.
- `styles.py`: style paragraf, karakter, dan tabel.
- `sections.py`: section, margin, ukuran halaman, heading numbering.
- `captions.py`: caption tabel/gambar, numbering, layout gambar.
- `tables.py`: tabel biasa dan tabel kode.
- `layout.py`: normalisasi spacing, indentasi, perataan, bold.
- `fields.py`: TOC, PAGEREF, SEQ, PAGE, NUMPAGES.
- `bookmarks.py`: bookmark `pNNNN`.
- `terms.py`: glosarium dan transformasi istilah.

Dokumen rinci ada di [docx.md](docx.md) dan
[contracts/docx-api.md](contracts/docx-api.md).

## CLI dan entry point

`pyproject.toml` mendaftarkan `docgen = "docgen.cli:main"`. Perintah yang
tersedia:

```bash
uv run --project <repo> docgen check <document.md>
uv run --project <repo> docgen build <document.md> [opsi]
uv run --project <repo> docgen doctor
uv run --project <repo> docgen reconcile <document.md>
```

Tidak ada perintah `new` atau `list`. Dokumen baru dibuat dengan menyalin
contoh atau menulis front matter sendiri.

## Platform

| Platform | DOCX | PDF | Catatan |
| --- | --- | --- | --- |
| Windows | ya | ya dengan Word | Word memperbarui field dan mengekspor PDF. |
| Debian/Linux | best-effort | tidak | Pandoc dan stage Python berjalan; field tidak difinalkan Word. |

Aturan target dijelaskan di [pdf.md](pdf.md).

## Batasan arsitektur

- Tidak ada mode folder atau file bab terpisah.
- Tidak ada filter Lua. Perilaku lama diport ke stage Python.
- Tidak ada mesin PDF selain Microsoft Word.
- Build hanya memakai pipeline Python; tidak ada jalur shell atau fallback lama.
- TOC dan daftar memakai field native; Word perlu memperbarui field.
