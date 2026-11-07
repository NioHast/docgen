#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# Build DOCX hanya membutuhkan Pandoc; lewati syarat Typst milik build PDF.
LAPORAN_ENV_SKIP_TYPST=1
# shellcheck source=tools/env.sh
source "$DIR/tools/env.sh"

# Build DOCX harus dijalankan dari Git Bash di Windows. WSL tidak dapat
# memanggil venv Windows dan path /mnt/c memicu WinError 5 pada python-docx.
if [ -r /proc/version ] && grep -qi "microsoft" /proc/version 2>/dev/null; then
  case "$DIR" in
    /mnt/c/*|/mnt/c)
      echo "ERROR: Jalankan build dari Git Bash, bukan WSL bash." >&2
      echo "       Alasan: venv Windows tidak bisa dipanggil dari WSL dan path /mnt/c memicu WinError 5." >&2
      exit 1
      ;;
  esac
fi

if [ -n "$1" ]; then
  OUTDIR="$(cd "$1" && pwd)"
elif [ -f "$(pwd)/metadata.yml" ] && [ -d "$(pwd)/chapters" ]; then
  OUTDIR="$(pwd)"
elif [ -f "$DIR/templates/default/metadata.yml" ] && [ -d "$DIR/templates/default/chapters" ]; then
  OUTDIR="$DIR/templates/default"
else
  OUTDIR="$DIR"
fi
REPORT="$OUTDIR/Laporan.docx"

# Resolve Python (handle WindowsApps stub redirector on Windows).
# Utamakan venv repo bila ada karena add_paragraph_ids.py membutuhkan
# python-docx/lxml; python sistem belum tentu memilikinya.
PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -V >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1 && python -V >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi
for VENV_PYTHON in "$DIR/.venv/Scripts/python.exe" "$DIR/.venv/bin/python"; do
  if [ -x "$VENV_PYTHON" ] && "$VENV_PYTHON" -V >/dev/null 2>&1; then
    PYTHON_BIN="$VENV_PYTHON"
    break
  fi
done

if [ ! -d "$OUTDIR/chapters" ]; then
  echo "ERROR: Direktori chapters/ tidak ditemukan."
  exit 1
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

FALLBACK_DIRS=(
  "$OUTDIR"
  "$DIR/templates/default"
  "$DIR"
  "$HOME/.agents/skills/laporan-generator/resources"
)

copy_asset() {
  local asset="$1"
  local dest="$2"
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -e "$base/$asset" ]; then
      cp -r "$base/$asset" "$dest/"
      return 0
    fi
  done
  return 1
}

copy_asset "cover.md" "$TMPDIR" || true
copy_asset "logo.jpg" "$TMPDIR" || true
copy_asset "reference.docx" "$TMPDIR" || true
copy_asset "docx.lua" "$TMPDIR" || true
copy_asset "metadata.yml" "$TMPDIR" || true
copy_asset "references.bib" "$TMPDIR" || true
copy_asset "apa.csl" "$TMPDIR" || true
copy_asset "refs" "$TMPDIR" || true
copy_asset "presets" "$TMPDIR" || true
copy_asset "scripts" "$TMPDIR" || true
copy_asset "tools" "$TMPDIR" || true

if [ ! -f "$TMPDIR/refs/ieee.csl" ]; then
  echo "ERROR: refs/ieee.csl tidak ditemukan; sitasi tidak dapat diproses." >&2
  echo "       Letakkan berkas CSL di refs/ieee.csl." >&2
  exit 1
fi

if [ -d "$OUTDIR/gambar" ]; then
  cp -r "$OUTDIR/gambar" "$TMPDIR/"
elif [ -d "$DIR/gambar" ]; then
  cp -r "$DIR/gambar" "$TMPDIR/"
fi

cp "$OUTDIR/chapters"/*.md "$TMPDIR/" 2>/dev/null || true
CHAPTER_FILES=$(find "$TMPDIR" -maxdepth 1 -name "bab*.md" | sort -V)
if [ -z "$CHAPTER_FILES" ]; then
  echo "ERROR: Tidak ada berkas bab*.md di direktori chapters/."
  exit 1
fi
INPUT_FILES=("$TMPDIR/cover.md")
while IFS= read -r f; do
  [ -n "$f" ] && INPUT_FILES+=("$f")
done < <(find "$TMPDIR" -maxdepth 1 -name "bab*.md" | sort -V)

cd "$TMPDIR"

PRESET_NAME=$(grep -E '^[[:space:]]*(preset|margin_preset):' "$TMPDIR/metadata.yml" 2>/dev/null | head -n 1 | cut -d: -f2- | tr -d '"'\''\r\n ')
PRESET_PATH=""
PRESET_OPTS=()
if [ -n "$PRESET_NAME" ] && [ -f "$TMPDIR/presets/${PRESET_NAME}.yml" ]; then
  PRESET_PATH="$TMPDIR/presets/${PRESET_NAME}.yml"
  PRESET_OPTS=("--metadata-file=$PRESET_PATH")
elif [ -f "$TMPDIR/presets/standard.yml" ]; then
  PRESET_PATH="$TMPDIR/presets/standard.yml"
  PRESET_OPTS=("--metadata-file=$PRESET_PATH")
else
  echo "ERROR: Preset format tidak ditemukan (metadata: '${PRESET_NAME:-<kosong>}')." >&2
  echo "       Sediakan presets/${PRESET_NAME}.yml atau presets/standard.yml." >&2
  exit 1
fi

STYLE_GENERATOR="$TMPDIR/tools/build_style.py"
if [ ! -f "$STYLE_GENERATOR" ]; then
  STYLE_GENERATOR="$DIR/tools/build_style.py"
fi
if [ ! -f "$STYLE_GENERATOR" ]; then
  echo "ERROR: tools/build_style.py tidak ditemukan; reference.docx tidak bisa digenerate dari preset." >&2
  exit 1
fi

GENERATED_REFERENCE="$TMPDIR/reference-generated.docx"
if ! "$PYTHON_BIN" "$STYLE_GENERATOR" --preset "$PRESET_PATH" --out "$GENERATED_REFERENCE"; then
  echo "ERROR: Gagal menghasilkan reference.docx dari preset '$PRESET_PATH'." >&2
  echo "       Build dihentikan; reference.docx lama TIDAK dipakai." >&2
  exit 1
fi
if [ ! -s "$GENERATED_REFERENCE" ]; then
  echo "ERROR: Generator tidak menghasilkan file reference.docx: $GENERATED_REFERENCE" >&2
  exit 1
fi

# --- Pemeriksaan istilah sebelum pandoc ------------------------------------
GLOSSARY="$OUTDIR/writing/istilah.tsv"
ISTILAH_REVIEW="$OUTDIR/review/istilah-baru.txt"

if [ -f "$DIR/.venv/Scripts/python.exe" ]; then
  ISTILAH_PYTHON="$DIR/.venv/Scripts/python.exe"
else
  ISTILAH_PYTHON="python"
fi

if ! "$ISTILAH_PYTHON" -c "import docx, lxml" >/dev/null 2>&1; then
  echo "ERROR: python-docx/lxml tidak tersedia untuk $ISTILAH_PYTHON." >&2
  echo "       Pasang dependensi dengan: pip install -r tools/requirements.txt" >&2
  exit 1
fi

if [ ! -f "$GLOSSARY" ]; then
  echo "ERROR: Glosarium tidak ditemukan: $GLOSSARY" >&2
  echo "       Modul istilah memerlukan writing/istilah.tsv." >&2
  exit 1
fi

ISTILAH_SCRIPT="$TMPDIR/tools/istilah.py"
if [ ! -f "$ISTILAH_SCRIPT" ]; then
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -f "$base/tools/istilah.py" ]; then
      ISTILAH_SCRIPT="$base/tools/istilah.py"
      break
    fi
  done
fi
if [ ! -f "$ISTILAH_SCRIPT" ]; then
  echo "ERROR: tools/istilah.py tidak ditemukan." >&2
  exit 1
fi

for CHAPTER in "$OUTDIR"/chapters/*.md; do
  [ -e "$CHAPTER" ] || continue
  CHECK_STATUS=0
  "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" check "$CHAPTER" \
    --glossary "$GLOSSARY" --review-file "$ISTILAH_REVIEW" || CHECK_STATUS=$?
  if [ "$CHECK_STATUS" -eq 2 ]; then
    echo "" >&2
    echo "ERROR: Masih ada penanda {{?istilah?}} yang belum diputuskan di:" >&2
    echo "       $CHAPTER" >&2
    echo "       Daftar penanda tercetak di atas. Putuskan lalu build ulang." >&2
    exit 1
  elif [ "$CHECK_STATUS" -ne 0 ]; then
    echo "ERROR: Pemeriksaan istilah gagal pada $CHAPTER." >&2
    exit "$CHECK_STATUS"
  fi
done

"${LAPORAN_PANDOC:-pandoc}" \
  "${INPUT_FILES[@]}" \
  "${PRESET_OPTS[@]}" \
  --metadata-file="metadata.yml" \
  --citeproc \
  --bibliography="references.bib" \
  --csl="refs/ieee.csl" \
  --metadata=reference-section-title="DAFTAR PUSTAKA" \
  --top-level-division=chapter \
  --reference-doc="$GENERATED_REFERENCE" \
  --lua-filter="docx.lua" \
  -o "$TMPDIR/Laporan-tmp.docx" 2>&1

FINALIZE_SCRIPT="$TMPDIR/scripts/finalize-docx.py"
PAGENUM_SCRIPT="$TMPDIR/scripts/docx-pagenum.py"
if [ ! -f "$FINALIZE_SCRIPT" ]; then
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -f "$base/scripts/finalize-docx.py" ]; then
      FINALIZE_SCRIPT="$base/scripts/finalize-docx.py"
      break
    fi
  done
fi
if [ ! -f "$PAGENUM_SCRIPT" ]; then
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -f "$base/scripts/docx-pagenum.py" ]; then
      PAGENUM_SCRIPT="$base/scripts/docx-pagenum.py"
      break
    fi
  done
fi

export PYTHONUTF8=1
"$PYTHON_BIN" "$FINALIZE_SCRIPT" "$TMPDIR/Laporan-tmp.docx" "$TMPDIR/Laporan-sect.docx"

# --- Caption/gambar/tabel (setelah finalize, sebelum istilah) --------------
FIGURES_SCRIPT="$TMPDIR/tools/format_figures.py"
if [ ! -f "$FIGURES_SCRIPT" ]; then
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -f "$base/tools/format_figures.py" ]; then
      FIGURES_SCRIPT="$base/tools/format_figures.py"
      break
    fi
  done
fi
if [ ! -f "$FIGURES_SCRIPT" ]; then
  echo "ERROR: tools/format_figures.py tidak ditemukan." >&2
  exit 1
fi

FIGURES_DOCX="$TMPDIR/Laporan-figs.docx"
if ! "$PYTHON_BIN" "$FIGURES_SCRIPT" --docx "$TMPDIR/Laporan-sect.docx" --out "$FIGURES_DOCX"; then
  echo "ERROR: format_figures.py gagal; build dihentikan." >&2
  echo "       Periksa pesan di atas untuk caption/gambar/tabel yang bermasalah." >&2
  exit 1
fi
if [ ! -s "$FIGURES_DOCX" ]; then
  echo "ERROR: format_figures.py tidak menghasilkan DOCX: $FIGURES_DOCX" >&2
  exit 1
fi

if ! "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" apply \
  "$FIGURES_DOCX" \
  --glossary "$GLOSSARY" \
  --review-file "$ISTILAH_REVIEW"; then
  echo "ERROR: apply istilah gagal; build dihentikan." >&2
  exit 1
fi

if ! "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" verify \
  "$FIGURES_DOCX" \
  --glossary "$GLOSSARY"; then
  echo "ERROR: verify istilah gagal; build dihentikan. Lihat temuan di atas." >&2
  exit 1
fi

"$PYTHON_BIN" "$PAGENUM_SCRIPT" "$FIGURES_DOCX" "$REPORT"

# --- ID paragraf + manifest Adeu (setelah finalize/istilah/pagenum) --------
mkdir -p "$OUTDIR/build"

PARAGRAPH_IDS_SCRIPT="$TMPDIR/tools/add_paragraph_ids.py"
if [ ! -f "$PARAGRAPH_IDS_SCRIPT" ]; then
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -f "$base/tools/add_paragraph_ids.py" ]; then
      PARAGRAPH_IDS_SCRIPT="$base/tools/add_paragraph_ids.py"
      break
    fi
  done
fi
if [ ! -f "$PARAGRAPH_IDS_SCRIPT" ]; then
  echo "ERROR: tools/add_paragraph_ids.py tidak ditemukan." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c "import docx, lxml" >/dev/null 2>&1; then
  echo "ERROR: python-docx/lxml tidak tersedia untuk $PYTHON_BIN." >&2
  echo "       tools/add_paragraph_ids.py memerlukan keduanya." >&2
  echo "       Pasang dependensi dengan: pip install -r tools/requirements.txt" >&2
  exit 1
fi

IDS_DOCX="$TMPDIR/Laporan-ids.docx"
if ! "$PYTHON_BIN" "$PARAGRAPH_IDS_SCRIPT" "$REPORT" \
  --out-docx "$IDS_DOCX" \
  --manifest "$OUTDIR/build/manifest.json" \
  --docx-name "Laporan.docx" \
  --source-dir "$OUTDIR/chapters"; then
  echo "ERROR: Gagal menambahkan ID paragraf ke $REPORT; build dihentikan." >&2
  exit 1
fi
if ! mv -f "$IDS_DOCX" "$REPORT"; then
  echo "ERROR: Gagal memindahkan DOCX ber-ID paragraf ke $REPORT." >&2
  exit 1
fi
rm -f "$IDS_DOCX"

echo "=== DOCX BERHASIL DIBUAT ==="
echo "Lokasi: $REPORT"
echo "Manifest: $OUTDIR/build/manifest.json"
