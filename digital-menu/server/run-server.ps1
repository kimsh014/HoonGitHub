# 메뉴판 서버를 계속 켜 두는 반복 스크립트. 작업 스케줄러 작업 "MenuBoardServer"가 SYSTEM 계정으로 창 없이 실행한다.
# - 서버(pocketbase.exe)가 꺼지면 5초 뒤 다시 켠다.
# - 서버 출력은 logs\server-날짜.log 에 남긴다. 하루에 한 파일, 5MB를 넘으면 .1 로 옮기고 새로 쓴다(하루 최대 약 10MB), 14일 지난 로그는 지운다.
# 직접 실행할 일은 없다. 점검할 때는 start-server.bat(창 있음)을 쓰되, 먼저 이 작업을 멈춘다.

$ErrorActionPreference = 'Continue'
$Root    = $PSScriptRoot
$Exe     = Join-Path $Root 'pocketbase.exe'
$LogDir  = Join-Path $Root 'logs'
$MaxLogBytes = 5MB
$KeepDays    = 14
$Utf8 = New-Object System.Text.UTF8Encoding($false)

try { [Console]::OutputEncoding = $Utf8 } catch { }
Set-Location -LiteralPath $Root
if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$script:LogDay = ''

function Remove-OldLogs {
    $limit = (Get-Date).AddDays(-$KeepDays)
    Get-ChildItem -LiteralPath $LogDir -Filter 'server-*.log' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $limit } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Write-Log([string]$Text) {
    try {
        $day = Get-Date -Format 'yyyyMMdd'
        if ($day -ne $script:LogDay) { $script:LogDay = $day; Remove-OldLogs }
        $file = Join-Path $LogDir "server-$day.log"
        if ((Test-Path -LiteralPath $file) -and (Get-Item -LiteralPath $file).Length -gt $MaxLogBytes) {
            $old = Join-Path $LogDir "server-$day.1.log"
            Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
            Move-Item -LiteralPath $file -Destination $old -Force
        }
        $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $Text + "`r`n"
        [System.IO.File]::AppendAllText($file, $line, $Utf8)
    } catch { }
}

# 같은 스크립트가 두 번 돌지 않게 한다(두 번째는 바로 끝남).
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Global\MenuBoardServerRunner', [ref]$created)
if (-not $created) {
    Write-Log '이미 다른 run-server.ps1 이 돌고 있어 이 실행은 끝냅니다.'
    exit 0
}

# 이 폴더의 pocketbase.exe 가 남아 있으면(이전 실행이 강제로 끝난 경우 등) 끄고 시작한다. 안 그러면 8090이 겹친다.
function Stop-OurServer {
    Get-CimInstance Win32_Process -Filter "Name='pocketbase.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -ieq $Exe) } |
        ForEach-Object {
            Write-Log ("남아 있던 서버(PID " + $_.ProcessId + ")를 끕니다.")
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

Write-Log ('---- 반복 스크립트 시작: ' + $Root)
Stop-OurServer

while ($true) {
    if (-not (Test-Path -LiteralPath $Exe)) {
        Write-Log 'pocketbase.exe 가 없습니다. 60초 뒤 다시 봅니다.'
        Start-Sleep -Seconds 60
        continue
    }
    Write-Log '서버를 켭니다: 0.0.0.0:8090'
    & $Exe serve --http '0.0.0.0:8090' `
        --dir (Join-Path $Root 'pb_data') `
        --migrationsDir (Join-Path $Root 'pb_migrations') `
        --hooksDir (Join-Path $Root 'pb_hooks') `
        --publicDir (Join-Path $Root 'pb_public') 2>&1 |
        ForEach-Object { Write-Log ([string]$_) }
    $code = $LASTEXITCODE
    Write-Log ("서버가 꺼졌습니다(종료 코드 $code). 5초 뒤 다시 켭니다.")
    Start-Sleep -Seconds 5
}
