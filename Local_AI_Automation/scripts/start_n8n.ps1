<#
.SYNOPSIS
    Start n8n automation hub
.DESCRIPTION
    Starts n8n and PostgreSQL containers for the Local AI Automation Hub
#>

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$DOCKER_DIR = "$PROJECT_ROOT\docker"

Write-Host "Starting n8n Automation Hub..." -ForegroundColor Cyan

# Check Docker
$dockerRunning = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $dockerRunning) {
    Write-Host "Starting Docker Desktop..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Start-Sleep -Seconds 30
}

# Start containers
Push-Location $DOCKER_DIR
try {
    docker compose up -d

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "n8n started successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Access n8n at: http://localhost:5678" -ForegroundColor White
        Write-Host ""

        # Get credentials from .env
        $envContent = Get-Content "$DOCKER_DIR\.env" -Raw
        if ($envContent -match "N8N_USER=(.+)") { $user = $Matches[1].Trim() }
        if ($envContent -match "N8N_PASSWORD=(.+)") { $pass = $Matches[1].Trim() }

        Write-Host "Credentials:" -ForegroundColor Gray
        Write-Host "  Username: $user" -ForegroundColor Gray
        Write-Host "  Password: $pass" -ForegroundColor Gray
        Write-Host ""

        # Wait for n8n to be ready
        Write-Host "Waiting for n8n to initialize..." -ForegroundColor Gray
        $maxAttempts = 30
        $attempt = 0
        while ($attempt -lt $maxAttempts) {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:5678/healthz" -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Write-Host "n8n is ready!" -ForegroundColor Green
                    break
                }
            } catch {}
            $attempt++
            Start-Sleep -Seconds 2
        }
    } else {
        Write-Error "Failed to start n8n containers"
    }
} finally {
    Pop-Location
}
