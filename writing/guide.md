# Panduan Menulis Naskah

Panduan ini berlaku untuk seluruh naskah berbahasa Indonesia di proyek ini.
Aturan perilaku ada di `writing/rules.yml`. Pemeriksa membaca berkas itu dan
tidak menyimpan salinan pola. Panduan ini menjelaskan alasan, urutan kerja, dan
cara membaca temuan.

## 1. Kontrak yang tidak berubah

1. Fakta tidak berubah: angka, satuan, sitasi, kutipan, nama, dan arah hubungan.
2. Jangan mengarang rujukan. Tulis `TODO-SITASI: <klaim>` bila sumber belum ada.
3. Jangan menebak istilah. Tulis `{{?istilah?}}`; build menolak penanda ini
   sampai diputuskan.
4. Jangan menyunting `Laporan.docx`, `Laporan.pdf`, atau `reference.docx`.
   Perbaiki sumber Markdown.
5. Jangan memindahkan, menghapus, atau mengganti sitasi saat menyunting prosa.

## 2. Nada

1. Tulis kalimat berita. Jangan menyapa pembaca, mengajak, atau memberi
   instruksi kepada pembaca.
2. Mulai bagian dengan unsur konkret: angka, nama tempat, nama lembaga, atau
   peristiwa bertanggal. Hapus pembuka yang tidak memuat satu pun unsur itu.
3. Samakan kekuatan klaim dengan bukti. Tulis `berhubungan` untuk korelasi dan
   `berpengaruh` hanya bila ada uji yang mendukung.
4. Jangan menilai karya sendiri dengan kata seperti `inovatif`, `efektif`, atau
   `menarik`. Ganti penilaian dengan ukuran yang bisa diperiksa.
5. Hapus kata penekan yang tidak mengubah makna. Contoh: `sangat`,
   `benar-benar`, `tentu saja`, `pada dasarnya`, `secara umum`.

## 3. Kalimat

1. Awali kalimat dengan subjek berupa nomina atau frasa nomina. Pola
   `Dari hasil analisis menunjukkan ...` kehilangan subjek dan dilaporkan
   sebagai `KE-01`.
2. Jangan memulai kalimat dengan kata depan lalu langsung memasang verba.
   Jadikan frasa itu subjek, atau pertahankan kata depan dan pakai bentuk pasif.
3. Jaga kalimat di bawah 35 kata (`KL-01`). Hitung kata, bukan klausa.
4. Pakai satu predikat utama per kalimat. Jangan menumpuk lebih dari dua klausa
   `yang`.
5. Pakai `di mana` hanya sebagai kata tanya. Sebagai perangkai, pilih `yang`,
   `tempat`, atau `saat` (`AI-14`).
6. Ganti `hal ini` dan `hal tersebut` dengan nomina yang ditunjuk (`AI-15`).
7. Pasif `di-` boleh di bab Metode. Jangan memaksakan aktif dan jangan menumpuk
   pasif.

## 4. Paragraf dan butir

1. Tulis satu gagasan per paragraf. Kalimat pertama menyatakan gagasan itu,
   bukan latar belakang umum.
2. Panjang wajar 3-7 kalimat atau 80-150 kata. Paragraf di atas 200 kata
   dipecah.
3. Jangan membuat rangkaian paragraf satu kalimat. Satu paragraf satu kalimat
   hanya boleh sekali sebagai penekanan atau peralihan.
4. Akhiri paragraf dengan implikasi atau lanjutan. Hapus
   `Dengan demikian dapat disimpulkan bahwa ...` di akhir paragraf.
5. Hubungkan paragraf lewat isi. Jangan mengandalkan `Selain itu`,
   `Oleh karena itu`, atau `Lebih lanjut` di awal setiap paragraf (`AI-16`,
   `AI-17`).
6. Sampaikan argumen dalam paragraf. Butir hanya untuk prosedur, kriteria, atau
   rumusan.
7. Hindari butir berlabel tebal yang mengulang labelnya sendiri (`AI-20`).
   Contoh yang dilaporkan: `- **Kecepatan Tinggi**: sistem ini cepat`.
   Pemeriksa melaporkan pola ini bila muncul minimal dua kali dalam satu berkas.
8. Label prosedur dan definisi dikecualikan. Contoh label: `Langkah`, `Seksi`,
   `Kriteria`, dan `Berkas`. Penjelasan yang dimulai dengan penanda definisi
   seperti `adalah` atau `merupakan` juga dikecualikan. Daftar lengkap ada di
   `writing/rules.yml`.

## 5. Klaim dan sitasi

1. Beri sitasi pada setiap klaim faktual: angka, proporsi, hubungan
   antarvariabel, temuan penelitian lain, definisi yang diperdebatkan, dan isi
   kebijakan.
2. Jangan menulis angka tanpa sumber. Untuk data sendiri, sumbernya tabel,
   gambar, atau lampiran. Untuk data orang lain, sumbernya publikasi.
3. Jangan mengarang rujukan, penulis, tahun, jurnal, volume, halaman, atau
   `DOI`. Bila belum terverifikasi, tulis `TODO-SITASI: <klaim>`.
4. Verifikasi kutipan pada sumber aslinya. Kemiripan topik tidak cukup.
5. Ikuti gaya sitasi proyek. Bila belum ada, pakai gaya `APA 7`. Pakai `dkk.`
   dan `hlm.` dalam naskah berbahasa Indonesia.
6. Satu klaim cukup satu sitasi utama. Sitasi berderet hanya boleh bila
   beberapa sumber memang dibandingkan.

## 6. Istilah asing

1. Tulis istilah asing yang belum diserap dengan miring: `*machine learning*`,
   `*grounded theory*`, `*in vitro*`.
2. Tulis istilah yang sudah diserap `KBBI` dengan tegak: mikrokontroler,
   sensor, prevalensi, daring, unduh.
3. Jangan menebak status serapan atau padanan. Bila ragu, tulis `{{?istilah?}}`.
4. Jangan menerjemahkan nama diri, nama algoritma, nama produk, standar, lambang
   satuan, dan nama takson. Contoh: `*Random Forest*`, `ISO 9001`, `10 V`,
   `*Oryza sativa*`.
5. Tetapkan satu bentuk untuk satu konsep dan pakai di seluruh naskah.
6. Pada kemunculan pertama, tulis kepanjangan lalu singkatan:
   `*Internet of Things*` (`IoT`).
7. Untuk kata asing berimbuhan, pakai tanda hubung (`di-*input*`) atau
   padanannya (`dimasukkan`).

## 7. Daftar kode

| Keluarga | Kode | Isi | Label |
| --- | --- | --- | --- |
| Kalimat efektif | `KE-01`–`KE-17` | subjek, pleonasme, perangkai, perbandingan | K |
| Nominalisasi dan klaim | `NM-01`, `KK-01` | verba penopang dan kekuatan klaim | G |
| Singkatan dan akronim | `SG-01`–`SG-06` | tanda hubung, titik, jamak, kepanjangan | K/G |
| Ejaan dan tanda baca | `EJ-01`–`EJ-11` | di/ke, bentuk terikat, angka, satuan, koma, em dash | K |
| Klise mesin dan kalke | `AI-01`–`AI-20` | pembuka kosong, kalke, penghubung berulang, butir berlabel | `AI` |
| Kata baku | `KB-01` | kamus kata tidak baku | K |
| Kalimat panjang | `KL-01` | lebih dari 35 kata | G |
| Penanda istilah | `IS-01` | `{{?istilah?}}` belum diputuskan | K |

## 8. Yang tidak boleh dikoreksi berlebihan

1. Pasif `di-` di bab Metode.
2. Hedging seperti `dapat`, `cenderung`, atau `diduga` bila buktinya belum kuat.
3. `signifikan` yang disertai nilai uji, misalnya `p < 0,05`.
4. Kutipan langsung, nama diri, nama tempat, dan istilah yang dipertahankan.
5. `bukan hanya ... tetapi juga ...` dan `bukan ... melainkan ...` adalah
   pasangan baku. Jangan mengubahnya menjadi klaim langsung bila maknanya
   berubah.
6. `bukan X, tetapi Y` dan `bukan X, tapi Y` adalah bentuk yang salah dan
   dilaporkan sebagai `KE-13`. Ganti dengan `bukan X, melainkan Y` atau
   `tidak X, tetapi Y`.

## 9. Memeriksa naskah

```bash
python tools/check_prose.py chapters/*.md
python tools/check_prose.py --self-test
python tools/check_prose.py --banding asli.md hasil.md
python tools/check_prose.py --abaikan SG-04 chapters/*.md
```

Label `K` memblokir. Label `G` dan `AI` memberi anjuran.

`AI-20` melaporkan butir berlabel tebal minimal dua kali per berkas. Label
prosedur dan definisi dikecualikan lewat daftar di `writing/rules.yml`.
`--self-test` menjalankan kasus uji mandiri pemeriksa.

## 10. Presedensi

1. Fakta: angka, sitasi, kutipan, nama, arah hubungan.
2. Pedoman kampus dan preset format.
3. Panduan ini.
4. Saran pemeriksa.

Bila pemeriksa dan panduan bertentangan, berhenti dan laporkan. Jangan memilih
diam-diam. Aturan `K` mengikat. Aturan `G` dan `AI` advisory. Aturan manual
membutuhkan penilaian manusia.

## 11. Contoh

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

```text
Sebelum:
- **Kecepatan Tinggi**: sistem ini cepat.
- **Ukuran Kecil**: berkas ini kecil.

Sesudah:
Sistem ini cepat dan berkasnya kecil.
```

Atribusi: kaidah Ejaan Bahasa Indonesia, Kamus Besar Bahasa Indonesia, dan Tata
Bahasa Baku Bahasa Indonesia. Sebagian pola pemeriksa berasal dari proyek
naskah-id (lisensi `MIT`).
