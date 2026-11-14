# ADR 0007: Span Slot Preset

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L05, L06, L08, L10, L12, L15
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 6, 7.1-7.8, dan
  [ADR 0004](0004-layouts-and-rendering.md)

## Konteks

F0 membekukan `SlotSpec` tanpa lebar kolom. Layout engine F1-LAYOUT kemudian
membagi 12 kolom secara rata di antara slot yang hadir dalam satu row. Aturan
itu cukup untuk layout simetris, tetapi 19 preset F2 membutuhkan komposisi
asimetris seperti 7+5, 8+4, dan 4+4+4. Tanpa lebar per slot, preset hanya bisa
memakai pembagian rata atau memindahkan angka geometri ke authoring, yang
dilarang oleh kontrak.

`BlockIR.span` sudah ada untuk layout `custom`. Field itu bukan kontrak yang
tepat untuk preset: author preset tidak menulis `span`, dan posisi block preset
harus ditentukan layout, bukan author.

## Keputusan

1. `SlotSpec` mendapat field `span: int = 1`. Nilainya lebar slot dalam kolom
   grid 12 kolom dan hanya berlaku untuk layout preset.
2. `span` slot wajib bilangan bulat 1 sampai 12. Jumlah seluruh `span` slot
   dalam satu row maksimal 12. `LayoutSpec.__post_init__` memanggil validator
   struktur sehingga definisi preset yang melanggar aturan gagal lebih awal.
3. Setiap ID slot di `rows` wajib ada di `slots`; validator yang sama menolak
   ID hantu, slot duplikat, dan slot yang tidak ditempatkan.
4. Layout engine memakai `SlotSpec.span` sebagai lebar block preset, bukan
   pembagian rata. `rows` tetap berisi ID slot, bukan objek `SlotSpec`.
5. Slot opsional yang tidak hadir tidak menghasilkan block dan tidak membagi
   ulang span. Slot sesudahnya bergeser ke kiri dengan span tetap; kolom sisa
   di kanan row dibiarkan kosong.
6. `BlockIR.span` tetap otoritas layout `custom` dan terpisah dari
   `SlotSpec.span`. Block preset yang membawa `span` tetap ditolak.

## Konsekuensi

- Preset F2 wajib mengisi `span` setiap slot sesuai komposisi visualnya.
  Default 1 hanya menjaga kompatibilitas bentuk dan bukan pengganti desain.
- Perubahan ini adalah amandemen kontrak pasca-F0 dan dicatat sebagai ADR.
- Test layout harus memeriksa lebar asimetris, batas span, jumlah row, dan ID
  slot yang tidak dikenal.
- Layout plan tetap deterministik karena span adalah data `LayoutSpec`, bukan
  input author atau hasil pengukuran.
- Custom grid tidak berubah pada F1-LAYOUT; implementasinya tetap milik
  F2-CUSTOM-GRID.

## Alternatif yang ditolak

- Membagi 12 kolom secara rata dan menambahkan pengecualian per preset di
  layout engine. Ditolak karena menciptakan logika geometri tersembunyi dan
  tidak bisa dinyatakan dalam kontrak preset.
- Memakai `BlockIR.span` untuk preset. Ditolak karena author preset tidak
  menulis block geometry dan field itu sudah menjadi otoritas custom.
- Menyimpan bobot atau rasio pecahan di `SlotSpec`. Ditolak karena grid 12
  kolom dan span bilangan bulat sudah menjadi kontrak yang ada.
- Menunda span ke F2. Ditolak karena F2 preset tidak bisa dibangun tanpa
  kontrak lebar yang stabil.

## Status

Diterima. Perubahan bentuk `SlotSpec`, aturan jumlah span per row, atau
hubungan span preset dengan span custom memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
