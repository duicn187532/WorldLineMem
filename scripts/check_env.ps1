<#
.SYNOPSIS
  Read-only inventory of the local experiment machine (Phase 1).

.DESCRIPTION
  Collects OS, CPU, memory, GPU, disk, Python interpreters and key packages
  (torch/ROCm, faiss, networkx, neo4j), the ROCm/HIP SDK, Ollama (version, installed
  and loaded models, OLLAMA_* settings) and git. Writes env_reports/env_<timestamp>.json
  and prints a summary.

  It changes nothing: no installs, no service starts, no driver or Ollama settings.
  The only network access is to the local Ollama API (default http://127.0.0.1:11434).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
  powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1 -OllamaUrl http://127.0.0.1:11434
#>
param(
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [string]$OutDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "env_reports")
)

$ErrorActionPreference = "Continue"
$report = [ordered]@{ generated = (Get-Date).ToString("o"); host = $env:COMPUTERNAME; notes = @() }

function Try-Run([string]$name, [scriptblock]$block) {
    try { return & $block } catch { $script:report.notes += "$name failed: $($_.Exception.Message)"; return $null }
}

# --- OS / CPU / memory -------------------------------------------------------------
$report.os = Try-Run "os" {
    $o = Get-CimInstance Win32_OperatingSystem
    [ordered]@{ caption = $o.Caption; version = $o.Version; build = $o.BuildNumber; arch = $o.OSArchitecture;
                total_visible_memory_gb = [math]::Round($o.TotalVisibleMemorySize / 1MB, 1);
                free_memory_gb = [math]::Round($o.FreePhysicalMemory / 1MB, 1) }
}
$report.cpu = Try-Run "cpu" {
    Get-CimInstance Win32_Processor | ForEach-Object {
        [ordered]@{ name = $_.Name.Trim(); cores = $_.NumberOfCores; logical = $_.NumberOfLogicalProcessors; max_mhz = $_.MaxClockSpeed } }
}
$report.memory = Try-Run "memory" {
    $cs = Get-CimInstance Win32_ComputerSystem
    $mods = Get-CimInstance Win32_PhysicalMemory | ForEach-Object { [ordered]@{ gb = [math]::Round($_.Capacity / 1GB, 1); speed = $_.Speed; part = "$($_.PartNumber)".Trim() } }
    [ordered]@{ installed_gb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1); modules = $mods
                note = "Unified memory: the OS sees RAM minus the GPU carve-out set in BIOS / AMD Adrenalin (Variable Graphics Memory)." }
}

# --- GPU -------------------------------------------------------------------------------
$report.gpu = Try-Run "gpu" {
    $vc = Get-CimInstance Win32_VideoController | ForEach-Object {
        [ordered]@{ name = $_.Name; driver_version = $_.DriverVersion; driver_date = "$($_.DriverDate)"; pnp = $_.PNPDeviceID } }
    # AdapterRAM is a 32-bit field (caps at 4 GB); the registry value is accurate.
    $classKey = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    $dedicated = Get-ChildItem $classKey -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        if ($p -and $p."HardwareInformation.qwMemorySize") {
            [ordered]@{ adapter = $p.DriverDesc; dedicated_gb = [math]::Round([double]$p."HardwareInformation.qwMemorySize" / 1GB, 1) } }
    }
    [ordered]@{ controllers = $vc; dedicated_memory = $dedicated }
}

# --- ROCm / HIP SDK ---------------------------------------------------------------------
$report.rocm = Try-Run "rocm" {
    $r = [ordered]@{ HIP_PATH = $env:HIP_PATH; ROCM_PATH = $env:ROCM_PATH; HSA_OVERRIDE_GFX_VERSION = $env:HSA_OVERRIDE_GFX_VERSION }
    foreach ($exe in @("hipInfo.exe", "hipcc.bat", "hipcc", "rocm-smi", "amd-smi")) {
        $c = Get-Command $exe -ErrorAction SilentlyContinue
        if ($c) { $r[$exe] = $c.Source }
    }
    if ($r["hipcc.bat"] -or $r["hipcc"]) { $r.hipcc_version = (& hipcc --version 2>&1 | Out-String).Trim() }
    if ($r["hipInfo.exe"]) { $r.hipinfo = (& hipInfo.exe 2>&1 | Select-String -Pattern "Name|gcnArchName|totalGlobalMem" | Out-String).Trim() }
    $r
}

# --- Disk ---------------------------------------------------------------------------------
$report.disk = Try-Run "disk" {
    Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
        [ordered]@{ drive = $_.DeviceID; size_gb = [math]::Round($_.Size / 1GB, 1); free_gb = [math]::Round($_.FreeSpace / 1GB, 1) } }
}

# --- Python interpreters and packages -------------------------------------------------------
$probe = @'
import json, platform, sys, importlib
out = {"executable": sys.executable, "version": platform.python_version()}
for name in ["numpy", "torch", "faiss", "networkx", "neo4j", "sentence_transformers", "transformers", "openai", "tiktoken"]:
    try:
        m = importlib.import_module(name)
        out[name] = getattr(m, "__version__", "installed")
    except Exception as e:
        out[name] = None
try:
    import torch
    out["torch_hip"] = getattr(torch.version, "hip", None)
    out["torch_cuda_build"] = torch.version.cuda
    out["torch_gpu_available"] = torch.cuda.is_available()
    if torch.cuda.is_available():
        out["torch_device"] = torch.cuda.get_device_name(0)
        free, total = torch.cuda.mem_get_info()
        out["torch_device_mem_gb"] = round(total / 2**30, 1)
except Exception as e:
    out["torch_probe_error"] = repr(e)
try:
    import faiss
    out["faiss_gpus"] = faiss.get_num_gpus() if hasattr(faiss, "get_num_gpus") else None
except Exception:
    pass
print(json.dumps(out))
'@
$probeFile = Join-Path $env:TEMP "wlmem_probe.py"
Set-Content -Path $probeFile -Value $probe -Encoding UTF8
$pythons = @()
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    # lines look like " -V:3.13 *        C:\Program Files\Python313\python.exe"
    $pythons += (& py -0p 2>$null) | ForEach-Object { if ($_ -match '([A-Za-z]:\\.*?pythonw?\.exe)') { $Matches[1] } } |
        Where-Object { $_ -and (Test-Path $_) }
}
foreach ($cmd in @("python", "python3")) {
    $c = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike "*WindowsApps*") { $pythons += $c.Source }
}
$repoVenv = Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"
if (Test-Path $repoVenv) { $pythons += $repoVenv }
$report.python = @($pythons | Select-Object -Unique | ForEach-Object {
    $exe = $_
    Try-Run "python $exe" { (& $exe $probeFile 2>$null | Select-Object -Last 1) | ConvertFrom-Json }
})
Remove-Item $probeFile -ErrorAction SilentlyContinue

# --- Ollama ---------------------------------------------------------------------------------
$report.ollama = Try-Run "ollama" {
    $o = [ordered]@{ url = $OllamaUrl }
    $cli = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cli) { $o.cli = $cli.Source; $o.cli_version = (& ollama --version 2>&1 | Out-String).Trim() }
    $o.env = [ordered]@{}
    Get-ChildItem env: | Where-Object { $_.Name -like "OLLAMA_*" -or $_.Name -like "HIP_VISIBLE*" -or $_.Name -like "ROCR_*" } |
        ForEach-Object { $o.env[$_.Name] = $_.Value }
    foreach ($scope in @("User", "Machine")) {
        foreach ($n in @("OLLAMA_MODELS", "OLLAMA_CONTEXT_LENGTH", "OLLAMA_FLASH_ATTENTION", "OLLAMA_KV_CACHE_TYPE", "OLLAMA_NUM_PARALLEL", "OLLAMA_MAX_LOADED_MODELS", "OLLAMA_KEEP_ALIVE")) {
            $v = [Environment]::GetEnvironmentVariable($n, $scope)
            if ($v) { $o.env["$scope`:$n"] = $v }
        }
    }
    try {
        $o.api_version = (Invoke-RestMethod "$OllamaUrl/api/version" -TimeoutSec 5).version
        $o.models = @((Invoke-RestMethod "$OllamaUrl/api/tags" -TimeoutSec 10).models | ForEach-Object {
            $m = $_
            $ctx = $null
            try {
                $show = Invoke-RestMethod "$OllamaUrl/api/show" -Method Post -Body (@{ model = $m.name } | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 20
                $ctx = ($show.model_info.PSObject.Properties | Where-Object { $_.Name -like "*context_length" } | Select-Object -First 1).Value
                $caps = $show.capabilities
            } catch { $caps = $null }
            [ordered]@{ name = $m.name; digest = $m.digest; size_gb = [math]::Round($m.size / 1GB, 2);
                        family = $m.details.family; params = $m.details.parameter_size; quant = $m.details.quantization_level;
                        native_context = $ctx; capabilities = $caps }
        })
        $o.loaded = @((Invoke-RestMethod "$OllamaUrl/api/ps" -TimeoutSec 5).models | ForEach-Object {
            [ordered]@{ name = $_.name; size_gb = [math]::Round($_.size / 1GB, 2); vram_gb = [math]::Round($_.size_vram / 1GB, 2); context = $_.context_length } })
    } catch { $o.api_error = "Ollama API not reachable at $OllamaUrl ($($_.Exception.Message)). Start the Ollama app and re-run." }
    $o
}

# --- Graph tooling (detect only; nothing is started) -----------------------------------------------
$report.graph = Try-Run "graph" {
    [ordered]@{
        neo4j_services = @(Get-Service -Name "*neo4j*" -ErrorAction SilentlyContinue | ForEach-Object { [ordered]@{ name = $_.Name; status = "$($_.Status)" } })
        neo4j_cli = (Get-Command neo4j -ErrorAction SilentlyContinue).Source
        docker_cli = (Get-Command docker -ErrorAction SilentlyContinue).Source
    }
}
$report.git = Try-Run "git" { (& git --version 2>&1 | Out-String).Trim() }

# --- Write ---------------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$path = Join-Path $OutDir "env_$stamp.json"
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $path -Encoding UTF8

Write-Host "=== WorldLineMem environment report ==="
Write-Host ("OS      : {0} (build {1})" -f $report.os.caption, $report.os.build)
Write-Host ("CPU     : {0}" -f (@($report.cpu)[0].name))
Write-Host ("Memory  : {0} GB installed, {1} GB visible to Windows" -f $report.memory.installed_gb, $report.os.total_visible_memory_gb)
Write-Host ("GPU     : {0}" -f ((@($report.gpu.controllers) | ForEach-Object { $_.name }) -join "; "))
Write-Host ("Ollama  : {0}" -f $(if ($report.ollama.api_version) { "API " + $report.ollama.api_version + ", " + @($report.ollama.models).Count + " models" } else { $report.ollama.api_error }))
foreach ($p in $report.python) { if ($p) { Write-Host ("Python  : {0} {1} torch={2} hip={3} gpu={4}" -f $p.version, $p.executable, $p.torch, $p.torch_hip, $p.torch_gpu_available) } }
if ($report.notes.Count) { Write-Host "Notes   :"; $report.notes | ForEach-Object { Write-Host "  - $_" } }
Write-Host "Saved   : $path"
