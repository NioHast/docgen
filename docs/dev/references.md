# Referensi Resmi

Registry ini adalah satu-satunya daftar label dan URL dokumentasi resmi untuk
teknologi yang dipakai repo. Dokumentasi aktif memakai label dari tabel di bawah
bila merujuk dokumentasi eksternal. Label harus unik; URL harus memakai skema
`http` atau `https` dan tidak boleh berulang.

## Registry

| Label | URL | Dipakai untuk |
| --- | --- | --- |
| Python 3.15 language reference | https://docs.python.org/3.15/reference/ | Sintaks, model data, dan semantik bahasa; `docs/dev/code-style.md`, `src/docgen/pipeline.py`, dan docstring modul. |
| Python 3.15 typing | https://docs.python.org/3.15/library/typing.html | Anotasi tipe, `Protocol`, dan tipe generik; `docs/dev/code-style.md`. |
| Python 3.15 pathlib | https://docs.python.org/3.15/library/pathlib.html | Operasi path dan berkas; `docs/dev/code-style.md`, `src/docgen/paths.py`. |
| Python 3.15 dataclasses | https://docs.python.org/3.15/library/dataclasses.html | Model data bernama; `docs/dev/code-style.md`. |
| PEP 649 | https://peps.python.org/pep-0649/ | Evaluasi anotasi secara defer; `docs/dev/code-style.md`. |
| OOXML ECMA-376 | https://ecma-international.org/publications-and-standards/standards/ecma-376/ | Struktur package dan WordprocessingML; `src/docgen/docx/package.py`, `src/docgen/docx/xml.py`, `docs/dev/docx/README.md`, `docs/dev/contracts/docx-api.md`. |
| Open XML SDK | https://learn.microsoft.com/en-us/office/open-xml/open-xml-sdk | Pemetaan API OOXML ke elemen Word; `docs/dev/docx/overview.md`. |
| WordprocessingML API reference | https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing?view=openxml-3.0.1 | Nama elemen dan properti `w:*`; `src/docgen/docx/` (`fields.py`, `sections.py`, `numbering.py`, `page.py`, `paragraphs.py`, `terms/model.py`), `docs/dev/docx/`, `docs/dev/contracts/docx-api.md`. |
| Word COM object model (VBA reference) | https://learn.microsoft.com/en-us/office/vba/api/overview/word | Otomasi Word melalui COM; `src/docgen/stages/office.py`, `scripts/word.ps1`, `docs/dev/pdf.md`. |
| Pandoc manual | https://pandoc.org/MANUAL.html | Konversi Markdown ke DOCX dan opsi CLI; `src/docgen/stages/pandoc.py`, `src/docgen/stages/front_matter.py`, `README.md`, `docs/dev/pipeline/overview.md`. |
| Pandoc installation | https://pandoc.org/installing.html | Prasyarat pemasangan Pandoc; `README.md`, `docs/user/troubleshooting.md`. |
| Pandoc Lua filters | https://pandoc.org/lua-filters.html | Referensi filter Lua; pipeline tidak memakai `--lua-filter`, tetapi kontrak historis menyebut paritasnya. |
| Ruff configuration | https://docs.astral.sh/ruff/configuration/ | Konfigurasi `[tool.ruff]`; `pyproject.toml`, `docs/dev/code-style.md`. |
| Ruff rules | https://docs.astral.sh/ruff/rules/ | Daftar kode aturan; `docs/dev/code-style.md`. |
| Ruff flake8-pytest-style | https://docs.astral.sh/ruff/rules/#flake8-pytest-style-pt | Aturan pytest yang dipilih untuk assertion dan raises; `docs/dev/code-style.md`, `docs/dev/test-quality.md`. |
| Ruff settings | https://docs.astral.sh/ruff/settings/ | Daftar pengaturan; `pyproject.toml`, `docs/dev/code-style.md`. |
| Ruff formatter | https://docs.astral.sh/ruff/formatter/ | Format otomatis dan `format --check`; `docs/dev/code-style.md`. |
| Ruff D101 | https://docs.astral.sh/ruff/rules/undocumented-public-class/ | Aturan docstring class publik yang diabaikan; `docs/dev/code-style.md`. |
| Ruff D102 | https://docs.astral.sh/ruff/rules/undocumented-public-method/ | Aturan docstring method publik yang diabaikan; `docs/dev/code-style.md`. |
| Ruff D103 | https://docs.astral.sh/ruff/rules/undocumented-public-function/ | Aturan docstring fungsi publik yang diabaikan; `docs/dev/code-style.md`. |
| Ruff D105 | https://docs.astral.sh/ruff/rules/undocumented-magic-method/ | Aturan docstring magic method yang diabaikan; `docs/dev/code-style.md`. |
| Ruff D107 | https://docs.astral.sh/ruff/rules/undocumented-public-init/ | Aturan docstring `__init__` yang diabaikan; `docs/dev/code-style.md`. |
| Ruff D202 | https://docs.astral.sh/ruff/rules/blank-line-after-function/ | Aturan baris kosong setelah docstring yang diabaikan; `docs/dev/code-style.md`. |
| Ruff D401 | https://docs.astral.sh/ruff/rules/non-imperative-mood/ | Aturan imperative mood yang diabaikan untuk docstring Indonesia; `docs/dev/code-style.md`. |
| Ruff D203 | https://docs.astral.sh/ruff/rules/incorrect-blank-line-before-class/ | Aturan yang diabaikan otomatis karena konflik dengan D211; `docs/dev/code-style.md`. |
| Ruff D211 | https://docs.astral.sh/ruff/rules/blank-line-before-class/ | Aturan docstring class yang dipakai; `docs/dev/code-style.md`. |
| Ruff D212 | https://docs.astral.sh/ruff/rules/multi-line-summary-first-line/ | Gaya ringkasan docstring yang dipakai; `docs/dev/code-style.md`. |
| Ruff D213 | https://docs.astral.sh/ruff/rules/multi-line-summary-second-line/ | Aturan yang diabaikan otomatis karena konflik dengan D212; `docs/dev/code-style.md`. |
| Ruff BLE001 | https://docs.astral.sh/ruff/rules/blind-except/ | Pengecualian boundary `# noqa`; `docs/dev/code-style.md`. |
| Ruff SIM118 | https://docs.astral.sh/ruff/rules/in-dict-keys/ | Pengecualian untuk objek non-Mapping; `docs/dev/code-style.md`. |
| Ruff E741 | https://docs.astral.sh/ruff/rules/ambiguous-variable-name/ | Per-file ignore `O` di `names.py`; `docs/dev/code-style.md`. |
| mypy configuration | https://mypy.readthedocs.io/en/stable/config_file.html | Konfigurasi `[tool.mypy]`; `pyproject.toml`, `docs/dev/code-style.md`. |
| mypy error codes | https://mypy.readthedocs.io/en/stable/error_code_list.html | Kode error dan `# type: ignore[kode]`; `docs/dev/code-style.md`. |
| pytest documentation | https://docs.pytest.org/en/stable/ | Penulisan dan menjalankan tes; `tests/`, `docs/dev/testing.md`. |
| pytest markers | https://docs.pytest.org/en/stable/how-to/mark.html | Marker `unit`, `integration`, `word`, dan `windows`; `pytest.ini`, `docs/dev/testing.md`. |
| Google Testing Blog - Test Behavior | https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html | Alasan test berfokus pada perilaku, bukan implementasi; `docs/dev/test-quality.md`. |
| Software Engineering at Google ch12 | https://abseil.io/resources/swe-book/html/ch12.html | Trade-off unit, integration, dan end-to-end test; `docs/dev/test-quality.md`. |
| Kent Beck Test Desiderata | https://testdesiderata.com/ | Sifat test yang diinginkan dan trade-off antarsifat; `docs/dev/test-quality.md`. |
| xUnit Test Patterns - Test Smells | http://xunitpatterns.com/TestSmells.html | Katalog gejala test; `docs/dev/test-quality.md`. |
| xUnit Test Patterns - Fragile Test | http://xunitpatterns.com/Fragile%20Test.html | Definisi dan perbaikan test yang rapuh; `docs/dev/test-quality.md`. |
| xUnit Test Patterns - Assertion Roulette | http://xunitpatterns.com/Assertion%20Roulette.html | Assertion tanpa pesan dan test yang terlalu ramai; `docs/dev/test-quality.md`. |
| pytest parametrize | https://docs.pytest.org/en/stable/how-to/parametrize.html | Test parametrik dan opsi id; `docs/dev/test-quality.md`. |
| pytest fixtures | https://docs.pytest.org/en/stable/how-to/fixtures.html | Setup, isolasi, dan resource test; `docs/dev/test-quality.md`. |
| pytest good practices | https://docs.pytest.org/en/stable/explanation/goodpractices.html | Struktur test dan praktik pytest; `docs/dev/test-quality.md`. |
| coverage.py | https://coverage.readthedocs.io/ | Pengukuran coverage sebagai diagnostik; `docs/dev/test-quality.md`. |
| coverage.py contexts | https://coverage.readthedocs.io/en/latest/contexts.html | Format dan pembacaan context dinamis dari `.coverage`; `docs/dev/test-quality.md`. |
| pytest-cov contexts | https://pytest-cov.readthedocs.io/en/stable/contexts.html | Opsi `--cov-context=test` untuk mencatat context per test; `docs/dev/test-quality.md`. |
| mutmut | https://github.com/boxed/mutmut | Mutation testing opsional untuk modul kritis; `docs/dev/test-quality.md`. |
| uv documentation | https://docs.astral.sh/uv/ | Environment, `uv run`, dan `uv sync`; `README.md`, `docs/dev/contributing.md`. |
| Mermaid CLI | https://github.com/mermaid-js/mermaid-cli | Perintah `mmdc` dan opsi render; `src/docgen/stages/mermaid.py`, `README.md`, `docs/user/mermaid.md`. |
| Mermaid documentation | https://mermaid.js.org/ | Sintaks diagram Mermaid; `docs/user/mermaid.md`. |
| lxml documentation | https://lxml.de/ | API `lxml.etree`; `src/docgen/docx/`, `docs/dev/contracts/docx-api.md`. |
| python-docx documentation | https://python-docx.readthedocs.io/ | Referensi pembanding untuk API DOCX; `docs/dev/contracts/docx-api.md`. |
| pypdf documentation | https://pypdf.readthedocs.io/ | Pemeriksaan PDF pada tes; `tests/integration/test_golden_pdf.py`. |
| ruamel.yaml documentation | https://yaml.dev/doc/ruamel.yaml/ | Parser YAML dan penanganan duplicate key; `src/docgen/config/common.py`. |
| Adeu GitHub | https://github.com/dealfluence/adeu | Source resmi SDK/CLI Adeu; `docs/dev/adeu-integration.md`. |
| Adeu PyPI | https://pypi.org/project/adeu/ | Distribusi paket Python SDK/CLI Adeu; `docs/dev/adeu-integration.md`. |
| Adeu MCP server npm | https://www.npmjs.com/package/@adeu/mcp-server | Server MCP eksternal untuk alur DOCX-LLM; bukan komponen repo ini; `docs/dev/adeu-integration.md`. |
| Adeu MCP tools | https://github.com/dealfluence/adeu/blob/main/skills/adeu-redlining/references/mcp-tools.md | Referensi tool MCP redlining Adeu; `docs/dev/adeu-integration.md`. |
| Adeu | https://adeu.ai | Situs perusahaan dan gambaran produk Adeu; `docs/dev/adeu-integration.md`. |

## Aturan pemakaian

- Registry ini sumber tunggal untuk URL dokumentasi eksternal. Jangan menulis
  URL resmi yang sama di banyak halaman; sebut label registry dan tautkan ke
  entri yang relevan bila pembaca perlu membuka dokumentasi.
- Hanya URL resmi atau primary source yang boleh masuk. Blog, forum, mirror,
  dan tautan pencarian tidak dipakai.
- Label harus unik dan URL tidak boleh duplikat. Perubahan entri wajib lolos
  `python tools/dev/check_docs.py`.
- Checker memeriksa tautan relatif di `README.md` dan `docs/**/*.md`,
  mengecualikan `docs/dev/archive/**`. Arsip dibekukan agar catatan sejarah
  tidak dipaksa berubah hanya karena tautan lama sudah tidak berlaku.
- URL eksternal di halaman lain belum diperiksa jaringannya. Checker hanya
  memvalidasi sintaks URL registry dan keberadaan target tautan relatif.
