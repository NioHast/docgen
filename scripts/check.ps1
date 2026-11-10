<#
.SYNOPSIS
    Gerbang check lokal untuk repo docgen.

.DESCRIPTION
    Menjalankan pemeriksaan format, lint, tipe, kontrak import, test,
    dokumentasi, lockfile, dan kualitas test secara berurutan dari root repo.
    Skrip berhenti pada kegagalan pertama dan keluar dengan kode perintah yang
    gagal.

    Skrip ini tidak memakai Microsoft Word dan tidak mengubah berkas.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/check.ps1

.NOTES
    Skrip dapat dipanggil dari direktori mana pun; lokasi kerja dipindahkan
    ke root repo berdasarkan lokasi berkas skrip.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Join-Path $PSScriptRoot "..")

function Assert-Gate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[check] GAGAL: $Name"
        exit $LASTEXITCODE
    }
}

Write-Host "[check] 1/8 ruff format --check"
uv run --extra dev ruff format --check .
Assert-Gate "ruff format --check"

Write-Host "[check] 2/8 ruff check"
uv run --extra dev ruff check .
Assert-Gate "ruff check"

Write-Host "[check] 3/8 mypy"
uv run --extra dev mypy
Assert-Gate "mypy"

Write-Host "[check] 4/8 lint-imports"
uv run --extra dev lint-imports --config pyproject.toml --no-cache
Assert-Gate "lint-imports"

Write-Host "[check] 5/8 pytest"
uv run --extra dev pytest -q
Assert-Gate "pytest"

Write-Host "[check] 6/8 check_docs"
uv run python tools/dev/check_docs.py
Assert-Gate "check_docs"

Write-Host "[check] 7/8 uv lock --check"
uv lock --check
Assert-Gate "uv lock --check"

# Warning-only: belum memakai --fail-on karena backlog temuan test belum bersih.
Write-Host "[check] 8/8 check_tests (warning-only)"
uv run --extra dev python tools/dev/check_tests.py tests --format json > $null
Assert-Gate "check_tests"

Write-Host "[check] OK"
exit 0
