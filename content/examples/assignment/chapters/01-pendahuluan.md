# Pendahuluan

## Latar Belakang

Laporan akademik menuntut struktur, penomoran, dan sitasi yang konsisten. Penulisan langsung di pengolah kata sering membuat format berpindah saat dokumen disunting ulang. Pemisahan antara naskah dan presentasi mengurangi masalah tersebut: naskah ditulis dalam Markdown, lalu dikonversi oleh Pandoc [@pandoc2024] menjadi DOCX atau PDF.

Pendekatan ini juga memudahkan peninjauan melalui Git. Perubahan teks tampil sebagai diff baris, bukan sebagai berkas biner yang tidak terbaca. Mesin keluaran dapat diganti tanpa menulis ulang isi laporan.

## Rumusan Masalah

1. Bagaimana menyusun naskah tugas dalam struktur bab yang baku?
2. Bagaimana memastikan format, metadata, dan sitasi konsisten saat build?
3. Bagaimana memisahkan konten dari aturan visual agar mudah dipakai ulang?

## Tujuan

Tujuan tugas ini adalah menghasilkan contoh laporan yang dibangun dari struktur `assignment`, format `undip-msi`, dan pipeline build yang sudah ada.
