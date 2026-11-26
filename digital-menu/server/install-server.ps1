# 메뉴판 서버 설치·제거. install-server.bat / uninstall-server.bat 이 관리자 권한으로 부른다.
#   -Reset      A/S 관리자(PocketBase superuser) 비밀번호를 새로 만든다.
#   -Uninstall  작업 스케줄러 작업, 방화벽 규칙, Defender 예외를 없앤다(pb_data는 그대로).
# 인터넷에서 아무것도 받지 않는다. Windows 기본 기능만 쓴다(Windows PowerShell 5.1에서 동작).
# 이 파일은 UTF-8(BOM 있음)으로 저장해야 한다. BOM이 없으면 Windows PowerShell 5.1이 한글을 깨뜨린다.
param(
    [switch]$Reset,
    [switch]$Uninstall
)

# ---- 바꿀 수 있는 값 ----
$TaskName         = 'MenuBoardServer'
$Port             = 8090
$AsEmail          = 'as@poswing.local'   # A/S용 PocketBase 관리자 이메일(모든 매장 같음, 비밀번호는 설치마다 다름)
$ActiveHoursStart = 7                    # Windows 업데이트가 재부팅하지 않는 시간(영업 시간) 시작
$ActiveHoursEnd   = 0                    # 끝(0 = 밤 12시). 시작~끝은 18시간 이하여야 한다(7~24시 = 17시간).
$FirewallGroup    = 'MenuBoard'
$PbVersion        = '0.40.6'
# -------------------------

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$Root      = $PSScriptRoot
$Exe       = Join-Path $Root 'pocketbase.exe'
$RunScript = Join-Path $Root 'run-server.ps1'
$PbData    = Join-Path $Root 'pb_data'
$PwFile    = Join-Path $Root 'AS-관리자-비밀번호.txt'
$script:Warnings = @()

function Step([string]$t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }
function Ok([string]$t)   { Write-Host "   [완료] $t" -ForegroundColor Green }
function Warn([string]$t) { Write-Host "   [주의] $t" -ForegroundColor Yellow; $script:Warnings += $t }
function Fail([string]$t) { Write-Host ''; Write-Host "[실패] $t" -ForegroundColor Red; exit 1 }

# pocketbase.exe 같은 프로그램을 부르고 출력(오류 포함)과 종료 코드를 돌려준다.
# Windows PowerShell 5.1은 프로그램의 오류 출력을 예외로 바꾸므로 잠깐 Continue로 둔다.
function Invoke-Exe([string]$File, [string[]]$Arguments) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = (& $File @Arguments 2>&1 | ForEach-Object { [string]$_ }) -join "`n"
        return @{ Code = $LASTEXITCODE; Out = $out }
    } finally { $ErrorActionPreference = $old }
}

function Stop-OurServer {
    $stopped = 0
    Get-CimInstance Win32_Process -Filter "Name='pocketbase.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -ieq $Exe) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $stopped++ }
    return $stopped
}

function Stop-OurTask {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        # 작업을 멈춰도 반복 스크립트(powershell.exe)가 남을 수 있어 이 폴더의 run-server.ps1 을 돌리는 것을 끈다.
        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($RunScript, [StringComparison]::OrdinalIgnoreCase) -ge 0 } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    return $task
}

function Remove-OurFirewallRules {
    Get-NetFirewallRule -Group $FirewallGroup -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    # Windows가 처음 실행 때 묻고 저절로 만든 pocketbase.exe 규칙도 지운다.
    # '취소'를 눌러 생긴 차단 규칙이 남아 있으면 허용 규칙보다 앞서 보드가 못 붙는다.
    Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue |
        Where-Object { $_.Program -and ($_.Program -ieq $Exe) } |
        Get-NetFirewallRule -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
}

# ---- 공통 확인 ----
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail '관리자 권한이 필요합니다. install-server.bat 으로 실행하세요.'
}
Write-Host "메뉴판 서버 폴더: $Root"

# ================= 제거 =================
if ($Uninstall) {
    Step '자동 실행 작업 없애기'
    $task = Stop-OurTask
    $n = Stop-OurServer
    if ($task) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; Ok "작업 '$TaskName' 을 지웠습니다." }
    else { Ok "작업 '$TaskName' 이 없습니다." }
    if ($n -gt 0) { Ok "돌던 서버를 껐습니다." }

    Step '방화벽 규칙 없애기'
    Remove-OurFirewallRules
    Ok "'$FirewallGroup' 규칙을 지웠습니다."

    Step 'Windows Defender 예외 없애기'
    try { Remove-MpPreference -ExclusionPath $Root; Ok '지웠습니다.' }
    catch { Ok '없거나 Defender가 꺼져 있습니다(괜찮음).' }

    Write-Host ''
    Write-Host '제거를 마쳤습니다. 메뉴·계정 데이터(pb_data)와 이 폴더는 그대로 남아 있습니다.' -ForegroundColor Green
    Write-Host '절전 끄기, 업데이트 활성 시간, 빠른 시작 설정은 되돌리지 않았습니다(필요하면 Windows 설정에서 직접).'
    exit 0
}

# ================= 설치 =================
Step '1. 파일 확인'
foreach ($p in @($Exe, $RunScript, (Join-Path $Root 'pb_migrations'), (Join-Path $Root 'pb_hooks'), (Join-Path $Root 'pb_public'))) {
    if (-not (Test-Path -LiteralPath $p)) { Fail "없습니다: $p  (배포 묶음의 server 폴더를 통째로 복사했는지 확인하세요)" }
}
$v = Invoke-Exe $Exe @('--version')
if ($v.Out -notmatch [regex]::Escape($PbVersion)) { Warn "pocketbase.exe 버전이 $PbVersion 이 아닙니다: $($v.Out)" }
else { Ok "pocketbase.exe $PbVersion" }
New-Item -ItemType Directory -Path (Join-Path $Root 'logs') -Force | Out-Null

# 서버는 SYSTEM 계정으로 이 폴더의 run-server.ps1과 pocketbase.exe를 돌린다. 일반 사용자가 이 폴더의 파일을
# 바꿀 수 있으면 SYSTEM 권한을 얻을 수 있으므로, 관리자·SYSTEM만 쓰고 일반 사용자(Users)는 읽기만 하게 한다.
$acl = Invoke-Exe "$env:SystemRoot\System32\icacls.exe" @($Root, '/inheritance:r', '/grant:r', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-545:(OI)(CI)RX', '/T', '/C', '/Q')
if ($acl.Code -ne 0) { Warn "폴더 권한을 바꾸지 못했습니다(일반 사용자가 서버 파일을 고칠 수 있음): $($acl.Out)" }
else { Ok '폴더 권한: 관리자·SYSTEM만 쓰기, 일반 사용자는 읽기만.' }
# 메뉴·계정 DB(비밀번호 해시, 로그인 토큰 키)와 백업, 로그, A/S 비밀번호 파일은 일반 사용자가 읽지도 못하게 한다.
New-Item -ItemType Directory -Path (Join-Path $Root 'pb_data') -Force | Out-Null
foreach ($p in @((Join-Path $Root 'pb_data'), (Join-Path $Root 'logs'))) {
    $r = Invoke-Exe "$env:SystemRoot\System32\icacls.exe" @($p, '/inheritance:r', '/grant:r', '*S-1-5-32-544:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '/T', '/C', '/Q')
    if ($r.Code -ne 0) { Warn "권한을 줄이지 못했습니다: $p" }
}
if (Test-Path -LiteralPath $PwFile) {
    $null = Invoke-Exe "$env:SystemRoot\System32\icacls.exe" @($PwFile, '/inheritance:r', '/grant:r', '*S-1-5-32-544:(R,D)', '*S-1-5-18:(R)')
}

Step '2. 돌고 있는 서버 끄기'
$null = Stop-OurTask
$n = Stop-OurServer
if ($n -gt 0) { Ok '이 폴더의 서버를 껐습니다(start-server.bat 창이 열려 있었다면 그 창은 닫으세요).' }
Start-Sleep -Seconds 1
$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listen) {
    $other = Get-Process -Id $listen.OwningProcess -ErrorAction SilentlyContinue
    Warn ("다른 프로그램이 $Port 포트를 쓰고 있습니다: " + $(if ($other) { $other.Path } else { "PID $($listen.OwningProcess)" }) + '. 그 프로그램을 끄지 않으면 메뉴판 서버가 켜지지 않습니다.')
} else { Ok "$Port 포트가 비어 있습니다." }

Step '3. A/S 관리자 계정'
# --reset 이 아니면 create 로 만들어 보고, 이미 있으면(email 중복) 그대로 둔다. --reset 이면 upsert 로 비밀번호를 바꾼다.
$alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'  # 헷갈리는 0 O o 1 l I 는 뺐다(손으로 옮겨 적으므로)
function New-RandomPassword([int]$Length) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $limit = 256 - (256 % $alphabet.Length)   # 치우치지 않게 넘치는 값은 버린다
    $sb = New-Object System.Text.StringBuilder
    $buf = New-Object byte[] 1
    while ($sb.Length -lt $Length) {
        $rng.GetBytes($buf)
        if ($buf[0] -lt $limit) { [void]$sb.Append($alphabet[$buf[0] % $alphabet.Length]) }
    }
    $rng.Dispose()
    return $sb.ToString()
}
$password = New-RandomPassword 24
if ($Reset) {
    $r = Invoke-Exe $Exe @('superuser', 'upsert', $AsEmail, $password, '--dir', $PbData)
} else {
    $r = Invoke-Exe $Exe @('superuser', 'create', $AsEmail, $password, '--dir', $PbData)
}
$savedPassword = $false
if ($r.Code -eq 0) {
    $savedPassword = $true
    Ok "$AsEmail 의 비밀번호를 새로 만들었습니다."
} elseif (-not $Reset -and $r.Out -match 'unique') {
    $password = $null
    Ok "$AsEmail 계정이 이미 있어 그대로 둡니다. 비밀번호를 새로 만들려면: install-server.bat --reset"
} else {
    $password = $null
    Warn "관리자 계정을 만들지 못했습니다: $($r.Out)"
}
if ($savedPassword) {
    if (Test-Path -LiteralPath $PwFile) { Remove-Item -LiteralPath $PwFile -Force }
    $text = @(
        '메뉴판 서버 A/S 관리자 계정 (PocketBase 관리자 화면 http://127.0.0.1:8090/_/ )'
        "이메일:   $AsEmail"
        "비밀번호: $password"
        ('만든 때:  ' + (Get-Date -Format 'yyyy-MM-dd HH:mm') + '  컴퓨터: ' + $env:COMPUTERNAME)
        ''
        'A/S 기록에 옮겨 적은 뒤 이 파일은 지우세요.'
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($PwFile, $text, (New-Object System.Text.UTF8Encoding($true)))
    # 관리자(Administrators)와 SYSTEM만 읽을 수 있게(관리자는 지우기도 가능). 이름 대신 SID를 써서 한글 Windows에서도 같게 동작.
    $ic = Invoke-Exe "$env:SystemRoot\System32\icacls.exe" @($PwFile, '/inheritance:r', '/grant:r', '*S-1-5-32-544:(R,D)', '*S-1-5-18:(R)')
    if ($ic.Code -ne 0) { Warn "비밀번호 파일 권한을 줄이지 못했습니다: $($ic.Out)" }
    else { Ok "비밀번호를 $PwFile 에 저장했습니다(관리자와 SYSTEM만 읽기)." }
}

Step '4. Windows Defender 예외'
try {
    Add-MpPreference -ExclusionPath $Root
    Ok "예외에 넣었습니다: $Root"
} catch {
    Warn 'Defender 예외를 넣지 못했습니다(다른 백신이 켜져 있으면 Defender가 꺼져 있어 그렇습니다). V3·알약을 쓰면 안내서대로 예외를 직접 넣으세요.'
}

Step '5. 방화벽 (같은 공유기 안에서만 8090 열기)'
try {
    Remove-OurFirewallRules
    $null = New-NetFirewallRule -DisplayName "MenuBoard Server TCP $Port" -Group $FirewallGroup `
        -Description '디지털 메뉴판 서버. 같은 망(LocalSubnet)의 TV만 들어오게 한다.' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port `
        -RemoteAddress LocalSubnet -Profile Domain, Private, Public
    $null = New-NetFirewallRule -DisplayName 'MenuBoard Server pocketbase.exe' -Group $FirewallGroup `
        -Description '디지털 메뉴판 서버 프로그램. 같은 망(LocalSubnet)에서 8090만.' `
        -Direction Inbound -Action Allow -Program $Exe -Protocol TCP -LocalPort $Port `
        -RemoteAddress LocalSubnet -Profile Domain, Private, Public
    Ok "TCP $Port 들어오기 허용(모든 프로필, 같은 망만)."
} catch {
    Warn "방화벽 규칙을 만들지 못했습니다: $($_.Exception.Message)"
}

Step '6. 절전 끄기, 업데이트 활성 시간'
foreach ($a in @('standby-timeout-ac', 'hibernate-timeout-ac', 'disk-timeout-ac')) {
    $p = Invoke-Exe "$env:SystemRoot\System32\powercfg.exe" @('/change', $a, '0')
    if ($p.Code -ne 0) { Warn "powercfg /change $a 0 실패: $($p.Out)" }
}
Ok '전원 연결 시 절전·최대 절전·하드디스크 끄기를 "안 함"으로 했습니다.'
try {
    $ux = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
    if (-not (Test-Path $ux)) { New-Item -Path $ux -Force | Out-Null }
    Set-ItemProperty -Path $ux -Name ActiveHoursStart -Value $ActiveHoursStart -Type DWord
    Set-ItemProperty -Path $ux -Name ActiveHoursEnd -Value $ActiveHoursEnd -Type DWord
    Set-ItemProperty -Path $ux -Name SmartActiveHoursState -Value 0 -Type DWord   # '자동으로 조정' 끄기
    $pol = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
    if (-not (Test-Path $pol)) { New-Item -Path $pol -Force | Out-Null }
    Set-ItemProperty -Path $pol -Name SetActiveHours -Value 1 -Type DWord
    Set-ItemProperty -Path $pol -Name ActiveHoursStart -Value $ActiveHoursStart -Type DWord
    Set-ItemProperty -Path $pol -Name ActiveHoursEnd -Value $ActiveHoursEnd -Type DWord
    # 사장님이 로그인해 있는 동안(영업 중)에는 업데이트가 스스로 다시 시작하지 않게(Windows 10 Pro 정책, 점검표 B-17)
    $au = Join-Path $pol 'AU'
    New-Item -Path $au -Force | Out-Null
    Set-ItemProperty -Path $au -Name NoAutoRebootWithLoggedOnUsers -Value 1 -Type DWord
    Ok "업데이트 활성 시간 $ActiveHoursStart 시 ~ $(if ($ActiveHoursEnd -eq 0) { 24 } else { $ActiveHoursEnd }) 시(이 시간과 로그인해 있는 동안에는 업데이트로 다시 시작하지 않음)."
} catch {
    Warn "업데이트 활성 시간을 넣지 못했습니다: $($_.Exception.Message)"
}
$ans = Read-Host '   빠른 시작을 끌까요? 꺼 두면 켤 때마다 서버가 깨끗하게 새로 뜹니다(권장). [Y/n]'
if ($ans -notmatch '^[nN]') {
    try {
        Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -Value 0 -Type DWord
        Ok '빠른 시작을 껐습니다.'
    } catch { Warn "빠른 시작을 끄지 못했습니다: $($_.Exception.Message)" }
} else { Ok '빠른 시작은 그대로 둡니다.' }

Step '7. 자동 실행 작업 등록 (컴퓨터가 켜지면, 로그인 없이, 창 없이)'
$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $psExe `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $RunScript + '"') `
    -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtStartup
$taskUser = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable -MultipleInstances IgnoreNew -DontStopOnIdleEnd -Priority 6
$null = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $taskUser -Settings $settings `
    -Description '디지털 메뉴판 서버(PocketBase :8090). 서버가 꺼지면 run-server.ps1 이 5초 뒤 다시 켠다. 로그: logs 폴더' -Force
Start-ScheduledTask -TaskName $TaskName
Ok "작업 '$TaskName' 을 등록하고 시작했습니다."

Step '8. 서버 응답 확인'
$up = $false
for ($i = 0; $i -lt 30 -and -not $up; $i++) {
    Start-Sleep -Seconds 1
    try {
        $res = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
        if ($res.StatusCode -eq 200) { $up = $true }
    } catch { }
}
if ($up) { Ok "http://127.0.0.1:$Port 에서 서버가 응답합니다." }
else { Warn "30초 안에 서버가 응답하지 않습니다. $Root\logs 의 오늘 로그를 보세요." }

# ---- 결과 ----
Write-Host ''
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host ' TV(보드)에 넣을 서버 주소 (공유기가 준 이 PC의 주소):'
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    ForEach-Object {
        $how = if ($_.PrefixOrigin -eq 'Dhcp') { '자동 받은 주소 - 공유기에서 DHCP 예약을 하세요' } else { '고정 주소' }
        Write-Host ("    {0}:{1}   ({2}, {3})" -f $_.IPAddress, $Port, $_.InterfaceAlias, $how)
    }
Write-Host " 메뉴 수정 화면: http://127.0.0.1:$Port/admin.html"
Write-Host " 메뉴판 화면:    http://127.0.0.1:$Port/?screen=1&zoom=100"
Write-Host '==================================================' -ForegroundColor Cyan
if ($savedPassword) {
    Write-Host ''
    Write-Host ' A/S 관리자 계정 (PocketBase 관리자 화면 /_/ )' -ForegroundColor Yellow
    Write-Host "   이메일:   $AsEmail" -ForegroundColor Yellow
    Write-Host "   비밀번호: $password" -ForegroundColor Yellow
    Write-Host " A/S 기록에 옮겨 적고, 이 파일은 지우세요:" -ForegroundColor Yellow
    Write-Host "   $PwFile" -ForegroundColor Yellow
}
if ($script:Warnings.Count -gt 0) {
    Write-Host ''
    Write-Host " 확인할 것 $($script:Warnings.Count)가지:" -ForegroundColor Yellow
    $script:Warnings | ForEach-Object { Write-Host "   - $_" -ForegroundColor Yellow }
} else {
    Write-Host ''
    Write-Host ' 설치를 마쳤습니다. 이 창을 닫아도 서버는 계속 돕니다.' -ForegroundColor Green
}
