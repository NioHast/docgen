# Pipeline Deck

Halaman ini menjelaskan perjalanan satu `deck.yaml` sampai PPTX, PDF, atau
Google Slides. Kontrak normatifnya ada di
[Deck IR](../contracts/deck-ir.md),
[key grammar](../contracts/key-grammar.md),
[skema deck](../contracts/deck-schema.md),
[layout](../contracts/layout-spec.md), dan
[renderer PPTX](../contracts/pptx-renderer.md). Panduan menulis YAML ada di
[deck-authoring.md](../user/deck-authoring.md).

## Diagram

```text
deck.yaml   transcripts.md   copy.yaml   assets/   diagrams/
    |             |              |          |          |
    +-------------+--------------+----------+----------+
                  |
                  v
          loader (safe YAML, strict)
                  |
                  v
          schema validation
                  |
                  v
          compiler -> DeckIR + KeyManifest
                  |              |
                  |              +--> coverage plan
                  v
          transcript parser -> TranscriptIR
                  |
                  v
          copy checker (error berhenti di sini)
                  |
                  v
          layout engine (slot, rows, measure)
                  |
                  v
              LayoutPlan
        |            |               |
        v            v               v
   PPTX render   staging PPTX     PDF via COM
                      |
                      v
          Google Slides + linked Sheets chart
```

## Tahap

| Tahap | Input | Output | Gagal bila |
| --- | --- | --- | --- |
| Loader | `deck.yaml` | mapping YAML | YAML tidak valid, key duplikat, tag kustom, atau lebih dari satu dokumen. |
| Schema | mapping | `DeckDefinition` | Field asing, tipe salah, geometri ditulis, ID duplikat, atau path aset tidak aman. |
| Compiler | `DeckDefinition` | `DeckIR` dan `KeyManifest` | ID atau key duplikat, inline Markdown tidak valid, atau key melebihi 160 karakter. |
| Transcript | `transcripts.md` | `TranscriptIR` | Slide hilang, duplikat, asing, bahasa tidak dikenal, atau durasi tidak valid. |
| Coverage | `DeckIR` | coverage plan | Ada objek tampil tanpa key, alt hilang, atau key duplikat. |
| Copy | `DeckIR`, `TranscriptIR`, `copy.yaml` | diagnostic | Ada diagnostic berperingkat error. |
| Layout | `DeckIR`, theme | `LayoutPlan` | Slot wajib kosong, role tidak cocok, atau overflow. |
| Render | `DeckIR`, `LayoutPlan`, theme | PPTX atau PDF | Font, `mmdc`, atau target render gagal. |
| Sync | staging PPTX, state | presentasi Slides | Kredensial, preflight chart, atau state tidak valid. |

Urutan ini penting: seluruh validasi naskah, coverage, dan copy selesai sebelum
layout, dan layout selesai sebelum render. Urutan internal antara coverage dan
copy dapat berbeda antara `check` dan `build`, tetapi keduanya wajib bersih
sebelum slide dirender. Error naskah tidak boleh baru ditemukan setelah slide
jadi.

## DeckIR dan key

`DeckIR` adalah satu-satunya objek yang dibaca layout engine, copy checker, dan
renderer. Renderer tidak membaca `deck.yaml` dan tidak mengenal nama theme.

Setiap teks tampil punya satu key datar dan satu binding. Contoh dari demo
deck:

| Lokasi YAML | Key |
| --- | --- |
| `slides[id=s01].blocks[id=title].text` | `s01.title.text` |
| `slides[id=s03].blocks[id=points].items[0]` | `s03.points.item1.text` |
| `slides[id=s05].notes` | `s05.notes` |
| `slides[id=s05].source.text` | `s05.source.text` |
| `slides[id=s09].blocks[id=table1].rows[2][3]` | `s09.table1.r3.c4` |
| `slides[id=s07].blocks[id=chart1].series[0].values[2]` | `s07.chart1.series1.value3` |

Binding menyimpan `yaml_path`, jadi `apply` menulis kembali ke lokasi yang pasti,
bukan menebak dari string key. Indeks leaf selalu 1-based; indeks array YAML
tetap 0-based.

Coverage plan memastikan setiap objek tampil punya key, tidak ada key duplikat,
dan setiap media punya alt. Pada branch ini, `check` demo deck melaporkan 306
key dan 3 chart untuk 24 slide.

## Invariant

- Satu berkas YAML per deck. `transcripts.md`, `copy.yaml`, dan aset adalah
  pendamping, bukan sumber konten kedua.
- Input yang sama menghasilkan `DeckIR`, `KeyManifest`, dan `LayoutPlan` yang
  deterministik.
- `DeckIR` dan turunannya immutable. Renderer tidak boleh memutasi IR.
- Satu key mewakili tepat satu nilai tampilan. ID slide dan block stabil
  lintas reorder.
- Semua teks tampil punya binding; teks tanpa key hanya chrome terdaftar.
- Layout tidak menciptakan teks, tidak menambah block, dan tidak punya fallback.
- Chart dan tabel tetap native. Chart tidak boleh menjadi gambar.
- Tidak ada shrink, autofit, atau pemotongan diam-diam. Overflow menggagalkan
  build.
- Geometri authoring hanya berasal dari layout dan `span`.
- Renderer boleh menulis koordinat ke PPTX setelah `LayoutPlan` dihitung.
- Tidak ada network atau LLM di `check`. Google hanya disentuh target `slides`.

## Modul

| Tanggung jawab | Modul |
| --- | --- |
| Loader dan schema | `autooffice.deck.model.loader`, `autooffice.deck.model.schema` |
| Compiler, key, binding | `autooffice.deck.model.compiler`, `keys`, `bindings` |
| Copy checker | `autooffice.deck.copy.checker`, `autooffice.deck.copy.config` |
| Transcript | `autooffice.deck.transcript.parser` |
| Layout dan overflow | `autooffice.deck.layout` |
| Render PPTX | `autooffice.deck.render.pptx` |
| Sinkronisasi Slides | `autooffice.google.slides` |

## Yang tidak dilakukan pipeline

- Tidak ada ekspresi, perhitungan angka, atau style inline di YAML.
- Tidak ada layout fallback untuk nama yang tidak dikenal.
- Tidak ada pull data chart dari Slides ke YAML.
- Tidak ada penulisan teks dari renderer; semua teks berasal dari block atau
  field slide.
- Tidak ada nama package atau entry point lama di permukaan perintah.
