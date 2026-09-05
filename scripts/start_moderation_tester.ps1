$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$environmentRoot = Join-Path $env:LOCALAPPDATA "GLMod\venv"
$environmentPython = Join-Path $environmentRoot "Scripts\python.exe"
$testerUrl = "http://127.0.0.1:8765"

try {
    $health = Invoke-RestMethod -Uri "$testerUrl/api/health" -TimeoutSec 2
    if ($health.status -eq "ok" -and $health.mode -eq "local-only") {
        Start-Process $testerUrl
        exit 0
    }
} catch {
    # The local tester is not running yet; continue with setup.
}

function Find-Python {
    $candidates = @(
        (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
        (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
        (Get-Command python3.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($candidate in $candidates) {
        & $candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }
    throw "Python 3.10 or newer is required. Install Python and run this launcher again."
}

if (-not (Test-Path -LiteralPath $environmentPython)) {
    $bootstrapPython = Find-Python
    Write-Host "Preparing the local moderation environment..."
    & $bootstrapPython -m venv $environmentRoot
}

$installedMarker = Join-Path $environmentRoot ".gingerlabs-moderation-installed"
if (-not (Test-Path -LiteralPath $installedMarker)) {
    Write-Host "Installing CPU moderation dependencies. This can take several minutes on the first run..."
    & $environmentPython -m pip install --upgrade pip
    & $environmentPython -m pip install -e "$repositoryRoot[moderation]"
    if ($LASTEXITCODE -ne 0) {
        throw "The moderation dependencies could not be installed."
    }
    New-Item -ItemType File -Path $installedMarker -Force | Out-Null
}

Set-Location $repositoryRoot
& $environmentPython -m gingerlabs_moderation
