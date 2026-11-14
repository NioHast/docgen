# Output

Halaman ini menjelaskan penamaan dan lokasi artefak pengguna. Kontrak CLI dan
penamaan output ada di [contracts/cli.md](../../contracts/cli.md). Artefak
antara dijelaskan di [artifacts.md](artifacts.md).

## Nama output DOCX

`report_name` wajib di front matter dan tidak memiliki nilai default. Nilai
kosong atau hanya whitespace menghasilkan `CFG-REQUIRED`. DOCX dan PDF memakai
stem yang sama, misalnya `report_name: "Tugas"` menghasilkan `Tugas.docx` dan
`Tugas.pdf`. Tidak ada flag CLI `--report-name`. Output ditulis di samping
`document.md`, kecuali dokumen di `examples/<name>/` yang ditulis ke
`examples/<name>/out/`.

## Artefak pengguna DOCX

| Artefak | Lokasi | Kapan |
| --- | --- | --- |
| DOCX | output dir | `--target docx` atau `docx,pdf` |
| PDF | output dir | `--target pdf` atau `docx,pdf` |
| `.laporan/manifest.json` | samping dokumen | Selalu ditulis oleh pipeline DOCX |
| `.laporan/istilah-baru.txt` | samping dokumen | `--terms` |
| `.laporan-build/` | samping dokumen | Hanya dengan `--keep-intermediate` |

Manifest dan bookmark `pNNNN` selalu aktif pada AutoOffice v1. Tidak ada flag
CLI untuk mematikannya.

## Artefak pengguna deck

| Artefak | Lokasi | Kapan |
| --- | --- | --- |
| PPTX | output dir | `--target pptx` atau `all` |
| PDF | output dir | `--target pdf` atau `all` |
| `.transcript.md` | output dir | Bila `transcripts.md` ada |
| `.slides-upload.pptx` | output dir | Staging internal `slides`; bukan deliverable |
| `.autooffice/state/` | samping YAML | Target `slides` atau sinkronisasi |
| `.autooffice/cache/` | samping YAML | Cache Mermaid |
| `.autooffice/review/` | samping YAML | Mode sync `pull`, `diff`, atau `apply` |
| `.autooffice-build/<stem>/` | samping YAML | Workspace deck |

`--out DIR` hanya memindahkan artefak final. State, cache, review, dan
intermediate deck tetap berada di samping YAML agar pembersihan workspace
tidak menyentuh direktori output.

Tidak ada output di `build/` atau `review/`.

## Halaman terkait

- [options.md](options.md) untuk flag yang memilih target.
- [artifacts.md](artifacts.md) untuk workspace dan penulisan atomic.
- [errors.md](errors.md) untuk kegagalan menulis output.
- [../docx/terms.md](../docx/terms.md) untuk isi review istilah.
