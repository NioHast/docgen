# ADR 0008: Grup Slot Minimal Satu

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L06, L21
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 6 dan 7,
  [ADR 0004](0004-layouts-and-rendering.md), dan
  [ADR 0007](0007-slot-span.md)

## Konteks

`SlotSpec.required` hanya bisa menyatakan bahwa satu slot tertentu wajib hadir.
Beberapa preset F2 membutuhkan syarat yang berbeda: minimal satu dari beberapa
slot alternatif harus hadir, tetapi tidak ada slot tertentu yang wajib. Contoh
utama adalah preset `toc` dengan `group1`, `group2`, dan `group3`, serta preset
`kpi` dengan `kpi1` sampai `kpi4`.

Memaksa `group1` atau `kpi1` sebagai `required` membuat slide yang hanya memakai
`group2` atau `kpi3` ditolak, padahal kontrak layout mengizinkan salah satu
anggota tersebut. Menambahkan logika khusus per preset di layout engine akan
menyembunyikan kontrak di kode dan menduplikasi aturan validasi.

## Keputusan

1. `LayoutSpec` mendapat field `min_one_of: tuple[tuple[str, ...], ...] = ()`.
   Setiap elemen adalah grup slot ID yang harus terisi minimal satu anggotanya
   pada setiap slide.
2. `LayoutSpec.__post_init__` memvalidasi bahwa setiap grup tidak kosong,
   seluruh slot ID-nya ada di `slots`, dan tidak ada slot ID yang muncul di lebih
   dari satu grup.
3. Slot anggota grup tidak otomatis menjadi `required=True`. Preset yang
   memakai `min_one_of` menetapkan `required=False` pada anggota grup agar
   anggota lain dapat menggantikannya.
4. `validate_slide` memeriksa setiap grup dan melempar `LayoutSpecError` yang
   menyebut slide dan grup bila tidak satu pun slot di grup hadir pada slide.
5. Preset `toc` memakai `min_one_of=(("group1", "group2", "group3"),)` dan
   preset `kpi` memakai `min_one_of=(("kpi1", "kpi2", "kpi3", "kpi4"),)`.
   Preset lain tidak berubah.
6. `rows`, `span`, dan urutan penempatan tidak berubah. `min_one_of` hanya
   menambah syarat kehadiran slot.

## Konsekuensi

- Kontrak `LayoutSpec` berubah setelah F0 dan dicatat sebagai amandemen melalui
  ADR ini.
- Preset dapat menyatakan alternatif slot tanpa logika khusus di layout engine.
- Test shape `LayoutSpec` wajib memuat field `min_one_of`, dan test preset wajib
  memeriksa slide yang hanya mengisi satu anggota grup.
- Pesan error kehadiran grup memakai `LayoutSpecError`, bukan
  `SlotValidationError`, karena yang dilanggar adalah kontrak `LayoutSpec`.
- Layout tanpa `min_one_of` tetap berperilaku sama karena default `()`.

## Alternatif yang ditolak

- Menjadikan `group1` atau `kpi1` selalu `required`. Ditolak karena slide yang
  hanya memakai `group2` atau `kpi3` menjadi tidak valid.
- Menambahkan pengecualian per preset di `validate_slide`. Ditolak karena
  kontrak layout tidak lagi dinyatakan di data `LayoutSpec`.
- Memakai string ekspresi atau bahasa aturan baru. Ditolak karena kebutuhan
  hanya satu tingkat: minimal satu dari sekumpulan slot, dan tuple slot ID sudah
  cukup tanpa parser tambahan.
- Menunda sampai F2. Ditolak karena preset `toc` dan `kpi` sudah membutuhkan
  kontrak ini sekarang.

## Status

Diterima. Perubahan bentuk atau semantik `min_one_of` memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
