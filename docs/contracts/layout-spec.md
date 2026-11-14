# Kontrak Spesifikasi Layout

Kontrak ini membekukan cara layout engine mengubah `DeckIR` dan `LayoutSpec`
menjadi `LayoutPlan`. Geometri dihitung dari grid 12 kolom dan token desain,
bukan dari angka authoring. Author hanya memilih layout, urutan block, dan
`span`; posisi absolut tidak pernah menjadi input.

Status: F0 contract, version 1
Sumber: AUTO_OFFICE_PLAN.md bagian 6 dan 7 (7.1 sampai 7.8).

## Daftar Isi

- [Input dan output](#input-dan-output)
- [Bentuk data](#bentuk-data)
- [Otoritas slots dan rows](#otoritas-slots-dan-rows)
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


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    layout_id: str
    slots: tuple[SlotSpec, ...]
    rows: tuple[tuple[str, ...], ...]
    accepts_source: bool


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
  block yang diterima, dan `role` slot.
- `rows` hanya menyusun ID slot untuk geometri preset. Setiap ID di dalam
  `rows` wajib merujuk `slot_id` yang ada di `slots`, tidak duplikat, dan
  setiap slot muncul tepat satu kali.
- `rows` bukan salinan `SlotSpec` dan bukan `rows` author untuk
  `layout: custom`. `rows` author tetap berada di `deck.yaml`.
- `accepts_source` menentukan apakah layout merender field slide `source`.
  `source` bukan slot.

## Registry dan discovery

Registry layout F0 adalah daftar statis di
`src/autooffice/deck/layout/registry.py`. Discovery preset berbasis file
adalah deliverable F1-LAYOUT; sebelum itu, menambah preset memerlukan
integration owner mengubah registry. Tidak ada fallback layout.

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
- `span` bilangan bulat 1 sampai 12; hanya untuk `layout: custom`.
- Block dirender kiri ke kanan sesuai urutan array.
- Tidak ada nested row, nested column, atau row gap override.
- Tinggi row mengikuti konten tertinggi di row itu.
- Block yang lebih pendek tidak boleh memaksa tinggi absolut.
- Preset memiliki rows internal dan slot sendiri; author tidak menulis `rows`.
- Slot wajib harus ada; slot opsional boleh tidak ada; block di luar slot ditolak.
- `divider` dan `spacer` hanya dipakai di `custom`.

## Overflow

Kebijakan v1 adalah fail atau flag, bukan shrink.

- Text tidak memakai autofit, shrink, atau pengecilan font diam-diam.
- Pengukuran memakai metrik Plus Jakarta Sans yang dibundel, lebar slot,
  padding, dan line-height dari token.
- Tabel, code block, dan row custom yang melewati area konten menggagalkan build.
- Tidak ada ellipsis otomatis dan tidak ada pemotongan tanpa peringatan.
- Pesan error menyebut slide ID, block ID, key, dan perkiraan overflow.

## Invariant

- Satu `LayoutPlan` per build berisi satu `SlideLayout` per slide.
- Geometri authoring hanya berasal dari layout dan `span`.
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

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Aturan | Test kontrak |
| --- | --- |
| Rumus kolom dan `span` menghasilkan lebar yang benar. | `tests/contract/test_layout_spec.py` (planned) |
| Jumlah `span` lebih dari 12 dalam satu row ditolak. | `tests/contract/test_layout_spec.py` (planned) |
| `span` di preset, `span` 0, dan `span` 13 ditolak. | `tests/contract/test_layout_spec.py` (planned) |
| Field geometri authoring ditolak. | `tests/contract/test_layout_spec.py` (planned) |
| Overflow teks, tabel, code, dan row menghasilkan error terstruktur. | `tests/contract/test_layout_spec.py` (planned) |
| Slot wajib hilang dan block di luar slot ditolak. | `tests/contract/test_layout_spec.py` (planned) |
| Hasil layout identik untuk input yang sama. | `tests/contract/test_layout_spec.py` (planned) |
| Golden layout memeriksa posisi slot dan `span`. | `tests/golden/test_layout_*.py` (planned) |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
