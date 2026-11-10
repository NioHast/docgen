# Diagram Mermaid

Diagram ditulis langsung di `document.md` sebagai code fence Mermaid. Stage
`mermaid` mengganti blok itu menjadi PNG di workspace sebelum Pandoc berjalan,
sehingga DOCX memuat gambar biasa. Berkas sumber tidak diubah.

## Sintaks

````markdown
```{.mermaid caption="Diagram pipeline"}
flowchart LR
  A[document.md] --> B[Pandoc]
  B --> C[DOCX]
```
````

Aturan:

- atribut `caption` wajib dan tidak boleh kosong;
- isi diagram tidak boleh kosong;
- fence penutup wajib ada;
- fence biasa seperti `python`, `bash`, atau `json` tidak disentuh;
- caption menjadi alt text gambar, bukan nomor manual.

Blok di atas diganti secara internal menjadi:

```markdown
![Diagram pipeline](gambar/mermaid-<hash>.png)
```

Nomor `Gambar bab.n` diberikan stage caption DOCX. Jangan menulis nomor di
Markdown.

## Kebutuhan `mmdc`

Pasang Node.js, lalu Mermaid CLI:

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc --version
```

`mmdc` harus dapat ditemukan dari `PATH`. Di Windows, folder global npm
biasanya `%APPDATA%\npm`; pastikan folder itu ada di `PATH`. Periksa dengan:

```bash
uv run --project <repo> docgen doctor
```

`doctor` menampilkan status `mmdc`. Bila `mmdc` tidak ada tetapi dokumen
memuat diagram, build berhenti dengan pesan instalasi. Tidak ada PNG atau
Markdown setengah jadi yang ditulis.

## Saat build

```bash
uv run --project <repo> docgen build document.md --target docx
```

Alur stage:

1. `validate` memeriksa caption tabel dan alt text gambar.
2. `mermaid` mengekstrak blok, menghitung hash, dan merender PNG.
3. `front_matter` memakai Markdown hasil penggantian.
4. `pandoc` membaca Markdown itu dan menyisipkan PNG ke DOCX.

PNG sementara ditulis ke `.laporan-build/gambar/mermaid-<hash>.png` di
samping `document.md`. Workspace dihapus setelah build kecuali memakai
`--keep`.

## Cache dan hash

- Hash berasal dari isi Mermaid yang dinormalisasi dan opsi render.
- Nama berkas memakai 12 karakter pertama hash.
- Diagram identik dalam satu build hanya dirender sekali.
- Bila PNG dengan hash yang sama sudah ada di workspace, `mmdc` tidak dipanggil
  lagi.
- Perubahan isi atau opsi menghasilkan hash baru dan PNG baru.
- Blok yang sudah menjadi gambar tidak dianggap Mermaid pada proses berikutnya.

Dengan `--keep`, isi `.laporan-build/` dapat diperiksa. Jangan menyalin PNG
hasil render menjadi sumber; sumber tetap blok Mermaid di `document.md`.

## Batasan

- `check` tidak merender Mermaid. Caption dan isi blok baru diperiksa
  saat build.
- Tidak ada perintah render Mermaid terpisah. Render selalu bagian dari build.
- Opsi `mmdc` seperti tema dan skala tidak diekspos sebagai flag CLI. Nilai
  default dipakai.
- Diagram yang sangat besar tetap mengikuti batas `mmdc` dan waktu render.

Bila render gagal, lihat [troubleshooting.md](troubleshooting.md).
