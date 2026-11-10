# Pipeline

`Pipeline.run(document_path, options)` memuat `document.md`, menjalankan stage
dengan urutan kanonik, menyimpan package DOCX satu kali, lalu menjalankan
finalisasi Word dan PDF bila diminta. Kontrak lengkap ada di
[contracts/stage-api.md](contracts/stage-api.md).

## Urutan stage

| Order | Stage | Modul | Memutasi | Catatan |
| ---: | --- | --- | --- | --- |
| 10 | `validate` | `stages/validate.py` | - | Caption tabel dan alt text gambar. |
| 20 | `mermaid` | `stages/mermaid.py` | workspace | Blok Mermaid menjadi PNG. |
| 30 | `style_reference` | `stages/style_reference.py` | workspace, cache | `reference.docx` turunan dari `format.yml`. |
| 35 | `front_matter` | `stages/front_matter.py` | workspace | Sampul, template, abstrak, nomor heading. |
| 40 | `pandoc` | `stages/pandoc.py` | package | Markdown menjadi DOCX. |
| 50 | `sections` | `stages/sections.py` | `word/document.xml` | Section break, margin, ukuran halaman, nomor heading DOCX. |
| 60 | `code` | `stages/code.py` | `word/document.xml` | Blok kode menjadi tabel 1x1. |
| 70 | `captions` | `stages/captions.py` | `word/document.xml` | Caption wajib, nomor bab, layout gambar. |
| 80 | `normalize` | `stages/normalize.py` | `word/document.xml` | Spasi 1,5, justify, hapus bold body. |
| 90 | `equations` | `stages/equations.py` | `word/document.xml` | Nomor persamaan `(bab.n)`. |
| 100 | `numbering` | `stages/numbering.py` | `word/document.xml`, `word/numbering.xml` | Indentasi daftar. |
| 110 | `blank_lines` | `stages/blank_lines.py` | `word/document.xml` | Paragraf kosong sesuai aturan layout. |
| 120 | `terms` | `stages/terms.py` | `word/document.xml`, `word/styles.xml` | Hanya aktif dengan `--terms`. |
| 130 | `toc` | `stages/toc.py` | `word/document.xml`, `word/styles.xml` | Field TOC native bila `structure.toc`. |
| 140 | `page_numbers` | `stages/page_numbers.py` | document, header/footer, rels, content types | Romawi front matter, Arab body. |
| 150 | `lists` | `stages/lists.py` | `word/document.xml` | Daftar tabel/gambar dan field `SEQ`. |
| 160 | `office` | `stages/office.py` | package | Word memperbarui field dan menyimpan DOCX. |
| 170 | `pdf` | `stages/pdf.py` | - | Word mengekspor PDF, Windows only. |

Guard utama:

- `style_reference` sebelum `front_matter`;
- `front_matter` sebelum `pandoc`;
- `sections` sebelum `code`, lalu `captions`, `normalize`, `equations`;
- `terms` sebelum `toc`, `toc` sebelum `page_numbers`, `page_numbers` sebelum
  `lists`;
- `office` sebelum `pdf`.

Stage yang salah urutan, duplikat, atau memutasi part tidak dikenal
menggagalkan `validate_stage_order`.

## Satu load dan satu save

- `pandoc` membuat package DOCX di workspace.
- `Pipeline` memuat package itu tepat satu kali.
- Semua stage sebelum `office` memutasi package di memori.
- Adeu hook menambahkan bookmark dan menyiapkan manifest di memori.
- `Pipeline` memanggil `save` tepat satu kali.
- Manifest ditulis setelah save.
- `office` dan `pdf` berjalan setelah save.

Stage tidak boleh memanggil `load` atau `save` target. `style_reference` boleh
memuat dan menyimpan `reference.docx` karena objeknya berbeda.

## Adeu hook

Adeu bukan stage kanonik, tetapi hook di dalam pass package:

1. Setelah `lists` dan sebelum save, `adeu/paragraph_ids.py`
   menambahkan bookmark `pNNNN`.
2. Manifest disiapkan di memori dengan `text_sha256`, `kind`, `heading_path`,
   dan status `protected`.
3. Setelah save, manifest ditulis ke `.laporan/manifest.json`.
4. Setelah `office`, pipeline memverifikasi bookmark `pNNNN` masih ada dan
   urutannya sama. Bookmark yang hilang menggagalkan build.

Rincian ada di [adeu-integration.md](adeu-integration.md).

## Opsi build

| Flag | Default | Arti |
| --- | --- | --- |
| `--target` | `both` | `docx`, `pdf`, atau `both`. |
| `--keep` | `false` | Pertahankan `.laporan-build/` dan intermediate DOCX. |
| `--terms` | `false` | Aktifkan check, apply, verify, dan review istilah. |
| `--no-manifest` | `false` | Bookmark tetap; manifest dan source scan mati. |
| `--no-adeu` | `false` | Bookmark, manifest, dan source scan mati. |
| `--allow-missing-word` | `false` | `both` boleh melewati PDF tanpa Word. |

Aturan target:

| Platform | `docx` | `pdf` | `both` |
| --- | --- | --- | --- |
| Windows dengan Word | DOCX | PDF | DOCX dan PDF |
| Windows tanpa Word | DOCX | error | DOCX dengan peringatan bila `--allow-missing-word`; selain itu error |
| Debian/Linux | DOCX best-effort | error | error, atau DOCX dengan `--allow-missing-word` |

`--target pdf` selalu membutuhkan Word, bahkan dengan
`--allow-missing-word`, karena tidak ada output yang diminta.

## Output

`report_name` wajib di front matter dan tidak memiliki nilai default. Nilai
kosong atau hanya whitespace menghasilkan `CFG-REQUIRED`. DOCX dan PDF memakai
stem yang sama, misalnya `report_name: "Tugas"` menghasilkan `Tugas.docx` dan
`Tugas.pdf`. Tidak ada flag CLI `--report-name`. Output ditulis di samping
`document.md`, kecuali dokumen di `examples/<name>/` yang ditulis ke
`examples/<name>/out/`.

| Artefak | Lokasi | Kapan |
| --- | --- | --- |
| DOCX | output dir | `--target docx` atau `both` |
| PDF | output dir | `--target pdf` atau `both` |
| `.laporan/manifest.json` | samping dokumen | Default, kecuali `--no-manifest` atau `--no-adeu` |
| `.laporan/istilah-baru.txt` | samping dokumen | `--terms` |
| `.laporan-build/` | samping dokumen | Hanya dengan `--keep` |

Tidak ada output di `build/` atau `review/`. Penulisan memakai file sementara
di direktori tujuan dan `os.replace`.

## Workspace

Workspace default adalah `.laporan-build/` di samping `document.md`. Isinya
antara lain Markdown hasil `front_matter`, PNG Mermaid, `reference.docx`
turunan, dan DOCX intermediate untuk target PDF. Tanpa `--keep`, workspace
dihapus di blok `finally`, termasuk saat build gagal.

## Error dan exit code

Semua error pipeline melempar subclass `DocgenError`. Stage yang melempar
exception tak dikenal dibungkus `StageError` dengan nama stage, path, dan
cause.

| Exit | Arti |
| ---: | --- |
| 0 | Sukses |
| 1 | Error input, konfigurasi, stage, tool, output, atau Word/PDF |
| 2 | Kesalahan pemakaian CLI |
| 3 | `reconcile`: ada perubahan manual |
| 4 | `reconcile`: pelanggaran paragraf terlindungi |
| 130 | Dibatalkan pengguna |

## Idempotensi

Semua stage yang memutasi package dideklarasikan idempoten, kecuali `office`
dan `pdf` yang bersifat semantik karena Word dapat menulis ulang package.
Definisi:

- `document.xml` setelah c14n memiliki hash yang sama pada dua run;
- part non-target byte-identik;
- stage yang tidak memutasi package tidak mengubah artefak.

Stage yang gagal idempotensi adalah bug. Matriks lengkap ada di
[contracts/stage-api.md](contracts/stage-api.md).

## Logging

Logger pipeline adalah `docgen.pipeline`; logger stage memakai
`docgen.stage.<name>`. Stage tidak memakai `print`. CLI memiliki stdout dan
stderr. Log tidak memuat seluruh isi dokumen atau data pribadi.
