<#
.SYNOPSIS
    OCR an image file to text using Tesseract.
.PARAMETER ImagePath
    Path to the image file.
.PARAMETER Lang
    Language(s) for OCR. Default: eng+swe
.EXAMPLE
    .\ocr_image_to_text.ps1 -ImagePath "C:\image.png"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$ImagePath,
    [string]$Lang = "eng+swe"
)

$tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseract) {
    $tesseract = "C:\Program Files\Tesseract-OCR\tesseract.exe"
    if (-not (Test-Path $tesseract)) {
        Write-Error "Tesseract not found. Please install UB-Mannheim.TesseractOCR via winget."
        exit 1
    }
}

if (-not (Test-Path $ImagePath)) {
    Write-Error "Image file not found: $ImagePath"
    exit 1
}

$outputBase = [System.IO.Path]::GetTempFileName()
& $tesseract $ImagePath $outputBase -l $Lang 2>$null
$outputFile = "$outputBase.txt"

if (Test-Path $outputFile) {
    Get-Content $outputFile
    Remove-Item $outputFile -Force
}
Remove-Item $outputBase -Force -ErrorAction SilentlyContinue
