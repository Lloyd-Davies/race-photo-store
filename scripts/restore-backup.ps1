param([Parameter(Mandatory=$true)][string]$Manifest, [Parameter(Mandatory=$true)][string]$IdentityFile, [Parameter(Mandatory=$true)][string]$CredentialsFile)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
if (!(Test-Path -LiteralPath $IdentityFile -PathType Leaf)) { throw 'Private key file missing.' }
if (!(Test-Path -LiteralPath $CredentialsFile -PathType Leaf)) { throw 'Read-only credentials file missing.' }
$previousManifest = $env:RESTORE_MANIFEST
$previousIdentity = $env:RESTORE_IDENTITY_FILE
try {
    $env:RESTORE_MANIFEST = $Manifest
    $env:RESTORE_IDENTITY_FILE = (Resolve-Path -LiteralPath $IdentityFile).Path.Replace('\','/')
    $composeArgs = @('--context', 'desktop-linux', 'compose', '--env-file', (Resolve-Path -LiteralPath $CredentialsFile).Path, '-p', 'race-photo-restore-drill', '-f', (Join-Path $repoRoot 'backup/compose.restore.yml'))
    & docker @composeArgs build restore
    if ($LASTEXITCODE -ne 0) { throw 'Restore image build failed.' }
    & docker @composeArgs up -d restore-postgres
    if ($LASTEXITCODE -ne 0) { throw 'Disposable database startup failed.' }
    & docker @composeArgs run --rm restore
    if ($LASTEXITCODE -ne 0) { throw 'Restore failed; disposable data retained for inspection.' }
} finally {
    $env:RESTORE_MANIFEST = $previousManifest
    $env:RESTORE_IDENTITY_FILE = $previousIdentity
}
