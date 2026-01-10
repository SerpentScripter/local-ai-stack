<#
.SYNOPSIS
    Extract text from PDF using pdftotext (Poppler).
.PARAMETER PdfPath
    Path to the PDF file.
.EXAMPLE
    .\pdf_to_text.ps1 -PdfPath "C:\document.pdf"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$PdfPath
)

$pdftotext = Get-Command pdftotext -ErrorAction SilentlyContinue
if (-not $pdftotext) {
    # Try common install locations
    $popperPaths = @(
        "C:\Program Files\poppler\Library\bin\pdftotext.exe",
        "C:\poppler\Library\bin\pdftotext.exe",
        "$env:LOCALAPPDATA\poppler\Library\bin\pdftotext.exe"
    )
    foreach ($p in $popperPaths) {
        if (Test-Path $p) {
            $pdftotext = $p
            break
        }
    }
}

if (-not $pdftotext) {
    Write-Error "pdftotext not found. Please install oschwartz10612.Poppler via winget."
    exit 1
}

if (-not (Test-Path $PdfPath)) {
    Write-Error "PDF file not found: $PdfPath"
    exit 1
}

& $pdftotext -layout $PdfPath -
