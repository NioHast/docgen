# Kontribusi

Panduan ini untuk perubahan kode, data format, tes, dan dokumentasi. Baca
[architecture.md](architecture.md) dan kontrak di [contracts/](contracts/config.md)
sebelum mengubah pipeline atau stage.

## Setup

```bash
uv sync --project <repo> --extra dev
uv run --project <repo> docgen --version
uv run --project <repo> pytest tests/unit
```

`uv.lock` harus ikut berubah bila `pyproject.toml` berubah. Jalankan
`uv lock`, bukan mengedit lock manual.

## Menjalankan tes

```bash
uv run --project <repo> pytest tests/unit
uv run --project <repo> pytest -m "not integration and not packaging and not e2e and not word and not windows"
uv run --project <repo> pytest
```

Tes yang membutuhkan Word atau Windows memakai marker `word` atau `windows`.
Tes PDF golden hanya berjalan di Windows. Di Debian, jalankan subset non-Windows
dan jangan mengklaim PDF lulus.

Tes packaging dijalankan dari luar repo dan memastikan `git status` tidak
berubah. Jangan menambahkan build DOCX (Word) ke tes unit.

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

- Urutan stage didefinisikan di `pipeline.py`. Mengubah urutan berarti
  memperbarui kontrak dan tes.
- Key `format.yml` dan `structure.yml` memakai skema tertutup. Key baru harus
  memiliki konsumen nyata dan tes positif/negatif.
- Jangan menambah key yang tidak dibaca kode.
- Template struktur harus tetap valid dan tidak keluar dari direktori template.
- Data paket dibaca lewat `src/docgen/paths.py`; jangan menambah fallback ke
  akar repo atau direktori kerja.

## Aturan dokumentasi

- Semua perintah `docgen` ditulis sebagai
  `uv run --project <repo> docgen ...`.
- Output pengguna ditulis di samping `document.md`; contoh ditulis di
  `examples/<name>/out/`. Jangan mendokumentasikan `build/` atau `review/`.
- Jangan merujuk path atau alat yang sudah dihapus.
- Jangan memakai em dash atau en dash.
- Tautan internal harus relatif dan menunjuk berkas yang ada.
- Jangan mengklaim fitur yang belum ada. TOC (table of contents) dan daftar memakai field native;
  daftar tabel/gambar memakai hybrid `SEQ`. PDF hanya Word di Windows.
- Dokumentasi pengguna ada di `docs/user/`; detail implementasi di
  `docs/dev/`. Jangan menduplikasi isi yang sama di dua tempat.

## Perubahan kontrak

Kontrak ada di `docs/dev/contracts/`. Perubahan yang mengubah perilaku publik
harus:

1. memperbarui kontrak;
2. menambah atau memperbarui tes;
3. mencatat keputusan di `docs/dev/decisions/` bila keputusan arsitektural;
4. memperbarui dokumentasi pengguna bila perilaku terlihat pengguna.

Jangan mengubah kontrak hanya agar tes lama lulus. Perbaiki implementasi atau
tes sesuai kontrak.

## Checklist sebelum selesai

- [ ] Perubahan hanya menyentuh area yang menjadi tanggung jawab.
- [ ] `pytest tests/unit` lulus.
- [ ] Tes integrasi terkait lulus atau dijelaskan alasannya.
- [ ] Tidak ada path atau alat lama yang diperkenalkan kembali.
- [ ] Tidak ada output build atau file sementara yang ikut dilacak.
- [ ] Dokumentasi dan tautan diperbarui.
- [ ] Tidak ada em dash atau en dash di dokumentasi.
- [ ] `git diff` diperiksa dan tidak berisi perubahan yang tidak disengaja.
