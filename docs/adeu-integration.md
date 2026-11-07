# Integrasi Adeu: Rekonsiliasi Edit DOCX ke Markdown

Dokumen ini menjelaskan kontrak integrasi antara pipeline build DOCX dan Adeu
untuk kasus pengguna menyunting `Laporan.docx` secara manual di Microsoft Word.
Tujuannya bukan menimpa Markdown secara otomatis, melainkan menghasilkan laporan
tinjauan yang bisa diputuskan manusia.

## Ringkasan alur

1. **Build DOCX** dari `chapters/*.md` seperti biasa.
2. **Tambah ID paragraf**: tahap pascaproses `tools/add_paragraph_ids.py`
   menambahkan bookmark `pNNNN` pada setiap paragraf body dan menulis
   `build/manifest.json`. Tahap ini dijalankan otomatis di akhir
   `build-docx.sh`, setelah finalisasi section, format caption, istilah, dan
   nomor halaman. Bookmark `pNNNN` lama dihapus lebih dulu, sehingga tahap ini
   idempoten; bookmark lain dipertahankan.
3. **Edit di Word** dengan Track Changes. Pengguna hanya boleh mengubah blok
   yang tidak dilindungi.
4. **Rekonsiliasi**: jalankan `tools/reconcile.py` terhadap DOCX hasil edit,
   manifest, dan direktori `chapters/`.
5. **Terapkan ke Markdown**: manusia memilih saran yang benar, lalu mengedit
   `chapters/*.md`. Alat rekonsiliasi tidak pernah menulis ke Markdown.
6. **Build ulang** DOCX (dan PDF) dari Markdown yang sudah diperbarui.

Alur ini menjaga Markdown sebagai sumber kebenaran. DOCX hanya menjadi media
tinjauan sementara; setiap perubahan harus kembali ke Markdown agar tidak hilang
pada build berikutnya.

## Prasyarat

Alat rekonsiliasi membutuhkan Python 3.12 dengan `python-docx` dan `lxml`
(dependensi yang sama dengan modul istilah). Dari akar proyek:

```powershell
.venv\Scripts\python.exe -m pip install -r tools\requirements.txt
```

Di Linux/macOS gunakan `.venv/bin/python`. Contoh perintah di bawah memakai
Python dari virtualenv proyek.

## Kontrak manifest

`build/manifest.json` adalah kontrak yang dibekukan pada versi 1. Jangan
menambah, mengganti nama, atau mengubah arti field tanpa menaikkan versi.

```json
{
  "version": 1,
  "docx": "Laporan.docx",
  "built_at": "2026-11-06T12:00:00+00:00",
  "paragraphs": [
    {
      "id": "p0001",
      "index": 0,
      "kind": "heading",
      "heading_path": ["BAB I PENDAHULUAN"],
      "text": "BAB I PENDAHULUAN",
      "text_sha256": "hex",
      "protected": false,
      "protected_reason": null,
      "source_file": "bab1-pendahuluan.md",
      "source_line": 12
    }
  ]
}
```

Field penting:

| Field | Arti |
|---|---|
| `id` | ID paragraf berformat `pNNNN`, sama dengan nama bookmark di DOCX. |
| `index` | Urutan paragraf di DOCX, dimulai dari 0. |
| `kind` | Salah satu dari `heading`, `body`, `table`, `caption`, `toc`, `bibliography`, `cover`. |
| `heading_path` | Jalur heading tempat paragraf berada, misalnya `["BAB II TINJAUAN PUSTAKA", "2.1 Landasan Teori"]`. |
| `text` | Teks paragraf lengkap saat build. |
| `text_sha256` | Hash teks saat build; berguna untuk audit manifest. |
| `protected` | `true` bila paragraf tidak boleh diedit manual. |
| `protected_reason` | Alasan perlindungan, misalnya `caption_style` atau `toc_field`. |
| `source_file` | Opsional; path Markdown relatif terhadap `--source-dir`. `null` bila tidak ada kecocokan unik. |
| `source_line` | Opsional; nomor baris 1-based awal blok Markdown. `null` bila tidak ada kecocokan unik. |

`source_file` dan `source_line` hanya ditulis bila `add_paragraph_ids.py`
dijalankan dengan `--source-dir`. `build-docx.sh` selalu menjalankannya dengan
`--source-dir "$OUTDIR/chapters"`, jadi manifest hasil build normal memuat kedua
field tersebut. Manifest hanya menjamin kecocokan bila heading path dan teks
paragraf cocok tepat satu kali di seluruh `chapters/`.

Bookmark `pNNNN` disisipkan di dalam DOCX dan diproyeksikan Adeu sebagai penanda
`{#pNNNN}`. `add_paragraph_ids.py` menaruh `w:bookmarkStart` setelah `w:pPr` dan
`w:bookmarkEnd` di akhir paragraf, sehingga bookmark membungkus isi paragraf
tanpa mengubah properti paragraf. ID dihitung dari urutan paragraf (`p0001`,
`p0002`, ...) dan dibuat ulang pada setiap build; karena itu DOCX dan manifest
harus berasal dari build yang sama. Bookmark harus unik dan konsisten dengan
manifest.

## Menjalankan rekonsiliasi

```powershell
.venv\Scripts\python.exe tools\reconcile.py `
  --docx Laporan-edited.docx `
  --manifest build\manifest.json `
  --chapters chapters `
  --out review\manual-edits.md
```

Di Linux/macOS:

```bash
.venv/bin/python tools/reconcile.py \
  --docx Laporan-edited.docx \
  --manifest build/manifest.json \
  --chapters chapters \
  --out review/manual-edits.md
```

Alat hanya membaca DOCX, manifest, dan `chapters/*.md`. Satu-satunya berkas yang
ditulis adalah `--out`. Alat menolak `--out` yang berada di dalam direktori
`chapters/`.

### Exit code

| Exit | Arti |
|---|---|
| `0` | Tidak ada perubahan; laporan tetap ditulis dengan ringkasan nol. |
| `2` | Ada perubahan yang perlu ditinjau (termasuk paragraf baru/hilang). |
| `3` | Ada perubahan atau penghapusan pada blok `protected` (pelanggaran), termasuk paragraf `protected` yang hilang dari DOCX. |
| `1` | Kesalahan input: DOCX/manifest tidak terbaca, manifest tidak valid, direktori `chapters/` tidak ada, atau argumen CLI salah. |

Exit code `3` diprioritaskan di atas `2`. Artinya, satu pelanggaran blok
terlindungi membuat seluruh proses gagal walau ada perubahan lain yang sah.

## Cara kerja

### 1. Ekstraksi teks per bookmark

`tools/reconcile.py` membuka body DOCX dengan `python-docx`, lalu menelusuri
`w:bookmarkStart` sampai `w:bookmarkEnd` yang cocok berdasarkan `w:id`. Teks
diambil dari node `w:t`, dengan `w:tab` menjadi tab dan `w:br`/`w:cr` menjadi
baris baru.

Track Changes dibaca pada **state accepted**:

- teks di dalam `w:ins` ikut terbaca;
- teks di dalam `w:del` dan `w:moveFrom` diabaikan;
- instruksi field (`w:instrText`) diabaikan.

Dengan demikian, yang dibandingkan adalah teks yang akan terlihat setelah semua
revisi diterima.

### 2. Perbandingan dengan manifest

Teks DOCX dan `manifest.paragraphs[].text` dinormalisasi ringan: akhir baris
disamakan, non-breaking space menjadi spasi, dan spasi di awal/akhir dibuang.
Perubahan isi sekecil apa pun selain itu dianggap berubah.

Paragraf yang tidak berubah tidak masuk laporan. Paragraf yang berubah dan
`protected: true` dicatat sebagai `PELANGGARAN` tanpa saran patch.

### 3. Pencarian sumber Markdown

Untuk paragraf tidak terlindungi yang berubah, alat mencari blok sumber di
`chapters/*.md`:

1. Blok Markdown diparse menjadi heading, paragraf, list, blockquote, tabel,
   dan blok kode. Setiap blok menyimpan `heading_path` dari heading di atasnya.
2. `heading_path` manifest dicocokkan dengan `heading_path` blok setelah
   normalisasi penomoran. Bila tidak persis sama, keduanya dicocokkan sebagai
   suffix yang utuh. Contoh: `BAB II TINJAUAN PUSTAKA` cocok dengan
   `# TINJAUAN PUSTAKA`, dan `2.1 Landasan Teori` cocok dengan
   `## Landasan Teori`.
3. Di antara blok dengan jalur yang cocok, `difflib.SequenceMatcher` memilih
   blok dengan kemiripan tertinggi terhadap teks lama manifest.
4. Blok terbaik dipakai bila kemiripannya minimal `0.35`. Jika tidak ada blok
   dengan jalur yang cocok atau kemiripannya terlalu rendah, laporan menandai
   `SUMBER TIDAK DITEMUKAN`.

Nomor blok di laporan adalah urutan blok non-kosong dalam satu berkas chapter,
dimulai dari 1, termasuk heading. Nomor ini bisa dipakai untuk mencari blok di
editor.

### 4. Paragraf baru dan hilang

- Bookmark `pNNNN` yang ada di DOCX tetapi tidak ada di manifest dilaporkan
  sebagai `PARAGRAF BARU`.
- Paragraf berisi teks yang sama sekali tidak berada di dalam bookmark
  `pNNNN` dilaporkan sebagai `PARAGRAF BARU: tanpa ID`.
- ID manifest yang tidak ditemukan di DOCX dilaporkan sebagai
  `PARAGRAF HILANG`. Bila paragraf tersebut `protected`, bagiannya dilaporkan
  sebagai `PELANGGARAN` dan exit code menjadi `3`.
- Paragraf kosong tanpa ID diabaikan agar tidak menghasilkan derau.

### 5. Penulisan laporan

Laporan ditulis sebagai UTF-8 dengan akhir baris LF dan urutan yang
deterministik. Menjalankan alat dua kali pada input yang sama menghasilkan isi
berkas yang identik. Tidak ada timestamp di laporan.

## Blok yang dilindungi dan alasannya

| Jenis | Contoh `protected_reason` | Alasan |
|---|---|---|
| TOC (Daftar isi) | `toc_field`, `toc_style` | Daftar isi adalah field Word yang diisi ulang saat build; nomor halaman dan hyperlink-nya dihitung otomatis. `toc_field` dipakai untuk paragraf di dalam field TOC; `toc_style` untuk paragraf bergaya `TOC1`/`TOC2`/`TOC3` di luar field. Edit manual akan hilang atau membuat nomor halaman basi. |
| Caption | `caption_style` | Caption memakai penomoran dan style khusus (misalnya `Tabel 2.1`). Edit manual dapat memutus urutan nomor, cross-reference, dan daftar tabel/gambar. |
| Section break | `sectpr` | Section break mengatur margin, orientasi, dan penomoran halaman (Romawi/Arab). Perubahan struktur ini tidak bisa diwakili oleh edit teks paragraf dan dapat merusak pagination. |
| Bibliography (Daftar pustaka) | `bibliography` | Daftar pustaka dihasilkan `citeproc` dari `references.bib` dan `refs/undip-msi.csl` (turunan APA 7, author-date alfabetis). Edit manual akan tertimpa build berikutnya dan membuat sitasi tidak konsisten. |
| Halaman sampul | `cover_style` | Sampul dihasilkan dari `cover.md` dan `metadata.yml`. Perubahan manual tidak akan bertahan dan membuat data sampul tidak sinkron. |
| Field nomor | `seq_field`, `page_field`, `pageref_field` | Field `SEQ`, `PAGE`, dan `PAGEREF` dihitung Word. Mengedit hasil field secara manual akan membuat nomor gambar/halaman tidak sinkron dengan isi dokumen. |

`protected` adalah keputusan build, bukan keputusan alat rekonsiliasi. Alat
hanya membaca nilai tersebut dari manifest. Jika sebuah blok perlu dilindungi,
tahap tambah ID harus menandainya saat manifest dibuat.

## Contoh keluaran laporan

```markdown
# Edit Manual

## Ringkasan
- Diperiksa: 312 paragraf
- Berubah: 4
- Dilindungi & dilanggar: 1

## p0042: BAB II / 2.1 Landasan Teori

Sumber: chapters/bab2-tinjauan-pustaka.md (blok 12, kemiripan 0.94)

**Sebelum**
> Landasan teori merupakan fondasi utama dalam penyusunan laporan.

**Sesudah**
> Landasan teori merupakan fondasi utama dalam penyusunan laporan akademik.

**Saran:** terapkan ke Markdown lalu build ulang.

---

## PELANGGARAN p0011: caption (protected: caption_style)

**Sebelum**
> Tabel 2.1 Ringkasan Pipeline

**Sesudah**
> Tabel 2.1 Ringkasan Pipeline (diedit)

> Blok ini tidak boleh diedit manual. Kembalikan dari build.
```

Jika sumber tidak ditemukan, bagian `Sumber:` diganti dengan:

```markdown
**SUMBER TIDAK DITEMUKAN**: tidak ada blok Markdown yang cocok dengan heading_path dan teks lama.
```

Paragraf baru dan hilang muncul sebagai bagian tersendiri:

```markdown
## PARAGRAF BARU p0999

ID ini ada di DOCX tetapi tidak ada di manifest.

**Sesudah**
> Paragraf ber-bookmark yang tidak dikenal manifest.

## PARAGRAF BARU: tanpa ID

**Sesudah**
> Paragraf yang disisipkan langsung di Word.

## PARAGRAF HILANG p0012: BAB II TINJAUAN PUSTAKA / 2.2 Kerangka Pemikiran

**Sebelum**
> Paragraf yang dihapus dari Word.
```

## Batasan

Alat ini sengaja konservatif dan belum menangani hal-hal berikut:

- **Tidak auto-merge atau auto-apply.** Laporan hanya berisi saran; tidak ada
  patch yang ditulis ke `chapters/*.md`. Manusia tetap yang memutuskan.
- **Tidak menangani gambar atau tabel baru.** Alat membandingkan teks paragraf,
  bukan struktur dokumen. Gambar yang disisipkan tidak terdeteksi; teks di dalam
  tabel baru hanya muncul sebagai paragraf tanpa ID. Struktur tabel,
  penggabungan sel, dan perubahan layout tidak dianalisis. Bookmark yang
  membungkus tabel hanya akan menggabungkan teks antarsel dengan newline.
- **Tidak membaca header/footer.** Perubahan pada header, footer, nomor
  halaman, atau teks di dalamnya tidak terlihat oleh rekonsiliasi.
- **Tidak membaca komentar, author, atau riwayat revisi.** Track Changes
  diringkas menjadi state accepted; alat tidak melaporkan siapa mengubah apa
  atau komentar Word.
- **Tidak mendeteksi perubahan format inline.** Hanya teks yang dibandingkan.
  Perubahan bold, italic, font, warna, atau style paragraf tidak dilaporkan.
- **Pencocokan sumber bersifat heuristik.** `heading_path` dan `difflib` bisa
  salah memilih blok bila ada beberapa paragraf yang sangat mirip di bagian
  yang sama. Angka kemiripan di laporan harus dibaca sebagai indikasi, bukan
  jaminan.
- **Sumber hanya `chapters/*.md`.** Perubahan yang berasal dari `cover.md`,
  `references.bib`, daftar isi otomatis, atau daftar pustaka otomatis tidak
  punya blok sumber yang bisa disarankan.
- **Tidak menambahkan ID baru.** Paragraf baru harus diberi ID oleh tahap
  tambah ID pada build berikutnya; alat rekonsiliasi hanya melaporkannya.
- **Manifest dan DOCX harus dari build yang sama.** Membandingkan DOCX editan
  lama dengan manifest build baru akan menghasilkan banyak `PARAGRAF HILANG`
  dan `PARAGRAF BARU` palsu.
- **DOCX tanpa bookmark `pNNNN`** akan menghasilkan laporan massal: semua ID
  manifest dilaporkan hilang dan semua paragraf berteks dilaporkan sebagai
  paragraf baru tanpa ID. Pastikan tahap tambah ID sudah dijalankan.
- **Hanya body dokumen.** Bookmark di luar `word/document.xml` (misalnya
  header/footer) tidak diekstrak.

## Integrasi di CI atau skrip build

Karena exit code `2` berarti "perlu ditinjau", jangan memakai `set -e` tanpa
menangani status tersebut. Contoh:

```bash
python tools/reconcile.py \
  --docx build/Laporan-edited.docx \
  --manifest build/manifest.json \
  --chapters chapters \
  --out review/manual-edits.md
status=$?

case "$status" in
  0) echo "Tidak ada edit manual." ;;
  2) echo "Ada edit manual; lihat review/manual-edits.md." ;;
  3) echo "Pelanggaran blok terlindungi; lihat review/manual-edits.md." >&2 ;;
  *) echo "Rekonsiliasi gagal." >&2 ;;
esac

exit "$status"
```

Artefak `review/manual-edits.md` sebaiknya disimpan bersama log CI agar reviewer
bisa melihat teks sebelum/sesudah dan blok sumber yang disarankan.
