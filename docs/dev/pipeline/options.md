# Opsi Build

Halaman ini menjelaskan flag `docgen build` dan matriks target per platform.
Kontrak CLI ada di [contracts/stage-api.md](../contracts/stage-api.md).

## Opsi build

| Flag | Default | Arti |
| --- | --- | --- |
| `--target` | `both` | `docx`, `pdf`, atau `both`. |
| `--keep` | `false` | Pertahankan `.laporan-build/` dan intermediate DOCX. |
| `--terms` | `false` | Aktifkan check, apply, verify, dan review istilah. |
| `--no-manifest` | `false` | Bookmark tetap; manifest dan source scan mati. |
| `--no-adeu` | `false` | Bookmark, manifest, dan source scan mati. |
| `--allow-missing-word` | `false` | `both` boleh melewati PDF tanpa Word. |

## Aturan target

| Platform | `docx` | `pdf` | `both` |
| --- | --- | --- | --- |
| Windows dengan Word | DOCX | PDF | DOCX dan PDF |
| Windows tanpa Word | DOCX | error | DOCX dengan peringatan bila `--allow-missing-word`; selain itu error |
| Debian/Linux | DOCX best-effort | error | error, atau DOCX dengan `--allow-missing-word` |

`--target pdf` selalu membutuhkan Word, bahkan dengan
`--allow-missing-word`, karena tidak ada output yang diminta.

## Referensi resmi

Label registry yang dipakai halaman ini: `Word COM object model (VBA
reference)`. URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [stages.md](stages.md) untuk stage yang diaktifkan `--terms`.
- [outputs.md](outputs.md) untuk nama dan lokasi artefak.
- [artifacts.md](artifacts.md) untuk efek `--keep`.
- [errors.md](errors.md) untuk kegagalan target.
