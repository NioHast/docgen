# Output

Halaman ini menjelaskan penamaan dan lokasi artefak pengguna. Kontrak output
ada di [contracts/stage-api.md](../contracts/stage-api.md). Artefak antara
dijelaskan di [artifacts.md](artifacts.md).

## Nama output

`report_name` wajib di front matter dan tidak memiliki nilai default. Nilai
kosong atau hanya whitespace menghasilkan `CFG-REQUIRED`. DOCX dan PDF memakai
stem yang sama, misalnya `report_name: "Tugas"` menghasilkan `Tugas.docx` dan
`Tugas.pdf`. Tidak ada flag CLI `--report-name`. Output ditulis di samping
`document.md`, kecuali dokumen di `examples/<name>/` yang ditulis ke
`examples/<name>/out/`.

## Artefak pengguna

| Artefak | Lokasi | Kapan |
| --- | --- | --- |
| DOCX | output dir | `--target docx` atau `both` |
| PDF | output dir | `--target pdf` atau `both` |
| `.laporan/manifest.json` | samping dokumen | Default, kecuali `--no-manifest` atau `--no-adeu` |
| `.laporan/istilah-baru.txt` | samping dokumen | `--terms` |
| `.laporan-build/` | samping dokumen | Hanya dengan `--keep` |

Tidak ada output di `build/` atau `review/`.

## Halaman terkait

- [options.md](options.md) untuk flag yang memilih target.
- [artifacts.md](artifacts.md) untuk workspace dan penulisan atomic.
- [errors.md](errors.md) untuk kegagalan menulis output.
- [../docx/terms.md](../docx/terms.md) untuk isi review istilah.
