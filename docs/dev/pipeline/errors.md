# Error dan Exit Code

Halaman ini menjelaskan kegagalan pipeline dan pemetaan exit code. Kontrak
error ada di [contracts/stage-api.md](../contracts/stage-api.md).

Semua error pipeline melempar subclass `DocgenError`. Stage yang melempar
exception tak dikenal dibungkus `StageError` dengan nama stage, path, dan
cause.

## Exit code

| Exit | Arti |
| ---: | --- |
| 0 | Sukses |
| 1 | Error input, konfigurasi, stage, tool, output, atau Word/PDF |
| 2 | Kesalahan pemakaian CLI |
| 3 | `reconcile`: ada perubahan manual |
| 4 | `reconcile`: pelanggaran paragraf terlindungi |
| 130 | Dibatalkan pengguna |

## Halaman terkait

- [overview.md](overview.md) untuk alur eksekusi.
- [options.md](options.md) untuk target yang dapat gagal.
- [outputs.md](outputs.md) untuk kegagalan penulisan.
- [../adeu-integration.md](../adeu-integration.md) untuk exit code `reconcile`.
