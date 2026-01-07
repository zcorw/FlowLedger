# Usage:
#   pwsh scripts\apply_sql.ps1            # uses scripts/run_migration.sql
#   pwsh scripts\apply_sql.ps1 -SqlFile path\to\file.sql
param(
  [string]$SqlFile = "$(Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\run_migration.sql')"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path $SqlFile)) {
  Write-Error "SQL file not found: $SqlFile"
  exit 1
}

# Pipe SQL into the db service without opening an interactive shell.
Get-Content $SqlFile | docker compose --env-file .env exec -T db `
  psql -U $Env:POSTGRES_USER -d $Env:POSTGRES_DB -f -
