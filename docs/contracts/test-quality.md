# Kontrak Test Quality

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 12.1, 12.2, 12.6, 12.7, dan 12.10.
Pemilik kontrak: test infrastructure owner.

## Tujuan

Kontrak ini membekukan aturan test yang deterministik, terisolasi, dan
bermakna. Test adalah kontrak yang dapat dieksekusi, bukan pelengkap gate.

## Invarian

1. Test tidak boleh bergantung pada network. Tidak ada akses HTTP, DNS,
   Google API, atau layanan eksternal di unit dan contract test.
2. COM dan Google memakai fake di unit dan contract test. Jalur nyata hanya
   dijalankan smoke final di Windows.
3. Tidak ada `time.sleep` untuk menunggu. Gunakan fake clock, event, atau
   mekanisme sinkronisasi yang deterministik.
4. Waktu, locale, urutan dictionary, dan angka acak tidak boleh menentukan
   hasil test. Seed wajib eksplisit bila randomness tidak terhindarkan.
5. Setiap test punya minimal satu assertion perilaku. Dilarang `assert True`,
   `assert 1 == 1`, test kosong, dan test yang hanya memanggil fungsi tanpa
   memeriksa hasil.
6. `pytest.mark.skip` atau `xfail` hanya boleh dipakai dengan alasan tertulis
   dan batas waktu perbaikan. Test yang tidak memenuhi environment harus
   gagal, bukan skip diam-diam.
7. Test tidak menulis ke path repo selain `tmp_path`. File output, state,
   cache, dan fixture sementara selalu berada di `tmp_path`.
8. Fixture tidak boleh mengubah state global tanpa cleanup. Test harus bisa
   dijalankan sendiri, dalam urutan acak, dan paralel tanpa saling
   memengaruhi.
9. Nama test menjelaskan perilaku yang diuji, bukan nama fungsi internal.
   Parameterized test dipakai untuk batas nilai, bukan untuk menggandakan
   assertion yang sama.
10. Golden test harus deterministik:
    - DOCX: bandingkan part relevan setelah normalisasi timestamp dan
      metadata.
    - PPTX: buka ZIP, normalisasi timestamp, relationship ID yang tidak
      stabil, dan whitespace XML.
    - Jangan membandingkan binary penuh tanpa normalisasi.
11. Golden hanya diperbarui dengan flag update eksplisit dan review
    integration owner. Lane hanya boleh menambah golden baru di path unik
    miliknya.
12. Fixture existing tidak boleh diedit lane. Fixture baru memakai nama unik.
    Fixture besar wajib punya alasan dan tidak menggantikan assertion
    semantik.
13. Baseline DOCX dibuat dari docgen sebelum kode lama dihapus. Fake Google
    berada di `src/autooffice/google/fake.py` atau `tests/fixtures/google/`
    dengan kontrak yang jelas.
14. Visual test memakai lock COM yang sama dengan PDF. Threshold pixel dan
    mask area wajib eksplisit. Perbedaan font atau versi PowerPoint
    dilaporkan, bukan diabaikan.
15. `tools/quality/check_tests.py` memeriksa tidak ada test tanpa assertion,
    `assert True`, skip tanpa alasan, `time.sleep`, akses network, penulisan
    di luar `tmp_path`, state global tanpa cleanup, dan ketergantungan urutan.

## Contoh

```python
import pytest

from autooffice.deck.charts import ChartSpecError, build_chart_spec


def test_chart_rejects_five_series(deck_factory):
    deck = deck_factory(series=5)

    with pytest.raises(ChartSpecError, match="maksimal 4 seri"):
        build_chart_spec(deck.slides[0].blocks[0])
```

Test ini deterministik, tidak memakai network, tidak menulis file, dan
menguji batas kontrak chart. Fixture `deck_factory` hanya membangun data di
memori.

## Aturan fixture

- Fixture harus kecil dan fokus pada satu skenario.
- Fixture domain dimiliki lane terkait; fixture shared dimiliki test
  infrastructure owner.
- Fixture tidak boleh membaca file di luar repo atau menulis ke repo.
- Fixture yang memakai fake clock wajib mengembalikan waktu yang sama pada
  setiap pemanggilan.
- Fixture besar harus dijelaskan di docstring dan tidak boleh menggantikan
  assertion pada nilai yang diperiksa.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Tidak ada network dan sleep | `tools/quality/check_tests.py` (planned); review `tests/**`. |
| Assertion perilaku | Checker AST dan review test. |
| Determinisme golden | `tests/golden/**` (planned); golden update flag. |
| Fake COM dan Google | `tests/pdf/**` (planned), `tests/google/**` (planned); bagian 12.8. |
| Isolasi `tmp_path` | Checker dan review fixture. |
| Visual test eksplisit | `tests/visual/**` (planned); F3-ACCEPT. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
