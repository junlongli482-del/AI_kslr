# Optional watchdog for the quick-entry AI service on port 1003.
# Run it in its own terminal: powershell -ExecutionPolicy Bypass -File scripts\watch-ai.ps1
param([int]$Interval = 10, [int]$Failures = 3)

$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root 'logs\ai.watch.log'
$bad = 0

function Write-Watch([string]$text) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $text
    Add-Content -LiteralPath $log -Value $line -Encoding utf8
    Write-Host $line
}

New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
Write-Watch "watch-ai started (interval=${Interval}s, threshold=$Failures)"

while ($true) {
    $ok = $false
    try {
        $response = Invoke-RestMethod -Uri 'http://127.0.0.1:1003/health' -TimeoutSec 4
        $ok = ($response.status -eq 'ok')
    } catch { $ok = $false }

    if ($ok) {
        if ($bad -gt 0) { Write-Watch "health recovered after $bad failure(s)" }
        $bad = 0
    } else {
        $bad++
        Write-Watch "health check failed ($bad/$Failures)"
        if ($bad -ge $Failures) {
            try {
                $conn = Get-NetTCPConnection -LocalPort 1003 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($conn) {
                    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
                    Write-Watch "stopped stale listener pid=$($conn.OwningProcess)"
                }
            } catch { Write-Watch "could not stop stale listener: $($_.Exception.Message)" }
            Start-Sleep -Seconds 2
            Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', ('"' + (Join-Path $PSScriptRoot 'dev.cmd') + '" ai') -WindowStyle Hidden
            Write-Watch "restart requested via scripts\dev.cmd ai"
            $bad = 0
        }
    }
    Start-Sleep -Seconds $Interval
}
