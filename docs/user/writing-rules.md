# Aturan Menulis

Panduan ini merangkum aturan prosa yang dipakai repo. Aturan ini bersifat
editorial; paket AutoOffice tidak menyertakan pemeriksa prosa terpisah.

## Daftar isi

- [Kontrak yang tidak berubah](#kontrak-yang-tidak-berubah)
- [Nada](#nada)
- [Kalimat dan paragraf](#kalimat-dan-paragraf)
- [Klaim dan sitasi](#klaim-dan-sitasi)
- [Istilah asing](#istilah-asing)
- [Glosarium](#glosarium)
- [Pemeriksaan otomatis](#pemeriksaan-otomatis)
- [Presedensi](#presedensi)
- [Contoh](#contoh)

## Kontrak yang tidak berubah

1. Fakta, angka, satuan, sitasi, kutipan, nama, dan arah hubungan tidak boleh
   berubah saat menyunting prosa.
2. Jangan mengarang rujukan. Tulis `TODO-SITASI: <klaim>` bila sumber belum
   tersedia.
3. Jangan menebak istilah asing. Tulis `{{?istilah?}}` sampai diputuskan.
4. Jangan menyunting DOCX (Word) atau PDF hasil build. Perbaiki `document.md`.
5. Jangan memindahkan, menghapus, atau mengganti sitasi saat menyunting prosa.
6. Jangan memakai em dash.

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

## Klaim dan sitasi

- Beri sitasi pada setiap klaim faktual: angka, proporsi, hubungan
  antarvariabel, temuan penelitian lain, definisi yang diperdebatkan, dan isi
  kebijakan.
- Jangan menulis angka tanpa sumber. Data sendiri bersumber dari tabel,
  gambar, atau lampiran.
- Verifikasi kutipan pada sumber aslinya.
- Satu klaim cukup satu sitasi utama. Sitasi berderet hanya bila beberapa
  sumber memang dibandingkan.
- Jangan menulis daftar pustaka manual; daftar dibentuk dari `references.bib`.

## Istilah asing

- Tulis istilah asing yang belum diserap dengan miring: `*machine learning*`.
- Tulis istilah yang sudah diserap KBBI (Kamus Besar Bahasa Indonesia) dengan tegak: mikrokontroler, sensor,
  daring, unduh.
- Jangan menebak status serapan atau padanan. Bila ragu, tulis
  `{{?istilah?}}`.
- Tetapkan satu bentuk untuk satu konsep dan pakai di seluruh naskah.
- Pada kemunculan pertama, tulis kepanjangan lalu singkatan:
  `*Internet of Things*` (`IoT`).
- Nama diri, nama algoritma, nama produk, standar, lambang satuan, dan nama
  takson tidak diterjemahkan.

## Glosarium

Glosarium paket berada di
`src/autooffice/docx/data/glossary/istilah.tsv`. Tambahkan
`istilah.tsv` di samping `document.md` untuk menimpa atau menambah entri.
Format TSV (tab-separated values) memakai header `term` dan `italic`:

```tsv
term	italic
machine learning	yes
data	no
```

Aktifkan gate istilah saat build:

```bash
uv run --project <repo> autooffice build document.md --target docx --terms
```

Dengan `--terms`, stage `terms` memproses penanda `{{?istilah?}}`, menerapkan
style `IstilahAsing`, dan menulis daftar tinjauan ke
`.laporan/istilah-baru.txt`. Penanda yang belum diputuskan menjadi item
tinjauan, bukan kegagalan build. Keputusan tetap di penulis: ganti dengan
istilah yang benar atau tambahkan entri glosarium, lalu build ulang.

Tanpa `--terms`, tidak ada penerapan istilah dan tidak ada review file.
Rincian ada di [docs/dev/docx/terms.md](../dev/docx/terms.md).

## Pemeriksaan otomatis

AutoOffice tidak menyertakan pemeriksa prosa terpisah. `autooffice check`
memvalidasi struktur, front matter, aset, urutan heading, dan caption, bukan
gaya prosa. Aturan di halaman ini dipakai saat review editorial.

Untuk istilah, aktifkan `--terms` saat build. Stage `terms` menerapkan style,
memverifikasi invariant, dan menulis `.laporan/istilah-baru.txt`. Rincian ada
di [docs/dev/docx/terms.md](../dev/docx/terms.md).

## Presedensi

1. Fakta: angka, sitasi, kutipan, nama, dan arah hubungan.
2. Pedoman kampus dan format `undip-msi`.
3. Panduan ini.

## Contoh

```text
Sebelum:
Di era digital ini, tidak dapat dipungkiri bahwa pipeline build sering gagal.

Sesudah:
Pipeline build gagal pada 3 dari 10 percobaan.
```

```text
Sebelum:
Dari hasil pengujian menunjukkan bahwa waktu build turun 42%.

Sesudah:
Hasil pengujian menunjukkan bahwa waktu build turun 42%.
```

```text
Sebelum:
Sistem ini bukan cepat, tetapi boros.

Sesudah:
Sistem ini tidak cepat, tetapi boros.
```

Atribusi: kaidah Ejaan Bahasa Indonesia, Kamus Besar Bahasa Indonesia, dan Tata
Bahasa Baku Bahasa Indonesia. Sebagian kaidah dalam panduan ini diadaptasi dari
proyek naskah-id (MIT). Teks lisensi ada di `LICENSE`.
