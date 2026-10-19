# Load the project-local .env into this PowerShell process without printing values.
# Dev scripts call this so ports, database and AI settings have one source of truth.
param([string]$Path = (Join-Path (Split-Path $PSScriptRoot -Parent) '.env'))
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing $Path. Copy .env.example to .env and fill local values."
}
foreach ($line in Get-Content -LiteralPath $Path) {
    $trim = $line.Trim()
    if (-not $trim -or $trim.StartsWith('#')) { continue }
    $index = $trim.IndexOf('=')
    if ($index -lt 1) { continue }
    $key = $trim.Substring(0, $index).Trim()
    $value = $trim.Substring($index + 1)
    if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
}
