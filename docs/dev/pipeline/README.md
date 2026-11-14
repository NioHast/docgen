# Pipeline

Folder ini menjelaskan cara `Pipeline` menjalankan stage, memilih opsi build,
menulis output, dan melaporkan error. Kontrak mengikat ada di
[contracts/docx.md](../../contracts/docx.md).

## Halaman

| Halaman | Isi |
| --- | --- |
| [overview.md](overview.md) | Model eksekusi, satu load dan satu save, Adeu hook, idempotensi, dan logging. |
| [stages.md](stages.md) | Urutan 18 stage dan guard yang wajib ditegakkan. |
| [options.md](options.md) | Flag `autooffice build` dan matriks target per platform. |
| [outputs.md](outputs.md) | `report_name`, lokasi output, dan artefak pengguna. |
| [artifacts.md](artifacts.md) | Workspace, artefak antara, dan penulisan atomic. |
| [errors.md](errors.md) | Hierarki error dan exit code. |

## Urutan baca

1. [overview.md](overview.md) untuk model eksekusi.
2. [stages.md](stages.md) untuk urutan dan guard.
3. [options.md](options.md) dan [outputs.md](outputs.md) untuk pemakaian CLI.
4. [artifacts.md](artifacts.md) dan [errors.md](errors.md) untuk diagnosis.

Dokumen terkait: [arsitektur](../architecture.md),
[lapisan DOCX](../docx/README.md), dan
[integrasi Adeu](../adeu-integration.md).
