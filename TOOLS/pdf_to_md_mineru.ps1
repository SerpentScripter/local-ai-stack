<#
.SYNOPSIS
    Convert PDF to Markdown/JSON using MinerU (if installed).
.PARAMETER PdfPath
    Path to the PDF file.
.PARAMETER OutputDir
    Output directory. Default: same as PDF.
.EXAMPLE
    .\pdf_to_md_mineru.ps1 -PdfPath "C:\document.pdf"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$PdfPath,
    [string]$OutputDir
)

$venvPath = "D:\SHARED\AI_Models\venvs\doc-tools"
$pythonExe = "$venvPath\Scripts\python.exe"

if (-not (Test-Path $PdfPath)) {
    Write-Error "PDF file not found: $PdfPath"
    exit 1
}

if (-not $OutputDir) {
    $OutputDir = [System.IO.Path]::GetDirectoryName($PdfPath)
}

if (Test-Path $pythonExe) {
    & $pythonExe -m mineru $PdfPath -o $OutputDir 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "MinerU not installed or failed. Install with: $venvPath\Scripts\pip.exe install 'mineru[all]'"
    }
} else {
    Write-Error "MinerU not installed. The doc-tools venv does not exist at $venvPath"
    Write-Host "To install manually:"
    Write-Host "  python -m venv $venvPath"
    Write-Host "  $venvPath\Scripts\pip.exe install 'mineru[all]'"
    exit 1
}
