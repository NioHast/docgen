#!/usr/bin/env bash
# tools/env.sh — siapkan Pandoc + Typst native sesuai platform.
#
# Pemakaian (di-source dari skrip build):
#   source "$DIR/tools/env.sh"
#
# Windows (Git Bash/MSYS/Cygwin):
#   - Hanya memakai perkakas Windows-native.
#   - Direktori instalasi Pandoc/Typst Windows ditambahkan ke PATH.
#   - Tidak pernah memanggil WSL atau menerjemahkan path lintas platform.
#
# Linux (termasuk WSL):
#   - Hanya mencari `pandoc`/`typst` native di PATH.
#   - Tidak pernah mencari `.exe` atau lokasi instalasi Windows.
#
# LAPORAN_ENV_SKIP_TYPST=1 melewati pengecekan Typst dan dipakai build DOCX
# yang hanya membutuhkan Pandoc.
#
# Build PDF memakai Typst, build DOCX memakai pandoc + reference.docx.

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
      # WSL juga melaporkan Linux; seluruh toolchain-nya Debian-native.
      printf 'linux'
      ;;
    *)
      printf 'unknown'
      ;;
  esac
}

_LAPORAN_PLATFORM="$(_laporan_platform)"
_LAPORAN_SEARCH_DIRS=()

_laporan_path_add() {
  local dir="$1"
  [ -n "$dir" ] || return 0
  [ -d "$dir" ] || return 0
  _LAPORAN_SEARCH_DIRS+=("$dir")
  case ":$PATH:" in
    *":$dir:"*) ;;
    *)
      PATH="$dir:$PATH"
      export PATH
      ;;
  esac
}

# Path Windows (C:\...) -> path POSIX untuk Git Bash. cygpath adalah bagian
# dari Git for Windows; tidak ada pemanggilan WSL di sini.
_laporan_windows_path() {
  local path="$1"
  [ -n "$path" ] || return 1
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$path" 2>/dev/null && return 0
  fi
  printf '%s\n' "$path"
}

if [ "$_LAPORAN_PLATFORM" = "windows" ]; then
  _laporan_local="$(_laporan_windows_path "${LOCALAPPDATA:-}" 2>/dev/null || true)"
  if [ -n "$_laporan_local" ]; then
    _laporan_path_add "$_laporan_local/Pandoc"
    _laporan_path_add "$_laporan_local/Microsoft/WinGet/Links"
    for _typst_dir in "$_laporan_local"/Microsoft/WinGet/Packages/Typst.Typst_*/*/; do
      if [ -d "$_typst_dir" ]; then
        _laporan_path_add "${_typst_dir%/}"
      fi
    done
  fi

  for _laporan_env in PROGRAMFILES PROGRAMW6432; do
    _laporan_base="${!_laporan_env:-}"
    [ -n "$_laporan_base" ] || continue
    _laporan_posix="$(_laporan_windows_path "$_laporan_base" 2>/dev/null || true)"
    if [ -n "$_laporan_posix" ]; then
      _laporan_path_add "$_laporan_posix/Pandoc"
    fi
  done

  _laporan_profile="$(_laporan_windows_path "${USERPROFILE:-}" 2>/dev/null || true)"
  if [ -n "$_laporan_profile" ]; then
    _laporan_path_add "$_laporan_profile/.cargo/bin"
  fi
fi

_LAPORAN_SKIP_TYPST=0
if [ "${LAPORAN_ENV_SKIP_TYPST:-0}" = "1" ]; then
  _LAPORAN_SKIP_TYPST=1
fi

_laporan_searched_dirs() {
  if [ "${#_LAPORAN_SEARCH_DIRS[@]}" -eq 0 ]; then
    printf '%s\n' '<tidak ada direktori instalasi yang diperiksa>'
    return 0
  fi
  printf '%s\n' "${_LAPORAN_SEARCH_DIRS[@]}"
}

# Verifikasi akhir: gagal cepat dengan pesan yang bisa ditindaklanjuti.
if ! command -v pandoc >/dev/null 2>&1; then
  if [ "$_LAPORAN_PLATFORM" = "windows" ]; then
    _laporan_error \
      "Pandoc Windows tidak ditemukan." \
      "Platform terdeteksi: $_LAPORAN_PLATFORM." \
      "Instal Pandoc dari https://pandoc.org/installing.html atau jalankan" \
      "'winget install JohnMacFarlane.Pandoc', lalu buka Git Bash baru." \
      "Direktori yang diperiksa:" \
      "$(_laporan_searched_dirs)"
  else
    _laporan_error \
      "Pandoc native tidak ditemukan di PATH." \
      "Platform terdeteksi: $_LAPORAN_PLATFORM." \
      "Instal paket Debian: sudo apt install pandoc" \
      "atau pasang Pandoc native dan pastikan 'pandoc --version' berhasil."
  fi
fi

if [ "$_LAPORAN_SKIP_TYPST" -eq 0 ] && ! command -v typst >/dev/null 2>&1; then
  if [ "$_LAPORAN_PLATFORM" = "windows" ]; then
    _laporan_error \
      "Typst Windows tidak ditemukan." \
      "Platform terdeteksi: $_LAPORAN_PLATFORM." \
      "Instal Typst dari https://typst.app/ atau jalankan" \
      "'winget install Typst.Typst', lalu buka Git Bash baru." \
      "Build PDF membutuhkan Typst; build DOCX tidak." \
      "Direktori yang diperiksa:" \
      "$(_laporan_searched_dirs)"
  else
    _laporan_error \
      "Typst native tidak ditemukan di PATH." \
      "Platform terdeteksi: $_LAPORAN_PLATFORM." \
      "Instal Typst native dari https://typst.app/ atau 'cargo install typst-cli'," \
      "lalu pastikan 'typst --version' berhasil." \
      "Build PDF membutuhkan Typst; build DOCX tidak."
  fi
fi
