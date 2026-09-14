# 바탕화면에 "AI 뉴스레터" 바로가기(.lnk)를 만든다. PowerShell에서: .\바로가기-만들기.ps1
# 실행기(.bat)와 아이콘을 %LOCALAPPDATA%\NewsletterReader 에 복사한 뒤 아이콘 붙은 바로가기를 만든다.
$src = $PSScriptRoot
$dst = Join-Path $env:LOCALAPPDATA "NewsletterReader"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item (Join-Path $src "AI뉴스레터.bat") $dst -Force
Copy-Item (Join-Path $src "newsletter.ico") $dst -Force
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desktop "AI 뉴스레터.lnk"))
$lnk.TargetPath = Join-Path $dst "AI뉴스레터.bat"
$lnk.WorkingDirectory = $dst
$lnk.IconLocation = (Join-Path $dst "newsletter.ico") + ",0"
$lnk.WindowStyle = 7
$lnk.Description = "AI 뉴스레터 리더 — 서버를 켜고 앱 창을 엽니다. 창을 닫으면 서버도 꺼집니다."
$lnk.Save()
"바로가기를 만들었습니다: $desktop\AI 뉴스레터.lnk"
