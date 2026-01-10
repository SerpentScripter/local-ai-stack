<#
.SYNOPSIS
    Convert PDF to Markdown using Marker (if installed).
.PARAMETER PdfPath
    Path to the PDF file.
.PARAMETER OutputDir
    Output directory. Default: same as PDF.
.EXAMPLE
    .\pdf_to_md_marker.ps1 -PdfPath "C:\document.pdf"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$PdfPath,
    [string]$OutputDir
)

$venvPath = "D:\SHARED\AI_Models\venvs\doc-tools"
$markerExe = "$venvPath\Scripts\marker_single.exe"
$pythonExe = "$venvPath\Scripts\python.exe"

if (-not (Test-Path $PdfPath)) {
    Write-Error "PDF file not found: $PdfPath"
    exit 1
}

if (-not $OutputDir) {
    $OutputDir = [System.IO.Path]::GetDirectoryName($PdfPath)
}

if (Test-Path $markerExe) {
    & $markerExe $PdfPath $OutputDir
} elseif (Test-Path $pythonExe) {
    & $pythonExe -m marker_single $PdfPath $OutputDir 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Marker not installed or failed. Install with: $venvPath\Scripts\pip.exe install marker-pdf"
    }
} else {
    Write-Error "Marker not installed. The doc-tools venv does not exist at $venvPath"
    Write-Host "To install manually:"
    Write-Host "  python -m venv $venvPath"
    Write-Host "  $venvPath\Scripts\pip.exe install marker-pdf"
    exit 1
}
