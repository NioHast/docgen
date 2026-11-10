# Script runtime (`scripts`)

## Tujuan

Folder ini menyimpan resource runtime untuk perkakas eksternal, bukan alat
pengembang Python. Saat ini satu-satunya skrip runtime adalah `word.ps1`,
adapter Microsoft Word yang memperbarui field DOCX dan mengekspor PDF. Skrip
ini dipanggil oleh pipeline melalui `docgen.stages.office` dan hanya berlaku di
Windows dengan Microsoft Word desktop.

## Ownership

- [PDF dan Word](../docs/dev/pdf.md) adalah sumber kebenaran alur PDF,
  batasan platform, dan variabel lingkungan Word.
- `scripts/word.ps1` adalah adapter Word tunggal. Perubahan parameter atau
  perilakunya harus disertai pembaruan `stages/office.py`, tes Word, dan
  dokumen PDF.
- Pemilik adapter Word mengelola folder ini. Jangan menambah adapter kedua
  atau memanggil Word dari modul Python lain.
- `stages/office.py` adalah satu-satunya pemanggil Python untuk skrip ini;
  jangan memanggilnya langsung dari stage lain.

## Entry point

`word.ps1` menerima:

- `-DocxPath` (wajib): DOCX yang akan diproses.
- `-PdfPath` (opsional): bila diisi, skrip mengekspor PDF dari snapshot DOCX.
- `-Visible`: menampilkan jendela Word untuk debugging.

Tanpa `-PdfPath`, skrip membuka DOCX, memperbarui field dan repaginasi, lalu
menyimpan DOCX di tempat. Dengan `-PdfPath`, DOCX sumber tidak diubah; skrip
membuat snapshot sementara, memperbarui field, mengekspor PDF, lalu menutup
snapshot tanpa menyimpan DOCX.

## Alat dev vs resource runtime

- `tools/` berisi alat pengembang Python: dijalankan manual atau di CI, tidak
  dipaketkan, dan tidak dipanggil pipeline.
- `scripts/` berisi resource runtime: `word.ps1` dipanggil `stages/office.py`
  saat build membutuhkan Word. Jangan memindahkan alat dev ke sini.
- Tidak ada mesin PDF kedua. Ekspor PDF hanya lewat Word dan adapter ini.

## Larangan

- Jangan menambahkan Python COM, `pywin32`, atau adapter Word kedua.
- Jangan memakai LibreOffice atau mesin konversi lain sebagai pengganti Word.
- Jangan mengubah DOCX sumber saat mode ekspor PDF; gunakan snapshot.
- Jangan menulis output ke folder sumber; hormati path yang diberikan
  pemanggil, termasuk direktori `out/` yang di-ignore.
- Jangan mengandalkan Word Online; COM hanya tersedia di Word desktop Windows.
- Jangan menaruh skrip pengembangan umum di folder ini.

## Tautan

- [PDF dan Word](../docs/dev/pdf.md)
- [Kontrak stage](../docs/dev/contracts/stage-api.md)
- [Rencana refactor](../docs/dev/archive/refactor-plan.md)
- [Pemanggil Python](../src/docgen/stages/office.py)
- [Adapter Word](word.ps1)
