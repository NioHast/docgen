# Audit Italic Istilah

`tools/audit_istilah.py` memeriksa DOCX hasil build dan menulis laporan
Markdown berisi istilah yang perlu diperbaiki atau perlu diputuskan. Alat ini
**tidak mengubah** DOCX, glosarium, atau naskah. Keputusan tetap di tangan
agent/penulis.

Alat ini melengkapi `tools/istilah.py`:

- `istilah.py apply` menegakkan keputusan glosarium saat build.
- `istilah.py verify` memeriksa invarian teknis (style, bahasa, penanda).
- `audit_istilah.py` mencari kasus yang belum tertangani: istilah
  `italic=yes` yang masih tegak, istilah `italic=no` yang masih miring, dan
  kata/frasa Latin yang belum ada di glosarium.

## Pemakaian

Dari akar proyek:

```powershell
.venv\Scripts\python.exe tools\audit_istilah.py `
  --docx Laporan.docx `
  --glossary writing\istilah.tsv `
  --out review\istilah-audit.md
```

Di Linux/macOS:

```bash
.venv/bin/python tools/audit_istilah.py \
  --docx Laporan.docx \
  --glossary writing/istilah.tsv \
  --out review/istilah-audit.md
```

Argumen:

| Argumen | Wajib | Default | Keterangan |
|---|---:|---|---|
| `--docx` | ya | tidak ada | DOCX hasil build yang diaudit |
| `--glossary` | tidak | `writing/istilah.tsv` | glosarium TSV |
| `--out` | tidak | `review/istilah-audit.md` | laporan Markdown |

Kode keluar:

- `0`: tidak ada `PERLU DIPERBAIKI` dan tidak ada `PERLU KEPUTUSAN`.
- `2`: ada temuan pada salah satu tabel tindak lanjut.
- `1`: DOCX/glosarium tidak ditemukan atau tidak valid.

`review/` sudah diabaikan Git, jadi laporan audit tidak ikut ter-commit.

## Alur kerja agent

1. **Build dulu, audit kemudian.** Audit membaca DOCX, bukan Markdown. Jalankan
   `bash build-docx.sh` (atau `make docx`) lebih dulu agar `IstilahAsing`
   sudah diterapkan.
2. **Jalankan audit** dengan perintah di atas.
3. **Baca `PERLU DIPERBAIKI`.** Untuk setiap baris:
   - `glossary_italic_missing`: istilah sudah `italic=yes` di glosarium,
     tetapi di DOCX masih tegak. Jika keputusan memang italic, pastikan build
     terakhir memakai glosarium terbaru lalu build ulang. Jika ternyata harus
     tegak, ubah baris glosarium menjadi `italic=no`.
   - `glossary_plain_but_italic`: istilah `italic=no` muncul miring. Hapus
     penekanan italic di `chapters/*.md`, atau ubah glosarium menjadi
     `italic=yes` bila keputusan berubah.
4. **Baca `PERLU KEPUTUSAN`.** Untuk setiap kata/frasa:
   - Istilah asing yang harus miring: tambahkan baris ke
     `writing/istilah.tsv` dengan `italic=yes`, `gloss_first` sesuai
     kebutuhan, dan `status=confirmed`.
   - Nama produk/perkakas/orang yang harus tegak: tambahkan dengan
     `italic=no`.
   - Kata Indonesia yang tidak perlu diaudit: tidak perlu masuk glosarium;
     cukup biarkan. Jika kata itu sering muncul dan mengotori laporan, daftar
     stopword/akhiran di alat dapat ditambah pada perubahan terpisah.
   - Baris bertanda `name` adalah nama CamelCase (mis. `PostgreSQL`,
     `JavaScript`). Perlakuan tetap sama: putuskan `italic=yes/no` dan
     tambahkan ke glosarium bila perlu.
5. **Edit sumber yang benar.** Glosarium untuk keputusan istilah; `chapters/*.md`
   untuk penggunaan yang perlu diubah. Jangan mengedit DOCX hasil build karena
   perubahan akan hilang pada build berikutnya.
6. **Build ulang** (`bash build-docx.sh`), lalu **audit ulang**. Ulangi sampai
   exit code `0` atau sampai semua temuan yang tersisa memang sengaja
   dibiarkan (mis. istilah baru yang menunggu keputusan penulis).

## Isi laporan

Laporan selalu memuat:

1. **Ringkasan**: jumlah istilah unik dan kemunculan per kategori.
2. **PERLU DIPERBAIKI**: `kata/frasa | status | jumlah | contoh konteks`.
3. **PERLU KEPUTUSAN**: `kata/frasa | jumlah | 3 contoh konteks`.
4. **OK**: istilah glosarium yang sudah sesuai (`kata | jumlah`).
5. **Cara menindaklanjuti**: ringkasan langkah di atas.

Kategori:

| Kategori | Arti | Tindakan |
|---|---|---|
| `glossary_italic` | `italic=yes`, sudah miring | tidak ada |
| `glossary_plain` | `italic=no`, sudah tegak | tidak ada |
| `glossary_italic_missing` | `italic=yes`, masih tegak | perbaiki |
| `glossary_plain_but_italic` | `italic=no`, masih miring | perbaiki |
| `unknown` | tidak ada di glosarium | putuskan |
| `mixed_case_name` | CamelCase, tidak ada di glosarium | putuskan; ditandai `name` |
| `abbreviation` | akronim kapital ≤ 6 huruf | diabaikan kecuali ada di glosarium |

Contoh laporan (disederhanakan):

```markdown
# Audit Italic Istilah

- Dokumen: `Laporan.docx`
- Glosarium: `writing/istilah.tsv`
- Paragraf diperiksa: 120

## Ringkasan

| Kategori | Istilah unik | Kemunculan |
|---|---:|---:|
| `glossary_italic` (OK) | 1 | 2 |
| `glossary_plain` (OK) | 1 | 4 |
| `glossary_italic_missing` (perlu diperbaiki) | 1 | 1 |
| `glossary_plain_but_italic` (perlu diperbaiki) | 0 | 0 |
| `unknown` (perlu keputusan) | 1 | 1 |
| `mixed_case_name` (perlu keputusan (nama)) | 0 | 0 |
| `abbreviation` (diabaikan) | 1 | 2 |

**PERLU DIPERBAIKI:** 1 istilah (1 kemunculan) · **PERLU KEPUTUSAN:** 1 istilah (1 kemunculan)

## PERLU DIPERBAIKI

| Kata/frasa | Status | Jumlah | Contoh konteks |
|---|---|---:|---|
| `training data` | `glossary_italic_missing` | 1 | …pada **training data** yang digunakan… |

## PERLU KEPUTUSAN

| Kata/frasa | Jumlah | 3 contoh konteks |
|---|---:|---|
| `Graphical` | 1 | …antarmuka **Graphical** pengguna… |

## OK

| Kata/frasa | Jumlah |
|---|---:|
| `data` | 4 |
| `deep learning` | 2 |
```

## Batasan heuristik

Alat ini membuat **laporan untuk ditinjau**, bukan memutuskan sendiri. Batasan
yang perlu diketahui:

- **Kata/frasa Latin** diambil dengan regex
  `[A-Za-z][A-Za-z0-9'’\-]*`, minimal 3 huruf. Kata yang lebih pendek
  (mis. `AI`, `ML`) tidak masuk laporan.
- **Frasa glosarium menang.** Istilah multi-kata dicocokkan paling panjang
  lebih dulu. `training data` dilaporkan sebagai satu frasa; kata `training`
  dan `data` di dalamnya tidak dilaporkan terpisah. `data` di tempat lain
  tetap dilaporkan sesuai baris glosariumnya.
- **Italic efektif** dihitung dari `w:i` langsung, character style
  (`IstilahAsing` selalu dianggap miring kecuali dimatikan langsung), lalu
  paragraph style. `w:iCs` (complex script) tidak diperiksa.
- **Run campuran.** Kata dianggap miring hanya jika seluruh hurufnya miring.
  Untuk istilah `italic=no`, satu bagian yang miring sudah cukup untuk
  dilaporkan `glossary_plain_but_italic`.
- **Stopword dan akhiran** hanya pengurang noise. Daftar kata Indonesia dan
  akhiran seperti `-nya`, `-kan`, `-an`, `-si`, `-ik`, `-ah` tidak lengkap.
  Kata Indonesia yang belum tercakup bisa muncul sebagai `unknown`; istilah
  Inggris yang kebetulan mirip kata Indonesia bisa ikut terlewat. Istilah yang
  ada di glosarium selalu diproses lebih dulu.
- **Akronim** hanya diabaikan jika semua huruf kapital dan jumlah hurufnya
  ≤ 6 (mis. `CNN`, `LSTM`, `COVID-19`). Akronim yang ada di glosarium tetap
  diklasifikasikan menurut glosarium.
- **Nama CamelCase** dideteksi dari kapital setelah huruf kecil
  (`PostgreSQL`, `JavaScript`, `macOS`). Kata yang hanya berawalan kapital
  (`Graphical`, `Pandoc`) tetap `unknown` dan perlu keputusan. Jika nama itu
  sudah ada di glosarium (mis. `Python`, `PostgreSQL`), glosarium yang menang.
- **Konteks** adalah 8 token dipisah spasi sebelum dan sesudah, bukan 8 kata
  linguistik. Tanda baca menempel pada token.
- **Bagian yang dilewati.** Paragraf ber-style `Bibliography` dilewati karena
  italic di daftar pustaka berasal dari CSL, bukan keputusan istilah. Isi
  field, `w:instrText`, hyperlink eksternal, footnote/endnote, komentar, dan
  bagian yang tidak dimuat python-docx tidak dipindai.
- **`status` glosarium tidak dipakai** untuk memfilter. Baris
  `status=review` tetap diperlakukan sesuai kolom `italic`.
- **Deterministik.** Laporan tidak memuat timestamp; urutan tabel berdasarkan
  jumlah kemunculan lalu kunci. Pemanggilan berulang pada input yang sama
  menghasilkan isi yang sama.
- **Bukan pengganti `verify`.** Audit tidak memeriksa style `IstilahAsing`
  yang salah, bahasa `en-US`, atau penanda `{{?…?}}`. Jalankan
  `tools/istilah.py verify` untuk invarian tersebut.

## Tes

```powershell
.venv\Scripts\python.exe -m pytest tests\test_audit_istilah.py -q
```

Tes membuat fixture DOCX sementara dengan python-docx dan memeriksa kategori,
pengabaian akronim, ekstraksi body/tabel/header/footer, konteks 8 kata,
determinisme laporan, serta exit code `0`/`2`.
