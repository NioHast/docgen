# Data paket (`src/docgen/data`)

## Tujuan

Folder ini menyimpan data deklaratif yang dibaca saat runtime: format tampilan,
struktur dokumen, template front matter, dan glosarium. Nilainya bukan kode:
tidak ada cabang logika, import, atau perhitungan di sini. Perubahan data
mengubah output build, jadi perlakukan seperti kontrak.

## Ownership

- [Kontrak config](../../../docs/dev/contracts/config.md) adalah sumber
  kebenaran skema `format.yml`, `structure.yml`, dan front matter. README ini
  tidak mendefinisikan key baru.
- ID format dan struktur adalah nama direktori. Menambah format atau struktur
  berarti menambah direktori yang sesuai, data valid, dan pembaruan kontrak
  serta tes.
- Nilai format dimiliki pemilik format; nilai urutan dan struktur dimiliki
  pemilik struktur; keputusan istilah dimiliki peninjau glosarium. Jangan
  menambah file ad hoc di folder ini.
- Sumber kebenaran nilai: `formats/<id>/format.yml`,
  `structures/<id>/structure.yml`, `glossary/istilah.tsv`, dan aset di
  direktori yang sama.

## Struktur YAML

- `formats/<id>/format.yml` mengatur nilai visual: `page`, `font`,
  `headings`, `captions`, `figures`, `code`, `bibliography_style`,
  `citation`, dan `assets`. Semua dimensi memakai satuan yang didukung
  kontrak; warna memakai heksadesimal `RRGGBB`.
- `structures/<id>/structure.yml` mengatur urutan dan pilihan: `front_matter`,
  `body`, `back_matter`, `toc`, `numbering`, `lists`, dan `cover`.
  `front_matter` dengan `source: template` merujuk ke
  `structures/<id>/templates/<nama>.md`.
- Aset format berada di direktori format: `citation.csl`, `logo.jpg`, dan
  `reference.docx`. Path aset relatif terhadap direktori format, path template
  relatif terhadap `templates/`, dan path bibliografi mengikuti kontrak
  (default format dapat ditimpa `document.md`). Semua path tidak boleh keluar
  dari direktori basisnya.

## Format glosarium

`glossary/istilah.tsv` adalah TSV UTF-8 dengan header wajib:

```tsv
term	italic
machine learning	yes
data	no
```

- Header harus persis `term<TAB>italic`; setiap baris data tepat dua kolom.
- Nilai `italic` hanya `yes` atau `no`.
- Baris kosong dan baris berawalan `#` diabaikan.
- Istilah duplikat (casefold) ditolak; pencocokan kata utuh dan
  case-insensitive.
- Glosarium pengguna di samping `document.md` bernama `istilah.tsv` dan
  menimpa entri paket dengan kunci yang sama.

## Larangan

- Jangan menaruh kode Python, logika kondisional, atau template executable di
  folder ini. Data hanya berisi nilai deklaratif.
- Jangan menambah key yang tidak dikenal kontrak; key mati adalah error.
- Jangan menulis output build, manifest, laporan, atau file sementara ke sini.
- Jangan menaruh kredensial, data pribadi, atau naskah pengguna di data paket.
- Jangan mengubah `reference.docx` atau `logo.jpg` tanpa memperbarui format
  dan tes terkait.

## Tautan

- [Kontrak config](../../../docs/dev/contracts/config.md)
- [Format dan struktur](../../../docs/dev/formats.md)
- [Peta repo](../../../docs/dev/repo-map.md)
- [Rencana refactor](../../../docs/dev/archive/refactor-plan.md)
- [README paket](../README.md)
