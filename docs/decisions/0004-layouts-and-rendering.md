# ADR 0004: Layout dan Rendering

- Status: diterima
- Tanggal: 2026-11-14
- Pemilik: integration owner
- Keputusan terkunci: L05, L06, L08, L10, L12, L15
- Rujukan: `AUTO_OFFICE_PLAN.md` bagian 6, 7, 8.3, 8.6, dan 11

## Konteks

deck-studio memiliki 21 layout, 12 theme, renderer HTML/Reveal, PptxGenJS,
dan beberapa layout memakai koordinat persen atau marks. AutoOffice harus
mempertahankan visual language deck-studio tanpa membawa template `.pptx`
eksternal, absolute positioning di authoring, HTML, atau renderer browser.
Font harus tertanam di PPTX, chart dan table harus native, dan theme `hitam`
harus jelas bukan dark theme.

## Keputusan

1. Design token diporting dari deck-studio ke `src/autooffice/design/data/`.
   Renderer membaca token yang sudah di-resolve; tidak ada hex, ukuran font,
   margin, gutter, atau radius hardcoded di renderer.
2. Theme produk hanya dua: `indigo` sebagai default dan `hitam` sebagai theme
   terang dengan aksen hitam. `hitam` memakai kanvas terang, aksen `#111827`,
   cover gradient `#111827` -> `#0B1220` -> `#000000`; palet `malam` tidak
   dipakai.
3. Warna chart memakai `chartSeries` empat warna yang lolos kontras 3:1:
   `indigo` `#4F46E5`, `#0F766E`, `#B45309`, `#BE123C`; `hitam` `#111827`,
   `#374151`, `#4B5563`, `#6B7280`. Chart dibatasi empat slot warna.
4. Tipografi deck memakai `Plus Jakarta Sans` weight 400, 600, 700, dan 800.
   TTF dibundel, dipakai test, dan ditanam di PPTX lewat post-processing
   OOXML. DOCX tidak memakai font ini.
5. Katalog layout v1 memuat 19 preset, termasuk `section`, ditambah `custom`.
   Layout `image-annotated`, `image-figure`, dan `table-long` tidak didukung.
6. Preset memiliki rows internal yang tidak ditulis author. Hanya `custom`
   memakai `rows` eksplisit. Grid 12 kolom, `span` 1-12, tanpa x/y absolut,
   tinggi mengikuti isi, dan gutter dari token. Overflow menggagalkan build.
7. PPTX dibangun dengan `python-pptx` dari token. Table, chart, image, notes,
   dan alt text native. Tidak ada base `.pptx` eksternal, SmartArt, video,
   audio, animasi, atau transisi.
8. Mermaid dirender oleh external `mmdc` menjadi PNG. Tidak ada native
   Mermaid shape dan tidak ada fallback teks.
9. Larangan desain bagian 11.5 berlaku: tidak ada gradient dekoratif selain
   cover, glow, glass, blur, blob 3D, pola acak, aksen body/caption/footer,
   atau font di luar design system.

## Konsekuensi

- Layout engine mengukur teks dengan TTF yang sama, memberi safety margin,
  tidak melakukan shrink, dan menggagalkan overflow sebelum render.
- Setiap preset memerlukan contract test slot, golden semantic, golden
  visual indigo, build minimal hitam, dan bukti tanpa overflow.
- Font embedding harus gagal keras bila PPTX tidak valid. Build tidak boleh
  mengirim PPTX tanpa font secara diam-diam.
- Chart native wajib di PPTX dan PDF; chart tidak boleh menjadi gambar.
- Table native wajib dan tidak boleh diubah menjadi gambar untuk PDF.
- Tidak ada dark mode v1. `hitam` adalah theme aksen, bukan tema gelap.
- Layout lane hanya menambah preset dan test unik; registry dimiliki
  integration owner.

## Alternatif yang ditolak

- Mendukung semua 21 layout deck-studio. Ditolak karena tiga layout memakai
  marks/koordinat dan menambah kontrak baru tanpa kebutuhan acceptance.
- Memakai template `.pptx` eksternal. Ditolak oleh L05.
- Mempertahankan HTML/Reveal atau PptxGenJS. Ditolak karena output browser
  bukan target dan font embedding membutuhkan OOXML.
- Membuat chart sebagai gambar. Ditolak karena chart harus editable dan
  native.
- Memakai 12 theme atau dark mode. Ditolak karena v1 hanya dua theme.
- Mengizinkan absolute positioning di YAML. Ditolak karena authoring harus
  memakai grid dan rows.

## Status

Diterima. Perubahan katalog layout, token, theme, font, atau mekanisme
renderer memerlukan ADR baru.

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
