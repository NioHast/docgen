# CLI AutoOffice

`autooffice` adalah satu-satunya permukaan perintah AutoOffice. Tidak ada alias,
shim, atau entry point kedua. Kontrak normatifnya ada di
[kontrak CLI](../contracts/cli.md).

## Perintah

```text
autooffice build <input> --target <targets> [opsi]
autooffice check <input> [opsi]
autooffice doctor [opsi]
autooffice --version
autooffice --help
```

`autooffice` tanpa perintah menampilkan bantuan dan keluar dengan kode 0.

## Target

| Input | `docx` | `pdf` | `pptx` | `slides` | `all` |
| --- | --- | --- | --- | --- | --- |
| `.md` | ya | ya, lewat DOCX | tidak | tidak | DOCX + PDF |
| `.yaml` | tidak | ya, lewat PPTX | ya | ya | PPTX + PDF + Slides |

- Target dipisah koma dan spasi setelah koma boleh.
- Duplikat dihapus dan urutan kanonik dipakai: `docx,pdf` untuk `.md`, lalu
  `pptx,pdf,slides` untuk `.yaml`.
- `all` tidak boleh digabung dengan target lain.
- `--target` wajib untuk `build`.
- `pdf` dari `.md` membangun DOCX lebih dulu; `pdf` dari `.yaml` membangun
  PPTX lebih dulu.
- `slides` dan `all` untuk `.yaml` memerlukan extra `google` serta kredensial
  OAuth. Jalur offline untuk deck adalah `pptx,pdf`.
- Input selain `.md` dan `.yaml` ditolak.

## Penamaan output

### Input `.md`

- `<report_name>.docx` dan `<report_name>.pdf` dari front matter.
- Manifest `.laporan/manifest.json` dan istilah `.laporan/istilah-baru.txt`
  tetap berada di samping dokumen sumber.
- Intermediate `.laporan-build/`.
- Target `pdf` tanpa `docx` membangun DOCX intermediate di dalam
  `.laporan-build/`; workspace dibersihkan setelah konversi PDF selesai.
  Intermediate di dalam workspace hanya dipertahankan bila
  `--keep-intermediate` aktif. DOCX final yang sudah ada tidak ditimpa.
- `examples/<nama>/document.md` menulis final ke `examples/<nama>/out/`;
  dokumen pengguna menulis di direktori dokumen.
- `--out DIR` hanya memindahkan artefak final.

### Input `.yaml`

- `<stem>.pptx`, `<stem>.pdf`, dan `<stem>.transcript.md` bila
  `transcripts.md` ada.
- Staging internal `<stem>.slides-upload.pptx`.
- State `.autooffice/state/<stem>.json`, cache `.autooffice/cache/`, review
  `.autooffice/review/`, dan intermediate `.autooffice-build/<stem>/`.
- `--out DIR` hanya memindahkan artefak final. State, cache, intermediate,
  dan review tetap di samping YAML agar pembersihan workspace aman.
- Mode `--sync diff|pull|apply` tidak merender dan tidak membuat workspace;
  mode tersebut juga tidak menghapus `.autooffice-build/<stem>/` yang sudah
  ada, termasuk intermediate yang dipertahankan `--keep-intermediate`.

## Flag

| Flag | Berlaku | Arti |
| --- | --- | --- |
| `--out DIR` | semua | Direktori output final; harus direktori, bukan berkas. |
| `--theme NAME` | `.yaml` | `indigo` atau `hitam`; menimpa `theme.name`. |
| `--terms` | `.md` | Menjalankan gate istilah seperti pipeline DOCX lama. |
| `--dry-run` | semua | Validasi dan cetak rencana tanpa menulis file final, state, atau remote. |
| `--keep-intermediate` | semua | Menyimpan intermediate di lokasi yang terdokumentasi; tanpa flag ini workspace dibersihkan setelah build/konversi PDF selesai. |
| `--sync MODE` | `.yaml` + `slides` | `push` (default), `pull`, `diff`, atau `apply`. |

`--theme` untuk `.md`, `--terms` untuk `.yaml`, dan `--sync` tanpa target
`slides` ditolak dengan kode keluar 2.

## Dry-run

`--dry-run` memvalidasi input, aset, copy checker, transkrip, compiler,
layout, dan coverage plan. Dry-run mencetak target yang dijalankan serta file
yang akan ditulis, tetapi tidak menulis file atau state, tidak memanggil
Word/PowerPoint COM, dan tidak menulis ke Drive, Sheets, atau Slides. Overflow,
key hilang, atau dependency wajib yang tidak tersedia menghasilkan kode
keluar nonzero.

## Check dan doctor

`autooffice check <input>` tidak memanggil Pandoc, Word, atau Google.

- `.md`: front matter, format, struktur, aset, urutan heading, dan caption.
- `.yaml`: schema, compiler, coverage plan, layout/overflow, copy checker, dan
  transcript validation bila modul dan berkasnya tersedia.

`autooffice doctor` memeriksa Python, Pandoc, `mmdc`, Word/PowerPoint COM,
pywin32, aset font, status font terpasang, extra Google, kredensial OAuth
lokal, dan izin tulis workspace tanpa jaringan. Tambahkan `--json` untuk
keluaran mesin yang deterministik. `doctor` tetap berjalan tanpa extra
`google`; pemeriksaan Google dilaporkan belum terpasang dan pemeriksaan lain
tetap dijalankan. Target `slides` mewajibkan aset font dan token Google,
tetapi tidak mewajibkan font terpasang karena memakai Google Fonts.

## Font untuk PPTX/PDF di Windows

Target `pptx` dan `pdf` dari `.yaml` menanam Plus Jakarta Sans lewat
PowerPoint COM; `pdf` dari `.md` memakai Word COM. Sebelum build, font harus
terpasang untuk pengguna saat ini dan terdaftar di registry HKCU. Pasang dari
aset yang dibundel repo:

```bash
python tools/install_fonts.py
python tools/install_fonts.py --list
```

Installer menyalin empat TTF ke
`%LOCALAPPDATA%\Microsoft\Windows\Fonts`, memperbarui
`HKCU\Software\Microsoft\Windows NT\CurrentVersion\Fonts`, memuat font ke sesi
berjalan, dan menyiarkan `WM_FONTCHANGE`. Installer tidak membutuhkan admin,
PowerShell, atau pywin32 dan aman dijalankan ulang karena berkas dengan hash
sama dilewati. `--list` hanya membaca status.

`autooffice doctor` melaporkan apakah font terpasang per-user atau di font
store sistem dan menyarankan perintah installer bila belum lengkap. Target
`slides` memakai Google Fonts sehingga tidak membutuhkan langkah ini.

## Kode keluar

| Kode | Arti |
| --- | --- |
| 0 | Sukses atau `check` tanpa temuan. |
| 1 | Validasi, build, coverage, dependency, COM, Google, atau temuan check. |
| 2 | Argumen CLI salah, target tidak valid, atau kombinasi flag salah. |

## Contoh

```bash
autooffice build document.md --target docx
autooffice build document.md --target docx,pdf --terms
autooffice build deck.yaml --target pptx,pdf
autooffice build deck.yaml --target all --dry-run
autooffice build deck.yaml --target slides --sync diff
autooffice check document.md
autooffice check deck.yaml --target pptx,pdf
autooffice doctor --json
```
