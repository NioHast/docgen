# Troubleshooting

Jalankan perintah `doctor` lebih dulu untuk memisahkan masalah perkakas dari
masalah naskah:

```bash
uv run --project <repo> docgen doctor
```

Perintah itu memeriksa Python, Pandoc, Word, dan `mmdc`. Exit code 1 berarti
dependensi wajib belum lengkap.

## Caption tabel atau gambar

Gejala:

```text
caption Markdown tidak valid:
- document.md:14: tabel tanpa caption; tambahkan baris ': Judul tabel'
- document.md:22: gambar tanpa alt text; tulis ![deskripsi gambar](path)
```

Tindakan:

1. Tambahkan baris `: Judul tabel` sebelum atau sesudah tabel.
2. Ganti `![](gambar/x.png)` menjadi `![Deskripsi gambar](gambar/x.png)`.
3. Jalankan ulang `check`.
4. Build ulang.

Jangan menambahkan caption kosong atau nomor manual. Nomor caption dibuat dari
Heading 1 dan urutan tabel/gambar.

## `mmdc` tidak ditemukan atau gagal render

Gejala:

```text
mmdc tidak ditemukan di PATH.
```

Tindakan:

```bash
node --version
npm install -g @mermaid-js/mermaid-cli
mmdc --version
```

Pastikan folder executable `mmdc` ada di `PATH`. Di Windows, folder global npm
biasanya `%APPDATA%\npm`. Bila `mmdc` ada tetapi render gagal, periksa pesan
`mmdc` pada error. Berkas PNG parsial dibersihkan dan build berhenti tanpa
output setengah jadi.

## Pandoc tidak ditemukan

Gejala:

```text
Pandoc tidak ditemukan; build DOCX tidak dapat dilanjutkan.
```

Tindakan:

1. Pasang Pandoc dari <https://pandoc.org/installing.html>.
2. Pastikan `pandoc --version` berhasil dari shell yang sama.
3. Jalankan `doctor` lagi.

Pipeline mencari `pandoc` di `PATH`, lalu di lokasi instalasi Windows yang
umum. Variabel `DOCGEN_PANDOC` atau `PANDOC` dapat menunjuk executable
eksplisit.

## Python terlalu lama

Gejala:

```text
Python 3.14.x (butuh >=3.15)
```

Tindakan:

```bash
uv python install 3.15
uv sync --extra dev
```

`pyproject.toml` mensyaratkan Python 3.15. `uv run --project <repo>` memakai
environment proyek dan tidak memakai Python global secara diam-diam.

## `ruamel.yaml` atau YAML tidak valid

Gejala:

- `ModuleNotFoundError: No module named 'ruamel'`
- `front matter tidak valid`
- `kunci YAML duplikat`

Tindakan:

```bash
uv sync --project <repo> --extra dev
```

Periksa juga:

- berkas harus UTF-8;
- front matter dimulai `---` di baris pertama dan ditutup `---`;
- gunakan spasi, bukan tab;
- jangan memakai anchor, alias, atau merge key;
- jangan menulis kunci duplikat.

## Word atau PDF

Gejala di Windows:

- `Microsoft Word tidak tersedia; PDF tidak dapat dihasilkan`
- `Word selesai tanpa error tetapi PDF tidak ditemukan`
- nomor halaman daftar isi masih `0`

Tindakan:

1. Pasang Microsoft Word desktop. Word Online tidak menyediakan COM.
2. Tutup DOCX atau PDF tujuan yang sedang dibuka aplikasi lain.
3. Jalankan ulang build.
4. Bila field belum diperbarui, buka DOCX di Word, perbarui field, simpan, lalu
   ekspor ulang.

`--target both` membutuhkan Word. Bila Word tidak ada, build berhenti sebelum
output kecuali memakai `--allow-missing-word`. Opsi itu menghasilkan DOCX dan
melewati PDF dengan peringatan. `--target pdf` tetap gagal tanpa Word karena
tidak ada output yang diminta.

## Debian dan Linux

Di Debian, PDF tidak didukung. Gunakan:

```bash
uv run --project <repo> docgen build document.md --target docx
```

DOCX di Debian bersifat best-effort. Pandoc dan stage Python berjalan, tetapi
finalisasi field Word tidak tersedia. TOC dan nomor halaman dapat tetap kosong
sampai DOCX dibuka dan diperbarui di Word. Jangan memakai LibreOffice sebagai
pengganti jalur PDF resmi.

## Path dan aset

- Gunakan pemisah `/`, termasuk di Windows.
- Path absolut, `..`, backslash, URL, dan data URI ditolak.
- Gambar harus berada di dalam direktori dokumen, biasanya `gambar/`.
- Bibliografi harus berekstensi `.bib` dan berada di direktori dokumen atau
  subdirektori.
- Bungkus path berspasi dengan tanda kutip di shell.
- Jalankan `check` setelah memindahkan berkas.

Gejala umum:

```text
berkas tidak ditemukan: gambar/diagram.png
path 'gambar' keluar dari direktori dokumen
bibliography harus berekstensi .bib
```

## Output terkunci atau gagal ditulis

Gejala:

```text
Permission denied
file is being used by another process
```

Tindakan:

1. Tutup Word, LibreOffice, atau PDF viewer yang membuka berkas output DOCX
   atau PDF (nama mengikuti `report_name`, misalnya `Tugas.docx` atau
   `Tugas.pdf`).
2. Pastikan direktori dokumen dapat ditulis.
3. Build ulang.

Pipeline menulis output secara atomic. Kegagalan tidak boleh meninggalkan DOCX
atau PDF setengah jadi di direktori tujuan.

## Istilah dan review file

Dengan `--terms`, hasil review ditulis ke `.laporan/istilah-baru.txt`. Bila
masih ada `{{?istilah?}}`, putuskan istilahnya:

1. Ganti penanda dengan istilah yang benar, atau
2. tambahkan entri ke `istilah.tsv` di samping `document.md`, lalu build ulang.

Kegagalan verifikasi istilah berarti ada pelanggaran style, misalnya istilah
dengan `italic: no` ditulis miring atau istilah `italic: yes` ditulis tegak.
Perbaiki naskah atau glosarium, bukan DOCX.

## Reconcile

`reconcile` mengembalikan exit code khusus:

| Exit | Arti |
| ---: | --- |
| 0 | Tidak ada perubahan manual. |
| 1 | Error input, manifest, atau DOCX. |
| 3 | Ada perubahan manual yang perlu ditinjau. |
| 4 | Ada pelanggaran paragraf terlindungi. |

Laporan default ada di `.laporan/reconcile.md`. Alat tidak mengubah DOCX,
manifest, atau Markdown. Terapkan sendiri perubahan yang disetujui ke
`document.md`, lalu build ulang.

## Bantuan lanjutan

- Periksa pesan `[ERROR]` lengkap; pesan menyebut path dan kode.
- Gunakan `--keep` untuk mempertahankan `.laporan-build/` dan intermediate
  DOCX.
- Baca [document-format.md](document-format.md) untuk aturan sumber.
- Baca [docs/dev/pipeline.md](../dev/pipeline.md) untuk urutan stage.
