@echo off
mkdir C:\http2-bomb-mcp\logs 2>nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\http2-bomb-mcp\setup_win11_iis_lab.ps1 > C:\http2-bomb-mcp\logs\setup_out.log 2> C:\http2-bomb-mcp\logs\setup_err.log
