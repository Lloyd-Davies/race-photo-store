param([string]$PythonExe = '', [switch]$SkipFrontend, [switch]$ContainersOnly)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot
try {
    if (!$ContainersOnly) {
    if (!(Test-Path '.venv-dev/Scripts/python.exe')) {
        if ($PythonExe) { & $PythonExe -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'; if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 required' }; & $PythonExe -m venv .venv-dev }
        else { & py -3.12 -m venv .venv-dev }
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or pass -PythonExe with its absolute path.' }
    }
    $devPython = Join-Path $repoRoot '.venv-dev/Scripts/python.exe'
    & $devPython -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'
    if ($LASTEXITCODE -ne 0) { throw 'Existing .venv-dev must use Python 3.12.' }
    & $devPython -m pip install -e shared -r api/requirements.txt -r api/requirements-test.txt -r worker/requirements.txt -r worker/requirements-test.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    }
    if (!$SkipFrontend) {
        & npm --prefix frontend ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    }
    Write-Host 'Setup ready. Start Docker Desktop, then run scripts/check.ps1 and scripts/local.ps1.'
} finally { Pop-Location }
