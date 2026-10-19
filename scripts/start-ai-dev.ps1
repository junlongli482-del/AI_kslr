$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'import-env.ps1')
$port = if ($env:AI_PORT) { $env:AI_PORT } else { '8091' }
Set-Location (Join-Path $root 'apps/ai')
& (Join-Path $root '.venv/Scripts/python.exe') -m uvicorn main:app --host 127.0.0.1 --port $port --reload --reload-dir .
exit $LASTEXITCODE
