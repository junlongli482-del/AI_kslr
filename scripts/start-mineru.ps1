# Resident local MinerU server used by apps/ai when MINERU_PROVIDER=auto|local.
# Keep this terminal open; the model is loaded on the first parse and reused after that.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $root 'runtime\mineru'
foreach ($dir in @('home', 'models', 'modelscope', 'uploads', 'tmp')) {
    New-Item -ItemType Directory -Force (Join-Path $runtime $dir) | Out-Null
}

$env:MINERU_HOME = Join-Path $runtime 'home'
$env:MINERU_MODEL_BASE_DIR = Join-Path $runtime 'models'
$env:MODELSCOPE_CACHE = Join-Path $runtime 'modelscope'
$env:TMP = Join-Path $runtime 'tmp'
$env:TEMP = $env:TMP

$exe = Join-Path $root '.venv-mineru\Scripts\mineru-kit.exe'
if (-not (Test-Path $exe)) {
    Write-Error "Local MinerU runtime not found: $exe (see HANDOFF local MinerU section)"
    exit 1
}
$port = if ($env:MINERU_LOCAL_PORT) { $env:MINERU_LOCAL_PORT } else { '8020' }
$concurrency = if ($env:MINERU_LOCAL_CONCURRENCY) { $env:MINERU_LOCAL_CONCURRENCY } else { '2' }

Write-Host "MinerU local server: http://127.0.0.1:$port tier=standard concurrency=$concurrency"
& $exe api-server --port $port --tier standard --concurrency $concurrency --upload-dir (Join-Path $runtime 'uploads')
