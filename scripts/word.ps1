<#
.SYNOPSIS
    Adapter tunggal Microsoft Word untuk finalisasi field DOCX dan ekspor PDF.

.DESCRIPTION
    Satu skrip untuk dua aksi:

    - Tanpa -PdfPath: buka DOCX, repaginate, perbarui seluruh field dan
      TableOfContents, lalu simpan DOCX di tempat.
    - Dengan -PdfPath: buat snapshot DOCX di direktori sementara, buka
      snapshot, repaginate, perbarui field dan TableOfContents, ekspor PDF
      dengan ExportAsFixedFormat, lalu tutup snapshot tanpa menyimpan DOCX.
      DOCX sumber tidak pernah diubah.

    Skrip ini hanya untuk Windows dengan Microsoft Word desktop terpasang.

.PARAMETER DocxPath
    Path ke berkas .docx. Path relatif diresolusikan terhadap direktori kerja
    saat skrip dijalankan.

.PARAMETER PdfPath
    Opsional. Path tujuan .pdf. Bila diberikan, skrip menjalankan mode ekspor
    PDF. Direktori induk dibuat bila belum ada.

.PARAMETER Visible
    Tampilkan jendela Word untuk debugging. Default: Word berjalan tersembunyi.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/word.ps1 -DocxPath Laporan.docx

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/word.ps1 -DocxPath Laporan.docx -PdfPath Laporan.pdf

.NOTES
    Mengembalikan exit code 0 hanya bila Word melaporkan sukses, DOCX/PDF
    benar-benar terbentuk, dan ukurannya tidak nol. Kegagalan apa pun
    menghasilkan exit code 1.

    Referensi: https://learn.microsoft.com/en-us/office/vba/api/overview/word
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$DocxPath,

    [Parameter(Position = 1)]
    [string]$PdfPath,

    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ExitCode = 0
$word = $null
$doc = $null
$workDir = $null

$exportMode = -not [string]::IsNullOrWhiteSpace($PdfPath)

function Write-Log {
    param([string]$Message)
    Write-Host "[word] $Message"
}

function Write-ErrorMessage {
    param([string]$Message)
    [Console]::Error.WriteLine("[word] ERROR: $Message")
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

function Assert-NonEmptyFile {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not [System.IO.File]::Exists($Path)) {
        throw [System.IO.IOException]::new(
            "Word selesai tanpa error tetapi $Label tidak terbentuk: $Path"
        )
    }

    $info = [System.IO.FileInfo]::new($Path)
    if ($info.Length -le 0) {
        throw [System.IO.IOException]::new(
            "Word selesai tanpa error tetapi $Label kosong: $Path"
        )
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

    $fullDocx = $resolved.ProviderPath
    if (Test-Path -LiteralPath $fullDocx -PathType Container) {
        throw [System.ArgumentException]::new(
            "Path menunjuk ke direktori, bukan berkas DOCX: $fullDocx"
        )
    }

    if ([System.IO.Path]::GetExtension($fullDocx).ToLowerInvariant() -ne '.docx') {
        throw [System.ArgumentException]::new(
            "Path bukan berkas .docx: $fullDocx"
        )
    }

    $fullPdf = $null
    if ($exportMode) {
        $fullPdf = [System.IO.Path]::GetFullPath($PdfPath)
        if ([System.IO.Path]::GetExtension($fullPdf).ToLowerInvariant() -ne '.pdf') {
            throw [System.ArgumentException]::new(
                "Path tujuan bukan berkas .pdf: $fullPdf"
            )
        }

        $pdfDir = [System.IO.Path]::GetDirectoryName($fullPdf)
        if (-not [System.IO.Directory]::Exists($pdfDir)) {
            [void][System.IO.Directory]::CreateDirectory($pdfDir)
        }

        # Jangan biarkan PDF lama bertahan bila ekspor gagal di tengah jalan.
        if ([System.IO.File]::Exists($fullPdf)) {
            [System.IO.File]::Delete($fullPdf)
        }
    }

    # --- Tentukan dokumen yang dibuka -------------------------------------
    # Mode ekspor memakai snapshot agar DOCX sumber tidak pernah disimpan
    # ulang oleh Word dan tidak meninggalkan owner file di direktori proyek.
    $pathToOpen = $fullDocx
    if ($exportMode) {
        $workDir = Join-Path ([System.IO.Path]::GetTempPath()) (
            "docgen-word-" + [guid]::NewGuid().ToString("N")
        )
        $pathToOpen = Join-Path $workDir "source.docx"
        try {
            [void][System.IO.Directory]::CreateDirectory($workDir)
            [System.IO.File]::Copy($fullDocx, $pathToOpen, $true)
            [System.IO.File]::SetAttributes(
                $pathToOpen,
                [System.IO.FileAttributes]::Archive
            )
        }
        catch {
            throw [System.IO.IOException]::new(
                "Gagal membuat salinan kerja DOCX: $fullDocx. " +
                "Detail: " + $_.Exception.Message
            )
        }
    }

    # --- Buka Microsoft Word lewat COM ------------------------------------
    try {
        $word = New-Object -ComObject Word.Application
    }
    catch {
        throw [System.InvalidOperationException]::new(
            "Microsoft Word tidak terpasang atau COM Word tidak tersedia. " +
            "Aksi ini membutuhkan Microsoft Word desktop di Windows. " +
            "Detail: " + $_.Exception.Message
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
        $doc = $word.Documents.Open($pathToOpen, $false, $false, $false)
    }
    catch {
        throw [System.InvalidOperationException]::new(
            "Gagal membuka dokumen di Word: $pathToOpen. " +
            "Pastikan berkas dan direktori sementara dapat dibaca. " +
            "Detail: " + $_.Exception.Message
        )
    }

    Write-Log "Word $($word.Version) membuka: $pathToOpen"

    if ($doc.ReadOnly) {
        throw [System.InvalidOperationException]::new(
            "Dokumen terbuka dalam mode read-only: $pathToOpen. " +
            "Periksa atribut atau izin berkas, lalu coba lagi."
        )
    }

    # --- Perbarui field dan daftar isi ------------------------------------
    # Repaginate dulu agar Word menghitung ulang nomor halaman sebelum
    # PAGEREF/TOC diperbarui.
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

    # Pastikan layout final sudah stabil sebelum disimpan/diekspor.
    [void]$doc.Repaginate()

    Write-Log "Field diperbarui: $fieldCount; daftar isi diperbarui: $tocCount"

    if ($exportMode) {
        # --- Ekspor ke PDF -------------------------------------------------
        # wdExportFormatPDF = 17.
        Write-Log "Mengekspor PDF: $fullPdf"
        try {
            $doc.ExportAsFixedFormat($fullPdf, 17)
        }
        catch {
            throw [System.IO.IOException]::new(
                "Gagal mengekspor PDF: $fullPdf. " +
                "Pastikan berkas tujuan tidak sedang dibuka aplikasi lain. " +
                "Detail: " + $_.Exception.Message
            )
        }
        Assert-NonEmptyFile -Path $fullPdf -Label "PDF"
        Write-Log "PDF diekspor: $fullPdf"
    }
    else {
        # --- Simpan DOCX ---------------------------------------------------
        try {
            [void]$doc.Save()
        }
        catch {
            throw [System.IO.IOException]::new(
                "Gagal menyimpan dokumen: $fullDocx. " +
                "Pastikan berkas tidak sedang dibuka di Word dan tidak " +
                "read-only. Detail: " + $_.Exception.Message
            )
        }
        Assert-NonEmptyFile -Path $fullDocx -Label "DOCX"
        Write-Log "DOCX disimpan: $fullDocx"
    }

    $script:ExitCode = 0
}
catch {
    Write-ErrorMessage $_.Exception.Message
    $script:ExitCode = 1
}
finally {
    if ($null -ne $doc) {
        try {
            $doc.Close(0)   # wdDoNotSaveChanges; Save() sudah dilakukan bila perlu
        }
        catch {
            # Abaikan kegagalan penutupan; Word tetap akan di-Quit.
        }
        Release-ComObject $doc
        $doc = $null
    }

    if ($null -ne $word) {
        try {
            # Tanpa argumen: seluruh dokumen sudah ditutup.
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

    if ($null -ne $workDir -and [System.IO.Directory]::Exists($workDir)) {
        try {
            [System.IO.Directory]::Delete($workDir, $true)
        }
        catch {
            # Direktori sementara akan dibersihkan OS bila gagal dihapus.
        }
    }

    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

exit $script:ExitCode
