$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$env:QUICK_ENTRY_DATA_DIR = Join-Path $root 'data'
Set-Location (Join-Path $root 'apps/api')
& ./mvnw.cmd spring-boot:run
exit $LASTEXITCODE
