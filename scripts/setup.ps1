<#
.SYNOPSIS
  Create the isolated experiment environment and fetch the pinned benchmarks.

.DESCRIPTION
  * Creates .venv in the repository with the chosen Python (default 3.13). Your global
    Python, PyTorch ROCm, Ollama and driver setup are not touched.
  * Installs this package and its small dependency set into .venv only.
  * Runs scripts/setup_external.py to clone the official repositories at pinned commits
    and download the pinned datasets (about 600 MB), verifying sha256 hashes.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -PythonVersion 3.12 -WithOptional
#>
param(
    [string]$PythonVersion = "3.13",
    [switch]$WithOptional,
    [switch]$SkipData
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo

$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating .venv with Python $PythonVersion"
    & py "-$PythonVersion" -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "py -$PythonVersion not found. Install it or pass -PythonVersion." }
}
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if (-not $SkipData) {
    $setupArgs = @("scripts\setup_external.py")
    if ($WithOptional) { $setupArgs += "--with-optional" }
    & $venvPy -X utf8 @setupArgs
    if ($LASTEXITCODE -ne 0) { throw "setup_external.py reported failures (see above)" }
    & (Join-Path $repo ".venv\Scripts\wlmem.exe") verify-data
}
Write-Host "Done. Activate with: .\.venv\Scripts\Activate.ps1"
