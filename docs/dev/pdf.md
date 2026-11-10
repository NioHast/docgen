# PDF dan Word

PDF hanya didukung di Windows dengan Microsoft Word desktop. Pipeline tidak
memakai LibreOffice atau mesin konversi lain. Di Debian, target yang tersedia
adalah DOCX best-effort.

## Daftar isi

- [Alur](#alur)
- [Target](#target)
- [Debian dan Linux](#debian-dan-linux)
- [Variabel lingkungan](#variabel-lingkungan)
- [Batasan](#batasan)
- [Pemeriksaan](#pemeriksaan)
- [Hardening Word COM](#hardening-word-com)
  - [Serialisasi](#serialisasi)
  - [Lifecycle dan PID](#lifecycle-dan-pid)
  - [Partial log dan step marker](#partial-log-dan-step-marker)
  - [Retry](#retry)
  - [Opsi Word](#opsi-word)
  - [Verifikasi](#verifikasi)
  - [CI](#ci)
  - [Batas](#batas)

## Alur

```text
Markdown
  -> Pandoc
  -> stage DOCX
  -> save DOCX
  -> office: Word memperbarui field dan menyimpan DOCX
  -> pdf: Word mengekspor DOCX final ke PDF
```

Ekspor PDF memakai DOCX final, bukan Markdown. Word memperbarui TOC,
`PAGEREF`, nomor halaman, dan field lain sebelum ekspor. Pipeline memeriksa
bahwa PDF yang dihasilkan ada dan memiliki header `%PDF-`.

Adaptor Word berada di `scripts/word.ps1` dan dipanggil lewat PowerShell.
Word berjalan tanpa interaksi pengguna. Output ditulis atomic ke direktori
tujuan.

## Target

| Target | Windows dengan Word | Windows tanpa Word | Debian/Linux |
| --- | --- | --- | --- |
| `--target docx` | DOCX, field diperbarui | DOCX, `office` dilewati dengan peringatan | DOCX best-effort |
| `--target pdf` | PDF | error | error |
| `--target both` | DOCX dan PDF | error, atau DOCX dengan `--allow-missing-word` | error, atau DOCX dengan `--allow-missing-word` |

`--target pdf` selalu membutuhkan Word karena tidak ada output yang diminta
selain PDF. `--allow-missing-word` hanya berlaku untuk `both`.

Untuk `--target pdf`, DOCX intermediate ditulis di workspace dan tidak
disalin ke direktori output. Dengan `--keep`, workspace dan DOCX intermediate
dipertahankan.

## Debian dan Linux

Di Debian, pipeline dapat menghasilkan DOCX selama Python dan Pandoc tersedia.
Namun:

- stage `office` tidak berjalan karena Word tidak ada;
- TOC dan nomor halaman dapat tetap kosong sampai DOCX dibuka di Word;
- PDF tidak dihasilkan;
- build `--target both` berhenti dengan `ToolMissingError` kecuali memakai
  `--allow-missing-word`;
- `--allow-missing-word` hanya menurunkan target menjadi DOCX dengan
  peringatan.

Jalur PDF resmi tetap Windows. Jangan mengklaim paritas PDF di Debian.

## Variabel lingkungan

| Variabel | Fungsi |
| --- | --- |
| `DOCGEN_WINWORD` | Path eksplisit ke `WINWORD.EXE`. |
| `DOCGEN_POWERSHELL` | Path eksplisit ke PowerShell. |
| `DOCGEN_WORD_SCRIPT` | Path eksplisit ke `scripts/word.ps1`. |
| `DOCGEN_PANDOC` | Path eksplisit ke Pandoc. |
| `PANDOC` | Alternatif path Pandoc. |

Deteksi default mencari Word di registry, `PATH`, dan folder instalasi
Microsoft Office. PowerShell dicari sebagai `powershell` atau `pwsh`.

## Batasan

- Word Online tidak menyediakan COM dan tidak dapat dipakai.
- PDF dapat berbeda sedikit dari DOCX karena font pengganti atau pemenggalan
  baris.
- Build DOCX tanpa Word tidak memfinalkan field. TOC dapat menampilkan `0`
  sampai dokumen dibuka dan field diperbarui.
- PDF tidak dijamin byte-identik antar build.
- Word dapat menulis ulang package DOCX saat menyimpan. Perubahan XML yang
  tidak disengaja mungkin muncul, tetapi tampilan tidak diubah secara sengaja.
- Tutup DOCX atau PDF tujuan sebelum build. Berkas yang terkunci membuat
  penulisan gagal.

## Pemeriksaan

`doctor` menampilkan status Word di Windows. Di platform lain, Word
ditampilkan sebagai tidak berlaku. `doctor` tidak memeriksa LibreOffice karena
LibreOffice bukan dependensi pipeline.

```bash
uv run --project <repo> docgen doctor
```

## Hardening Word COM

Pemanggilan Word nyata melewati beberapa lapis pengaman agar build paralel
tidak saling mengganggu dan kegagalan COM dapat didiagnosis.

### Serialisasi

- Pemanggilan Word diserialisasi dengan lock file `%TEMP%/docgen-word.lock`
  memakai `msvcrt.locking`. Hanya satu proses Word automation yang berjalan
  pada satu waktu.
- Bila lock tidak diperoleh dalam 30 detik, stage gagal dengan `WORD-BUSY`.
  Tidak ada dua build Word yang berjalan paralel.

### Lifecycle dan PID

- `scripts/word.ps1 -PidFile <path>` mencatat PID proses `WINWORD.EXE` baru.
  Nilai `0` berarti tidak ada proses baru yang terdeteksi, misalnya karena
  menempel ke instance Word yang sudah berjalan.
- Saat timeout, pohon proses PowerShell dihentikan lebih dulu, lalu hanya PID
  Word yang tercatat yang dihentikan.
- Saat sukses, PID yang masih hidup dibersihkan hanya bila image prosesnya
  `WINWORD.EXE`.
- Pipeline tidak pernah menghentikan semua proses `WINWORD.EXE`; cleanup selalu
  memakai PID yang tercatat.

### Partial log dan step marker

- Skrip menulis marker `[word] STEP open`, `opened`, `repaginate`,
  `fields_update`, `toc_update`, `save`, `export`, dan `done` ke log.
- stdout/stderr disimpan ke file sementara agar isi parsial tetap terbaca saat
  proses dihentikan.
- Saat timeout, pesan memuat step terakhir dan 10 baris log terakhir.
  `WORD-TIMEOUT` menyebut langkah yang macet.

### Retry

- Maksimal satu retry (dua percobaan) untuk `RPC_E_CALL_REJECTED`,
  `0x80010001`, `0x800706BE`, dan `Call was rejected by callee`.
- Timeout, DOCX tidak valid, dan error non-transien tidak di-retry.

### Opsi Word

- Sebelum dokumen dibuka, adapter menetapkan `AutomationSecurity=3`,
  `Options.UpdateLinksAtOpen=false`, `Options.ConfirmConversions=false`,
  `Visible=false`, `DisplayAlerts=0`, dan `ScreenUpdating=false`.

### Verifikasi

- Build thesis di Windows dengan Word 16 menghasilkan DOCX dan PDF, tiga TOC
  terisi, tidak ada proses Word tersisa, dan tidak ada file PID tertinggal.

### CI

- GitHub-hosted runner tidak dijamin memiliki Word desktop atau sesi
  interaktif. Word COM yang andal memerlukan self-hosted Windows runner dengan
  Word berlisensi dan sesi interaktif.
- Ini catatan strategi, bukan workflow: tidak ada file workflow baru.

### Batas

- PID reuse mungkin terjadi, tetapi kecil; cleanup sukses dibatasi pada image
  `WINWORD.EXE`.
- Retry hanya mendeteksi marker yang dikenal; pesan COM terlokalisasi mungkin
  tidak di-retry.
- Timeout tetap global (300 detik). Step marker membantu diagnosis, bukan
  timeout per langkah.
