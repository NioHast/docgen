# Kontrak Deck IR

Kontrak ini membekukan model antara compiler dan renderer. Compiler
mentransformasi YAML tervalidasi menjadi `DeckIR` dan `KeyManifest`; layout
engine menambahkan `LayoutPlan`. Renderer hanya boleh menerima objek ini
beserta `Theme`, bukan path YAML atau file token.

Status: F0 contract, version 1, diamendemen ADR 0009 untuk `SlideIR.rows`.
Sumber: AUTO_OFFICE_PLAN.md bagian 3.4, 5.1, dan 8.1;
[docs/decisions/0009-explicit-custom-rows.md](../decisions/0009-explicit-custom-rows.md).

## Input dan output

- Input: objek schema tervalidasi dari compiler.
- Output: satu `DeckIR` immutable dan satu `KeyManifest` per build deck.
- Konsumen: layout engine, copy checker, renderer PPTX, dan sinkronisasi Slides.
- `LayoutPlan` adalah output layout engine, bukan bagian dari `DeckIR`.

## Bentuk data

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class KeyBinding:
    key: str
    slide_id: str
    block_id: str | None
    leaf: str
    kind: Literal["text", "data", "notes", "source", "media_text"]
    sync: bool
    yaml_path: tuple[str | int, ...]
    value: str | int | float
    plain_text: str


@dataclass(frozen=True, slots=True)
class KeyManifest:
    bindings: tuple[KeyBinding, ...]


@dataclass(frozen=True, slots=True)
class BlockIR:
    block_id: str
    block_type: str
    span: int | None
    role: str | None
    fields: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class SlideIR:
    slide_id: str
    layout: str
    order: int
    blocks: tuple[BlockIR, ...]
    notes: str | None
    source: Mapping[str, str] | None
    rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class DeckIR:
    schema: str
    meta: Mapping[str, str]
    theme_name: str
    slides: tuple[SlideIR, ...]
    keys: KeyManifest
```

`source` adalah mapping, bukan field `source_text`. Bila `source` ada,
`source["text"]` wajib dan `source["url"]` opsional; `source.text` menjadi
key, sedangkan `source.url` bukan key.

`rows` menyimpan block ID per row untuk slide `layout: custom`. Compiler
mengisi `rows` dari authoring dan mempertahankan urutan block row-major, sehingga
urutan ID di `rows` sama dengan urutan `blocks`. Slide preset memakai default
`rows=()`. Bila `rows` terisi, setiap ID wajib ada di `blocks`, tidak boleh
duplikat, dan setiap row minimal satu ID; slide custom wajib memuat setiap
block tepat satu kali, sedangkan slide non-custom boleh memuat sebagian block.
`rows` kosong berarti IR tidak membawa batas row eksplisit dan hanya dipakai
oleh IR yang dibuat manual; hasil compiler untuk slide custom selalu terisi.

`kind` hanya bernilai `text`, `data`, `notes`, `source`, atau `media_text`.
`text` untuk teks tampil, `data` untuk angka chart, `notes` untuk catatan
pembicara, `source` untuk teks sumber slide, dan `media_text` untuk teks media
seperti alt atau caption.

`order` sama dengan indeks nol-based slide di `DeckIR.slides`; validator
menolak nilai yang tidak cocok. Mapping `meta`, `source`, dan `fields`
dibungkus read-only saat konstruksi, misalnya dengan `MappingProxyType`.
Contoh ini menunjukkan bentuk kontrak, bukan kode final.

## Invariant

- `DeckIR`, `SlideIR`, `BlockIR`, `KeyBinding`, dan `KeyManifest` immutable.
- Koleksi memakai tuple atau mapping read-only; tidak ada list mutable bersama.
- Tidak ada import dari `autooffice.deck.render`, `autooffice.google`,
  `python-pptx`, atau Word COM di modul model.
- `DeckIR` tidak memuat `LayoutPlan`, path output, ID Google, atau state build.
- Satu `DeckIR` dan satu `KeyManifest` per build deck.
- Satu `KeyBinding` per key; key duplikat ditolak sebelum IR dibuat.
- Semua teks tampil punya binding; teks tanpa key hanya chrome terdaftar.
- `order` sama dengan indeks nol-based slide di `DeckIR.slides`; ID slide
  tetap stabil dan tidak dihitung dari posisi.
- `source` memakai mapping dengan `text` wajib dan `url` opsional; tidak ada
  field `source_text`.
- `rows` hanya berisi block ID yang ada di `blocks`, tanpa duplikat, dan
  menutup seluruh block untuk `layout: custom`; slide preset memakai `rows=()`.
- `fields` hanya berisi field yang lolos `BlockSpec`, tanpa field geometri.
- Mapping `meta`, `source`, dan `fields` read-only setelah konstruksi.
- `plain_text` sudah dinormalisasi sesuai mode teks atau preserve newline.
- `value` menyimpan nilai sumber; `plain_text` menyimpan nilai tampilan.
- Asset path sudah tervalidasi dan relatif terhadap root deck, tanpa file handle.
- Kompilasi deterministik: input sama menghasilkan urutan binding dan field sama.
- Renderer tidak boleh memutasi IR; bila butuh nilai turunan, renderer membuat
  salinan lokal sendiri.

## Acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Aturan | Test kontrak |
| --- | --- |
| Mutasi dataclass IR memunculkan `FrozenInstanceError`. | `tests/contract/test_deck_ir.py` (planned) |
| Import model tidak menarik renderer, Google, pptx, atau COM. | `tests/contract/test_deck_ir.py` (planned) |
| Compile dua kali menghasilkan manifest yang identik. | `tests/contract/test_deck_ir.py` (planned) |
| Rows custom tersimpan eksplisit dan menutup seluruh block. | `tests/deck/model/test_compiler.py`, `tests/contract/test_contract_shapes.py` |
| Setiap teks tampil punya binding dan setiap binding punya key. | `tests/contract/test_deck_ir.py` (planned) |
| Key duplikat ditolak sebelum `DeckIR` dibuat. | `tests/contract/test_deck_ir.py` (planned) |
| IR tidak memuat path output, state Google, atau `LayoutPlan`. | `tests/contract/test_deck_ir.py` (planned) |
| `yaml_path` tersedia untuk apply dan tidak dihitung ulang dari key. | `tests/contract/test_deck_ir.py` (planned) |
| Field block divalidasi terhadap `BlockSpec` sebelum masuk IR. | `tests/contract/test_deck_ir.py` (planned) |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
