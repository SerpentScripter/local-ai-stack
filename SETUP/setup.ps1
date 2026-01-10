#Requires -Version 5.1
<#
.SYNOPSIS
    Master installer for local AI stack on Windows.
.DESCRIPTION
    Installs Docker Desktop, Ollama, Git, Python 3.11, Tesseract, Poppler, QPDF.
    Configures environment variables, pulls Ollama models, starts Docker services.
.NOTES
    Run this script - it will self-elevate if needed.
#>

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# === CONFIGURATION ===
$AI_MODELS_ROOT = "D:\SHARED\AI_Models"
$LOGS_DIR = "$AI_MODELS_ROOT\LOGS"
$SETUP_DIR = "$AI_MODELS_ROOT\SETUP"
$TOOLS_DIR = "$AI_MODELS_ROOT\TOOLS"
$VENVS_DIR = "$AI_MODELS_ROOT\venvs"

$OLLAMA_MODELS = @(
    "deepseek-r1:32b",
    "qwen3-coder:30b",
    "qwen2.5:14b",
    "qwen2.5vl:7b",
    "bge-m3:latest"
)

# === START LOGGING ===
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "$LOGS_DIR\setup_$timestamp.log"
New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null
Start-Transcript -Path $logFile -Append

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Stack Setup - Starting" -ForegroundColor Cyan
Write-Host "  Log: $logFile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# === CHECK AND SELF-ELEVATE ===
function Test-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "[!] Not running as Administrator. Attempting self-elevation..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    if (-not $scriptPath) { $scriptPath = $PSCommandPath }
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    Stop-Transcript
    exit
}

Write-Host "[OK] Running as Administrator" -ForegroundColor Green

# === HELPER FUNCTIONS ===
function Install-WingetPackage {
    param(
        [string]$PackageId,
        [string]$Name
    )
    Write-Host "[*] Installing $Name ($PackageId)..." -ForegroundColor Yellow
    try {
        $installed = winget list --id $PackageId 2>$null | Select-String $PackageId
        if ($installed) {
            Write-Host "    [SKIP] $Name already installed" -ForegroundColor Gray
            return $true
        }
        winget install --id $PackageId --accept-source-agreements --accept-package-agreements --silent --disable-interactivity
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] $Name installed successfully" -ForegroundColor Green
            return $true
        } else {
            Write-Host "    [WARN] $Name install returned code $LASTEXITCODE" -ForegroundColor Yellow
            return $false
        }
    } catch {
        Write-Host "    [ERROR] Failed to install $Name : $_" -ForegroundColor Red
        return $false
    }
}

function Set-EnvVar {
    param(
        [string]$Name,
        [string]$Value,
        [string]$Target = "Machine"
    )
    try {
        [Environment]::SetEnvironmentVariable($Name, $Value, $Target)
        # Also set in current session
        Set-Item -Path "Env:\$Name" -Value $Value -ErrorAction SilentlyContinue
        Write-Host "    [OK] Set $Name = $Value ($Target)" -ForegroundColor Green
    } catch {
        Write-Host "    [ERROR] Failed to set $Name : $_" -ForegroundColor Red
    }
}

function Wait-ForUrl {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 120,
        [int]$IntervalSeconds = 5
    )
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
            # Keep trying
        }
        Start-Sleep -Seconds $IntervalSeconds
        $elapsed += $IntervalSeconds
        Write-Host "    Waiting for $Url... ($elapsed s)" -ForegroundColor Gray
    }
    return $false
}

# === STEP 1: CREATE FOLDERS ===
Write-Host "`n[STEP 1] Creating folder structure..." -ForegroundColor Cyan
$folders = @(
    "$AI_MODELS_ROOT\ollama\models",
    "$AI_MODELS_ROOT\openwebui\data",
    "$AI_MODELS_ROOT\langflow\data",
    "$AI_MODELS_ROOT\langflow\postgres",
    "$SETUP_DIR",
    "$TOOLS_DIR",
    "$LOGS_DIR",
    "$VENVS_DIR",
    "$AI_MODELS_ROOT\cache",
    "$AI_MODELS_ROOT\hf",
    "$AI_MODELS_ROOT\torch",
    "$AI_MODELS_ROOT\pip_cache"
)
foreach ($folder in $folders) {
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
}
Write-Host "[OK] Folders created" -ForegroundColor Green

# === STEP 2: INSTALL PREREQUISITES ===
Write-Host "`n[STEP 2] Installing prerequisites via winget..." -ForegroundColor Cyan

$packages = @(
    @{Id = "Docker.DockerDesktop"; Name = "Docker Desktop"},
    @{Id = "Ollama.Ollama"; Name = "Ollama"},
    @{Id = "Git.Git"; Name = "Git"},
    @{Id = "Python.Python.3.11"; Name = "Python 3.11"},
    @{Id = "UB-Mannheim.TesseractOCR"; Name = "Tesseract OCR"},
    @{Id = "oschwartz10612.Poppler"; Name = "Poppler"},
    @{Id = "QPDF.QPDF"; Name = "QPDF"}
)

$installResults = @{}
foreach ($pkg in $packages) {
    $result = Install-WingetPackage -PackageId $pkg.Id -Name $pkg.Name
    $installResults[$pkg.Name] = $result
}

# Refresh PATH for current session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# === STEP 3: SET ENVIRONMENT VARIABLES ===
Write-Host "`n[STEP 3] Setting environment variables..." -ForegroundColor Cyan
Set-EnvVar -Name "TR_AI_MODELS_DIR" -Value $AI_MODELS_ROOT
Set-EnvVar -Name "OLLAMA_MODELS" -Value "$AI_MODELS_ROOT\ollama\models"
Set-EnvVar -Name "HF_HOME" -Value "$AI_MODELS_ROOT\hf"
Set-EnvVar -Name "TRANSFORMERS_CACHE" -Value "$AI_MODELS_ROOT\hf\transformers"
Set-EnvVar -Name "TORCH_HOME" -Value "$AI_MODELS_ROOT\torch"
Set-EnvVar -Name "PIP_CACHE_DIR" -Value "$AI_MODELS_ROOT\pip_cache"

# Also set for User scope
Set-EnvVar -Name "TR_AI_MODELS_DIR" -Value $AI_MODELS_ROOT -Target "User"
Set-EnvVar -Name "OLLAMA_MODELS" -Value "$AI_MODELS_ROOT\ollama\models" -Target "User"
Set-EnvVar -Name "HF_HOME" -Value "$AI_MODELS_ROOT\hf" -Target "User"
Set-EnvVar -Name "TRANSFORMERS_CACHE" -Value "$AI_MODELS_ROOT\hf\transformers" -Target "User"
Set-EnvVar -Name "TORCH_HOME" -Value "$AI_MODELS_ROOT\torch" -Target "User"
Set-EnvVar -Name "PIP_CACHE_DIR" -Value "$AI_MODELS_ROOT\pip_cache" -Target "User"

Write-Host "[OK] Environment variables set" -ForegroundColor Green

# === STEP 4: ENSURE OLLAMA IS RUNNING ===
Write-Host "`n[STEP 4] Ensuring Ollama is running..." -ForegroundColor Cyan

# Set OLLAMA_MODELS in current session
$env:OLLAMA_MODELS = "$AI_MODELS_ROOT\ollama\models"

# Check if Ollama is already running
$ollamaRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        $ollamaRunning = $true
        Write-Host "    [OK] Ollama already running" -ForegroundColor Green
    }
} catch {
    Write-Host "    [*] Ollama not responding, attempting to start..." -ForegroundColor Yellow
}

if (-not $ollamaRunning) {
    # Find and start Ollama
    $ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaPath) {
        $ollamaPath = "C:\Program Files\Ollama\ollama.exe"
        if (-not (Test-Path $ollamaPath)) {
            $ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
        }
    } else {
        $ollamaPath = $ollamaPath.Source
    }

    if (Test-Path $ollamaPath) {
        Write-Host "    [*] Starting Ollama from: $ollamaPath" -ForegroundColor Yellow
        Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 5

        if (Wait-ForUrl -Url "http://localhost:11434" -TimeoutSeconds 60) {
            Write-Host "    [OK] Ollama started successfully" -ForegroundColor Green
            $ollamaRunning = $true
        } else {
            Write-Host "    [ERROR] Ollama failed to start within timeout" -ForegroundColor Red
        }
    } else {
        Write-Host "    [ERROR] Ollama executable not found" -ForegroundColor Red
    }
}

# === STEP 5: PULL OLLAMA MODELS ===
Write-Host "`n[STEP 5] Pulling Ollama models..." -ForegroundColor Cyan

if ($ollamaRunning) {
    foreach ($model in $OLLAMA_MODELS) {
        Write-Host "    [*] Pulling $model (this may take a while)..." -ForegroundColor Yellow
        try {
            & ollama pull $model 2>&1 | ForEach-Object { Write-Host "      $_" }
            if ($LASTEXITCODE -eq 0) {
                Write-Host "    [OK] $model pulled successfully" -ForegroundColor Green
            } else {
                Write-Host "    [WARN] $model pull returned code $LASTEXITCODE" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "    [ERROR] Failed to pull $model : $_" -ForegroundColor Red
        }
    }

    Write-Host "`n    [*] Listing installed models:" -ForegroundColor Yellow
    & ollama list
} else {
    Write-Host "    [SKIP] Ollama not running, skipping model pulls" -ForegroundColor Yellow
}

# === STEP 6: WRITE DOCKER-COMPOSE ===
Write-Host "`n[STEP 6] Writing docker-compose.yml..." -ForegroundColor Cyan

$dockerCompose = @"
version: '3.8'

services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:8080"
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - WEBUI_AUTH=false
    volumes:
      - D:/SHARED/AI_Models/openwebui/data:/app/backend/data
    extra_hosts:
      - "host.docker.internal:host-gateway"

  langflow:
    image: langflowai/langflow:latest
    container_name: langflow
    restart: unless-stopped
    ports:
      - "127.0.0.1:7860:7860"
    environment:
      - LANGFLOW_DATABASE_URL=postgresql://langflow:langflow@langflow-db:5432/langflow
      - LANGFLOW_CONFIG_DIR=/app/langflow
    volumes:
      - D:/SHARED/AI_Models/langflow/data:/app/langflow
    depends_on:
      - langflow-db

  langflow-db:
    image: postgres:15-alpine
    container_name: langflow-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=langflow
      - POSTGRES_PASSWORD=langflow
      - POSTGRES_DB=langflow
    volumes:
      - D:/SHARED/AI_Models/langflow/postgres:/var/lib/postgresql/data
"@

$dockerComposePath = "$SETUP_DIR\docker-compose.yml"
$dockerCompose | Out-File -FilePath $dockerComposePath -Encoding utf8 -Force
Write-Host "[OK] docker-compose.yml written to $dockerComposePath" -ForegroundColor Green

# === STEP 7: START DOCKER SERVICES ===
Write-Host "`n[STEP 7] Starting Docker services..." -ForegroundColor Cyan

# Check if Docker is running
$dockerRunning = $false
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
        Write-Host "    [OK] Docker is running" -ForegroundColor Green
    }
} catch {
    Write-Host "    [*] Docker not responding" -ForegroundColor Yellow
}

if (-not $dockerRunning) {
    Write-Host "    [*] Attempting to start Docker Desktop..." -ForegroundColor Yellow
    $dockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktopPath) {
        Start-Process -FilePath $dockerDesktopPath
        Write-Host "    [*] Waiting for Docker to start (up to 120s)..." -ForegroundColor Yellow
        $waited = 0
        while ($waited -lt 120) {
            Start-Sleep -Seconds 10
            $waited += 10
            try {
                $dockerInfo = docker info 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $dockerRunning = $true
                    Write-Host "    [OK] Docker started after ${waited}s" -ForegroundColor Green
                    break
                }
            } catch {}
            Write-Host "      Still waiting... (${waited}s)" -ForegroundColor Gray
        }
    } else {
        Write-Host "    [ERROR] Docker Desktop not found at expected path" -ForegroundColor Red
    }
}

if ($dockerRunning) {
    Push-Location $SETUP_DIR
    try {
        Write-Host "    [*] Running docker compose up -d..." -ForegroundColor Yellow
        docker compose up -d 2>&1 | ForEach-Object { Write-Host "      $_" }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [OK] Docker services started" -ForegroundColor Green
        } else {
            Write-Host "    [WARN] docker compose returned code $LASTEXITCODE" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "    [ERROR] Failed to start Docker services: $_" -ForegroundColor Red
    }
    Pop-Location
} else {
    Write-Host "    [SKIP] Docker not running, skipping service startup" -ForegroundColor Yellow
}

# === STEP 8: CREATE PYTHON VENV FOR DOC-TOOLS ===
Write-Host "`n[STEP 8] Creating Python venv for doc-tools..." -ForegroundColor Cyan

$venvPath = "$VENVS_DIR\doc-tools"
$pythonExe = Get-Command python -ErrorAction SilentlyContinue

if ($pythonExe) {
    try {
        Write-Host "    [*] Creating venv at $venvPath..." -ForegroundColor Yellow
        & python -m venv $venvPath

        $venvPip = "$venvPath\Scripts\pip.exe"
        $venvPython = "$venvPath\Scripts\python.exe"

        if (Test-Path $venvPip) {
            Write-Host "    [*] Upgrading pip, wheel, setuptools..." -ForegroundColor Yellow
            & $venvPip install -U pip wheel setuptools 2>&1 | Select-Object -Last 3

            Write-Host "    [*] Installing marker-pdf, pytesseract, pillow..." -ForegroundColor Yellow
            & $venvPip install marker-pdf pytesseract pillow 2>&1 | Select-Object -Last 5

            Write-Host "    [*] Attempting to install mineru[all] (may fail, that's OK)..." -ForegroundColor Yellow
            & $venvPip install "mineru[all]" 2>&1 | Select-Object -Last 5

            Write-Host "    [OK] Doc-tools venv created" -ForegroundColor Green
        } else {
            Write-Host "    [ERROR] Venv pip not found" -ForegroundColor Red
        }
    } catch {
        Write-Host "    [ERROR] Failed to create venv: $_" -ForegroundColor Red
    }
} else {
    Write-Host "    [ERROR] Python not found in PATH" -ForegroundColor Red
}

# === STEP 9: DOWNLOAD SWEDISH TESSDATA ===
Write-Host "`n[STEP 9] Checking Swedish tessdata..." -ForegroundColor Cyan

$tessdataPath = "C:\Program Files\Tesseract-OCR\tessdata"
if (-not (Test-Path $tessdataPath)) {
    $tessdataPath = "$env:LOCALAPPDATA\Tesseract-OCR\tessdata"
}

if (Test-Path $tessdataPath) {
    $sweFile = "$tessdataPath\swe.traineddata"
    if (Test-Path $sweFile) {
        Write-Host "    [SKIP] Swedish tessdata already exists" -ForegroundColor Gray
    } else {
        Write-Host "    [*] Downloading Swedish tessdata..." -ForegroundColor Yellow
        try {
            $sweUrl = "https://github.com/tesseract-ocr/tessdata/raw/main/swe.traineddata"
            Invoke-WebRequest -Uri $sweUrl -OutFile $sweFile -UseBasicParsing
            Write-Host "    [OK] Swedish tessdata downloaded" -ForegroundColor Green
        } catch {
            Write-Host "    [ERROR] Failed to download Swedish tessdata: $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "    [WARN] Tessdata directory not found, skipping Swedish download" -ForegroundColor Yellow
}

# === STEP 10: CREATE HELPER SCRIPTS ===
Write-Host "`n[STEP 10] Creating helper scripts in TOOLS..." -ForegroundColor Cyan

# ocr_image_to_text.ps1
$ocrScript = @'
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
'@
$ocrScript | Out-File -FilePath "$TOOLS_DIR\ocr_image_to_text.ps1" -Encoding utf8 -Force

# pdf_to_text.ps1
$pdfToTextScript = @'
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
'@
$pdfToTextScript | Out-File -FilePath "$TOOLS_DIR\pdf_to_text.ps1" -Encoding utf8 -Force

# pdf_sanitize.ps1
$pdfSanitizeScript = @'
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
'@
$pdfSanitizeScript | Out-File -FilePath "$TOOLS_DIR\pdf_sanitize.ps1" -Encoding utf8 -Force

# pdf_to_md_marker.ps1
$markerScript = @'
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
'@
$markerScript | Out-File -FilePath "$TOOLS_DIR\pdf_to_md_marker.ps1" -Encoding utf8 -Force

# pdf_to_md_mineru.ps1
$mineruScript = @'
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
'@
$mineruScript | Out-File -FilePath "$TOOLS_DIR\pdf_to_md_mineru.ps1" -Encoding utf8 -Force

Write-Host "[OK] Helper scripts created in $TOOLS_DIR" -ForegroundColor Green

# === STEP 11: WRITE README ===
Write-Host "`n[STEP 11] Writing README.md..." -ForegroundColor Cyan

$readme = @"
# Local AI Stack - README

## Overview
This is a fully offline-capable local AI stack installed on Windows.

## Ports & Services

| Service      | URL                          | Description                    |
|--------------|------------------------------|--------------------------------|
| Ollama       | http://localhost:11434       | Local LLM API                  |
| Open WebUI   | http://localhost:3000        | ChatGPT-like web interface     |
| Langflow     | http://localhost:7860        | Visual workflow builder        |

## Model Storage
All models and data are stored under: ``D:\SHARED\AI_Models\``

- Ollama models: ``D:\SHARED\AI_Models\ollama\models``
- HuggingFace cache: ``D:\SHARED\AI_Models\hf``
- Torch cache: ``D:\SHARED\AI_Models\torch``
- Open WebUI data: ``D:\SHARED\AI_Models\openwebui\data``
- Langflow data: ``D:\SHARED\AI_Models\langflow\data``

## Start/Stop Commands

### Start Docker Services
``````powershell
cd D:\SHARED\AI_Models\SETUP
docker compose up -d
``````

### Stop Docker Services
``````powershell
cd D:\SHARED\AI_Models\SETUP
docker compose down
``````

### Start Ollama (if not running)
``````powershell
ollama serve
``````

### Pull a new model
``````powershell
ollama pull <model-name>
``````

### List installed models
``````powershell
ollama list
``````

## Installed Ollama Models
- deepseek-r1:32b
- qwen3-coder:30b
- qwen2.5:14b
- qwen2.5vl:7b
- bge-m3:latest

## Verification Checklist

1. **Ollama running?**
   ``````powershell
   curl http://localhost:11434
   # Should return "Ollama is running"
   ``````

2. **Models installed?**
   ``````powershell
   ollama list
   ``````

3. **Open WebUI accessible?**
   Open http://localhost:3000 in browser

4. **Langflow accessible?**
   Open http://localhost:7860 in browser

5. **Docker containers running?**
   ``````powershell
   docker ps
   ``````

## TOOLS Directory
Helper scripts are in ``D:\SHARED\AI_Models\TOOLS\``:

- ``ocr_image_to_text.ps1`` - OCR images with Tesseract
- ``pdf_to_text.ps1`` - Extract text from PDFs with Poppler
- ``pdf_sanitize.ps1`` - Repair/linearize PDFs with QPDF
- ``pdf_to_md_marker.ps1`` - Convert PDF to Markdown with Marker
- ``pdf_to_md_mineru.ps1`` - Convert PDF to Markdown/JSON with MinerU

## Environment Variables
These are set system-wide:
- ``TR_AI_MODELS_DIR`` = D:\SHARED\AI_Models
- ``OLLAMA_MODELS`` = D:\SHARED\AI_Models\ollama\models
- ``HF_HOME`` = D:\SHARED\AI_Models\hf
- ``TRANSFORMERS_CACHE`` = D:\SHARED\AI_Models\hf\transformers
- ``TORCH_HOME`` = D:\SHARED\AI_Models\torch
- ``PIP_CACHE_DIR`` = D:\SHARED\AI_Models\pip_cache

## Logs
Setup logs are stored in: ``D:\SHARED\AI_Models\LOGS\``

## Troubleshooting

### Docker containers won't start
1. Ensure Docker Desktop is running
2. Check logs: ``docker compose logs``
3. Try restarting: ``docker compose down && docker compose up -d``

### Ollama models not pulling
1. Check disk space on D: drive
2. Ensure OLLAMA_MODELS env var is set
3. Try: ``ollama pull <model>`` manually

### Open WebUI can't connect to Ollama
1. Ensure Ollama is running: ``curl http://localhost:11434``
2. Restart Open WebUI container
"@

$readme | Out-File -FilePath "$SETUP_DIR\README.md" -Encoding utf8 -Force
Write-Host "[OK] README.md written" -ForegroundColor Green

# === SUMMARY ===
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  SETUP COMPLETE - SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nInstallation Results:" -ForegroundColor White
foreach ($pkg in $installResults.Keys) {
    if ($installResults[$pkg]) {
        Write-Host "  [OK] $pkg" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $pkg (may need manual check)" -ForegroundColor Yellow
    }
}

Write-Host "`nServices:" -ForegroundColor White
Write-Host "  Ollama: http://localhost:11434" -ForegroundColor Cyan
Write-Host "  Open WebUI: http://localhost:3000" -ForegroundColor Cyan
Write-Host "  Langflow: http://localhost:7860" -ForegroundColor Cyan

Write-Host "`nNext Steps:" -ForegroundColor White
Write-Host "  1. Open http://localhost:3000 for Open WebUI" -ForegroundColor White
Write-Host "  2. Open http://localhost:7860 for Langflow" -ForegroundColor White
Write-Host "  3. Run 'ollama list' to see installed models" -ForegroundColor White

Write-Host "`nLog file: $logFile" -ForegroundColor Gray

Stop-Transcript
Write-Host "`nSetup script finished. Press Enter to close..." -ForegroundColor Green
Read-Host
