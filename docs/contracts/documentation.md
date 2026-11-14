# Kontrak Dokumentasi

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 12.9, 18.11, dan keputusan L18.
Pemilik kontrak: integration owner dan docs owner.

## Tujuan

Kontrak ini membekukan struktur, navigasi, dan aturan isi dokumentasi
AutoOffice. Dokumentasi harus bisa dipahami tanpa membaca plan dan tanpa
menebak urutan baca.

## Invarian

1. Dokumentasi berada di lima direktori:
   - `docs/user` untuk pengguna dan penulis.
   - `docs/dev` untuk developer dan kontributor.
   - `docs/learn` untuk materi konsep bertahap.
   - `docs/contracts` untuk kontrak normatif.
   - `docs/decisions` untuk ADR.
2. `docs/README.md` adalah indeks utama dan wajib menautkan
   `docs/user/README.md`, `docs/dev/README.md`, `docs/learn/README.md`,
   `docs/contracts/README.md`, dan `docs/decisions/README.md`. Setiap halaman
   terdaftar di indeks direktori atau indeks utamanya.
3. Setiap halaman punya tepat satu judul level 1.
4. Setiap code fence punya language. Perintah `autooffice` yang
   didokumentasikan harus ada di kontrak CLI.
5. Semua tautan relatif harus resolve. Tautan ke nama repo lama dilarang di
   docs user. Dokumen migrasi historis dikecualikan sesuai A24.
6. Kontrak di `docs/contracts` bersifat normatif dan tidak diduplikasi di
   docs user, dev, atau learn. Dokumen lain merujuk kontrak, bukan menyalin
   isinya.
7. Tidak ada tutorial per fitur untuk v1. Dokumentasi v1 berisi quickstart,
   model authoring, CLI, konsep, kontrak, dan troubleshooting.
8. Halaman yang usang ditandai `superseded` atau dihapus. Arsip berada di
   `docs/dev/archive/**` dan tidak boleh menjadi acuan aktif.
9. Navigasi harus jelas dari `docs/README.md` menuju indeks direktori, lalu
   ke halaman konkret. Setiap halaman kontrak menautkan balik ke plan.
10. Docs checker `python tools/quality/check_docs.py` wajib keluar 0 untuk
    dokumentasi aktif. Checker memeriksa tautan relatif, TOC halaman lebih
    dari 150 baris, dan registry referensi.
11. Halaman lebih dari 150 baris wajib punya `## Daftar Isi` dengan anchor
    yang valid menurut slug GitHub.
12. Dokumentasi tidak boleh mengklaim perilaku yang belum ada di kontrak atau
    plan. Label `F0`, `rencana`, dan `historis` dipakai bila relevan.

## Struktur direktori

```text
docs/
  README.md
  user/
    README.md
  dev/
    README.md
  learn/
    README.md
  contracts/
    README.md
    cli.md
    docx.md
    design-token.md
    coverage.md
    test-quality.md
    documentation.md
    ownership.md
    copy.md
    transcript.md
    google-state.md
  decisions/
    README.md
    0001-assumption-closure.md
    0002-scope-and-package.md
    0003-deck-model-and-keys.md
    0004-layouts-and-rendering.md
    0005-google-sheets-and-pdf.md
    0006-quality-migration-and-humanizer.md
```

Daftar di atas adalah kontrak minimum F0, bukan daftar lengkap kontrak lane
lain. Kontrak inti deck berada di direktori yang sama dan tetap dimiliki
lane-nya.

## Contoh

```text
docs/README.md
  -> contracts/README.md
     -> contracts/cli.md
        -> ../../AUTO_OFFICE_PLAN.md
  -> decisions/README.md
     -> decisions/0001-assumption-closure.md
```

Setiap panah harus berupa tautan relatif yang resolve dan diuji oleh docs
checker.

## Pemetaan acceptance

| Invarian | Bukti |
| --- | --- |
| Lima direktori dan indeks | Review `docs/README.md` dan `docs/learn/README.md`; `check_docs.py`. |
| Tautan valid dan TOC | `python tools/quality/check_docs.py` keluar 0. |
| Judul dan code fence | Docs checker dan review F2-DOCS. |
| Tidak ada tutorial per fitur | Review struktur `docs/user` dan `docs/learn`. |
| Kontrak tidak diduplikasi | Review docs user/dev/learn; bagian 12.9. |
| Perintah ada di CLI | Bandingkan dengan `docs/contracts/cli.md`; docs checker. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
