# Kontrak CLI

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 10 (10.1-10.11), 13.2, dan keputusan L16.
Pemilik kontrak: integration owner.

## Tujuan

Kontrak ini membekukan satu permukaan perintah `autooffice`: nama perintah,
matriks target, penamaan output, exit code, dan aturan error. Permukaan di
bawah ini adalah permukaan final v1. Tidak ada permukaan kedua, alias, shim,
atau entry point baru.

## Invarian

1. Perintah yang diizinkan hanya:

```text
autooffice build <input> --target <targets> [opsi]
autooffice check <input> [opsi]
autooffice doctor [opsi]
autooffice --version
autooffice --help
```

2. Permukaan final v1 tidak punya perintah, alias, atau entry point `docgen`
   dan `deck-studio`. Pengecualian transisi: entry point `docgen` yang sudah
   ada tetap berfungsi sampai parity F1-DOCX diterima, bukan bagian permukaan
   AutoOffice v1, dan dihapus setelah parity. Tidak ada alias baru.
   `--help` hanya menampilkan perintah yang didukung.
3. `--target` wajib untuk `build`. Target dipisah koma, spasi setelah koma
   boleh, duplikat dihapus, dan urutan kanonik dipertahankan.
4. `all` tidak boleh digabung dengan target lain.
5. Input selain `.md` dan `.yaml` ditolak. `docx` hanya untuk `.md`; `pptx`
   dan `slides` hanya untuk `.yaml`.

`tools/quality/check_no_legacy.py` pada F0 bersifat list-only: hanya memuat
daftar target no-legacy. Implementasi pemeriksaan penuh masih pending dan
dijadwalkan pada F3-GATE.

## Matriks target

| Input | `docx` | `pdf` | `pptx` | `slides` | `all` |
| --- | --- | --- | --- | --- | --- |
| `.md` | ya | ya, lewat DOCX | tidak | tidak | DOCX + PDF |
| `.yaml` | tidak | ya, lewat PPTX | ya | ya | PPTX + PDF + Slides |

- `pdf` untuk `.md` membangun DOCX terlebih dahulu.
- `pdf` untuk `.yaml` membangun PPTX terlebih dahulu.
- `slides` memerlukan extra `google` dan kredensial OAuth.
- `all` untuk `.yaml` memerlukan Google; `all` bukan mode offline.
- `pptx,pdf` adalah jalur offline untuk PPTX dan PDF.

## Flag

| Flag | Berlaku | Aturan |
| --- | --- | --- |
| `--out DIR` | semua | Direktori output, dibuat bila belum ada; tidak boleh menunjuk file. |
| `--theme NAME` | `.yaml` | `indigo` atau `hitam`; menimpa `theme.name`; error untuk `.md`. |
| `--terms` | `.md` | Menulis daftar istilah baru seperti docgen; error untuk `.yaml`. |
| `--dry-run` | semua | Validasi penuh dan cetak rencana; tidak menulis output, state, atau remote. |
| `--keep-intermediate` | semua | Menyimpan intermediate di lokasi yang didokumentasikan. |
| `--sync MODE` | `.yaml` + `slides` | `push` (default), `pull`, `diff`, `apply`. |

`--sync` hanya valid bila target berisi `slides`. `pull`, `diff`, dan `apply`
memerlukan state dengan `presentation_id`.

## Penamaan output

Input `.md` mengikuti perilaku docgen:

- `<report_name>.docx` dan `<report_name>.pdf` dari front matter.
- Manifest `.laporan/manifest.json`.
- Istilah `.laporan/istilah-baru.txt`.
- Intermediate `.laporan-build/`.
- `examples/<name>/document.md` default ke `examples/<name>/out/`.
- `--out DIR` menimpa direktori output; lokasi manifest dan intermediate
  mengikuti aturan docgen.

Input `.yaml`:

- Output default di samping YAML, kecuali `examples/<name>/` memakai
  `examples/<name>/out/`.
- `<stem>.pptx`, `<stem>.pdf`, dan `<stem>.transcript.md` bila
  `transcripts.md` ada.
- Staging internal `<stem>.slides-upload.pptx`, bukan deliverable.
- State `.autooffice/state/<stem>.json`, cache `.autooffice/cache/`,
  intermediate `.autooffice-build/<stem>/`, dan review `.autooffice/review/`.
- `--out DIR` mengubah direktori artefak final, bukan identitas state.

## Dry-run dan penulisan

`--dry-run` wajib memvalidasi input dan aset, menjalankan copy checker dan
transcript validation, menyusun compiler, layout measurement, coverage plan,
serta mencetak file, target, aksi Google, dan rencana diff. Dry-run tidak
menulis file atau state, tidak memanggil COM, dan tidak menulis ke Drive,
Sheets, atau Slides. Temuan overflow, key hilang, atau kredensial Google yang
tidak ada saat target Slides menghasilkan exit code nonzero.

File final ditulis atomik. Output yang sudah selesai tidak dihapus saat target
lain gagal, tetapi exit code tetap nonzero dan ringkasan diberikan.

## Exit code

| Kode | Arti |
| --- | --- |
| 0 | Sukses; `diff` dengan perbedaan tetap 0 karena operasi diff berhasil. |
| 1 | Validasi, build, coverage, dependency, COM, atau Google gagal. |
| 2 | Argumen CLI salah, target tidak valid, atau kombinasi flag salah. |

Error validasi menyebut input, slide, block, key, dan field. Error aset
menyebut path relatif dan path absolut hasil resolusi. Error Google menyebut
operasi, file, dan langkah; error COM menyebut aplikasi, file, dan target.
Tidak ada traceback panjang kecuali environment debug eksplisit dan tidak ada
fallback diam-diam.

## Contoh

```bash
autooffice build examples/demo-deck/deck.yaml --target pptx,pdf --out out
autooffice build examples/demo-deck/deck.yaml --target slides --sync diff
autooffice check examples/docx/thesis-single/document.md
```

Perintah pertama menulis `out/demo-deck.pptx` dan `out/demo-deck.pdf` tanpa
memanggil Google. Perintah kedua hanya membaca remote dan menulis laporan diff
di `.autooffice/review/`.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Permukaan final v1 dan pengecualian transisi `docgen` | `autooffice --help`; review F0-CONTRACTS; parity F1-DOCX. |
| `check_no_legacy` F0 list-only, implementasi F3 | Daftar target di `tools/quality/check_no_legacy.py`; F3-GATE pending. |
| Matriks target dan normalisasi | `tests/cli/test_targets.py` (planned), acceptance bagian 18.8. |
| Penamaan output dan `--out` | `tests/cli/test_outputs.py` (planned), golden output. |
| Exit code dan error | `tests/cli/test_exit_codes.py` (planned), contract test pesan error. |
| Dry-run tanpa efek samping | `tests/cli/test_dry_run.py` (planned), fake Google dan fake COM. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
