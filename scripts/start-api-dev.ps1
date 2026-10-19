$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'import-env.ps1')
$env:QUICK_ENTRY_DATA_DIR = Join-Path $root 'data'
Set-Location (Join-Path $root 'apps/api')
& ./mvnw.cmd spring-boot:run
exit $LASTEXITCODE
