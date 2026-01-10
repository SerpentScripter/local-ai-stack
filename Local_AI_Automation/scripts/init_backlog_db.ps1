<#
.SYNOPSIS
    Initialize the backlog SQLite database
.DESCRIPTION
    Creates the backlog database with schema for task tracking
#>

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$DATA_DIR = "$PROJECT_ROOT\data\backlog"
$DB_PATH = "$DATA_DIR\backlog.db"
$SCHEMA_PATH = "$DATA_DIR\schema.sql"

Write-Host "Initializing Backlog Database..." -ForegroundColor Cyan

# Check if sqlite3 is available
$sqlite = Get-Command sqlite3 -ErrorAction SilentlyContinue
if (-not $sqlite) {
    # Try common locations
    $sqlitePaths = @(
        "C:\Program Files\SQLite\sqlite3.exe",
        "C:\sqlite\sqlite3.exe",
        "$env:LOCALAPPDATA\Programs\SQLite\sqlite3.exe"
    )

    foreach ($path in $sqlitePaths) {
        if (Test-Path $path) {
            $sqlite = $path
            break
        }
    }

    if (-not $sqlite) {
        Write-Host "SQLite not found. Installing via winget..." -ForegroundColor Yellow
        winget install --id SQLite.SQLite -e --accept-package-agreements --accept-source-agreements
        $sqlite = "sqlite3"
    }
}

# Create database
if (Test-Path $DB_PATH) {
    $backup = "$DB_PATH.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Write-Host "Backing up existing database to: $backup" -ForegroundColor Yellow
    Copy-Item $DB_PATH $backup
}

# Execute schema
Write-Host "Creating database schema..." -ForegroundColor Gray
& $sqlite $DB_PATH ".read $SCHEMA_PATH"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Database initialized successfully!" -ForegroundColor Green
    Write-Host "Location: $DB_PATH" -ForegroundColor Gray

    # Show table info
    Write-Host ""
    Write-Host "Tables created:" -ForegroundColor Cyan
    & $sqlite $DB_PATH ".tables"

    Write-Host ""
    Write-Host "Categories:" -ForegroundColor Cyan
    & $sqlite $DB_PATH "SELECT name FROM categories;"
} else {
    Write-Error "Failed to initialize database"
}
