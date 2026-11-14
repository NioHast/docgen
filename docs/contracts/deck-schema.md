# Kontrak Skema Deck

Kontrak ini membekukan bentuk berkas `deck.yaml` sebagai satu-satunya input
authoring deck. Ia menetapkan top-level, `meta`, `theme`, `defaults`, slide,
block, path aset, `notes`, `source`, dan inline Markdown. Tabel field lengkap
tidak diulang di sini; rujukan utamanya adalah plan bagian 4.3 sampai 4.12.

Status: F0 contract, version 1
Sumber: AUTO_OFFICE_PLAN.md bagian 4 (4.1 sampai 4.12 dan 4.14).

## Input dan output

- Input: satu berkas `deck.yaml`, UTF-8, dibaca dengan safe loader.
- Output: objek schema tervalidasi yang diserahkan ke compiler, bukan DeckIR.
- Tidak ada include, partial, atau file slide terpisah.
- Error wajib menyebut path, slide ID, block ID, dan key bila relevan.

## Bentuk top-level

| Field | Wajib | Ringkas |
| --- | --- | --- |
| `schema` | ya | Harus `autooffice.deck/v1`. |
| `meta` | ya | `title` dan `author` wajib; `subtitle`, `organization`, `date`, `language`, `description` opsional. |
| `theme` | tidak | Hanya `name`, nilainya `indigo` atau `hitam`. Default `indigo`. |
| `defaults` | tidak | `layout`, `image_fit`, `code_language`; tanpa nilai visual. |
| `slides` | ya | Minimal satu; urutan array adalah urutan presentasi. |

Tidak ada field top-level lain. `meta` tidak boleh memuat token, path output,
ID Google, atau state build.

## Slide dan block

- Slide memakai `id` berpola `^s[0-9]{2,}$`, eksplisit, unik, dan tidak
  di-renumber saat reorder.
- Field slide: `layout`, `notes`, `source`, dan tepat salah satu dari `blocks`
  atau `rows`. `layout: custom` wajib memakai `rows`; preset wajib memakai
  `blocks`.
- `layout` default `content` dari `defaults.layout`.
- Block memakai `id` berpola `^[a-z][a-z0-9_]*$`, maksimal 32 karakter, dan
  unik per slide.
- `span` hanya untuk `layout: custom`, bilangan bulat 1 sampai 12.
- `source.text` wajib bila `source` ada dan merupakan key. `source.url`
  opsional dan bukan key.
- `notes` adalah plain text, bukan bagian visual, tetapi tetap key dan ikut
  sinkronisasi teks.

## Path dan teks

- Path relatif terhadap direktori YAML, memakai `/`, tanpa absolut, UNC,
  drive letter, `..`, atau URL remote.
- Gambar hanya `.png`, `.jpg`, `.jpeg`, `.webp`; diagram hanya `.mmd`.
- Inline Markdown hanya `**bold**`, `` `inline code` ``, link `https`, `http`,
  atau `mailto`, dan escape `\*`, `\_`, `` \` ``, `\[`, `\]`.
- Italic, heading Markdown, list Markdown, gambar Markdown, table Markdown,
  blockquote Markdown, HTML, footnote, dan link relatif ditolak.
- Teks yang tampil tidak boleh kosong dan tidak boleh memakai em dash atau en
  dash.

## Invariant

- Satu berkas YAML per deck; tidak ada sumber kedua.
- Key asing ditolak; tidak ada `extra` atau `metadata` bebas.
- YAML tidak mendefinisikan warna, font, ukuran, margin, padding, atau koordinat.
- Semua ID stabil dan unik sesuai lingkupnya.
- `blocks` dan `rows` saling eksklusif.
- Hanya 11 block type yang diterima; daftarnya di [block-spec.md](block-spec.md).
- `span` dilarang pada preset dan wajib pada custom.
- Semua nilai tampil adalah string setelah inline Markdown; nilai chart adalah angka.
- Semua path aset harus ada saat `check` dan `build`.
- Semua gambar, diagram, dan chart wajib punya `alt` non-kosong.
- Tidak ada `font_size`, `color`, `margin`, `padding`, `x`, `y`, `width`,
  `height`, atau `position` di authoring.
- Perubahan nama field adalah perubahan kontrak dan memerlukan ADR.

## Contoh minimal

```yaml
schema: autooffice.deck/v1

meta:
  title: "Kontrak Deck"
  author: "Tim AutoOffice"
  language: "id-ID"

theme:
  name: indigo

defaults:
  layout: content
  image_fit: contain
  code_language: text

slides:
  - id: s01
    layout: content
    notes: |
      Catatan pembicara untuk slide pertama.
    source:
      text: "Sumber: data internal, 2026"
    blocks:
      - id: title
        type: text
        role: title
        text: "Satu skema untuk semua target"
      - id: points
        type: bullets
        items:
          - "Satu berkas YAML per deck."
          - "Key datar dan stabil."
```

## Catatan implementasi F1-MODEL

- Implementasi ada di `src/autooffice/deck/model/schema.py` dan `loader.py`.
  Loader memakai `ruamel.yaml` safe loader dan menolak key mapping duplikat,
  tag kustom, serta lebih dari satu dokumen YAML.
- Field geometri (bagian 7.7) dan field style (`font_size`, `color`, `margin`,
  `padding`, dan sejenisnya) ditolak di semua objek. Ini penegasan invariant
  yang sudah dibekukan, bukan field baru.
- Path aset harus relatif, memakai `/`, tanpa segmen kosong, `.`, `..`,
  backslash, drive letter, UNC, atau URL. `source.url` tetap hanya http/https.
- `meta.language` dinormalisasi ke `id` atau `en`; nilai lain ditolak.
- `notes` dan `code` memakai mode preserve-newline; field inline memakai
  normalisasi inline. `code` tidak diparse sebagai Markdown.
- Batas chart: `bar`/`line` 1-4 seri; `donut` tepat 1 seri dengan 2-4
  kategori. `orientation` hanya untuk `bar`.
- `span` custom wajib 1-12 dan total per row maksimal 12; `span` preset
  ditolak. Contoh plan 4.13 yang menjumlahkan lebih dari 12 dalam satu row
  bersifat ilustratif; aturan 7.2 dan layout-spec menang.
- `divider` dan `spacer` hanya untuk custom. `role` hanya untuk block `text`;
  kecocokan dengan slot preset ditegakkan lane layout.
- Keberadaan file aset diperiksa saat check/build; model memvalidasi bentuk
  path dan symlink escape.

## Acceptance

Catatan F1-MODEL: test bentuk tetap di `tests/contract/**`; test perilaku ada di `tests/deck/model/**`.

| Aturan | Test kontrak |
| --- | --- |
| `schema` salah atau field top-level asing ditolak. | `tests/deck/model/test_loader.py`, `test_schema.py` |
| ID slide atau block duplikat ditolak dengan kedua ID. | `tests/deck/model/test_schema.py` |
| `blocks` dan `rows` bersamaan ditolak. | `tests/deck/model/test_schema.py` |
| `span` pada preset atau di luar 1 sampai 12 ditolak. | `tests/deck/model/test_schema.py` |
| Field geometri dan style inline ditolak. | `tests/deck/model/test_schema.py` |
| Path absolut, `..`, dan URL remote ditolak. | `tests/deck/model/test_schema.py` |
| Inline Markdown di luar daftar ditolak. | `tests/deck/model/test_markdown.py` |
| Contoh minimal lolos load dan compile. | `tests/deck/model/test_loader.py`, `test_compiler.py` |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
