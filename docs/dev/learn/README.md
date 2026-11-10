# Materi Belajar docgen

Materi ini adalah jalur belajar berlapis untuk repo `docgen`: dari programmer
yang baru membuka repo sampai kontributor yang mengubah stage, helper DOCX,
atau dokumentasi. Setiap halaman punya tujuan, prasyarat, contoh dari repo,
perintah yang bisa dijalankan, latihan, dan tautan ke halaman berikutnya.

## Untuk siapa

| Pembaca | Mulai dari | Target akhir |
| --- | --- | --- |
| Pemula | [00 - Mulai di Sini](00-start-here.md) | Bisa menyiapkan environment dan menjalankan `check`. |
| Pemula yang siap build | 00, lalu [01 - Model Mental](01-mental-model.md) dan [02 - Build Pertama](02-first-build.md) | Paham lapisan dasar dan bisa menghasilkan DOCX. |
| Calon kontributor | 00 dan 01, lalu [03 - Tahap Pipeline](03-pipeline-stages.md) | Bisa melacak stage dan membaca output/error. |
| Kontributor pipeline | 00 sampai 03 | Bisa membaca kegagalan stage dan workspace. |
| Kontributor DOCX | 03, lalu [04 - Model DOCX](04-docx-model.md) | Bisa memilih helper DOCX yang benar. |
| Debugger | 02 sampai [05 - Tes dan Debugging](05-testing-and-debugging.md) | Bisa memilih tes dan menelusuri error tanpa menebak. |
| Kontributor rutin | 00 sampai [06 - Resep Perubahan](06-change-recipes.md) | Bisa mengubah konten, data, kode, dan docs dengan aman. |

## Peta halaman

| Halaman | Isi utama | Prasyarat |
| --- | --- | --- |
| [00 - Mulai di Sini](00-start-here.md) | Orientasi repo, setup, perintah aman, peta belajar. | Terminal dan Git dasar. |
| [01 - Model Mental](01-mental-model.md) | Empat lapisan, sumber versus artefak, satu load/satu save, batas Word, zero-fallback. | 00. |
| [02 - Build Pertama](02-first-build.md) | `check`, build DOCX, nama output, target PDF, peringatan tanpa Word. | 00 dan 01. |
| [03 - Tahap Pipeline](03-pipeline-stages.md) | 18 stage, urutan, guard, `StageResult`, artifact, workspace. | 01 dan 02. |
| [04 - Model DOCX](04-docx-model.md) | Package OPC, peta modul, helper kanonis, field, terms. | 03 dan dasar XML/ZIP. |
| [05 - Tes dan Debugging](05-testing-and-debugging.md) | Unit, integration, e2e, packaging, golden, alur debug. | 02 sampai 04. |
| [06 - Resep Perubahan](06-change-recipes.md) | Resep konten, data format, helper DOCX, stage, terms, docs. | 00 sampai 05. |

## Jalur baca yang disarankan

### Jalur pemula

1. [00 - Mulai di Sini](00-start-here.md)
2. [01 - Model Mental](01-mental-model.md)
3. [02 - Build Pertama](02-first-build.md)

Setelah tiga halaman ini, pembaca bisa membedakan sumber dan artefak, memilih
target build, serta membaca pesan error dasar.

### Jalur kontributor

1. [00 - Mulai di Sini](00-start-here.md)
2. [01 - Model Mental](01-mental-model.md)
3. [03 - Tahap Pipeline](03-pipeline-stages.md)
4. [04 - Model DOCX](04-docx-model.md)
5. [05 - Tes dan Debugging](05-testing-and-debugging.md)
6. [06 - Resep Perubahan](06-change-recipes.md)

Halaman [02 - Build Pertama](02-first-build.md) tetap dibaca sebelum mengubah
output karena build adalah cara melihat akibat perubahan.

### Jalur debug

1. [02 - Build Pertama](02-first-build.md)
2. [03 - Tahap Pipeline](03-pipeline-stages.md)
3. [05 - Tes dan Debugging](05-testing-and-debugging.md)

Gunakan [06 - Resep Perubahan](06-change-recipes.md) setelah penyebab error
ditemukan, bukan sebelum.

## Konvensi perintah

Semua perintah ditulis untuk dijalankan dari akar repo:

```bash
uv run docgen check examples/assignment-single/document.md
uv run --extra dev pytest tests/unit
```

- `uv run docgen ...` memakai entry point `docgen = "docgen.cli:main"`.
- `uv run --extra dev pytest ...` memakai dependensi pengembangan dari
  `pyproject.toml`.
- Jika perintah dijalankan dari direktori lain, tambahkan
  `--project <path-repo>` pada `uv`, misalnya
  `uv run --project <path-repo> docgen --version`.
- Output build adalah artefak. Jangan menyunting DOCX atau PDF sebagai
  sumber; perbaiki `document.md` atau data di `src/docgen/data/`.

## Cara memakai latihan

Latihan dirancang aman untuk pemula. Latihan yang mengubah berkas selalu
memakai salinan di direktori sementara, bukan `examples/` di repo. Setiap
latihan menyebut cara memeriksa hasil, misalnya exit code, baris output, atau
berkas yang harus muncul.

## Verifikasi dokumentasi

Perintah pemeriksa tautan dan registry referensi:

```bash
uv run python tools/dev/check_docs.py
```

Hasil yang diharapkan adalah `Broken: 0`. Halaman ini memakai tautan relatif
dan label dari [registry referensi](../references.md), bukan URL yang ditulis
ulang di banyak tempat.

## Tautan

- [Dokumentasi developer](../README.md)
- [Arsitektur](../architecture.md)
- [Peta repo](../repo-map.md)
- [Glosarium codebase](../glossary.md)
- [Kontrak konfigurasi](../contracts/config.md)
- [Kontrak stage](../contracts/stage-api.md)
- [Kontrak DOCX](../contracts/docx-api.md)
- [Registry referensi](../references.md)
