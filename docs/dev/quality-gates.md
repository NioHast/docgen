# Quality Gates

Halaman ini mencatat gate lokal AutoOffice, urutan eksekusinya, dan batas
offline-nya. Wrapper lama `scripts/check.ps1` sudah dihapus;
`tools/quality/gate.py` adalah satu-satunya gate, seperti dijelaskan di
[testing.md](testing.md).

## Prinsip

- Gate dijalankan lokal; tidak ada GitHub Actions dan tidak ada merge yang
  bergantung pada CI.
- Gate tidak memanggil Word/PowerPoint COM, Google API live, atau jaringan.
  Jalur nyata hanya dijalankan smoke manual di Windows pada gate final.
- Setiap langkah read-only terhadap repo. Output build, coverage HTML, dan
  cache ditulis di luar jalur yang di-track atau diabaikan Git.
- Gate berhenti pada kegagalan pertama kecuali `--keep-going` diberikan.
- Coverage dihitung untuk `src/autooffice` dengan kebijakan berbasis risiko:
  global line+branch minimal 90%, modul kritis 100%, adapter minimal 85%,
  sesuai [kontrak coverage](../contracts/coverage.md).

## Perintah

```bash
uv run python tools/quality/gate.py
uv run python tools/quality/gate.py --list
uv run python tools/quality/gate.py --dry-run
uv run python tools/quality/gate.py --dry-run lock no-legacy
uv run python tools/quality/gate.py lint types tests
uv run python tools/quality/gate.py --keep-going docs test-quality
```

`--list` mencetak nama dan deskripsi langkah. `--dry-run` mencetak perintah
tanpa menjalankannya. Nama langkah yang tidak dikenal ditolak dengan exit 2.

## Langkah gate

| Nama | Perintah | Tujuan |
| --- | --- | --- |
| `format` | `uv run ruff format --check .` | Pastikan format tidak berubah. |
| `lint` | `uv run ruff check .` | Lint seluruh repo. |
| `types` | `uv run mypy src/autooffice` | Type check paket AutoOffice. |
| `imports` | `uv run lint-imports` | Kontrak import antar domain. |
| `tests` | `uv run pytest -q --cov=autooffice --cov-branch --cov-fail-under=90` | Test dan ambang global. |
| `coverage-policy` | `uv run python tools/quality/check_coverage.py` | Kritis 100%, adapter 85%, detail baris/branch hilang. |
| `lock` | `uv lock --check` | Pastikan `uv.lock` mutakhir tanpa menulis. |
| `docs` | `uv run python tools/quality/check_docs.py` | Tautan, TOC, judul, fence, indeks, registry. |
| `test-quality` | `uv run python tools/quality/check_tests.py` | Assertion, sleep, network, dan penulisan path. |
| `no-legacy` | `uv run python tools/quality/check_no_legacy.py` | Pemeriksa path, package, entry point, dan teknologi legacy; blocking. |
| `python-style` | `uv run python tools/quality/check_python.py` | Future import, alias typing warisan, dan API stdlib deprecated. |

Langkah `coverage-policy` membaca `.coverage` hasil langkah `tests` tanpa
menjalankan ulang suite. Checker mencetak baris dan branch yang hilang untuk
setiap pemeriksaan yang gagal.

Langkah `no-legacy` menjalankan pemeriksa penuh dan bersifat blocking. Checker
memindai path, import, entry point, dan nama teknologi legacy; allowlist
eksplisit mencakup arsip, ADR, fixture golden, plan, execution log, dan guard
negatif. Temuan aktif menghentikan gate.

Langkah `python-style` bersifat blocking. Seluruh future import sudah
dibersihkan, sehingga setiap temuan checker harus diperbaiki dan tidak lagi
dibiarkan sebagai peringatan.

## Checker dokumentasi

`check_docs.py` memeriksa:

- tautan relatif di `README.md`, `docs/**/*.md`, dan README modul;
- TOC untuk dokumen lebih dari 150 baris dan anchor gaya GitHub;
- tepat satu judul level 1 dan bahasa pada setiap code fence;
- semua halaman `docs/` terjangkau dari `docs/README.md`;
- registry `docs/dev/references.md` memuat label dan URL unik yang valid.

`docs/dev/archive/**` dikecualikan. README internal `src/autooffice/**`
dimiliki lane domain dan tidak diperiksa sebagai dokumentasi kontrak.

## Checker kualitas test

`check_tests.py` memindai AST dan menolak:

- test tanpa assertion perilaku;
- `assert True`, `assert 1 == 1`, dan tautologi bentuk lain;
- `time.sleep`;
- akses `requests`, `urllib`, `httpx`, `aiohttp`, `socket`, atau `http.client`;
- penulisan yang jelas di luar `tmp_path`, termasuk `open()` mode tulis;
- `pytest.mark.skip` atau `skipif` tanpa alasan.

Checker mengabaikan `tests/fixtures/**`. Kode keluar 0 bersih, 1 ada
pelanggaran, dan 2 path tidak ditemukan.

## Gate final

Gate final menambahkan langkah yang tidak dijalankan gate lokal harian:

```bash
uv build
uv run autooffice doctor --target all
uv run autooffice check examples/demo-deck/deck.yaml
uv run autooffice build examples/demo-deck/deck.yaml --target all --out <tmp>
```

Langkah final dijalankan pada Windows dengan Word dan PowerPoint terpasang.
Smoke Google live adalah gerbang manual terpisah dan tidak boleh dipanggil oleh
`tools/quality/gate.py`.

## Rujukan

- [Kontrak test quality](../contracts/test-quality.md)
- [Kontrak coverage](../contracts/coverage.md)
- [Kontrak dokumentasi](../contracts/documentation.md)
- [Testing](testing.md)
