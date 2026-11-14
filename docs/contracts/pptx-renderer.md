# Kontrak Renderer PPTX

Kontrak ini membekukan input, output, dan larangan renderer PPTX. Renderer
menggambar `DeckIR` dan `LayoutPlan` menjadi presentasi native dengan
`python-pptx`; ia tidak membaca YAML, tidak membaca file token, dan tidak
menciptakan teks. PDF dari PPTX dan staging Google Slides memakai renderer yang
sama.

Status: F0 contract, version 1
Sumber: AUTO_OFFICE_PLAN.md bagian 8.1 dan 8.3.

## Daftar Isi

- [Input dan output](#input-dan-output)
- [Aturan presentasi](#aturan-presentasi)
- [Teks, tabel, chart, dan gambar](#teks-tabel-chart-dan-gambar)
- [Alt text dan key](#alt-text-dan-key)
- [Font embedding](#font-embedding)
- [Staging Slides](#staging-slides)
- [Invariant](#invariant)
- [Acceptance](#acceptance)

## Input dan output

```python
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class OutputTarget(StrEnum):
    PPTX = "pptx"
    PDF = "pdf"
    SLIDES = "slides"


@dataclass(frozen=True, slots=True)
class CoverageReport:
    missing_keys: tuple[str, ...]
    duplicate_keys: tuple[str, ...]
    unkeyed_visible: tuple[str, ...]
    missing_alt: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (
            self.missing_keys
            or self.duplicate_keys
            or self.unkeyed_visible
            or self.missing_alt
        )


@dataclass(frozen=True, slots=True)
class RenderRequest:
    deck: DeckIR
    layout: LayoutPlan
    theme: Theme
    target: OutputTarget
    workspace: Path


@dataclass(frozen=True, slots=True)
class RenderResult:
    artifact_path: Path
    coverage: CoverageReport
    warnings: tuple[str, ...]
    content_hash: str
    target_metadata: Mapping[str, str]


class DeckRenderer(Protocol):
    def render(self, request: RenderRequest) -> RenderResult:
        ...
```

- Input: `DeckIR`, `LayoutPlan`, `Theme`, `OutputTarget`, dan `workspace`.
- Output: artefak, `CoverageReport`, warning, hash konten, dan metadata target.
- `CoverageReport.ok` hanya `True` bila keempat daftar temuan kosong.
- `target_metadata` read-only; renderer tidak menerima path YAML.

## Aturan presentasi

- Ukuran 16:9, 13.333 x 7.5 inci.
- Dibangun dengan `python-pptx`; master, theme color/font, dan layout visual
  dihasilkan dari token.
- Tidak ada base `.pptx` di repo atau dari user; presentasi kosong library
  hanya container teknis.
- Slide background dari token; semua shape, table, chart, image, notes, dan
  alt text dibuat native.
- Tidak ada animasi, transisi, SmartArt, video, atau audio; tidak ada node
  timing atau transition di OOXML.
- Tidak ada placeholder layout yang tidak dipakai.

## Teks, tabel, chart, dan gambar

- Word wrap aktif; auto-size dimatikan; tidak ada shrink.
- Spasi paragraf dan line-height dari token; minimum 10 pt.
- Teks yang overflow gagal sebelum render atau saat verifikasi layout.
- Table memakai `shapes.add_table`, header baris pertama, tanpa merged cell;
  border dan fill dari token, angka rata kanan, teks rata kiri.
- Chart `bar`, `line`, dan `donut` native; data native, bukan shape; title,
  legend, gridline, axis, dan font dari token.
- Image crop native dan proporsional; WebP dinormalisasi ke PNG sebelum embed.
- Notes native hanya untuk slide yang punya `notes`; key `sNN.notes`.
- Table dan chart tidak boleh diubah menjadi gambar untuk PDF.

## Alt text dan key

- Shape teks berkey memiliki `name` yang memuat key dan `title` berisi key
  yang sama; `description` berisi teks manusia atau deskripsi aksesibilitas.
- Image dan diagram memiliki `descr` alt manusia; chart memiliki alt manusia
  di `descr` dan key chart di metadata.
- Chrome memakai nama `chrome:*` dan bukan key.
- Coverage memeriksa key shape, key table cell, chart, notes, dan alt.
- Key table cell dibaca dari XML table native, bukan dari shape terpisah.

## Font embedding

- TTF Plus Jakarta Sans disertakan di package; renderer menambah font parts ke
  OOXML setelah `python-pptx` menyimpan.
- Font yang ditanam: Regular, SemiBold, Bold, ExtraBold.
- Family harus `Plus Jakarta Sans`, sama dengan Google Fonts.
- Bila embedding gagal atau PPTX tidak valid, build wajib gagal.
- PPTX harus bisa dibuka PowerPoint tanpa prompt repair.
- Test memeriksa content type, relationship, dan `embeddedFontLst`.

## Staging Slides

- `--target slides` membuat staging PPTX internal dengan layout dan teks yang
  sama.
- Chart diganti placeholder shape, bukan native chart.
- Placeholder bernama dan beralt `autooffice:chart:<chart_id>`.
- Staging bukan deliverable kecuali `--keep-intermediate`.
- Deliverable `pptx` tetap memakai chart native.

## Invariant

- Satu renderer PPTX untuk PPTX, PDF dari PPTX, dan staging Slides.
- Protokol `DeckRenderer` hanya punya
  `render(request: RenderRequest) -> RenderResult`; target dibaca dari
  `request.target`.
- Renderer tidak membaca YAML dan tidak membaca file token dari disk.
- Renderer tidak menciptakan teks; semua teks berasal dari IR atau chrome terdaftar.
- Renderer tidak menulis output final sebelum coverage lulus.
- Renderer tidak menelan error, tidak memakai template eksternal, dan tidak
  melakukan fallback ke HTML, LibreOffice, atau screenshot.
- Output deterministik untuk input yang sama, kecuali timestamp yang dinormalisasi.
- Semua output ditulis atomik; file sementara bukan output final.
- Error menyebut input, slide ID, block ID, key, dan target bila relevan.
- Tidak ada shrink, animasi, transisi, SmartArt, video, atau audio.
- Font embedding gagal berarti build gagal, bukan warning.

## Acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Aturan | Test kontrak |
| --- | --- |
| Tidak ada `<p:timing>` dan `<p:transition>` di PPTX. | `tests/contract/test_pptx_renderer.py` (planned) |
| Font parts, content type, relationship, dan `embeddedFontLst` valid. | `tests/contract/test_pptx_renderer.py` (planned) |
| Table terdeteksi native, bukan gambar atau shape group. | `tests/contract/test_pptx_renderer.py` (planned) |
| Chart terdeteksi native dan data sama dengan IR. | `tests/contract/test_pptx_renderer.py` (planned) |
| Shape teks berkey punya `name` dan `title` yang cocok. | `tests/contract/test_pptx_renderer.py` (planned) |
| Image dan diagram punya alt manusia di `descr`. | `tests/contract/test_pptx_renderer.py` (planned) |
| Notes hanya dibuat untuk slide yang punya `notes`. | `tests/contract/test_pptx_renderer.py` (planned) |
| Coverage gagal berarti tidak ada output final. | `tests/contract/test_pptx_renderer.py` (planned) |
| PPTX terbuka di PowerPoint tanpa repair. | `tests/visual/test_pptx_open.py` (planned) |
| Golden PPTX memeriksa struktur dan posisi slot. | `tests/golden/test_pptx_*.py` (planned) |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
