<#
.SYNOPSIS
    Stop all Local AI Automation Hub services
#>

$ErrorActionPreference = "Continue"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$DOCKER_DIR = "$PROJECT_ROOT\docker"

Write-Host "Stopping Local AI Automation Hub..." -ForegroundColor Cyan

# Stop Backlog API
$backlogProc = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*backlog_api*" }
if ($backlogProc) {
    Stop-Process -Id $backlogProc.Id -Force
    Write-Host "  Backlog API stopped" -ForegroundColor Green
}

# Stop n8n containers
Push-Location $DOCKER_DIR
docker compose down 2>&1 | Out-Null
Write-Host "  n8n stopped" -ForegroundColor Green
Pop-Location

Write-Host ""
Write-Host "All services stopped." -ForegroundColor Green
