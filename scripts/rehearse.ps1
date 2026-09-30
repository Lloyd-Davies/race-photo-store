$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    & docker --context desktop-linux build -f scripts/Dockerfile.checks -t race-photo-local-checks:worktree .
    if ($LASTEXITCODE -ne 0) { throw 'Rehearsal image build failed.' }
    $rehearsalScript = Join-Path $PSScriptRoot 'rehearse-migrations.py'
    & docker --context desktop-linux run --rm -v /var/run/docker.sock:/var/run/docker.sock --mount "type=bind,source=$rehearsalScript,target=/workspace/rehearse.py,readonly" --entrypoint python race-photo-local-checks:worktree /workspace/rehearse.py
    if ($LASTEXITCODE -ne 0) { throw 'Disposable migration rehearsal failed.' }
} finally { Pop-Location }
