@echo off
rem Digital menu board - hardware test helper. Double-click this file.
rem Asks for admin rights (UAC) because some checks read firewall, Defender and scheduled tasks.
rem Options are passed to hw-test.ps1, e.g.:  run-hw-test.bat -Only H-25,H-13
rem From another laptop on the same network:   run-hw-test.bat -Server http://192.168.0.10:8090
setlocal
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
net session >nul 2>&1
if errorlevel 1 (
  "%PS%" -NoProfile -Command "$a = '%*'; try { if ($a) { Start-Process -FilePath '%~f0' -ArgumentList $a -Verb RunAs } else { Start-Process -FilePath '%~f0' -Verb RunAs }; exit 0 } catch { exit 1 }"
  if not errorlevel 1 exit /b
  echo Admin rights were not granted. Running without admin: some checks will be skipped.
)
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0hw-test.ps1" %*
echo.
pause
