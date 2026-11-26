@echo off
rem 보드를 USB(또는 adb 네트워크)로 연결한 PC에서 더블클릭: 보드 앱을 설치하고 켠다.
rem adb가 없으면 APK를 USB 메모리로 옮겨 보드의 파일 관리자에서 설치해도 된다.
chcp 65001 >nul
cd /d "%~dp0"
set "ADB=adb"
where adb >nul 2>nul || set "ADB=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
"%ADB%" devices
"%ADB%" install -r menuboard-player.apk
rem 부팅 때 자동 실행(다른 앱 위에 표시)과 매장 서버에서 받은 업데이트 설치를 허용한다.
rem 리모컨만 있는 TV는 이 설정 화면이 숨겨져 있는 경우가 많아 여기서 해 둔다.
"%ADB%" shell appops set com.menuboard.player SYSTEM_ALERT_WINDOW allow
"%ADB%" shell appops set com.menuboard.player REQUEST_INSTALL_PACKAGES allow
rem USB 메모리의 설정 파일(menuboard.txt) 읽기 허용
"%ADB%" shell appops set com.menuboard.player MANAGE_EXTERNAL_STORAGE allow
rem A/S 연결 잠금: 앱이 ADB를 평소 꺼 두고, 관리 화면(TV 관리)이나 USB 설정 파일로 연 시간에만 켠다.
rem 주의: 이 줄 다음부터는 관리 화면에서 'A/S 연결 열기'를 해야 이 PC에서 adb로 붙을 수 있다.
"%ADB%" shell pm grant com.menuboard.player android.permission.WRITE_SECURE_SETTINGS
rem 홈 앱을 바꿀 수 있는 보드면 메뉴판을 홈 앱으로 둔다(구글 TV 등은 실패해도 괜찮다. 부팅 수신기로 뜬다).
"%ADB%" shell cmd package set-home-activity com.menuboard.player/.MainActivity
"%ADB%" shell am start -n com.menuboard.player/.MainActivity
echo.
echo 보드가 같은 망의 매장 서버를 스스로 찾습니다. 못 찾으면 설정 화면이 뜹니다.
echo 설정 화면: 리모컨 확인 버튼 2초 누르기. 서버 주소, 화면 번호, 글자 크기 배율을 넣고 저장하세요.
echo 설치가 끝나면 이 TV의 adb는 잠깁니다. 다시 붙으려면 POS기 관리 화면 http://서버주소:8090/devices.html 에서 'A/S 연결 열기'.
pause
