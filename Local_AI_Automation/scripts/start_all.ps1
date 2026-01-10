<#
.SYNOPSIS
    Start all Local AI Automation Hub services
.DESCRIPTION
    Starts n8n, backlog API, and verifies Ollama connectivity
#>

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$DOCKER_DIR = "$PROJECT_ROOT\docker"
$SCRIPTS_DIR = "$PROJECT_ROOT\scripts"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TR Local AI Automation Hub Startup   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Ollama
Write-Host "[1/4] Checking Ollama..." -ForegroundColor Yellow
try {
    $ollamaResponse = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
    $models = $ollamaResponse.models | Select-Object -ExpandProperty name
    Write-Host "  Ollama OK - Models: $($models -join ', ')" -ForegroundColor Green
} catch {
    Write-Host "  Ollama not running. Starting..." -ForegroundColor Yellow
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
}

# 2. Start Docker containers (n8n)
Write-Host "[2/4] Starting n8n..." -ForegroundColor Yellow
Push-Location $DOCKER_DIR
try {
    $n8nRunning = docker ps --filter "name=n8n" --format "{{.Names}}" 2>$null
    if ($n8nRunning -eq "n8n") {
        Write-Host "  n8n already running" -ForegroundColor Green
    } else {
        docker compose up -d 2>&1 | Out-Null
        Write-Host "  n8n started" -ForegroundColor Green
    }
} finally {
    Pop-Location
}

# 3. Initialize database if needed
Write-Host "[3/4] Checking backlog database..." -ForegroundColor Yellow
$dbPath = "$PROJECT_ROOT\data\backlog\backlog.db"
if (-not (Test-Path $dbPath)) {
    Write-Host "  Initializing database..." -ForegroundColor Yellow
    python "$SCRIPTS_DIR\init_database.py" --with-samples 2>&1 | Out-Null
    Write-Host "  Database initialized with sample data" -ForegroundColor Green
} else {
    Write-Host "  Database exists" -ForegroundColor Green
}

# 4. Start Backlog API
Write-Host "[4/4] Starting Backlog API..." -ForegroundColor Yellow
$backlogApiRunning = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*backlog_api*" }
if ($backlogApiRunning) {
    Write-Host "  Backlog API already running" -ForegroundColor Green
} else {
    Start-Process python -ArgumentList "$SCRIPTS_DIR\backlog_api.py" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Host "  Backlog API started on http://localhost:8765" -ForegroundColor Green
}

# Wait for services
Write-Host ""
Write-Host "Waiting for services to initialize..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# Health checks
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Service Status                       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$services = @(
    @{ Name = "Ollama"; Url = "http://localhost:11434/api/tags"; Port = 11434 },
    @{ Name = "n8n"; Url = "http://localhost:5678/healthz"; Port = 5678 },
    @{ Name = "Backlog API"; Url = "http://localhost:8765/health"; Port = 8765 }
)

foreach ($svc in $services) {
    try {
        $response = Invoke-RestMethod -Uri $svc.Url -TimeoutSec 3 -ErrorAction Stop
        Write-Host "  [OK] $($svc.Name) - http://localhost:$($svc.Port)" -ForegroundColor Green
    } catch {
        Write-Host "  [--] $($svc.Name) - Not responding" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Access URLs                          " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  n8n:         http://localhost:5678" -ForegroundColor White
Write-Host "  Backlog API: http://localhost:8765" -ForegroundColor White
Write-Host "  Ollama:      http://localhost:11434" -ForegroundColor White
Write-Host ""

# Get n8n credentials
$envFile = "$DOCKER_DIR\.env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    if ($envContent -match "N8N_USER=(.+)") { $n8nUser = $Matches[1].Trim() }
    if ($envContent -match "N8N_PASSWORD=(.+)") { $n8nPass = $Matches[1].Trim() }

    Write-Host "n8n Credentials:" -ForegroundColor Gray
    Write-Host "  Username: $n8nUser" -ForegroundColor Gray
    Write-Host "  Password: $n8nPass" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Ready! Import workflows from: $PROJECT_ROOT\workflows\" -ForegroundColor Green
