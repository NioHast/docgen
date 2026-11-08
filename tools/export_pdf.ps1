<#
.SYNOPSIS
    Ekspor DOCX final menjadi PDF memakai Microsoft Word COM.

.DESCRIPTION
    Membuat snapshot sementara dari DOCX sumber, membukanya di Microsoft Word
    secara tersembunyi, memperbarui seluruh field (termasuk nomor halaman
    TOC/PAGEREF), memperbarui setiap TableOfContents, lalu mengekspor dokumen
    ke PDF dengan ExportAsFixedFormat. DOCX sumber tidak pernah dibuka atau
    disimpan; Word ditutup tanpa mengubah dokumen.

    Skrip ini ditujukan untuk Windows yang memiliki Microsoft Word desktop.
    Di Debian/Linux gunakan tools/export_pdf.py yang memanggil LibreOffice
    headless.

.PARAMETER DocxPath
    Path ke berkas .docx sumber. Path relatif diresolusikan terhadap direktori
    kerja saat skrip dijalankan.

.PARAMETER PdfPath
    Path tujuan PDF. Direktori induk dibuat bila belum ada. Berkas PDF lama
    pada path ini dihapus sebelum ekspor agar kegagalan tidak meninggalkan
    keluaran basi.

.PARAMETER Visible
    Tampilkan jendela Word. Berguna untuk men-debug proses ekspor.
    Default: Word berjalan tersembunyi.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/export_pdf.ps1 -DocxPath Laporan.docx -PdfPath Laporan.pdf

.NOTES
    Hanya tersedia di Windows dengan Microsoft Word terpasang. Langkah ini
    tidak dapat dijalankan di Linux/macOS/CI tanpa Word.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$DocxPath,

    [Parameter(Mandatory = $true, Position = 1)]
    [ValidateNotNullOrEmpty()]
    [string]$PdfPath,

    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ExitCode = 0
$word = $null
$doc = $null
$workDir = $null

function Write-Log {
    param([string]$Message)
    Write-Host "[export_pdf] $Message"
}

function Write-ErrorMessage {
    param([string]$Message)
    [Console]::Error.WriteLine("[export_pdf] ERROR: $Message")
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

    $fullDocx = $resolved.ProviderPath
    if (Test-Path -LiteralPath $fullDocx -PathType Container) {
        throw [System.ArgumentException]::new(
            "Path menunjuk ke direktori, bukan berkas DOCX: $fullDocx"
        )
    }

    if ([System.IO.Path]::GetExtension($fullDocx) -ne '.docx') {
        throw [System.ArgumentException]::new(
            "Path bukan berkas .docx: $fullDocx"
        )
    }

    $fullPdf = [System.IO.Path]::GetFullPath($PdfPath)
    if ([System.IO.Path]::GetExtension($fullPdf) -ne '.pdf') {
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

    # --- Siapkan salinan kerja --------------------------------------------
    # Word membuka snapshot sementara, bukan DOCX sumber. Ini mencegah Word
    # membuat owner file (~$...) di direktori proyek, menghindari lock bila
    # DOCX sedang dibuka aplikasi lain, dan memastikan DOCX sumber tidak
    # pernah ditulis ulang. Field/TOC tetap dihitung dari isi snapshot yang
    # identik dengan DOCX final.
    $workDir = Join-Path ([System.IO.Path]::GetTempPath()) (
        "laporan-pdf-" + [guid]::NewGuid().ToString("N")
    )
    $snapshot = Join-Path $workDir "source.docx"
    try {
        [void][System.IO.Directory]::CreateDirectory($workDir)
        [System.IO.File]::Copy($fullDocx, $snapshot, $true)
        # Salinan kerja harus dapat ditulis agar Word dapat memperbarui field
        # di memori meskipun DOCX sumber bersifat read-only.
        [System.IO.File]::SetAttributes(
            $snapshot,
            [System.IO.FileAttributes]::Archive
        )
    }
    catch {
        throw [System.IO.IOException]::new(
            "Gagal membuat salinan kerja DOCX: $fullDocx. " +
            "Detail: " + $_.Exception.Message
        )
    }

    # --- Buka Microsoft Word lewat COM ------------------------------------
    try {
        $word = New-Object -ComObject Word.Application
    }
    catch {
        throw [System.InvalidOperationException]::new(
            "Microsoft Word tidak terpasang atau COM Word tidak tersedia. " +
            "Ekspor PDF di Windows membutuhkan Microsoft Word desktop. " +
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
        $doc = $word.Documents.Open($snapshot, $false, $false, $false)
    }
    catch {
        throw [System.InvalidOperationException]::new(
            "Gagal membuka salinan DOCX di Word: $snapshot. " +
            "Pastikan berkas sumber dan direktori sementara dapat dibaca. " +
            "Detail: " + $_.Exception.Message
        )
    }

    Write-Log "Word $($word.Version) membuka: $fullDocx (snapshot)"

    if ($doc.ReadOnly) {
        throw [System.InvalidOperationException]::new(
            "Snapshot DOCX terbuka dalam mode read-only: $snapshot. " +
            "Periksa atribut atau izin direktori sementara, lalu coba lagi."
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

    # Pastikan layout final sudah stabil sebelum diekspor.
    [void]$doc.Repaginate()

    Write-Log "Field diperbarui: $fieldCount; daftar isi diperbarui: $tocCount"

    # --- Ekspor ke PDF -----------------------------------------------------
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
    Write-Log "ExportAsFixedFormat selesai."

    if (-not [System.IO.File]::Exists($fullPdf)) {
        throw [System.IO.IOException]::new(
            "Word selesai tanpa error tetapi PDF tidak terbentuk: $fullPdf"
        )
    }

    Write-Log "PDF diekspor: $fullPdf"
    $script:ExitCode = 0
}
catch {
    Write-ErrorMessage $_.Exception.Message
    $script:ExitCode = 1
}
finally {
    if ($null -ne $doc) {
        try {
            $doc.Close(0)   # wdDoNotSaveChanges; DOCX sumber tidak diubah
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
