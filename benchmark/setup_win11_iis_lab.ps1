# Win11 IIS lab setup for http2-bomb apex_iis_mp
param(
    [string]$ArchiveUrl = "http://192.168.2.50:8888/http2-bomb-mcp-win.tar.gz",
    [string]$InstallRoot = "C:\http2-bomb-mcp",
    [int]$HttpsPort = 443
)

$ErrorActionPreference = "Continue"
$LogDir = Join-Path $InstallRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("setup_win11_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

Log "START setup Win11 IIS lab"

Log "OpenSSH Server"
try {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction SilentlyContinue | Out-Null
    Start-Service sshd -ErrorAction SilentlyContinue
    Set-Service sshd -StartupType Automatic -ErrorAction SilentlyContinue
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue | Out-Null
} catch {
    Log ("OpenSSH skip: " + $_.Exception.Message)
}

Log "Enable IIS features"
$features = @(
    "IIS-WebServerRole","IIS-WebServer","IIS-CommonHttpFeatures","IIS-HttpErrors",
    "IIS-ApplicationDevelopment","IIS-NetFxExtensibility45","IIS-HealthAndDiagnostics",
    "IIS-HttpLogging","IIS-Security","IIS-RequestFiltering","IIS-Performance",
    "IIS-WebServerManagementTools","IIS-ManagementConsole","IIS-ASPNET45"
)
foreach ($f in $features) {
    Log ("Feature: " + $f)
    Enable-WindowsOptionalFeature -Online -FeatureName $f -All -NoRestart -ErrorAction SilentlyContinue | Out-Null
}

Log "Python via winget if missing"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

Log "Download archive"
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$archive = Join-Path $env:TEMP "http2-bomb-mcp-win.tar.gz"
Invoke-WebRequest -Uri $ArchiveUrl -OutFile $archive -UseBasicParsing
tar -xzf $archive -C $InstallRoot
Log "Extracted to $InstallRoot"

Log "pip install"
Set-Location $InstallRoot
python -m pip install --upgrade pip -q
if (Test-Path "requirements.txt") { python -m pip install -r requirements.txt -q }

Log "Configure IIS HTTPS"
Import-Module WebAdministration -ErrorAction SilentlyContinue
$site = Get-Website -Name "Default Web Site" -ErrorAction SilentlyContinue
if (-not $site) {
    New-Website -Name "Default Web Site" -Port 80 -PhysicalPath "C:\inetpub\wwwroot" -Force | Out-Null
}
$cert = Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -match "win11-lab" } | Select-Object -First 1
if (-not $cert) {
    $cert = New-SelfSignedCertificate -DnsName @("win11-lab.local","localhost") -CertStoreLocation "Cert:\LocalMachine\My"
}
$binding = Get-WebBinding -Name "Default Web Site" -Protocol https -ErrorAction SilentlyContinue
if (-not $binding) {
    New-WebBinding -Name "Default Web Site" -Protocol https -Port $HttpsPort -SslFlags 0
}
$bindingPath = "IIS:\SslBindings\0.0.0.0!$HttpsPort"
if (-not (Test-Path $bindingPath)) {
    New-Item $bindingPath -Value $cert -Force | Out-Null
}
Start-Service W3SVC
Set-Service W3SVC -StartupType Automatic
New-NetFirewallRule -DisplayName "IIS-HTTPS-Lab" -Direction Inbound -Protocol TCP -LocalPort $HttpsPort -Action Allow -ErrorAction SilentlyContinue | Out-Null
New-NetFirewallRule -DisplayName "ICMPv4-Echo" -Protocol ICMPv4 -IcmpType 8 -Direction Inbound -Action Allow -ErrorAction SilentlyContinue | Out-Null

Log "Verify"
Get-Service W3SVC | Format-List | Out-String | ForEach-Object { Log $_ }
cmd /c "netstat -an | findstr :443" | ForEach-Object { Log $_ }

Log "DONE"
Log ("Orchestrator: powershell -ExecutionPolicy Bypass -File " + (Join-Path $InstallRoot "benchmark\iis_apex_orchestrator.ps1") + " -Host 127.0.0.1 -Port $HttpsPort -Preset 8gb")
