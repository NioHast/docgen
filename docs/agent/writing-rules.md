# Aturan Menulis

Ringkasan ini bukan pengganti panduan lengkap. Sumber aturan perilaku ada di
[`writing/guide.md`](../../writing/guide.md), sedangkan pola pemeriksa dibaca
`tools/check_prose.py` dari [`writing/rules.yml`](../../writing/rules.yml).

## Kontrak yang tidak berubah

1. Fakta, angka, satuan, sitasi, kutipan, nama, dan arah hubungan tidak boleh
   berubah saat menyunting prosa.
2. Jangan mengarang rujukan. Tulis `TODO-SITASI: <klaim>` bila sumber belum
   tersedia.
3. Jangan menebak istilah asing. Tulis `{{?istilah?}}`; build berhenti sampai
   penanda itu diputuskan.
4. Jangan menyunting `Laporan.docx`, `Laporan.pdf`, atau `reference.docx`.
   Perbaiki Markdown sumber.
5. Jangan memindahkan, menghapus, atau mengganti sitasi saat menyunting prosa.

## Nada

- Tulis kalimat berita, bukan sapaan atau ajakan kepada pembaca.
- Awali bagian dengan unsur konkret: angka, nama tempat, lembaga, atau
  peristiwa bertanggal.
- Samakan kekuatan klaim dengan bukti. Pakai `berhubungan` untuk korelasi dan
  `berpengaruh` hanya bila ada uji yang mendukung.
- Jangan menilai karya sendiri dengan kata seperti `inovatif`, `efektif`, atau
  `menarik`.
- Hapus kata penekan yang tidak mengubah makna, misalnya `sangat`,
  `benar-benar`, `tentu saja`, `pada dasarnya`, dan `secara umum`.

## Kalimat dan paragraf

- Awali kalimat dengan subjek berupa nomina atau frasa nomina.
- Jaga kalimat di bawah 35 kata dan pakai satu predikat utama.
- Pakai `di mana` hanya sebagai kata tanya. Sebagai perangkai, pilih `yang`,
  `tempat`, atau `saat`.
- Ganti `hal ini` dan `hal tersebut` dengan nomina yang ditunjuk.
- Tulis satu gagasan per paragraf. Panjang wajar 3 sampai 7 kalimat atau 80
  sampai 150 kata; paragraf di atas 200 kata dipecah.
- Hubungkan paragraf lewat isi, bukan dengan `Selain itu`, `Oleh karena itu`,
  atau `Lebih lanjut` di awal setiap paragraf.
- Gunakan butir hanya untuk prosedur, kriteria, atau rumusan.

## Klaim, sitasi, dan istilah

- Beri sitasi pada setiap klaim faktual: angka, proporsi, hubungan
  antarvariabel, temuan penelitian lain, definisi yang diperdebatkan, dan isi
  kebijakan.
- Jangan menulis angka tanpa sumber. Data sendiri bersumber dari tabel,
  gambar, atau lampiran.
- Verifikasi kutipan pada sumber aslinya.
- Tulis istilah asing yang belum diserap dengan miring: `*machine learning*`.
- Tulis istilah yang sudah diserap KBBI dengan tegak: mikrokontroler, sensor,
  daring.
- Tetapkan satu bentuk untuk satu konsep dan pakai di seluruh naskah.
- Jangan memakai em dash; pemeriksa melaporkannya sebagai `EJ-11`.

## Menjalankan pemeriksa

```bash
python tools/check_prose.py document.md
python tools/check_prose.py chapters/*.md
make lint-prosa
```

Pilihan lain:

```bash
python tools/check_prose.py --banding asli.md hasil.md
python tools/check_prose.py --abaikan SG-04,KL-01 document.md
python tools/check_prose.py --self-test
```

Label `K` memblokir dan membuat kode keluar `1`. Label `G` dan `AI` hanya
memberi anjuran. `--banding` memeriksa angka, sitasi, dan kutipan antara dua
versi. `--self-test` menjalankan kasus uji mandiri pemeriksa.

Pemeriksaan caption dijalankan terpisah:

```bash
python tools/check_captions.py document.md
```

Glosarium diterapkan ke DOCX oleh `tools/terms.py`. Penanda `{{?istilah?}}`
yang tersisa akan menghentikan build. Untuk memeriksa DOCX final:

```bash
python tools/terms.py verify Laporan.docx --glossary writing/istilah.tsv
```

Baca [`writing/guide.md`](../../writing/guide.md) untuk alasan, contoh, dan
presedensi aturan. Bila pemeriksa dan panduan bertentangan, berhenti dan
laporkan; jangan memilih diam-diam.
