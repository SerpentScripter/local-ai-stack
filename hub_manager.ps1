<#
.SYNOPSIS
    Unified Hub Manager for Local AI Stack
.DESCRIPTION
    Manages all services: Ollama, Docker stacks, and Backlog API.
    Respects port configuration in root .env file.
#>

# --- Command Parser ---
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "status", "restart")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Continue"
$PROJECT_ROOT = $PSScriptRoot
$ENV_FILE = "$PROJECT_ROOT\.env"

# --- Load Environment Variables ---
function Load-Env {
    if (Test-Path $ENV_FILE) {
        Get-Content $ENV_FILE | ForEach-Object {
            if ($_ -match "^(?<name>[^#\s=]+)=(?<value>.*)$") {
                $name = $Matches['name'].Trim()
                $value = $Matches['value'].Trim().Trim('"').Trim("'")
                [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
                Set-Item -Path "Env:\$name" -Value $value
            }
        }
    }
}

Load-Env

# Defaults
$OLLAMA_PORT = if ($env:OLLAMA_PORT) { $env:OLLAMA_PORT } else { "11434" }
$N8N_PORT = if ($env:N8N_PORT) { $env:N8N_PORT } else { "5678" }
$OPEN_WEBUI_PORT = if ($env:OPEN_WEBUI_PORT) { $env:OPEN_WEBUI_PORT } else { "3000" }
$LANGFLOW_PORT = if ($env:LANGFLOW_PORT) { $env:LANGFLOW_PORT } else { "7860" }
$BACKLOG_API_PORT = if ($env:BACKLOG_API_PORT) { $env:BACKLOG_API_PORT } else { "8765" }

function Show-Status {
    Write-Host "`n--- System Status ---" -ForegroundColor Cyan
    python "$PROJECT_ROOT\service_status.py"
}

function Start-Services {
    Write-Host "`n--- Starting Local AI Stack ---" -ForegroundColor Cyan
    
    # 1. Ollama
    $ollamaRunning = (Get-Process ollama -ErrorAction SilentlyContinue)
    if (-not $ollamaRunning) {
        Write-Host "[*] Starting Ollama..." -ForegroundColor Yellow
        Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
    else {
        Write-Host "[OK] Ollama is already running" -ForegroundColor Green
    }

    # 2. Docker: Hub Services (Open WebUI, Langflow)
    Write-Host "[*] Starting Hub Docker services..." -ForegroundColor Yellow
    Push-Location "$PROJECT_ROOT\SETUP"
    docker compose up -d
    Pop-Location

    # 3. Docker: Automation Services (n8n)
    Write-Host "[*] Starting Automation Docker services..." -ForegroundColor Yellow
    Push-Location "$PROJECT_ROOT\Local_AI_Automation\docker"
    docker compose up -d
    Pop-Location

    # 4. Backlog API
    $apiRunning = (Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*backlog_api*" })
    if (-not $apiRunning) {
        Write-Host "[*] Starting Backlog API..." -ForegroundColor Yellow
        Start-Process python -ArgumentList "$PROJECT_ROOT\Local_AI_Automation\scripts\backlog_api.py" -WindowStyle Hidden
    }
    else {
        Write-Host "[OK] Backlog API is already running" -ForegroundColor Green
    }

    Write-Host "`n[OK] All services initiated." -ForegroundColor Green
    Show-Status
}

function Stop-Services {
    Write-Host "`n--- Stopping Local AI Stack ---" -ForegroundColor Cyan
    
    # 1. Backlog API
    Write-Host "[*] Stopping Backlog API..." -ForegroundColor Yellow
    $apiProcesses = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*backlog_api*" }
    foreach ($p in $apiProcesses) { Stop-Process $p.Id -Force }

    # 2. Docker: Automation Services
    Write-Host "[*] Stopping Automation Docker services..." -ForegroundColor Yellow
    Push-Location "$PROJECT_ROOT\Local_AI_Automation\docker"
    docker compose down
    Pop-Location

    # 3. Docker: Hub Services
    Write-Host "[*] Stopping Hub Docker services..." -ForegroundColor Yellow
    Push-Location "$PROJECT_ROOT\SETUP"
    docker compose down
    Pop-Location

    Write-Host "[OK] Stack stopped." -ForegroundColor Green
}

switch ($Action) {
    "start" { Start-Services }
    "stop" { Stop-Services }
    "status" { Show-Status }
    "restart" { Stop-Services; Start-Sleep -Seconds 2; Start-Services }
}
