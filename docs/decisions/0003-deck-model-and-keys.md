# ADR 0003: Model Deck dan Key

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L04, L07
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 4, 5, dan 6.2

## Konteks

deck-studio memakai model deck JSON dan key turunan yang terikat pada posisi
array. Renderer, coverage, dan sinkronisasi Google Slides membaca key yang
sama, sehingga reorder atau perubahan struktur dapat memutus mapping teks.
AutoOffice memerlukan satu model authoring YAML yang stabil, dapat
dikompilasi menjadi key datar, dan dapat dipakai oleh renderer, coverage,
serta sync tanpa menebak posisi.

## Keputusan

1. Satu berkas `deck.yaml` per deck menjadi satu-satunya input authoring.
   Struktur bertingkat memuat `meta`, `theme`, `defaults`, dan `slides`.
   Compiler menghasilkan key datar yang stabil, bukan renderer membaca YAML.
2. Slide ID ditulis eksplisit dengan pola `^s[0-9]{2,}$`, unik dalam deck,
   dan tidak di-renumber saat slide dipindahkan. Nomor halaman mengikuti
   posisi tampilan, bukan ID.
3. Block ID memakai pola `^[a-z][a-z0-9_]*$`, maksimal 32 karakter, unik
   dalam satu slide, dan tidak mengandung titik. Block boleh dipindahkan di
   dalam slide tanpa mengubah key.
4. Key datar memakai bentuk `<slide_id>.<block_id>.<leaf>` untuk block dan
   `<slide_id>.<leaf>` untuk slide. Indeks selalu 1-based dan memakai bentuk
   `itemN`, `catN`, `seriesN`, `valueN`, `rN`, `cN`, `hN`.
5. KeyBinding menyimpan `key`, `slide_id`, `block_id`, `leaf`, `kind`,
   `sync`, `yaml_path`, `value`, dan `plain_text`. Pull/apply memakai
   `yaml_path`, bukan menebak dari string key.
6. Duplikasi key, ID, atau binding yang tidak cocok dengan schema block
   ditolak compiler. Compiler deterministik dan tidak memakai hash acak.
7. Block type v1 hanya `text`, `bullets`, `image`, `table`, `chart`, `code`,
   `quote`, `diagram`, `divider`, `spacer`, dan `metric`. Tidak ada
   `callout`.
8. Nama field, leaf, dan slot bagian 4 dan 6 dibekukan apa adanya (A17).
   Perubahan setelah F0 memerlukan ADR dan rebase lane.

## Konsekuensi

- Reorder slide tidak mengubah key. Menyisipkan slide memakai ID baru yang
  belum dipakai, misalnya `s25`, bukan menggeser ID lain.
- Mengganti ID slide atau block memerlukan migrasi key dan memutus mapping
  sync Google Slides lama. Konsekuensi ini harus dicatat di dokumentasi
  migrasi.
- Urutan ID tidak mencerminkan urutan tampil setelah reorder. Ini disengaja,
  bukan error.
- Key duplikat ditolak dengan pesan yang menyebut kedua slide atau block.
- Panjang key maksimal 160 karakter. Schema harus disederhanakan, bukan
  dipotong diam-diam.
- Coverage, renderer, dan sync memakai KeyBinding yang sama. Tidak ada
  key yang dibuat ulang oleh renderer.
- Block type baru memerlukan ADR dan perubahan block registry.

## Alternatif yang ditolak

- Menurunkan ID dari posisi array. Ditolak karena reorder dan insert memutus
  key serta sync.
- Mempertahankan model JSON deck-studio. Ditolak karena tidak satu YAML dan
  terikat renderer browser.
- Memakai nested key YAML sebagai key renderer. Ditolak karena sync remote
  membutuhkan key datar yang stabil.
- Auto-renumber slide setelah reorder. Ditolak karena memutus mapping dan
  membuat diff tidak deterministik.
- Mengizinkan leaf bebas atau `callout`. Ditolak karena schema harus tertutup
  dan block type dibatasi.

## Status

Diterima. Perubahan schema, ID, grammar key, atau block type memerlukan ADR
baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
