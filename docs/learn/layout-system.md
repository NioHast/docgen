# Sistem Layout Deck

Halaman ini menjelaskan cara AutoOffice menempatkan block tanpa koordinat
authoring. Kontrak normatifnya ada di
[spesifikasi layout](../contracts/layout-spec.md), dengan amandemen
[ADR 0007](../decisions/0007-slot-span.md),
[ADR 0008](../decisions/0008-min-one-of.md),
[ADR 0009](../decisions/0009-explicit-custom-rows.md), dan
[ADR 0012](../decisions/0012-chart-kind-preset.md). Cara memilih layout saat
menulis YAML ada di [deck-authoring.md](../user/deck-authoring.md).

## Kanvas dan grid

Kanvas 16:9 berukuran 13,333 x 7,5 inci, setara 1280 x 720 px atau 960 x 540
pt. Semua posisi dihitung dari grid 12 kolom:

```text
content_width  = slide_width - margin_left - margin_right
column_width   = (content_width - 11 * gutter) / 12
span_width(n)  = n * column_width + (n - 1) * gutter
```

Margin, gutter, row gap, padding, dan tinggi baris adalah token design system,
bukan angka author. Author tidak menulis angka geometri sama sekali.

## Preset dan custom

| Aspek | Preset | `layout: custom` |
| --- | --- | --- |
| Geometri | Milik `LayoutSpec` | Dihitung dari `rows` author |
| Konten | `blocks` dengan ID slot | `rows` berisi block dengan `span` |
| `span` | Dilarang; slot punya `span` sendiri | Wajib 1 sampai 12 |
| Row | Internal, tidak ditulis author | Ditulis author, minimal satu |
| Block asing | Ditolak | ID bebas, unik per slide |
| `divider` dan `spacer` | Ditolak | Boleh |

Preset memakai slot sebagai kontrak. `slot_id` harus sama dengan ID block,
tipe block harus diterima slot, dan `role` block `text` harus sama dengan role
slot. Slot opsional yang tidak hadir tidak memakan kolom dan tidak membagi
ulang span slot lain. Custom tidak memakai `SlotSpec`, `required`, role slot,
atau `min_one_of`.

## Kind chart pada slot

`SlotSpec.chart_kind` mengikat slot chart preset ke satu kind chart. Nilainya
`bar`, `line`, `donut`, atau `None` (default). `None` berarti slot tidak
membatasi kind chart; nilai lain ditolak saat `LayoutSpec` dibuat.
Pemeriksaan hanya berlaku bila block yang mengisi slot bertipe `chart`,
sehingga block non-chart tidak dibandingkan. Ketidakcocokan menggagalkan
validasi slide dengan `LayoutSpecError` yang menyebut slide, block, slot, kind
aktual, dan kind yang disyaratkan.

Preset `bars`, `line`, dan `donut` menetapkan `chart_kind` berturut-turut
`bar`, `line`, dan `donut` pada slot `chart1`. Layout `custom` tidak memakai
`SlotSpec`, sehingga tidak terkena aturan ini. Perubahan bentuk atau semantik
field ini memerlukan ADR baru; lihat
[ADR 0012](../decisions/0012-chart-kind-preset.md).

## Span slot dan span block

Ada dua kontrak span yang terpisah dan tidak boleh dicampur:

- `SlotSpec.span` menentukan lebar slot preset. Nilainya ditetapkan layout,
  bukan author.
- `BlockIR.span` menentukan lebar block custom. Nilainya ditulis author di
  `deck.yaml`.

Keduanya bilangan bulat 1 sampai 12. Jumlah span dalam satu row maksimal 12;
sisa kolom di kanan row dibiarkan kosong. Block ditempatkan kiri ke kanan
sesuai urutan array. Contoh row 7+5 pada `image-split` memakai lebar 7 kolom
dan 5 kolom, bukan pembagian rata.

## min_one_of

`required` menyatakan satu slot tertentu wajib hadir. `min_one_of` menyatakan
minimal satu anggota dari beberapa slot alternatif harus hadir, tanpa memaksa
slot tertentu.

- `toc` memakai grup `group1`, `group2`, `group3`.
- `kpi` memakai grup `kpi1`, `kpi2`, `kpi3`, `kpi4`.

Anggota grup tidak otomatis `required`. Bila tidak satu pun anggota hadir,
validasi slide gagal. `min_one_of` tidak mengubah row, span, atau urutan
penempatan.

## Tinggi dan overflow

Tinggi row mengikuti block tertinggi di row itu. Tidak ada fixed height dan
tidak ada block yang boleh memaksa tinggi absolut.

Kebijakan v1 adalah fail atau flag, bukan shrink:

- Teks diukur dengan metrik Plus Jakarta Sans yang dibundel, lebar slot,
  padding, dan line-height token.
- Teks, tabel, code, dan row custom yang melewati area konten menghasilkan
  error dan build gagal.
- Tidak ada autofit, shrink, ellipsis otomatis, atau pemotongan tanpa
  peringatan.
- Pesan error menyebut slide, block, key, dan perkiraan overflow.
- Pengukuran deterministik dan tidak memakai browser, PowerPoint COM, atau
  Google Slides.

Media memakai tinggi area yang tersedia. Gambar default `contain`, sedangkan
`cover` memenuhi frame dengan crop proporsional, bukan regangan. Chart dan
tabel tidak boleh menutupi teks atau keluar dari slot.

## Tanpa absolute positioning

Schema menolak field geometri berikut di semua objek authoring:

```text
x, y, left, top, right, bottom, width, height,
position, absolute, anchor, translate, rotate, z, z_index
```

Schema juga menolak field style seperti `font_size`, `color`, `margin`, dan
`padding`. Renderer baru boleh menulis koordinat ke PPTX setelah layout engine
menghitung `LayoutPlan`. Larangan absolute berlaku pada authoring, bukan pada
XML output.

## Invariant

- Satu `LayoutPlan` per build berisi satu `SlideLayout` per slide.
- Geometri hanya berasal dari layout preset atau `rows` dan `span` custom.
- `SlotSpec.span` dan `BlockIR.span` tidak pernah tercampur dalam satu slide.
- Batas row custom berasal dari `SlideIR.rows` hasil compiler, bukan heuristik
  span atau key.
- Slot wajib harus ada; block di luar slot preset ditolak.
- Layout di luar katalog ditolak; tidak ada fallback.
- Layout tidak bercabang menurut nama deck, path input, atau theme.
- Semua spacing, radius, ukuran font, dan line-height berasal dari token.
- `spacer.size` hanya memilih token `sm`, `md`, atau `lg`.
- Hasil layout deterministik untuk input yang sama.
