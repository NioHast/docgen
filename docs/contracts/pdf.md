# Kontrak PDF

Status: F0 contract, version 1
Cakupan implementasi: F2-PDF, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 8.5 dan F2-PDF.
Pemilik kontrak: PDF/COM owner.

## Daftar Isi

- [Tujuan](#tujuan)
- [API](#api)
- [Invarian](#invarian)
- [Error](#error)
- [Contoh](#contoh)
- [Acceptance](#acceptance)

## Tujuan

Kontrak ini membekukan adapter Word COM dan PowerPoint COM di
`autooffice.pdf` untuk finalisasi field DOCX serta ekspor PDF dari DOCX dan
PPTX. Adapter menggantikan `scripts/word.ps1` tanpa PowerShell dan hanya
berjalan di Windows dengan Microsoft Word dan Microsoft PowerPoint desktop.

## API

```python
def export_pdf(
    docx: Path,
    pdf: Path,
    *,
    timeout_s: float = 120.0,
    visible: bool = False,
) -> Path: ...


def update_fields(
    docx: Path,
    *,
    timeout_s: float = 120.0,
    visible: bool = False,
) -> Path: ...


def export_pptx_pdf(
    pptx: Path,
    pdf: Path,
    *,
    timeout_s: float = 120.0,
    visible: bool = False,
) -> Path: ...


def embed_fonts(
    pptx: Path,
    *,
    timeout_s: float = 120.0,
) -> Path: ...
```

- `export_pdf` adalah ekspor DOCX lewat Word. `export_pptx_pdf` adalah ekspor
  PPTX lewat PowerPoint; implementasinya berada di
  `autooffice.pdf.powerpoint.export_pdf` dan diekspor ulang dengan nama
  `export_pptx_pdf` agar tidak bentrok dengan API DOCX.
- `embed_fonts` adalah embedding font TrueType ke PPTX lewat PowerPoint COM.
  Implementasinya berada di `autooffice.pdf.powerpoint.embed_fonts` dan
  diekspor ulang sebagai `embed_pptx_fonts`. Fungsi membuka snapshot, memanggil
  `SaveCopyAs(path, ppSaveAsOpenXMLPresentation=24,
  EmbedTrueTypeFonts=msoTrue)`, memverifikasi hasil, lalu mengganti PPTX sumber
  secara atomik.
- Path hasil dikembalikan dalam bentuk absolut.
- `timeout_s` wajib positif dan terbatas; nilainya membatasi seluruh operasi
  COM lewat watchdog.
- `visible=True` hanya untuk debugging; default Word dan PowerPoint dijalankan
  tersembunyi. PowerPoint tidak menerima `Application.Visible = False`, jadi
  adapter hanya menulis `Visible = True` saat debugging dan mengandalkan
  `WithWindow=False` untuk menyembunyikan presentasi.
- `export_pdf` dan `export_pptx_pdf` menyalin sumber ke snapshot sementara.
  Word/PowerPoint tidak pernah membuka path sumber, sehingga DOCX/PPTX sumber
  tidak berubah setelah ekspor.
- `update_fields` juga memakai snapshot: Word membuka salinan sementara,
  memanggil `Save()` pada salinan itu, lalu adapter memverifikasi DOCX hasil
  dan mengganti DOCX sumber dengan `os.replace`. Bila COM atau verifikasi
  gagal, DOCX sumber tidak berubah.

## Invarian

1. Guard platform dan import pywin32 bersifat lazy. Di non-Windows atau tanpa
   pywin32, API melempar `PdfUnavailableError` dengan tindakan yang jelas.
2. Urutan COM Word: buat Word, atur opsi, buka dokumen, repaginate, update
   seluruh field, update setiap `TableOfContents`, repaginate, lalu simpan atau
   ekspor.
3. Urutan COM PowerPoint: buat PowerPoint, atur opsi, buka snapshot dengan
   `ReadOnly=True`, `Untitled=False`, dan `WithWindow=False`, ekspor dengan
   `SaveAs` format `ppSaveAsPDF = 32`, lalu tutup presentasi tanpa menyimpan.
4. Mode ekspor Word dan PowerPoint memakai snapshot dan menulis PDF ke path
   sementara di direktori tujuan. PDF final dipindahkan dengan `os.replace`
   setelah header `%PDF-` dan ukuran non-zero diverifikasi.
5. Mode `update_fields` membuka snapshot, memanggil `Save()` pada snapshot,
   memverifikasi DOCX hasil ada, berukuran lebih dari nol, dan diawali magic
   ZIP (`PK\x03\x04`), lalu mengganti DOCX sumber dengan `os.replace`.
   Kegagalan COM atau verifikasi tidak mengubah DOCX sumber.
6. Dokumen Word ditutup dengan `wdDoNotSaveChanges`; presentasi PowerPoint
   ditutup dengan `Close()` tanpa `Save`. Word/PowerPoint selalu `Quit` di
   blok `finally`, termasuk saat error atau timeout.
7. Snapshot PID `WINWORD.EXE`/`POWERPNT.EXE` diambil sebelum aplikasi dibuat
   dan wajib berhasil; bila snapshot gagal, operasi dibatalkan sebelum
   `DispatchEx`. PID automation diambil dari `Application.Hwnd` melalui
   `GetWindowThreadProcessId`, bukan dari selisih snapshot. PID itu harus
   bukan PID snapshot awal, terlihat di snapshot baru, image-nya cocok, dan
   creation time-nya terbaca. Sebelum `taskkill`, image dan creation time
   dibaca ulang dan harus sama persis. Proses Office pengguna, termasuk yang
   dibuka setelah snapshot, tidak pernah dibunuh; PID ambigu tidak diklaim
   dan tidak dihentikan.
8. Timeout memakai watchdog wall-clock. Saat timeout, PID automation yang
   sudah terverifikasi dihentikan, lalu worker ditunggu berhenti dalam budget
   cleanup terbatas.
   Bila worker berhenti, `WordTimeoutError` dilempar. Bila worker masih
   hidup, `WordCleanupError` dilempar, snapshot/temp dipertahankan, dan
   pemanggil tidak menghapusnya. Karena cleanup itu, panggilan dapat melewati
   `timeout_s` sebesar budget cleanup terbatas, bukan tanpa batas.
9. Seluruh operasi diserialisasi dengan lock file global
   `%TEMP%/docgen-word.lock` dan `msvcrt.locking`.
10. API tidak memakai PowerShell dan tidak memanggil `scripts/word.ps1`.
    `tasklist` dan `taskkill` hanya dipakai untuk inspeksi dan cleanup PID,
    dan selalu dipanggil lewat path absolut di `%SystemRoot%\System32`
    (`%SystemRoot%\Sysnative` untuk interpreter 32-bit di Windows 64-bit),
    bukan lewat nama yang dapat dibajak `PATH` atau direktori kerja.
11. `autooffice.pdf` hanya boleh mengimpor stdlib, `autooffice.errors`, modul
    `autooffice.pdf` sendiri, dan `python-pptx` untuk verifikasi paket hasil
    embedding. Paket ini tidak mengimpor `deck`, `google`, `cli`, atau
    renderer DOCX/PPTX.
12. Embedding font PowerPoint memakai snapshot. `SaveCopyAs` menulis ke berkas
    sementara di direktori PPTX sumber. PPTX sumber baru diganti dengan
    `os.replace` setelah verifikasi lulus: `p:embeddedFontLst` memuat
    `p:font typeface="Plus Jakarta Sans"`; `p:regular` dan `p:bold` merujuk
    part `ppt/fonts/*.fntdata` yang berbeda, ada, dan tidak kosong; tidak ada
    `p:timing` atau `p:transition`; marker key/alt text sumber masih ada; dan
    paket dapat dibuka python-pptx. Bila COM atau verifikasi gagal, PPTX
    sumber tetap utuh dan berkas sementara dihapus.
13. Embedding font hanya berjalan di Windows dengan Microsoft PowerPoint
    desktop dan font Plus Jakarta Sans terpasang. Target final PPTX/PDF gagal
    bila embedding tidak tersedia; staging Slides tidak memanggil embedding.

## Error

| Error | Arti |
| --- | --- |
| `PdfUnavailableError` | Non-Windows, pywin32 tidak ada, COM tidak dapat diinisialisasi, atau Word/PowerPoint tidak terpasang. |
| `WordComError` | Dokumen read-only, langkah COM Word/PowerPoint gagal, output DOCX/PDF tidak valid, atau hasil embedding font tidak memuat font Plus Jakarta Sans regular/bold, memuat `p:timing`/`p:transition`, atau tidak dapat dibuka python-pptx. |
| `ProcessSnapshotError` | Snapshot PID Office gagal; operasi dibatalkan sebelum aplikasi COM dibuat. Subclass `WordComError`. |
| `WordTimeoutError` | Operasi melewati `timeout_s`; watchdog menghentikan PID automation yang terverifikasi lalu menunggu worker berhenti. |
| `WordCleanupError` | Worker COM masih hidup setelah budget cleanup. Cleanup ambigu: snapshot/temp dipertahankan dan proses Office harus diperiksa manual. Subclass `WordTimeoutError`. |
| `WordBusyError` | Lock COM tidak diperoleh sebelum sisa `timeout_s` habis; default 30 detik bila `com_lock` dipanggil langsung. |
| `FileNotFoundError` | DOCX/PPTX input tidak ditemukan. |
| `ValueError` | Suffix path salah atau `timeout_s` tidak valid. |

## Contoh

```python
from pathlib import Path

from autooffice.pdf import embed_pptx_fonts, export_pdf, export_pptx_pdf, update_fields

docx = Path("out/Laporan.docx")
update_fields(docx, timeout_s=300)
pdf = export_pdf(docx, Path("out/Laporan.pdf"), timeout_s=300)
deck = embed_pptx_fonts(Path("out/Deck.pptx"), timeout_s=300)
deck_pdf = export_pptx_pdf(deck, Path("out/Deck.pdf"), timeout_s=300)
print(pdf, deck_pdf)
```

## Acceptance

| Perilaku | Bukti |
| --- | --- |
| Urutan COM dan opsi Word | `tests/pdf/test_word.py` dengan fake COM. |
| Urutan COM dan opsi PowerPoint | `tests/pdf/test_powerpoint.py` dengan fake COM. |
| DOCX/PPTX sumber tidak berubah saat ekspor | Snapshot palsu dimutasi; byte sumber tetap sama. |
| `update_fields` memakai snapshot dan replace atomik | Fake membuka snapshot, bukan path sumber; replace hanya terjadi setelah verifikasi snapshot dan temp; sumber tetap utuh saat COM gagal. |
| PDF PowerPoint ditutup tanpa menyimpan | Fake mencatat `SaveAs(32)` dan `Close()`, tanpa `Save`. |
| Embedding font PowerPoint | Fake mencatat `SaveCopyAs(24, -1)` dan `Open(ReadOnly=False)`; verifikasi menuntut Plus Jakarta Sans regular/bold, tanpa timing/transition; sumber utuh saat gagal. |
| CLI menanam font untuk PPTX/PDF, bukan Slides | `tests/cli/test_deck_build.py`; `tests/cli/test_deck_slides.py`. |
| Timeout dan cleanup PID | Fake COM memblokir; watchdog memanggil terminate PID tercatat lalu menunggu worker berhenti. |
| Cleanup ambigu | `tests/pdf/test_com.py` memeriksa `WordCleanupError`; worker masih dapat menulis setelah error. |
| Non-Windows dan pywin32 hilang | `tests/pdf/test_com.py`; pesan menyebut tindakan. |
| Process cleanup tidak menyentuh instance pengguna | PID `Hwnd` yang ambigu tidak diklaim; PID reuse (image/creation time berubah) tidak dihentikan; instance pengguna tidak dibunuh. |
| Path absolut `tasklist`/`taskkill` | `tests/pdf/test_com.py` memeriksa `System32`/`Sysnative` dan menolak `SystemRoot` hilang. |
| Serialisasi | `tests/pdf/test_com.py` menguji lock file Windows. |
| Batas import | `uv run lint-imports`. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
