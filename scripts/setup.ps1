# One-time Earth Station setup on Windows.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$python = $null
foreach ($candidate in @("py -3.12", "py -3.11", "python")) {
    $exe, $args_ = $candidate.Split(" ", 2)
    if (Get-Command $exe -ErrorAction SilentlyContinue) {
        $ok = & $exe $args_ -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
        if ($ok -eq "True") { $python = $candidate; break }
    }
}
if (-not $python) {
    Write-Host "Python 3.11 or newer is required: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "Using $python"

if (-not (Test-Path .venv)) {
    $exe, $args_ = $python.Split(" ", 2)
    & $exe $args_ -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example (defaults use the simulator)."
} else {
    Write-Host ".env already exists; left unchanged. Compare it with .env.example for new settings."
}

Write-Host ""
Write-Host "Setup done. Next:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python -m earth_station --sim      # try it with the fake rover"
Write-Host "  pytest                             # run the tests"
