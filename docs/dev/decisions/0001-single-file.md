# ADR 0001: Satu `document.md` sebagai Sumber

- Status: diterima
- Tanggal: 2026-11-09

## Konteks

Naskah akademik dapat dipecah menjadi banyak berkas bab, metadata terpisah, dan
berkas sampul. Pemecahan itu mempermudah kerja paralel, tetapi menambah
konsumsi yang harus dijaga: urutan berkas, path relatif, metadata ganda, dan
kemungkinan berkas bab hilang. Agent juga harus memahami beberapa format
berkas sebelum dapat menulis satu kalimat.

## Keputusan

Satu dokumen memakai satu berkas `document.md`. Berkas itu memuat YAML front
matter dan seluruh body Markdown. Gambar, bibliografi, dan glosarium tambahan
berada di direktori yang sama. Tidak ada mode folder atau file bab terpisah.

Urutan bab tetap ditentukan `structure.yml`, bukan urutan berkas atau urutan
heading yang ditemukan. Setiap Heading 1 harus cocok dengan `body`.

## Konsekuensi

- Sumber mudah dibaca, didiff, dan dipindahkan sebagai satu unit.
- Agent hanya perlu memahami satu berkas konten.
- Perubahan urutan bab dilakukan di struktur, bukan dengan mengganti nama
  berkas.
- Dokumen besar berada dalam satu berkas; editor harus mampu menangani ukuran
  tersebut.
- Tidak ada pembagian tugas per bab di tingkat berkas. Kolaborasi dilakukan
  lewat diff atau pemisahan dokumen.
- `check` dapat membandingkan Heading 1 dengan struktur secara langsung.

## Alternatif yang ditolak

- **Banyak berkas bab.** Ditolak karena menambah konsumsi path, urutan, dan
  metadata yang harus dijaga.
- **Satu berkas tanpa struktur.** Ditolak karena urutan bab dan front matter
  menjadi tidak dapat divalidasi.
