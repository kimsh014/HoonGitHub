@echo off
rem 메뉴판 키패드 앱(MenuBoardKeypad.exe)을 빌드한다. Windows 10에 들어 있는 .NET Framework 4.x의 csc.exe만 쓴다(따로 설치할 것 없음).
rem   build.bat        MenuBoardKeypad.exe 만들기
rem   build.bat test   키패드 규칙 검사(tests\KeypadLogicTests.cs)도 돌리기
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo [실패] .NET Framework 4 의 csc.exe 를 찾지 못했습니다. Windows 10 이면 기본으로 있습니다.
  exit /b 1
)
"%CSC%" -nologo -langversion:5 -target:winexe -optimize+ -codepage:65001 -win32manifest:src\app.manifest -out:MenuBoardKeypad.exe ^
  -r:System.Windows.Forms.dll -r:System.Drawing.dll -r:System.Web.Extensions.dll -r:System.Security.dll src\*.cs
if errorlevel 1 (
  echo [실패] 빌드하지 못했습니다.
  exit /b 1
)
echo [완료] MenuBoardKeypad.exe
if /i not "%~1"=="test" exit /b 0
"%CSC%" -nologo -langversion:5 -target:exe -codepage:65001 -out:"%TEMP%\KeypadLogicTests.exe" src\KeypadLogic.cs tests\KeypadLogicTests.cs
if errorlevel 1 exit /b 1
"%TEMP%\KeypadLogicTests.exe"
