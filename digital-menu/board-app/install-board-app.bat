@echo off
rem 보드를 USB(또는 adb 네트워크)로 연결한 PC에서 더블클릭: 보드 앱을 설치하고 켠다.
rem adb가 없으면 APK를 USB 메모리로 옮겨 보드의 파일 관리자에서 설치해도 된다.
chcp 65001 >nul
cd /d "%~dp0"
set "ADB=adb"
where adb >nul 2>nul || set "ADB=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
"%ADB%" devices
"%ADB%" install -r menuboard-player.apk
"%ADB%" shell am start -n com.menuboard.player/.MainActivity
echo.
echo 보드에 설정 화면이 뜨면 서버 주소, 화면 번호, 글자 크기 배율을 넣고 저장하세요.
pause
