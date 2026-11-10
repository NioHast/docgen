# Code Style

Dokumen ini adalah kontrak gaya kode Python untuk `docgen`. Konfigurasi yang
dijalankan mesin ada di `pyproject.toml`; dokumen ini menjelaskan alasan,
contoh benar dan salah, serta batas pengecualian. Jika dokumen dan konfigurasi
berbeda, `pyproject.toml` menang dan dokumen ini harus diperbaiki.

Ruang lingkup Ruff adalah file Python di repo, termasuk `src`, `tests`, dan
`tools`, kecuali `docs/` yang dikecualikan. Mypy saat ini memeriksa
`src/docgen` sesuai `files` di `[tool.mypy]`. Gaya penulisan dokumen Markdown
diatur di [contributing.md](contributing.md).

## Daftar isi

- [Ringkasan alur kerja](#ringkasan-alur-kerja)
- [Prinsip umum](#prinsip-umum)
- [Format dan formatter](#format-dan-formatter)
- [Aturan Ruff](#aturan-ruff)
  - [Status aturan](#status-aturan)
  - [Tabel aturan](#tabel-aturan)
  - [Konflik aturan docstring](#konflik-aturan-docstring)
  - [Contoh aturan penting](#contoh-aturan-penting)
- [Docstring](#docstring)
- [Mypy](#mypy)
- [Import dan tipe](#import-dan-tipe)
- [Error](#error)
- [Test](#test)
- [XML](#xml)
- [Pengecualian dan noqa](#pengecualian-dan-noqa)
- [Verifikasi sebelum commit](#verifikasi-sebelum-commit)
- [Rujukan resmi](#rujukan-resmi)

## Ringkasan alur kerja

Jalankan dari root repo. Urutan ini dipakai lokal dan di gate otomatis.

| Urutan | Tahap | Perintah | Alasan |
| --- | --- | --- | --- |
| 1 | Format | `uv run --extra dev ruff format .` lalu `uv run --extra dev ruff format --check .` | Formatter menormalkan spasi dan pemenggalan baris lebih murah daripada memperbaiki manual. `--check` memastikan tidak ada perubahan yang tertinggal. |
| 2 | Lint | `uv run --extra dev ruff check .` | Lint cepat. Setelah format stabil, temuan lint bukan lagi noise format. |
| 3 | Tipe | `uv run --extra dev mypy` | Kontrak tipe diperiksa sebelum suite test yang lebih mahal. |
| 4 | Test | `uv run --extra dev pytest` | Perilaku diverifikasi terakhir karena paling lambat dan paling luas. |
| 5 | Dokumentasi | `uv run python tools/dev/check_docs.py` | Tautan relatif dan registry referensi valid. Jalankan bila docs berubah. |

Alasan urutannya: formatter lebih dulu agar lint tidak melaporkan spasi yang
akan segera diubah; lint sebelum mypy karena kesalahan import dan nama jauh
lebih cepat didiagnosis; mypy sebelum pytest karena kegagalan tipe lebih murah
daripada menjalankan seluruh suite; test terakhir karena cakupannya paling
luas.

## Prinsip umum

- Target bahasa adalah Python 3.15. Anotasi memakai sintaks modern dan tidak
  memerlukan `from __future__ import annotations` karena Python Enhancement
  Proposal (PEP) 649 sudah menjadi perilaku default.
- Panjang baris maksimum 100 kolom.
- Satu modul memiliki satu alasan perubahan. Jangan menambah abstraksi untuk
  kebutuhan yang belum ada.
- Tidak ada komentar historis, workaround, monkey patch, atau kode mati.
  Komentar menjelaskan perilaku sekarang dan alasan teknis yang masih berlaku.
- Konfigurasi adalah sumber kebenaran untuk aturan yang dapat dijalankan mesin.
  Dokumen ini tidak boleh menambah aturan yang tidak ditegakkan Ruff atau mypy.
- Perubahan gaya harus terpisah dari perubahan perilaku. Jangan mencampur
  reformat seluruh berkas dengan perbaikan logika di satu commit.
- Ruff dan mypy dipasang dari `[project.optional-dependencies].dev` dengan pin
  eksak. Versi yang dipakai saat ini adalah Ruff 0.17.4 dan mypy 2.4.1. Jangan
  bergantung pada tool global.

## Format dan formatter

Ruff formatter adalah satu-satunya penentu format. Jangan merapikan spasi,
indentasi, atau pemenggalan baris secara manual jika formatter dapat
melakukannya. Pengaturan format berasal dari `[tool.ruff]`: `line-length = 100`
dan `target-version = "py315"`. Lihat [Ruff configuration](references.md#registry)
dan [Ruff formatter](references.md#registry).

```bash
uv run --extra dev ruff format .
uv run --extra dev ruff format --check .
```

`docs/` dikecualikan dari Ruff melalui `extend-exclude = ["docs"]` di
`[tool.ruff]`. Dokumentasi memuat snippet Python ilustratif di code fence yang
tidak selalu mengikuti format kode yang dijalankan, sehingga formatter tidak
boleh menulis ulang docs. Pemeriksaan menyeluruh tetap memakai
`uv run --extra dev ruff format --check .`; path docs otomatis dilewati saat
Ruff menelusuri direktori. File docs yang disebut eksplisit tetap diperiksa,
tetapi itu bukan gate utama.

Aturan praktis:

- Indentasi empat spasi, tanpa tab.
- String memakai tanda kutip ganda kecuali kutip tunggal lebih jelas karena
  isi string memuat kutip ganda.
- Baris yang melewati 100 kolom dipenggal oleh formatter. Jangan menambah
  `# fmt: off` kecuali ada alasan struktural yang sempit, misalnya tabel data
  yang keterbacaannya rusak bila dipenggal.
- Dua baris kosong memisahkan definisi top-level. Satu baris kosong memisahkan
  method di dalam class. Formatter menangani keduanya.
- Trailing comma dipertahankan pada koleksi multi-baris agar diff tetap kecil.
- Akhir berkas selalu memakai satu newline.

## Aturan Ruff

Sumber aturan adalah `[tool.ruff.lint]` di `pyproject.toml`. Daftar aturan dan
pengaturannya ada di [Ruff rules](references.md#registry) dan
[Ruff settings](references.md#registry).

`select` memilih kelompok aturan yang dijalankan. `ignore` mematikan aturan
tertentu untuk seluruh repo. `per-file-ignores` mematikan aturan hanya pada
path yang disebut. Jangan menambah aturan baru lewat dokumen ini; ubah
`pyproject.toml` lebih dulu, lalu perbarui tabel.

Tautan pada kolom Link resmi menuju [registry referensi](references.md#registry);
URL resmi hanya disimpan di sana agar tidak terduplikasi.

### Status aturan

| Status | Arti |
| --- | --- |
| Dipakai | Aturan dijalankan dan pelanggarannya harus diperbaiki. |
| Diabaikan | Aturan tidak dijalankan, baik lewat `ignore` maupun karena Ruff menyelesaikan konflik dengan aturan lain. Alasan membedakan keduanya. |
| Dikecualikan | Aturan tetap dijalankan, tetapi path atau baris tertentu dikecualikan dengan `per-file-ignores` atau `# noqa` beralasan. |

### Tabel aturan

| Rule | Status | Alasan | Contoh | Link resmi |
| --- | --- | --- | --- | --- |
| `E` | Dipakai | pycodestyle error: spasi, indentasi, baris kosong, dan panjang baris maksimum 100 kolom. | `x=1` menjadi `x = 1` | [Ruff rules](references.md#registry) |
| `F` | Dipakai | pyflakes: nama tidak terdefinisi, import mati, dan variabel lokal mati. | `import os` tanpa pemakaian dihapus | [Ruff rules](references.md#registry) |
| `W` | Dipakai | pycodestyle warning: trailing whitespace dan baris kosong berlebih. | `x = 1 ` menjadi `x = 1` | [Ruff rules](references.md#registry) |
| `I` | Dipakai | isort: urutan dan pengelompokan import deterministik. | stdlib, pihak ketiga, lalu `docgen` | [Ruff rules](references.md#registry) |
| `UP` | Dipakai | pyupgrade: sintaks lama yang sudah digantikan Python 3.15. | `Optional[str]` menjadi `str \| None` | [Ruff rules](references.md#registry) |
| `B` | Dipakai | flake8-bugbear: mutable default, perbandingan, dan pola loop rawan bug. | `def f(x=[])` menjadi `def f(x: list[str] \| None = None)` | [Ruff rules](references.md#registry) |
| `SIM` | Dipakai | flake8-simplify: kontrol alur yang bisa disederhanakan tanpa mengubah perilaku. | `if a:` berisi `if b:` menjadi `if a and b:` | [Ruff rules](references.md#registry) |
| `RUF` | Dipakai | aturan khusus Ruff: konsistensi dan potensi bug. | `# noqa` tanpa kode atau tanpa efek ditandai `RUF100` | [Ruff rules](references.md#registry) |
| `BLE` | Dipakai | flake8-blind-except: `except` terlalu luas tanpa alasan. | `except:` menjadi `except ValueError as exc:` | [Ruff rules](references.md#registry) |
| `D` | Dipakai | pydocstyle: kualitas docstring. Subaturan yang diabaikan dan konflik dicatat di bawah. | `"""ringkasan"""` menjadi `"""Ringkasan."""` | [Ruff rules](references.md#registry) |
| `D101` | Diabaikan | Docstring class publik ditunda; prioritas ada pada docstring modul kunci. | `class Report:` boleh tanpa docstring pada tahap ini | [Ruff D101](references.md#registry) |
| `D102` | Diabaikan | Docstring method publik ditunda; kontrak method ada di docs dan test. | `def render(self):` boleh tanpa docstring pada tahap ini | [Ruff D102](references.md#registry) |
| `D103` | Diabaikan | Docstring fungsi publik ditunda; fungsi panjang tetap wajib lewat kontrak docstring. | `def helper():` pendek boleh tanpa docstring | [Ruff D103](references.md#registry) |
| `D105` | Diabaikan | Docstring magic method biasanya mengulang perilaku yang sudah jelas. | `def __len__(self):` tidak wajib docstring | [Ruff D105](references.md#registry) |
| `D107` | Diabaikan | Docstring `__init__` tidak menambah informasi bila class sudah jelas. | `def __init__(self, path):` tidak wajib docstring | [Ruff D107](references.md#registry) |
| `D202` | Diabaikan | Baris kosong setelah docstring fungsi tidak dipakai secara konsisten. | `"""Ringkasan."""` boleh langsung diikuti kode | [Ruff D202](references.md#registry) |
| `D401` | Diabaikan | Imperative mood Inggris tidak sesuai docstring bahasa Indonesia. | `"""Mengembalikan hasil."""` tidak perlu diubah menjadi `Return ...` | [Ruff D401](references.md#registry) |
| `BLE001` | Dikecualikan | Blind except hanya boleh di boundary opsional dengan `# noqa: BLE001 - alasan`; selain itu perbaiki tipe atau re-raise. | `except Exception:  # noqa: BLE001 - boundary` bukan pola umum | [Ruff BLE001](references.md#registry) |
| `SIM118` | Dikecualikan | `dict.keys()` hanya untuk objek yang bukan `Mapping`; Mapping memakai `in` langsung. | `if "docx" in artifacts:` bukan `if "docx" in artifacts.keys():` | [Ruff SIM118](references.md#registry) |
| `E741` | Dikecualikan | Per-file ignore untuk `O` di `names.py`; `O` adalah prefix namespace OOXML resmi, bukan variabel lokal. | `O = f"{{{O_NS}}}"` hanya di `src/docgen/docx/names.py` | [Ruff E741](references.md#registry) |
| `D203` | Diabaikan | Bertentangan dengan D211. Ruff mengabaikan D203 secara otomatis; jangan menambahkannya ke `ignore`. | Baris kosong sebelum docstring class salah karena D211 dipilih | [Ruff D203](references.md#registry) |
| `D211` | Dipakai | Tidak ada baris kosong antara `class` dan docstring. | `class A:` lalu `"""Ringkasan."""` tanpa baris kosong | [Ruff D211](references.md#registry) |
| `D212` | Dipakai | Ringkasan docstring multi-baris dimulai pada baris pertama setelah `"""`. | `"""Ringkasan.` lalu detail pada baris berikutnya | [Ruff D212](references.md#registry) |
| `D213` | Diabaikan | Bertentangan dengan D212. Ruff mengabaikan D213 secara otomatis; jangan menambahkannya ke `ignore`. | Ringkasan pada baris kedua setelah `"""` adalah salah | [Ruff D213](references.md#registry) |

`BLE001` dan `SIM118` adalah subaturan dari kelompok `BLE` dan `SIM` yang
dipilih, bukan aturan tambahan di luar `pyproject.toml`. `E741` berasal dari
`per-file-ignores`, sedangkan `D211` dan `D212` berasal dari kelompok `D`.

Subaturan `D` lain yang tidak tercantum di tabel tetap aktif karena
`select = ["D"]`: `D100`, `D104`, `D106`, `D200`, `D201`, `D204` sampai `D210`,
`D214`, `D215`, `D300`, `D301`, `D400`, dan `D402` sampai `D421`. Aturan itu
tidak punya pengecualian proyek; contoh dan deskripsi resminya ada di
[Ruff rules](references.md#registry).

### Konflik aturan docstring

Ruff 0.17.4 mencetak dua peringatan konfigurasi setiap kali dijalankan:

```text
warning: `incorrect-blank-line-before-class` (D203) and `blank-line-before-class` (D211) are incompatible. Ignoring `incorrect-blank-line-before-class`.
warning: `multi-line-summary-first-line` (D212) and `multi-line-summary-second-line` (D213) are incompatible. Ignoring `multi-line-summary-second-line`.
```

Peringatan itu normal dan bukan kegagalan. Kedua pasangan aturan saling
bertentangan; Ruff memilih satu aturan dan mengabaikan yang lain. `select`
tidak diturunkan dan `D203` serta `D213` tidak ditulis di `ignore` karena Ruff
sudah menanganinya.

Pilihan proyek:

- `D211` dipakai, `D203` diabaikan otomatis. Docstring class langsung menempel
  pada `class` tanpa baris kosong.
- `D212` dipakai, `D213` diabaikan otomatis. Ringkasan docstring multi-baris
  dimulai pada baris pertama setelah `"""`.

Alasannya: ringkasan langsung terlihat, tidak menambah baris kosong, konsisten
dengan docstring satu baris, dan tidak memisahkan kontrak dari definisi class
atau fungsi.

### Contoh aturan penting

Blind except hanya untuk boundary yang benar-benar tidak dapat dipersempit:

```python
# Salah: menelan semua error tanpa alasan.
try:
    relationships = package.relationships(DOCUMENT_PART)
except Exception:
    relationships = {}

# Benar: tangkap tipe yang relevan dan pertahankan rantai error.
try:
    relationships = package.relationships(DOCUMENT_PART)
except OSError as exc:
    raise PackageError("relationships tidak dapat dibaca") from exc

# Dikecualikan: boundary opsional, alasan wajib pada baris yang sama.
try:
    relationships = package.relationships(DOCUMENT_PART)
except Exception:  # noqa: BLE001 - package tanpa rels adalah boundary opsional
    relationships = {}
```

`SIM118` hanya berlaku untuk objek yang benar-benar `Mapping`:

```python
# Salah: Mapping sudah mendukung pemeriksaan kunci langsung.
if "docx" in artifacts.keys():
    ...

# Benar.
if "docx" in artifacts:
    ...

# Dikecualikan: artifacts adalah adapter non-Mapping.
if "docx" in artifacts.keys():  # noqa: SIM118 - Artifacts bukan Mapping
    ...
```

Gaya docstring D212 dan D211:

```python
# Benar: ringkasan pada baris pertama (D212), tanpa baris kosong (D211).
class Report:
    """Ringkasan kontrak laporan.

    Detail menjelaskan invariant dan error utama.
    """


# Salah: ringkasan pada baris kedua (D213).
class Report:
    """
    Ringkasan kontrak laporan.
    """
```

```text
# Salah: baris kosong sebelum docstring class (D203).
class Report:

    """Ringkasan kontrak laporan."""
```

## Docstring

Docstring ditulis dalam bahasa Indonesia yang jelas, ringkas, dan berfungsi
sebagai kontrak. Docstring menjelaskan input, output, invariant, efek samping,
dan error utama; docstring bukan narasi riwayat perubahan.

- Ringkasan satu baris diakhiri titik. Gunakan `D400` dan `D415` sebagai
  pemeriksaan otomatis.
- Jika docstring lebih dari satu baris, sisipkan satu baris kosong setelah
  ringkasan (`D205`).
- Gaya ringkasan multi-baris yang dipilih adalah `D212`: ringkasan dimulai pada
  baris pertama setelah `"""`. `D213` tidak dipakai karena bertentangan dengan
  `D212` dan Ruff mengabaikannya otomatis.
- Jangan mengulang nama fungsi pada baris pertama (`D402`) dan jangan memulai
  dengan kata "This" (`D404`).
- Gunakan tanda kutip tiga ganda (`D300`). Tanda kutip penutup docstring
  multi-baris berada pada baris terpisah (`D209`).
- Modul kunci wajib punya module docstring: `pipeline.py`, `config.py` atau
  `config/__init__.py`, `errors.py`, dan `document.py`. Ini adalah kontrak
  docstring modul, bukan pengecualian dari `D100`.
- Fungsi lebih dari 40 baris wajib punya docstring yang menjelaskan input,
  output, invariant, dan error utama. Fungsi yang lebih dari 80 baris dan punya
  banyak tanggung jawab harus dipecah, bukan hanya diberi docstring.
- Docstring publik tidak wajib untuk setiap class, method, dan fungsi kecil
  pada tahap ini. Aturan `D101`, `D102`, `D103`, `D105`, dan `D107` diabaikan
  agar penambahan docstring mengikuti nilai dan risiko modul, bukan jumlah
  simbol.
- `D401` diabaikan karena imperative mood Inggris tidak berlaku untuk docstring
  berbahasa Indonesia. `D202` diabaikan karena baris kosong setelah docstring
  tidak dipakai secara konsisten.
- Jika memakai section docstring, ikuti aturan `D405` sampai `D416` (nama
  section, garis bawah, dan jarak). Proyek tidak mewajibkan section untuk semua
  fungsi.

Contoh:

```python
def render_toc(package: DocxPackage, *, keep_existing: bool) -> TocReport:
    """Sisipkan field TOC ke package dan kembalikan ringkasan hasilnya.

    ``keep_existing`` mempertahankan TOC lama bila bernilai benar. Fungsi
    mengubah part dokumen dan mengembalikan jumlah entri yang diperbarui.
    Jika part dokumen tidak dapat ditulis, fungsi melempar ``StageError``.
    """
```

## Mypy

Mypy memeriksa `src/docgen` pada tahap ini. Konfigurasi berasal dari
`[tool.mypy]` di `pyproject.toml`; dokumentasi pengaturannya ada di
[mypy configuration](references.md#registry).

| Setelan | Nilai | Alasan |
| --- | --- | --- |
| `python_version` | `"3.15"` | Target runtime dan sintaks yang sama dengan Ruff. |
| `files` | `["src/docgen"]` | Fokus pada kode sumber; `tests` dan `tools` belum masuk gate mypy. |
| `check_untyped_defs` | `true` | Fungsi tanpa anotasi tetap diperiksa isinya. |
| `no_implicit_optional` | `true` | Default `None` wajib dianotasi `X \| None`. |
| `warn_unused_configs` | `true` | Konfigurasi yang tidak lagi dipakai dilaporkan. |
| `warn_unused_ignores` | `true` | `# type: ignore` yang sudah tidak perlu dilaporkan. |
| `warn_redundant_casts` | `true` | `cast` yang tidak menambah informasi dilaporkan. |
| `ignore_missing_imports` | `true` | Stub pihak ketiga belum lengkap; longgarkan dulu, ketatkan per modul. |

Aturan tipe:

- Target Python 3.15. Jangan menulis `from __future__ import annotations` di
  `src`, `tests`, atau `tools`. PEP 649 sudah membuat anotasi dievaluasi secara
  defer; future import itu hanya menambah noise dan dapat menyembunyikan
  perbedaan perilaku.
- Gunakan tipe bawaan: `list[str]`, `dict[str, int]`, `tuple[int, ...]`.
- Gunakan `X | None`, bukan `Optional[X]`. Gunakan `X | Y`, bukan `Union[X, Y]`.
- Anotasi parameter dan return untuk fungsi publik, method publik, dan fungsi
  yang dipanggil lintas modul.
- Hindari `Any`. Bila tipe pihak ketiga tidak diketahui, isolasi di satu
  adapter dan beri komentar singkat tentang batasnya.
- Gunakan `Protocol` atau `dataclass` bila bentuk data perlu bernama. Jangan
  memakai `dict[str, Any]` sebagai pengganti model.
- `# type: ignore` wajib sempit, menyebut kode kesalahan, dan menyebut alasan:
  `# type: ignore[attr-defined]  # package adapter belum punya stub`.
  `warn_unused_ignores` akan menandai ignore yang sudah tidak diperlukan.
- `cast` hanya dipakai setelah ada pemeriksaan runtime yang membenarkan tipe
  hasil cast. `warn_redundant_casts` menandai cast yang tidak perlu.
- Parameter opsional tidak boleh memiliki default `None` tanpa anotasi
  `X | None`; `no_implicit_optional` menegakkan aturan ini.

Perintah pemeriksaan:

```bash
uv run --extra dev mypy
uv run --extra dev mypy src/docgen/pipeline.py
```

Tahapan peningkatan:

1. **Tahap awal, non-strict.** Konfigurasi saat ini adalah baseline bersih,
   bukan strict total. `ignore_missing_imports` masih `true` karena stub
   pihak ketiga belum lengkap.
2. **Strict per modul baru.** Modul baru yang ditulis dari awal wajib strict
   sejak dibuat. Tambahkan override untuk modul tersebut, bukan menaikkan
   seluruh proyek sekaligus.

   ```toml
   [[tool.mypy.overrides]]
   module = "docgen.modul_baru"
   strict = true
   ```

3. **Strict total bukan gate v0.2.0.** Strict total baru dipertimbangkan
   setelah stub pihak ketiga memadai, semua signature publik dianotasi, dan
   `ignore_missing_imports` tidak dipakai. Jangan menambah `ignore_errors`
   global untuk menurunkan target.

## Import dan tipe

Ruff dengan aturan `I` mengurutkan dan mengelompokkan import. Kelompoknya:
standard library, pihak ketiga, lalu paket internal `docgen`. Setiap kelompok
dipisahkan satu baris kosong.

- Satu nama per baris untuk import langsung. Hindari `import *`. Pengecualian
  hanya `from .names import *` di `src/docgen/docx/__init__.py` untuk
  re-export namespace, dengan `# noqa: F403` dan alasan blok.
- Import internal di dalam paket memakai bentuk relatif yang sudah dipakai
  modul sekitarnya, misalnya `from ..errors import DocgenError`.
- Import pihak ketiga tidak boleh bergantung pada urutan efek samping.
- Import yang hanya dipakai untuk anotasi tetap import biasa bila tidak
  menimbulkan siklus. Bila ada siklus nyata, gunakan `TYPE_CHECKING` secara
  sempit dan jangan memindahkan seluruh import ke blok itu.
- Jangan menambah alias import untuk nama yang sudah jelas. Alias hanya dipakai
  bila nama bentrok atau modul diimpor dengan makna berbeda.
- Import mati dihapus, bukan diberi `# noqa: F401`.
- Import setelah kode hanya boleh untuk alasan struktural yang sempit:
  menghindari siklus inisialisasi, menambah `sys.path` sebelum import tool,
  atau memasang marker modul. Setiap baris memakai `# noqa: E402` dan blok
  diberi alasan tepat di atasnya. Contoh yang sudah ada:
  `src/docgen/docx/__init__.py`.

Contoh urutan yang benar:

```python
import sys
from pathlib import Path

from lxml import etree

from .errors import DocgenError
```

## Error

- Semua error domain mewarisi `DocgenError`. Error yang lebih spesifik memakai
  subclass yang sudah ada, misalnya `ConfigError`, `StageError`, atau
  `ValidationError`.
- Jangan menelan error menjadi warning kecuali kontrak stage menyatakan bahwa
  kegagalan tersebut memang dapat dipulihkan.
- Jangan memakai `except Exception: pass` atau `except:` tanpa re-raise.
  Ruff `BLE` menandai blind except. Bila pemulihan luas memang diperlukan,
  tangkap tipe yang relevan, catat konteks, lalu re-raise atau ubah menjadi
  error domain.
- `BLE001` hanya dikecualikan pada boundary opsional dengan alasan tertulis.
  Contoh saat ini: `src/docgen/pipeline.py` untuk pengaman siklus impor dan
  `src/docgen/docx/terms/model.py` untuk package tanpa rels.
- Pertahankan rantai error dengan `raise NewError(...) from exc` agar penyebab
  asli tidak hilang.
- Pesan error untuk pengguna ditulis dalam bahasa Indonesia, menyebut path,
  key, atau stage yang bermasalah, dan memberi tindakan yang dapat dilakukan.
- Traceback hanya untuk pengembang. Jangan mencetak stack trace langsung ke
  output pengguna.

## Test

- Test memakai pytest dan mengikuti marker yang terdaftar di `pytest.ini`:
  `unit`, `integration`, `packaging`, `e2e`, `word`, dan `windows`.
- Satu test menguji satu perilaku. Nama test menyatakan perilaku yang
  diharapkan, bukan nama fungsi internal.
- Test unit tidak memanggil Word, jaringan, atau proses eksternal. Test yang
  membutuhkannya diberi marker yang sesuai.
- Gunakan `tmp_path` untuk file sementara dan bersihkan artifact di akhir test.
- Test regresi ditambahkan untuk setiap bug yang diperbaiki. Test harus gagal
  pada perilaku lama dan lulus pada perilaku baru.
- Test tidak membandingkan byte ZIP (arsip) mentah. Untuk output DOCX (format
  dokumen Word), bandingkan part yang relevan atau hash c14n seperti golden
  test yang sudah ada.
- Test tidak bergantung pada urutan eksekusi, waktu, atau locale mesin.
  Hindari `sleep`; tunggu kondisi yang eksplisit.
- Test yang memeriksa error memeriksa tipe error dan pesan kunci, bukan seluruh
  teks yang mudah berubah.

## XML

- Namespace dan nama elemen OOXML (Office Open XML) diambil dari konstanta di
  `docx/names.py`. Jangan menulis prefix namespace sebagai string lepas di
  stage atau modul domain.
- Parsing dan serialisasi memakai helper di `docx/xml.py`, misalnya
  `parse_xml` dan `sha256_c14n`.
- Jangan memakai regex atau penggantian string pada XML yang sudah diserialkan
  bila operasi pohon XML dapat dilakukan. Regex pada XML rapuh terhadap
  namespace, atribut, dan urutan child.
- Urutan child yang sudah ditetapkan, seperti `STYLE_ORDER`, wajib
  dipertahankan. Jangan mengandalkan urutan dict atau urutan atribut.
- Jangan menambah komentar XML, pretty-print, atau deklarasi baru kecuali stage
  memang mengubah part tersebut. Perubahan format XML dapat mengubah hash
  golden.
- Jangan mengaktifkan entity resolution, DTD (Document Type Definition), atau
  akses jaringan saat parsing. XML dari pengguna diperlakukan sebagai data
  tidak tepercaya.
- Perubahan pada helper XML harus disertai test yang membandingkan hasil c14n
  atau memeriksa elemen target secara eksplisit.

## Pengecualian dan noqa

Pengecualian hanya dipakai bila aturan lint salah mendeteksi kode yang sah
secara domain atau bila ada boundary opsional yang tidak dapat dipersempit.
Perbaiki kode lebih dulu; `# noqa` adalah pilihan terakhir.

Aturan `# noqa`:

- Wajib menyebut kode aturan dan alasan pada baris yang sama. Formatnya
  `# noqa: KODE - alasan`.
- Beberapa kode dipisahkan koma, misalnya
  `# noqa: E402, F403 - import re-export setelah definisi error`.
- Jangan memakai `# noqa` tanpa kode, `# ruff: noqa` untuk seluruh berkas, atau
  `# noqa` untuk menutupi import mati dan kode mati.
- Jangan memakai `# noqa: E501` untuk panjang baris. Jalankan formatter atau
  pindahkan ekspresi ke variabel yang lebih jelas.
- Bila satu blok import berurutan memerlukan kode yang sama, alasan blok boleh
  ditulis sekali pada komentar tepat di atas blok. Setiap baris tetap menyebut
  kodenya. Pola ini dipakai di `src/docgen/docx/__init__.py`.
- `# type: ignore` mengikuti aturan tersendiri: kode sempit dan alasan singkat,
  misalnya `# type: ignore[attr-defined]  # package adapter belum punya stub`.
  Jangan memakai `# type: ignore` tanpa kode.
- `# fmt: off` dan `# fmt: on` hanya untuk alasan struktural yang sempit, bukan
  untuk menghindari format yang tidak disukai.

Pengecualian per file yang tercatat di `pyproject.toml`:

| File | Rule | Alasan |
| --- | --- | --- |
| `src/docgen/docx/names.py` | `E741` | `O` adalah prefix namespace OOXML resmi pada tabel Clark notation. Mengganti nama konstanta akan memutus tabel namespace publik. |

Contoh pengecualian inline yang dipakai saat ini:

- `BLE001` di `src/docgen/pipeline.py` untuk pengaman siklus impor.
- `BLE001` di `src/docgen/docx/terms/model.py` untuk package tanpa rels.
- `SIM118` di `src/docgen/stages/office.py` dan `src/docgen/stages/mermaid.py`
  karena `Artifacts` bukan `Mapping`.
- `SIM118` di `tests/unit/test_pandoc_stage.py` karena fake artifacts bukan
  `Mapping`.
- `E402` dan `F403` pada blok import `src/docgen/docx/__init__.py` karena
  import ditempatkan setelah kelas error untuk menghindari siklus inisialisasi.
  Alasan blok ditulis tepat di atas blok.

## Verifikasi sebelum commit

Jalankan dari root repo. Jangan commit bila salah satu perintah gagal.

```bash
uv sync --extra dev
uv run --extra dev ruff format .
uv run --extra dev ruff format --check .
uv run --extra dev ruff check .
uv run --extra dev mypy
uv run --extra dev pytest
uv run python tools/dev/check_docs.py
git diff --check
```

Ekspektasi:

- `ruff format --check .` exit 0 dan melaporkan semua file Python di luar
  `docs/` sudah formatted. `docs/` dilewati oleh `extend-exclude`.
- `ruff check .` exit 0 dengan `All checks passed!`. Dua warning konflik
  D203/D211 dan D212/D213 adalah normal.
- `mypy` exit 0 dengan `Success: no issues found in ... source files`. Jumlah
  file dapat berubah saat modul ditambah.
- `pytest` melaporkan seluruh tes lulus. Skip yang sudah ada tidak boleh
  bertambah; jangan mengganti kegagalan dengan skip.
- `check_docs.py` melaporkan `Broken: 0` dan jumlah entri registry yang valid.
- `git diff --check` tidak melaporkan whitespace error.
- `git status --short` hanya menampilkan file yang memang diubah.

## Rujukan resmi

Semua label di halaman ini terdaftar di [references.md](references.md#registry).
Halaman ini tidak menduplikasi URL resmi; setiap label menaut ke registry.
Label yang dipakai untuk konfigurasi dan aturan:

| Kebutuhan | Label registry |
| --- | --- |
| Konfigurasi Ruff | [Ruff configuration](references.md#registry) |
| Daftar aturan Ruff | [Ruff rules](references.md#registry) |
| Pengaturan Ruff | [Ruff settings](references.md#registry) |
| Formatter Ruff | [Ruff formatter](references.md#registry) |
| Konfigurasi mypy | [mypy configuration](references.md#registry) |
| Kode error mypy | [mypy error codes](references.md#registry) |
| Bahasa Python 3.15 | [Python 3.15 language reference](references.md#registry) |
| Anotasi tipe Python 3.15 | [Python 3.15 typing](references.md#registry) |
| Evaluasi anotasi | [PEP 649](references.md#registry) |
| Test | [pytest documentation](references.md#registry) |
| Environment dan `uv run` | [uv documentation](references.md#registry) |
