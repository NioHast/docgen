# ADR 0009: Rows Custom Eksplisit di SlideIR

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L06, L21
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 6 dan 7,
  [ADR 0004](0004-layouts-and-rendering.md), dan
  [ADR 0007](0007-slot-span.md)

## Konteks

Compiler meratakan `rows` author menjadi `SlideIR.blocks` yang datar. Layout
custom kemudian merekonstruksi batas row dari petunjuk key manifest atau jumlah
span. Untuk row parsial yang seluruhnya terdiri dari block tanpa key seperti
`divider` dan `spacer`, kedua heuristik tidak dapat membedakan dua row author
dari satu row yang kebetulan belum penuh. Hasilnya bergantung pada bentuk
kebetulan input, bukan pada kontrak.

Batas row adalah data authoring yang sudah diketahui compiler. Menyimpannya di
IR menghilangkan rekonstruksi dan membuat hasil layout deterministik tanpa
bergantung pada key atau nilai span.

## Keputusan

1. `SlideIR` mendapat field `rows: tuple[tuple[str, ...], ...] = ()` berisi
   block ID per row. Slide preset memakai default kosong.
2. `SlideIR.__post_init__` memvalidasi bahwa setiap block ID di `rows` ada di
   `blocks`, tidak ada ID duplikat, dan setiap row tidak kosong. Slide
   `layout: custom` wajib memuat setiap block tepat satu kali; slide non-custom
   boleh memuat sebagian block.
3. `rows` kosong berarti IR tidak membawa batas row eksplisit. Compiler selalu
   mengisi `rows` untuk slide custom; hanya IR yang dibuat manual tanpa rows
   yang memakai fallback layout.
4. Compiler mengisi `SlideIR.rows` dari `SlideDefinition.rows` dan menjaga
   urutan block row-major yang sama dengan `blocks`.
5. Layout custom memakai `SlideIR.rows` sebagai otoritas. Fallback rekonstruksi
   span hanya berlaku bila `rows` kosong; bila tidak ada rows maupun block,
   planner melempar `CustomLayoutError` yang menyebut slide.
6. Heuristik petunjuk key manifest dihapus karena sumber kebenaran row sudah
   ada di IR dan heuristik itu tidak berlaku untuk block tanpa key.

## Konsekuensi

- Bentuk `SlideIR` berubah setelah F0 dan dicatat sebagai amandemen melalui ADR
  ini; test shape wajib memuat `rows`.
- `SlideIR.rows` untuk slide preset tetap `()`, sehingga renderer dan copy
  checker tidak berubah.
- Partial row `divider`/`spacer` kini deterministik tanpa key atau hint.
- Test compiler wajib memeriksa rows custom persis sesuai urutan authoring.
- IR lama yang dibuat manual tanpa rows masih dapat direncanakan lewat fallback
  span, tetapi fallback itu bukan jalur compiler dan tidak dipakai build normal.

## Alternatif yang ditolak

- Menyimpan `BlockIR` di dalam `rows`. Ditolak karena menduplikasi objek block
  dan memutus invariant `blocks` sebagai daftar block slide.
- Menambah field `row_index` pada `BlockIR`. Ditolak karena mengubah setiap
  block dan tetap membutuhkan validasi urutan.
- Mempertahankan heuristik key manifest sebagai sumber utama. Ditolak karena
  block tanpa key tidak punya hint dan hasilnya tidak deterministik.
- Mewajibkan `rows` untuk semua layout. Ditolak karena rows preset adalah milik
  `LayoutSpec`, bukan author.

## Status

Diterima. Perubahan bentuk atau semantik `SlideIR.rows` memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
