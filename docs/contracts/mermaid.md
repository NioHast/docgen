# Kontrak Mermaid Deck

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 4.8, 8.6, dan 18.7.

Kontrak ini membekukan render blok `diagram` menjadi PNG melalui executable
eksternal `mmdc` dan integrasinya ke renderer PPTX. Tidak ada implementasi
Mermaid di Python.

## Daftar Isi

- [API](#api)
- [Aturan sumber dan path](#aturan-sumber-dan-path)
- [Tool dan output](#tool-dan-output)
- [Theme](#theme)
- [Cache](#cache)
- [Integrasi PPTX](#integrasi-pptx)
- [Acceptance](#acceptance)

## API

```python
from pathlib import Path

from autooffice.design.theme import Theme


def render_mermaid(
    source: Path,
    out: Path,
    *,
    theme: Theme,
    cache_dir: Path,
) -> Path:
    ...
```

- `source` adalah satu file `.mmd`.
- `out` wajib berakhiran `.png`; renderer tidak menerima SVG sebagai output.
- `cache_dir` adalah direktori cache; fungsi membuatnya bila belum ada.
- Fungsi mengembalikan path `out` setelah PNG valid ditulis.

Helper `resolve_mermaid_source(deck_root, relative_path)` memvalidasi field
`source` relatif terhadap root deck. Helper ini dipakai renderer sebelum file
diserahkan ke `render_mermaid`.

## Aturan sumber dan path

- Satu block `diagram` merujuk tepat satu file `.mmd`.
- Path wajib relatif, memakai `/`, tanpa segmen kosong, `.`, atau `..`.
- URL remote, UNC path, path absolut, dan backslash ditolak.
- Path hasil resolve wajib tetap berada di bawah root deck.
- File yang tidak ada ditolak sebagai error, bukan dianggap diagram kosong.

## Tool dan output

- Hanya `mmdc` eksternal yang menjalankan Mermaid.
- `mmdc` dicari dari `AUTOOFFICE_MMDC` atau `PATH`; `doctor` melaporkan
  ketersediaan dan versinya.
- Bila `mmdc` tidak ditemukan, error memuat perintah instalasi
  `npm install -g @mermaid-js/mermaid-cli`.
- Output selalu PNG. Render memakai `--scale 2` dan ukuran maksimum 2400 px;
  versi `mmdc` 12 ke atas memakai `--size`, versi lama memakai `--width`.
- Bila `mmdc` gagal, timeout, atau tidak menghasilkan PNG valid, build gagal.
  Tidak ada fallback teks, shape, SVG, atau screenshot.

### Validasi PNG

PNG dianggap valid hanya bila lengkap, bukan sekadar delapan byte signature:

- signature PNG di awal file;
- chunk `IHDR` pertama dengan panjang 13 dan parameter yang masuk akal;
- sedikitnya satu chunk `IDAT`;
- chunk `IEND` terakhir dengan panjang nol, tanpa data setelahnya;
- seluruh CRC chunk cocok, dan tidak ada chunk yang terpotong.

Cache hit memakai validasi yang sama sebelum menyalin. Entri cache yang tidak
lengkap atau rusak dihapus lalu dirender ulang; file rusak tidak pernah
disalin ke output.

### Batas resource dan terminasi proses

| Resource | Batas | Perilaku saat terlampaui |
| --- | --- | --- |
| Ukuran sumber `.mmd` | 1.000.000 byte | `MermaidError` sebelum `mmdc` dipanggil |
| Output setiap stream `mmdc` | 65.536 byte | `MermaidError`; kelebihan dibuang |
| Render | 180 detik | proses dan seluruh keturunannya dihentikan, lalu `MermaidError` |
| Probe versi | 30 detik | proses dan seluruh keturunannya dihentikan, lalu `MermaidError` |

`mmdc` dijalankan dalam process group baru: POSIX memakai
`start_new_session=True` dan `killpg`; Windows memakai
`CREATE_NEW_PROCESS_GROUP` plus Job Object dengan
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Bila Job Object tidak dapat dipakai,
fallback memakai path absolut `%SystemRoot%\System32\taskkill.exe` dengan
`/T`; `taskkill` dari `PATH` tidak pernah dipanggil. Timeout menghentikan
seluruh pohon proses, bukan hanya proses `mmdc` langsung.

### Penulisan file

Penyalinan PNG ke output atau cache memakai `tempfile.mkstemp` di direktori
tujuan, menulis melalui file descriptor, `flush`, `fsync`, lalu `os.replace`.
Tidak ada nama temp yang dapat diprediksi seperti `.<nama>.<pid>.tmp`, sehingga
symlink atau file yang sudah disiapkan penyerang tidak diikuti.

## Theme

Token theme diterjemahkan menjadi `themeVariables` Mermaid dan ditulis ke file
konfigurasi sementara:

```json
{
  "theme": "base",
  "themeVariables": {
    "background": "#FAFAFA",
    "fontFamily": "Plus Jakarta Sans",
    "primaryColor": "#EEF2FF",
    "primaryTextColor": "#0B0B0F",
    "lineColor": "#4338CA"
  }
}
```

`--theme base` dan `--backgroundColor` juga berasal dari token. Theme tidak
pernah dibaca dari file YAML oleh renderer.

## Cache

Cache berada di `cache/mermaid/` di bawah workspace renderer. Nama file:

```text
mermaid-<sha256>.png
```

SHA-256 dihitung dari:

- hash isi file `.mmd`;
- token theme yang disuntikkan;
- versi `mmdc`;
- opsi output: format PNG, theme, background, scale, dan ukuran.

Cache hit menyalin PNG ke `out` tanpa menjalankan render ulang. Perubahan isi
sumber, theme, versi `mmdc`, atau opsi output menghasilkan cache key baru.
File cache yang rusak atau bukan PNG lengkap dihapus dan dirender ulang.

Setiap PNG cache memiliki sidecar `mermaid-<sha256>.json` yang memuat format,
digest, hash sumber, fingerprint theme, versi `mmdc`, dan opsi output. Sidecar
dipakai hanya untuk lookup cache-first: bila `mmdc` tidak tersedia, renderer
mencari sidecar dengan hash sumber dan theme yang cocok, memvalidasi PNG-nya,
lalu menyalin PNG valid tanpa membutuhkan executable. Bila `mmdc` tersedia,
lookup tetap memakai digest lengkap yang memuat versi, sehingga perubahan versi
tetap menghasilkan render baru.

Cache diperiksa sebelum `mmdc` diwajibkan. PNG cache valid harus tetap dapat
dipakai saat `mmdc` hilang dari `PATH` atau `AUTOOFFICE_MMDC`; bila tidak ada
cache yang cocok, error instalasi `mmdc` baru dikembalikan.

## Integrasi PPTX

- Renderer memanggil `mmdc` hanya saat menemukan block `diagram`.
- PNG ditempatkan sebagai picture native pada kotak `PlacedBlock` dengan mode
  contain dan rasio aspek dipertahankan.
- Alt manusia ditulis ke `descr`; namespace block
  `autooffice:diagram:<slide>.<block>` ditulis ke `name` dan `title`.
- Caption dirender sebagai text box berkey `<slide>.<block>.caption`.
- Coverage memeriksa alt manusia dan key caption. Kegagalan render atau
  coverage membatalkan artefak final.
- Diagram di Google Slides dan PDF tetap berupa gambar, bukan node native.

## Acceptance

| Aturan | Test |
| --- | --- |
| Fake `mmdc` menulis PNG dan argumennya benar. | `tests/deck/media/test_mermaid.py` |
| Cache hit tidak menjalankan render ulang. | `tests/deck/media/test_mermaid.py` |
| Cache valid dipakai meski `mmdc` tidak tersedia. | `tests/deck/media/test_mermaid.py` |
| Cache dengan 8 byte signature saja dihapus dan dirender ulang. | `tests/deck/media/test_mermaid.py` |
| PNG valid wajib memiliki `IHDR`/`IDAT`/`IEND` dan CRC benar. | `tests/deck/media/test_mermaid.py` |
| Symlink pada nama temp lama tidak diikuti. | `tests/deck/media/test_mermaid.py` |
| Timeout menghentikan proses anak `mmdc`. | `tests/deck/media/test_mermaid.py` |
| Batas ukuran sumber, output, dan timeout menghasilkan `MermaidError`. | `tests/deck/media/test_mermaid.py` |
| Perubahan sumber, theme, dan versi mengganti cache key. | `tests/deck/media/test_mermaid.py` |
| `mmdc` hilang atau gagal berarti error keras. | `tests/deck/media/test_mermaid.py` |
| Smoke `mmdc` asli tersedia sebagai test integration. | `tests/deck/media/test_mermaid.py` |
| Diagram masuk PPTX sebagai picture dengan alt dan caption. | `tests/deck/render/pptx/test_diagram.py` |
| Tidak ada fallback teks atau shape. | `tests/deck/render/pptx/test_diagram.py` |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
