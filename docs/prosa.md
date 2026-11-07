# Pemeriksa Prosa Naskah

Pemeriksa pola kaidah dan klise mesin untuk naskah Indonesia, terutama skripsi
di proyek ini. Skrip ini turunan `scripts/periksa.py` dari proyek
[naskah-id](https://github.com/nothinx/naskah-id) (MIT, Copyright (c) 2026 nothinx),
dengan perbaikan pembacaan heading `.docx` dan pemeriksaan penanda istilah.

Hanya memakai pustaka standar Python 3. Tidak butuh jaringan dan tidak menambah paket.

## Cara pakai

```bash
python tools/periksa_prosa.py berkas.md          # Markdown atau teks biasa
python tools/periksa_prosa.py skripsi.docx       # Word
python tools/periksa_prosa.py bab1.md bab2.docx  # beberapa berkas sekaligus
python tools/periksa_prosa.py - < naskah.txt     # baca dari stdin
```

Untuk memeriksa seluruh bab proyek sekaligus:

```bash
make lint-prosa
```

Contoh keluaran:

```
skripsi.docx:12: [KE-01 K] 'Dari hasil pengujian menunjukkan': subjek hilang karena kata depan; buang kata depannya atau pakai verba pasif
skripsi.docx:15: [KB-01 K] 'analisa': baku: analisis
skripsi.docx:20: [NM-01 G] 'mengalami penurunan': nominalisasi; pakai verbanya langsung
```

Pada `.docx`, nomor baris adalah nomor paragraf. Paragraf bergaya `Heading1`,
`Heading2`, dan `Heading3` dibaca sebagai `#`, `##`, dan `###`, sehingga batas bagian
sama seperti pada Markdown. Bagian `Daftar Pustaka`, `Referensi`, `Bibliografi`, dan
`Abstract` sampai judul berikutnya sengaja dilewati.

Pilihan lain:

```bash
python tools/periksa_prosa.py --abaikan SG-04,KL-01 skripsi.docx  # lewati kode tertentu
python tools/periksa_prosa.py --banding asli.md hasil.md          # cek angka, sitasi, kutipan yang berubah
python tools/periksa_prosa.py --tes                               # uji mandiri
python tools/periksa_prosa.py --validasi                          # cek paket sumber (butuh SKILL.md)
```

Label `K` (kaidah) membuat kode keluar 1. Label `G` (gaya) dan `AI` (klise mesin)
hanya anjuran dan tidak menggagalkan lint. `--validasi` hanya untuk mengembangkan
paket sumber; di proyek ini `SKILL.md` tidak ada, jadi perintah itu memberi pesan
dan keluar 1. Lint prosa tidak memerlukannya.

## Kode temuan

| Kode | Arti | Label |
| --- | --- | --- |
| `KE-01`–`KE-17` | Kalimat efektif: subjek hilang, pleonasme, perangkai, perbandingan | K |
| `NM-01` | Nominalisasi | G |
| `KK-01` | Klaim terlalu kuat (`membuktikan`) | G |
| `SG-01`–`SG-06` | Singkatan dan akronim: tanda hubung, titik, jamak, kepanjangan | K/G |
| `EJ-01`–`EJ-11` | Ejaan: di/ke, bentuk terikat, angka, satuan, koma, em dash | K |
| `AI-01`–`AI-19` | Klise mesin dan kalke | AI |
| `KB-01` | Kata tidak baku (129 pasangan) | K |
| `KL-01` | Kalimat lebih dari 35 kata | G |
| `IS-01` | Penanda istilah `{{?…?}}` belum diputuskan | K |

`IS-01` hanya melaporkan penanda yang tersisa. Pemeriksa tidak menebak istilah dan
tidak mengubah teks; saran yang diberikan: "putuskan lalu hapus penanda".

## Panduan menulis

Kaidah penulisan naskah ada di [`../writing/panduan.md`](../writing/panduan.md).
Daftar pola larangan beserta alasannya ada di
[`../writing/larangan.txt`](../writing/larangan.txt). Jalankan pemeriksa sebelum
menyerahkan draf.

## Batasan

- Tidak memeriksa italic/istilah asing secara otomatis. Pemilihan padanan, penulisan
  miring, dan konsistensi istilah harus dibaca manusia.
- Tidak memvalidasi isi daftar pustaka. Bagian itu hanya dilewati, bukan diperiksa.
- Tidak membaca footnote, endnote, komentar Word, atau bagian dokumen di luar
  `word/document.xml`.
- Berbasis regex: temuan bisa salah positif atau terlewat. Setiap temuan perlu dibaca
  dalam konteksnya; jangan dipakai untuk menilai apakah teks ditulis mesin.

## Tes

```bash
.venv/Scripts/python.exe -m pytest tests/test_periksa_prosa.py -q
python tools/periksa_prosa.py --tes
```

Di Linux/macOS gunakan `.venv/bin/python`. `--tes` bawaan berisi 109 kasus. Tes di
`tests/test_periksa_prosa.py` menambah regresi untuk `.docx` yang memuat `Abstract`,
`Daftar Pustaka`, pemetaan heading, dan penanda `IS-01`.

## Lisensi dan atribusi

Kode ini MIT, Copyright (c) 2026 nothinx, berdasarkan
[naskah-id](https://github.com/nothinx/naskah-id). Isi `contoh/korpus/` pada proyek
asal berlisensi CC BY-SA 4.0 dan **tidak** disertakan dalam salinan ini.

```text
MIT License

Copyright (c) 2026 nothinx

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
