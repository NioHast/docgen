# COM Word dan PowerPoint

Halaman ini menjelaskan lapisan COM Office di `src/autooffice/pdf/com.py` dan
pemakaiannya oleh adapter `src/autooffice/pdf/word.py` serta
`src/autooffice/pdf/powerpoint.py`. Kontrak perilaku ada di
[Kontrak PDF](../contracts/pdf.md).

## Daftar Isi

- [Alur](#alur)
- [Alur Word](#alur-word)
- [Alur PowerPoint](#alur-powerpoint)
- [Embedding font PPTX](#embedding-font-pptx)
- [Guard lazy](#guard-lazy)
- [COM apartment dan thread](#com-apartment-dan-thread)
- [Watchdog](#watchdog)
- [PID dan cleanup](#pid-dan-cleanup)
- [Lock](#lock)
- [Verifikasi output](#verifikasi-output)
- [Test](#test)

## Alur

```text
API publik
  -> deadline timeout_s
  -> com_lock dengan sisa deadline
  -> snapshot PID WINWORD/POWERPNT (wajib berhasil)
  -> thread worker + COM apartment
  -> DispatchEx("Word.Application") atau DispatchEx("PowerPoint.Application")
  -> PID automation dari Application.Hwnd + GetWindowThreadProcessId
  -> opsi aplikasi, buka snapshot
  -> Word: repaginate, update field, update TOC, repaginate
     PowerPoint: SaveAs(ppSaveAsPDF=32) atau
                 SaveCopyAs(ppSaveAsOpenXMLPresentation=24, msoTrue)
  -> Save (update_fields), ekspor PDF, atau embedding font
  -> Close, Quit
  -> verifikasi output, lalu os.replace atomik
  -> cleanup PID automation yang terverifikasi
```

Word dan PowerPoint tidak pernah dijalankan lewat PowerShell atau proses shell.
`subprocess` hanya dipakai untuk `tasklist` dan `taskkill` saat membaca atau
membersihkan PID. Keduanya dipanggil lewat path absolut di
`%SystemRoot%\System32` (atau `%SystemRoot%\Sysnative` bila interpreter
32-bit berjalan di Windows 64-bit), bukan lewat nama yang bisa dibajak
executable di direktori kerja atau `PATH`.

## Alur Word

`autooffice.pdf.word.export_pdf` menyalin DOCX ke snapshot, membuka snapshot,
memperbarui seluruh field dan `TableOfContents`, lalu memanggil
`ExportAsFixedFormat(path, wdExportFormatPDF=17)`. Mode `update_fields` juga
membuka snapshot, memanggil `Save()` pada snapshot, memverifikasi hasil, lalu
mengganti DOCX sumber dengan `os.replace`. Jalur sumber tidak pernah dibuka
Word; kegagalan COM tidak mengubah DOCX sumber.

## Alur PowerPoint

`autooffice.pdf.powerpoint.export_pdf` menyalin PPTX ke snapshot, membuka
snapshot dengan `Presentations.Open(path, ReadOnly=True, Untitled=False,
WithWindow=False)`, lalu memanggil `SaveAs(path, ppSaveAsPDF=32)`. Presentasi
ditutup dengan `Close()` tanpa `Save`, sehingga snapshot dan PPTX sumber tidak
berubah. Adapter tidak memakai `ExportAsFixedFormat` agar format PDF yang
diminta eksplisit sama dengan konstanta `ppSaveAsPDF`.

PowerPoint menolak `Application.Visible = False` dengan error "Hiding the
application window is not allowed". Karena itu adapter hanya menulis
`Visible = True` saat `visible=True`; default tetap tanpa jendela presentasi
lewat `WithWindow=False`. `DisplayAlerts = ppAlertsNone (1)` dipasang agar
dialog modal tidak muncul saat ekspor.

## Embedding font PPTX

`autooffice.pdf.powerpoint.embed_fonts` bersifat Windows-only dan membutuhkan
Microsoft PowerPoint desktop. CLI memanggilnya untuk target final `pptx` dan
`pdf` setelah renderer menulis PPTX; staging `slides` tidak memanggilnya karena
Google Slides memakai Google Fonts.

Alurnya:

1. Salin PPTX sumber ke snapshot sementara. PPTX sumber tidak pernah dibuka
   langsung oleh PowerPoint.
2. Buka snapshot dengan `ReadOnly=False`, `Untitled=False`,
   `WithWindow=False`.
3. Panggil `SaveCopyAs(path, ppSaveAsOpenXMLPresentation=24,
   EmbedTrueTypeFonts=msoTrue)`. Format 24 adalah Open XML Presentation;
   `msoTrue` dikirim sebagai `-1`.
4. Verifikasi hasil sebelum menyentuh sumber:
   - ada `p:font typeface="Plus Jakarta Sans"` pada `p:embeddedFontLst`;
   - `p:regular` dan `p:bold` menunjuk relasi ke part
     `ppt/fonts/*.fntdata` yang berbeda, ada, dan tidak kosong;
   - tidak ada `p:timing` atau `p:transition` pada slide;
   - marker key `autooffice:*` dan alt text `descr` dari sumber masih ada;
   - paket dapat dibuka `python-pptx`.
5. Ganti PPTX sumber dengan `os.replace` hanya setelah seluruh verifikasi
   lulus. Selama proses, PPTX sumber tidak pernah dibuka PowerPoint; bila COM,
   penulisan, atau verifikasi gagal, sumber tidak berubah.

Font yang ditanam harus terpasang di Windows karena PowerPoint hanya dapat
menanam font yang dikenal sistem. Empat TTF Plus Jakarta Sans dibundel package
untuk build dan test, tetapi mesin build tetap perlu memasang font tersebut.
Embedding mengubah byte PPTX setelah renderer menghitung `content_hash`; hash
artefak final harus dihitung ulang bila diperlukan.

## Guard lazy

`autooffice.pdf` dapat diimpor di Linux dan pada mesin tanpa pywin32.
`load_com_modules()` baru mengimpor `win32com.client` dan `pythoncom` ketika
Word atau PowerPoint akan dipakai. Dalam kondisi berikut API melempar
`PdfUnavailableError` dengan pesan yang menyebut tindakan:

- `sys.platform != "win32"`;
- pywin32 tidak terpasang di Windows;
- apartment COM gagal diinisialisasi;
- `DispatchEx` gagal karena Word atau PowerPoint tidak terpasang.

## COM apartment dan thread

Operasi Office berjalan di thread worker daemon. `CoInitialize()` dan
`CoUninitialize()` dipanggil di thread yang sama, sehingga objek COM tidak
melintasi apartment. Thread utama hanya menunggu hasil, menjalankan watchdog,
dan memberi sinyal cleanup.

## Watchdog

`run_with_watchdog()` menunggu hasil worker dengan `timeout_s` wall-clock.
Saat waktu habis:

1. `on_timeout` menghentikan PID Word/PowerPoint yang sudah terverifikasi;
2. worker ditunggu sampai benar-benar berhenti (maksimum
   `WATCHDOG_CLEANUP_TIMEOUT_S`, atau budget cleanup turunan);
3. bila worker berhenti, `WordTimeoutError` dilempar dan direktori kerja aman
   dibersihkan;
4. bila worker masih hidup, `WordCleanupError` dilempar dengan pesan cleanup
   ambigu. Pemanggil tidak menghapus snapshot/temp pada kasus ini karena worker
   masih dapat menulis ke sana; proses Office harus diperiksa manual.

Cleanup dan `tasklist`/`taskkill` memakai sisa deadline. Jadi lock, operasi COM,
dan cleanup tidak lagi masing-masing memakai batas default 30 detik yang tidak
terkait `timeout_s`. Karena menunggu worker dan cleanup PID, satu panggilan
dapat melewati `timeout_s` sebesar budget cleanup terbatas
(`WATCHDOG_CLEANUP_TIMEOUT_S` dan batas terminate), bukan tanpa batas.

## PID dan cleanup

- Snapshot PID `WINWORD.EXE` atau `POWERPNT.EXE` diambil sebelum `DispatchEx`.
  Snapshot mengembalikan `set[int] | None`; `None` berarti pembacaan tasklist
  gagal. Bila snapshot awal gagal, operasi dibatalkan sebelum aplikasi COM
  dibuat sehingga tidak ada proses yang bisa salah dihentikan.
- PID automation tidak diambil dari "PID baru terendah". Setelah aplikasi
  dibuat, `Application.Hwnd` diterjemahkan menjadi PID pemilik window dengan
  `GetWindowThreadProcessId`. PID itu harus bukan PID snapshot awal, terlihat
  di snapshot baru, image-nya cocok, dan creation time-nya dapat dibaca.
  Bila salah satu syarat gagal, tracker tidak mengklaim PID apa pun.
- Instance Office pengguna yang sudah berjalan sebelum automation, atau yang
  dibuka pengguna setelah `begin`, tidak pernah menjadi target karena PID
  automation ditentukan dari window handle, bukan dari selisih snapshot.
- Sebelum `taskkill`, nama image dan creation time dibaca ulang dan harus sama
  persis dengan nilai saat PID diklaim. PID yang sudah dipakai ulang proses
  lain (image atau creation time berbeda) tidak dihentikan.
- `Close` dan `Quit()` selalu dicoba di blok `finally`. Kegagalan cleanup tidak
  menimpa error utama.

## Lock

`com_lock()` memakai `msvcrt.locking` pada file lock di `%TEMP%` dan
menerima `timeout_s` turunan dari deadline operasi. Nama berkas lock masih
historis sampai F3, tetapi lock yang sama dipakai bersama oleh Word dan
PowerPoint, sehingga satu mesin hanya menjalankan satu operasi COM Office pada
satu waktu. Pemanggil baru tidak boleh memegang lock lama saat memanggil
adapter ini; kepemilikan lock ada di adapter.

Lock adalah no-op di non-Windows. Di Windows, kegagalan memperoleh lock
menghasilkan `WordBusyError` setelah sisa budget habis, bukan setelah default
30 detik yang tidak terkait timeout pemanggil.

## Verifikasi output

- PDF harus ada, berukuran lebih dari nol, dan diawali `%PDF-`.
- DOCX hasil `update_fields` harus ada, berukuran lebih dari nol, dan diawali
  magic ZIP (`PK\x03\x04`) sebelum mengganti sumber.
- PDF final dan DOCX final ditulis dengan `os.replace` agar target lama tidak
  setengah jadi. Sumber hanya berubah setelah verifikasi lulus.

## Test

`tests/pdf` memakai fake COM, fake `pythoncom`, dan fake process control. Tidak
ada Word/PowerPoint nyata, PowerShell, atau jaringan. Tes deadline memakai jeda
pendek untuk mengukur timeout. Yang dibekukan:

- urutan panggilan COM Word dan argumen `Open`/`ExportAsFixedFormat`;
- urutan panggilan COM PowerPoint, argumen `Open`, `SaveAs(32)`, dan `Close`
  tanpa `Save`;
- urutan embedding font, argumen `Open(ReadOnly=False)` dan
  `SaveCopyAs(24, -1)`, verifikasi font Plus Jakarta Sans regular/bold,
  tidak adanya timing/transition, marker/alt yang dipertahankan, python-pptx,
  serta sumber utuh saat gagal;
- DOCX/PPTX sumber tetap utuh saat ekspor dan finalisasi field;
- `update_fields` memakai snapshot lalu mengganti path sumber secara atomik;
- timeout memanggil cleanup PID dan menunggu worker berhenti; worker yang
  masih hidup menghasilkan `WordCleanupError`;
- guard non-Windows dan pywin32 hilang;
- snapshot proses gagal membatalkan operasi sebelum `DispatchEx`;
- dua PID Office baru, PID reuse, dan Office pengguna yang dibuka setelah
  `begin` tidak menggeser target cleanup;
- path absolut `System32`/`Sysnative` dan lock COM dengan timeout turunan.

Smoke Word dan PowerPoint nyata dijalankan terpisah di Windows pada gate final.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
