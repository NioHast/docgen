# Kontrak Key Grammar

Kontrak ini membekukan key datar yang menjadi identitas teks lintas PPTX,
coverage, dan sinkronisasi Google Slides. Compiler membentuk key dari YAML,
menyimpannya di `KeyManifest`, dan menyimpan pemetaan balik ke `yaml_path`
melalui `KeyBinding`. Key yang sama dipakai untuk render, diff, pull, dan apply.

Status: F0 contract, version 1
Sumber: AUTO_OFFICE_PLAN.md bagian 5 (5.2 sampai 5.6).

## Bentuk data

```text
key          = slide_id "." path
path         = block_id "." leaf_path | slide_leaf
slide_leaf   = "notes" | "source.text"
slide_id     = "s" 2*DIGIT
block_id     = LOWER *(LOWER / DIGIT / "_")
leaf_path    = leaf_segment *("." leaf_segment)
leaf_segment = LOWER *(LOWER / DIGIT / "_")
```

Key untuk block mengikuti pola `<slide_id>.<block_id>.<leaf>`. Key untuk
slide sendiri mengikuti pola `<slide_id>.<leaf>`.

Contoh:

```text
s01.title.text
s01.notes
s01.source.text
s03.kpi1.value
s04.chart1.series1.value3
s05.table1.r2.c3
```

## Aturan ID dan leaf

- Slide ID wajib cocok dengan `^s[0-9]{2,}$`, eksplisit, unik dalam deck, dan
  tidak di-renumber saat reorder.
- Block ID wajib cocok dengan `^[a-z][a-z0-9_]*$`, unik per slide, tanpa titik,
  maksimal 32 karakter.
- Block boleh dipindah di dalam slide tanpa mengubah key.
- Leaf adalah nama field block. Indeks selalu 1-based.
- Bentuk indeks yang diizinkan: `itemN`, `catN`, `seriesN`, `valueN`, `rN`,
  `cN`, `hN`.
- Segmen hanya huruf kecil, angka, dan underscore. Tidak ada spasi, tanda
  hubung, atau titik di dalam satu segmen.
- Panjang key maksimal 160 karakter. Key lebih panjang ditolak, bukan dipotong.
- Key kosong dan key duplikat ditolak validator.

## Mapping nested YAML

| Lokasi YAML | Key |
| --- | --- |
| `slides[id=s03].blocks[id=title].text` | `s03.title.text` |
| `slides[id=s03].blocks[id=agenda].items[0]` | `s03.agenda.item1.text` |
| `slides[id=s03].blocks[id=table1].columns[1]` | `s03.table1.h2` |
| `slides[id=s03].blocks[id=table1].rows[2][3]` | `s03.table1.r3.c4` |
| `slides[id=s03].blocks[id=chart1].categories[1]` | `s03.chart1.cat2` |
| `slides[id=s03].blocks[id=chart1].series[0].name` | `s03.chart1.series1.name` |
| `slides[id=s03].blocks[id=chart1].series[0].values[2]` | `s03.chart1.series1.value3` |
| `slides[id=s03].notes` | `s03.notes` |
| `slides[id=s03].source.text` | `s03.source.text` |

Mapping ini adalah kontrak. Compiler tidak boleh mengganti nama leaf tanpa ADR.

## KeyBinding

Setiap key wajib punya satu binding. Field binding:

- `key`: key datar yang unik.
- `slide_id` dan `block_id`: pemilik key; `block_id` kosong untuk key slide.
- `leaf`: nama leaf beserta indeks bila ada.
- `kind`: `text`, `data`, `notes`, `source`, atau `media_text`.
- `sync`: apakah key ikut sinkronisasi teks Google Slides.
- `yaml_path`: path YAML yang disimpan compiler, misalnya
  `["slides", 2, "blocks", 1, "value"]`.
- `value`: string sumber untuk teks atau angka untuk data chart.
- `plain_text`: nilai tampilan setelah inline Markdown dan normalisasi.

Pull dan apply memakai `yaml_path`, bukan menebak posisi dari string key.
Binding harus deterministik; tidak boleh memakai hash acak atau urutan
dictionary yang tidak stabil.

## Contoh

```json
{
  "key": "s03.kpi1.value",
  "slide_id": "s03",
  "block_id": "kpi1",
  "leaf": "value",
  "kind": "text",
  "sync": true,
  "yaml_path": ["slides", 2, "blocks", 1, "value"],
  "value": "100%",
  "plain_text": "100%"
}
```

## Invariant

- Satu key mewakili tepat satu nilai tampilan.
- Key adalah satu string; nesting YAML tidak menjadi struktur key bersarang.
- ID stabil lintas reorder slide dan block.
- Semua indeks 1-based; indeks nol ditolak.
- Key duplikat, key kosong, dan key lebih dari 160 karakter ditolak.
- Setiap key punya tepat satu binding dengan `yaml_path`.
- `plain_text` adalah hasil normalisasi, bukan YAML mentah.
- Key yang dideklarasikan wajib muncul tepat satu kali di output.
- Key asing di remote ditolak saat apply, bukan dipetakan diam-diam.
- Rename slide ID atau block ID adalah breaking change dan butuh migrasi key.
- v1 tidak punya alias key.
- Chart data memakai `kind: data`; chart title dan label tidak ikut
  pull/diff/apply teks.

## Acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Aturan | Test kontrak |
| --- | --- |
| Grammar menolak slide ID, block ID, dan leaf yang tidak valid. | `tests/contract/test_key_grammar.py` (planned) |
| Indeks 0, indeks negatif, dan titik di dalam satu segmen ditolak. | `tests/contract/test_key_grammar.py` (planned) |
| Key duplikat ditolak dengan kedua lokasi. | `tests/contract/test_key_grammar.py` (planned) |
| Key lebih dari 160 karakter ditolak tanpa pemotongan. | `tests/contract/test_key_grammar.py` (planned) |
| Reorder slide dan block tidak mengubah key. | `tests/contract/test_key_grammar.py` (planned) |
| Mapping nested YAML ke key sesuai tabel. | `tests/contract/test_key_grammar.py` (planned) |
| `yaml_path` dipakai apply untuk menulis nilai kembali. | `tests/contract/test_key_grammar.py` (planned) |
| Binding deterministik untuk input yang sama. | `tests/contract/test_key_grammar.py` (planned) |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
