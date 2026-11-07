<#
.SYNOPSIS
    Memperbarui field DOCX (termasuk daftar isi/TOC) memakai Microsoft Word COM.

.DESCRIPTION
    Membuka dokumen di Microsoft Word secara tersembunyi, memaksa repaginasi,
    memperbarui seluruh field di badan dokumen dan seluruh TablesOfContents,
    lalu menyimpannya kembali ke berkas yang sama.

    Skrip ini ditujukan untuk Windows yang memiliki Microsoft Word desktop.
    Skrip tidak mengubah teks, style, atau struktur dokumen secara sengaja;
    perubahan yang terlihat hanyalah hasil perhitungan field oleh Word
    (misalnya nomor halaman TOC/PAGEREF).

.PARAMETER DocxPath
    Path ke berkas .docx yang akan diperbarui. Path relatif diresolusikan
    terhadap direktori kerja saat skrip dijalankan.

.PARAMETER Visible
    Tampilkan jendela Word. Berguna untuk men-debug proses pembaruan field.
    Default: Word berjalan tersembunyi.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/update_fields.ps1 -DocxPath Laporan.docx

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/update_fields.ps1 -DocxPath Laporan.docx -Visible

.NOTES
    Hanya tersedia di Windows dengan Microsoft Word terpasang. Langkah ini
    tidak dapat dijalankan di Linux/macOS/CI tanpa Word.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$DocxPath,

    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ExitCode = 0
$word = $null
$doc = $null

function Write-Log {
    param([string]$Message)
    Write-Host "[update_fields] $Message"
}

function Write-ErrorMessage {
    param([string]$Message)
    [Console]::Error.WriteLine("[update_fields] ERROR: $Message")
}

function Release-ComObject {
    param([object]$ComObject)

    if ($null -eq $ComObject) {
        return
    }

    try {
        if ([System.Runtime.InteropServices.Marshal]::IsComObject($ComObject)) {
            [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($ComObject)
        }
    }
    catch {
        # Objek mungkin sudah dilepas; abaikan kegagalan pelepasan.
    }
}

try {
    # --- Validasi path sebelum menyentuh COM -------------------------------
    try {
        $resolved = Resolve-Path -LiteralPath $DocxPath -ErrorAction Stop
    }
    catch {
        throw [System.IO.FileNotFoundException]::new(
            "Berkas DOCX tidak ditemukan: $DocxPath"
        )
    }

    if ($resolved.Provider.Name -ne 'FileSystem') {
        throw [System.ArgumentException]::new(
            "Path bukan berkas biasa: $DocxPath"
        )
    }

    $fullPath = $resolved.ProviderPath
    if (Test-Path -LiteralPath $fullPath -PathType Container) {
        throw [System.ArgumentException]::new(
            "Path menunjuk ke direktori, bukan berkas DOCX: $fullPath"
        )
    }

    if ([System.IO.Path]::GetExtension($fullPath) -ne '.docx') {
        throw [System.ArgumentException]::new(
            "Path bukan berkas .docx: $fullPath"
        )
    }

    # --- Buka Microsoft Word lewat COM ------------------------------------
    try {
        $word = New-Object -ComObject Word.Application
    }
    catch {
        throw [System.InvalidOperationException]::new(
            "Microsoft Word tidak terpasang atau COM Word tidak tersedia. " +
            "Langkah ini membutuhkan Microsoft Word desktop di Windows dan " +
            "tidak dapat dijalankan di Linux/macOS/CI. Detail: " +
            $_.Exception.Message
        )
    }

    $word.Visible = [bool]$Visible
    $word.DisplayAlerts = 0   # wdAlertsNone
    try {
        $word.ScreenUpdating = $false
    }
    catch {
        # Properti opsional; tidak semua instalasi mengeksposnya.
    }

    try {
        # ConfirmConversions=false, ReadOnly=false, AddToRecentFiles=false
        $doc = $word.Documents.Open($fullPath, $false, $false, $false)
    }
    catch {
        throw [System.InvalidOperationException]::new(
            "Gagal membuka dokumen di Word: $fullPath. " +
            "Pastikan berkas tidak sedang dibuka atau dikunci proses lain. " +
            "Detail: " + $_.Exception.Message
        )
    }

    Write-Log "Word $($word.Version) membuka: $fullPath"

    if ($doc.ReadOnly) {
        throw [System.InvalidOperationException]::new(
            "Dokumen terbuka dalam mode read-only: $fullPath. " +
            "Tutup dokumen di Word atau periksa izin/lock berkas, lalu coba lagi."
        )
    }

    # --- Perbarui field ----------------------------------------------------
    # Repaginate dulu agar Word menghitung ulang nomor halaman sebelum
    # PAGEREF/TOC di-update.
    [void]$doc.Repaginate()

    $fieldCount = $doc.Fields.Count
    [void]$doc.Fields.Update()

    $tocCount = $doc.TablesOfContents.Count
    for ($i = 1; $i -le $tocCount; $i++) {
        $toc = $null
        try {
            $toc = $doc.TablesOfContents.Item($i)
            [void]$toc.Update()
        }
        finally {
            Release-ComObject $toc
        }
    }

    # Pastikan layout final sudah stabil sebelum disimpan.
    [void]$doc.Repaginate()

    Write-Log "Field diperbarui: $fieldCount; daftar isi diperbarui: $tocCount"

    try {
        [void]$doc.Save()
    }
    catch {
        throw [System.IO.IOException]::new(
            "Gagal menyimpan dokumen: $fullPath. " +
            "Pastikan berkas tidak sedang dibuka di Word dan tidak read-only. " +
            "Detail: " + $_.Exception.Message
        )
    }
    Write-Log "Disimpan: $fullPath"

    $script:ExitCode = 0
}
catch {
    Write-ErrorMessage $_.Exception.Message
    $script:ExitCode = 1
}
finally {
    if ($null -ne $doc) {
        try {
            $doc.Close(0)   # wdDoNotSaveChanges; sudah Save() bila berhasil
        }
        catch {
            # Abaikan kegagalan penutupan; Word tetap akan di-Quit.
        }
        Release-ComObject $doc
        $doc = $null
    }

    if ($null -ne $word) {
        try {
            # Tanpa argumen: seluruh dokumen sudah ditutup dan disimpan.
            # Memakai argumen posisional dapat memicu error PSReference pada
            # PowerShell 5.1 karena parameter COM Quit bersifat by-ref.
            $word.Quit()
        }
        catch {
            # Abaikan kegagalan Quit; proses Word mungkin sudah tertutup.
        }
        Release-ComObject $word
        $word = $null
    }

    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

exit $script:ExitCode
