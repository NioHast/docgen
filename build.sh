#!/usr/bin/env bash
# Bangun PDF dari DOCX final.
#
# Alur:
#   1. Bila <REPORT_NAME>.docx belum ada, jalankan build-docx.sh.
#   2. Ekspor DOCX ke PDF lewat tools/export_pdf.py:
#      - Windows: Microsoft Word COM (field + TOC diperbarui).
#      - Debian/Linux: LibreOffice headless (soffice).
#
# Tidak ada lagi Pandoc -> Typst di jalur PDF. Glosarium, caption, penomoran,
# dan nomor halaman sudah ditangani pipeline DOCX.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# Proyek turunan (mis. proposal/tugas) dapat memakai metadata dan nama laporan
# lain tanpa menyalin skrip. Default tetap metadata.yml dan Laporan.
METADATA_NAME="${LAPORAN_METADATA:-metadata.yml}"
REPORT_NAME="${LAPORAN_REPORT_NAME:-Laporan}"

# Direktori bab: LAPORAN_CHAPTERS eksplisit menang. Bila metadata berada di
# subdirektori (mis. examples/proposal/metadata.yml), default-nya
# <dir metadata>/chapters.
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

if [ -n "${1:-}" ]; then
  OUTDIR="$(cd "$1" && pwd)"
elif [ -f "$(resolve_path "$METADATA_NAME" "$(pwd)")" ] && [ -d "$(resolve_path "$CHAPTERS_DIR" "$(pwd)")" ]; then
  OUTDIR="$(pwd)"
else
  OUTDIR="$DIR"
fi

DOCX="$OUTDIR/${REPORT_NAME}.docx"
PDF="$OUTDIR/${REPORT_NAME}.pdf"

# Python 3 native platform. LAPORAN_PYTHON menang; lalu venv proyek; lalu
# python3/python dari PATH. export_pdf.py hanya memakai pustaka standar.
case "$(uname -s 2>/dev/null || printf 'unknown')" in
  MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
  Linux*) PLATFORM="linux" ;;
  *) PLATFORM="unknown" ;;
esac

if [ "$PLATFORM" = "windows" ]; then
  VENV_PYTHON="$DIR/.venv/Scripts/python.exe"
  PATH_PYTHONS="python python3"
else
  VENV_PYTHON="$DIR/.venv/bin/python"
  PATH_PYTHONS="python3 python"
fi

PYTHON_BIN="${LAPORAN_PYTHON:-}"
if [ -z "$PYTHON_BIN" ] && [ -x "$VENV_PYTHON" ] \
  && "$VENV_PYTHON" -V >/dev/null 2>&1; then
  PYTHON_BIN="$VENV_PYTHON"
fi
if [ -z "$PYTHON_BIN" ]; then
  for candidate in $PATH_PYTHONS; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -V >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
if [ -z "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -V >/dev/null 2>&1; then
  echo "ERROR: Python 3 tidak ditemukan untuk ekspor PDF." >&2
  if [ -n "${LAPORAN_PYTHON:-}" ]; then
    echo "       LAPORAN_PYTHON=$LAPORAN_PYTHON tidak dapat dijalankan." >&2
  fi
  echo "       Instal Python 3 atau sediakan .venv native platform." >&2
  exit 1
fi

EXPORT_SCRIPT="$DIR/tools/export_pdf.py"
if [ ! -f "$EXPORT_SCRIPT" ]; then
  echo "ERROR: tools/export_pdf.py tidak ditemukan di $DIR/tools." >&2
  exit 1
fi

if [ ! -f "$DOCX" ]; then
  echo "[INFO] DOCX belum ada: $DOCX"
  echo "[INFO] Menjalankan build-docx.sh lebih dulu."
  LAPORAN_METADATA="$METADATA_NAME" \
  LAPORAN_CHAPTERS="$CHAPTERS_DIR" \
  LAPORAN_REPORT_NAME="$REPORT_NAME" \
    "$DIR/build-docx.sh" "$OUTDIR"
fi

if [ ! -f "$DOCX" ]; then
  echo "ERROR: DOCX tidak ditemukan setelah build-docx.sh: $DOCX" >&2
  exit 1
fi

echo "[INFO] Sumber PDF: $DOCX"

export PYTHONUTF8=1

if ! "$PYTHON_BIN" "$EXPORT_SCRIPT" "$DOCX" --output "$PDF"; then
  echo "" >&2
  echo "[ERROR] EKSPOR PDF GAGAL." >&2
  echo "  1. Windows: pastikan Microsoft Word desktop terpasang dan DOCX" >&2
  echo "     sumber dapat dibaca." >&2
  echo "  2. Debian/Linux: pastikan LibreOffice terpasang (soffice) dan tidak" >&2
  echo "     ada proses lain yang mengunci PDF tujuan." >&2
  echo "  3. Periksa pesan error di atas untuk detailnya." >&2
  exit 1
fi

if [ ! -f "$PDF" ]; then
  echo "ERROR: PDF tidak terbentuk: $PDF" >&2
  exit 1
fi

echo ""
echo "=== PDF BERHASIL DIBUAT ==="
echo "Sumber: $DOCX"
echo "Lokasi: $PDF"
