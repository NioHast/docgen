# Pipeline Proposal Tesis MSI UNDIP

Dokumen ini menjelaskan pipeline proposal tesis Magister Sistem Informasi
UNDIP yang terpisah dari pipeline tesis/skripsi. Preset proposal mengikuti
kerangka resmi pada `acuan/re/07-panduan-msi.md` §7 dan tetap memakai mesin
build DOCX yang sama.

## Struktur

```text
proposal/
|-- metadata.yml
|-- cover.md
|-- chapters/
|   |-- 1-pendahuluan.md
|   |-- 2-tinjauan-pustaka.md
|   |-- 3-metode-penelitian.md
|   `-- 4-jadwal-penelitian.md
`-- gambar/
    `-- .gitkeep
```

| Berkas | Isi |
| --- | --- |
| `proposal/metadata.yml` | Judul, penulis, NIM, institusi, fakultas, tahun, dan preset `undip-msi-proposal`. Tidak memuat abstrak atau kata pengantar. |
| `proposal/cover.md` | Hanya arahan daftar isi (tanpa prosa Kata Pengantar). `build-docx.sh` memakai berkas ini saat metadata berada di `proposal/`. |
| `proposal/chapters/1-pendahuluan.md` | 1.1 Latar Belakang, 1.2 Tujuan Penelitian, 1.3 Manfaat Penelitian. |
| `proposal/chapters/2-tinjauan-pustaka.md` | 2.1 Tinjauan Pustaka, 2.2 Dasar Teori. |
| `proposal/chapters/3-metode-penelitian.md` | 3.1 Bahan dan Alat Penelitian, 3.2 Prosedur Penelitian. |
| `proposal/chapters/4-jadwal-penelitian.md` | Matriks jadwal penelitian. |
| `proposal/gambar/` | Gambar proposal. Berkas gambar dirujuk dari Markdown dengan path relatif. |

Daftar Pustaka tidak ditulis manual. Sitasi memakai kunci BibTeX dari
`references.bib`, misalnya `[@pandoc2024]`, lalu `--citeproc` membentuk Daftar
Pustaka otomatis.

## Preset

Berkas `presets/undip-msi-proposal.yml` memakai nilai final berikut:

| Kunci | Nilai |
| --- | --- |
| Margin | atas 4 cm, bawah 3 cm, kiri 4 cm, kanan 3 cm |
| Font | Times New Roman 12 pt |
| Spasi baris | 1,5 baris (`normal_line_spacing: 360`) |
| Indentasi baris pertama | 1,25 cm |
| Heading 1/2/3 | Times New Roman 12 pt |
| Caption gambar/tabel | 12 pt; caption tabel rata kiri |
| `heading_chapter_prefix` | `""` |
| `heading_chapter_num_format` | `arabic` |
| `heading_sub_dot` | `true` |
| `heading_subsub_dot` | `true` |
| `cover_show_lecturer` | `false` |
| `cover_logo_width` | `4.7cm` |

Dengan konfigurasi tersebut, Heading 1 proposal menjadi `1. PENDAHULUAN`,
bukan `BAB I` dua baris.

## Cara build

Dari root repositori:

```bash
bash build-proposal.sh
```

Wrapper tersebut menjalankan:

```bash
export LAPORAN_METADATA=proposal/metadata.yml
export LAPORAN_REPORT_NAME=Proposal
bash build-docx.sh
```

Keluaran yang diharapkan adalah `Proposal.docx` di root repositori. Wrapper
tidak menduplikasi logika `build-docx.sh`; seluruh pemrosesan preset, sitasi,
finalisasi, caption, istilah, nomor halaman, dan ID paragraf tetap dilakukan
oleh `build-docx.sh`. Jalankan dari Git Bash dengan venv Windows di Windows,
atau dari bash dengan venv Debian di Debian/Linux; tidak ada interop lintas OS.

Build proposal memerlukan `build-docx.sh` yang mendukung variabel
`LAPORAN_METADATA` dan `LAPORAN_REPORT_NAME`, serta membaca bab dari
`proposal/chapters/`. Dukungan dua variabel tersebut saja belum cukup bila
`build-docx.sh` masih mencari `chapters/bab*.md` di root repositori.

## Perbedaan dengan tesis

| Aspek | Proposal | Tesis |
| --- | --- | --- |
| Penomoran bagian | `1.`–`4.` (angka Arab) | `BAB I`–`BAB V` (angka Romawi) |
| Jumlah bab | 4 | 5 |
| Abstrak | Tidak ada | Ada (Indonesia dan Inggris) |
| Kata pengantar | Tidak ada | Ada |
| Hasil dan pembahasan | Tidak ada | Ada |
| Kesimpulan dan saran | Tidak ada | Ada |
| Jadwal penelitian | Ada sebagai bab tersendiri | Tidak ada dalam kerangka |
| Front matter | Cover, persetujuan/pengesahan, daftar isi | Cover, pengesahan, pernyataan, kata pengantar, daftar, abstrak |
| Teks sampul | Proposal Tesis untuk Tesis S-2 / Program Studi Magister Sistem Informasi | Tesis / untuk memenuhi sebagian persyaratan / mencapai derajat Sarjana S-2 |

Perbedaan isi bab diterapkan lewat `proposal/chapters/`; perbedaan format
diterapkan lewat preset `undip-msi-proposal`.

## Batasan

- **Front matter masih memakai komponen yang ada.** Build belum memiliki
  `document_type: "proposal"`, `cover_kind: "proposal"`, atau
  `approval_kind: "persetujuan-proposal"`. Karena itu proposal masih memakai
  blok approval yang sama dengan tesis. KATA PENGANTAR tidak lagi ikut terbawa:
  `build-docx.sh` memakai `proposal/cover.md` yang hanya berisi arahan daftar
  isi bila metadata menunjuk ke `proposal/metadata.yml`.
- **Label pengesahan belum berubah.** Blok approval yang ada masih memakai
  label `LEMBAR PENGESAHAN`, bukan `HALAMAN PERSETUJUAN` khusus proposal.
- **Teks sampul belum otomatis bergaya proposal.** Teks "Proposal Tesis untuk
  Tesis S-2 / Program Studi Magister Sistem Informasi" belum dihasilkan oleh
  build; sampul masih mengikuti teks tesis.
- **Penomoran caption mengikuti Heading 1 bergaya `BAB ...`.** Alat
  `format_figures.py` mengenali nomor bab dari Heading 1 yang berawalan
  `BAB`. Heading proposal `1. PENDAHULUAN` belum dikenali sebagai bab, sehingga
  nomor caption proposal perlu diperiksa secara manual sampai dukungan
  penomoran proposal ditambahkan.
- **Gaya sitasi mengikuti CSL build.** `build-docx.sh` memakai
  `refs/undip-msi.csl` (turunan APA 7, author-date) selama preset tidak
  menentukan kunci `csl:`. Preset proposal tidak mengunci CSL tersendiri.
- **Daftar isi dan nomor halaman** tetap mengikuti pipeline DOCX yang ada.
  Perbedaan format front matter proposal belum diterapkan otomatis.
- **Penemuan bab mengikuti direktori metadata.** `build-docx.sh` membaca
  `proposal/chapters/` bila `LAPORAN_METADATA` menunjuk ke
  `proposal/metadata.yml`; `LAPORAN_CHAPTERS` tetap dapat menimpa direktori
  tersebut secara eksplisit.
