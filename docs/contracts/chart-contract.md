# Kontrak Chart

Kontrak ini membekukan hubungan antara chart di YAML, chart native di PPTX,
dan linked chart di Google Slides. Chart adalah objek data, bukan gambar.
Data mengalir satu arah dari YAML ke Sheets; tidak ada pull data chart.

Status: F0 contract, version 1
Sumber: AUTO_OFFICE_PLAN.md bagian 8.3, 8.4, dan 9.1 sampai 9.5.

## Bentuk data

- `chart_id` logis: `<slide_id>.<block_id>`, misalnya `s04.chart1`; unik per deck.
- Field spec: `kind`, `orientation`, `title`, `alt`, `categories`, `series`,
  `unit`, dan `caption`.
- `kind`: `bar`, `line`, atau `donut`.
- `orientation`: `vertical` atau `horizontal`, hanya untuk `bar`.
- `series[].name` plain text dan `series[].values` adalah angka.
- `categories` minimal dua label; panjang setiap `values` sama dengan
  panjang `categories`.
- `chartSeries` adalah token warna chart dengan tepat empat slot per theme.

Placeholder staging memakai nama dan alt `autooffice:chart:<chart_id>`.
State menyimpan `chart_id`, `tab_name`, `sheet_id`, dan `embedded_chart_id`.

## Aturan native dan linked

- PPTX: `bar` menjadi bar atau column chart native, `line` menjadi line chart
  native dengan marker, `donut` menjadi doughnut chart native.
- Google Slides: setiap chart block menjadi linked Sheets chart.
- Chart tidak boleh menjadi gambar, screenshot, atau kumpulan shape.
- Chart tidak boleh diubah menjadi gambar untuk PDF.
- Warna seri dan kategori donut berasal dari `chartSeries` yang lolos kontras 3:1.
- Legend, gridline, axis, title, dan font berasal dari token.
- Chart title native; alt manusia di `descr` dan key chart di metadata.
- Chart tidak boleh menutupi teks atau keluar dari slot chart.

## Batas slot warna

- Maksimal empat slot warna per chart pada semua theme.
- `bar` dan `line`: jumlah slot adalah jumlah seri, 1 sampai 4.
- `donut`: tepat satu seri dan 2 sampai 4 kategori berwarna.
- Lima seri atau lima kategori donut ditolak schema, bukan dipotong.
- Palet `indigo`: `#4F46E5`, `#0F766E`, `#B45309`, `#BE123C`.
- Palet `hitam`: `#111827`, `#374151`, `#4B5563`, `#6B7280`.
- Batas ini menjaga validitas deck saat theme berganti.

## Sheets dan preflight

- Satu spreadsheet per deck; satu tab per chart; satu chart object per tab.
- Nama spreadsheet: `AutoOffice Charts - <meta.title>`.
- Tab memakai `chart_id`; bila lebih dari 100 karakter, potong dan tambah hash
  8 karakter.
- Baris 1 header; kolom A kategori; kolom B dan seterusnya seri.
- Tidak ada formula dan tidak ada data dua arah.
- Chart object diletakkan di area yang tidak menutupi data.
- Preflight table berjalan sebelum placeholder chart dihapus.
- Preflight memverifikasi semua placeholder lengkap sebelum menghapus satu pun.
- Placeholder tidak ditemukan atau ganda berarti push gagal.
- Linked chart dibuat dengan `createSheetsChart` dan `linkingMode: LINKED`.
- Posisi dan ukuran linked chart diambil dari placeholder.
- Bila linked chart untuk `chart_id` sudah ada, jangan buat duplikat.
- Rerun harus idempoten; kegagalan di tengah dicatat di state.
- Bila preflight gagal, tidak ada placeholder dihapus, tidak ada linked chart
  dibuat, dan state tidak ditulis.

## Invariant

- Satu chart native PPTX per chart block.
- Satu linked chart Slides per chart block.
- Chart data, title, dan label tidak ikut pull, diff, atau apply teks.
- Tidak ada edit chart dari Slides ke YAML.
- Tidak ada formula, data dua arah, atau chart image.
- Jumlah nilai setiap seri sama dengan jumlah kategori.
- Jumlah slot warna tidak lebih dari empat.
- `chart_id` stabil dan tidak berubah saat reorder.
- Warna chart tidak boleh ditulis di YAML.
- Spreadsheet kedua tidak dibuat bila state masih valid.
- Spreadsheet dan presentasi user tidak dihapus otomatis.

## Contoh minimal

```yaml
- id: chart1
  type: chart
  kind: line
  title: "Adopsi per kuartal"
  alt: "Grafik garis adopsi 2025 dan 2026 naik setiap kuartal"
  categories: ["Q1", "Q2", "Q3", "Q4"]
  series:
    - name: "2025"
      values: [12, 18, 27, 35]
    - name: "2026"
      values: [20, 29, 41, 52]
  unit: "persen"
```

## Acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Aturan | Test kontrak |
| --- | --- |
| Chart PPTX terdeteksi native dan bukan gambar. | `tests/contract/test_chart_contract.py` (planned) |
| Data chart XML sama dengan nilai YAML. | `tests/contract/test_chart_contract.py` (planned) |
| Lima seri `bar` atau `line` ditolak. | `tests/contract/test_chart_contract.py` (planned) |
| Donut dengan dua seri atau lima kategori ditolak. | `tests/contract/test_chart_contract.py` (planned) |
| `chartSeries` lolos kontras 3:1 di indigo dan hitam. | `tests/contract/test_chart_contract.py` (planned) |
| Placeholder memakai marker `autooffice:chart:<chart_id>`. | `tests/contract/test_chart_contract.py` (planned) |
| Preflight gagal tidak menghapus placeholder dan tidak menulis state. | `tests/contract/test_chart_contract.py` (planned) |
| Satu tab per chart dan satu chart object per tab. | `tests/integration/test_google_charts.py` (planned) |
| Rerun tidak membuat linked chart duplikat. | `tests/integration/test_google_charts.py` (planned) |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
