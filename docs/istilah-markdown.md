# Preprocessing Istilah untuk PDF

Pipeline PDF (`build.sh` dengan Pandoc + Typst) tidak melewati
`tools/istilah.py` karena modul tersebut bekerja pada DOCX. Tanpa langkah
tambahan, istilah glosarium yang tegak di Markdown akan tetap tegak di PDF
walaupun DOCX sudah memakai italic. `tools/istilah_markdown.py` menutup celah
itu dengan memproses Markdown sebelum Pandoc.

## Perintah

```bash
python tools/istilah_markdown.py \
  --src chapters \
  --glossary writing/istilah.tsv \
  --out /tmp/chapters-pre
```

Alat ini menyalin setiap `*.md` di `--src` (hanya level teratas, tidak
rekursif) ke `--out`, lalu menulis versi yang sudah diproses. Direktori
keluaran dibuat bila belum ada. Jika `--out` sama dengan `--src`, perintah
ditolak dengan exit code `1` agar sumber tidak tertimpa.

## Aturan pemrosesan

- Istilah dengan `italic=yes` dibungkus `*...*`.
- Frasa terpanjang menang. Pada `training data dan data`, `training data`
  dipilih sebagai satu span dan `data` di dalamnya tidak diproses lagi.
- Istilah `italic=no` tetap dipertimbangkan sebagai penghalang. Misalnya
  `big data` yang tegak mencegah `data` di dalamnya ikut dimiringkan.
- Pencocokan case-insensitive, tetapi teks asli dipertahankan. `Graphical
  User Interface` dan `graphical user interface` sama-sama dikenali dan
  kapitalisasinya tidak diubah.
- Batas kata mengikuti `tools/istilah.py`: `data` tidak cocok di dalam
  `datang` atau `metadata`, dan spasi harus literal.

Area berikut tidak diubah:

- isi code fence (```` ``` ```` atau `~~~`);
- inline code (`` `...` ``);
- tautan inline `[...](...)`, gambar `![...](...)`, autolink, URL/email
  telanjang, sitasi `[@kunci]`, dan footnote `[^1]`;
- teks yang sudah berada di dalam `*...*` atau `_..._`;
- YAML frontmatter di awal berkas.

Alat ini idempoten: menjalankan ulang hasil preprocessing tidak menambah
bintang baru. Glosarium divalidasi dengan header dan nilai kolom yang sama
seperti `tools/istilah.py`; glosarium tidak valid membuat perintah berhenti
dengan exit code `1`.

## Integrasi ke `build.sh`

Sebelum Pandoc, `build.sh` menjalankan:

```bash
"$PYTHON_BIN" "$ISTILAH_MD_SCRIPT" \
  --src "$CHAPTERS_PATH" \
  --glossary "$GLOSSARY" \
  --out "$TMPDIR/chapters-pre"
```

Pandoc kemudian memakai berkas di `$TMPDIR/chapters-pre`, bukan `chapters/`
asli. `cover.md` tetap dipakai sebagai berkas terpisah. Build DOCX
(`build-docx.sh`) tidak berubah dan tetap memakai `tools/istilah.py`.

Build PDF memilih interpreter Python dari `.venv` bila tersedia (Windows/Git
Bash), lalu `python3`/`python`. Di WSL, Python Linux diutamakan agar path
`/mnt/c` dan `/tmp` bisa dibaca langsung. Glosarium dicari di
`writing/istilah.tsv` pada direktori keluaran atau direktori proyek.

## Tes

```bash
.venv/Scripts/python.exe -m pytest tests/test_istilah_markdown.py -q
```

Tes mencakup istilah `Graphical User Interface`, frasa terpanjang, code fence
dan inline code, teks yang sudah italic, tautan, frontmatter, penolakan
`--out` sama dengan `--src`, dan idempotensi.

## Batasan

- Hanya berkas `*.md` pada level teratas `--src` yang diproses.
- Istilah yang menempel langsung pada penanda `*` atau `_` (misalnya
  `*kata*pipeline`) dilewati agar tidak menghasilkan deretan bintang yang
  ambigu dan tidak idempoten.
- Istilah di dalam inline math atau HTML mentah belum dilindungi secara
  khusus; tulis istilah tersebut di luar markup bila perlu.
- Alat ini hanya menambahkan penanda italic Markdown. Pengaturan gaya akhir
  tetap mengikuti template Typst dan `italic=no` tidak dipaksakan menjadi
  tegak bila penulis sudah menulisnya miring secara manual.
