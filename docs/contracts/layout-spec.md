# Kontrak Spesifikasi Layout

Kontrak ini membekukan cara layout engine mengubah `DeckIR` dan `LayoutSpec`
menjadi `LayoutPlan`. Geometri dihitung dari grid 12 kolom dan token desain,
bukan dari angka authoring. Author hanya memilih layout, urutan block, dan
`span` untuk `custom`; posisi absolut tidak pernah menjadi input.

Status: F0 contract, version 1, diamendemen ADR 0007, ADR 0008, ADR 0009, dan
ADR 0012. F1-LAYOUT menambahkan klarifikasi discovery, penempatan row preset,
source, dan gate overflow. Amandemen pasca-F0 menambahkan `SlotSpec.span` untuk
preset asimetris, `LayoutSpec.min_one_of` untuk grup slot minimal satu,
`SlideIR.rows` untuk batas row custom eksplisit, dan `SlotSpec.chart_kind`
untuk mengikat kind chart pada slot preset.
Sumber: AUTO_OFFICE_PLAN.md bagian 6 dan 7 (7.1 sampai 7.8);
[docs/decisions/0007-slot-span.md](../decisions/0007-slot-span.md);
[docs/decisions/0008-min-one-of.md](../decisions/0008-min-one-of.md);
[docs/decisions/0009-explicit-custom-rows.md](../decisions/0009-explicit-custom-rows.md);
[docs/decisions/0012-chart-kind-preset.md](../decisions/0012-chart-kind-preset.md).

## Daftar Isi

- [Input dan output](#input-dan-output)
- [Bentuk data](#bentuk-data)
- [Otoritas slots dan rows](#otoritas-slots-dan-rows)
- [Kind chart per slot](#kind-chart-per-slot)
- [Slot minimal satu (min_one_of)](#slot-minimal-satu-min_one_of)
- [Registry dan discovery](#registry-dan-discovery)
- [Kanvas dan grid](#kanvas-dan-grid)
- [Rows dan tinggi](#rows-dan-tinggi)
- [Overflow](#overflow)
- [Invariant](#invariant)
- [Acceptance](#acceptance)

## Input dan output

- Input: `DeckIR`, registry `LayoutSpec`, `Theme`, dan token spacing.
- Output: satu `LayoutPlan` per build; build gagal bila daftar overflow tidak kosong.
- Pengukuran tidak memakai browser, PowerPoint COM, atau Google Slides.

## Bentuk data

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlotSpec:
    slot_id: str
    required: bool
    block_types: tuple[str, ...]
    role: str | None
    span: int = 1
    chart_kind: str | None = None


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    layout_id: str
    slots: tuple[SlotSpec, ...]
    rows: tuple[tuple[str, ...], ...]
    accepts_source: bool
    min_one_of: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class PlacedBlock:
    block_id: str
    left_emu: int
    top_emu: int
    width_emu: int
    height_emu: int


@dataclass(frozen=True, slots=True)
class SlideLayout:
    slide_id: str
    boxes: tuple[PlacedBlock, ...]
    overflow_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LayoutPlan:
    slides: tuple[SlideLayout, ...]
```

## Otoritas slots dan rows

- `slots` adalah otoritas kontrak slot: `slot_id`, wajib atau opsional, tipe
  block yang diterima, `role` slot, `span` slot, dan `chart_kind` slot.
- `span` slot adalah lebar slot dalam kolom grid 12 kolom, bilangan bulat 1
  sampai 12, dan default 1. Hanya layout preset yang memakai `SlotSpec.span`.
- `rows` hanya menyusun ID slot untuk geometri preset. Setiap ID di dalam
  `rows` wajib merujuk `slot_id` yang ada di `slots`, tidak duplikat, dan
  setiap slot muncul tepat satu kali dalam satu `LayoutSpec`.
- Jumlah `span` seluruh slot dalam satu row maksimal 12. Row boleh memakai
  kurang dari 12 kolom; sisa kolom di kanan row tetap kosong.
- `rows` bukan salinan `SlotSpec` dan bukan rows author untuk
  `layout: custom`. Rows author dikompilasi ke `SlideIR.rows`; layout engine
  membaca batas row custom dari IR, bukan dari `deck.yaml` atau heuristik span.
- `accepts_source` menentukan apakah layout merender field slide `source`.
  `source` bukan slot.

## Kind chart per slot

`SlotSpec.chart_kind` mengikat satu slot chart preset ke satu kind chart.
Nilainya `bar`, `line`, `donut`, atau `None` (default). `None` berarti slot
tidak membatasi kind chart; `bar`, `line`, dan `donut` berarti block chart yang
mengisi slot harus memakai `kind` yang sama.

- Nilai selain tiga kind itu, termasuk string kosong dan non-string, ditolak
  saat `LayoutSpec` dibuat.
- Pemeriksaan hanya berlaku bila slot punya `chart_kind` dan block yang
  mengisi slot bertipe `chart`. Block non-chart tidak dibandingkan dengan
  `chart_kind`.
- Ketidakcocokan menggagalkan validasi slide dengan `LayoutSpecError` yang
  menyebut slide, block, slot, kind aktual, dan kind yang disyaratkan.
- Preset `bars`, `line`, dan `donut` memakai `chart_kind` berturut-turut
  `bar`, `line`, dan `donut` pada slot `chart1`.
- Layout `custom` tidak memakai `SlotSpec`, sehingga tidak terkena aturan ini.

## Slot minimal satu (min_one_of)

`LayoutSpec.min_one_of` menyatakan grup slot yang harus terisi minimal satu
anggota pada setiap slide. Field ini melengkapi `required` per slot: `required`
berarti satu slot wajib hadir, sedangkan `min_one_of` berarti setidaknya satu
dari beberapa slot alternatif wajib hadir tanpa memaksa slot tertentu.

- Nilai default adalah `()`, artinya tidak ada grup minimal satu.
- Setiap grup adalah tuple slot ID yang tidak kosong.
- Seluruh slot ID di dalam grup wajib ada di `slots`.
- Satu slot ID hanya boleh muncul di satu grup; duplikat di dalam atau antar
  grup ditolak.
- Slot anggota grup tidak otomatis menjadi `required=True`. Preset yang memakai
  `min_one_of` menetapkan `required=False` pada anggota grup agar salah satu
  anggota lain bisa menggantikannya.
- Validasi slide gagal dengan `LayoutSpecError` yang menyebut slide dan grup
  bila tidak satu pun slot di grup hadir pada `blocks` slide.

Contoh: preset `toc` memakai
`min_one_of=(("group1", "group2", "group3"),)`, dan preset `kpi` memakai
`min_one_of=(("kpi1", "kpi2", "kpi3", "kpi4"),)`.

## Registry dan discovery

Discovery preset berbasis file adalah deliverable F1-LAYOUT. Registry memindai
package `autooffice.deck.layout.presets` untuk setiap modul yang mengekspos
`LAYOUT: LayoutSpec`, lalu mengurutkannya secara deterministik berdasarkan
`layout_id`. Modul tanpa `LAYOUT` diabaikan; `LAYOUT` bertipe salah dan
`layout_id` duplikat menggagalkan registry.

Bila package preset belum berisi satu pun `LAYOUT` (kondisi F1), registry
memakai fallback nama katalog F0 agar schema tetap menerima 19 preset dan
`custom`. Fallback hanya berisi nama; belum ada `LayoutSpec` bawaan. Layout
`custom` bukan preset dan tetap tersedia sebagai nama layout.

Preset F2 cukup menambah modul di package tersebut; tidak ada perubahan pada
`registry.py`. Tidak ada fallback layout saat build: layout yang tidak
ditemukan ditolak.

## Kanvas dan grid

- Kanvas 16:9, 13.333 inci x 7.5 inci, ekivalen 1280 x 720 px dan 960 x 540 pt.
- Grid 12 kolom; margin dan gutter berasal dari token.
- Kolom dihitung dari lebar konten:

```text
content_width = slide_width - margin_left - margin_right
column_width = (content_width - 11 * gutter) / 12
span_width(span) = span * column_width + (span - 1) * gutter
```

- Posisi horizontal mengikuti urutan block dalam row dan nilai `span`.
- Tidak ada offset, `start`, `col_start`, atau `align` horizontal.
- Sisa kolom di kanan row boleh kosong.

## Rows dan tinggi

- `rows` minimal satu dan setiap row minimal satu block.
- Jumlah `span` dalam satu row maksimal 12.
- `SlotSpec.span` dan `BlockIR.span` adalah dua kontrak terpisah:
  - Layout preset memakai `SlotSpec.span`. `BlockIR.span` pada block preset
    ditolak karena posisi preset bukan milik author.
  - Layout custom memakai `BlockIR.span` yang ditulis author. `SlotSpec` tidak
    dipakai layout custom.
- Keduanya memakai bilangan bulat 1 sampai 12 dan aturan jumlah per row yang
  sama.
- Block dirender kiri ke kanan sesuai urutan array.
- Tidak ada nested row, nested column, atau row gap override.
- Tinggi row mengikuti konten tertinggi di row itu.
- Block yang lebih pendek tidak boleh memaksa tinggi absolut.
- Media block (`image`, `chart`, `diagram`) memakai contain dan tinggi yang
  tersedia di area konten; tinggi natural 16:9 bukan tinggi tetap.
- Preset memiliki rows internal dan slot sendiri; author tidak menulis `rows`.
- Slot wajib harus ada; slot opsional boleh tidak ada; block di luar slot ditolak.
- Setiap grup `min_one_of` harus terisi minimal satu slot pada slide.
- `divider` dan `spacer` hanya dipakai di `custom`.

Klarifikasi penempatan preset F1-LAYOUT:

- Geometri row preset memakai `span` masing-masing `SlotSpec`, bukan pembagian
  rata. Contoh row 7+5 menghasilkan lebar 7 kolom dan 5 kolom.
- Slot opsional yang tidak hadir tidak menghasilkan `PlacedBlock` dan tidak
  memakan kolom. Slot sesudahnya bergeser ke kiri dengan `span` tetap; sisa
  kolom di kanan row dibiarkan kosong. Span tidak dibagi ulang.
- Setiap `PlacedBlock` memakai tinggi row, yaitu tinggi konten natural
  tertinggi pada row tersebut. Tidak ada tinggi absolut.
- `source` bukan slot dan tidak menghasilkan `PlacedBlock`. Bila
  `accepts_source` bernilai `False`, source yang ada ditolak agar tidak hilang
  diam-diam.

Klarifikasi custom F1-LAYOUT/F2-CUSTOM-GRID:

- `layout: custom` tidak memakai `SlotSpec` atau `LayoutSpec` preset. Tidak ada
  pencarian slot, `required`, `role` slot, atau `min_one_of` pada custom.
- Rows custom berasal dari author di `deck.yaml` dan dikompilasi menjadi
  `SlideIR.rows`: satu tingkat rows, setiap row minimal satu block, dan setiap
  block wajib memiliki `span` 1 sampai 12. Compiler mempertahankan urutan block
  row-major yang sama dengan `SlideIR.blocks`.
- Layout engine memakai `SlideIR.rows` sebagai otoritas batas row, bukan
  heuristik span atau petunjuk key. Fallback span hanya berlaku untuk IR lama
  yang dibuat manual tanpa rows dan bukan jalur build compiler.
- Layout engine memvalidasi ulang IR custom sebelum menempatkan block: rows
  tidak kosong, block ID unik, block type valid, jumlah span per row maksimal
  12, serta tidak ada field geometri absolut atau field slot preset.
- Urutan block di dalam row menentukan posisi kiri ke kanan. Block tidak dapat
  membuat row sendiri, mengatur posisi vertikal, atau menimpa row gap.
- Tinggi row custom mengikuti block tertinggi pada row itu. Media tetap memakai
  mode contain dan tinggi area yang tersedia; tinggi natural 16:9 bukan tinggi
  tetap.
- `source` dan `notes` tetap boleh ada pada slide custom. Keduanya bukan block,
  tidak menghasilkan `PlacedBlock`, dan tidak mengubah geometri rows.
- `plan_deck` merencanakan slide custom tanpa entri registry preset dan tanpa
  melempar `UnknownLayoutError`.

## Overflow

Kebijakan v1 adalah fail atau flag, bukan shrink.

- Text tidak memakai autofit, shrink, atau pengecilan font diam-diam.
- Pengukuran memakai metrik Plus Jakarta Sans yang dibundel, lebar slot,
  padding, dan line-height dari token.
- Tabel, code block, dan row custom yang melewati area konten menggagalkan build.
- Tidak ada ellipsis otomatis dan tidak ada pemotongan tanpa peringatan.
- Pesan error menyebut slide ID, block ID, key, dan perkiraan overflow.

Klarifikasi F1-LAYOUT:

- Pengukuran teks memakai TTF Plus Jakarta Sans yang dibundel melalui Pillow.
  Line-height dan tracking berasal dari `Theme.typography`; code memakai
  `Theme.code`.
- `SlideLayout.overflow_keys` diisi dalam urutan row dan slot. Overflow
  horizontal (teks atau sel yang lebih lebar dari area) dan overflow vertikal
  (row melewati batas bawah area konten) sama-sama masuk daftar tersebut.
- `plan_slide` dan `plan_deck(fail_on_overflow=False)` mengembalikan plan
  beserta `overflow_keys` untuk diagnostik. `plan_deck` dan
  `build_layout_plan` gagal dengan `LayoutOverflowError` bila daftar tidak
  kosong. Error membawa `plan`, `findings`, dan `overflow_keys`.

## Invariant

- Satu `LayoutPlan` per build berisi satu `SlideLayout` per slide.
- Geometri authoring hanya berasal dari layout dan `span`.
- Layout preset memakai `SlotSpec.span`; layout custom memakai `BlockIR.span`.
  Tidak ada jalur yang mencampur keduanya.
- Batas row custom berasal dari `SlideIR.rows` hasil compiler, bukan heuristik
  span atau petunjuk key.
- `min_one_of` hanya menyatakan syarat kehadiran slot; ia tidak mengubah
  urutan row, `span`, atau `required` suatu slot.
- `chart_kind` hanya menyatakan kind chart yang sah untuk slot chart preset;
  ia tidak mengubah tipe block yang diterima slot atau urutan row.
- Field `x`, `y`, `left`, `top`, `right`, `bottom`, `width`, `height`,
  `position`, `absolute`, `anchor`, `translate`, `rotate`, `z`, dan `z_index`
  ditolak di semua objek authoring.
- Renderer boleh menulis koordinat ke PPTX setelah `LayoutPlan` dihitung.
- Semua margin, padding, gutter, radius, font size, dan line-height berasal
  dari token; renderer tidak menulis angka baru.
- `spacer.size` hanya memilih token `sm`, `md`, atau `lg`.
- Layout tidak bercabang berdasarkan nama deck, path input, atau theme.
- Layout tidak menciptakan teks dan tidak menambah block `callout`.
- Layout di luar katalog ditolak; tidak ada fallback layout.
- `LayoutPlan` deterministik untuk input yang sama.
- Tidak ada fixed height, overlay di luar block, atau absolute frame di v1.

## Acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Perilaku F1-LAYOUT ada di `tests/deck/layout/`; golden visual per layout tetap deliverable F2.

| Aturan | Test kontrak |
| --- | --- |
| Rumus kolom dan `span` menghasilkan lebar yang benar. | `tests/deck/layout/test_grid.py` |
| Jumlah `span` lebih dari 12 dalam satu row ditolak. | `tests/deck/layout/test_grid.py`, `tests/deck/layout/test_slots.py` |
| `SlotSpec.span` 0 atau 13 ditolak; `BlockIR.span` di preset ditolak. | `tests/deck/layout/test_slots.py` |
| Row preset asimetris 7+5 memakai lebar slot, bukan pembagian rata. | `tests/deck/layout/test_plan.py` |
| Slot opsional yang absen tidak membagi ulang `span`. | `tests/deck/layout/test_plan.py` |
| Field geometri authoring ditolak. | `tests/deck/layout/test_slots.py` |
| Overflow teks, tabel, code, dan row menghasilkan error terstruktur. | `tests/deck/layout/test_measure.py`, `tests/deck/layout/test_plan.py` |
| Slot wajib hilang dan block di luar slot ditolak. | `tests/deck/layout/test_slots.py` |
| Grup `min_one_of` kosong, slot tidak dikenal, duplikat, atau tidak terisi ditolak. | `tests/deck/layout/test_slots.py`, `tests/deck/layout/test_presets_core.py` |
| Hasil layout identik untuk input yang sama. | `tests/deck/layout/test_plan.py` |
| Discovery preset deterministik dan fallback nama F0. | `tests/deck/layout/test_registry.py` |
| Batas row custom berasal dari `SlideIR.rows`; partial row unkeyed deterministik. | `tests/deck/layout/test_custom.py` |
| Golden layout memeriksa posisi slot dan `span`. | `tests/golden/test_layout_*.py` (planned) |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
