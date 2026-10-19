$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location (Join-Path $root 'apps/ai')
& (Join-Path $root '.venv/Scripts/python.exe') -m uvicorn main:app --host 127.0.0.1 --port 8091 --reload --reload-dir .
exit $LASTEXITCODE
