$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'import-env.ps1')
Set-Location (Join-Path $root 'apps/web')
$vite = Join-Path $root 'apps/web/node_modules/vite/bin/vite.js'
if (-not (Test-Path -LiteralPath $vite)) {
    throw 'Frontend dependencies are missing. Install apps/web dependencies before starting Vite.'
}

# pnpm may only exist in the coding tool PATH. Starting installed Vite needs Node only.
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$node = if ($nodeCommand) { $nodeCommand.Source } else { $null }
if (-not $node) {
    $candidates = @(
        "$env:NVM_SYMLINK/node.exe",
        "$env:ProgramFiles/nodejs/node.exe",
        'D:/nvm4w/nodejs/node.exe',
        (Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Packages/OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe/node-v24.20.0-win-x64/node.exe')
    )
    $node = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $node) {
    throw 'Node.js was not found. Install Node.js or add node.exe to PATH, then reopen CMD.'
}
$port = if ($env:WEB_PORT) { $env:WEB_PORT } else { '5173' }
Write-Host "Starting Vite with $node on 127.0.0.1:$port"
& $node $vite --host 127.0.0.1 --port $port --strictPort
exit $LASTEXITCODE
