#!/usr/bin/env bash
# tools/env.sh — deteksi dan siapkan Pandoc + Typst untuk build laporan.
#
# Pemakaian (di-source dari skrip build):
#   source "$DIR/tools/env.sh"
#
# Yang dilakukan:
#   - Mendeteksi platform: Windows (Git Bash/MSYS/Cygwin), WSL, atau Linux.
#   - Menambahkan direktori Pandoc/Typst ke PATH bila belum ada.
#   - Di WSL, mengekspor LAPORAN_PANDOC/LAPORAN_TYPST karena executable Windows
#     (mis. typst.exe) tidak ditemukan oleh pencarian PATH Linux, dan Pandoc
#     distro Linux bisa lebih lama daripada Typst yang terpasang di Windows.
#   - Tidak mengubah direktori kerja dan tidak mencetak apa pun bila berhasil.
#   - Bila perkakas tidak ditemukan: pesan jelas + exit 1.
#   - LAPORAN_ENV_SKIP_TYPST=1 melewati pengecekan Typst dan tidak menyetel
#     LAPORAN_TYPST; dipakai build DOCX yang hanya membutuhkan Pandoc.
#
# Build PDF memakai Typst, build DOCX memakai pandoc + reference.docx.
# Keduanya berbagi file ini; build-docx.sh menyalakan LAPORAN_ENV_SKIP_TYPST.

# Aman bila di-source dua kali.
if [ "${_LAPORAN_ENV_LOADED:-0}" = "1" ]; then
  return 0 2>/dev/null || exit 0
fi
_LAPORAN_ENV_LOADED=1

_laporan_error() {
  printf '[env] ERROR: %s\n' "$1" >&2
  shift
  while [ "$#" -gt 0 ]; do
    printf '[env]        %s\n' "$1" >&2
    shift
  done
  exit 1
}

_laporan_platform() {
  local kernel
  kernel="$(uname -s 2>/dev/null || printf 'unknown')"
  case "$kernel" in
    MINGW*|MSYS*|CYGWIN*)
      printf 'windows'
      ;;
    Linux*)
      if [ -r /proc/version ] && grep -qi 'microsoft' /proc/version 2>/dev/null; then
        printf 'wsl'
      else
        printf 'linux'
      fi
      ;;
    *)
      printf 'unknown'
      ;;
  esac
}

_LAPORAN_PLATFORM="$(_laporan_platform)"

# Mengubah path Windows (C:\...) menjadi path POSIX yang bisa dipakai shell ini.
_laporan_to_posix() {
  local path="$1"
  [ -n "$path" ] || return 1
  if command -v wslpath >/dev/null 2>&1; then
    wslpath -u "$path" 2>/dev/null && return 0
  fi
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$path" 2>/dev/null && return 0
  fi
  printf '%s\n' "$path"
}

# Lokasi %LOCALAPPDATA% milik Windows, dalam bentuk path POSIX.
_laporan_local_appdata() {
  local win_path=""
  if [ -n "${LOCALAPPDATA:-}" ]; then
    win_path="$LOCALAPPDATA"
  elif command -v cmd.exe >/dev/null 2>&1; then
    win_path="$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r\n')"
  fi
  [ -n "$win_path" ] || return 1
  _laporan_to_posix "$win_path"
}

_laporan_path_add() {
  local dir="$1"
  [ -n "$dir" ] || return 0
  [ -d "$dir" ] || return 0
  case ":$PATH:" in
    *":$dir:"*) ;;
    *)
      PATH="$dir:$PATH"
      export PATH
      ;;
  esac
}

_LAPORAN_WIN_DIRS=()

_laporan_register_win_dir() {
  local dir="$1"
  [ -n "$dir" ] || return 0
  [ -d "$dir" ] || return 0
  _LAPORAN_WIN_DIRS+=("$dir")
  _laporan_path_add "$dir"
}

case "$_LAPORAN_PLATFORM" in
  windows|wsl)
    _WIN_LOCAL="$(_laporan_local_appdata 2>/dev/null || true)"
    if [ -n "$_WIN_LOCAL" ]; then
      _laporan_register_win_dir "$_WIN_LOCAL/Pandoc"
      _laporan_register_win_dir "$_WIN_LOCAL/Microsoft/WinGet/Links"
      for _typst_dir in "$_WIN_LOCAL"/Microsoft/WinGet/Packages/Typst.Typst_*/*/; do
        [ -d "$_typst_dir" ] && _laporan_register_win_dir "${_typst_dir%/}"
      done
    fi
    for _program_files in "${PROGRAMFILES:-}" "${PROGRAMW6432:-}" \
      "/mnt/c/Program Files" "/c/Program Files"; do
      [ -n "$_program_files" ] || continue
      _program_files="$(_laporan_to_posix "$_program_files" 2>/dev/null || printf '%s' "$_program_files")"
      _laporan_register_win_dir "$_program_files/Pandoc"
    done
    ;;
esac

_LAPORAN_SKIP_TYPST=0
if [ "${LAPORAN_ENV_SKIP_TYPST:-0}" = "1" ]; then
  _LAPORAN_SKIP_TYPST=1
fi

_LAPORAN_PANDOC_EXE=""
_LAPORAN_TYPST_EXE=""
for _win_dir in "${_LAPORAN_WIN_DIRS[@]}"; do
  if [ -z "$_LAPORAN_PANDOC_EXE" ] && [ -f "$_win_dir/pandoc.exe" ]; then
    _LAPORAN_PANDOC_EXE="$_win_dir/pandoc.exe"
  fi
  if [ -z "$_LAPORAN_TYPST_EXE" ] && [ -f "$_win_dir/typst.exe" ]; then
    _LAPORAN_TYPST_EXE="$_win_dir/typst.exe"
  fi
done

# Di WSL, executable Windows tidak ikut ditemukan oleh pencarian PATH Linux.
# Karena itu path lengkapnya diekspor agar build.sh bisa memberikannya ke
# pandoc (--pdf-engine) dan pandoc Windows.
if [ "$_LAPORAN_SKIP_TYPST" -eq 0 ] &&
  [ -n "$_LAPORAN_TYPST_EXE" ] && ! command -v typst >/dev/null 2>&1; then
  LAPORAN_TYPST="$_LAPORAN_TYPST_EXE"
fi

# Di WSL, Typst native biasanya tidak ada. Pasangan yang tersedia adalah
# Pandoc + Typst versi Windows. Pandoc distro Linux sering terlalu lama untuk
# sintaks Typst keluaran baru, jadi gunakan Pandoc Windows bila ada.
# Argumen path POSIX dikonversi ke format Windows sebelum diteruskan.
if [ "$_LAPORAN_PLATFORM" = "wsl" ] && [ -n "$_LAPORAN_PANDOC_EXE" ]; then
  _laporan_wsl_to_win() {
    local path="$1"
    case "$path" in
      /*) wslpath -w -- "$path" 2>/dev/null || printf '%s' "$path" ;;
      *) printf '%s' "$path" ;;
    esac
  }

  _laporan_pandoc_windows() {
    local -a args=()
    local arg flag value
    local want_output=0
    for arg in "$@"; do
      if [ "$want_output" -eq 1 ]; then
        args+=("$(_laporan_wsl_to_win "$arg")")
        want_output=0
        continue
      fi
      case "$arg" in
        -o|--output)
          args+=("$arg")
          want_output=1
          ;;
        --output=*)
          args+=("--output=$(_laporan_wsl_to_win "${arg#--output=}")")
          ;;
        --*=/*)
          flag="${arg%%=*}"
          value="${arg#*=}"
          args+=("$flag=$(_laporan_wsl_to_win "$value")")
          ;;
        /*)
          args+=("$(_laporan_wsl_to_win "$arg")")
          ;;
        *)
          args+=("$arg")
          ;;
      esac
    done
    "$_LAPORAN_PANDOC_EXE" "${args[@]}"
  }

  LAPORAN_PANDOC="_laporan_pandoc_windows"
fi

_laporan_searched_dirs() {
  if [ "${#_LAPORAN_WIN_DIRS[@]}" -eq 0 ]; then
    printf '%s\n' '<tidak ada direktori Windows yang terdeteksi>'
    return 0
  fi
  printf '%s\n' "${_LAPORAN_WIN_DIRS[@]}"
}

# Verifikasi akhir: gagal cepat dengan pesan yang bisa ditindaklanjuti.
if [ -z "${LAPORAN_PANDOC:-}" ] && ! command -v pandoc >/dev/null 2>&1; then
  _laporan_error \
    "Pandoc tidak ditemukan." \
    "Platform terdeteksi: $_LAPORAN_PLATFORM." \
    "Instal Pandoc dari https://pandoc.org/installing.html, atau pastikan" \
    "pandoc.exe ada di PATH / direktori berikut lalu jalankan ulang:" \
    "$(_laporan_searched_dirs)"
fi

if [ "$_LAPORAN_SKIP_TYPST" -eq 0 ] &&
  [ -z "${LAPORAN_TYPST:-}" ] && ! command -v typst >/dev/null 2>&1; then
  _laporan_error \
    "Typst tidak ditemukan." \
    "Platform terdeteksi: $_LAPORAN_PLATFORM." \
    "Instal Typst dari https://typst.app/, atau pastikan typst/typst.exe ada di PATH." \
    "Build PDF membutuhkan Typst; build DOCX tidak." \
    "Direktori yang diperiksa:" \
    "$(_laporan_searched_dirs)"
fi
