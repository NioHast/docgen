# PDF, Word, dan PowerPoint

AutoOffice mengekspor PDF lewat COM Office di Windows: Word untuk DOCX dan
PowerPoint untuk PPTX. Tidak ada LibreOffice, mesin konversi lain, atau jalur
PowerShell. Semua jalur COM membutuhkan `pywin32` dari extra `windows`.

## Alur PDF DOCX

```text
document.md
  -> Pandoc
  -> stage DOCX
  -> save DOCX
  -> office: autooffice.pdf.word.update_fields
  -> pdf: autooffice.pdf.word.export_pdf
```

`office` memperbarui seluruh field, termasuk TOC dan `PAGEREF`, pada snapshot
sementara, memanggil `Save()` di snapshot, memverifikasi DOCX hasil, lalu
mengganti DOCX sumber dengan `os.replace`. Kegagalan COM atau verifikasi tidak
mengubah DOCX sumber. `pdf` menyalin DOCX ke snapshot, mengekspor snapshot
lewat Word, dan tidak membuka path sumber. Pipeline memeriksa bahwa PDF ada dan
memiliki header `%PDF-`.

Target `docx` tetap menghasilkan DOCX di Windows tanpa Word dengan peringatan;
field dan TOC belum difinalkan. Target `pdf` atau `all` untuk `.md` selalu
membutuhkan Word. Di Linux atau Windows tanpa Word, gunakan `--target docx`.

## Alur PDF dan font PPTX

```text
deck.yaml
  -> renderer PPTX
  -> embed font Plus Jakarta Sans lewat PowerPoint COM
  -> pdf: autooffice.pdf.powerpoint.export_pdf
```

Renderer menulis PPTX, lalu CLI menanam font Plus Jakarta Sans lewat
`autooffice.pdf.powerpoint.embed_fonts` sebelum mempublikasikan artefak final.
Embedding memakai `SaveCopyAs(ppSaveAsOpenXMLPresentation=24,
EmbedTrueTypeFonts=msoTrue)`, lalu memverifikasi paket hasil: font Plus Jakarta
Sans ada pada `p:embeddedFontLst` dengan `p:regular` dan `p:bold` merujuk part
`ppt/fonts/*.fntdata` yang berbeda dan tidak kosong, tidak ada `p:timing` atau
`p:transition`, marker/alt text sumber masih ada, dan paket dapat dibuka
python-pptx. PPTX sumber baru diganti secara atomik setelah verifikasi lulus;
bila COM atau verifikasi gagal, PPTX sumber tidak berubah.

Target `pptx` dan `pdf` untuk `.yaml` memerlukan Windows dengan PowerPoint
desktop dan font Plus Jakarta Sans terpasang. Staging untuk target `slides`
tidak menanam font karena Google Slides memakai Google Fonts.

## Target

| Input | Target | Windows + Office desktop | Linux/macOS |
| --- | --- | --- | --- |
| `.md` | `docx` | DOCX, field difinalkan Word | DOCX best-effort, field belum final |
| `.md` | `pdf` | PDF lewat Word | error |
| `.md` | `all` | DOCX dan PDF lewat Word | DOCX dapat tertulis, lalu error karena PDF tidak tersedia |
| `.yaml` | `pptx` | PPTX dengan font tertanam | error saat embedding font |
| `.yaml` | `pdf` | PDF lewat PowerPoint | error |
| `.yaml` | `pptx,pdf` | PPTX dan PDF | error |
| `.yaml` | `slides` | Google Slides, tanpa Office COM | Google Slides, tanpa Office COM |
| `.yaml` | `all` | PPTX, PDF, dan Slides | error untuk PPTX/PDF |

`all` tidak boleh digabung dengan target lain. Untuk `.md`, `all` sama dengan
`docx,pdf`. Untuk `.yaml`, `all` sama dengan `pptx,pdf,slides` dan memerlukan
kredensial Google.

DOCX intermediate untuk target `pdf` tanpa DOCX final ditulis di
`.laporan-build/` dan dihapus setelah PDF selesai, kecuali
`--keep-intermediate`. PPTX intermediate untuk target `pdf` tanpa PPTX final
ditulis di `.autooffice-build/<stem>/` dan mengikuti aturan yang sama.

## Debian dan Linux

Pipeline DOCX dapat berjalan selama Python dan Pandoc tersedia. Namun:

- `office` tidak berjalan tanpa Word, sehingga TOC dan nomor halaman dapat
  tetap kosong sampai DOCX dibuka di Word;
- target `pdf` dan `all` untuk `.md` gagal karena Word tidak tersedia;
- target `pptx` dan `pdf` untuk `.yaml` gagal saat embedding font atau ekspor;
- target `slides` dapat berjalan dengan extra `google` dan kredensial OAuth.

Jalur PDF resmi tetap Windows. Jangan mengklaim paritas PDF di Linux.

## Variabel lingkungan

| Variabel | Fungsi |
| --- | --- |
| `DOCGEN_WINWORD` | Override path `WINWORD.EXE`; dibaca `find_word_executable`. |
| `DOCGEN_PANDOC` | Override path Pandoc. |
| `PANDOC` | Alternatif path Pandoc. |

Nama environment DOCX masih memakai prefix historis sampai F3. Deteksi default
mencari Word di registry, `PATH`, dan folder instalasi Microsoft Office.

## Batasan

- Word Online dan PowerPoint Online tidak menyediakan COM.
- PDF dapat berbeda sedikit dari DOCX/PPTX karena font pengganti atau
  pemenggalan baris.
- DOCX tanpa Word tidak memfinalkan field. TOC dapat menampilkan `0` sampai
  dokumen dibuka dan field diperbarui.
- PDF tidak dijamin byte-identik antar build.
- Word dan PowerPoint dapat menulis ulang package saat menyimpan. Perubahan
  XML yang tidak disengaja mungkin muncul, tetapi tampilan tidak diubah secara
  sengaja.
- Tutup DOCX, PPTX, atau PDF tujuan sebelum build. Berkas yang terkunci
  membuat penulisan gagal.

## Pemeriksaan

`autooffice doctor` memeriksa Python, Pandoc, `mmdc`, registrasi COM Word dan
PowerPoint, `pywin32`, aset font, status font terpasang, extra Google,
kredensial OAuth lokal, dan izin tulis workspace tanpa jaringan.

```bash
uv run --project <repo> autooffice doctor
uv run --project <repo> autooffice doctor --target docx,pdf
uv run --project <repo> autooffice doctor --json
```

## COM, watchdog, dan cleanup

- PID automation diambil dari `Application.Hwnd` lewat
  `GetWindowThreadProcessId`, bukan dari selisih snapshot. PID yang diklaim
  harus lolos pemeriksaan image dan creation time; sebelum `taskkill` keduanya
  dibaca ulang. Proses Office pengguna atau PID ambigu tidak pernah dihentikan.
- Snapshot PID diambil sebelum aplikasi COM dibuat. Bila snapshot gagal,
  operasi dibatalkan sebelum `DispatchEx`.
- `tasklist` dan `taskkill` dipanggil lewat path absolut di
  `%SystemRoot%\System32` (`Sysnative` untuk Python 32-bit di Windows 64-bit).
- Watchdog menunggu worker berhenti setelah timeout. Cleanup ambigu
  (`WordCleanupError`) mempertahankan snapshot/temp dan dapat melewati
  `timeout_s` sebesar budget cleanup terbatas.

Detail lifecycle COM, lock, dan verifikasi output ada di [COM Office](com.md).
Kontrak perilaku ada di [Kontrak PDF](../contracts/pdf.md).
