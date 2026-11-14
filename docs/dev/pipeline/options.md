# Opsi Build

Halaman ini menjelaskan flag `autooffice build` dan matriks target. Kontrak
CLI ada di [contracts/cli.md](../../contracts/cli.md).

## Opsi build

| Flag | Berlaku | Arti |
| --- | --- | --- |
| `--target` | wajib | Target dipisah koma: `docx,pdf` untuk `.md`; `pptx,pdf,slides` untuk `.yaml`; atau `all`. |
| `--out DIR` | semua | Direktori output final; harus direktori, bukan berkas. |
| `--theme NAME` | `.yaml` | `indigo` atau `hitam`; menimpa `theme.name`. |
| `--terms` | `.md` | Aktifkan check, apply, verify, dan review istilah. |
| `--dry-run` | semua | Validasi penuh dan cetak rencana tanpa menulis output, state, atau remote. |
| `--keep-intermediate` | semua | Pertahankan workspace dan intermediate DOCX/PPTX/staging. |
| `--sync MODE` | `.yaml` + `slides` | `push` (default), `pull`, `diff`, atau `apply`. |

Untuk platform tanpa Word, pilih `--target docx`. Target `all` tidak
diturunkan otomatis menjadi DOCX.

## Aturan target

| Input | `docx` | `pdf` | `pptx` | `slides` | `all` |
| --- | --- | --- | --- | --- | --- |
| `.md` | ya | ya, lewat DOCX | tidak | tidak | DOCX + PDF |
| `.yaml` | tidak | ya, lewat PPTX | ya | ya | PPTX + PDF + Slides |

- Target dipisah koma; spasi setelah koma boleh.
- Duplikat dihapus dan urutan kanonik dipertahankan.
- `all` tidak boleh digabung dengan target lain.
- `pdf` untuk `.md` membangun DOCX lebih dulu; `pdf` untuk `.yaml` membangun
  PPTX lebih dulu.
- `slides` memerlukan extra `google` dan kredensial OAuth.
- `all` untuk `.yaml` memerlukan Google; `pptx,pdf` adalah jalur offline.

## Target per platform DOCX

| Platform | `docx` | `pdf` | `all` |
| --- | --- | --- | --- |
| Windows dengan Word | DOCX, field diperbarui | PDF | DOCX dan PDF |
| Windows tanpa Word | DOCX dengan peringatan | error | DOCX dapat tertulis, lalu error |
| Linux | DOCX best-effort, field belum final | error | DOCX dapat tertulis, lalu error |

`pdf` dan `all` untuk `.md` selalu membutuhkan Word karena PDF tidak dapat
dihasilkan tanpa Word. Tidak ada fallback diam-diam yang menurunkan `all`
menjadi DOCX.

## Referensi resmi

Label registry yang dipakai halaman ini: `Word COM object model (VBA
reference)`. URL resminya ada di [registry referensi](../references.md).

## Halaman terkait

- [stages.md](stages.md) untuk stage yang diaktifkan `--terms`.
- [outputs.md](outputs.md) untuk nama dan lokasi artefak.
- [artifacts.md](artifacts.md) untuk efek `--keep-intermediate`.
- [errors.md](errors.md) untuk kegagalan target.
- [../pdf.md](../pdf.md) untuk Word, PowerPoint, dan embedding font.
