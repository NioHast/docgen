# Gaya Python 3.15

Dokumen ini merangkum kebijakan gaya Python untuk AutoOffice, fitur typing dan
standard library yang sudah digantikan, serta cara checker menegakkan aturan.
Target proyek adalah Python 3.15 tanpa jalur kompatibilitas ke versi lama.
Sumber kebenaran yang dapat dijalankan tetap `pyproject.toml` dan checker;
dokumen ini menjelaskan alasan dan aturan migrasinya.

## Daftar Isi

- [Target dan kebijakan](#target-dan-kebijakan)
- [Anotasi future import](#anotasi-future-import)
  - [Status](#status)
  - [Alasan menghapus](#alasan-menghapus)
  - [Pengganti](#pengganti)
  - [Aturan migrasi](#aturan-migrasi)
- [Fitur typing yang digantikan](#fitur-typing-yang-digantikan)
- [API stdlib yang deprecated](#api-stdlib-yang-deprecated)
- [Fitur Python 3.13 sampai 3.15](#fitur-python-313-sampai-315)
  - [Baseline Python 3.12](#baseline-python-312)
  - [Fitur 3.13 sampai 3.15](#fitur-313-sampai-315)
- [Audit proyek](#audit-proyek)
  - [Ringkasan hitungan](#ringkasan-hitungan)
  - [Temuan spesifik](#temuan-spesifik)
- [Penegakan](#penegakan)
  - [Checker](#checker)
  - [Aturan AGENTS.md](#aturan-agentsmd)
- [Referensi](#referensi)

## Target dan kebijakan

- `requires-python = ">=3.15"` di `pyproject.toml`. Tidak ada dukungan resmi
  untuk Python 3.14 atau lebih lama.
- Ruff memakai `target-version = "py315"` dan mypy memakai
  `python_version = "3.15"`. Sintaks modern langsung menjadi default, bukan
  fitur opsional.
- Kode baru wajib memakai sintaks yang tersedia di 3.15: builtin generik
  (`list[str]`, `dict[str, int]`), `X | None`, `type` statement PEP 695, dan
  parameter tipe PEP 695. Jangan menulis shim untuk versi lama.
- API yang sudah deprecated tidak dipakai untuk kode baru. Checker menolak
  subset yang sudah disepakati; tabel di dokumen ini menjadi rujukan
  penggantinya.
- Pengecualian hanya boleh lewat komentar
  `# python-style: allow <rule>` pada baris yang sama, dengan alasan tertulis.
  Pengecualian bukan cara untuk menunda migrasi kode baru.
- Cakupan checker adalah `src/autooffice/**/*.py` dan `tests/**/*.py`.
  Jalur DOCX legacy di luar `src/autooffice` tidak menjadi target penulisan
  baru sampai dihapus pada F3.

## Anotasi future import

### Status

- Python 3.14 mengimplementasikan PEP 649 dan PEP 749: anotasi dievaluasi
  secara lazy by default. `from __future__ import annotations` tidak lagi
  diperlukan untuk kode yang hanya mendukung 3.14 ke atas.
- Panduan resmi modernisasi typing menyatakan: "Remove unnecessary uses of
  `from __future__ import annotations` for code only supporting Python 3.14
  and up."
- PEP 749 mendeprekasi future import tersebut. Di Python 3.15 ia masih bekerja,
  tetapi mengubah modul kembali ke semantik string annotation PEP 563.
- Proyek ini menargetkan 3.15, jadi future import adalah noise yang
  bertentangan dengan target. Jangan menambahkannya ke file baru.

### Alasan menghapus

- Menghindari dua semantik anotasi dalam satu codebase. Tanpa future import,
  `__annotations__` mengikuti PEP 649; dengan future import, nilainya menjadi
  string PEP 563.
- Forward reference tetap didukung tanpa tanda kutip. Contoh berikut valid
  tanpa future import karena anotasi baru dievaluasi saat diakses:

  ```python
  class Node:
      parent: Node | None = None
  ```

- Anotasi string dapat menyembunyikan nama yang salah sampai
  `typing.get_type_hints` dipanggil. Anotasi lazy tetap menunda evaluasi, tetapi
  tidak memaksa setiap anotasi menjadi string.
- Future import adalah kandidat penghapusan di masa depan. Menghapusnya
  sekarang menghindari migrasi tambahan saat deprecation berlanjut.
- Sebagian besar file hanya perlu menghapus satu baris. Perubahan ini tidak
  mengubah perilaku runtime pada kode yang tidak menginspeksi anotasi.

### Pengganti

Tidak ada baris pengganti. Hapus `from __future__ import annotations` dan biarkan
anotasi menjadi lazy secara default.

- Untuk membaca anotasi saat runtime, gunakan `typing.get_type_hints` atau
  `annotationlib`. Jangan mem-parse `__annotations__` sebagai string.
- Untuk serialisasi skema atau validasi, tentukan apakah data yang dibutuhkan
  adalah tipe hasil resolusi, bukan representasi string. Jika ya, gunakan
  helper resolusi resmi, bukan `eval`.
- Jika sebuah modul sengaja membutuhkan string annotation untuk kompatibilitas
  eksternal, pertahankan future import dengan komentar allow dan alasan yang
  spesifik. Proyek 3.15 tidak membutuhkannya untuk kode internal.

### Aturan migrasi

1. Future import sudah dihapus dari seluruh `src/autooffice` dan `tests`;
   jangan menambahkannya kembali.
2. Hapus per area yang koheren, misalnya satu paket domain atau satu direktori
   test, dan jalankan test area tersebut. Jangan mencampur penghapusan dengan
   perubahan perilaku.
3. Periksa kode yang menginspeksi `__annotations__`, `inspect.signature`,
   `typing.get_type_hints`, atau metadata library. Pastikan hasilnya tetap
   berupa tipe, bukan string.
4. Jalankan `uv run pytest` untuk area yang berubah dan
   `uv run python tools/quality/check_python.py`. Temuan `future-annotations`
   harus turun, bukan berpindah ke aturan lain.
5. Seluruh future import sudah dibersihkan; langkah gate `python-style`
   sekarang blocking dan kegagalannya menghentikan gate.
6. Jangan menambahkan future import baru meskipun file lain masih memakainya.
   Konsistensi dicapai dengan menghapus, bukan dengan menambah.

## Fitur typing yang digantikan

Alias di kolom kiri tidak boleh diimpor dari `typing`. Gunakan pengganti di
kolom tengah. Kolom pemakaian proyek adalah hasil audit pada snapshot
2026-11-14; angka 0 berarti tidak ada pemakaian di `src/autooffice` atau
`tests`.

| Alias lama | Pengganti | Versi minimum | Pemakaian proyek |
| --- | --- | --- | --- |
| `typing.List` | `list` | 3.9 (PEP 585) | 0 |
| `typing.Dict` | `dict` | 3.9 (PEP 585) | 0 |
| `typing.Tuple` | `tuple` | 3.9 (PEP 585) | 0 |
| `typing.Set` | `set` | 3.9 (PEP 585) | 0 |
| `typing.FrozenSet` | `frozenset` | 3.9 (PEP 585) | 0 |
| `typing.Type` | `type` | 3.9 (PEP 585) | 0 |
| `typing.Optional[X]` | `X \| None` | 3.10 (PEP 604) | 0 |
| `typing.Union[X, Y]` | `X \| Y` | 3.10 (PEP 604) | 0 |
| `typing.Callable` | `collections.abc.Callable` | 3.9 (PEP 585) | 0 |
| `typing.Iterable` | `collections.abc.Iterable` | 3.9 (PEP 585) | 0 |
| `typing.Iterator` | `collections.abc.Iterator` | 3.9 (PEP 585) | 0 |
| `typing.Mapping` | `collections.abc.Mapping` | 3.9 (PEP 585) | 0 |
| `typing.MutableMapping` | `collections.abc.MutableMapping` | 3.9 (PEP 585) | 0 |
| `typing.Sequence` | `collections.abc.Sequence` | 3.9 (PEP 585) | 0 |
| `typing.Hashable` | `collections.abc.Hashable` | 3.12 | 0 |
| `typing.Sized` | `collections.abc.Sized` | 3.12 | 0 |
| `typing.Text` | `str` | 3.0 | 0 |
| `typing.NoReturn` | `typing.Never` | 3.11 (PEP 673) | 0 |
| `typing.ByteString` | `bytes \| bytearray \| memoryview` atau `collections.abc.Buffer` | 3.12 (PEP 688) | 0 |
| `typing.AnyStr` | parameter tipe dengan constraint PEP 695 | 3.12 (PEP 695) | 0 |
| `typing.TypeAlias` | `type` statement | 3.12 (PEP 695) | 0 |
| `typing.TypeGuard` | `typing.TypeIs` bila narrowing dua arah dibutuhkan | 3.13 (PEP 742) | 0 |

Catatan:

- Proyek sudah memakai `collections.abc.Callable`, `Iterable`, `Mapping`, dan
  `Sequence` secara langsung. Itu bukan pelanggaran; yang dilarang adalah
  impor nama yang sama dari `typing`.
- `Never`, `Required`, `NotRequired`, `Unpack`, `TypeIs`, `ReadOnly`, `IO`,
  `BinaryIO`, `Any`, `cast`, `Literal`, `Protocol`, `TypedDict`, `NamedTuple`,
  `ClassVar`, `TYPE_CHECKING`, dan `override` tetap diizinkan dari `typing`.
- `TypeGuard` masih valid, tetapi `TypeIs` lebih tepat untuk predikat yang
  mempersempit kedua cabang. Migrasikan hanya bila semantiknya cocok.
- `from typing import *` tidak dipakai di proyek. Jangan menambahkannya.

## API stdlib yang deprecated

| API lama | Pengganti | Status | Pemakaian proyek |
| --- | --- | --- | --- |
| `datetime.utcnow()` | `datetime.now(UTC)` | Deprecated 3.12 | 0 |
| `datetime.utcfromtimestamp()` | `datetime.fromtimestamp(ts, UTC)` | Deprecated 3.12 | 0 |
| `asyncio.get_event_loop()` | `asyncio.run` atau `asyncio.Runner` | Policy system deprecated 3.14 | 0 |
| `asyncio.get_event_loop_policy()` | `asyncio.run` atau `asyncio.Runner` | Policy system deprecated 3.14 | 0 |
| `codecs.open()` | `open()` bawaan | Deprecated | 0 |
| `re.match()` | `re.prefixmatch()` | Soft-deprecated 3.15 | 3 panggilan langsung; 66 `.match(` di `src/autooffice` |
| `typing.AnyStr` | Parameter tipe dengan constraint PEP 695 | Deprecated 3.13 | 0 |
| `typing.TypeAlias` | `type` statement | Digantikan PEP 695 | 0 |
| `typing.ByteString` | `bytes \| bytearray \| memoryview` atau `Buffer` | Deprecated 3.9, dihapus 3.14 | 0 |
| `pkg_resources` | `importlib.resources` | API pihak ketiga yang deprecated | 0 |

Catatan:

- `datetime.utcnow()` mengembalikan naive datetime. Penggantinya membuat
  timezone eksplisit dan menghindari bug perbandingan antar timezone.
- Sistem policy asyncio digantikan `asyncio.run` dan `asyncio.Runner`. Jangan
  memasang policy global baru.
- `re.match` adalah soft-deprecation di 3.15. Penggantian harus per panggilan
  karena 63 panggilan lain adalah metode pattern atau objek lain, bukan
  `re.match` langsung.
- `importlib.resources` adalah pengganti `pkg_resources` untuk membaca resource
  package. Tidak ada pemakaian `pkg_resources` di proyek saat audit.

## Fitur Python 3.13 sampai 3.15

Semua fitur di bawah tersedia pada target 3.15. Gunakan bila kebutuhannya
nyata; jangan menambah abstraksi hanya karena fitur tersedia.

### Baseline Python 3.12

| Fitur | Kapan dipakai |
| --- | --- |
| Sintaks parameter tipe PEP 695 (`def f[T]`, `class C[T]`, `type Alias = ...`) | Generic dan alias baru. Jangan memakai `TypeVar` atau `Generic` eksplisit. |
| `@override` (PEP 698) | Method subclass yang mengganti method induk. Membantu type checker mendeteksi nama yang salah. |
| `Path.walk` | Traversal direktori rekursif. Lebih ringkas daripada `os.walk` dan tetap berbasis `Path`. |
| `itertools.batched` | Memproses iterable dalam batch berukuran tetap, misalnya chunk render atau upload. |

### Fitur 3.13 sampai 3.15

| Fitur | Versi | Kapan dipakai | Catatan |
| --- | --- | --- | --- |
| Anotasi lazy PEP 649/749 | 3.14 | Semua kode baru. Hapus future import. | Forward reference langsung didukung. |
| `typing.TypeIs` (PEP 742) | 3.13 | Predikat yang mempersempit tipe di kedua cabang. | Lebih kuat daripada `TypeGuard` untuk fungsi `is_*`. |
| `typing.ReadOnly` (PEP 705) | 3.13 | Key `TypedDict` yang tidak boleh diubah. | Cocok untuk konfigurasi read-only. |
| `warnings.deprecated` (PEP 702) | 3.13 | Menandai API publik yang akan dihapus. | Type checker dapat membaca status deprecated. |
| `frozendict` (PEP 814) | 3.15 | Mapping immutable untuk konstanta publik. | Jangan mengganti `MappingProxyType` internal tanpa alasan. |
| `sentinel` (PEP 661) | 3.15 | Nilai default unik pada signature. | Ganti pola `object()` sentinel. |
| Explicit lazy imports (PEP 810) | 3.15 | Dependensi opsional atau mahal yang jarang dipakai. | Jangan menyembunyikan dependensi inti; ukur startup. |
| Unpacking in comprehensions (PEP 798) | 3.15 | Meratakan iterable bersarang di comprehension. | Pakai loop biasa bila lebih dari dua level. |
| UTF-8 default (PEP 686) | 3.15 | I/O teks baru. | `encoding="utf-8"` eksplisit tetap boleh dan lebih jelas. |
| `TypedDict` extra items (PEP 728) | 3.15 | Skema konfigurasi tertutup yang menolak key tak dikenal. | Gunakan `closed` dan `extra_items`; konversi bentuk fungsional lebih dulu. |
| `TypeForm` (PEP 747) | 3.15 | API yang menerima ekspresi tipe, bukan instance. | Belum ada kebutuhan di repo; jangan menambah API hanya untuk memakainya. |
| `disjoint_base` (PEP 800) | 3.15 | Hierarki class tertutup yang panas di `isinstance`. | Butuh profiling; bukan dekorator default. |

## Audit proyek

### Ringkasan hitungan

Angka di bawah adalah snapshot audit lane pada 2026-11-14. Lane paralel yang
menambah modul dapat menaikkan angka saat checker dijalankan; jumlah terbaru
selalu berasal dari perintah checker, bukan dari tabel ini.

| Item | Hitungan | Catatan |
| --- | --- | --- |
| `from __future__ import annotations` di `src/autooffice` | 0 | Termasuk 10 file Google yang dibersihkan terakhir. |
| `from __future__ import annotations` di `tests` | 0 | Termasuk 9 file Google yang dibersihkan terakhir. |
| Total future import | 0 | 89 file dibersihkan, 19 file Google menyusul, total 108 pada snapshot. |
| Future import di jalur legacy DOCX | 0 | Jalur legacy sudah bersih. |
| Alias typing warisan | 0 | Tidak ada `List`, `Dict`, `Optional`, `Union`, dan sejenisnya dari `typing`. |
| `TypeVar` atau `Generic` | 0 | Sintaks PEP 695 belum diperlukan karena belum ada generic baru. |
| `TypedDict` bentuk fungsional | 1 | `CoverData` di `src/autooffice/design/tokens.py`. |
| Panggilan `.match(` di `src/autooffice` | 66 | 3 di antaranya `re.match` langsung; 15 panggilan lain di `tests`. |
| `datetime.utcnow` atau `utcfromtimestamp` | 0 | Tidak ada. |
| `asyncio.get_event_loop` atau policy | 0 | Tidak ada. |
| `pkg_resources` | 0 | Tidak ada. |
| `codecs.open` | 0 | Tidak ada. |
| Temuan checker selain future import | 0 | Baseline bersih untuk aturan lain. |

### Temuan spesifik

1. **108 future import pada snapshot.** Sebanyak 89 file non-Google
   dibersihkan lebih dulu, lalu 19 file Google (10 di
   `src/autooffice/google` dan 9 di `tests/google`) menyusul. Keadaan akhir:
   0 temuan `future-annotations`. Tidak ada alasan modul yang terdokumentasi
   untuk mempertahankannya.
2. **Satu `TypedDict` fungsional.** `src/autooffice/design/tokens.py:177`
   mendefinisikan:

   ```python
   CoverData = TypedDict("CoverData", {"from": str, "mid": str, "to": str})
   ```

   Bentuk fungsional dipertahankan karena `from` adalah keyword Python dan
   tidak dapat ditulis sebagai nama field pada class syntax. Jangan mengonversi
   secara mekanis. Jika skema ini nanti memakai `closed` atau `extra_items` dari
   PEP 728, evaluasi class syntax bersama pemetaan key `from` lebih dulu.
3. **66 panggilan `.match(` di `src/autooffice`.** Tiga panggilan langsung
   `re.match` berada di
   `src/autooffice/docx/markdown/blocks.py:274`,
   `src/autooffice/docx/package/fields.py:641`, dan
   `src/autooffice/docx/paths.py:189`. `re.match` soft-deprecated di 3.15;
   `re.prefixmatch` adalah pengganti yang dianjurkan. 63 panggilan lain harus
   diperiksa per konteks karena belum tentu semuanya `re.match`. Di `tests` ada
   15 panggilan `.match(` tambahan.
4. **Tidak ada alias typing warisan.** Audit tidak menemukan `typing.List`,
   `typing.Dict`, `typing.Optional`, `typing.Union`, `typing.Type`,
   `typing.Callable`, `typing.AnyStr`, `typing.TypeAlias`, atau
   `typing.TypeGuard`. Import `Callable`, `Iterable`, `Mapping`, dan `Sequence`
   berasal dari `collections.abc` dan sudah benar.
5. **Tidak ada `TypeVar` atau `Generic`.** Kode belum membutuhkan generic
   eksplisit. Jika nanti butuh, gunakan sintaks PEP 695, bukan `TypeVar`.
6. **Tidak ada API deprecated yang lain.** Tidak ditemukan `datetime.utcnow`,
   `datetime.utcfromtimestamp`, `asyncio.get_event_loop`,
   `asyncio.get_event_loop_policy`, `pkg_resources`, atau `codecs.open`.

## Penegakan

### Checker

`tools/quality/check_python.py` adalah checker AST dan tokenize yang read-only.
Ia tidak mengimpor kode yang diperiksa, tidak mengakses jaringan, dan tidak
menulis berkas.

| Rule | Menolak | Pengganti |
| --- | --- | --- |
| `future-annotations` | `from __future__ import annotations` | Hapus baris; anotasi lazy default. |
| `legacy-typing` | Alias warisan dari `typing` | Builtin generik, `X \| None`, atau `collections.abc`. |
| `datetime-utcnow` | `datetime.utcnow` dan `utcfromtimestamp` | `datetime.now(UTC)` dan `datetime.fromtimestamp(ts, UTC)`. |
| `asyncio-loop` | `get_event_loop` dan `get_event_loop_policy` | `asyncio.run` atau `asyncio.Runner`. |
| `pkg-resources` | Import atau penggunaan `pkg_resources` | `importlib.resources`. |
| `codecs-open` | `codecs.open` | `open()` bawaan. |

Perintah pemeriksaan:

```bash
uv run python tools/quality/check_python.py
uv run python tools/quality/check_python.py --list
uv run python tools/quality/check_python.py --format json
uv run python tools/quality/check_python.py --format json src/autooffice tests
```

Kode keluar 0 bila bersih, 1 bila ada temuan, dan 2 bila path tidak ditemukan.
`--list` mencetak nama aturan yang dapat dipakai di komentar allow.

Pengecualian ditulis pada baris yang sama dengan temuan:

```python
nilai = modul.utcnow()  # python-style: allow datetime-utcnow - data lama tanpa timezone
```

Komentar pada baris sebelumnya tidak berlaku. Allow comment untuk aturan lain
juga tidak berlaku. Pengecualian harus menyebut alasan yang dapat diperiksa
ulang, bukan sekadar menonaktifkan checker.

Langkah gate `python-style` bersifat blocking: temuan checker menghentikan
gate pada pelanggaran pertama.

### Aturan AGENTS.md

Aturan yang harus tercermin di `AGENTS.md`:

- Jangan menulis `from __future__ import annotations` di
  `src/autooffice/**` atau `tests/**`. Target Python 3.15 memakai anotasi lazy
  PEP 649/749.
- Gunakan `list`, `dict`, `tuple`, `set`, `type`, `X | None`, dan
  `collections.abc` untuk anotasi baru.
- Jalankan `uv run python tools/quality/check_python.py` sebelum commit.
- Pengecualian wajib memakai `# python-style: allow <rule>` pada baris yang
  sama dengan alasan tertulis.

Checker adalah penegak utama. Aturan AGENTS.md menjelaskan kebijakan kepada
kontributor dan agent; keduanya harus bergerak ke arah yang sama.

## Referensi

Semua tautan di bawah menuju sumber resmi Python atau PEP.

| Sumber | URL |
| --- | --- |
| PEP 649: Deferred Evaluation of Annotations | https://peps.python.org/pep-0649/ |
| PEP 749: Deferred Evaluation of Annotations Using Descriptors | https://peps.python.org/pep-0749/ |
| PEP 563: Postponed Evaluation of Annotations | https://peps.python.org/pep-0563/ |
| Python 3.14: What's New | https://docs.python.org/3.14/whatsnew/3.14.html |
| Python 3.15: What's New | https://docs.python.org/3.15/whatsnew/3.15.html |
| Python 3.15: typing | https://docs.python.org/3.15/library/typing.html |
| Python 3.15: annotationlib | https://docs.python.org/3.15/library/annotationlib.html |
| Typing modernization guide | https://typing.python.org/en/latest/guides/modernizing.html |
| PEP 742: TypeIs | https://peps.python.org/pep-0742/ |
| PEP 705: ReadOnly TypedDict Items | https://peps.python.org/pep-0705/ |
| PEP 702: Marking Deprecated APIs | https://peps.python.org/pep-0702/ |
| PEP 814: Add frozendict | https://peps.python.org/pep-0814/ |
| PEP 661: Sentinel Values | https://peps.python.org/pep-0661/ |
| PEP 810: Explicit Lazy Imports | https://peps.python.org/pep-0810/ |
| PEP 798: Unpacking in Comprehensions | https://peps.python.org/pep-0798/ |
| PEP 686: Make UTF-8 Mode Default | https://peps.python.org/pep-0686/ |
| PEP 728: TypedDict with Typed Extra Items | https://peps.python.org/pep-0728/ |
| PEP 747: Annotating Type Forms | https://peps.python.org/pep-0747/ |
| PEP 800: Disjoint Bases | https://peps.python.org/pep-0800/ |
| PEP 695: Type Parameter Syntax | https://peps.python.org/pep-0695/ |
| PEP 698: Override Decorator | https://peps.python.org/pep-0698/ |
| Python 3.15: re | https://docs.python.org/3.15/library/re.html |
| Python 3.15: datetime | https://docs.python.org/3.15/library/datetime.html |
| Python 3.15: asyncio | https://docs.python.org/3.15/library/asyncio.html |
| Python 3.15: codecs | https://docs.python.org/3.15/library/codecs.html |
| Python 3.15: importlib.resources | https://docs.python.org/3.15/library/importlib.resources.html |
| Python 3.15: pathlib | https://docs.python.org/3.15/library/pathlib.html |
| Python 3.15: itertools | https://docs.python.org/3.15/library/itertools.html |
| Python 3.13: What's New | https://docs.python.org/3.13/whatsnew/3.13.html |
| Python 3.12: What's New | https://docs.python.org/3.12/whatsnew/3.12.html |
