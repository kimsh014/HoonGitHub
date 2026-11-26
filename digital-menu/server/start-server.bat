@echo off
rem 개발·점검용: 메뉴판 서버를 이 창에서 켠다. 이 창을 닫으면 서버도 꺼진다.
rem 매장 POS기에는 install-server.bat 으로 설치한다(창 없이, 켜질 때 자동 실행).
rem 방화벽 등 시스템 설정은 건드리지 않는다(처음 켤 때 Windows가 묻는 창에서 '허용'을 누른다).
chcp 65001 >nul
cd /d "%~dp0"

rem 자동 실행 서버가 이미 8090을 쓰고 있으면 둘이 겹친다.
set "MB_BUSY="
schtasks /query /tn MenuBoardServer >nul 2>&1 && set "MB_BUSY=1"
netstat -ano | findstr /r /c:":8090 .*LISTENING" >nul && set "MB_BUSY=1"
if defined MB_BUSY (
  echo ==================================================
  echo  [주의] 이 PC에는 메뉴판 서버 자동 실행이 설치되어 있거나 8090 포트를 이미 쓰는 서버가 있습니다.
  echo  그대로 켜면 8090이 겹쳐 이 창의 서버는 켜지지 않습니다.
  echo  점검하려면 관리자 명령 프롬프트에서 먼저: schtasks /end /tn MenuBoardServer
  echo  점검이 끝나면 PC를 다시 켜거나:            schtasks /run /tn MenuBoardServer
  echo ==================================================
  pause
)

echo ==================================================
echo  [개발·점검용] 매장 설치는 install-server.bat 을 쓰세요.
echo  보드 설정 화면의 "서버 주소"에 아래 중 매장 네트워크 주소를 넣으세요
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr IPv4') do echo    %%a:8090
echo.
echo  수정 화면: 이 POS의 브라우저에서 http://127.0.0.1:8090/admin.html
echo  이 창을 닫으면 서버가 꺼집니다.
echo ==================================================
pocketbase.exe serve --http 0.0.0.0:8090 --dir pb_data --migrationsDir pb_migrations --hooksDir pb_hooks --publicDir pb_public
pause
