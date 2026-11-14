# Batas Keamanan Resource

Dokumen ini mencatat batas resource yang diterapkan pada input yang tidak
tepercaya: package DOCX, helper XML/renderer PPTX, dan berkas `deck.yaml`.
Batas ZIP diperiksa dalam dua lapis: preflight EOCD/central directory sebelum
`ZipFile` dibuat, lalu pembacaan bertahap berbatas berdasarkan byte aktual.
Metadata `ZipInfo` tidak dipercaya sebagai bukti bahwa isi entry kecil. Tidak
ada entry ZIP yang ditulis ke disk saat validasi.

## Package DOCX

`autooffice.docx.package.io.read_zip` memakai helper bersama
`autooffice.common.zip`:

| Batas | Nilai | Konstanta |
| --- | --- | --- |
| Jumlah entry | 4.096 | `MAX_ZIP_ENTRIES` |
| Ukuran satu entry setelah dekompresi | 256 MiB | `MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES` |
| Total ukuran setelah dekompresi | 1 GiB | `MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES` |
| Rasio kompresi per entry (deklarasi dan aktual) | 200:1 | `MAX_ZIP_COMPRESSION_RATIO` |
| Denominator minimum rasio aktual | 64 byte | `ZIP_RATIO_MIN_COMPRESSED_BYTES` |
| Ukuran central directory | 16 MiB | `MAX_ZIP_CENTRAL_DIRECTORY_BYTES` |
| Potongan baca entry | 1 MiB | `ZIP_READ_CHUNK_BYTES` |

Preflight membaca EOCD atau ZIP64 EOCD, memeriksa jumlah entry dan ukuran
central directory, lalu memindai record central directory tanpa membuat
`ZipInfo`. Jumlah entry dari EOCD tidak dipercaya: record aktual dihitung ulang,
sehingga EOCD palsu yang mengklaim satu entry tidak melewati batas.

Setelah preflight, setiap entry dibaca lewat `archive.open()` dan `read(1 MiB)`
berulang. Batas per-entry dan total dihitung dari byte hasil dekompresi; arsip
ditolak segera setelah byte aktual melewati batas, meskipun `file_size` di
central directory menyatakan nol atau kecil. Rasio kompresi juga dihitung dari
byte aktual: pembaca menghitung byte mentah yang dibaca dari arsip dan byte
hasil dekompresi, lalu menolak entry yang melebihi 200:1. Denominator rasio
memakai minimum 64 byte agar entry sangat kecil tidak memicu rasio palsu.
Pemeriksaan metadata tetap dipakai sebagai preflight murah, tetapi bukan
satu-satunya dasar keputusan. Pelanggaran melempar `PackageError` dengan kode
`PKG-ZIP-LIMIT`. Pesan menyebut entry yang bermasalah dan nilai batasnya.

## Helper XML dan ZIP PPTX

`autooffice.deck.render.pptx.xml` memakai batas ZIP yang sama dari
`autooffice.common.zip` untuk paket PPTX dan workbook XLSX tertanam.
Pelanggaran melempar `PptxRenderError` dengan kode `PPTX-ZIP-LIMIT`.
Pemeriksaan berlaku untuk `forbidden_node_paths`, `validate_package`,
`normalize_embedded_workbooks`, `content_hash`, dan workbook di dalamnya.

Semua part XML di-parse dengan parser yang dikonfigurasi:

- `resolve_entities=False`
- `no_network=True`
- `load_dtd=False`
- `dtd_validation=False`
- `attribute_defaults=False`
- `recover=False`
- `huge_tree=False`

Part yang memuat `DOCTYPE`, internal DTD, atau node entity ditolak dengan
`PptxRenderError` berkode `PPTX-XML-UNSAFE`, sebelum traversal node.

Kontrak import melarang `autooffice.deck.render.pptx` mengimpor
`autooffice.docx`. Karena itu parser aman DOCX dan PPTX dijaga ekuivalen dan
diuji terpisah; memindahkannya ke modul bersama memerlukan perubahan kontrak
import terlebih dahulu.

## Berkas YAML deck

`autooffice.deck.model.loader` membatasi input sebelum dan sesudah safe load:

| Batas | Nilai | Konstanta |
| --- | --- | --- |
| Ukuran berkas/teks | 5 MiB | `MAX_DECK_BYTES` |
| Jumlah dokumen YAML | 1 | `MAX_DECK_DOCUMENTS` |
| Jumlah alias (`*anchor`) | 100 | `MAX_DECK_ALIASES` |
| Kedalaman struktur | 64 | `MAX_DECK_NESTING_DEPTH` |

Berkas dibaca paling banyak `MAX_DECK_BYTES + 1` byte; jika masih ada byte
tambahan, berkas langsung ditolak. Ukuran teks UTF-8 juga diperiksa sebelum
parse. Jumlah dokumen dibatasi dengan `islice` sehingga dokumen berikutnya
tidak pernah dikonstruksi. Alias dihitung dari event parser tanpa membangun
objek Python. Kedalaman memakai `YAML.max_depth` milik ruamel dengan
`YAML(typ="safe", pure=True)` agar batas tetap berlaku pada implementasi Python
murni. Pelanggaran melempar `DeckLoadError` (subclass `DeckSchemaError`) dengan
pesan yang menyebut batas dan saran perbaikan.

## Verifikasi

- `tests/docx/test_package_security.py`
- `tests/deck/render/pptx/test_xml_security.py`
- `tests/deck/model/test_loader_limits.py`

Fixture ZIP bom berukuran di bawah 64 KB: central directory mengklaim
`file_size = 0` sementara data aktual 2 MiB. Test memakai batas entry rendah
dan potongan baca kecil, lalu memastikan pembaca menolak setelah byte aktual
melewati batas tanpa pernah memakai `archive.read`. Test rasio aktual memakai
payload 2 MiB yang sangat kompresibel; dengan `file_size = 0` dan compressed
size 2.049 byte, pembaca menolak pada rasio aktual 207:1. Test entry-count
memalsukan jumlah entry di EOCD dan memasang monkeypatch pada
`zipfile.ZipFile` untuk membuktikan preflight menolak sebelum daftar `ZipInfo`
dibangun.
