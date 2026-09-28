@echo off
cd /d "%~dp0"
python -c "import serial, openpyxl" 2>nul || (
  echo Installing required packages...
  python -m pip install -r requirements.txt || (echo Please install Python 3.9+ first: https://www.python.org/downloads/ & pause & exit /b 1)
)
start "" pythonw gui.py
