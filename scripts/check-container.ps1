$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    & docker --context desktop-linux build -f scripts/Dockerfile.checks -t race-photo-local-checks:worktree .
    if ($LASTEXITCODE -ne 0) { throw 'Backend check image build failed.' }
    # Testcontainers needs Docker access to create disposable Postgres/Ryuk.
    # No host secrets, photo directories or production volumes are mounted.
    & docker --context desktop-linux run --rm -v /var/run/docker.sock:/var/run/docker.sock race-photo-local-checks:worktree
    if ($LASTEXITCODE -ne 0) { throw 'Container backend checks failed.' }
} finally { Pop-Location }
