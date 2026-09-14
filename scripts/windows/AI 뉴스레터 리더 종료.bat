@echo off
%SystemRoot%\System32\chcp.com 65001 >nul
wsl.exe -d Ubuntu -- bash -lc "~/projects/Newsletter-Agent/scripts/reader-stop.sh"
timeout /t 2 >nul
