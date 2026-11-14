# Kontribusi

Panduan ini untuk perubahan kode, data format, tes, dan dokumentasi. Baca
[architecture.md](architecture.md) dan [indeks kontrak AutoOffice](../contracts/)
sebelum mengubah pipeline atau stage.

## Setup

```bash
uv sync --project <repo> --extra dev
uv run --project <repo> autooffice --version
uv run --project <repo> pytest tests/cli tests/docx
```

`uv.lock` harus ikut berubah bila `pyproject.toml` berubah. Jalankan
`uv lock`, bukan mengedit lock manual.

## Menjalankan tes

```bash
uv run --project <repo> pytest tests/cli tests/docx
uv run --project <repo> pytest -m "not integration and not packaging and not word and not windows and not slow"
uv run --project <repo> pytest
```

Suite AutoOffice berada di `tests/cli`, `tests/contract`, `tests/deck`,
`tests/design`, `tests/docx`, `tests/google`, `tests/pdf`,
`tests/performance`, `tests/property`, `tests/tools`, dan `tests/visual`.
Tes yang membutuhkan Word atau Windows memakai marker `word` atau `windows`.
Tes PDF memakai fake COM di suite offline; smoke Word/PowerPoint nyata hanya
dijalankan pada gate final di Windows. Di Linux, jalankan subset non-Windows
dan jangan mengklaim PDF lulus.

Jalankan tes CLI dan DOCX lebih dulu untuk perubahan yang menyentuh kedua area
tersebut. Jangan menambahkan build DOCX (Word) ke tes domain.

## Aturan kode

- Python 3.15 dan type hint modern.
- Satu tanggung jawab per modul. Stage tidak memuat logika package.
- Stage hanya memutasi part yang dideklarasikan.
- Jangan memanggil `DocumentPackage.load` atau `save` dari stage.
- Stage baru harus mengikuti kontrak `Stage.run(ctx)` dan urutan kanonik.
- Error memakai subclass `DocgenError`; jangan menelan error menjadi warning
  kecuali kontrak mengizinkan.
- Jangan menambah workaround, monkey patch, atau dead code.
- Jangan menambah dependensi tanpa memperbarui `pyproject.toml` dan `uv.lock`.

## Aturan stage dan data

- Urutan stage didefinisikan di `autooffice/docx/pipeline.py`. Mengubah urutan
  berarti memperbarui kontrak dan tes.
- Key `format.yml` dan `structure.yml` memakai skema tertutup. Key baru harus
  memiliki konsumen nyata dan tes positif/negatif.
- Jangan menambah key yang tidak dibaca kode.
- Template struktur harus tetap valid dan tidak keluar dari direktori template.
- Data paket dibaca lewat `src/autooffice/docx/paths.py`; jangan menambah fallback ke
  akar repo atau direktori kerja.

## Aturan dokumentasi

- Semua perintah `autooffice` ditulis sebagai
  `uv run --project <repo> autooffice ...`.
- Output pengguna ditulis di samping `document.md` atau `deck.yaml`; contoh
  ditulis di `examples/<name>/out/`. Jangan mendokumentasikan `build/` atau
  `review/`.
- Jangan merujuk path atau alat yang sudah dihapus.
- Jangan memakai em dash atau en dash.
- Tautan internal harus relatif dan menunjuk berkas yang ada.
- Jangan mengklaim fitur yang belum ada. TOC (table of contents) dan daftar
  DOCX memakai field native; daftar tabel/gambar memakai hybrid `SEQ`. PDF
  DOCX memakai Word di Windows; PDF dan font presentasi PowerPoint (PPTX)
  memakai PowerPoint di Windows.
- Dokumentasi pengguna ada di `docs/user/`; detail implementasi di
  `docs/dev/`. Jangan menduplikasi isi yang sama di dua tempat.

## Perubahan kontrak

Kontrak ada di `docs/contracts/`. Perubahan yang mengubah perilaku publik
harus:

1. memperbarui kontrak;
2. menambah atau memperbarui tes;
3. mencatat keputusan di `docs/decisions/` bila keputusan arsitektural;
4. memperbarui dokumentasi pengguna bila perilaku terlihat pengguna.

Jangan mengubah kontrak hanya agar tes lama lulus. Perbaiki implementasi atau
tes sesuai kontrak.

## Checklist sebelum selesai

- [ ] Perubahan hanya menyentuh area yang menjadi tanggung jawab.
- [ ] `uv run python tools/quality/gate.py` lulus.
- [ ] Tes integrasi terkait lulus atau dijelaskan alasannya.
- [ ] Tidak ada path atau alat lama yang diperkenalkan kembali.
- [ ] Tidak ada output build atau file sementara yang ikut dilacak.
- [ ] Dokumentasi dan tautan diperbarui.
- [ ] Tidak ada em dash atau en dash di dokumentasi.
- [ ] `git diff` diperiksa dan tidak berisi perubahan yang tidak disengaja.
