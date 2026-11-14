# ADR 0012: Kind Chart pada Slot Preset

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L06, L07, L08, L21
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 6, 7, dan 8.3;
  [ADR 0004](0004-layouts-and-rendering.md),
  [ADR 0007](0007-slot-span.md), dan
  [kontrak layout](../contracts/layout-spec.md)

## Konteks

Preset `bars`, `line`, dan `donut` dinamai menurut visual chart yang dimaksud,
tetapi `SlotSpec` tidak menyimpan kind chart yang diwajibkan. Akibatnya preset
`bars` menerima block `chart` dengan `kind: line`, dan sebaliknya. Deck tetap
lolos validasi, tetapi nama layout tidak lagi menggambarkan isi slide dan
kombinasi yang tidak disengaja tidak bisa ditolak lebih awal.

Aturan ini tidak dapat dinyatakan lewat `block_types` karena ketiganya
menerima block type `chart` yang sama. Menambahkan pengecualian per nama preset
di layout engine akan menyembunyikan kontrak di kode, sedangkan nama layout
sendiri bukan input yang boleh dipakai layout engine untuk bercabang.

## Keputusan

1. `SlotSpec` mendapat field `chart_kind: str | None = None`.
2. Nilai yang sah hanya `bar`, `line`, atau `donut`. Nilai lain, termasuk
   string kosong dan non-string, ditolak `LayoutSpecError` saat `LayoutSpec`
   dibuat.
3. `None` berarti slot tidak membatasi kind chart.
4. `validate_slide` memeriksa kecocokan hanya bila slot memiliki `chart_kind`
   dan block yang mengisi slot bertipe `chart`. Block non-chart tidak
   dibandingkan dengan `chart_kind`.
5. Ketidakcocokan melempar `LayoutSpecError` yang menyebut slide, block, slot,
   kind aktual, dan kind yang disyaratkan.
6. Preset `bars`, `line`, dan `donut` menetapkan `chart_kind` berturut-turut
   `bar`, `line`, dan `donut` pada slot `chart1`.
7. Layout `custom` tidak memakai `SlotSpec`, sehingga tidak terkena aturan ini.
   Demo deck tetap valid karena setiap chart sudah memakai kind yang sesuai
   dengan layout-nya.

## Konsekuensi

- Bentuk `SlotSpec` berubah setelah F0 dan dicatat sebagai amandemen melalui
  ADR ini; test shape wajib memuat field `chart_kind`.
- Test data preset wajib memeriksa `chart_kind`, dan test slot wajib memeriksa
  penolakan kind yang salah, penerimaan kind yang benar, serta slot tanpa
  `chart_kind`.
- Kesalahan authoring terdeteksi saat `autooffice check` dan build, bukan
  menghasilkan deck dengan visual yang tidak sesuai nama layout.
- Preset chart baru wajib menetapkan `chart_kind` bila nama atau desainnya
  mengikat satu kind tertentu.
- Tidak ada perubahan bentuk YAML. Author tetap menulis `kind` pada block
  `chart`; field baru hanya berada di kontrak layout internal.

## Alternatif yang ditolak

- Mencocokkan `kind` dengan `layout_id` di layout engine. Ditolak karena layout
  engine tidak boleh bercabang berdasarkan nama layout dan aturan menjadi
  tersembunyi.
- Menambahkan block type baru per kind chart, misalnya `bar-chart`. Ditolak
  karena menduplikasi kontrak block `chart` dan mengubah schema YAML.
- Menambahkan aturan kondisional di schema YAML. Ditolak karena schema tidak
  memiliki registry layout saat validasi dan aturan slot adalah milik
  `LayoutSpec`.
- Membiarkan kind apa pun dan hanya mengandalkan dokumentasi. Ditolak karena
  kesalahan authoring tidak terdeteksi dan nama preset menjadi menyesatkan.
- Mewajibkan `chart_kind` pada semua slot chart. Ditolak karena layout custom
  dan preset chart generik di masa depan mungkin tidak mengikat satu kind.

## Status

Diterima. Perubahan bentuk atau semantik `SlotSpec.chart_kind` memerlukan ADR
baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
