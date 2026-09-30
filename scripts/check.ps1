$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    $devPython = Join-Path $repoRoot '.venv-dev/Scripts/python.exe'
    if (!(Test-Path $devPython)) {
        & (Join-Path $PSScriptRoot 'check-container.ps1')
    } else {
    $checkRoot = Join-Path $repoRoot '.localdata/check'
    New-Item -ItemType Directory -Force -Path $checkRoot | Out-Null
    if (Test-Path (Join-Path $checkRoot '.env')) { throw 'Remove the unexpected .localdata/check/.env before testing.' }
    # Test fixtures start disposable PostgreSQL; never use production .env credentials.
    $safeEnv = @{ DATABASE_URL='postgresql+psycopg://test:test@127.0.0.1/test'; REDIS_URL='redis://127.0.0.1:6379/0'; ADMIN_TOKEN='test-admin-token'; ADMIN_SESSION_SECRET='test-only'; PUBLIC_BASE_URL='http://testserver'; STORAGE_ROOT=(Join-Path $repoRoot '.localdata/check/photos'); CACHE_ROOT=(Join-Path $repoRoot '.localdata/check/cache'); STORAGE_BACKEND='local'; ZIP_STORAGE_BACKEND='local'; PROOF_STORAGE_BACKEND='local'; ORIGINAL_STORAGE_BACKEND='local'; EMAIL_ENABLED='false'; STRIPE_SECRET_KEY=''; STRIPE_WEBHOOK_SECRET=''; BREVO_API_KEY=''; BREVO_WEBHOOK_SECRET=''; R2_ACCOUNT_ID=''; R2_ACCESS_KEY_ID=''; R2_SECRET_ACCESS_KEY=''; R2_ENDPOINT_URL=''; R2_PUBLIC_BASE_URL=''; SEO_SITE_URL='https://example.com'; SEO_LOGO_URL='https://example.com/favicon.svg' }
    $previous = @{}
    $safeEnv['PYTHONPATH'] = ((Join-Path $repoRoot 'api'), (Join-Path $repoRoot 'worker'), (Join-Path $repoRoot 'shared')) -join [IO.Path]::PathSeparator
    foreach ($key in $safeEnv.Keys) { $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process'); [Environment]::SetEnvironmentVariable($key, $safeEnv[$key], 'Process') }
    try {
        # Empty env values are removed by Windows PowerShell, so use a clean cwd
        # as well: pydantic must never fall back to the operator's root .env.
        Push-Location $checkRoot
        try {
        foreach ($suite in @('api/tests', 'worker/tests')) {
            & $devPython -m pytest (Join-Path $repoRoot $suite) -q
            if ($LASTEXITCODE -ne 0) { throw "Tests failed: $suite" }
        }
        } finally { Pop-Location }
    } finally { foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') } }
    }
    foreach ($task in @('test', 'typecheck', 'build')) {
        & npm --prefix frontend run $task
        if ($LASTEXITCODE -ne 0) { throw "Frontend $task failed." }
    }
} finally { Pop-Location }
