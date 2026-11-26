# 메뉴판 키패드 앱 설치·제거. install-order-app.bat 이 관리자 권한으로 부른다.
#   -Uninstall  작업 스케줄러 작업을 없애고 앱을 끈다(설정 %APPDATA%\MenuBoard\keypad.ini 는 그대로).
# - MenuBoardKeypad.exe 가 없거나 소스보다 오래되었으면 Windows 기본 csc.exe 로 빌드한다(build.bat).
# - 이 폴더를 관리자·SYSTEM만 고칠 수 있게 잠근다(가장 높은 권한으로 도는 exe를 다른 계정·프로그램이 바꿔치기하지 못하게).
# - 작업 "MenuBoardKeypad"를 화면에 로그인해 있는 사용자(판매 프로그램을 쓰는 계정)로, 로그인할 때, 가장 높은 권한으로 실행하게 등록한다.
#   UAC 창에 다른 관리자 계정을 넣어 설치해도 화면에 로그인한 사용자로 등록된다.
#   가장 높은 권한이어야 관리자 권한으로 도는 판매 프로그램 위에서도 숫자패드를 받는다(Windows UIPI).
#   앱 안의 지킴이가 앱이 꺼지면 다시 켠다. 작업은 시간 제한 없이 돈다.
# 이 파일은 UTF-8(BOM 있음)으로 저장해야 한다. BOM이 없으면 Windows PowerShell 5.1이 한글을 깨뜨린다.
param([switch]$Uninstall)

$TaskName = 'MenuBoardKeypad'
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$Root = $PSScriptRoot
$Exe  = Join-Path $Root 'MenuBoardKeypad.exe'

function Step([string]$t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }
function Ok([string]$t)   { Write-Host "   [완료] $t" -ForegroundColor Green }
function Warn([string]$t) { Write-Host "   [주의] $t" -ForegroundColor Yellow }
function Fail([string]$t) { Write-Host ''; Write-Host "[실패] $t" -ForegroundColor Red; exit 1 }

function Stop-App {
    $n = 0
    Get-CimInstance Win32_Process -Filter "Name='MenuBoardKeypad.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -ieq $Exe) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }
    return $n
}

Step '앱 끄기'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
$stopped = Stop-App
Ok "켜져 있던 것 $stopped 개를 껐습니다."

if ($Uninstall) {
    Step '자동 실행 없애기'
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Ok "작업 '$TaskName' 을 지웠습니다."
    } else { Ok '등록된 작업이 없습니다.' }
    Write-Host ''
    Write-Host '키패드 앱을 없앴습니다. 설정(연동 키)은 %APPDATA%\MenuBoard\keypad.ini 에 남아 있습니다.'
    exit 0
}

Step '빌드'
$sources = Get-ChildItem -LiteralPath (Join-Path $Root 'src') -File
$newest = ($sources | Measure-Object -Property LastWriteTime -Maximum).Maximum
if ((Test-Path -LiteralPath $Exe) -and (Get-Item -LiteralPath $Exe).LastWriteTime -ge $newest) {
    Ok 'MenuBoardKeypad.exe 가 최신입니다.'
} else {
    & cmd.exe /c "`"$(Join-Path $Root 'build.bat')`""
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Exe)) { Fail 'MenuBoardKeypad.exe 를 빌드하지 못했습니다. 위 오류를 확인하세요.' }
    Ok 'MenuBoardKeypad.exe 를 만들었습니다.'
}

Step '폴더 잠그기'
$ErrorActionPreference = 'Continue'  # Windows PowerShell 5.1은 프로그램의 오류 출력을 예외로 바꾼다
$acl = (& "$env:SystemRoot\System32\icacls.exe" $Root /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' /T /C /Q 2>&1 | ForEach-Object { [string]$_ }) -join ' '
$ErrorActionPreference = 'Stop'
if ($LASTEXITCODE -ne 0) { Warn "폴더 권한을 바꾸지 못했습니다(다른 계정이 앱을 바꿀 수 있음): $acl" }
else { Ok '관리자·SYSTEM만 고칠 수 있고, 다른 사용자는 읽기·실행만 됩니다.' }

Step '로그인할 때 자동 실행'
$user = (Get-CimInstance Win32_ComputerSystem).UserName  # 화면에 로그인한 사용자
if (-not $user) { $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name }
$isAdmin = $false
try {
    $isAdmin = [bool](Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction Stop | Where-Object { $_.Name -ieq $user })
} catch { $isAdmin = $true } # 도메인 계정 등 확인할 수 없으면 경고하지 않는다
if (-not $isAdmin) {
    Warn "$user 은(는) 관리자 계정이 아닙니다. 판매 프로그램이 관리자 권한으로 돌면 키패드를 받지 못할 수 있습니다(설정에서 '숫자패드 받기'를 끄고 화면 단추로 부르거나, 이 계정을 관리자로 바꾸세요)."
}
$action   = New-ScheduledTaskAction -Execute $Exe -WorkingDirectory $Root
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $user
$who      = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
$null = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $who -Settings $settings `
    -Description '메뉴판 키패드 앱: 숫자패드로 번호+Enter를 치면 TV 메뉴판에 번호를 띄운다.' -Force
Ok "작업 '$TaskName' ($user, 로그인할 때, 가장 높은 권한)"
Write-Host "   판매 프로그램을 이 계정($user)으로 쓰는지 확인하세요. 다르면 그 계정으로 로그인해 다시 설치합니다." 

Step '지금 켜기'
try { Start-ScheduledTask -TaskName $TaskName } catch { Warn "지금 켜지 못했습니다. 다시 로그인하면 켜집니다: $($_.Exception.Message)" }
Start-Sleep -Seconds 2
$running = @(Get-CimInstance Win32_Process -Filter "Name='MenuBoardKeypad.exe'" -ErrorAction SilentlyContinue).Count
if ($running -ge 2) { Ok '번호 창이 떴습니다(오른쪽 아래).' } else { Warn '번호 창이 아직 안 보입니다. 잠시 뒤에도 없으면 %LOCALAPPDATA%\MenuBoard\keypad.log 를 확인하세요.' }

Write-Host ''
Write-Host '설치가 끝났습니다.' -ForegroundColor Green
Write-Host ' 1. 처음이면 번호 창의 설정이 열립니다. 수정 화면(admin.html) 맨 아래 POS·키오스크 연동 키를 붙여 넣고 [연결 확인] → [저장].'
Write-Host ' 2. 숫자패드로 번호 + Enter 를 치면 TV에 번호가 뜹니다. + 다시 부르기, - 빼기, . 한 자리 지움.'
Write-Host ' 3. 판매 프로그램 화면에서 숫자패드를 눌러도 판매 프로그램에는 숫자가 들어가지 않습니다(설정에서 끌 수 있음).'
