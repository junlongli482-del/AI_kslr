$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$env:QUICK_ENTRY_DATA_DIR = Join-Path $root 'data'
Set-Location (Join-Path $root 'apps/api')
& java -jar target/quick-entry-api-0.1.0.jar
