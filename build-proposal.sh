#!/usr/bin/env bash
# Build proposal tesis MSI UNDIP dari examples/proposal/metadata.yml.
#
# Wrapper ini hanya memilih metadata dan nama keluaran; seluruh logika build
# tetap berada di build-docx.sh. Kontrak yang dipakai:
#   LAPORAN_METADATA    -> berkas metadata proposal (relatif ke root repo)
#   LAPORAN_REPORT_NAME -> nama keluaran tanpa ekstensi (Proposal.docx)
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

export LAPORAN_METADATA="examples/proposal/metadata.yml"
export LAPORAN_REPORT_NAME="Proposal"
# LAPORAN_CHAPTERS tidak perlu diset: build-docx.sh menurunkan
# examples/proposal/chapters dari direktori examples/proposal/metadata.yml.

bash build-docx.sh
