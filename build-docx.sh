#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
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

# Resolve Python (handle WindowsApps stub redirector on Windows)
PYTHON_BIN="python3"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -V >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1 && python -V >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi

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
copy_asset "presets" "$TMPDIR" || true
copy_asset "scripts" "$TMPDIR" || true
copy_asset "tools" "$TMPDIR" || true

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

pandoc \
  "${INPUT_FILES[@]}" \
  "${PRESET_OPTS[@]}" \
  --metadata-file="metadata.yml" \
  --citeproc \
  --bibliography="references.bib" \
  --csl="apa.csl" \
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

if ! "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" apply \
  "$TMPDIR/Laporan-sect.docx" \
  --glossary "$GLOSSARY" \
  --review-file "$ISTILAH_REVIEW"; then
  echo "ERROR: apply istilah gagal; build dihentikan." >&2
  exit 1
fi

if ! "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" verify \
  "$TMPDIR/Laporan-sect.docx" \
  --glossary "$GLOSSARY"; then
  echo "ERROR: verify istilah gagal; build dihentikan. Lihat temuan di atas." >&2
  exit 1
fi

"$PYTHON_BIN" "$PAGENUM_SCRIPT" "$TMPDIR/Laporan-sect.docx" "$REPORT"

echo "=== DOCX BERHASIL DIBUAT ==="
echo "Lokasi: $REPORT"
