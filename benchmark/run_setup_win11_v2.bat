@echo off
set LOG=C:\http2-bomb-mcp\logs\setup2.log
mkdir C:\http2-bomb-mcp\logs 2>nul
echo [%TIME%] START>>%LOG%

echo [%TIME%] DISM IIS>>%LOG%
dism /online /enable-feature /featurename:IIS-WebServerRole /all /norestart >>%LOG% 2>&1

echo [%TIME%] DOWNLOAD>>%LOG%
curl.exe -s -o C:\http2-bomb-mcp\win.tar.gz http://192.168.2.50:8888/http2-bomb-mcp-win.tar.gz >>%LOG% 2>&1
tar -xzf C:\http2-bomb-mcp\win.tar.gz -C C:\http2-bomb-mcp >>%LOG% 2>&1

echo [%TIME%] WINGET PYTHON>>%LOG%
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent >>%LOG% 2>&1

echo [%TIME%] PIP>>%LOG%
set PATH=%PATH%;C:\Users\Public\AppData\Local\Programs\Python\Python312;C:\Users\Public\AppData\Local\Programs\Python\Python312\Scripts
for /f "tokens=*" %%i in ('where python 2^>nul') do set PY=%%i
if not defined PY set PY=python
%PY% -m pip install --upgrade pip >>%LOG% 2>&1
cd /d C:\http2-bomb-mcp
%PY% -m pip install -r requirements.txt >>%LOG% 2>&1

echo [%TIME%] IIS HTTPS>>%LOG%
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$cert=New-SelfSignedCertificate -DnsName 'localhost','win11-lab.local' -CertStoreLocation 'Cert:\LocalMachine\My'; Import-Module WebAdministration; if(-not (Get-WebBinding -Name 'Default Web Site' -Protocol https -ErrorAction SilentlyContinue)){New-WebBinding -Name 'Default Web Site' -Protocol https -Port 443}; New-Item 'IIS:\SslBindings\0.0.0.0!443' -Value $cert -Force | Out-Null; Start-Service W3SVC; Set-Service W3SVC -StartupType Automatic; New-NetFirewallRule -DisplayName 'IIS-443' -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue" >>%LOG% 2>&1

echo [%TIME%] DONE>>%LOG%
netstat -an | findstr ":443" >>%LOG% 2>&1
sc query W3SVC >>%LOG% 2>&1
