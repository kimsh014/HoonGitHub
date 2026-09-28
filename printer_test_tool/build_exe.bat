@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
python -m PyInstaller --noconfirm --onefile --windowed --name PrinterTester gui.py || (pause & exit /b 1)
echo.
echo Done: dist\PrinterTester.exe  (copy this single file to the test PC)
pause
