#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# tools/ wajib ada sebelum source: env.sh dan seluruh skrip tahap DOCX berada
# di sana. Tanpa ini build tidak boleh berjalan dengan aset proyek lain.
if [ ! -d "$DIR/tools" ]; then
  echo "ERROR: Direktori wajib 'tools/' tidak ditemukan di $DIR." >&2
  echo "       build-docx.sh membutuhkan tools/env.sh dan skrip tahap DOCX." >&2
  exit 1
fi

# Build DOCX hanya membutuhkan Pandoc; lewati syarat Typst milik build PDF.
LAPORAN_ENV_SKIP_TYPST=1
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
else
  OUTDIR="$DIR"
fi
REPORT="$OUTDIR/${REPORT_NAME}.docx"

# Manifest tesis tetap build/manifest.json agar reconcile/docs menemukannya.
# Laporan lain (mis. Proposal) memakai nama sendiri agar tidak saling menimpa.
if [ "$REPORT_NAME" = "Laporan" ]; then
  MANIFEST_PATH="$OUTDIR/build/manifest.json"
else
  MANIFEST_PATH="$OUTDIR/build/manifest-${REPORT_NAME}.json"
fi

CHAPTERS_PATH="$(resolve_path "$CHAPTERS_DIR" "$OUTDIR")"
CHAPTERS_PARENT="$(dirname "$CHAPTERS_PATH")"

# Resolve Python native platform. LAPORAN_PYTHON menang; default memakai venv
# proyek (.venv/Scripts/python.exe di Windows, .venv/bin/python di Linux)
# karena add_paragraph_ids.py membutuhkan python-docx/lxml.
PYTHON_BIN="${LAPORAN_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ "${_LAPORAN_PLATFORM:-}" = "windows" ]; then
    VENV_PYTHON="$DIR/.venv/Scripts/python.exe"
  else
    VENV_PYTHON="$DIR/.venv/bin/python"
  fi
  if [ -x "$VENV_PYTHON" ] && "$VENV_PYTHON" -V >/dev/null 2>&1; then
    PYTHON_BIN="$VENV_PYTHON"
  elif [ "${_LAPORAN_PLATFORM:-}" = "windows" ]; then
    if command -v python >/dev/null 2>&1 && python -V >/dev/null 2>&1; then
      PYTHON_BIN="python"
    fi
  elif command -v python3 >/dev/null 2>&1 && python3 -V >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1 && python -V >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi

if [ -z "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -V >/dev/null 2>&1; then
  echo "ERROR: Python 3 tidak ditemukan untuk pipeline DOCX." >&2
  if [ -n "${LAPORAN_PYTHON:-}" ]; then
    echo "       LAPORAN_PYTHON=$LAPORAN_PYTHON tidak dapat dijalankan." >&2
  fi
  echo "       Instal Python 3 atau sediakan .venv native platform." >&2
  exit 1
fi

if [ ! -d "$CHAPTERS_PATH" ]; then
  echo "ERROR: Direktori $CHAPTERS_DIR tidak ditemukan." >&2
  exit 1
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

FALLBACK_DIRS=(
  "$OUTDIR"
  "$DIR"
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

# Aset inti tidak boleh hilang diam-diam: tanpa aset ini build akan memakai
# default Pandoc atau menghasilkan dokumen yang salah format.
require_asset() {
  local asset="$1"
  if copy_asset "$asset" "$TMPDIR"; then
    return 0
  fi
  echo "ERROR: Aset wajib '$asset' tidak ditemukan." >&2
  echo "       Dicari di:" >&2
  for base in "${FALLBACK_DIRS[@]}"; do
    printf '         - %s/%s\n' "$base" "$asset" >&2
  done
  echo "       Build dihentikan agar tidak memakai aset dari proyek lain." >&2
  exit 1
}

# Varian untuk aset yang harus tetap berada di subdirektori relatifnya
# (mis. refs/undip-msi.csl).
require_asset_path() {
  local asset="$1"
  local base candidate
  for base in "${FALLBACK_DIRS[@]}"; do
    candidate="$base/$asset"
    if [ -f "$candidate" ]; then
      mkdir -p "$TMPDIR/$(dirname "$asset")"
      cp "$candidate" "$TMPDIR/$asset"
      return 0
    fi
  done
  echo "ERROR: Aset wajib '$asset' tidak ditemukan." >&2
  echo "       Dicari di:" >&2
  for base in "${FALLBACK_DIRS[@]}"; do
    printf '         - %s/%s\n' "$base" "$asset" >&2
  done
  echo "       Build dihentikan agar tidak memakai aset dari proyek lain." >&2
  exit 1
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

# Cari script tahap DOCX di salinan $TMPDIR/tools, lalu di FALLBACK_DIRS.
resolve_tool() {
  local name="$1"
  local candidate="$TMPDIR/tools/$name"
  local base
  if [ -f "$candidate" ]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  for base in "${FALLBACK_DIRS[@]}"; do
    if [ -f "$base/tools/$name" ]; then
      printf '%s\n' "$base/tools/$name"
      return 0
    fi
  done
  return 1
}

# Cover mengikuti direktori metadata bila tersedia (mis. proposal/cover.md).
# Default tetap cover.md root agar perilaku tesis tidak berubah.
COVER_SOURCE=""
case "$METADATA_NAME" in
  */*)
    COVER_DIR="${METADATA_NAME%/*}"
    [ -n "$COVER_DIR" ] || COVER_DIR="."
    for base in "${FALLBACK_DIRS[@]}"; do
      candidate="$(resolve_path "$COVER_DIR/cover.md" "$base")"
      if [ -f "$candidate" ]; then
        COVER_SOURCE="$candidate"
        break
      fi
    done
    ;;
esac
if [ -n "$COVER_SOURCE" ]; then
  cp "$COVER_SOURCE" "$TMPDIR/cover.md"
else
  require_asset "cover.md"
fi
# Logo wajib: cover selalu merujuk logo.jpg, jadi build harus berhenti bila
# aset ini hilang agar tidak menghasilkan sampul tanpa logo.
require_asset "logo.jpg"
require_asset "reference.docx"
require_asset "docx.lua"
if ! copy_metadata "$METADATA_NAME" "$TMPDIR"; then
  echo "ERROR: Berkas metadata '$METADATA_NAME' tidak ditemukan." >&2
  echo "       Sediakan metadata.yml atau set LAPORAN_METADATA." >&2
  echo "       Dicari di:" >&2
  for base in "${FALLBACK_DIRS[@]}"; do
    printf '         - %s/%s\n' "$base" "$METADATA_NAME" >&2
  done
  exit 1
fi
METADATA_BASENAME="$(basename "$METADATA_NAME")"
require_asset "references.bib"
copy_asset "apa.csl" "$TMPDIR" || true
require_asset_path "refs/undip-msi.csl"
# refs/ lainnya (mis. ieee.csl) tetap disalin bila ada agar preset lain bisa
# memakai CSL alternatif; refs/undip-msi.csl sudah diwajibkan di atas.
copy_asset "refs" "$TMPDIR" || true
require_asset "presets"
require_asset "scripts"
require_asset "tools"

GAMBAR_DIR="$CHAPTERS_PARENT/gambar"
if [ -d "$GAMBAR_DIR" ]; then
  cp -r "$GAMBAR_DIR" "$TMPDIR/"
elif [ -d "$OUTDIR/gambar" ]; then
  cp -r "$OUTDIR/gambar" "$TMPDIR/"
elif [ -d "$DIR/gambar" ]; then
  cp -r "$DIR/gambar" "$TMPDIR/"
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
PRESET_CSL=$(grep -E '^[[:space:]]*csl:' "$PRESET_PATH" 2>/dev/null | head -n 1 | cut -d: -f2- | tr -d '"'\''\r\n ')
if [ -n "$PRESET_CSL" ]; then
  CSL_PATH="$PRESET_CSL"
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

# Pakai Python yang sudah dipilih di awal build. PYTHON_BIN sudah
# memprioritaskan .venv/Scripts/python.exe (Windows) atau .venv/bin/python
# (Linux), lalu fallback ke python3/python sistem.
ISTILAH_PYTHON="$PYTHON_BIN"

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

for CHAPTER in "$CHAPTERS_PATH"/*.md; do
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

# `python -m laporan build` meneruskan toc dari struktur lewat environment.
# Nilai ini adalah metadata Pandoc eksplisit sehingga menimpa metadata.yml;
# build langsung tanpa env tetap memakai kunci `toc` di metadata proyek
# (docx.lua memakai default true bila kunci tidak ada).
TOC_OPTS=()
if [ -n "${LAPORAN_TOC:-}" ]; then
  TOC_OPTS=("--metadata=toc=${LAPORAN_TOC}")
fi

if ! pandoc \
  "${INPUT_FILES[@]}" \
  "${PRESET_OPTS[@]}" \
  --metadata-file="$METADATA_BASENAME" \
  "${TOC_OPTS[@]}" \
  --citeproc \
  --bibliography="references.bib" \
  --csl="$CSL_PATH" \
  --metadata=reference-section-title="DAFTAR PUSTAKA" \
  --top-level-division=chapter \
  --reference-doc="$GENERATED_REFERENCE" \
  --lua-filter="docx.lua" \
  -o "$TMPDIR/Laporan-tmp.docx" 2>&1; then
  echo "ERROR: Pandoc gagal menghasilkan DOCX; build dihentikan." >&2
  exit 1
fi

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
if [ ! -f "$FINALIZE_SCRIPT" ]; then
  echo "ERROR: scripts/finalize-docx.py tidak ditemukan." >&2
  exit 1
fi
if ! "$PYTHON_BIN" "$FINALIZE_SCRIPT" "$TMPDIR/Laporan-tmp.docx" "$TMPDIR/Laporan-sect.docx"; then
  echo "ERROR: finalize-docx.py gagal; build dihentikan." >&2
  exit 1
fi
if [ ! -s "$TMPDIR/Laporan-sect.docx" ]; then
  echo "ERROR: finalize-docx.py tidak menghasilkan DOCX: $TMPDIR/Laporan-sect.docx" >&2
  exit 1
fi

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

# --- Normalisasi layout, kode, dan persamaan -------------------------------
NORMALIZE_SCRIPT="$(resolve_tool normalize_layout.py)" || {
  echo "ERROR: tools/normalize_layout.py tidak ditemukan." >&2
  exit 1
}
NORMALIZE_DOCX="$TMPDIR/Laporan-layout.docx"
if ! "$PYTHON_BIN" "$NORMALIZE_SCRIPT" --docx "$FIGURES_DOCX" --out "$NORMALIZE_DOCX"; then
  echo "ERROR: normalize_layout.py gagal; build dihentikan." >&2
  exit 1
fi
if [ ! -s "$NORMALIZE_DOCX" ]; then
  echo "ERROR: normalize_layout.py tidak menghasilkan DOCX: $NORMALIZE_DOCX" >&2
  exit 1
fi

CODE_SCRIPT="$(resolve_tool format_code.py)" || {
  echo "ERROR: tools/format_code.py tidak ditemukan." >&2
  exit 1
}
CODE_DOCX="$TMPDIR/Laporan-code.docx"
if ! "$PYTHON_BIN" "$CODE_SCRIPT" --docx "$NORMALIZE_DOCX" --out "$CODE_DOCX"; then
  echo "ERROR: format_code.py gagal; build dihentikan." >&2
  exit 1
fi
if [ ! -s "$CODE_DOCX" ]; then
  echo "ERROR: format_code.py tidak menghasilkan DOCX: $CODE_DOCX" >&2
  exit 1
fi

EQUATIONS_SCRIPT="$(resolve_tool format_equations.py)" || {
  echo "ERROR: tools/format_equations.py tidak ditemukan." >&2
  exit 1
}
EQUATIONS_DOCX="$TMPDIR/Laporan-eq.docx"
if ! "$PYTHON_BIN" "$EQUATIONS_SCRIPT" --docx "$CODE_DOCX" --out "$EQUATIONS_DOCX"; then
  echo "ERROR: format_equations.py gagal; build dihentikan." >&2
  exit 1
fi
if [ ! -s "$EQUATIONS_DOCX" ]; then
  echo "ERROR: format_equations.py tidak menghasilkan DOCX: $EQUATIONS_DOCX" >&2
  exit 1
fi

# --- Numbering daftar dan paragraf kosong ----------------------------------
NUMBERING_SCRIPT="$(resolve_tool format_numbering.py)" || {
  echo "ERROR: tools/format_numbering.py tidak ditemukan." >&2
  exit 1
}
NUMBERING_DOCX="$TMPDIR/Laporan-numbering.docx"
if ! "$PYTHON_BIN" "$NUMBERING_SCRIPT" --docx "$EQUATIONS_DOCX" --out "$NUMBERING_DOCX"; then
  echo "ERROR: format_numbering.py gagal; build dihentikan." >&2
  exit 1
fi
if [ ! -s "$NUMBERING_DOCX" ]; then
  echo "ERROR: format_numbering.py tidak menghasilkan DOCX: $NUMBERING_DOCX" >&2
  exit 1
fi

BLANK_LINES_SCRIPT="$(resolve_tool insert_blank_lines.py)" || {
  echo "ERROR: tools/insert_blank_lines.py tidak ditemukan." >&2
  exit 1
}
BLANK_LINES_DOCX="$TMPDIR/Laporan-blank.docx"
if ! "$PYTHON_BIN" "$BLANK_LINES_SCRIPT" --docx "$NUMBERING_DOCX" --out "$BLANK_LINES_DOCX"; then
  echo "ERROR: insert_blank_lines.py gagal; build dihentikan." >&2
  exit 1
fi
if [ ! -s "$BLANK_LINES_DOCX" ]; then
  echo "ERROR: insert_blank_lines.py tidak menghasilkan DOCX: $BLANK_LINES_DOCX" >&2
  exit 1
fi

# --- Istilah (setelah format kode/persamaan/numbering/blank lines) ----------
# istilah.py apply bekerja in-place; pakai salinan agar output tahap sebelumnya
# tetap utuh dan rantai tidak menimpa input di tengah jalan.
ISTILAH_DOCX="$TMPDIR/Laporan-istilah.docx"
if ! cp "$BLANK_LINES_DOCX" "$ISTILAH_DOCX"; then
  echo "ERROR: Gagal menyalin DOCX ke $ISTILAH_DOCX." >&2
  exit 1
fi

if ! "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" apply \
  "$ISTILAH_DOCX" \
  --glossary "$GLOSSARY" \
  --review-file "$ISTILAH_REVIEW"; then
  echo "ERROR: apply istilah gagal; build dihentikan." >&2
  exit 1
fi

if ! "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" verify \
  "$ISTILAH_DOCX" \
  --glossary "$GLOSSARY"; then
  echo "ERROR: verify istilah gagal; build dihentikan. Lihat temuan di atas." >&2
  exit 1
fi

if [ ! -f "$PAGENUM_SCRIPT" ]; then
  echo "ERROR: scripts/docx-pagenum.py tidak ditemukan." >&2
  exit 1
fi
if ! "$PYTHON_BIN" "$PAGENUM_SCRIPT" "$ISTILAH_DOCX" "$REPORT"; then
  echo "ERROR: docx-pagenum.py gagal; build dihentikan." >&2
  exit 1
fi

# --- Finalisasi field Word (Windows) / pembersihan settings (Linux) -------
# Word hanya dipakai di Windows. Di Linux, field TOC memakai cache terakhir
# dan updateFields dibersihkan langsung oleh scripts/finalize-docx.py.
# Jalankan sebelum add_paragraph_ids.py agar manifest mencerminkan DOCX final.
if [ "${_LAPORAN_PLATFORM:-}" = "windows" ]; then
  WORD_FINALIZE_SCRIPT="$(resolve_tool word_finalize.py)" || {
    echo "ERROR: tools/word_finalize.py tidak ditemukan." >&2
    exit 1
  }
  if ! "$PYTHON_BIN" "$WORD_FINALIZE_SCRIPT" "$REPORT"; then
    echo "ERROR: word_finalize.py gagal; build dihentikan." >&2
    exit 1
  fi
else
  echo "[WARN] Word dilewati: finalisasi field Word hanya tersedia di Windows." >&2
  echo "[WARN] TOC memakai cache terakhir; updateFields dibersihkan tanpa Word." >&2
  if ! "$PYTHON_BIN" "$FINALIZE_SCRIPT" --in-place "$REPORT"; then
    echo "ERROR: gagal membersihkan updateFields pada $REPORT." >&2
    exit 1
  fi
fi

# --- Verifikasi istilah pada DOCX final setelah finalisasi field -----------
# Word dapat mengubah run/style saat memperbarui field; verifikasi ulang agar
# penandaan istilah yang rusak tidak lolos ke manifest.
if ! "$ISTILAH_PYTHON" "$ISTILAH_SCRIPT" verify \
  "$REPORT" \
  --glossary "$GLOSSARY"; then
  echo "ERROR: verify istilah setelah finalisasi Word gagal; build dihentikan." >&2
  echo "       Lihat temuan di atas dan periksa perubahan Word pada DOCX." >&2
  exit 1
fi

# --- ID paragraf + manifest Adeu (dari DOCX final setelah Word) ------------
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
  --manifest "$MANIFEST_PATH" \
  --docx-name "${REPORT_NAME}.docx" \
  --source-dir "$CHAPTERS_PATH"; then
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
echo "Manifest: $MANIFEST_PATH"
