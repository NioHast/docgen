# Code Style

Dokumen ini adalah acuan gaya kode Python untuk `docgen`. Konfigurasi yang
berlaku ada di `pyproject.toml`; dokumen ini menjelaskan alasan, contoh, dan
batas pengecualiannya. Ruff menangani format dan lint, sedangkan mypy menangani
pemeriksaan tipe secara bertahap.

## Daftar isi

- [Prinsip umum](#prinsip-umum)
- [Format](#format)
- [Import](#import)
- [Type](#type)
- [Docstring](#docstring)
- [Error](#error)
- [Test](#test)
- [XML](#xml)
- [Aturan Ruff](#aturan-ruff)
- [Tahapan mypy](#tahapan-mypy)
- [Alur kerja](#alur-kerja)
- [Rujukan resmi](#rujukan-resmi)

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

## Format

Ruff formatter adalah satu-satunya penentu format. Jangan merapikan spasi,
indentasi, atau pemenggalan baris secara manual jika formatter dapat
melakukannya.

```bash
uv run --project . ruff format src tests
uv run --project . ruff format --check src tests
```

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

## Import

Ruff dengan aturan `I` mengurutkan dan mengelompokkan import. Kelompoknya:
standard library, pihak ketiga, lalu paket internal `docgen`. Setiap kelompok
dipisahkan satu baris kosong.

- Satu nama per baris untuk import langsung. Hindari `import *`.
- Import internal di dalam paket memakai bentuk relatif yang sudah dipakai
  modul sekitarnya, misalnya `from ..errors import DocgenError`.
- Import pihak ketiga tidak boleh bergantung pada urutan efek samping.
- Import yang hanya dipakai untuk anotasi tetap import biasa bila tidak
  menimbulkan siklus. Bila ada siklus nyata, gunakan `TYPE_CHECKING` secara
  sempit dan jangan memindahkan seluruh import ke blok itu.
- Jangan menambah alias import untuk nama yang sudah jelas. Alias hanya dipakai
  bila nama bentrok atau modul diimpor dengan makna berbeda.
- Import mati dihapus, bukan diberi `# noqa: F401`.

Contoh urutan yang benar:

```python
import sys
from pathlib import Path

from lxml import etree

from .errors import DocgenError
```

## Type

Anotasi tipe adalah kontrak yang dibaca manusia dan diperiksa mypy. Tulis
anotasi yang menyatakan bentuk data sebenarnya, bukan anotasi longgar agar mypy
cepat lulus.

- Gunakan tipe bawaan: `list[str]`, `dict[str, int]`, `tuple[int, ...]`.
- Gunakan `X | None`, bukan `Optional[X]`. Gunakan `X | Y`, bukan `Union[X, Y]`.
- Anotasi parameter dan return untuk fungsi publik, method publik, dan fungsi
  yang dipanggil lintas modul.
- Hindari `Any`. Bila tipe pihak ketiga tidak diketahui, isolasi di satu
  adapter dan beri komentar singkat tentang batasnya.
- Gunakan `Protocol` atau `dataclass` bila bentuk data perlu bernama. Jangan
  memakai `dict[str, Any]` sebagai pengganti model.
- `# type: ignore` wajib menyebut kode kesalahan, misalnya
  `# type: ignore[attr-defined]`, dan alasan singkat. `warn_unused_ignores`
  akan menandai ignore yang sudah tidak diperlukan.
- `cast` hanya dipakai setelah ada pemeriksaan runtime yang membenarkan tipe
  hasil cast. `warn_redundant_casts` menandai cast yang tidak perlu.
- Parameter opsional tidak boleh memiliki default `None` tanpa anotasi
  `X | None`; `no_implicit_optional` menegakkan aturan ini.
- Mypy memeriksa `src/docgen` pada tahap ini. Perubahan anotasi tidak boleh
  menambah error baru pada `uv run --project . mypy`.

## Docstring

Docstring ditulis dalam bahasa Indonesia yang jelas. Gaya pydocstyle dipilih
melalui aturan `D`, tetapi beberapa aturan yang tidak sesuai konteks proyek
diabaikan (lihat tabel aturan).

- Modul kunci wajib punya module docstring: `pipeline.py`, `config.py`,
  `errors.py`, dan `document.py`.
- Fungsi lebih dari 40 baris wajib punya docstring yang menjelaskan input,
  output, invariant, dan error utama.
- Baris pertama adalah ringkasan singkat yang diakhiri titik, lalu satu baris
  kosong sebelum penjelasan lanjutan.
- Jangan mengulang nama fungsi pada baris pertama.
- Jelaskan parameter yang tidak jelas dari namanya, efek samping, dan error
  yang mungkin dilempar. Parameter yang sudah jelas cukup disebut bila
  kontraknya perlu ditegaskan.
- Docstring tidak menyimpan riwayat perubahan atau alasan historis.
- Docstring publik tidak wajib untuk setiap class, method, dan fungsi kecil
  pada tahap ini. Aturan `D101`, `D102`, `D103`, `D105`, dan `D107` diabaikan
  agar penambahan docstring mengikuti nilai dan risiko modul, bukan jumlah
  simbol.
- `D401` diabaikan karena imperative mood Inggris tidak berlaku untuk docstring
  berbahasa Indonesia. `D202` diabaikan karena baris kosong setelah docstring
  tidak dipakai secara konsisten.

Contoh:

```python
def render_toc(package: DocxPackage, *, keep_existing: bool) -> TocReport:
    """Sisipkan field TOC ke package dan kembalikan ringkasan hasilnya.

    ``keep_existing`` mempertahankan TOC lama bila bernilai benar. Fungsi
    mengubah part dokumen dan mengembalikan jumlah entri yang diperbarui.
    Jika part dokumen tidak dapat ditulis, fungsi melempar ``StageError``.
    """
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

## Aturan Ruff

Konfigurasi ada di `[tool.ruff]` dan `[tool.ruff.lint]`. Tabel berikut mencakup
semua kelompok yang dipilih dan semua aturan yang diabaikan. Status `Aktif`
berarti aturan dijalankan, `Aktif sebagian` berarti kelompok dipilih dengan
pengecualian, dan `Diabaikan` berarti aturan tidak dijalankan.

| Rule | Status | Alasan | Contoh | Link resmi |
| --- | --- | --- | --- | --- |
| `E` | Aktif | Menjaga spasi, indentasi, dan panjang baris agar diff mudah dibaca. | `x=1` menjadi `x = 1` | [pycodestyle E](https://docs.astral.sh/ruff/rules/#pycodestyle-e-w) |
| `F` | Aktif | Menangkap nama tidak terdefinisi dan import atau variabel mati. | `import os` yang tidak dipakai ditandai `F401` | [pyflakes F](https://docs.astral.sh/ruff/rules/#pyflakes-f) |
| `W` | Aktif | Menangkap trailing whitespace dan masalah spasi yang tidak terlihat. | Baris berakhir dengan spasi ditandai `W291` | [pycodestyle W](https://docs.astral.sh/ruff/rules/#pycodestyle-e-w) |
| `I` | Aktif | Menjaga urutan dan pengelompokan import tetap deterministik. | `from pathlib import Path` diletakkan sebelum import pihak ketiga | [isort I](https://docs.astral.sh/ruff/rules/#isort-i) |
| `UP` | Aktif | Mengganti sintaks lama dengan bentuk Python 3.15 yang lebih ringkas. | `Optional[str]` menjadi `str \| None` | [pyupgrade UP](https://docs.astral.sh/ruff/rules/#pyupgrade-up) |
| `B` | Aktif | Menangkap pola rawan bug seperti mutable default dan perbandingan salah. | `def f(x=[])` diganti `def f(x=None)` | [flake8-bugbear B](https://docs.astral.sh/ruff/rules/#flake8-bugbear-b) |
| `SIM` | Aktif | Menyederhanakan kontrol alur yang berbelit tanpa mengubah perilaku. | `if a: if b:` digabung menjadi `if a and b:` | [flake8-simplify SIM](https://docs.astral.sh/ruff/rules/#flake8-simplify-sim) |
| `RUF` | Aktif | Menjaga konsistensi khusus Ruff dan menangkap potensi bug. | `# noqa` tanpa kode dan tanpa efek ditandai `RUF100` | [Ruff-specific RUF](https://docs.astral.sh/ruff/rules/#ruff-specific-rules-ruf) |
| `BLE` | Aktif | Menolak blind except yang menyembunyikan error. | `except:` diganti `except ValueError as exc:` lalu re-raise | [flake8-blind-except BLE](https://docs.astral.sh/ruff/rules/#flake8-blind-except-ble) |
| `D` | Aktif sebagian | Menjaga kualitas docstring, dengan pengecualian yang tercantum di bawah. | Docstring tanpa ringkasan ditandai `D` | [pydocstyle D](https://docs.astral.sh/ruff/rules/#pydocstyle-d) |
| `D101` | Diabaikan | Docstring class publik ditunda sampai docstring modul kunci selesai. | `class Report:` boleh tanpa docstring pada tahap ini | [D101](https://docs.astral.sh/ruff/rules/undocumented-public-class/) |
| `D102` | Diabaikan | Docstring method publik ditunda; kontrak method ada di docs dan test. | `def render(self):` boleh tanpa docstring pada tahap ini | [D102](https://docs.astral.sh/ruff/rules/undocumented-public-method/) |
| `D103` | Diabaikan | Docstring fungsi publik ditunda; fungsi panjang tetap wajib punya docstring. | `def helper():` boleh tanpa docstring bila pendek | [D103](https://docs.astral.sh/ruff/rules/undocumented-public-function/) |
| `D105` | Diabaikan | Docstring magic method biasanya mengulang perilaku yang sudah jelas. | `def __len__(self):` tidak wajib docstring | [D105](https://docs.astral.sh/ruff/rules/undocumented-magic-method/) |
| `D107` | Diabaikan | Docstring `__init__` tidak menambah informasi bila class sudah jelas. | `def __init__(self, path):` tidak wajib docstring | [D107](https://docs.astral.sh/ruff/rules/undocumented-public-init/) |
| `D202` | Diabaikan | Baris kosong setelah docstring tidak dipakai secara konsisten. | `"""Ringkasan."""` boleh diikuti langsung kode | [D202](https://docs.astral.sh/ruff/rules/blank-line-after-function/) |
| `D401` | Diabaikan | Imperative mood Inggris tidak sesuai docstring bahasa Indonesia. | `"""Mengembalikan hasil."""` tidak perlu diubah menjadi `Return ...` | [D401](https://docs.astral.sh/ruff/rules/non-imperative-mood/) |

Ruff 0.17.4 memberi peringatan bahwa
[D203](https://docs.astral.sh/ruff/rules/incorrect-blank-line-before-class/)
bertentangan dengan [D211](https://docs.astral.sh/ruff/rules/blank-line-before-class/)
dan [D213](https://docs.astral.sh/ruff/rules/multi-line-summary-second-line/)
bertentangan dengan [D212](https://docs.astral.sh/ruff/rules/multi-line-summary-first-line/).
Ruff mengabaikan `D203` dan `D213` secara otomatis. `select` tidak diturunkan;
perilaku ini dicatat agar baseline lint dapat direproduksi.

## Tahapan mypy

Mypy tidak langsung strict total. Peningkatan dilakukan bertahap agar setiap
tahap punya baseline yang dapat diverifikasi.

1. **Tahap awal, non-strict.** Konfigurasi saat ini memeriksa `src/docgen`
   dengan `check_untyped_defs`, `no_implicit_optional`, `warn_unused_configs`,
   `warn_unused_ignores`, dan `warn_redundant_casts`. `ignore_missing_imports`
   dilonggarkan karena stub pihak ketiga belum lengkap. Target tahap ini adalah
   baseline bersih, bukan strict total.
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
   tidak ada `ignore_missing_imports`. Jangan menjadikan strict total sebagai
   syarat rilis v0.2.0.

Perintah pemeriksaan:

```bash
uv run --project . mypy
uv run --project . mypy src/docgen/pipeline.py
```

## Alur kerja

Dari root repo:

```bash
uv sync --project . --extra dev
uv run --project . ruff format src tests
uv run --project . ruff check src tests
uv run --project . mypy
uv run --project . pytest
```

Urutan di atas disengaja: format lebih dulu, lalu lint, lalu tipe, lalu test.
Pada gate otomatis, gunakan `ruff format --check` agar tidak ada perubahan file
yang tidak diinginkan.

- Jalankan `ruff check --fix` hanya untuk perbaikan aman seperti urutan import
  dan tanda kutip, lalu periksa diff.
- Jangan memakai `--unsafe-fixes` tanpa review manual.
- Jangan mengubah `uv.lock` secara manual. Setelah `pyproject.toml` berubah,
  jalankan `uv lock`.
- Pin versi Ruff dan mypy eksak. Peningkatan versi dilakukan bersama
  pembaruan lock dan pemeriksaan ulang baseline.

## Rujukan resmi

- Konfigurasi Ruff: [https://docs.astral.sh/ruff/configuration/](https://docs.astral.sh/ruff/configuration/)
- Daftar aturan Ruff: [https://docs.astral.sh/ruff/rules/](https://docs.astral.sh/ruff/rules/)
- Pengaturan Ruff: [https://docs.astral.sh/ruff/settings/](https://docs.astral.sh/ruff/settings/)
- Formatter Ruff: [https://docs.astral.sh/ruff/formatter/](https://docs.astral.sh/ruff/formatter/)
- Dokumentasi mypy: [https://mypy.readthedocs.io/](https://mypy.readthedocs.io/)
- Dokumentasi Python 3.15: [https://docs.python.org/3.15/](https://docs.python.org/3.15/)
- Dokumentasi pytest: [https://docs.pytest.org/](https://docs.pytest.org/)
