# ADR 0004: Format dan Struktur Dipisahkan

- Status: diterima
- Tanggal: 2026-11-09

## Konteks

Aturan visual dan urutan bagian sering tercampur dalam satu konfigurasi.
Akibatnya, mengganti jenis laporan berarti menyalin nilai margin dan font, atau
mengubah urutan bab berarti menyentuh aturan tampilan. Preset terpisah juga
membuat nilai yang sama tersebar di beberapa berkas.

## Keputusan

Ada dua lapisan data:

- **Format** di `format.yml`: halaman, margin, font, heading, caption, kode,
  sitasi, dan aset visual.
- **Struktur** di `structure.yml`: front matter, body, back matter, TOC,
  daftar, penomoran, dan cover.

Keduanya memakai skema tertutup. Format tidak memuat urutan bab; struktur tidak
memuat margin atau font. Nilai penomoran ada di struktur karena berbeda antar
jenis laporan, meskipun formatnya sama.

Satu format dapat dipakai banyak struktur. Dokumen memilih keduanya lewat
front matter. Perbedaan `document.format` dan `structure.format` menghasilkan
peringatan selama format yang dipilih valid.

## Konsekuensi

- Perubahan visual tidak menyentuh naskah atau urutan bab.
- Perubahan urutan bab tidak menyentuh nilai visual.
- Format baru cukup menambah direktori format, tanpa menyalin struktur.
- Struktur baru harus mendeklarasikan front matter, body, dan penomoran.
- Validator harus memeriksa konsistensi lintas berkas.
- Tidak ada fallback ke preset lama atau nilai default tersembunyi.

## Alternatif yang ditolak

- **Satu berkas konfigurasi.** Ditolak karena mencampur dua tanggung jawab dan
  mempersulit pemakaian ulang.
- **Preset per struktur.** Ditolak karena menduplikasi nilai visual dan
  membuat sumber kebenaran ganda.
- **Nilai visual di front matter.** Ditolak karena naskah menjadi bergantung
  pada tampilan.
