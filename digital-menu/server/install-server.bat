@echo off
rem 매장 POS기에 메뉴판 서버를 설치한다(창 없이, 컴퓨터가 켜지면 자동 실행).
rem 더블클릭하면 관리자 권한을 묻는다. '예'를 누른다.
rem   install-server.bat          설치. 다시 실행해도 된다(설정은 새로 맞추고 메뉴 데이터는 그대로).
rem   install-server.bat --reset  A/S 관리자 비밀번호를 새로 만든다.
rem 인터넷에서 아무것도 받지 않는다. Windows 기본 기능(작업 스케줄러, 방화벽, powercfg)만 쓴다.
chcp 65001 >nul
setlocal
set "MB_RESET="
if /i "%~1"=="--reset" set "MB_RESET=-Reset"
if /i "%~1"=="/reset" set "MB_RESET=-Reset"

rem 관리자 권한이 아니면 스스로 관리자 권한으로 다시 실행한다.
fltmc >nul 2>&1
if errorlevel 1 goto elevate

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-server.ps1" %MB_RESET%
echo.
pause
exit /b

:elevate
echo 관리자 권한으로 다시 엽니다. 사용자 계정 컨트롤 창에서 '예'를 누르세요.
set "MB_SELF=%~f0"
set "MB_ARGS=%*"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { if ($env:MB_ARGS) { Start-Process -FilePath $env:MB_SELF -ArgumentList $env:MB_ARGS -Verb RunAs } else { Start-Process -FilePath $env:MB_SELF -Verb RunAs } } catch { exit 1 }"
if errorlevel 1 (
  echo 관리자 권한을 얻지 못했습니다. install-server.bat 을 마우스 오른쪽 단추로 눌러 '관리자 권한으로 실행'을 고르세요.
  pause
)
exit /b
