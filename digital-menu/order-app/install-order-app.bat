@echo off
rem 매장 POS기에 메뉴판 키패드 앱을 설치한다(Windows 로그인 때 자동 실행, 꺼지면 다시 켬).
rem 더블클릭하면 관리자 권한을 묻는다. '예'를 누른다. 판매 프로그램을 쓰는 Windows 계정으로 로그인한 상태에서 실행한다.
rem   install-order-app.bat               설치. 다시 실행해도 된다(설정은 그대로).
rem   install-order-app.bat --uninstall   자동 실행을 없애고 앱을 끈다.
rem 인터넷에서 아무것도 받지 않는다. Windows 기본 기능(.NET Framework csc, 작업 스케줄러)만 쓴다.
chcp 65001 >nul
setlocal
set "MB_UNINSTALL="
if /i "%~1"=="--uninstall" set "MB_UNINSTALL=-Uninstall"
if /i "%~1"=="/uninstall" set "MB_UNINSTALL=-Uninstall"

fltmc >nul 2>&1
if errorlevel 1 goto elevate

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-order-app.ps1" %MB_UNINSTALL%
echo.
pause
exit /b

:elevate
echo 관리자 권한으로 다시 엽니다. 사용자 계정 컨트롤 창에서 '예'를 누르세요.
set "MB_SELF=%~f0"
set "MB_ARGS=%*"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { if ($env:MB_ARGS) { Start-Process -FilePath $env:MB_SELF -ArgumentList $env:MB_ARGS -Verb RunAs } else { Start-Process -FilePath $env:MB_SELF -Verb RunAs } } catch { exit 1 }"
if errorlevel 1 (
  echo 관리자 권한을 얻지 못했습니다. install-order-app.bat 을 마우스 오른쪽 단추로 눌러 '관리자 권한으로 실행'을 고르세요.
  pause
)
exit /b
