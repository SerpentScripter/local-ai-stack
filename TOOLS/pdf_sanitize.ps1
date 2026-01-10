<#
.SYNOPSIS
    Sanitize/repair PDF using QPDF.
.PARAMETER PdfPath
    Path to the input PDF file.
.PARAMETER OutputPath
    Path for the output PDF. Default: adds _sanitized suffix.
.EXAMPLE
    .\pdf_sanitize.ps1 -PdfPath "C:\document.pdf"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$PdfPath,
    [string]$OutputPath
)

$qpdf = Get-Command qpdf -ErrorAction SilentlyContinue
if (-not $qpdf) {
    Write-Error "qpdf not found. Please install QPDF.QPDF via winget."
    exit 1
}

if (-not (Test-Path $PdfPath)) {
    Write-Error "PDF file not found: $PdfPath"
    exit 1
}

if (-not $OutputPath) {
    $dir = [System.IO.Path]::GetDirectoryName($PdfPath)
    $name = [System.IO.Path]::GetFileNameWithoutExtension($PdfPath)
    $OutputPath = Join-Path $dir "$($name)_sanitized.pdf"
}

& qpdf --linearize --replace-input $PdfPath 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "PDF sanitized successfully: $PdfPath"
} else {
    # Try without replace-input
    & qpdf --linearize $PdfPath $OutputPath 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "PDF sanitized to: $OutputPath"
    } else {
        Write-Error "Failed to sanitize PDF"
    }
}
