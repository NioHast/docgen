# ID Paragraf dan Bookmark Adeu

`tools/add_paragraph_ids.py` memberi setiap paragraf body DOCX sebuah
bookmark stabil `p0001`, `p0002`, dan seterusnya. Adeu memproyeksikan bookmark
itu menjadi penanda `{#nama}` sehingga komentar, diff, atau rujukan dapat
diarahkan ke paragraf yang sama meskipun dokumen sudah disunting di Word.

Alat ini hanya mengubah `word/document.xml`. Semua part lain (header, footer,
styles, numbering, media, relasi, dan properti dokumen) disalin byte-per-byte
dari DOCX asli.

Dependensi: `python-docx` dan `lxml` (lihat `requirements.txt`).
`pytest` hanya diperlukan untuk menjalankan tes.

## Perintah

Dari akar proyek:

```powershell
.venv\Scripts\python.exe tools\add_paragraph_ids.py Laporan.docx `
  --out-docx Laporan-ids.docx `
  --manifest Laporan-ids.json
```

Dengan pencocokan sumber Markdown (opsional):

```powershell
.venv\Scripts\python.exe tools\add_paragraph_ids.py Laporan.docx `
  --out-docx Laporan-ids.docx `
  --manifest Laporan-ids.json `
  --source-dir chapters
```

Di Linux/macOS gunakan `.venv/bin/python`.

Input tidak pernah ditimpa kecuali `--out-docx` memang menunjuk path yang sama;
penulisan dilakukan lewat file sementara lalu `os.replace`.

## Aturan bookmark

- Nama bookmark: `p0001`, `p0002`, dst., urut kemunculan paragraf di body.
  Nomor terus bertambah untuk paragraf di dalam tabel dan text box.
- Bookmark `w:bookmarkStart` disisipkan tepat setelah `w:pPr` (atau di awal
  paragraf bila tidak ada `w:pPr`), dan `w:bookmarkEnd` menjadi child terakhir
  paragraf. Dengan demikian bookmark membungkus isi paragraf, bukan properti
  paragraf.
- Header, footer, dan footnote tidak dihitung karena berada di part XML lain.
- Sebelum injeksi, semua bookmark body yang sudah bernama `pNNNN` dihapus.
  Alat dapat dijalankan berulang kali: nama dan urutan bookmark tetap sama,
  tidak ada nama atau `w:id` duplikat.
- `w:id` baru selalu dimulai di atas ID bookmark lain yang masih ada, sehingga
  bookmark TOC/PAGEREF milik Word tidak rusak.
- Teks, run, style, field, section, dan urutan elemen tidak diubah.

## Manifest

Manifest ditulis sebagai JSON UTF-8:

```json
{
  "version": 1,
  "docx": "Laporan-ids.docx",
  "built_at": "2026-11-06T15:04:05+00:00",
  "paragraphs": [
    {
      "id": "p0001",
      "index": 0,
      "kind": "heading",
      "heading_path": ["BAB I PENDAHULUAN"],
      "text": "BAB I PENDAHULUAN",
      "text_sha256": "…",
      "protected": false,
      "protected_reason": null
    }
  ]
}
```

- `id`: nama bookmark, selalu `p` + sedikitnya empat digit.
- `index`: indeks paragraf body, mulai dari 0, termasuk paragraf tabel.
- `kind`: `heading`, `body`, `table`, `caption`, `toc`, `bibliography`, atau
  `cover`.
- `heading_path`: teks heading terakhir per level pada saat paragraf muncul.
  Heading yang sedang dibaca sudah termasuk dalam path-nya sendiri. Level yang
  lebih dalam dari heading baru dipotong.
- `text`: teks paragraf yang terlihat. Tab dan line break menjadi `\t`/`\n`;
  kode field (`w:instrText`) dan teks terhapus tidak ikut.
- `text_sha256`: SHA-256 dari `text` yang di-encode UTF-8.
- `protected`: `true` bila paragraf tidak boleh dijadikan target komentar Adeu.
- `protected_reason`: alasan singkat, atau `null`.

Bila `--source-dir` diberikan, setiap entri juga mendapat `source_file` dan
`source_line`. Tanpa opsi itu, kedua kunci tidak ditulis agar bentuk manifest
tetap sama dengan kontrak dasar.

### Deteksi `kind`

Urutan pemeriksaan:

1. `w:pStyle` `Heading1` … `Heading9` → `heading`.
2. `ImageCaption`, `TableCaption`, atau `Caption` → `caption`.
3. `Bibliography` → `bibliography`.
4. `Title` atau style berawalan `Cover` → `cover`.
5. Style berawalan `TOC` (mis. `TOC1`, `TOCHeading`) → `toc`.
6. Paragraf di dalam field TOC → `toc`.
7. Paragraf di dalam `w:tbl` → `table`.
8. Sisanya → `body`.

Style semantik (heading, caption, bibliography, cover, TOC) diprioritaskan di
atas posisi tabel. Paragraf biasa di dalam tabel tetap mendapat `table`.

### Proteksi

`protected` bernilai `true` bila salah satu kondisi berikut terpenuhi.
`protected_reason` memakai alasan pertama yang cocok:

| Kondisi | `protected_reason` |
| --- | --- |
| Berada di dalam field `TOC` | `toc_field` |
| Mengandung `w:sectPr` | `sectpr` |
| Mengandung field `SEQ` | `seq_field` |
| Mengandung field `PAGEREF` | `pageref_field` |
| Mengandung field `PAGE` | `page_field` |
| `kind` caption | `caption_style` |
| `kind` toc dari style TOC | `toc_style` |
| `kind` bibliography | `bibliography` |
| `kind` cover | `cover_style` |

Field kompleks dilacak dari `w:fldChar` (`begin`/`separate`/`end`) dan
`w:instrText`, termasuk field yang membentang beberapa paragraf seperti TOC.
Field sederhana `w:fldSimple` juga dikenali. `SEQ`, `PAGEREF`, dan `PAGE`
dibedakan sebagai nama field, jadi `PAGEREF` tidak salah dianggap `PAGE`.

## Pencocokan `--source-dir`

Pencocokan dilakukan konservatif:

- Semua `*.md` di bawah direktori sumber dibaca, lalu heading dan blok paragraf
  dipetakan ke `(heading_path, teks ternormalisasi)`.
- Penomoran heading umum dibuang agar `1.1. Latar Belakang` di DOCX cocok
  dengan `## Latar Belakang` di Markdown; `BAB I PENDAHULUAN` juga dinormalkan.
- Markup inline sederhana (penekanan, code span, tautan) dinormalkan.
- Sebuah paragraf hanya diberi sumber bila kuncinya cocok **tepat satu kali**
  di seluruh direktori sumber. Jika nol atau lebih dari satu kandidat, kedua
  nilai dibiarkan `null`.
- `source_file` ditulis relatif terhadap `--source-dir` dengan pemisah `/`.
- `source_line` adalah nomor baris 1-based tempat blok dimulai.

Transformasi Pandoc yang kompleks (mis. sitasi `[@kunci]` yang sudah menjadi
teks sitasi author-date, persamaan, atau caption otomatis) tidak ditebak. Paragraf seperti itu
tetap `null`.

## Jaminan dan batasan

- Tes membandingkan hash semua part ZIP kecuali `word/document.xml`; part lain
  harus identik.
- Teks dan style paragraf dipertahankan. Perbandingan canonical XML setelah
  bookmark `pNNNN` dihapus juga harus sama dengan input.
- Hasil dapat dibuka `python-docx` dan lolos `zipfile.testzip()`.
- Versi ini belum memberi ID pada paragraf header/footer/footnote, gambar,
  komentar, atau catatan kaki di part terpisah.
- Bookmark hanya diberi nama `pNNNN`; bookmark lain tidak diubah.

## Tes

```powershell
.venv\Scripts\python.exe -m pytest tests\test_paragraph_ids.py -v
```

Fixture dibuat oleh `tests/fixtures/paragraph_ids/make_fixture.py` dengan
`python-docx`, bukan dari `Laporan.docx`.
