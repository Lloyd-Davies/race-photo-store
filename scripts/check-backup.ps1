$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$composeArgs = @('--context', 'desktop-linux', 'compose', '--env-file', (Join-Path $PSScriptRoot 'local.env'), '-p', 'race-photo-backup-test', '-f', (Join-Path $repoRoot 'backup/compose.test.yml'))
try {
    & docker @composeArgs build tests
    if ($LASTEXITCODE -ne 0) { throw 'Backup test image build failed.' }
    & docker @composeArgs up --abort-on-container-exit --exit-code-from tests
    if ($LASTEXITCODE -ne 0) { throw 'Backup tests failed.' }
} finally {
    & docker @composeArgs down
}
