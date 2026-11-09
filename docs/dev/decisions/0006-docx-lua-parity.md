# ADR 0006: Paritas Perilaku Filter Lua Lama

- Status: diterima
- Tanggal: 2026-11-09

## Konteks

Filter Lua lama menangani sampul, penomoran heading, TOC, daftar, halaman
pengesahan, abstrak, page break, dan formatting heading. Filter itu juga
memiliki bug yang sudah dikenal, antara lain judul dua kata yang panjang,
daftar gambar/tabel kosong, dan metadata skalar yang terpecah. Menghapus
perilaku secara diam-diam akan mengubah keluaran dan merusak naskah yang sudah
ada.

## Keputusan

Perilaku filter Lua lama diport penuh ke stage Python, termasuk perbaikan bug.
Cakupan port:

- sampul dan identitas;
- penomoran Heading 1, 2, dan 3;
- template pengesahan dan pernyataan;
- kata pengantar, abstrak, dan kata kunci;
- page break dan section break;
- TOC native;
- formatting inline pada heading;
- spacer eksplisit.

Pipeline tidak memakai filter Lua. Semua perilaku dijalankan sebelum atau
sesudah Pandoc sesuai tanggung jawab stage.

## Konsekuensi

- Keluaran lama dapat dibandingkan dengan golden test.
- Bug lama tidak ikut dipertahankan.
- Setiap perilaku harus memiliki tes dan, bila menyentuh Word, manual spike.
- Perubahan perilaku yang disengaja harus dicatat di ADR atau dokumentasi.
- Parameter format dibaca dari `format.yml`, bukan dari default filter.

## Alternatif yang ditolak

- **Mempertahankan filter Lua.** Ditolak karena sulit diuji, sulit menjaga
  satu load/save, dan mencampur logika Markdown dengan Word.
- **Menghapus perilaku yang dianggap jarang dipakai.** Ditolak karena
  perubahan keluaran tidak dapat diprediksi dan merusak kompatibilitas.
- **Port sebagian.** Ditolak karena perilaku yang tersisa akan bergantung pada
  dua mesin yang berbeda.
