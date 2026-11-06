# Istilah Asing pada DOCX

Modul ini memberi style pada istilah asing di file `.docx` yang sudah jadi,
mengubah penanda `{{?istilah?}}` menjadi teks review ber-highlight, serta
memeriksa konsistensinya. Modul dijalankan dari `tools/istilah.py` dan
diintegrasikan ke `build-docx.sh` sesudah `finalize-docx.py`.

Dependensi: `python-docx` dan `lxml` (lihat `tools/requirements.txt`).
`pytest` hanya diperlukan untuk menjalankan tes.

## Setup

Dari akar proyek:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r tools\requirements.txt
```

Semua contoh perintah di bawah memakai `.venv\Scripts\python.exe`. Di Linux/macOS
padanan path-nya adalah `.venv/bin/python`.

## Format glosarium

File UTF-8, LF, tab-separated. Baris komentar diawali `#`. Header wajib:

```tsv
term	italic	gloss_first	status
training data	yes	no	confirmed
big data	yes	no	confirmed
data	no	no	confirmed
Python	no	no	confirmed
Microsoft Word	no	no	confirmed
```

Kolom:

- `term`: satu istilah/frasa. Boleh multi-kata dan boleh bertanda hubung.
- `italic`: `yes` atau `no`. `yes` berarti istilah harus miring dan mendapat
  style `IstilahAsing`; `no` berarti harus tegak.
- `gloss_first`: `yes` atau `no` (divalidasi; belum dipakai, lihat Batasan).
- `status`: `confirmed` atau `review` (divalidasi; belum dipakai untuk
  memfilter, lihat Batasan).

Glosarium divalidasi sebelum dipakai. Duplikat term (tanpa membedakan huruf
besar/kecil), jumlah kolom salah, dan nilai di luar pilihan akan membuat
perintah berhenti dengan exit code `1`.

## Sintaks penanda

Penanda adalah `{{?istilah?}}`. Isinya tidak boleh kosong, mengandung
`{{`/`}}`, atau newline. `??` kosong dan `{{??}}` menghasilkan error exit `1`;
begitu juga `{{?` tanpa penutup. Teks yang memang perlu memuat literal `{{?`
harus dihindari atau diolah di luar dokumen, karena belum ada mekanisme escape.

Kalimat tanya biasa seperti `Apa itu data? Mengapa penting?` bukan penanda dan
tidak diubah. Sintaks lama `?istilah?` tidak dikenali sebagai penanda.

## Perintah

### `check <file.md> [--glossary <tsv>]`

Mencari penanda `{{?…?}}` di Markdown dan menulis daftarnya (satu per baris,
unik) ke `review/istilah-baru.txt` relatif terhadap file Markdown. Untuk build,
lokasi tersebut dioverride dengan `--review-file` agar selalu berada di
`review/istilah-baru.txt` pada akar proyek.

- Exit `0`: tidak ada penanda.
- Exit `2`: ada penanda baru.
- Exit `1`: file tidak ada, glosarium tidak valid, atau penanda kosong/rusak.

Jika `--glossary` tidak diberikan, modul mencari `istilah.tsv` di folder file
Markdown lalu di current directory. Kalau ditemukan, file itu tetap divalidasi.

Contoh:

```powershell
.venv\Scripts\python.exe tools\istilah.py check chapters\bab1-pendahuluan.md
```

### `apply <file.docx> --glossary <tsv> [--review-file <txt>]`

Modul utama. Perilaku:

1. Menambahkan character style `IstilahAsing` bila belum ada: berdasarkan
   `DefaultParagraphFont`, dengan `w:i` dan `w:lang w:val="en-US"`. Style yang
   sudah ada tetapi tidak memenuhi invariant ini diperbaiki.
2. Menambahkan character style `IstilahReview` bila belum ada: highlight
   kuning.
3. Mencari istilah `italic=yes` pada setiap paragraf, termasuk paragraf di
   tabel, header, dan footer. Paragraf ber-style `Bibliography` dilewati
   karena italic di sana berasal dari CSL.
4. Menerapkan `IstilahAsing` pada teks asli tanpa mengubah kapitalisasi. Run
   yang diberi style juga mendapat `w:i` dan `w:lang w:val="en-US"` langsung,
   sehingga direct formatting lama tidak menang.
5. Mengubah `{{?sesuatu?}}` menjadi teks `sesuatu` dengan style
   `IstilahReview`, lalu mencatat `sesuatu` ke daftar review. Tanpa
   `--review-file`, daftar ditulis ke `review/istilah-baru.txt` relatif
   terhadap DOCX.

Delimiter `{{?` dan `?}}` dihapus; teks di dalamnya tetap ada. Daftar review
ditulis ulang setiap `apply`/`check`, tetapi item review yang sudah ada tetap
dipertahankan saat `apply` dijalankan ulang. `IstilahReview` tidak pernah
dipromosikan menjadi `IstilahAsing`.

Istilah yang sudah italic manual (direct formatting) tidak diberi
`IstilahAsing`; `verify` hanya mencetak peringatan `[direct formatting]`.
Penanda yang berada di dalam field atau hyperlink eksternal tidak diubah.
`apply` mencetak peringatan dan memasukkannya ke daftar review; `verify` akan
melaporkannya sebagai kegagalan sampai penanda dipindahkan ke teks biasa.

```powershell
.venv\Scripts\python.exe tools\istilah.py apply Laporan.docx --glossary writing\istilah.tsv --review-file review\istilah-baru.txt
```

### `verify <file.docx> --glossary <tsv>`

Exit `1` bila menemukan salah satu dari:

- istilah `italic=yes` muncul sebagai teks biasa tanpa `IstilahAsing`;
- istilah `italic=no` muncul dengan `IstilahAsing` atau italic efektif;
- ada span `IstilahAsing` yang isinya bukan istilah di glosarium;
- ada run `IstilahAsing` yang tidak efektif italic (`w:i` dimatikan) atau
  bahasa efektifnya bukan `en-US`;
- run berisi istilah `italic=yes` tanpa `IstilahAsing`, tetapi run itu punya
  direct `w:lang=en-US`;
- masih ada penanda `{{?…?}}` (termasuk yang berada di field/hyperlink
  eksternal).

Teks Inggris biasa, nama produk `italic=no`, item `IstilahReview`, dan teks
bukan istilah glosarium tidak digagalkan hanya karena memakai
`w:lang=en-US`. Istilah `italic=yes` yang sudah italic manual dianggap benar
tanpa `IstilahAsing`; `verify` hanya mencetak peringatan `[direct formatting]`,
bukan kegagalan. Pengecualiannya adalah cek bahasa sempit di atas. Teks
ber-style `IstilahReview` dianggap masih menunggu keputusan; gunakan perintah
`review` untuk melihatnya. `verify` tidak menggagalkan build hanya karena ada
item review.

```powershell
.venv\Scripts\python.exe tools\istilah.py verify Laporan.docx --glossary writing\istilah.tsv
```

### `review <file.docx>`

Mencetak daftar teks ber-style `IstilahReview` (dan penanda `{{?…?}}` yang
masih tersisa) beserta nomor paragraf. Penanda di field/hyperlink eksternal
juga ikut dicetak. Perintah ini tidak mengubah file.

```powershell
.venv\Scripts\python.exe tools\istilah.py review Laporan.docx
```

## Aturan pencocokan

- **Frasa terpanjang menang.** Pada `big data dan data`, `big data` dipilih
  sebagai satu span; `data` di dalamnya tidak diproses lagi. Istilah
  `italic=no` tetap ikut dipertimbangkan sebagai penghalang.
- **Batas kata.** `data` tidak cocok di dalam `datang` atau `metadata`.
- **Case-insensitive**, tetapi teks asli dipertahankan.
- **Spasi literal.** `training data` tidak cocok dengan `training  data`.
- **Tanda hubung** didukung, misalnya `fine-tuning`.
- **Lintas run.** Teks seluruh paragraf disatukan untuk pencocokan, lalu
  dipetakan balik ke `w:t`/run. Istilah yang terpotong beberapa run (umum pada
  hasil Pandoc) tetap ditangani.
- **Tidak menyentuh** teks di dalam field (`w:fldChar`, `w:fldSimple`),
  `w:instrText`, atau hyperlink eksternal. Istilah di area itu juga diabaikan
  oleh pencocokan, tetapi penanda `{{?…?}}` di sana dilaporkan sebagai warning
  dan tidak diubah.
- Paragraf ber-style `Bibliography` dilewati. CSL memang meng-italic judul
  buku/laporan dan nama jurnal di daftar pustaka, sehingga italic di sana bukan
  keputusan penulisan istilah pada naskah.
- **Invariant `IstilahAsing`.** Run ber-style ini harus efektif italic dan
  berbahasa `en-US`; `verify` memeriksa properti efektif, bukan hanya ID
  style.
- Format langsung lain pada run yang dipecah (misalnya bold) ikut
  dipertahankan.

## Integrasi ke `build-docx.sh`

Urutan build yang dipakai:

1. Pandoc menghasilkan DOCX sementara.
2. `scripts/finalize-docx.py` menyiapkan section.
3. `tools/istilah.py apply` menerapkan `IstilahAsing`/`IstilahReview`.
4. `scripts/docx-pagenum.py` menghitung nomor halaman dari PDF.

`apply` harus berjalan sebelum `docx-pagenum.py`: italic dapat mengubah lebar
teks dan paginasi, sehingga nomor halaman di daftar isi bisa meleset bila
dihitung lebih dulu.

Sebelum Pandoc, `build-docx.sh` menjalankan:

```bash
tools/istilah.py check chapters/*.md --glossary writing/istilah.tsv
```

Jika ada penanda `{{?…?}}` yang belum diputuskan, build berhenti dan
menampilkan daftarnya. Build juga berhenti bila `writing/istilah.tsv` tidak ada
atau bila `python-docx`/`lxml` belum terpasang; pesan yang ditampilkan meminta
`pip install -r tools/requirements.txt`.

Setelah `apply`, build menjalankan `verify` pada DOCX yang sama. Jika verify
gagal, build exit non-zero dan menampilkan seluruh temuan. File review selalu
ditulis ke `review/istilah-baru.txt` di akar proyek.

## Tes

```powershell
.venv\Scripts\python.exe -m pytest tests\test_istilah.py tests\test_integration_istilah.py -q
```

Fixture DOCX statis dapat dibuat ulang dengan:

```powershell
.venv\Scripts\python.exe tests\fixtures\istilah\make_fixtures.py
```

## Batasan yang diketahui

- `gloss_first` dan `status` baru divalidasi. Modul belum menambahkan gloss
  Indonesia pada kemunculan pertama, dan belum memfilter baris berstatus
  `review`; istilah `italic=yes` tetap diterapkan.
- `apply` juga memproses tabel, header, dan footer. **Footnote/endnote**,
  komentar, dan isi bagian dokumen yang tidak dimuat python-docx belum
  dipindai. Paragraf `Bibliography` sengaja dilewati (lihat aturan
  pencocokan).
- Field yang membentang lintas paragraf belum dilacak sebagai satu state.
  Field yang umum (satu paragraf) dilewati dengan benar.
- Hyperlink internal tetap diproses; hyperlink eksternal dilewati.
- Bila run yang terkena istilah sudah memakai character style lain,
  `IstilahAsing` menggantikan `rStyle` run tersebut. Format langsung lain
  (bold, ukuran, warna, dan sebagainya) tetap disalin.
- Penanda `{{?…?}}` harus berada dalam satu paragraf dan tidak boleh memuat
  `{{`, `}}`, atau newline. Penanda di field/hyperlink eksternal tidak bisa
  diubah otomatis.
- Literal `{{?` di teks biasa akan dianggap awal penanda dan bisa menghasilkan
  error; belum ada escape khusus. Hindari menulis `{{?` di naskah kecuali
  sebagai penanda.
- Daftar review adalah hasil build terakhir; file `review/istilah-baru.txt`
  ditimpa, tetapi item review yang masih ada di DOCX dipertahankan saat
  `apply` berikutnya.
