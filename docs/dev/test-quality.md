# Kualitas Test

Dokumen ini membahas pemilihan kasus test untuk repo ini: perilaku apa yang
layak dibekukan, perilaku apa yang sebaiknya dibiarkan bebas berubah, dan
bagaimana menilai test yang sudah ada. Fokusnya adalah keputusan desain test,
bukan perintah menjalankan suite. Untuk perintah, marker, dan invariant golden
baseline, lihat [testing.md](testing.md).

## Daftar isi

- [Tujuan dan posisi](#tujuan-dan-posisi)
- [Prinsip inti](#prinsip-inti)
- [Layak dijadikan test](#layak-dijadikan-test)
- [Tidak layak atau perlu hati-hati](#tidak-layak-atau-perlu-hati-hati)
- [Test smells](#test-smells)
- [Parameterized test](#parameterized-test)
- [Mocking](#mocking)
- [Golden dan snapshot test](#golden-dan-snapshot-test)
- [Coverage dan mutation testing](#coverage-dan-mutation-testing)
- [Checklist keputusan](#checklist-keputusan)
- [Checklist review test](#checklist-review-test)
- [Contoh dari repo ini](#contoh-dari-repo-ini)
- [Pemeriksaan deterministik](#pemeriksaan-deterministik)
- [Hasil audit suite saat ini](#hasil-audit-suite-saat-ini)
- [Referensi resmi](#referensi-resmi)

## Tujuan dan posisi

Tiga dokumen punya peran berbeda. [testing.md](testing.md) menjawab bagaimana
menjalankan test, marker apa yang dipakai, dan invariant golden apa yang
dibekukan. Dokumen kontrak di [contracts/](contracts/config.md) menjawab
perilaku apa yang dijanjikan kepada pemanggil. Dokumen ini menjawab kasus
seperti apa yang layak dijadikan test dan kapan sebuah test lebih banyak biaya
daripada nilainya.

Kontrak tetap sumber kebenaran perilaku. Test yang gagal karena kontrak berubah
bukan alasan untuk langsung mengubah test. Periksa dulu apakah implementasi
atau kontrak yang salah, lalu perbaiki salah satunya secara sadar. Test tidak
boleh disesuaikan hanya agar suite hijau.

Dokumen ini tidak menetapkan jumlah test minimum atau target coverage. Biaya
dan risiko berbeda antarmodul sehingga keputusan yang baik selalu
mempertimbangkan keduanya.

## Prinsip inti

Test yang baik memberi sinyal ketika perilaku yang dijanjikan rusak. Test yang
sama juga tetap lulus ketika kode dirapikan tanpa mengubah perilaku. Dua sifat
itu menjadi kompas utama; sisanya adalah cara mencapainya.

| Prinsip | Arti praktis |
| --- | --- |
| Perilaku, bukan implementasi | Assert hasil yang terlihat pemanggil, bukan nama helper atau urutan pemanggilan internal. |
| API publik | Uji permukaan yang dijanjikan: fungsi package, CLI, skema config, dan artefak output. Helper privat diuji lewat efeknya, kecuali ada alasan kuat. |
| State, bukan interaksi | Assert keadaan akhir. Interaksi hanya diperiksa bila interaksi itu sendiri adalah kontrak, misalnya penulisan berkas atau pemanggilan Word COM. |
| Structure-insensitive, behavior-sensitive | Refactor struktur internal tidak boleh memecahkan test. Perubahan perilaku harus memecahkannya. |
| Deterministik | Waktu, locale, urutan acak, jaringan, dan state global tidak boleh menentukan hasil. |
| Terisolasi | Test bisa dijalankan sendiri, berurutan acak, atau paralel tanpa saling memengaruhi. |
| Spesifik | Satu test punya satu alasan utama untuk gagal. Assertion menunjukkan nilai yang diharapkan dan yang diterima. |
| Terbaca | Nama test menyatakan perilaku. Susunan arrange, act, assert terlihat tanpa membuka implementasi. |
| DAMP over DRY | Descriptive And Meaningful Phrases lebih penting daripada menghapus semua duplikasi. Duplikasi kecil yang membuat skenario jelas dapat diterima. |

Beberapa prinsip saling bertukar. Test yang lebih predictive biasanya lebih
lambat dan lebih mahal karena memakai Word, Pandoc, `mmdc`, atau seluruh
pipeline. Test unit cepat, tetapi tidak memverifikasi integrasi di boundary.
Pilih level terendah yang masih dapat menangkap risiko yang sedang dijaga;
jangan memindahkan semua keyakinan ke level paling mahal.

"Test public API" bukan larangan menyentuh helper privat. Ada error path yang
hanya bisa dicapai lewat helper tertentu. Dalam kasus itu, uji helper tersebut
dengan sadar bahwa test akan ikut berubah saat implementasi berubah. Jangan
menganggap kestabilan helper privat sebagai kontrak publik.

## Layak dijadikan test

Gunakan daftar berikut sebagai saringan, bukan kewajiban. Satu perilaku cukup
diuji di level paling murah yang masih meyakinkan.

- **Kontrak publik dan perilaku yang dilihat pengguna.** Contohnya flag CLI,
  kode error domain, struktur DOCX yang dipakai pengguna, schema `format.yml`,
  dan isi manifest. Test di sini melindungi janji, bukan cara mencapainya.
- **Regresi yang pernah terjadi.** Bug yang sudah pernah lolos perlu test yang
  mereproduksi kondisi awalnya. Test regresi yang baik gagal pada kode lama dan
  lulus pada perbaikan, tanpa bergantung pada detail perbaikan.
- **Boundary dan error path.** Input kosong, bagian XML yang hilang, nilai
  negatif, tipe salah, dan batas ukuran adalah sumber bug yang umum. Assert
  kode error domain, bukan sekadar "melempar exception".
- **Invariant data dan format.** Urutan elemen OOXML yang diwajibkan schema,
  field daftar isi, target relationship, dan hash manifest adalah kontrak data.
  Tulis invariant yang dilindungi secara eksplisit agar kegagalan mudah dibaca.
- **Idempotency.** Operasi yang dijalankan dua kali harus menghasilkan keadaan
  yang sama. Package roundtrip, stage berulang, dan hash XML kanonis adalah
  contoh yang layak diuji.
- **Integrasi dengan boundary eksternal.** Pandoc, Word COM, `mmdc`, dan
  filesystem berperilaku di luar kendali repo. Satu test kontrak pada boundary
  nyata lebih bernilai daripada banyak test unit yang memalsukan semuanya.
- **Trust dan security boundary.** Pastikan kode pipeline hanya berasal dari
  package, input pengguna tidak dieksekusi, dan path tidak keluar dari direktori
  yang diizinkan. Test seperti ini melindungi properti yang tidak terlihat di
  output normal.
- **Golden output bila output adalah produk.** DOCX dan PDF adalah produk
  pengguna. Bekukan invariant yang penting, misalnya jumlah halaman, ukuran
  halaman, field daftar isi, atau teks kunci, bukan seluruh byte berkas.

## Tidak layak atau perlu hati-hati

Tidak semua pola di bawah ini salah. Beberapa tetap sah bila ada alasan
eksplisit dan biaya perawatannya diterima. Tabel ini membantu memilih
alternatif yang lebih tepat sebelum menambah test.

| Pola | Alasan | Alternatif yang lebih baik |
| --- | --- | --- |
| Menguji stdlib atau framework | Python, pytest, lxml, dan zipfile sudah punya test sendiri. Test duplikat menambah biaya tanpa menambah keyakinan. | Uji perilaku repo di boundary: adapter, validasi, dan pemetaan error. |
| Tautologi | Assert konstanta ke dirinya sendiri, atau menghitung expected dengan rumus yang sama dengan implementasi, tidak bisa gagal saat perilaku rusak. | Pakai nilai expected independen, invariant, atau fixture yang dibuat manual. |
| Getter dan delegasi trivial | Method yang hanya mengembalikan field atau meneruskan argumen tidak punya keputusan untuk diuji. | Uji di pemanggil yang memakai nilai itu, atau saat getter mulai punya logika. |
| Detail privat | Nama helper, urutan pemanggilan internal, dan struktur objek internal berubah saat refactor yang aman. | Assert efek yang terlihat publik; sentuh privat hanya bila itu satu-satunya seam yang masuk akal. |
| Duplikasi test di level lain | Perilaku yang sama diuji unit dan integration menambah waktu serta perawatan ganda. | Pilih satu level paling murah yang masih meyakinkan; simpan test integration tipis bila perlu. |
| Snapshot seluruh output tanpa invariant | Perubahan format yang tidak penting memecahkan test, dan diff besar jarang dibaca serius. | Assert field, elemen, atau hash kanonis tertentu yang punya alasan jelas. |
| Over-mock | Mock yang terlalu banyak membuat unit yang diuji tidak benar-benar berjalan; test hanya memeriksa koreografi mock. | Mock hanya boundary eksternal; biarkan kolaborator internal berjalan nyata. |
| Dead code atau API yang sudah dihapus | Menguji perilaku kode mati membuat kode itu tetap dipertahankan. Pengecualian: test kontrak ketiadaan API justru menjaga penghapusan. | Hapus test yang mengeksekusi kode mati. Pertahankan test yang memastikan nama lama tidak muncul lagi. |
| Test yang tidak mungkin gagal | Assertion terlalu lemah, error ditelan, atau mock selalu mengembalikan nilai yang diharapkan. | Buat test gagal secara sengaja pada implementasi rusak sebelum mengandalkannya. |
| Test environment-specific tanpa nilai kontrak | Locale mesin, versi Word, path absolut, atau urutan filesystem membuat hasil berubah tanpa perilaku rusak. | Normalisasi input, pakai `tmp_path`, tandai marker, dan uji invariant yang stabil. |

## Test smells

Nama smell di bawah dipinjam dari xUnit Test Patterns. Smell adalah gejala yang
perlu diperiksa, bukan vonis bahwa test tertentu buruk.

| Smell | Gejala | Dampak | Perbaikan |
| --- | --- | --- | --- |
| Fragile Test | Test gagal saat refactor yang tidak mengubah perilaku, misalnya karena urutan atribut XML atau nama helper berubah. | Sinyal palsu, test sering dilonggarkan, dan kepercayaan pada suite menurun. | Assert perilaku atau invariant; normalisasi bagian yang tidak relevan; persempit cakupan test. |
| Assertion Roulette atau Eager Test | Banyak assertion dalam satu test tanpa pesan, atau satu test menjalankan beberapa skenario sekaligus. | Lokasi kegagalan sulit diketahui dan diagnosis menjadi lambat. | Pisahkan per perilaku, beri pesan assertion, dan batasi satu alasan utama gagal per test. |
| Obscure Test atau Mystery Guest | Setup jauh dari test, nilai ajaib tanpa nama, atau fixture eksternal yang tidak dijelaskan. | Pembaca tidak tahu perilaku apa yang sedang diuji. | Susun data penting di dalam test, beri nama konstanta, dan jelaskan fixture di dekat pemakaian. |
| Erratic Test | Hasil berubah antarjalankan karena waktu, urutan, jaringan, atau state bersama. | Test diabaikan atau dianggap gagal acak sehingga regresi nyata ikut tersembunyi. | Isolasi dengan `tmp_path`, suntikkan waktu, hindari jaringan, dan bersihkan state global. |
| Slow Tests | Suite butuh menit karena selalu memanggil Word, Pandoc, atau `mmdc`. | Umpan balik lambat, test dilewati, dan commit kecil terhambat. | Pisahkan marker, kecilkan fixture, pakai fake di unit, dan jalankan test mahal di gate. |
| Test Code Duplication | Setup dan assertion disalin dengan sedikit perbedaan di banyak tempat. | Perbaikan harus diulang dan salinan mulai menyimpang. | Pakai fixture, helper, atau parametrize yang menyembunyikan noise, bukan perilaku. |

## Parameterized test

Parameterized test berguna ketika satu perilaku diuji dengan beberapa input.
Setiap kasus harus mewakili kelas perilaku yang berbeda, bukan variasi kosmetik
dari jalur yang sama.

- Bedakan batas dan error path: nilai minimum, maksimum, kosong, hilang, tipe
  salah, dan nilai di luar rentang. Kasus seperti ini lebih bernilai daripada
  menguji banyak nama yang semuanya masuk ke cabang yang sama.
- Jangan menduplikasi path yang sudah diuji test lain. Jika satu kasus butuh
  assertion atau setup berbeda, pisahkan menjadi test tersendiri.
- Beri id yang terbaca atau susun parameter sehingga pesan gagal menyebut kasus
  yang salah. Pesan "gagal di parameter 3" tidak membantu tanpa melihat kode.
- Jangan memaksa satu matriks besar untuk perilaku yang tidak berhubungan.
  Matriks besar sulit dibaca dan sering menutupi kasus yang benar-benar penting.
- Contoh di repo: `tests/unit/test_docx_page.py` memakai parameter untuk ukuran
  portrait, landscape, atribut yang hilang, dan atribut bukan bilangan bulat.
  Setiap kelompok mewakili kegagalan yang berbeda.

Lihat [pytest parametrize](references.md#registry) untuk sintaks dan opsi id.

## Mocking

Mock adalah alat untuk memotong boundary yang mahal atau tidak deterministik.
Mock bukan alat untuk mengganti kolaborator internal yang justru ingin diuji.

Boundary eksternal yang biasa dimock atau difake di repo ini:

- Word COM, karena Word hanya ada di Windows dan sulit dijalankan di CI.
- Pandoc dan `mmdc`, karena keduanya proses eksternal dengan versi berbeda.
- Filesystem, hanya untuk kegagalan yang sulit dibuat nyata, misalnya izin
  ditolak atau disk penuh. Untuk perilaku normal, `tmp_path` lebih baik karena
  file benar-benar ditulis dan dibaca.
- Waktu, jaringan, dan environment variable, bila nilainya memengaruhi hasil.

Aturan praktisnya:

- Mock di seam yang dimiliki repo, misalnya adapter Word atau pemanggil proses.
  Assert kontrak seam tersebut, bukan urutan pemanggilan helper internal.
- Jangan memock value object, dataclass, atau struktur data sederhana. Pakai
  objek nyata agar test menguji perilaku sebenarnya.
- Interaction assertion sah bila interaksi itu sendiri adalah kontrak. Contohnya
  memastikan pipeline tidak memanggil shell, atau memastikan adapter Word
  menerima path dan timeout yang benar.
- Jika satu test membutuhkan banyak mock untuk sekadar berjalan, level test atau
  desain seam perlu dipertanyakan. Pindahkan test ke level yang lebih tepat.
- Fake lebih baik daripada mock bila perilaku yang ditiru cukup sederhana.
  `tests/unit/test_office.py` memakai `FakeWordAdapter` tanpa COM, sedangkan
  `tests/unit/test_mermaid.py` memakai executable `mmdc` palsu untuk menguji
  proses, path output, dan kegagalan render.

Lihat [pytest fixtures](references.md#registry) untuk cara menyediakan fake dan
resource test yang bersih.

## Golden dan snapshot test

Golden test cocok ketika output adalah produk dan detail kecilnya penting,
misalnya DOCX atau PDF. Golden test tidak cocok sebagai pengganti invariant yang
tidak dipahami; snapshot besar tanpa daftar invariant hanya memindahkan
kebingungan ke diff.

Cara mengurangi brittleness:

- Normalisasi bagian yang tidak stabil: timestamp, path absolut, metadata
  dokumen, urutan zip, dan namespace prefix yang tidak bermakna.
- Assert invariant tertentu, bukan seluruh isi berkas. Contohnya jumlah field
  daftar isi, instruksi field, style paragraf, jumlah halaman, ukuran halaman,
  teks kunci, dan target relationship.
- Gunakan fixture kecil yang mewakili satu perilaku. Fixture besar memperlambat
  test dan membuat diff sulit ditinjau.
- Jelaskan alasan setiap hash. Hash berguna untuk idempotency atau canonical
  XML, tetapi hash tanpa penjelasan tidak memberi tahu apa yang sebenarnya
  dilindungi.
- Perbarui fixture hanya setelah memahami penyebab perubahan. Jangan regenerate
  golden agar test hijau tanpa memeriksa output.
- Pisahkan test yang membutuhkan Word atau Windows dengan marker dan skip
  eksplisit. Jangan biarkan test menjadi false-green ketika fixture tidak ada.

`tests/integration/test_golden_docx.py` adalah contoh golden yang menguji
invariant, bukan menyalin seluruh XML. `tests/integration/test_golden_pdf.py`
memakai invariant JSON dan skip eksplisit saat fixture PDF tidak tersedia.

## Coverage dan mutation testing

Coverage adalah diagnostik, bukan target. Angka coverage membantu menemukan
cabang yang belum dijalankan, tetapi tidak menjamin bahwa assertion-nya
berarti. File dengan coverage 100 persen tetap bisa punya test yang tidak
mungkin gagal saat perilaku rusak.

- Gunakan coverage untuk melihat error path dan cabang yang terlewat, terutama
  di modul dengan risiko tinggi.
- Jangan mengejar persentase dengan test yang hanya memanggil fungsi tanpa
  assertion. Itu menaikkan angka tanpa menambah keyakinan.
- Pengecualian seperti `if TYPE_CHECKING`, platform-specific branch, dan kode
  defensif yang tidak dapat dicapai perlu dikecualikan secara sadar, bukan
  dipaksa dieksekusi.
- Mutation testing opsional untuk modul kritis, misalnya hash manifest, urutan
  field, atau validasi path. Mutan yang bertahan menunjukkan assertion yang
  lemah, tetapi biaya menjalankannya tidak cocok untuk seluruh repo.
- Jalankan mutation testing pada subset modul dan interpretasikan hasilnya
  bersama review manusia. Angka mutan yang bertahan bukan target tersendiri.

Lihat [coverage.py](references.md#registry) dan [mutmut](references.md#registry)
untuk alat yang dipakai di luar gate utama.

## Checklist keputusan

Tujuh pertanyaan berikut diajukan sebelum menambah test baru. Jika ada jawaban
yang tidak memuaskan, pertimbangkan level test atau keputusan desainnya.

1. Kontrak apa yang dilindungi test ini, dan siapa pemakainya?
2. Bug pengguna apa yang terjadi jika perilaku ini rusak?
3. Bisakah test ini lulus meskipun perilaku yang dilindungi rusak?
4. Apakah refactor aman yang tidak mengubah perilaku bisa memecahkan test ini?
5. Sudah ada test di level lebih tepat yang melindungi perilaku yang sama?
6. Apakah pesan gagal cukup spesifik untuk menunjukkan penyebabnya?
7. Apakah test deterministik dan biayanya sebanding dengan risiko yang dijaga?

## Checklist review test

Reviewer test mencari sinyal, bukan jumlah baris. Hal yang biasa diperiksa:

- Nama test menyatakan perilaku yang diharapkan, bukan nama fungsi internal.
- Assertion memeriksa hasil yang terlihat pemanggil dan menyebut nilai yang
  diharapkan.
- Test akan gagal jika implementasi benar-benar rusak, bukan hanya jika nama
  helper berubah.
- Tidak ada ketergantungan pada urutan test, waktu nyata, jaringan, atau state
  global.
- Fixture minimal, dijelaskan, dan tidak menyembunyikan setup penting jauh dari
  test.
- Boundary dan error path diuji dengan kode error yang spesifik.
- Mock hanya berada di boundary eksternal; kolaborator internal berjalan nyata.
- Kasus parameterized mewakili perilaku berbeda dan tidak menduplikasi path.
- Golden test punya daftar invariant dan alasan untuk setiap hash atau snapshot.
- Test baru tidak menduplikasi test yang sudah ada di level lebih tepat.
- Pesan kegagalan cukup untuk memulai diagnosis tanpa membuka implementasi.
- Test dapat dibaca dan dipahami tanpa menebak maksud penulisnya.

## Contoh dari repo ini

Contoh berikut dipakai sebagai pola, bukan peringkat. Daftar ini bukan hasil
audit menyeluruh dan tidak boleh dibaca sebagai vonis untuk test lain.

| Test | Kontrak yang dilindungi | Kenapa menjadi contoh baik |
| --- | --- | --- |
| `tests/unit/test_docx_body_errors.py` | Pemetaan package tanpa `word/document.xml` ke error domain: `BookmarkError`, `CaptionError` dengan kode `CAPTION-NO-BODY`, `FieldError`, dan `SectionError`. | Fixture package minimal, assertion pada tipe dan kode error domain. Fokusnya boundary error, bukan detail XML. |
| `tests/unit/test_docx_page.py` | `content_width` dan `page_size` pada boundary ukuran halaman, margin, gutter, dan input tidak valid. | Parameterisasi memisahkan kasus batas dan error. Assertion memakai aritmetika independen dan kode `PAGE-WIDTH`. |
| `tests/unit/test_api_removed.py` | API dan alias yang sudah dihapus tidak muncul lagi. | Menguji kontrak penghapusan, bukan perilaku kode mati. Test sengaja memeriksa ketiadaan nama. |
| `tests/test_check_docs.py` | Perilaku checker dokumentasi: tautan rusak, daftar isi, registry duplikat, dan exit code. | Memanggil API publik checker dengan direktori sementara. Assertion menyebut berkas, baris, atau pesan yang spesifik. |

Beberapa pola perlu hati-hati, tetapi tetap bisa sah dalam konteks tertentu:

- **Snapshot XML penuh di test DOCX.** Sah bila stabilitas XML kanonis adalah
  kontrak, misalnya untuk idempotency, dan fixture-nya kecil. Di luar itu,
  assert elemen atau properti tertentu agar refactor yang tidak mengubah
  perilaku tidak memecahkan test.
- **Test helper privat.** Sah bila helper adalah satu-satunya seam untuk
  mencapai error path atau bila helper tersebut memang kontrak internal yang
  sedang distabilkan. Terima bahwa test akan berubah bersama implementasi, dan
  jangan memeriksa nama helper atau urutan pemanggilan internal.
- **Test yang bergantung pada Word, Pandoc, atau `mmdc`.** Sah sebagai test
  integrasi yang dijalankan di gate atau mesin khusus. Wajib memakai marker,
  skip eksplisit saat alat tidak ada, dan tidak menjadi satu-satunya bukti
  untuk perilaku yang bisa diuji dengan fake di level unit.
- **Test konstanta publik.** Sah bila konstanta seperti `PAGE_SIZES` adalah
  kontrak yang dibaca pemanggil. Nilainya harus berasal dari spesifikasi atau
  perhitungan independen, bukan disalin dari implementasi.

Jangan menuduh test tertentu buruk tanpa membaca tujuan, riwayat, dan biaya
perawatannya. Gunakan pola di dokumen ini untuk mengajukan pertanyaan, bukan
untuk memberi label.

## Pemeriksaan deterministik

Pemeriksaan deterministik memberi sinyal awal yang dapat diulang tanpa membuka
Word atau menjalankan build. Hasilnya bukan keputusan akhir: sinyal dipakai
untuk memilih test yang perlu dibaca, lalu reviewer memutuskan dengan konteks
kontrak. Tiga lapisan yang dipakai:

| Lapisan | Alat | Sifat | Status |
| --- | --- | --- | --- |
| Statis | Ruff PT dan `tools/dev/check_tests.py` | Membaca AST dan aturan gaya; tidak menjalankan test. | Dipakai sebelum suite. |
| Coverage | `pytest-cov` dan `tools/dev/check_coverage.py` | Membaca context per test dari `.coverage`; butuh suite dijalankan. | Dipakai setelah suite unit. |
| Mutation | `mutmut` atau alat sejenis | Mengubah kode untuk menguji kekuatan assertion. | Belum diimplementasikan; langkah berikutnya. |

Mutation testing belum menjadi bagian gate. Jalankan hanya pada subset modul
kritis setelah sinyal statis dan coverage stabil; lihat
[Coverage dan mutation testing](#coverage-dan-mutation-testing).

### Ruff PT

Delapan aturan `flake8-pytest-style` berikut aktif di `[tool.ruff.lint]`:
`PT010`, `PT011`, `PT012`, `PT014`, `PT018`, `PT019`, `PT027`, dan `PT028`.
Aturan ini menjaga `pytest.raises`, assertion, fixture, dan `parametrize` tetap
spesifik. Perintah fokus untuk suite test:

```bash
uv run --extra dev ruff check --select PT010,PT011,PT012,PT014,PT018,PT019,PT027,PT028 tests
```

Perintah di atas memeriksa aturan PT saja. Gate lint penuh tetap memakai
`uv run --extra dev ruff check .` seperti di [code-style.md](code-style.md).
Detail alasan tiap aturan ada di halaman yang sama; daftar resminya di
[Ruff flake8-pytest-style](references.md#registry).

### Pemeriksaan statis test

`tools/dev/check_tests.py` memindai fungsi `test_*` pada tingkat module dan
class, lalu memberi verdict berdasarkan sinyal AST. Alat ini tidak menjalankan
test dan tidak membaca niat penulis.

```bash
python tools/dev/check_tests.py tests --format json
python tools/dev/check_tests.py tests --format markdown
python tools/dev/check_tests.py tests --fail-on high
```

Default exit code adalah 0 meskipun ada temuan, karena temuan diperlakukan
sebagai warning. `--fail-on high|medium|low` menaikkan exit code menjadi 1 bila
ada finding non-`KEEP` pada level keyakinan tersebut atau lebih tinggi. Path
yang tidak ditemukan menghasilkan exit code 2. Opsi `--output PATH` menulis
laporan ke berkas, bukan stdout.

Bentuk JSON ringkas:

```text
{
  "schema_version": 1,
  "generated_by": "tools/dev/check_tests.py",
  "summary": {
    "total": int, "KEEP": int, "KEEP-WEAK": int,
    "MERGE": int, "TRIM": int, "REMOVE": int
  },
  "tests": [{
    "id": str, "file": str, "line": int,
    "verdict": "KEEP" | "KEEP-WEAK" | "MERGE" | "TRIM" | "REMOVE",
    "confidence": "low" | "medium" | "high",
    "signals": [str], "evidence": str, "suggested_action": str,
    "duplicate_of": str | null
  }]
}
```

`duplicate_of` hanya terisi pada sinyal `duplicate_body` dan menunjuk id test
pertama yang body AST-nya sama.

| Verdict | Arti | Sinyal yang memicunya |
| --- | --- | --- |
| `KEEP` | Tidak ada sinyal kelemahan. | Tidak ada. |
| `KEEP-WEAK` | Test berharga, assertion perlu diperkuat. | `broad_raises`, `exit_code_only`, `env_dependent`, `platform_skip_only`. |
| `MERGE` | Duplikat atau tumpang tindih. | `duplicate_body`, `integration_in_unit`. |
| `TRIM` | Sebagian berharga, sebagian detail implementasi. | `private_access`, `exact_snapshot`. |
| `REMOVE` | Tidak memberi sinyal regresi. | `no_assert`, `tautology`, `expected_from_sut`, `existence_only`. |

Verdict diambil dari sinyal dengan tingkat keparahan tertinggi, bukan jumlah
sinyal. Satu sinyal `no_assert` sudah cukup untuk `REMOVE`.

Batas alat ini:

- Deteksi duplikasi hanya exact AST setelah docstring dibuang. Dua test yang
  setara secara semantik tetapi berbeda literal, nama, atau susunan statement
  tidak ditandai duplikat.
- Alat tidak menilai niat test, kontrak yang dilindungi, atau apakah assertion
  benar-benar independen dari implementasi.
- Pola dinamis seperti helper yang dibangun saat runtime atau assertion di
  dalam library pihak ketiga dapat lolos.
- Temuan adalah bahan review. Jangan menghapus test hanya karena verdict
  `REMOVE`; periksa kontrak dan riwayatnya lebih dulu.

### Coverage context

`pytest-cov` dengan `--cov-context=test` mencatat test mana yang menjalankan
setiap baris. `tools/dev/check_coverage.py` membaca `.coverage` lewat
`CoverageData`, lalu menghitung baris unik dan baris yang tumpang tindih.

```bash
COVERAGE_CORE=ctrace uv run --extra dev pytest tests/unit \
  --cov=src/docgen --cov-context=test
python tools/dev/check_coverage.py \
  --coverage-file .coverage --source src/docgen --format json
```

`COVERAGE_CORE=ctrace` wajib dipakai. Core `sysmon` belum mendukung dynamic
context secara lengkap, sehingga context `|run` dapat hilang atau tidak stabil
dan analisis overlap menjadi salah. `check_coverage.py` hanya menghitung context
fase `|run`; context `setup` dan `teardown` diabaikan.

Default `--max-covered-lines` adalah 1000. Test yang melampaui batas itu
ditandai `god_test`. Naikkan batas hanya untuk test integrasi yang memang
menjalankan satu alur panjang, bukan untuk membuat gate hijau.

| Sinyal | Verdict dan keyakinan | Arti |
| --- | --- | --- |
| `no_unique_coverage` | `KEEP-WEAK` / low | Test tidak punya baris yang hanya dicakup dirinya sendiri. Ini informasi overlap, bukan vonis duplikat. |
| `god_test` | `TRIM` / medium | Test mencakup baris melebihi `--max-covered-lines`; pecah per perilaku bila memang terlalu luas. |
| `integration_only_lines` | high pada tingkat baris | Baris hanya dicakup test integration/e2e, bukan unit. Sinyal ini baru muncul bila context integration/e2e ikut dijalankan. |

Jika `no_unique_coverage` dan `god_test` muncul bersamaan, `god_test` menentukan
verdict `TRIM` medium; `no_unique_coverage` tetap menjadi informasi overlap.

`no_unique_coverage` lazim pada suite yang sehat karena beberapa test boleh
menyentuh jalur yang sama dengan assertion dan tujuan berbeda. Periksa isi test
sebelum menggabungkan atau menghapus. `integration_only_lines` adalah daftar
baris, bukan verdict test; tambahkan unit test atau pindahkan cakupan sesuai
risiko. Untuk memunculkan sinyal itu, sertakan `tests/integration` dan
`tests/e2e` pada invokasi pytest yang sama.

Contoh hasil audit saat tooling diperkenalkan: 584 test, 370 test dengan
`no_unique_coverage` (low), dan 52 `god_test`. Angka ini contoh yang akan
berubah ketika suite dan konfigurasi coverage berubah; jangan memakainya sebagai
baseline atau target.

### Urutan pemakaian

```text
ruff PT -> check_tests -> coverage -> review manual -> perbaiki
```

1. Jalankan Ruff PT untuk menangkap kesalahan bentuk yang paling murah.
2. Jalankan `check_tests.py` untuk memetakan kandidat test yang perlu dibaca.
3. Jalankan coverage context untuk melihat overlap dan test yang terlalu luas.
4. Review manual dengan [Checklist review test](#checklist-review-test) dan
   kontrak yang dilindungi.
5. Perbaiki test atau assertion. Jangan mengubah kode produksi hanya agar
   sinyal tooling hilang.

Untuk baseline lama, biarkan default warning dan baru pasang `--fail-on high`
setelah temuan high sudah diselesaikan. Gate yang terlalu ketat di awal membuat
tim menghapus test, bukan memperbaiki mutunya.

### Batas keseluruhan

Sinyal deterministik bukan keputusan akhir. `KEEP` tidak membuktikan test kuat,
dan `KEEP-WEAK`, `TRIM`, atau `REMOVE` tidak membuktikan test harus diubah.
Keputusan tetap memakai kontrak, riwayat bug, biaya perawatan, dan checklist di
dokumen ini. Mutation testing tetap langkah berikutnya dan belum menjadi gate.

## Hasil audit suite saat ini

Audit ini menilai seluruh 617 fungsi test di 49 berkas. Semua fungsi mendapat
verdict; angka di bawah adalah inventaris saat audit, bukan target yang harus
dikejar. Porsi dibulatkan ke satu desimal sehingga totalnya tidak selalu tepat
100%.

| Verdict | Jumlah | Porsi |
| --- | ---: | ---: |
| KEEP | 447 | 72,4% |
| KEEP-WEAK | 78 | 12,6% |
| MERGE | 39 | 6,3% |
| TRIM | 38 | 6,2% |
| REMOVE | 15 | 2,4% |

Sebaran per area:

| Area | Fungsi | KEEP | KEEP-WEAK | MERGE | TRIM | REMOVE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T1 Core/CLI/config/pipeline | 88 | 56 | 14 | 7 | 10 | 1 |
| T2 DOCX core | 123 | 93 | 12 | 8 | 7 | 3 |
| T3 DOCX features/TOC/lists/layout | 75 | 53 | 8 | 6 | 6 | 2 |
| T4 Stages terms/captions/code/equations | 69 | 54 | 9 | 4 | 2 | 0 |
| T5 Front matter/Pandoc/Mermaid/headings | 89 | 63 | 15 | 2 | 6 | 3 |
| T6 Office/PDF/integration/e2e | 62 | 45 | 8 | 4 | 3 | 2 |
| T7 Adeu/tools/golden fixtures | 111 | 83 | 12 | 8 | 4 | 4 |

Arti verdict:

| Verdict | Arti |
| --- | --- |
| KEEP | Layak dipertahankan. |
| KEEP-WEAK | Layak, assertion perlu diperkuat. |
| MERGE | Duplikat atau tumpang tindih; gabung. |
| TRIM | Sebagian berharga, sebagian detail implementasi. |
| REMOVE | Tidak memberi sinyal regresi. |

### 15 test yang disarankan REMOVE

Tabel berikut adalah kandidat penghapusan untuk Fase 1. Lokasi mengacu pada
berkas saat audit dilakukan.

| Berkas:baris | Test | Alasan |
| --- | --- | --- |
| `tests/unit/test_api_removed.py:186` | `test_private_duplikat_docx_hilang` | Menguji keberadaan helper privat; tautologis. |
| `tests/unit/test_docx_runs.py:240` | `test_strip_bold_is_consistent_with_xml_is_on` | Expected dihitung dari `is_on` yang juga dipakai implementasi. |
| `tests/unit/test_docx_runs.py:269` | `test_run_child_order_is_valid` | Urutan child sudah diassert di test lain. |
| `tests/unit/test_page_numbers.py:387` | `test_referenced_header_footer_parts_have_page_fields` | Nama menjanjikan page field, tetapi hanya cek `has_part`. |
| `tests/unit/test_stages_layout.py:480` | `test_content_width_dari_sectpr` | Duplikat `content_width` A4 di `test_docx_page.py`. |
| `tests/unit/test_stages_layout.py:492` | `test_content_width_tanpa_sectpr_menimbulkan_page_error` | Duplikat error `PAGE-WIDTH`. |
| `tests/unit/test_front_matter.py:425` | `test_stage_tidak_memakai_body_dokumen_saat_artifact_hilang` | Duplikat test artifact hilang. |
| `tests/unit/test_mermaid.py:459` | `test_mmdc_asli_merender_png` | Integration `mmdc` di unit suite. |
| `tests/unit/test_markdown_headings.py:167` | `test_number_markdown_idempoten_pada_input_yang_sudah_bernomor` | Duplikat idempotensi. |
| `tests/unit/test_office.py:447` | `test_tidak_ada_jalur_pdf_selain_word` | `hasattr` negatif + grep string. |
| `tests/packaging/test_repo_local.py:151` | `test_version_dan_check_tidak_mengubah_git_status` | Duplikat dua test sebelumnya. |
| `tests/test_check_docs.py:244` | `test_refactor_plan_archive_memuat_banner_archived` | Snapshot konten arsip, bukan perilaku checker. |
| `tests/test_check_prose.py:54` | `test_semua_pola_ada_di_rules_yml` | Tautologis: `ATURAN` dibaca dari `rules.yml`. |
| `tests/test_check_prose_docx.py:143` | `test_tes_bawaan_tetap_109` | Duplikat persis self-test. |
| `tests/unit/test_golden_fixtures.py:31` | `test_golden_fixture_files_exist` | Hanya cek keberadaan file. |

### Pola temuan prioritas

Sepuluh pola berikut muncul berulang dan menjadi prioritas perbaikan:

| # | Temuan | Tindakan |
| ---: | --- | --- |
| 1 | Error-path reconcile hanya assert exit 1. | Assert kode error domain, lalu exit code sebagai konsekuensinya. |
| 2 | `check_prose` punya test tautologis/white-box dan snapshot angka. | Ganti dengan assertion perilaku checker; jangan membaca `rules.yml` untuk membuktikan isi `rules.yml`. |
| 3 | Golden PDF hanya skip platform; perlu skip Word/Pandoc/`mmdc` yang eksplisit. | Tambahkan skip eksplisit per alat dan alasan agar tidak false-green di mesin tanpa fixture. |
| 4 | `test_pipeline_python` menulis ke `examples/.../out`; harus hermetic `tmp_path`. | Salin fixture ke `tmp_path` dan jalankan pipeline di sana. |
| 5 | Golden TOC unit menduplikasi integration golden DOCX. | Pertahankan satu level; jadikan unit test pemeriksaan field TOC yang terpisah. |
| 6 | Ukuran halaman A4/Letter/landscape diuji berulang di beberapa test. | Pusatkan matriks ukuran di `test_docx_page.py` dan hapus duplikat. |
| 7 | Test idempotensi bisa lulus meski implementasi no-op. | Assert perubahan pertama dan bandingkan hasil kedua dengan nilai konkret. |
| 8 | Snapshot nilai `config/format.yml` brittle. | Assert field semantik yang dikonsumsi pipeline, bukan salinan seluruh nilai. |
| 9 | Test API removed banyak `hasattr`/`is not None` tautologis. | Batasi pada simbol publik yang dijanjikan hilang; uji perilaku pengganti. |
| 10 | Metadata stage duplikat antar stage dan test `mmdc` berada di unit. | Satukan invariant metadata di level stage; pindahkan `mmdc` ke suite integration. |

### Rencana tindakan

Perbaikan dilakukan bertahap agar setiap fase dapat ditinjau sendiri:

1. **Fase 1a**: hapus 15 test REMOVE. **Status: sudah dijalankan** (15 test
   REMOVE sudah dihapus).
2. **Fase 1b**: gabungkan 39 test MERGE. **Status: belum dijalankan.**
3. **Fase 2**: perkuat 78 test KEEP-WEAK, terutama kode error, hitungan eksak,
   dan penghapusan tautologi. **Status: belum dijalankan.**
4. **Fase 3**: rapikan 38 test TRIM; pertahankan assertion semantik dan buang
   detail implementasi. **Status: belum dijalankan.**

Status faktual saat ini: 15 test REMOVE sudah dijalankan; 39 MERGE, 78
KEEP-WEAK, dan 38 TRIM masih backlog. Daftar di atas adalah backlog, bukan
alasan untuk langsung menghapus atau melonggarkan test tanpa membaca konteks.

## Referensi resmi

Label berikut terdaftar di [registry referensi](references.md#registry). Nama
label dipakai di dokumen ini dan di dokumen developer lain.

| Label | Alasan |
| --- | --- |
| [Google Testing Blog - Test Behavior](references.md#registry) | Alasan test berfokus pada perilaku dan bukan implementasi. |
| [Software Engineering at Google ch12](references.md#registry) | Trade-off unit, integration, dan end-to-end test di skala besar. |
| [Kent Beck Test Desiderata](references.md#registry) | Sifat test yang diinginkan dan trade-off antarsifat. |
| [xUnit Test Patterns - Test Smells](references.md#registry) | Katalog gejala test yang perlu diperiksa. |
| [xUnit Test Patterns - Fragile Test](references.md#registry) | Definisi dan perbaikan test yang rapuh terhadap refactor. |
| [xUnit Test Patterns - Assertion Roulette](references.md#registry) | Assertion tanpa pesan dan test yang terlalu ramai. |
| [pytest parametrize](references.md#registry) | Sintaks dan opsi test parametrik. |
| [pytest fixtures](references.md#registry) | Setup, isolasi, dan resource test. |
| [pytest good practices](references.md#registry) | Struktur test dan praktik pytest yang disarankan. |
| [Ruff flake8-pytest-style](references.md#registry) | Aturan pytest yang diperiksa Ruff untuk assertion dan raises. |
| [coverage.py](references.md#registry) | Pengukuran coverage sebagai diagnostik. |
| [coverage.py contexts](references.md#registry) | Format context dinamis yang dibaca dari `.coverage`. |
| [pytest-cov contexts](references.md#registry) | Opsi `--cov-context=test` untuk mencatat context per test. |
| [mutmut](references.md#registry) | Mutation testing opsional untuk modul kritis. |
