@echo off
%SystemRoot%\System32\chcp.com 65001 >nul
title AI 뉴스레터 리더
echo 리더 앱을 켜는 중...
wsl.exe -d Ubuntu -- bash -lc "~/projects/Newsletter-Agent/scripts/reader-start.sh"
if errorlevel 1 (
  echo.
  echo 시작에 실패했습니다. 아무 키나 누르면 닫힙니다.
  pause >nul
  exit /b 1
)
start "" http://127.0.0.1:8100
