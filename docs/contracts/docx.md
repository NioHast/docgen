# Kontrak DOCX

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 8.2, 16.1, 18.2, dan F1-DOCX.
Pemilik kontrak: DOCX owner; pembekuan F0 oleh integration owner.

## Tujuan

Kontrak ini membekukan migrasi pipeline DOCX docgen ke `autooffice.docx`
tanpa perubahan perilaku dokumen. Yang berubah hanya namespace, entry point,
nama satu flag, lokasi kode, dan dokumentasi.

## Invarian parity docgen

1. Satu `document.md` tetap menjadi satu-satunya sumber dokumen.
2. Front matter, format `format.yml`, dan struktur `structure.yml`
   dipertahankan tanpa perubahan arti.
3. Pandoc dan `--citeproc` tetap dipakai. Urutan stage tidak berubah.
4. Hanya ada satu `DocumentPackage.load()` dan satu `DocumentPackage.save()`
   untuk dokumen target. Part non-target harus byte-identik setelah
   normalisasi timestamp dan metadata.
5. Stage finalisasi Word tetap menghasilkan TOC, daftar, caption, tabel,
   code, equation, numbering, dan page number seperti docgen.
6. Manifest Adeu tetap deterministik di `.laporan/manifest.json` dan bookmark
   tetap `pNNNN`.
7. `report_name` wajib dan aman sebagai nama berkas. Output default:
   `<report_name>.docx` dan `<report_name>.pdf`; contoh di
   `examples/<name>/document.md` memakai `examples/<name>/out/`.
8. `--terms` menjalankan check, apply, verify, dan gate istilah seperti
   docgen. Output istilah baru berada di `.laporan/istilah-baru.txt`.
   `--terms` hanya berlaku untuk `.md`, bukan `.yaml`.
9. DOCX tidak memakai design system deck, tidak memakai Plus Jakarta Sans,
   dan tidak menjalankan copy checker atau humanizer.
10. Flag lama DOCX tidak dipertahankan. Opsi workspace lama diganti
    `--keep-intermediate`; tidak ada alias untuk flag lama.
11. PDF DOCX memakai Word COM di Windows. File input tidak boleh diubah dan
    Word harus menutup dokumen serta prosesnya.

## API `build_docx`

API publik berada di `autooffice.docx.command` dan memiliki urutan argumen
yang stabil:

```python
def build_docx(
    input: Path,
    out: Path | None,
    terms: bool,
    keep_intermediate: bool,
) -> DocxResult: ...
```

- `input`: path `document.md`.
- `out`: direktori output final; `None` memakai aturan output docgen.
- `terms`: mengaktifkan gate istilah dan output istilah baru.
- `keep_intermediate`: mempertahankan `.laporan-build/` dan intermediate DOCX.
- Return `DocxResult` memuat path DOCX, manifest, istilah, warnings, dan
  workspace yang dipertahankan; field final dibekukan di F1-DOCX.

Output yang berada di dalam `.laporan-build/` hanya diizinkan bila
`keep_intermediate=True`. Tanpa keep, pipeline menolak dengan
`OutputError("OUTPUT-WORKSPACE")` karena workspace dibersihkan di blok
`finally`. Jalur CLI `--target pdf` tanpa `docx` memakai intermediate DOCX di
dalam `.laporan-build/`, mengonversinya ke PDF, lalu membersihkan workspace
setelah konversi selesai; `--keep-intermediate` menahan pembersihan tersebut.
DOCX final yang sudah ada di direktori output tidak ditimpa oleh jalur
PDF-only ini.

Pemanggil CLI tidak boleh mengimpor modul internal DOCX. `cli` boleh
memanggil `build_docx`; `docx` tidak boleh mengimpor `deck`, `google`, atau
`cli`. Import-linter menegakkan aturan ini.

## Batas import

| Modul | Boleh mengimpor | Tidak boleh mengimpor |
| --- | --- | --- |
| `autooffice.docx.**` | `common`, `errors`, library DOCX | `deck`, `google`, `cli` |
| `autooffice.docx.command` | pipeline DOCX, `errors` | `deck`, `google` |
| `autooffice.cli` | semua modul publik, termasuk `build_docx` | tidak ada modul domain yang mengimpor `cli` |

## Contoh

```python
from pathlib import Path

from autooffice.docx.command import build_docx

result = build_docx(
    input=Path("examples/thesis-single/document.md"),
    out=None,
    terms=True,
    keep_intermediate=False,
)
print(result.docx)
print(result.manifest)
```

Hasil yang diharapkan setara dengan perilaku pipeline DOCX lama dengan
`--terms` sebelum penghapusan: DOCX, manifest, dan istilah berada di lokasi
yang sama dengan perilaku lama.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Parity visual dan part | Golden DOCX dari baseline docgen; `tests/docx/test_golden.py` (planned); bagian 18.2. |
| Urutan stage dan satu save | Contract test pipeline; `tests/docx/test_pipeline.py` (planned). |
| Manifest dan bookmark | Golden manifest; `tests/docx/test_adeu.py` (planned). |
| `--terms` | `tests/docx/test_terms.py` (planned); output `istilah-baru.txt`. |
| Batas import | `lint-imports`; kontrak import bagian 12.5. |
| API `build_docx` | `tests/contract/test_docx_api.py` (planned); F1-DOCX acceptance. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
