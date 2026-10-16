param([switch]$Build)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location $root
New-Item -ItemType Directory -Force -Path data/logs | Out-Null
if (-not (Test-Path '.env')) { throw '请从.env.example创建.env并填写服务密钥。' }
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw '请先执行README中的Python依赖安装步骤。' }
try { $null=Invoke-RestMethod 'http://127.0.0.1:8090/api/health' -TimeoutSec 2; $apiRunning=$true } catch { $apiRunning=$false }
try { $null=Invoke-RestMethod 'http://127.0.0.1:8091/health' -TimeoutSec 2; $aiRunning=$true } catch { $aiRunning=$false }
if ($Build) {
    & "$root/apps/api/mvnw.cmd" -q -f "$root/apps/api/pom.xml" package
    if ($LASTEXITCODE -ne 0) { throw 'Java构建失败' }
    Push-Location apps/web
    try { & pnpm build; if ($LASTEXITCODE -ne 0) { throw '网页构建失败' } } finally { Pop-Location }
}
$db=(docker ps --filter 'name=^/quick-entry-postgres$' --format '{{.Names}}')
if (-not $db) {
    $existing=(docker ps -a --filter 'name=^/quick-entry-postgres$' --format '{{.Names}}')
    if ($existing) { docker start quick-entry-postgres | Out-Null }
    else { docker compose -f deploy/compose.yaml up -d | Out-Null }
}
if (-not $aiRunning) {
    Start-Process -FilePath "$root/.venv/Scripts/python.exe" -ArgumentList '-m uvicorn main:app --app-dir apps/ai --host 127.0.0.1 --port 8091' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root/data/logs/ai.out.log" -RedirectStandardError "$root/data/logs/ai.err.log"
}
if (-not $apiRunning) {
    $env:QUICK_ENTRY_DATA_DIR=Join-Path $root 'data'
    Start-Process -FilePath 'java' -ArgumentList '-jar apps/api/target/quick-entry-api-0.1.0.jar' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root/data/logs/api.out.log" -RedirectStandardError "$root/data/logs/api.err.log"
}
try { $null=Invoke-WebRequest 'http://127.0.0.1:5173' -TimeoutSec 2; $webRunning=$true } catch { $webRunning=$false }
if (-not $webRunning) {
    Start-Process -FilePath 'node' -ArgumentList 'node_modules/vite/bin/vite.js --host 127.0.0.1' -WorkingDirectory "$root/apps/web" -WindowStyle Hidden -RedirectStandardOutput "$root/data/logs/web.out.log" -RedirectStandardError "$root/data/logs/web.err.log"
}
Write-Output '工作台地址：http://127.0.0.1:5173；如首次启动请等待约10秒。'
