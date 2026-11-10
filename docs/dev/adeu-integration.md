# Integrasi Adeu

Fitur Adeu berada di `src/docgen/adeu/`. Fitur ini menambahkan
bookmark paragraf, menulis manifest, memetakan sumber Markdown, dan
menyediakan perintah `reconcile`. Bookmark dan manifest dibuat sebagai hook di
dalam pass package, bukan stage kanonik.

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
menghasilkan exit code 4 pada `reconcile`.

## Source scan

Source scan memetakan paragraf manifest ke `document.md`:

- hanya dilakukan bila manifest aktif;
- membaca Markdown di direktori dokumen secara rekursif;
- melewati `out/`, `build/`, `review/`, dan `.laporan*`;
- mencocokkan heading path dan teks yang dinormalisasi;
- hanya menulis `source_file` dan `source_line` bila pasangan blok unik.

Bila pasangan tidak unik, field source dibiarkan `null`. Source scan tidak
mengubah Markdown.

## Flag build

| Flag | Bookmark | Manifest | Source scan |
| --- | --- | --- | --- |
| default | ya | ya | ya |
| `--no-manifest` | ya | tidak | tidak |
| `--no-adeu` | tidak | tidak | tidak |

`--no-adeu` menyiratkan `--no-manifest`. `--no-manifest` tidak mematikan
bookmark.

## Reconcile

```bash
uv run --project <repo> docgen reconcile document.md
```

Default:

| Opsi | Default |
| --- | --- |
| `--docx` | `docgen.paths.output_directory()`: `examples/<nama>/document.md` -> `<folder>/out/<report_name>.docx`; dokumen lain -> `<folder-dokumen>/<report_name>.docx` |
| `--manifest` | `.laporan/manifest.json` di samping dokumen |
| `--out` | `.laporan/reconcile.md` di samping dokumen |

Path `--docx` dihitung oleh `docgen.paths.output_directory()`. Dokumen di
`examples/<nama>/document.md` memakai `<folder>/out/`; dokumen lain memakai
folder dokumen. Nilai `--docx` eksplisit selalu menang. Bila DOCX tidak ada,
`reconcile` gagal dengan `ReconcileError` berkode `RECONCILE-INPUT` yang
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
- `reconcile` tidak menulis ulang Markdown secara otomatis.
- Word dapat menulis ulang package saat finalisasi, sehingga perbandingan
  harus memakai DOCX hasil edit yang masih mempertahankan bookmark.
