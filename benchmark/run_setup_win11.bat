@echo off
mkdir C:\APEX-Ngin2dos\logs 2>nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\APEX-Ngin2dos\setup_win11_iis_lab.ps1 > C:\APEX-Ngin2dos\logs\setup_out.log 2> C:\APEX-Ngin2dos\logs\setup_err.log
