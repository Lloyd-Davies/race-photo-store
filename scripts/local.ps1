param([ValidateSet('start', 'stop', 'status', 'logs', 'config')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    $composeArgs = @('--context', 'desktop-linux', 'compose', '--env-file', 'scripts/local.env', '-p', 'race-photo-local', '-f', 'compose.local.yml')
    switch ($Action) {
        'start' { & docker @composeArgs up -d --build --wait --wait-timeout 180 }
        'stop' { & docker @composeArgs down } # Deliberately retain local data and volumes.
        'status' { & docker @composeArgs ps }
        'logs' { & docker @composeArgs logs --tail 100 }
        'config' { & docker @composeArgs config }
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker local $Action failed. Start Docker Desktop and inspect local logs." }
} finally { Pop-Location }
