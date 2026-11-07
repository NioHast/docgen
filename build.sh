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
cp "$CHAPTERS_PATH"/*.md "$TMPDIR/" 2>/dev/null || true
CHAPTER_FILES=$(find "$TMPDIR" -maxdepth 1 -name "bab*.md" | sort -V)
if [ -z "$CHAPTER_FILES" ]; then
  # Proposal memakai nama berangka (1-pendahuluan.md, ...), bukan bab*.md.
  CHAPTER_FILES=$(find "$TMPDIR" -maxdepth 1 -name "*.md" ! -name "cover.md" | sort -V)
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