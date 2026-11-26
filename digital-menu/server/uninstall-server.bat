@echo off
rem 메뉴판 서버 자동 실행을 없앤다(작업 스케줄러 작업, 방화벽 규칙, Defender 예외).
rem 메뉴·계정 데이터(pb_data)와 이 폴더는 지우지 않는다. 데이터까지 없애려면 백업한 뒤 이 폴더를 직접 지운다.
chcp 65001 >nul
setlocal
fltmc >nul 2>&1
if errorlevel 1 goto elevate

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-server.ps1" -Uninstall
echo.
pause
exit /b

:elevate
echo 관리자 권한으로 다시 엽니다. 사용자 계정 컨트롤 창에서 '예'를 누르세요.
set "MB_SELF=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Start-Process -FilePath $env:MB_SELF -Verb RunAs } catch { exit 1 }"
if errorlevel 1 (
  echo 관리자 권한을 얻지 못했습니다. uninstall-server.bat 을 마우스 오른쪽 단추로 눌러 '관리자 권한으로 실행'을 고르세요.
  pause
)
exit /b
