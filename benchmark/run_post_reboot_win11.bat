@echo off
set LOG=C:\APEX-Ngin2dos\logs\post_reboot.log
echo [%TIME%] POST_REBOOT>>%LOG%

echo [%TIME%] START W3SVC>>%LOG%
sc start W3SVC>>%LOG% 2>&1
sc config W3SVC start= auto>>%LOG% 2>&1

echo [%TIME%] INSTALL PYTHON>>%LOG%
if not exist C:\APEX-Ngin2dos\Python312 (
  curl.exe -L -o C:\APEX-Ngin2dos\python-installer.exe https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe >>%LOG% 2>&1
  C:\APEX-Ngin2dos\python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 TargetDir=C:\APEX-Ngin2dos\Python312 >>%LOG% 2>&1
)
set PATH=C:\APEX-Ngin2dos\Python312;C:\APEX-Ngin2dos\Python312\Scripts;%PATH%

echo [%TIME%] PIP>>%LOG%
cd /d C:\APEX-Ngin2dos
python -m pip install --upgrade pip >>%LOG% 2>&1
python -m pip install -r requirements.txt >>%LOG% 2>&1

echo [%TIME%] IIS HTTPS>>%LOG%
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Import-Module WebAdministration; $cert=Get-ChildItem Cert:\LocalMachine\My | Select-Object -First 1; if(-not $cert){$cert=New-SelfSignedCertificate -DnsName 'localhost' -CertStoreLocation 'Cert:\LocalMachine\My'}; if(-not (Get-WebBinding -Name 'Default Web Site' -Protocol https -ErrorAction SilentlyContinue)){New-WebBinding -Name 'Default Web Site' -Protocol https -Port 443}; if(-not (Test-Path 'IIS:\SslBindings\0.0.0.0!443')){New-Item 'IIS:\SslBindings\0.0.0.0!443' -Value $cert -Force}; Start-Service W3SVC; iisreset /start" >>%LOG% 2>&1

echo [%TIME%] VERIFY>>%LOG%
netstat -an | findstr "LISTENING" | findstr ":443" >>%LOG% 2>&1
sc query W3SVC >>%LOG% 2>&1
python --version >>%LOG% 2>&1

echo [%TIME%] RUN ORCHESTRATOR>>%LOG%
powershell.exe -ExecutionPolicy Bypass -File C:\APEX-Ngin2dos\benchmark\iis_apex_orchestrator.ps1 -Host 127.0.0.1 -Port 443 -Preset 8gb >>%LOG% 2>&1

echo [%TIME%] ALL_DONE>>%LOG%
