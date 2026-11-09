# PDF dan Word

PDF hanya didukung di Windows dengan Microsoft Word desktop. Pipeline tidak
memakai LibreOffice atau mesin konversi lain. Di Debian, target yang tersedia
adalah DOCX best-effort.

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

Adaptor Word berada di `resources/word.ps1` dan dipanggil lewat PowerShell.
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
| `DOCGEN_WORD_SCRIPT` | Path eksplisit ke `resources/word.ps1`. |
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
