# Alat pengembang (`tools`)

## Tujuan

Folder ini berisi alat Python untuk pengembang dan peninjau, bukan kode
runtime `docgen`. Alat membaca repo atau DOCX hasil build, lalu mencetak
temuan; tidak ada yang diimpor oleh `src/docgen`. `tools/dev/` adalah rumah
untuk pemeriksa dan aturan prosa.

## Ownership

- [Testing](../docs/dev/testing.md) menjelaskan cara menjalankan tes alat dan
  baseline; [code style](../docs/dev/code-style.md) mengatur gaya Python
  alat; [registry referensi](../docs/dev/references.md) adalah sumber URL
  resmi.
- `tools/dev/rules.yml` adalah satu-satunya sumber pola prosa. Jangan
  menyalin regex ke skrip atau dokumen lain.
- Alat baru harus punya penggunaan jelas, exit code terdokumentasi, dan tes di
  `tests/test_*.py`. Perubahan pada alat tidak boleh mengubah perilaku runtime
  `docgen`.

## Alat yang tersedia

| Alat | Fungsi |
| --- | --- |
| `dev/check_docs.py` | Memeriksa tautan relatif di README/docs aktif dan validitas registry `docs/dev/references.md`. |
| `dev/check_prose.py` | Memeriksa pola kaidah, gaya, dan klise prosa Indonesia; aturan dibaca dari `dev/rules.yml`. |
| `dev/audit_terms.py` | Mengaudit italic istilah pada DOCX hasil build; hanya membaca dan menulis laporan Markdown. |
| `dev/check_tests.py` | Memindai AST fungsi `test_*`, mencetak laporan JSON atau Markdown, dan memakai warning sebagai default. `--fail-on` menerima `high`, `medium`, atau `low` dan mengubah temuan menjadi gate. |
| `dev/check_coverage.py` | Membaca `.coverage` hasil `pytest-cov`, membutuhkan `COVERAGE_CORE=ctrace`, dan melaporkan sinyal overlap, god test, serta baris integration-only. |
| `dev/rules.yml` | Data aturan prosa: kamus, akronim, singkatan, dan pola. |

## Alat dev vs resource runtime

- `tools/` adalah alat pengembang: dijalankan manual atau di CI, tidak
  dipaketkan ke wheel, dan tidak dipanggil pipeline.
- `scripts/` adalah resource runtime: `scripts/word.ps1` dipanggil
  `stages/office.py` untuk memperbarui field dan mengekspor PDF. Jangan
  memindahkan alat dev ke `scripts/` atau sebaliknya.
- Alat boleh memakai API `docgen` sebagai klien, tetapi `src/docgen` tidak
  boleh mengimpor `tools/`.

## Larangan

- Jangan menambah dependensi runtime ke `pyproject.toml` hanya untuk alat;
  gunakan dev dependency.
- Jangan mengakses jaringan atau mengubah file pengguna. Audit istilah bersifat
  read-only terhadap DOCX.
- Jangan menduplikasi aturan dari `rules.yml`, `references.md`, atau kontrak
  di dalam skrip.
- Jangan menulis output generated ke repo; gunakan path eksplisit pengguna
  atau direktori sementara.
- Jangan membuat alat yang diam-diam menjadi jalur build kedua.

## Tautan

- [Testing](../docs/dev/testing.md)
- [Code style](../docs/dev/code-style.md)
- [Registry referensi](../docs/dev/references.md)
- [Rencana refactor](../docs/dev/archive/refactor-plan.md)
- [Aturan prosa](dev/rules.yml)
- [README scripts](../scripts/README.md)
