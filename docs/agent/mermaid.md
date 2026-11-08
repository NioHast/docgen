# Mermaid Inline

Diagram Mermaid ditulis langsung di Markdown sebagai code fence, lalu dirender
menjadi PNG oleh modul `src/laporan/mermaid.py`. Blok sumber diganti dengan
gambar Markdown biasa sehingga Pandoc dan pipeline caption tidak perlu
mengetahui Mermaid sama sekali.

## Sintaks

````markdown
```{.mermaid caption="Diagram pipeline"}
flowchart TD
  A --> B
```
````

Aturan:

- atribut `caption` **wajib** dan tidak boleh kosong;
- isi diagram adalah baris di antara fence pembuka dan penutup;
- fence biasa (Python, JSON, dan sebagainya) tidak disentuh;
- caption menjadi alt text gambar, bukan nomor manual.

Blok di atas diganti menjadi:

```markdown
![Diagram pipeline](gambar/mermaid-<hash>.png)
```

Nomor `Gambar bab.n` diberikan oleh pipeline caption DOCX yang sudah ada
(`format_figures.py`) dari alt text gambar. Jangan menulis nomor manual di
Markdown.

## Perintah

Dari akar repositori, jalankan modulnya langsung:

```bash
python src/laporan/mermaid.py \
  --src chapters \
  --out-dir . \
  --mmdc mmdc
```

Bila paket sudah terpasang (editable), perintah yang setara adalah
`python -m laporan.mermaid` dengan opsi yang sama.

| Opsi | Keterangan |
| --- | --- |
| `--src <file.md\|dir>` | Satu berkas Markdown atau direktori sumber. Direktori diproses rekursif untuk berkas `.md` saja. |
| `--out-dir <task>` | Folder tugas. PNG ditulis ke `<task>/gambar/`. |
| `--mmdc <path>` | Path executable Mermaid CLI. Default: cari `mmdc` di `PATH`. |
| `--theme <nama>` | Opsi `mmdc`, mis. `default`, `dark`, `forest`. |
| `--background <warna>` | Warna latar PNG. |
| `--size <piksel>` | Ukuran maksimum PNG (`--size` mmdc). |
| `--scale <angka>` | Skala render `mmdc`. |

Contoh Windows dengan executable eksplisit:

```bat
.venv\Scripts\python.exe src\laporan\mermaid.py ^
  --src chapters ^
  --out-dir . ^
  --mmdc "%APPDATA%\npm\mmdc.cmd"
```

`--src` boleh menunjuk satu berkas:

```bash
python src/laporan/mermaid.py --src chapters/bab3-metodologi.md --out-dir .
```

## Keluaran dan cache

- PNG ditulis ke `<out-dir>/gambar/mermaid-<hash>.png`.
- Hash adalah SHA-256 dari isi Mermaid yang sudah dinormalisasi ditambah opsi
  render; 12 karakter pertama dipakai sebagai nama berkas.
- Bila PNG dengan hash tersebut sudah ada, `mmdc` tidak dipanggil lagi.
- Diagram identik yang muncul beberapa kali hanya dirender sekali.
- Blok yang sudah diganti tidak dianggap blok Mermaid pada eksekusi berikutnya,
  sehingga perintah ini idempoten.
- Penulisan Markdown mempertahankan line ending dan BOM berkas asli.

Hanya berkas `.md` yang dibaca dan diubah. `.bib`, gambar lain, dan keluaran
build tidak disentuh.

## Kebutuhan `mmdc`

Pasang Node.js, lalu Mermaid CLI:

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc --version
```

Versi yang diverifikasi di Windows: `12.2.0`.

Bila `mmdc` tidak ditemukan saat ada diagram yang perlu dirender, perintah
berhenti dengan exit code `1` dan pesan instalasi. Tidak ada Markdown yang
ditulis dan tidak ada PNG yang dibuat. Pemeriksaan yang sama berlaku bila
caption hilang: seluruh berkas divalidasi lebih dulu sebelum render dimulai.

## Alur build

Mode satu berkas merender blok Mermaid secara otomatis:

```bash
python -m laporan build-file document.md
```

Mode folder menjalankan renderer lebih dulu, lalu build direktori proyek:

```bash
python src/laporan/mermaid.py --src chapters --out-dir . --mmdc mmdc
python -m laporan build <direktori-proyek>
```

Build menyalin `chapters/*.md` dan `gambar/` ke direktori sementara yang sama,
jadi path relatif `gambar/mermaid-<hash>.png` tetap valid. Modul ini tidak
mengubah TOC, aturan caption, atau skrip build. Format blok dan aturan caption
ada di [document-format.md](document-format.md).

## Tes

```bash
.venv/Scripts/python.exe -m pytest tests/test_mermaid.py -q
```

Tes mencakup ekstraksi blok, caption wajib, idempotensi hash, penggantian
Markdown, render dua diagram ke `gambar/`, cache antar-eksekusi, serta render
nyata dengan `mmdc` bila tersedia.
