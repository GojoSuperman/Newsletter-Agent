@echo off
rem AI 뉴스레터 리더 실행기 — WSL에서 서버를 켜고, 앱 창(브라우저)을 띄운 뒤, 창이 닫히면 서버를 끈다.
%SystemRoot%\System32\chcp.com 65001 >nul
title AI 뉴스레터

wsl.exe -d Ubuntu -- bash -lc "~/projects/Newsletter-Agent/scripts/reader-start.sh"
if errorlevel 1 (
  echo.
  echo 서버 시작에 실패했습니다. 아무 키나 누르면 닫힙니다.
  pause >nul
  exit /b 1
)

set "PROFILE=%LOCALAPPDATA%\NewsletterReader\browser-profile"
set "URL=http://127.0.0.1:8100"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"

rem 전용 프로필로 띄우면 별도 프로세스가 되어 창이 닫힐 때까지 /wait 가 실제로 기다린다.
if exist "%EDGE%" (
  start "" /wait "%EDGE%" --app=%URL% --user-data-dir="%PROFILE%" --window-size=1280,900 --no-first-run --no-default-browser-check
) else if exist "%CHROME%" (
  start "" /wait "%CHROME%" --app=%URL% --user-data-dir="%PROFILE%" --window-size=1280,900 --no-first-run --no-default-browser-check
) else (
  start "" %URL%
  echo 앱 창을 닫아도 서버는 켜져 있습니다. 이 창을 닫으면 서버를 끕니다.
  pause >nul
)

wsl.exe -d Ubuntu -- bash -lc "~/projects/Newsletter-Agent/scripts/reader-stop.sh"
