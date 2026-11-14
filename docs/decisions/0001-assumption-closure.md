# ADR 0001: Penutupan Asumsi F0

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 19

## Konteks

F0 tidak boleh lulus selama asumsi A1-A25 di bagian 19 plan belum ditutup.
Sebagian asumsi memengaruhi schema, layout, CLI, Google, PDF, dan acceptance.
Menunda jawaban akan memblokir seluruh lane fitur dan memaksa lane menebak
kontrak. Plan mencatat bahwa A1, A5, dan A25 sudah dikonfirmasi pengguna per
2026-11-14. Asumsi lain belum punya jawaban eksplisit.

## Keputusan

1. A1, A5, dan A25 dikonfirmasi oleh pengguna.
2. A2-A4 dan A6-A24 ditutup dengan default plan. Default tersebut menjadi
   keputusan yang mengikat untuk F0, bukan asumsi implisit.
3. Penutupan ini dicatat untuk kelulusan F0-CONTRACTS. Tidak ada asumsi yang
   masih menjadi gate F0.
4. Setiap perubahan atas keputusan di tabel ini memerlukan ADR baru dan
   pembaruan kontrak terkait.

| ID | Asumsi ringkas | Status | Dasar |
| --- | --- | --- | --- |
| A1 | Slide ID eksplisit dan stabil, tidak di-renumber saat reorder. | Dikonfirmasi pengguna | Bagian 5.3 |
| A2 | Preset layout punya rows internal; hanya `custom` memakai `rows`. | Ditutup dengan default plan | Bagian 6.4 |
| A3 | Sync memakai `build --target slides --sync push/pull/diff/apply`. | Ditutup dengan default plan | Bagian 10.3, 10.7 |
| A4 | Output, state, cache, dan review mengikuti bagian 10.4. | Ditutup dengan default plan | Bagian 10.4 |
| A5 | `hitam` adalah kanvas terang dengan aksen `#111827`, bukan dark theme. | Dikonfirmasi pengguna | Bagian 11.2 |
| A6 | Font TTF Plus Jakarta Sans 400/600/700/800 dibundel; tanpa italic. | Ditutup dengan default plan | Bagian 11.4 |
| A7 | Gambar `.png`, `.jpg`, `.jpeg`, `.webp`; WebP ke PNG; SVG ditolak. | Ditutup dengan default plan | Bagian 4.8, 11 |
| A8 | Slides memakai staging PPTX dengan placeholder chart. | Ditutup dengan default plan | Bagian 8.3, 8.4 |
| A9 | File dimiliki akun OAuth; scope `drive.file`, `presentations`, `spreadsheets`. | Ditutup dengan default plan | Bagian 9.7 |
| A10 | Sync teks mencakup teks slide, table cell, notes, dan source. | Ditutup dengan default plan | Bagian 8.4 |
| A11 | Layout `image-annotated`, `image-figure`, `table-long` tidak didukung. | Ditutup dengan default plan | Bagian 6.3 |
| A12 | Flag lama docgen `--no-manifest`, `--no-adeu`, `--allow-missing-word` dihapus. | Ditutup dengan default plan | Bagian 16.1 |
| A13 | Coverage 100% line dan branch dengan exclusion terbatas. | Ditutup dengan default plan | Bagian 12.3 |
| A14 | `background` adalah layout konteks tiga poin, bukan preview resep latar. | Ditutup dengan default plan | Bagian 6.2 |
| A15 | Setiap push Slides membuat presentasi baru dan menyimpan ID aktif. | Ditutup dengan default plan | Bagian 8.4 |
| A16 | `source` hanya di level slide, bukan per block. | Ditutup dengan default plan | Bagian 4.9, 5.6 |
| A17 | Nama field dan slot bagian 4 dan 6 dibekukan apa adanya. | Ditutup dengan default plan | Bagian 4, 6 |
| A18 | Mypy dan import-linter dibekukan di F0 setelah audit stub. | Ditutup dengan default plan | Bagian 12.4 |
| A19 | `apply` menulis `.autooffice/review/<stem>.applied.yaml`, bukan menimpa sumber. | Ditutup dengan default plan | Bagian 10.7 |
| A20 | `source.url` adalah hyperlink, bukan key teks. | Ditutup dengan default plan | Bagian 4.9 |
| A21 | Table memakai header native baris pertama dan tanpa merged cell. | Ditutup dengan default plan | Bagian 8.3, 8.4 |
| A22 | `.autooffice/**` dan `.autooffice-build/**` tidak di-track Git; keduanya di-ignore. | Ditutup dengan default plan | Bagian 9.6 |
| A23 | `deck-studio` diarsipkan atau dihapus; `docgen` di-rename menjadi `autooffice`. | Ditutup dengan default plan | Bagian 16.4 |
| A24 | Dokumen migrasi boleh historis; larangan nama lama berlaku untuk runtime dan docs user. | Ditutup dengan default plan | Bagian 16.3, 19 |
| A25 | Chart maksimal empat slot warna dengan `chartSeries` chart-safe 3:1. | Dikonfirmasi pengguna | Bagian 11.2 |

## Konsekuensi

- Lane fitur boleh bergantung pada default A2-A4 dan A6-A24 tanpa menunggu
  jawaban tambahan.
- A1, A5, dan A25 tetap menjadi keputusan pengguna dan tidak boleh diubah
  oleh lane.
- A17 membekukan schema dan slot. Perubahan setelah F0 memerlukan ADR dan
  rebase lane.
- A12 menghapus flag lama tanpa shim. Dokumentasi dan CLI baru tidak boleh
  menyebut flag tersebut sebagai opsi.
- A13 mengikat gate coverage dan exclusion policy.
- A15 membuat setiap push menghasilkan presentasi baru; cleanup tidak
  otomatis.
- A22 mewajibkan `.autooffice/**` dan `.autooffice-build/**` masuk ignore
  sejak scaffold.
- A24 memberi pengecualian historis hanya untuk dokumen migrasi.

## Alternatif yang ditolak

- Menunda penutupan sampai pemilik menjawab. Ditolak karena F0 adalah hard
  barrier dan tidak boleh melewati gate.
- Memperlakukan default sebagai asumsi implisit. Ditolak karena bagian 19.2
  melarang asumsi implisit untuk keputusan yang memengaruhi acceptance.
- Membuka ulang asumsi per lane. Ditolak karena menyebabkan kontrak berbeda
  antar lane.

## Status

Diterima. Penutupan dicatat untuk F0. Perubahan memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
