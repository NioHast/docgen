# ADR 0003: Orkestrasi Pipeline di Python

- Status: diterima
- Tanggal: 2026-11-09

## Konteks

Pipeline lama mengandalkan rangkaian perintah shell dan filter Lua. Urutan
tahap tersebar di beberapa berkas, sulit diuji tanpa menjalankan seluruh
build, dan perilaku platform bergantung pada shell. Setiap tahap juga dapat
membaca dan menulis DOCX sendiri, sehingga invariant satu pass tidak dapat
ditegakkan.

## Keputusan

Orkestrasi dipindahkan ke Python di `src/docgen/`. `Pipeline` memiliki urutan
stage kanonik, `StageContext`, `Workspace`, `ArtifactStore`, dan `BuildReport`.
Setiap stage mengimplementasikan `run(ctx)` dan hanya memutasi part yang
dideklarasikan.

Urutan dijaga oleh `CANONICAL_ORDER` dan guard keras. Stage yang salah urutan,
duplikat, atau memutasi part tidak dikenal menggagalkan pipeline.

## Konsekuensi

- Urutan dan invariant dapat diuji tanpa Word.
- Satu package dimuat dan disimpan oleh pipeline, bukan oleh stage.
- Error memiliki tipe, kode, stage, dan path yang konsisten.
- Platform Windows dan Debian memakai jalur kode yang sama; perbedaan hanya
  pada adapter Word dan target.
- Semua kontributor harus memahami kontrak stage sebelum menambah tahap.
- Perilaku lama harus diport, bukan dipanggil ulang lewat shell.

## Alternatif yang ditolak

- **Mempertahankan orkestrasi shell.** Ditolak karena sulit diuji, sulit
  membawa invariant package, dan bergantung pada platform.
- **Satu skrip monolitik.** Ditolak karena tidak memiliki batas mutasi dan
  sulit diuji per tahap.
- **Orkestrasi di filter Lua.** Ditolak karena Word dan ZIP tidak dapat
  dikelola dengan aman dari dalam filter.
