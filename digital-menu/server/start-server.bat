@echo off
rem 매장 POS에서 더블클릭해 메뉴판 서버를 켠다. 이 창을 닫으면 서버도 꺼진다.
rem 방화벽 등 시스템 설정은 건드리지 않는다(처음 켤 때 Windows가 묻는 창에서 '허용'을 누른다).
chcp 65001 >nul
cd /d "%~dp0"
echo ==================================================
echo  보드 설정 화면의 "서버 주소"에 아래 중 매장 네트워크 주소를 넣으세요
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr IPv4') do echo    %%a:8090
echo.
echo  수정 화면: 이 POS의 브라우저에서 http://127.0.0.1:8090/admin.html
echo  이 창을 닫으면 서버가 꺼집니다.
echo ==================================================
pocketbase.exe serve --http 0.0.0.0:8090 --dir pb_data --migrationsDir pb_migrations --hooksDir pb_hooks --publicDir pb_public
pause
