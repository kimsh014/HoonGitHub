@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
python make_manual.py
python -m PyInstaller --noconfirm --onefile --windowed --name PrinterTester --add-data "manual.html;." gui.py || (pause & exit /b 1)
echo.
echo Done: dist\PrinterTester.exe  (copy this single file to the test PC)
pause
