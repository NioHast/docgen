# Glosarium Codebase

Glosarium ini menjelaskan istilah internal yang dipakai di kode, tes, dan
dokumentasi developer. Untuk glosarium istilah asing yang ditulis miring,
lihat [docx/terms.md](docx/terms.md); halaman itu adalah fitur naskah, bukan
daftar istilah arsitektur.

| Istilah | Arti | Rujukan |
| --- | --- | --- |
| ADR | Architecture Decision Record; catatan keputusan arsitektur yang mengikat. | [decisions/](decisions/) |
| Artefak | Nilai yang dihasilkan satu stage dan diteruskan ke stage lain melalui context; bukan selalu file output. | [contracts/stage-api.md](contracts/stage-api.md) |
| c14n | Canonical XML; bentuk ternormalisasi untuk membandingkan `document.xml` dan menghitung hash. | [docx/package.md](docx/package.md) |
| `DocumentPackage` | Representasi paket DOCX di memori: part, XML terparse, relationship, dan operasi load/save. | [docx/package.md](docx/package.md) |
| Front matter | Blok YAML di awal `document.md` yang memuat metadata, `format`, dan `structure`. | [formats.md](formats.md) |
| Format | Data tampilan di `format.yml`: halaman, font, heading, caption, kode, sitasi. | [formats.md](formats.md) |
| Golden invariant | Baseline hash atau fingerprint output yang dipakai untuk mendeteksi regresi. | [testing.md](testing.md) |
| Kontrak | Spesifikasi API atau perilaku yang mengikat implementasi dan tes. | [contracts/](contracts/) |
| Manifest | `.laporan/manifest.json`; daftar paragraf, bookmark, hash teks, dan status perlindungan. | [adeu-integration.md](adeu-integration.md) |
| Marker | Label pytest yang memilih kelompok tes, misalnya `unit`, `integration`, `word`, atau `windows`. | [testing.md](testing.md) |
| Output dir | Direktori tujuan artefak pengguna: samping `document.md` atau `examples/<name>/out/`. | [pipeline/outputs.md](pipeline/outputs.md) |
| Paragraph ID | Bookmark `pNNNN` pada paragraf body untuk mencocokkan DOCX dengan manifest. | [docx/bookmarks.md](docx/bookmarks.md) |
| Part | Anggota paket OOXML/ZIP, misalnya `word/document.xml` atau `word/styles.xml`. | [docx/package.md](docx/package.md) |
| Pipeline | Orkestrator yang memuat dokumen, menjalankan stage berurutan, dan menyimpan hasil. | [pipeline/overview.md](pipeline/overview.md) |
| Reconcile | Pembandingan DOCX hasil edit manual dengan manifest untuk menghasilkan laporan tinjauan. | [adeu-integration.md](adeu-integration.md) |
| `reference.docx` | Template Word yang diturunkan dari `format.yml` dan dipakai Pandoc. | [docx/styles.md](docx/styles.md) |
| Relationship | Relasi OPC antarpart, misalnya `document.xml` ke header atau footer. | [docx/package.md](docx/package.md) |
| `report_name` | Field front matter wajib yang menentukan stem nama DOCX dan PDF. | [pipeline/outputs.md](pipeline/outputs.md) |
| Review file | `.laporan/istilah-baru.txt`; daftar istilah yang perlu diputuskan, bukan output dokumen. | [docx/terms.md](docx/terms.md) |
| Source scan | Pemetaan paragraf manifest ke berkas dan baris Markdown sumber. | [adeu-integration.md](adeu-integration.md) |
| Stage | Unit kerja pipeline dengan urutan, input, mutasi, dan hasil yang dideklarasikan. | [pipeline/stages.md](pipeline/stages.md) |
| Structure | Data urutan front matter, body, back matter, penomoran, TOC, dan daftar. | [formats.md](formats.md) |
| Workspace | Direktori kerja sementara `.laporan-build/` untuk artefak antara. | [pipeline/artifacts.md](pipeline/artifacts.md) |
