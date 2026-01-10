<#
.SYNOPSIS
    Stop n8n automation hub
#>

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$DOCKER_DIR = "$PROJECT_ROOT\docker"

Write-Host "Stopping n8n Automation Hub..." -ForegroundColor Cyan

Push-Location $DOCKER_DIR
try {
    docker compose down

    if ($LASTEXITCODE -eq 0) {
        Write-Host "n8n stopped successfully!" -ForegroundColor Green
    }
} finally {
    Pop-Location
}
