# Aturan Menulis

Panduan ini merangkum aturan prosa yang dipakai repo. Sumber pola pemeriksa
ada di `tools/dev/rules.yml`; jangan menyalin regex ke berkas lain.

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

Glosarium paket berada di `src/docgen/data/glossary/istilah.tsv`. Tambahkan
`istilah.tsv` di samping `document.md` untuk menimpa atau menambah entri.
Format TSV (tab-separated values) memakai header `term` dan `italic`:

```tsv
term	italic
machine learning	yes
data	no
```

Aktifkan gate istilah saat build:

```bash
uv run --project <repo> docgen build document.md --target docx --terms
```

Dengan `--terms`, stage `terms` memproses penanda `{{?istilah?}}`, menerapkan
style `IstilahAsing`, dan menulis daftar tinjauan ke
`.laporan/istilah-baru.txt`. Penanda yang belum diputuskan menjadi item
tinjauan, bukan kegagalan build. Keputusan tetap di penulis: ganti dengan
istilah yang benar atau tambahkan entri glosarium, lalu build ulang.

Tanpa `--terms`, tidak ada penerapan istilah dan tidak ada review file.
Rincian ada di [docs/dev/terms.md](../dev/terms.md).

## Menjalankan pemeriksa prosa

```bash
uv run --project <repo> python tools/dev/check_prose.py document.md
uv run --project <repo> python tools/dev/check_prose.py --banding asli.md document.md
uv run --project <repo> python tools/dev/check_prose.py --abaikan SG-04,KL-01 document.md
uv run --project <repo> python tools/dev/check_prose.py --self-test
```

Label `K` memblokir dan membuat kode keluar `1`. Label `G` dan `AI` hanya
memberi anjuran. `--banding` memeriksa angka, sitasi, dan kutipan antara dua
versi. `--self-test` menjalankan kasus uji mandiri pemeriksa.

Pemeriksa menerima `.md`, `.txt`, dan `.docx`. Pada DOCX, teks dibaca per
paragraf dan nomor baris laporan adalah nomor paragraf.

## Audit istilah DOCX

Untuk memeriksa hasil build:

```bash
uv run --project <repo> python tools/dev/audit_terms.py \
  --docx Tugas.docx \
  --glossary src/docgen/data/glossary/istilah.tsv \
  --out .laporan/istilah-audit.md
```

Alat ini hanya membaca DOCX dan menulis laporan. Alat tidak mengubah DOCX,
glosarium, atau naskah.

## Kode temuan

| Keluarga | Kode | Isi |
| --- | --- | --- |
| Kalimat efektif | `KE-01` sampai `KE-17` | subjek, pleonasme, perangkai, perbandingan |
| Nominalisasi dan klaim | `NM-01`, `KK-01` | verba penopang dan kekuatan klaim |
| Singkatan | `SG-01` sampai `SG-06` | tanda hubung, titik, jamak, kepanjangan |
| Ejaan dan tanda baca | `EJ-01` sampai `EJ-11` | di/ke, bentuk terikat, angka, satuan, koma, em dash |
| Klise mesin | `AI-01` sampai `AI-20` | pembuka kosong, kalke, penghubung berulang |
| Kata baku | `KB-01` | kata tidak baku |
| Kalimat panjang | `KL-01` | lebih dari 35 kata |
| Penanda istilah | `IS-01` | `{{?istilah?}}` belum diputuskan |

## Presedensi

1. Fakta: angka, sitasi, kutipan, nama, dan arah hubungan.
2. Pedoman kampus dan format `undip-msi`.
3. Panduan ini.
4. Saran pemeriksa.

Bila pemeriksa dan panduan bertentangan, berhenti dan laporkan. Jangan memilih
diam-diam. Aturan `K` mengikat; `G` dan `AI` advisory.

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
Bahasa Baku Bahasa Indonesia. Sebagian pola pemeriksa berasal dari proyek
naskah-id (MIT). Teks lisensi ada di `LICENSE`.
