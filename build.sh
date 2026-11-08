#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
# Siapkan Pandoc/Typst (PATH Windows/WSL) sebelum perkakas dipanggil.
# shellcheck source=tools/env.sh
source "$DIR/tools/env.sh"

# Proyek turunan (mis. proposal) dapat memakai metadata dan nama laporan lain
# tanpa menyalin skrip. Default tetap metadata.yml dan Laporan.
METADATA_NAME="${LAPORAN_METADATA:-metadata.yml}"
REPORT_NAME="${LAPORAN_REPORT_NAME:-Laporan}"

# Direktori bab: LAPORAN_CHAPTERS eksplisit menang. Bila metadata berada di
# subdirektori (mis. proposal/metadata.yml), default-nya <dir metadata>/chapters.
if [ -n "${LAPORAN_CHAPTERS:-}" ]; then
  CHAPTERS_DIR="$LAPORAN_CHAPTERS"
else
  case "$METADATA_NAME" in
    */*)
      METADATA_DIR="${METADATA_NAME%/*}"
      [ -n "$METADATA_DIR" ] || METADATA_DIR="."
      CHAPTERS_DIR="$METADATA_DIR/chapters"
      ;;
    *)
      CHAPTERS_DIR="chapters"
      ;;
  esac
fi

# Gabungkan path relatif dengan basis; path absolut dibiarkan apa adanya.
resolve_path() {
  local path="$1"
  local base="$2"
  case "$path" in
    /*|[A-Za-z]:*) printf '%s\n' "$path" ;;
    *) printf '%s/%s\n' "$base" "$path" ;;
  esac
}

if [ -n "$1" ]; then
  OUTDIR="$(cd "$1" && pwd)"
elif [ -f "$(resolve_path "$METADATA_NAME" "$(pwd)")" ] && [ -d "$(resolve_path "$CHAPTERS_DIR" "$(pwd)")" ]; then
  OUTDIR="$(pwd)"
elif [ -f "$(resolve_path "$METADATA_NAME" "$DIR/templates/default")" ] && [ -d "$(resolve_path "$CHAPTERS_DIR" "$DIR/templates/default")" ]; then
  OUTDIR="$DIR/templates/default"
else
  OUTDIR="$DIR"
fi
REPORT="$OUTDIR/${REPORT_NAME}.pdf"
CHAPTERS_PATH="$(resolve_path "$CHAPTERS_DIR" "$OUTDIR")"
CHAPTERS_PARENT="$(dirname "$CHAPTERS_PATH")"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

FALLBACK_DIRS=(
  "$OUTDIR"
  "$DIR/templates/default"
  "$DIR"
  "$HOME/.agents/skills/laporan-generator/resources"
)

# Preprocessing istilah Markdown membutuhkan Python. Build PDF sebelumnya
# tidak memerlukan Python, jadi tetap dukung python sistem bila .venv tidak ada.
PYTHON_BIN=""
PYTHON_IS_WINDOWS=0

# Di WSL, utamakan Python Linux agar path /mnt/c dan /tmp bisa dibaca
# langsung. Venv Windows hanya dipakai bila Python Linux tidak tersedia.
if [ "${_LAPORAN_PLATFORM:-}" = "wsl" ]; then
  if command -v python3 >/dev/null 2>&1 && python3 -V >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1 && python -V >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi

if [ -z "$PYTHON_BIN" ]; then
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
fi

case "$PYTHON_BIN" in
  *.exe|[A-Za-z]:*) PYTHON_IS_WINDOWS=1 ;;
esac

# Python Windows tidak mengenal path /mnt/c; konversi saat build berjalan di WSL.
python_path() {
  local path="$1"
  if [ "$PYTHON_IS_WINDOWS" = "1" ] && [ "${_LAPORAN_PLATFORM:-}" = "wsl" ]; then
    wslpath -w -- "$path" 2>/dev/null || printf '%s' "$path"
  else
    printf '%s' "$path"
  fi
}

if ! "$PYTHON_BIN" -V >/dev/null 2>&1; then
  echo "ERROR: Python 3 tidak ditemukan untuk preprocessing istilah Markdown." >&2
  echo "       Instal Python 3 atau sediakan .venv di direktori proyek." >&2
  exit 1
fi

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

# Salin metadata dengan nama aslinya. LAPORAN_METADATA boleh berupa path
# relatif terhadap OUTDIR/DIR atau path absolut.
copy_metadata() {
  local name="$1"
  local dest="$2"
  local base
  case "$name" in
    /*|[A-Za-z]:*)
      if [ -f "$name" ]; then
        cp "$name" "$dest/"
        return 0
      fi
      return 1
      ;;
  esac
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -f "$base/$name" ]; then
      cp "$base/$name" "$dest/"
      return 0
    fi
  done
  return 1
}

copy_asset "cover.md" "$TMPDIR" || true
copy_asset "template.typ" "$TMPDIR" || true
copy_asset "logo.jpg" "$TMPDIR" || true
if ! copy_metadata "$METADATA_NAME" "$TMPDIR"; then
  echo "ERROR: Berkas metadata '$METADATA_NAME' tidak ditemukan." >&2
  echo "       Sediakan metadata.yml atau set LAPORAN_METADATA." >&2
  exit 1
fi
METADATA_BASENAME="$(basename "$METADATA_NAME")"
copy_asset "references.bib" "$TMPDIR" || true
copy_asset "apa.csl" "$TMPDIR" || true
copy_asset "refs" "$TMPDIR" || true
copy_asset "presets" "$TMPDIR" || true

if [ ! -d "$CHAPTERS_PATH" ]; then
  echo "ERROR: Direktori $CHAPTERS_DIR tidak ditemukan." >&2
  echo "Buat folder $CHAPTERS_DIR dengan file .md (mis. bab1-pendahuluan.md atau 1-pendahuluan.md)." >&2
  exit 1
fi

# Preprocessing istilah sebelum Pandoc: hasilnya yang menjadi input, bukan
# chapters/ asli. Direktori keluaran berada di dalam TMPDIR agar tidak
# menimpa sumber dan otomatis dibersihkan oleh trap.
GLOSSARY=""
for base in "${FALLBACK_DIRS[@]}"; do
  if [ -f "$base/writing/istilah.tsv" ]; then
    GLOSSARY="$base/writing/istilah.tsv"
    break
  fi
done
if [ -z "$GLOSSARY" ]; then
  echo "ERROR: Glosarium writing/istilah.tsv tidak ditemukan." >&2
  echo "       Sediakan writing/istilah.tsv untuk preprocessing istilah PDF." >&2
  exit 1
fi

ISTILAH_MD_SCRIPT=""
for base in "${FALLBACK_DIRS[@]}"; do
  if [ -f "$base/tools/istilah_markdown.py" ]; then
    ISTILAH_MD_SCRIPT="$base/tools/istilah_markdown.py"
    break
  fi
done
if [ -z "$ISTILAH_MD_SCRIPT" ]; then
  echo "ERROR: tools/istilah_markdown.py tidak ditemukan." >&2
  exit 1
fi

PREPROCESSED_DIR="$TMPDIR/chapters-pre"
if ! "$PYTHON_BIN" "$(python_path "$ISTILAH_MD_SCRIPT")" \
  --src "$(python_path "$CHAPTERS_PATH")" \
  --glossary "$(python_path "$GLOSSARY")" \
  --out "$(python_path "$PREPROCESSED_DIR")"; then
  echo "ERROR: Preprocessing istilah Markdown gagal." >&2
  echo "       Periksa $GLOSSARY dan berkas .md di $CHAPTERS_DIR." >&2
  exit 1
fi

CHAPTER_FILES=$(find "$PREPROCESSED_DIR" -maxdepth 1 -name "bab*.md" | sort -V)
if [ -z "$CHAPTER_FILES" ]; then
  # Proposal memakai nama berangka (1-pendahuluan.md, ...), bukan bab*.md.
  CHAPTER_FILES=$(find "$PREPROCESSED_DIR" -maxdepth 1 -name "*.md" ! -name "cover.md" | sort -V)
fi
if [ -z "$CHAPTER_FILES" ]; then
  echo "ERROR: Tidak ada berkas .md di direktori $CHAPTERS_DIR." >&2
  exit 1
fi
INPUT_FILES=("$TMPDIR/cover.md")
while IFS= read -r f; do
  [ -n "$f" ] && INPUT_FILES+=("$f")
done <<< "$CHAPTER_FILES"

GAMBAR_DIR="$CHAPTERS_PARENT/gambar"
if [ -d "$GAMBAR_DIR" ]; then
  cp -r "$GAMBAR_DIR" "$TMPDIR/"
elif [ -d "$OUTDIR/gambar" ]; then
  cp -r "$OUTDIR/gambar" "$TMPDIR/"
elif [ -d "$DIR/gambar" ]; then
  cp -r "$DIR/gambar" "$TMPDIR/"
fi
if [ -d "$TMPDIR/gambar" ]; then
  IM_CONV="convert"
  command -v magick >/dev/null 2>&1 && IM_CONV="magick"
  find "$TMPDIR/gambar" -type f \( -name "*.png" -o -name "*.PNG" \) -exec $IM_CONV {} -alpha off {} \; 2>/dev/null || true
fi

cd "$TMPDIR"

PRESET_NAME=$(grep -E '^[[:space:]]*(preset|margin_preset):' "$TMPDIR/$METADATA_BASENAME" 2>/dev/null | head -n 1 | cut -d: -f2- | tr -d '"'\''\r\n ')
PRESET_PATH=""
PRESET_OPTS=()
if [ -n "$PRESET_NAME" ]; then
  if [ ! -f "$TMPDIR/presets/${PRESET_NAME}.yml" ]; then
    echo "ERROR: Preset '${PRESET_NAME}' tidak ditemukan di presets/. Perbaiki $METADATA_BASENAME." >&2
    exit 1
  fi
  PRESET_PATH="$TMPDIR/presets/${PRESET_NAME}.yml"
  PRESET_OPTS=("--metadata-file=$PRESET_PATH")
elif [ -f "$TMPDIR/presets/standard.yml" ]; then
  PRESET_PATH="$TMPDIR/presets/standard.yml"
  PRESET_OPTS=("--metadata-file=$PRESET_PATH")
else
  echo "ERROR: Preset format tidak ditemukan (metadata: '<kosong>')." >&2
  echo "       Sediakan presets/standard.yml." >&2
  exit 1
fi

# Gaya sitasi mengikuti kunci csl: pada preset; default turunan APA 7 UNDIP MSI.
CSL_PATH="refs/undip-msi.csl"
if [ -n "$PRESET_PATH" ]; then
  PRESET_CSL=$(grep -E '^[[:space:]]*csl:' "$PRESET_PATH" 2>/dev/null | head -n 1 | cut -d: -f2- | tr -d '"'\''\r\n ')
  if [ -n "$PRESET_CSL" ]; then
    CSL_PATH="$PRESET_CSL"
  fi
fi
case "$CSL_PATH" in
  /*|[A-Za-z]:*) CSL_FILE="$CSL_PATH" ;;
  *) CSL_FILE="$TMPDIR/$CSL_PATH" ;;
esac
if [ ! -f "$CSL_FILE" ]; then
  echo "ERROR: Berkas CSL '$CSL_PATH' tidak ditemukan; sitasi tidak dapat diproses." >&2
  echo "       Periksa kunci csl: pada preset atau sediakan refs/undip-msi.csl." >&2
  exit 1
fi

if ! "${LAPORAN_PANDOC:-pandoc}" \
  "${INPUT_FILES[@]}" \
  --template="template.typ" \
  "${PRESET_OPTS[@]}" \
  --metadata-file="$METADATA_BASENAME" \
  --citeproc \
  --bibliography="references.bib" \
  --csl="$CSL_PATH" \
  --metadata=reference-section-title="DAFTAR PUSTAKA" \
  --top-level-division=chapter \
  --pdf-engine="${LAPORAN_TYPST:-typst}" \
  --no-highlight \
  -o "$REPORT" 2>&1; then
  echo ""
  echo "[ERROR] BUILD GAGAL: Terjadi kesalahan saat kompilasi Pandoc/Typst."
  echo "Kemungkinan penyebab & solusi:"
  echo "  1. Sintaks YAML di $METADATA_BASENAME tidak valid -> Cek docs/metadata-schema.md"
  echo "  2. Berkas gambar tidak ditemukan atau rusak -> Cek path gambar di $GAMBAR_DIR/"
  echo "  3. Sintaks Markdown tidak didukung -> Cek docs/troubleshooting.md"
  echo "  4. Gunakan Docker jika ada masalah dependensi lokal: docker compose run --rm laporan-generator"
  exit 1
fi

echo ""
echo "=== PDF BERHASIL DIBUAT ==="
echo "Lokasi: $REPORT"