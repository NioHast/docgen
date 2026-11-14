# 02 - Build Pertama

Halaman ini memandu build DOCX pertama dari contoh yang sudah tersedia.
Setelah membacanya, pembaca bisa menyiapkan prasyarat, menjalankan `check`,
membangun DOCX, menemukan output, dan memahami aturan target PDF.

## Tujuan halaman

Setelah halaman ini, pembaca bisa:

1. memeriksa prasyarat build dengan `doctor`;
2. menjelaskan front matter minimum, termasuk `report_name` wajib;
3. menjalankan `check` dan `build --target docx`;
4. menemukan DOCX, manifest, dan workspace;
5. memilih target `docx`, `pdf`, atau `all` sesuai platform dan Word;
6. membaca peringatan saat Word tidak tersedia.

## Prasyarat

- [00 - Mulai di Sini](00-start-here.md) dan
  [01 - Model Mental](01-mental-model.md).
- `uv` sudah terpasang.
- Pandoc tersedia untuk build DOCX.
- Microsoft Word desktop di Windows hanya diperlukan untuk PDF dan
  finalisasi field. Word Online tidak dipakai.
- `mmdc` hanya diperlukan bila dokumen memakai blok Mermaid.

## Daftar isi

- [Periksa prasyarat](#periksa-prasyarat)
- [Front matter minimum](#front-matter-minimum)
- [Body yang cocok dengan struktur](#body-yang-cocok-dengan-struktur)
- [Langkah build DOCX](#langkah-build-docx)
- [Apa yang terjadi saat build](#apa-yang-terjadi-saat-build)
- [Nama output dan manifest](#nama-output-dan-manifest)
- [Target PDF dan peringatan Word](#target-pdf-dan-peringatan-word)
- [Kesalahan umum build pertama](#kesalahan-umum-build-pertama)
- [Latihan](#latihan)
- [Halaman berikutnya](#halaman-berikutnya)
- [Referensi dan kontrak](#referensi-dan-kontrak)

## Periksa prasyarat

Jalankan dari akar repo:

```bash
uv sync --extra dev
uv run autooffice --version
uv run autooffice doctor
```

`doctor` mencetak status Python, Pandoc, Word, dan `mmdc`. Exit code 1 berarti
dependensi wajib untuk DOCX belum lengkap. Perhatikan bahwa:

- Python harus 3.15 atau lebih baru;
- Pandoc wajib untuk DOCX;
- Word hanya relevan di Windows dan untuk PDF/finalisasi field;
- `mmdc` hanya wajib jika ada blok Mermaid.

Setelah `doctor` siap untuk DOCX, lanjut ke contoh.

## Front matter minimum

Front matter adalah YAML di antara `---` pembuka dan penutup. Field wajib
adalah `title`, `author`, `structure`, `format`, dan `report_name`.
`report_name` tidak punya default dan tidak bisa diberikan lewat CLI.

Contoh nyata dari `examples/assignment-single/document.md`:

```yaml
---
title: "Analisis Pipeline Markdown untuk Laporan Tugas"
author: "Nama Mahasiswa"
nim: "30000000000000"
lecturer: "Dr. Nama Dosen Pengampu, M.Kom."
lecturer_label: "Dosen Pengampu:"
course: "Penulisan Laporan Akademik"
institution: "Universitas Diponegoro"
faculty: "Program Studi Magister Sistem Informasi"
year: "2026"
date: "Agustus 2026"
lang: "id-ID"
report_name: "Tugas"
structure: assignment
format: undip-msi
bibliography: references.bib
---
```

Yang perlu diperhatikan:

- `structure` dan `format` adalah ID, bukan path. ID harus sama dengan nama
  direktori di `src/autooffice/docx/data/`.
- `bibliography` relatif terhadap direktori `document.md`. Jika sitasi
  digunakan, berkas `.bib` harus ada.
- `report_name` harus aman sebagai nama berkas. Nilai yang mengandung `\`,
  `/`, `:`, `*`, `?`, `"`, `<`, `>`, atau `|` ditolak.
- `abstract_id`, `abstract_en`, dan `preface` wajib diisi jika struktur
  mendeklarasikannya sebagai `source: document`.

## Body yang cocok dengan struktur

Front matter saja tidak cukup. Heading 1 di body harus cocok dengan daftar
`body` pada struktur. Untuk `assignment`, urutannya adalah:

```markdown
# Pendahuluan

...

# Pembahasan

...

# Penutup

...
```

Heading 1 ditulis tanpa nomor. Pipeline yang menambahkan nomor sesuai
`structure.numbering`. Jika urutan atau ejaan heading tidak cocok, `check`
gagal dengan `CFG-BODY-ORDER`. Untuk contoh thesis, body harus memuat lima
bab yang dideklarasikan `src/autooffice/docx/data/structures/thesis/structure.yml`.

## Langkah build DOCX

Urutan yang disarankan:

```bash
uv sync --extra dev
uv run autooffice check examples/assignment-single/document.md
uv run autooffice build examples/assignment-single/document.md --target docx
```

Arti tiap langkah:

1. `sync` memastikan environment dan dependensi pengembangan tersedia.
2. `check` memvalidasi input tanpa memanggil Pandoc atau Word.
3. `build --target docx` menjalankan pipeline Python dan menghasilkan DOCX.

Keluaran yang diharapkan dari build:

```text
[OK] Keluaran: ...\examples\assignment-single\out\Tugas.docx
[OK] Keluaran: ...\examples\assignment-single\.laporan\manifest.json
```

Jika Word tidak tersedia tetapi target hanya DOCX, build tetap berhasil
dengan peringatan. Peringatan itu bukan kegagalan.

## Apa yang terjadi saat build

Secara ringkas:

1. front matter, format, struktur, aset, dan caption divalidasi;
2. Mermaid dirender bila ada;
3. `reference.docx` turunan dibuat dari `format.yml`;
4. front matter Markdown dimaterialisasi: sampul, template legal, abstrak,
   dan penomoran heading;
5. Pandoc mengubah Markdown menjadi DOCX;
6. stage Python menambahkan section, caption, persamaan, numbering, field
   TOC, nomor halaman, dan daftar tabel/gambar;
7. package disimpan satu kali;
8. Word memperbarui field dan mengekspor PDF bila diminta dan tersedia.

Urutan lengkap ada di [03 - Tahap Pipeline](03-pipeline-stages.md).

## Nama output dan manifest

Untuk dokumen di `examples/<nama>/document.md`, output ditulis ke
`examples/<nama>/out/`. Untuk dokumen pengguna lain, output ditulis di folder
yang sama dengan `document.md`.

Contoh dengan `report_name: "Tugas"`:

| Artefak | Lokasi |
| --- | --- |
| DOCX | `examples/assignment-single/out/Tugas.docx` |
| PDF | `examples/assignment-single/out/Tugas.pdf` jika Word tersedia |
| Manifest | `examples/assignment-single/.laporan/manifest.json` |
| Review istilah | `examples/assignment-single/.laporan/istilah-baru.txt` jika `--terms` |
| Workspace | `examples/assignment-single/.laporan-build/` jika `--keep-intermediate` |

Manifest berisi bookmark `pNNNN` dan peta paragraf. Manifest dan bookmark
selalu ditulis oleh AutoOffice v1; tidak ada flag CLI untuk mematikannya.

## Target PDF dan peringatan Word

Matriks target:

| Platform dan alat | `--target docx` | `--target pdf` | `--target all` |
| --- | --- | --- | --- |
| Windows dengan Word | DOCX, field diperbarui | PDF | DOCX dan PDF |
| Windows tanpa Word | DOCX dengan peringatan | error | DOCX dapat tertulis, lalu error |
| Debian/Linux | DOCX best-effort, field belum final | error | DOCX dapat tertulis, lalu error |

Perintah DOCX dan PDF di Windows dengan Word:

```bash
uv run autooffice build examples/thesis-single/document.md --target docx,pdf
```

Perintah yang aman tanpa Word:

```bash
uv run autooffice build examples/thesis-single/document.md --target docx
```

Tanpa Word, stage `office` tidak berjalan. Pipeline memberi peringatan:

```text
Microsoft Word tidak tersedia; field DOCX tidak diperbarui dan TOC memakai cache terakhir. DOCX tetap dihasilkan.
```

Field TOC yang baru ditulis belum berisi entri. Akibatnya TOC bisa tampil
kosong di DOCX sampai dokumen dibuka di Word dan field diperbarui. Nomor
halaman juga belum final. Ini bukan bug pipeline: finalisasi field adalah
tanggung jawab Word.

`--target pdf` dan `--target all` selalu membutuhkan Word karena PDF tidak
dapat dihasilkan tanpa Word. Tidak ada flag yang menurunkan `all` menjadi
DOCX.

## Kesalahan umum build pertama

| Gejala | Kode atau penyebab | Tindakan |
| --- | --- | --- |
| Front matter ditolak | `CFG-REQUIRED` | Isi field wajib, terutama `report_name`. |
| Heading 1 tidak cocok | `CFG-BODY-ORDER` | Samakan judul dan urutan dengan `structure.body`. |
| Bibliografi atau gambar tidak ditemukan | `CFG-ASSET-MISSING` | Perbaiki path relatif dan sediakan berkas. |
| Pandoc tidak menemukan input | `PANDOC-INPUT` | Jalankan pipeline normal; jangan mengandalkan berkas cadangan. |
| Word tidak ditemukan saat minta PDF | `TOOL-MISSING` | Gunakan `--target docx` atau pasang Word desktop. |
| TOC kosong | Word belum memperbarui field | Buka DOCX di Word dan perbarui field, atau build ulang dengan Word. |

Saat error muncul, salin baris `[ERROR]` lengkap. Baris itu memuat path, key,
dan kode yang dibutuhkan untuk mencari penyebab.

## Latihan

### 1. Periksa contoh tanpa build

Jalankan:

```bash
uv run autooffice check examples/assignment-single/document.md
```

Cara memeriksa: exit code 0, output `[OK]`, dan ringkasan memuat
`format=undip-msi struktur=assignment author=1 bab=3`. Perintah ini tidak
membuat DOCX.

### 2. Build DOCX dan periksa artefak

Jalankan:

```bash
uv run autooffice build examples/assignment-single/document.md --target docx
```

Cara memeriksa:

```bash
ls -l examples/assignment-single/out/Tugas.docx
ls -l examples/assignment-single/.laporan/manifest.json
```

Kedua berkas harus ada dan ukurannya tidak nol. Jika Word tidak tersedia,
peringatan TOC boleh muncul, tetapi DOCX tetap harus ada.

### 3. Ganti report_name pada salinan

Salin `examples/assignment-single` ke direktori sementara di luar repo, ubah
`report_name` menjadi `"Latihan"`, lalu jalankan:

```bash
uv run autooffice build <path-salinan>/document.md --target docx
```

Cara memeriksa: output harus berada di `<path-salinan>/out/Latihan.docx`.
Tidak boleh ada `Tugas.docx` baru dari salinan itu. Ini menunjukkan nama
output benar-benar berasal dari `report_name`, bukan dari default.

## Halaman berikutnya

Lanjut ke [03 - Tahap Pipeline](03-pipeline-stages.md) untuk memahami 18 stage
dan cara membaca kegagalannya.

## Referensi dan kontrak

| Kebutuhan | Dokumen |
| --- | --- |
| Opsi build dan matriks target | [pipeline/options.md](../pipeline/options.md) |
| Nama dan lokasi output | [pipeline/outputs.md](../pipeline/outputs.md) |
| Artefak dan workspace | [pipeline/artifacts.md](../pipeline/artifacts.md) |
| Error dan exit code | [pipeline/errors.md](../pipeline/errors.md) |
| PDF dan Word | [pdf.md](../pdf.md) |
| Contoh repo | [examples/README.md](../../../examples/README.md) |
| Kontrak konfigurasi | [formats.md](../formats.md) |
| Kontrak stage dan CLI | [contracts/cli.md](../../contracts/cli.md) |

### Referensi resmi

Label registry yang dipakai halaman ini: `Pandoc installation`, `Pandoc
manual`, `uv documentation`, `Word COM object model (VBA reference)`, dan
`pytest documentation`. URL resminya ada di
[registry referensi](../references.md).
