# Integrasi Adeu

Fitur Adeu berada di `src/autooffice/docx/adeu/`. Fitur ini menambahkan
bookmark paragraf, menulis manifest, memetakan sumber Markdown, dan menyimpan
modul rekonsiliasi internal. Bookmark dan manifest dibuat sebagai hook di
dalam pass package, bukan stage kanonik. Permukaan CLI AutoOffice v1 tidak
memiliki subperintah `reconcile`.

## Apa itu Adeu

Adeu adalah produk dan engine eksternal, bukan bagian dari repo ini. Ia adalah
**MCP server** untuk Microsoft Word: server yang menyediakan tool dan sumber
data untuk dipanggil AI agent. Pemanggilannya memakai **Model Context Protocol
(MCP)**, yaitu standar agar AI agent dapat memanggil tool dan membaca dokumen
dengan cara yang seragam. Adeu tersedia sebagai MCP server (Python/Node) dan
SDK.

Adeu adalah **docx ↔ LLM translator**: ia membaca DOCX menjadi
Markdown/CriticMarkup, memvalidasi edit, lalu menulis edit tersebut kembali
sebagai **native Word Track Changes** tanpa merusak format. Adeu menyebut
dirinya "Virtual DOM for Microsoft Word".

Repo ini **bukan** server MCP Adeu dan tidak memanggil atau membungkus server
tersebut. Yang ada di repo ini adalah lapisan integrasi di `src/autooffice/docx/adeu/`:

| Aspek | Adeu (eksternal) | `src/autooffice/docx/adeu/` (repo ini) |
| --- | --- | --- |
| Bentuk | MCP server (Python/Node) dan SDK; proyek terpisah. | Kode integrasi Python di dalam pipeline `autooffice`; bukan server MCP. |
| Tugas | Membaca DOCX menjadi Markdown/CriticMarkup, memvalidasi edit, dan menulisnya sebagai native Word Track Changes. | Menambahkan bookmark `pNNNN`, menulis manifest deterministik `.laporan/manifest.json`, memetakan paragraf ke sumber Markdown, dan menyediakan modul rekonsiliasi internal. |
| Cara pakai | Dipasang dan dijalankan sendiri oleh pengguna atau agent. | Dipanggil lewat `autooffice build`; modul rekonsiliasi hanya dipakai pengembang dan tidak diekspos sebagai perintah publik. |

Alur kerja yang didukung repo ini:

1. `autooffice build` menghasilkan DOCX dan manifest. Setiap paragraf body mendapat
   bookmark `pNNNN` yang menghubungkan DOCX, manifest, dan Markdown.
2. Adeu atau agent mengedit DOCX. Adeu dapat menulis edit sebagai native Word
   Track Changes.
3. Modul rekonsiliasi internal membandingkan DOCX hasil edit dengan manifest
   dan sumber Markdown, lalu menulis laporan (default `.laporan/reconcile.md`).
   Perubahan yang disetujui tetap diterapkan manual ke `document.md`, lalu
   build ulang.

Tautan resmi:

- Repo resmi: <https://github.com/dealfluence/adeu>
- PyPI: <https://pypi.org/project/adeu/>
- MCP server (npm): <https://www.npmjs.com/package/@adeu/mcp-server>
- Referensi tool MCP: <https://github.com/dealfluence/adeu/blob/main/skills/adeu-redlining/references/mcp-tools.md>
- Situs perusahaan: <https://adeu.ai>

> **Peringatan:** bila yang Anda cari adalah MCP server Adeu, itu proyek
> terpisah di tautan di atas. Repo ini tidak memanggil, membungkus, atau
> mendistribusikan server tersebut; repo ini hanya menyediakan bookmark,
> manifest, source scan, dan modul rekonsiliasi internal untuk alur edit DOCX.

## Daftar isi

- [Apa itu Adeu](#apa-itu-adeu)
- [Bookmark `pNNNN`](#bookmark-pnnnn)
- [Manifest](#manifest)
- [Paragraf terlindungi](#paragraf-terlindungi)
- [Source scan](#source-scan)
- [Manifest dan bookmark](#manifest-dan-bookmark)
- [Modul rekonsiliasi internal](#modul-rekonsiliasi-internal)
- [Batasan](#batasan)

## Bookmark `pNNNN`

Setelah stage `lists` dan sebelum package disimpan, setiap paragraf body
mendapat bookmark berurutan:

```text
p0001
p0002
p0003
```

Aturan:

- nama bookmark cocok dengan `^p\d{4,}$`;
- urutan bookmark sama dengan urutan paragraf body;
- bookmark ditambahkan ke package di memori;
- setelah `office`, pipeline membaca ulang DOCX dan memastikan seluruh
  bookmark masih ada dan urutannya sama;
- bookmark yang hilang atau berubah menggagalkan build dengan
  `BookmarkError`.

Bookmark menjadi penghubung antara DOCX, manifest, dan Markdown.

## Manifest

Manifest default berada di samping `document.md` (`.laporan/manifest.json`
relatif terhadap direktori dokumen):

```text
.laporan/manifest.json
```

Bentuk versi 1:

```json
{
  "version": 1,
  "docx": "Tugas.docx",
  "paragraphs": [
    {
      "id": "p0001",
      "index": 0,
      "kind": "heading",
      "heading_path": ["Pendahuluan"],
      "text": "BAB I",
      "text_sha256": "...",
      "protected": false,
      "protected_reason": null,
      "source_file": "document.md",
      "source_line": 12
    }
  ]
}
```

Field:

| Field | Isi |
| --- | --- |
| `version` | Versi skema, saat ini `1`. |
| `docx` | Nama berkas DOCX, bukan path. |
| `id` | Bookmark `pNNNN`. |
| `index` | Urutan paragraf, mulai 0. |
| `kind` | `heading`, `body`, `table`, `caption`, `toc`, `bibliography`, atau `cover`. |
| `heading_path` | Jalur heading aktif. |
| `text` | Teks paragraf final yang terlihat. |
| `text_sha256` | SHA-256 dari `text`. |
| `protected` | Boolean. |
| `protected_reason` | Alasan proteksi atau `null`. |
| `source_file` | Path Markdown relatif, bila source scan aktif. |
| `source_line` | Nomor baris, bila source scan aktif. |

Manifest deterministik: tanpa `built_at`, urutan paragraf stabil, dan hash
dihitung dari teks final. Manifest divalidasi ketat saat dibaca dan ditulis.
Hash yang tidak cocok, ID duplikat, index duplikat, atau kunci tidak dikenal
menggagalkan proses.

## Paragraf terlindungi

Paragraf berikut ditandai `protected: true` dan tidak boleh diubah lewat
rekonsiliasi:

| Reason | Arti |
| --- | --- |
| `toc_field` | Paragraf di dalam field TOC. |
| `sectpr` | Paragraf memuat section properties. |
| `seq_field` | Paragraf memuat field `SEQ`. |
| `pageref_field` | Paragraf memuat `PAGEREF`. |
| `page_field` | Paragraf memuat field `PAGE`. |
| `caption_style` | Paragraf bergaya caption. |
| `toc_style` | Paragraf bergaya TOC. |
| `bibliography` | Paragraf daftar pustaka. |
| `cover_style` | Paragraf sampul. |

Perubahan pada paragraf terlindungi dilaporkan sebagai pelanggaran dan
menghasilkan exit code 4 pada modul rekonsiliasi internal.

## Source scan

Source scan memetakan paragraf manifest ke `document.md`:

- hanya dilakukan bila manifest aktif;
- membaca Markdown di direktori dokumen secara rekursif;
- melewati `out/`, `build/`, `review/`, dan `.laporan*`;
- mencocokkan heading path dan teks yang dinormalisasi;
- hanya menulis `source_file` dan `source_line` bila pasangan blok unik.

Bila pasangan tidak unik, field source dibiarkan `null`. Source scan tidak
mengubah Markdown.

## Manifest dan bookmark

AutoOffice v1 selalu menulis bookmark dan manifest untuk setiap build DOCX.
Tidak ada flag `--no-manifest` atau `--no-adeu` pada CLI. Source scan mengikuti
manifest yang aktif; tidak ada mode yang mematikan salah satunya.

## Modul rekonsiliasi internal

Modul `autooffice.docx.adeu.reconcile` tersedia untuk pengembang dan tes
parity. Modul ini bukan subperintah CLI AutoOffice v1 dan tidak dijanjikan
sebagai permukaan publik.

Default:

| Opsi | Default |
| --- | --- |
| `--docx` | `autooffice.docx.paths.output_directory()`: `examples/<nama>/document.md` -> `<folder>/out/<report_name>.docx`; dokumen lain -> `<folder-dokumen>/<report_name>.docx` |
| `--manifest` | `.laporan/manifest.json` di samping dokumen |
| `--out` | `.laporan/reconcile.md` di samping dokumen |

Path `--docx` dihitung oleh `autooffice.docx.paths.output_directory()`. Dokumen di
`examples/<nama>/document.md` memakai `<folder>/out/`; dokumen lain memakai
folder dokumen. Nilai `--docx` eksplisit selalu menang. Bila DOCX tidak ada,
modul rekonsiliasi gagal dengan `ReconcileError` berkode `RECONCILE-INPUT` yang
menyebut path yang diharapkan; tidak ada fallback ke lokasi lain.

Alur:

1. Baca `document.md` dan front matter untuk `report_name`; field ini wajib
   dan tidak punya nilai default. Tidak ada flag CLI `--report-name`.
2. Muat manifest dan validasi hash.
3. Baca DOCX hasil edit dan ambil teks paragraf ber-bookmark.
4. Bandingkan teks DOCX dengan manifest.
5. Cocokkan paragraf ke blok Markdown untuk petunjuk sumber.
6. Tulis laporan Markdown.

Alat hanya menulis laporan. DOCX, manifest, dan `document.md` tidak diubah.
`--out` harus berekstensi `.md` dan tidak boleh menimpa ketiga berkas sumber.

### Exit code

| Exit | Arti |
| ---: | --- |
| 0 | Tidak ada perubahan manual. |
| 1 | Error input, manifest, atau DOCX. |
| 2 | Kesalahan pemakaian CLI. |
| 3 | Ada perubahan manual yang perlu ditinjau. |
| 4 | Ada pelanggaran paragraf terlindungi. |

Perubahan yang disetujui tetap diterapkan manual ke `document.md`, lalu build
ulang. Jangan menyunting DOCX sebagai sumber.

## Batasan

- Manifest memetakan paragraf body, bukan isi header/footer.
- Teks yang tidak terlihat atau berada di field dapat dilaporkan sebagai
  paragraf tanpa ID.
- Perubahan struktur besar dapat membuat pencocokan sumber ambigu.
- Modul rekonsiliasi tidak menulis ulang Markdown secara otomatis.
- Word dapat menulis ulang package saat finalisasi, sehingga perbandingan
  harus memakai DOCX hasil edit yang masih mempertahankan bookmark.
