# Pemeriksa Prosa Naskah

Pemeriksa pola kaidah, gaya, dan klise mesin untuk naskah berbahasa Indonesia.
Skrip `tools/check_prose.py` membaca seluruh aturan dari `writing/rules.yml`.
Skrip tidak menyimpan salinan regex. Makefile memanggil skrip ini langsung
lewat target `lint-prosa`.

Pemeriksa ini turunan `scripts/periksa.py` dari proyek naskah-id (lisensi
`MIT`, Copyright (c) 2026 nothinx). Tambahan proyek: pemetaan heading `.docx`,
penanda istilah `IS-01`, em dash `EJ-11`, dan aturan butir berlabel `AI-20`.
Hanya memakai pustaka standar Python 3. Tidak butuh jaringan dan tidak menambah
paket.

## Cara pakai

```bash
python tools/check_prose.py berkas.md          # Markdown atau teks biasa
python tools/check_prose.py skripsi.docx       # Word
python tools/check_prose.py bab1.md bab2.docx  # beberapa berkas sekaligus
python tools/check_prose.py - < naskah.txt     # baca dari stdin
```

Untuk memeriksa seluruh bab proyek sekaligus:

```bash
make lint-prosa
```

`make lint-prosa` memanggil `tools/check_prose.py` untuk seluruh berkas
`chapters/*.md`.

Pilihan lain:

```bash
python tools/check_prose.py --abaikan SG-04,KL-01 skripsi.docx  # lewati kode tertentu
python tools/check_prose.py --banding asli.md hasil.md          # cek angka, sitasi, kutipan
python tools/check_prose.py --self-test                         # uji mandiri
python tools/check_prose.py --validasi                          # cek paket sumber
```

Label `K` membuat kode keluar 1. Label `G` dan `AI` hanya anjuran dan tidak
menggagalkan lint. `--validasi` khusus paket sumber naskah-id; di proyek ini
`SKILL.md` tidak ada, jadi perintah itu memberi pesan dan keluar 1. Lint prosa
tidak memerlukannya.

## Sumber aturan

`writing/rules.yml` adalah satu-satunya sumber perilaku. Berkas itu memuat
kode, label, regex, minimal kemunculan, saran, kamus kata baku, akronim, dan
daftar putih. Untuk menambah atau mengubah aturan, sunting `rules.yml` lalu
jalankan tes. Jangan menyalin regex ke panduan, dokumentasi, atau skrip lain.

Panduan menulis ada di `writing/guide.md`. Panduan itu menjelaskan alasan dan
urutan kerja, bukan daftar pola.

## Label dan kode

| Label | Arti | Kode keluar |
| --- | --- | --- |
| `K` | kaidah | 1 |
| `G` | gaya | 0 |
| `AI` | klise mesin | 0 |

Keluarga kode: `KE`, `NM`, `KK`, `SG`, `EJ`, `AI`, `KB`, `KL`, dan `IS`.
Rincian tiap kode ada di `writing/rules.yml`. Perintah
`python tools/check_prose.py --self-test` memeriksa perilaku dasarnya.

## Aturan dinamis dan butir berlabel

Empat aturan ditangani oleh fungsi khusus, bukan oleh satu pola statis biasa:

- `SG-04`: token kapital yang belum dijelaskan.
- `SG-06`: kepanjangan singkatan bukan nama diri.
- `KL-01`: kalimat lebih dari 35 kata.
- `IS-01`: penanda `{{?istilah?}}` yang belum diputuskan.

`AI-20` memakai regex pada teks mentah karena pemeriksa membuang penanda butir
sebelum mencocokkan pola lain. Aturan ini melaporkan butir berlabel tebal yang
mengulang labelnya sendiri, misalnya
`- **Kecepatan Tinggi**: sistem ini cepat`. Minimal dua butir per berkas. Label
prosedur dan definisi dikecualikan lewat daftar di `rules.yml`.

## Berkas Word

Pada `.docx`, nomor baris adalah nomor paragraf. Paragraf bergaya `Heading1`,
`Heading2`, dan `Heading3` dibaca sebagai `#`, `##`, dan `###`. Bagian
`Daftar Pustaka`, `Referensi`, `Bibliografi`, dan `Abstract` sampai judul
berikutnya dilewati.

## Batasan

- Tidak memeriksa italic atau istilah asing secara otomatis.
- Tidak memvalidasi isi daftar pustaka.
- Tidak membaca footnote, endnote, komentar Word, atau bagian di luar
  `word/document.xml`.
- Berbasis regex: temuan bisa salah positif atau terlewat. Setiap temuan perlu
  dibaca dalam konteksnya.
- `AI-20` memakai heuristik. Satu daftar definisi yang wajar bisa tetap
  dilaporkan bila tidak memakai label yang ada di daftar pengecualian.
- `AI-20` hanya melihat penanda butir Markdown; daftar berbutir di `.docx`
  tanpa penanda itu tidak dikenali.

## Tes

```bash
.venv/Scripts/python.exe -m pytest tests/test_check_prose.py tests/test_check_prose_docx.py -q
python tools/check_prose.py --self-test
```

`tests/test_check_prose.py` memeriksa jumlah kode, kamus, akronim, regresi
`AI-20`, dan sinkronisasi dasar antara `rules.yml` dan pemeriksa.

## Lisensi dan atribusi

Kode ini `MIT`, Copyright (c) 2026 nothinx, berdasarkan proyek naskah-id.
Isi `contoh/korpus/` pada proyek asal berlisensi `CC BY-SA 4.0` dan tidak
disertakan dalam salinan ini.

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
