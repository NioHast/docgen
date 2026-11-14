# Script runtime (`scripts`)

## Tujuan

Folder ini menyimpan resource runtime untuk perkakas eksternal, bukan alat
pengembang Python. Satu-satunya skrip yang tersisa adalah `word.ps1`, adapter
Microsoft Word legacy untuk package `docgen`. Skrip ini hanya dipanggil oleh
`docgen.stages.office` dan hanya berlaku di Windows dengan Microsoft Word
desktop.

AutoOffice tidak memakai `word.ps1` dan tidak memakai PowerShell. Pipeline
AutoOffice memanggil adapter Word COM Python di
`src/autooffice/pdf/word.py` melalui stage
`autooffice.docx.stages.office`.

## Status migrasi

- `scripts/check.ps1` sudah dihapus. Gate lokal kini dijalankan dengan
  `uv run python tools/quality/gate.py`.
- `scripts/word.ps1` sekarang **legacy `docgen` saja**. Jalur PDF `docgen`
  masih memakainya sampai F3.
- AutoOffice DOCX dan PDF memakai `autooffice.pdf.word`; tidak ada subprocess
  PowerShell di AutoOffice.
- `scripts/word.ps1` akan dihapus pada F3 bersama package `docgen`.

## Ownership

- [PDF dan Word](../docs/dev/pdf.md) adalah sumber kebenaran alur PDF,
  batasan platform, variabel lingkungan Word, dan pemisahan jalur AutoOffice
  versus legacy.
- [COM Word](../docs/dev/com.md) menjelaskan adapter AutoOffice di
  `src/autooffice/pdf/word.py`.
- `scripts/word.ps1` hanya milik jalur legacy `docgen`. Perubahan parameter
  atau perilakunya harus disertai pembaruan `src/docgen/stages/office.py` dan
  tes legacy.
- `src/docgen/stages/office.py` adalah satu-satunya pemanggil Python untuk
  `word.ps1`; jangan memanggilnya dari stage AutoOffice atau modul lain.
- Jangan menambah adapter Word kedua di folder ini. AutoOffice memakai
  `autooffice.pdf.word`.

## Entry point legacy (`word.ps1`)

`word.ps1` menerima:

- `-DocxPath` (wajib): DOCX yang akan diproses.
- `-PdfPath` (opsional): bila diisi, skrip mengekspor PDF dari snapshot DOCX.
- `-Visible`: menampilkan jendela Word untuk debugging.

Tanpa `-PdfPath`, skrip membuka DOCX, memperbarui field dan repaginasi, lalu
menyimpan DOCX di tempat. Dengan `-PdfPath`, DOCX sumber tidak diubah; skrip
membuat snapshot sementara, memperbarui field, mengekspor PDF, lalu menutup
snapshot tanpa menyimpan DOCX.

Entry point AutoOffice setara ada di `autooffice.pdf.word.update_fields` dan
`autooffice.pdf.word.export_pdf`, dengan semantik snapshot yang sama.

## Alat dev vs resource runtime

- `tools/` berisi alat pengembang Python: dijalankan manual atau di CI, tidak
  dipaketkan, dan tidak dipanggil pipeline.
- `scripts/` berisi resource runtime legacy: `word.ps1` dipanggil
  `src/docgen/stages/office.py` saat build legacy membutuhkan Word.
- AutoOffice memakai adapter Python di `src/autooffice/pdf/`, bukan resource
  di folder ini.
- Tidak ada mesin PDF kedua. Ekspor PDF hanya lewat Word dan adapter yang
  sesuai jalur.

## Larangan

- Jangan memakai LibreOffice atau mesin konversi lain sebagai pengganti Word.
- Jangan mengubah DOCX sumber saat mode ekspor PDF; gunakan snapshot.
- Jangan menulis output ke folder sumber; hormati path yang diberikan
  pemanggil, termasuk direktori `out/` yang di-ignore.
- Jangan mengandalkan Word Online; COM hanya tersedia di Word desktop Windows.
- Jangan menambah pemanggil baru ke `word.ps1`; semua kode baru AutoOffice
  harus memakai `autooffice.pdf.word`.
- Jangan menaruh skrip pengembangan umum di folder ini.

## Tautan

- [PDF dan Word](../docs/dev/pdf.md)
- [COM Word](../docs/dev/com.md)
- [Kontrak stage](../docs/dev/contracts/stage-api.md)
- [Rencana refactor](../docs/dev/archive/refactor-plan.md)
- [Pemanggil Python legacy](../src/docgen/stages/office.py)
- [Adapter Word legacy](word.ps1)
