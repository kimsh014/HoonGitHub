# 하드웨어 시험 도우미. run-hw-test.bat 이 관리자 권한으로 부른다(Windows PowerShell 5.1).
# hw-tests.json 의 시험표를 차례로 보여 주고, 기계가 볼 수 있는 것은 직접 검사하고(서버·Windows 설정·TV 원격 관리 API·adb),
# 사람이 봐야 하는 것은 통과/실패를 물어 results\<시각-PC이름>\ 에 run.json·report.md·증거 파일(사진·로그)로 남긴다.
# 사용법은 README.md. 이 파일은 UTF-8(BOM 있음)·CRLF로 저장한다(Windows PowerShell 5.1이 BOM 없는 한글을 깨뜨림).
param(
    [string]$Plan = '',                         # 시험 묶음 번호(hw-tests.json 의 plans.id). 비우면 메뉴에서 고른다
    [string[]]$Only = @(),                      # 항목 번호만 골라 하기. 예: -Only H-25,H-13
    [string]$Server = 'http://127.0.0.1:8090',  # 메뉴판 서버. 다른 노트북에서 돌릴 때 http://POS기주소:8090
    [string]$ServerDir = 'C:\MenuBoard\server', # POS기의 서버 폴더(설치 안내서 기준)
    [string]$TvName = '',                       # TV가 여럿일 때 이름 일부로 고르기(비우면 모두)
    [string]$Adb = '',                          # adb.exe 위치(비우면 찾아봄)
    [int]$AdbPort = 5555,
    [switch]$AutoOnly,                          # 사람 손이 필요 없는 자동 검사만
    [switch]$Resume,                            # 지난 시험 이어 하기(다시 시작한 뒤 자동으로 붙음)
    [string]$Report = '',                       # 결과 폴더를 주면 report.md 만 다시 만든다
    [string]$OutRoot = '',                      # 결과를 둘 곳(기본: 이 폴더의 results)
    [switch]$SelfTest                           # 스크립트 자체 점검(사람에게 묻지 않음, CI용)
)

$ErrorActionPreference = 'Continue'
$Here = $PSScriptRoot
$Utf8 = New-Object System.Text.UTF8Encoding($false)
if (-not $OutRoot) { $OutRoot = Join-Path $Here 'results' }
$Server = $Server.TrimEnd('/')
$script:IsWindows = ($env:OS -eq 'Windows_NT')
$script:Interactive = -not $SelfTest
$script:Answers = New-Object System.Collections.Queue   # SelfTest 때 사람 대신 넣는 답
if ($env:HWTEST_ANSWERS) { foreach ($a in $env:HWTEST_ANSWERS.Split('|')) { $script:Answers.Enqueue($a) } }

# ───────────────────────── 화면 출력·묻기 ─────────────────────────

function Say([string]$t, [string]$c = 'Gray') { Write-Host $t -ForegroundColor $c }
function Title([string]$t) { Write-Host ''; Write-Host ('━━ ' + $t + ' ') -ForegroundColor Cyan }

function Ask([string]$prompt, [string]$default = '') {
    if ($script:Answers.Count -gt 0) {
        $a = [string]$script:Answers.Dequeue(); Say "$prompt $a" 'DarkGray'
        if ($a -eq '') { return $default }
        return $a
    }
    if (-not $script:Interactive) { return $default }
    $a = Read-Host $prompt
    if ($null -eq $a -or $a -eq '') { return $default }
    return $a.Trim()
}

function Ask-Secret([string]$prompt) {
    if ($env:HWTEST_PASSWORD) { return (ConvertTo-SecureString $env:HWTEST_PASSWORD -AsPlainText -Force) }
    if (-not $script:Interactive) { return $null }
    return (Read-Host $prompt -AsSecureString)
}

function Plain([Security.SecureString]$s) {
    if ($null -eq $s) { return '' }
    $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}

function Is-Admin {
    if (-not $script:IsWindows) { return $false }
    $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function UnixNow { return [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) }

function Res([string]$status, [string]$detail, $value = $null, $files = @()) {
    return @{ status = $status; detail = $detail; value = $value; files = @($files) }
}

# ───────────────────────── 결과 저장 ─────────────────────────

$script:Run = $null
$script:RunDir = ''
$script:EvDir = ''

function New-Run {
    $id = (Get-Date -Format 'yyyyMMdd-HHmm') + '-' + $env:COMPUTERNAME
    $script:RunDir = Join-Path $OutRoot $id
    $script:EvDir = Join-Path $script:RunDir 'evidence'
    New-Item -ItemType Directory -Path $script:EvDir -Force | Out-Null
    $script:Run = [pscustomobject]@{
        id = $id; version = 1; state = 'running'
        started = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); finished = ''
        tester = ''; computer = $env:COMPUTERNAME; server = $Server; serverDir = $ServerDir
        queue = @(); pc = $null; tvs = @(); notes = @()
        results = @()
    }
}

function Load-Run([string]$dir) {
    $file = Join-Path $dir 'run.json'
    $script:Run = [IO.File]::ReadAllText($file, $Utf8) | ConvertFrom-Json
    $script:RunDir = $dir
    $script:EvDir = Join-Path $dir 'evidence'
    New-Item -ItemType Directory -Path $script:EvDir -Force | Out-Null
    if ($null -eq $script:Run.results) { $script:Run.results = @() }
}

function Save-Run {
    if (-not $script:RunDir) { return }
    $json = $script:Run | ConvertTo-Json -Depth 8
    $tmp = Join-Path $script:RunDir 'run.json.tmp'
    [IO.File]::WriteAllText($tmp, $json, $Utf8)
    Move-Item -LiteralPath $tmp -Destination (Join-Path $script:RunDir 'run.json') -Force
}

function Find-Result([string]$item, [string]$step) {
    foreach ($r in @($script:Run.results)) { if ($r.item -eq $item -and $r.step -eq $step) { return $r } }
    return $null
}

function Add-Result($item, $step, [hashtable]$r, [string]$memo = '') {
    $old = Find-Result $item.id $step.n
    $rows = @($script:Run.results | Where-Object { -not ($_.item -eq $item.id -and $_.step -eq $step.n) })
    $row = [pscustomobject]@{
        item = $item.id; step = $step.n; title = $item.title
        do = [string]$step.do; expect = [string]$step.expect; auto = [string]$step.auto
        status = $r.status; detail = [string]$r.detail; value = $r.value
        files = @($r.files | Where-Object { $_ }); memo = $memo
        at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    }
    if ($old -and $old.status -eq 'pending' -and $old.files) { $row.files = @($old.files) + @($row.files) }
    $script:Run.results = @($rows) + @($row)
    Save-Run
    return $row
}

function Ev([string]$name) {
    $safe = ($name -replace '[\\/:*?"<>| ]', '_')
    return (Join-Path $script:EvDir $safe)
}

function Rel([string]$path) {
    if (-not $path) { return '' }
    return $path.Substring($script:RunDir.Length).TrimStart('\', '/').Replace('\', '/')
}

# ───────────────────────── 서버 API ─────────────────────────

$script:Token = ''
$script:AuthKind = ''          # users | _superusers
$script:AuthId = ''
$script:Login = $null          # @{ kind; email; pw(SecureString) } — 메모리에만 둔다
$script:StoreId = ''
$script:ClockOffset = 0        # 서버 시각 - 이 PC 시각(초)

function Http([string]$method, [string]$path, $body = $null, [int]$timeout = 10, [switch]$NoAuth, [string]$OutFile = '') {
    $url = if ($path -match '^https?://') { $path } else { $Server + $path }
    $headers = @{}
    if ($script:Token -and -not $NoAuth) { $headers['Authorization'] = $script:Token }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $res = @{ ok = $false; code = 0; body = ''; json = $null; ms = 0; error = ''; date = $null }
    try {
        $p = @{ Uri = $url; Method = $method; Headers = $headers; TimeoutSec = $timeout; UseBasicParsing = $true }
        if ($null -ne $body) {
            $p['Body'] = $Utf8.GetBytes(($body | ConvertTo-Json -Depth 6 -Compress))
            $p['ContentType'] = 'application/json; charset=utf-8'
        }
        if ($OutFile) { $p['OutFile'] = $OutFile; $p['PassThru'] = $true }
        $w = Invoke-WebRequest @p
        $res.code = [int]$w.StatusCode
        $res.ok = ($res.code -ge 200 -and $res.code -lt 300)
        if (-not $OutFile) {
            if ($w.RawContentStream) { $res.body = $Utf8.GetString($w.RawContentStream.ToArray()) } else { $res.body = [string]$w.Content }
        }
        if ($w.Headers['Date']) { $res.date = [DateTimeOffset]::Parse([string]$w.Headers['Date']) }
    } catch {
        $res.error = $_.Exception.Message
        $resp = $null
        try { $resp = $_.Exception.Response } catch { }
        if ($resp) {
            try { $res.code = [int]$resp.StatusCode } catch { }
            try {
                $sr = New-Object IO.StreamReader($resp.GetResponseStream(), $Utf8)
                $res.body = $sr.ReadToEnd(); $sr.Close()
            } catch { }
        }
        if (-not $res.body -and $_.ErrorDetails -and $_.ErrorDetails.Message) { $res.body = [string]$_.ErrorDetails.Message }
    }
    $sw.Stop()
    $res.ms = [int]$sw.ElapsedMilliseconds
    $trim = ([string]$res.body).TrimStart()
    if ($trim.StartsWith('{') -or $trim.StartsWith('[')) {
        try { $res.json = $res.body | ConvertFrom-Json } catch { }
    }
    if ($res.date) { $script:ClockOffset = [int64]($res.date.ToUnixTimeSeconds() - (UnixNow)) }
    return $res
}

function ServerNow { return (UnixNow) + $script:ClockOffset }

function Server-Up { $h = Http 'GET' '/api/health' -timeout 3 -NoAuth; return $h.ok }

function Auth-With([string]$kind, [string]$email, [Security.SecureString]$pw) {
    $r = Http 'POST' "/api/collections/$kind/auth-with-password" @{ identity = $email; password = (Plain $pw) } -NoAuth
    if (-not $r.ok -or -not $r.json.token) { return $false }
    $script:Token = [string]$r.json.token
    $script:AuthKind = $kind
    $script:AuthId = [string]$r.json.record.id
    if ($kind -eq 'users' -and $r.json.record.store) { $script:StoreId = [string]$r.json.record.store }
    $script:Login = @{ kind = $kind; email = $email; pw = $pw }
    return $true
}

# 매장 계정(사장님) 또는 A/S 관리자로 로그인한다. 비밀번호는 파일에 남기지 않는다.
function Ensure-Login([switch]$Superuser) {
    if ($script:Token -and (-not $Superuser -or $script:AuthKind -eq '_superusers')) { return $true }
    if ($script:Login -and (-not $Superuser -or $script:Login.kind -eq '_superusers')) {
        if (Auth-With $script:Login.kind $script:Login.email $script:Login.pw) { return $true }
    }
    if ($env:HWTEST_EMAIL -and -not $Superuser) {
        $kind = if ($env:HWTEST_KIND) { $env:HWTEST_KIND } else { 'users' }
        if (Auth-With $kind $env:HWTEST_EMAIL (Ask-Secret '')) { return $true }
    }
    if (-not $script:Interactive) { return $false }
    for ($i = 0; $i -lt 3; $i++) {
        if ($Superuser) {
            Say '   A/S 관리자 계정이 필요합니다(설치 때 A/S 기록지에 적은 as@poswing.local 과 비밀번호).' 'Yellow'
            $email = Ask '   A/S 관리자 이메일 [as@poswing.local]' 'as@poswing.local'
            $kind = '_superusers'
        } else {
            $email = Ask '   매장 계정(사장님) 이메일 (A/S 관리자로 하려면 as@poswing.local)'
            if (-not $email) { return $false }
            $kind = if ($email -like 'as@*') { '_superusers' } else { 'users' }
        }
        $pw = Ask-Secret '   비밀번호(화면에 안 보임)'
        if (Auth-With $kind $email $pw) { Say "   로그인했습니다($kind)." 'Green'; return $true }
        Say '   로그인 실패. 이메일·비밀번호를 확인하세요.' 'Red'
    }
    return $false
}

function Api([string]$method, [string]$path, $body = $null, [int]$timeout = 15) {
    $r = Http $method $path $body $timeout
    if ($r.code -eq 401 -and $script:Login) {
        if (Auth-With $script:Login.kind $script:Login.email $script:Login.pw) { $r = Http $method $path $body $timeout }
    }
    return $r
}

function Get-StoreId {
    if ($script:StoreId) { return $script:StoreId }
    $r = Http 'GET' '/api/menuboard/store' -NoAuth
    if ($r.ok -and $r.json.id) { $script:StoreId = [string]$r.json.id }
    return $script:StoreId
}

function Get-Tvs {
    $r = Api 'GET' '/api/collections/devices/records?perPage=200&sort=name'
    if (-not $r.ok) { throw "TV 목록을 못 읽었습니다(HTTP $($r.code)): $($r.body)" }
    $now = ServerNow
    $list = @()
    foreach ($d in @($r.json.items)) {
        if ($TvName -and ([string]$d.name).IndexOf($TvName, [StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
        $age = $now - [int64]$d.last_seen
        $d | Add-Member -NotePropertyName age -NotePropertyValue $age -Force
        $d | Add-Member -NotePropertyName online -NotePropertyValue ($age -le 45) -Force
        $list += $d
    }
    return ,$list
}

function Tv-Line($d) {
    $rp = $d.reported
    $s = "$($d.name) [$($d.ip)] 버전 $($d.version), "
    if ($d.online) { $s += "켜짐($($d.age)초 전 보고)" } else { $s += "꺼짐/안 보임($($d.age)초 전 마지막)" }
    if ($rp) {
        $s += ", 화면 $($rp.screen), 배율 $($rp.zoom), 방향 $($rp.rotation), 밝기 $($rp.brightness), $($rp.width)x$($rp.height), adb $($rp.adb)"
        if ($rp.note) { $s += ", 알림: $($rp.note)" }
        if ($rp.usb) { $s += ", USB: $($rp.usb)" }
    }
    return $s
}

# ───────────────────────── adb ─────────────────────────

$script:AdbExe = ''
$script:AdbSerial = ''
$script:AdbOpened = @()    # 이 시험이 연 A/S 연결(끝날 때 닫기)

function Find-Adb {
    $c = @()
    if ($Adb) { $c += $Adb }
    $c += (Join-Path $Here 'tools\platform-tools\adb.exe')
    $c += (Join-Path $Here '..\board-app\platform-tools\adb.exe')
    if ($env:LOCALAPPDATA) { $c += (Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe') }
    foreach ($p in $c) { if ($p -and (Test-Path -LiteralPath $p)) { return (Resolve-Path -LiteralPath $p).Path } }
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return ''
}

function Adb-Run([string[]]$a, [int]$timeoutSec = 30) {
    if (-not $script:AdbExe) { return @{ code = -1; out = 'adb 없음' } }
    $old = [Console]::OutputEncoding
    try {
        try { [Console]::OutputEncoding = $Utf8 } catch { }
        $ea = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        $out = (& $script:AdbExe @a 2>&1 | ForEach-Object { [string]$_ }) -join "`n"
        $ErrorActionPreference = $ea
        return @{ code = $LASTEXITCODE; out = $out }
    } finally { try { [Console]::OutputEncoding = $old } catch { } }
}

function Sh([string]$cmd) {
    $r = Adb-Run @('-s', $script:AdbSerial, 'shell', $cmd)
    return ([string]$r.out).Trim()
}

function Adb-Devices {
    $r = Adb-Run @('devices')
    $list = @()
    foreach ($line in ([string]$r.out -split "`n")) {
        if ($line -match '^(\S+)\s+(device|unauthorized|offline)\s*$') { $list += [pscustomobject]@{ serial = $Matches[1]; state = $Matches[2] } }
    }
    return ,$list
}

function Ensure-Adb([switch]$Quiet) {
    if (-not $script:AdbExe) { if (-not $Quiet) { Say '   adb.exe 를 찾지 못했습니다(README의 준비물 참고).' 'Yellow' }; return $false }
    if ($script:AdbSerial) {
        $st = Adb-Run @('-s', $script:AdbSerial, 'get-state')
        if (([string]$st.out).Trim() -eq 'device') { return $true }
    }
    $devs = @(Adb-Devices | Where-Object { $_.state -eq 'device' })
    if ($devs.Count -eq 1) { $script:AdbSerial = $devs[0].serial; return $true }
    if ($devs.Count -gt 1) {
        Say ('   adb 기기가 여럿입니다: ' + (($devs | ForEach-Object { $_.serial }) -join ', ')) 'Yellow'
        $s = Ask '   쓸 기기(일련번호 또는 주소:포트)' $devs[0].serial
        $script:AdbSerial = $s; return $true
    }
    if ($Quiet) { return $false }
    Say '   adb로 붙은 TV가 없습니다. TV 앱이 평소 adb를 잠가 둡니다.' 'Yellow'
    $a = Ask '   A/S 연결을 30분 열고 네트워크로 붙을까요? [Y/n]' 'y'
    if ($a -match '^[nN]') { return $false }
    $r = & $script:Checks['tv.openAdb'] ([pscustomobject]@{ minutes = 30 })
    Say ('   ' + $r.detail)
    return ($r.status -eq 'pass')
}

# ───────────────────────── Windows 도우미 ─────────────────────────

function Native([string]$exe, [string[]]$a) {
    $ea = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $out = (& $exe @a 2>&1 | ForEach-Object { [string]$_ }) -join "`n"; return @{ code = $LASTEXITCODE; out = $out } }
    catch { return @{ code = -1; out = $_.Exception.Message } }
    finally { $ErrorActionPreference = $ea }
}

function Server-IsLocal { return ($Server -match '://(127\.0\.0\.1|localhost)(:|/|$)') }

function Pb-Processes {
    if (-not $script:IsWindows) { return @() }
    return @(Get-CimInstance Win32_Process -Filter "Name='pocketbase.exe'" -ErrorAction SilentlyContinue)
}

function Shot-Pos([string]$name) {
    if (-not $script:IsWindows) { return '' }
    try {
        Add-Type -AssemblyName System.Windows.Forms, System.Drawing
        $b = [Windows.Forms.SystemInformation]::VirtualScreen
        $bmp = New-Object Drawing.Bitmap $b.Width, $b.Height
        $g = [Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
        $file = Ev ($name + '-pos.png')
        $bmp.Save($file, [Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        return $file
    } catch { Say "   POS 화면을 찍지 못했습니다: $($_.Exception.Message)" 'Yellow'; return '' }
}

function Pick-Tv([string]$why) {
    $tvs = @(Get-Tvs)
    if ($tvs.Count -eq 0) { return $null }
    if ($tvs.Count -eq 1) { return $tvs[0] }
    Say "   TV가 $($tvs.Count)대입니다. $why"
    for ($i = 0; $i -lt $tvs.Count; $i++) { Say ("   [{0}] {1}" -f ($i + 1), (Tv-Line $tvs[$i])) }
    $n = Ask '   번호' '1'
    $k = 0; if (-not [int]::TryParse($n, [ref]$k) -or $k -lt 1 -or $k -gt $tvs.Count) { $k = 1 }
    return $tvs[$k - 1]
}

# TV의 다음 보고(지금 이후)를 기다린다.
function Wait-Report([string]$id, [int64]$after, [int]$maxSec) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $maxSec) {
        $r = Api 'GET' "/api/collections/devices/records/$id"
        if ($r.ok -and [int64]$r.json.last_seen -gt $after) { return $r.json }
        Start-Sleep -Seconds 3
    }
    return $null
}

# ───────────────────────── 자동 검사 목록 ─────────────────────────
# 각 검사는 인자($a, hw-tests.json 의 args)를 받아 R(status, detail, value, files)를 돌려준다.
# status: pass 통과 / fail 실패 / skip 못 함(이유를 detail에) / info 기록만

$script:Checks = @{}

$script:Checks['pc.info'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $dv = ''
    try { $dv = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop).DisplayVersion } catch { }
    $bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue
    $free = [math]::Round($disk.FreeSpace / 1GB, 1)
    $v = [pscustomobject]@{
        os = $os.Caption; build = $os.BuildNumber; release = $dv; cpu = $cpu
        ramGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1); freeRamGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
        diskFreeGB = $free; bios = if ($bios) { "$($bios.Manufacturer) $($bios.SMBIOSBIOSVersion)" } else { '' }
        lastBoot = $os.LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss')
    }
    $d = "$($v.os) $($v.release) (빌드 $($v.build)), $($v.cpu), 메모리 $($v.ramGB)GB(남음 $($v.freeRamGB)GB), C 빈 공간 $($free)GB"
    if ($free -lt 10) { return (Res 'fail' "$d — C 빈 공간이 10GB보다 적음" $v) }
    return (Res 'info' $d $v)
}

$script:Checks['build.apk'] = {
    param($a)
    $apk = Join-Path $Here '..\board-app\build\menuboard-player.apk'
    $json = Join-Path $Here '..\board-app\build\updates\board-app.json'
    if (-not (Test-Path -LiteralPath $apk)) { return (Res 'fail' "APK가 없습니다: $apk (build.sh 를 먼저 실행)") }
    $f = Get-Item -LiteralPath $apk
    $sha = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLower()
    $d = "menuboard-player.apk $([math]::Round($f.Length / 1MB, 2))MB, 만든 시각 $($f.LastWriteTime.ToString('MM-dd HH:mm')), sha256 $($sha.Substring(0, 12))…"
    if (-not (Test-Path -LiteralPath $json)) { return (Res 'fail' "$d — updates\board-app.json 이 없음") }
    $j = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $json).Path, $Utf8) | ConvertFrom-Json
    $d += ", 버전 $($j.versionName)(코드 $($j.versionCode))"
    $copy = Ev 'board-app.json'
    Copy-Item -LiteralPath $json -Destination $copy -Force
    if ($j.sha256 -ne $sha) { return (Res 'fail' "$d — board-app.json 의 sha256 이 APK와 다름" $j @($copy)) }
    return (Res 'pass' $d $j @($copy))
}

$script:Checks['server.health'] = {
    param($a)
    $bad = @(); $ms = @()
    foreach ($p in @('/api/health', '/admin.html', '/devices.html', '/?screen=1')) {
        $r = Http 'GET' $p -timeout 5 -NoAuth
        $ms += "$p $($r.code) $($r.ms)ms"
        if (-not $r.ok) { $bad += "$p → $($r.code) $($r.error)" }
    }
    $win = @()
    if ($script:IsWindows -and (Server-IsLocal)) {
        $win = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -match 'start-server\.bat' })
    }
    $d = ($ms -join ', ')
    if ($bad.Count) { return (Res 'fail' ("응답 안 함: " + ($bad -join '; '))) }
    if ($win.Count) { return (Res 'fail' "$d — start-server.bat 창이 켜져 있음(작업 스케줄러 서버와 겹침)") }
    return (Res 'pass' $d)
}

$script:Checks['server.lan'] = {
    param($a)
    if (-not (Server-IsLocal)) {
        $r = Http 'GET' '/api/health' -timeout 5 -NoAuth
        if ($r.ok) { return (Res 'pass' "$Server 응답 $($r.ms)ms") } else { return (Res 'fail' "$Server 응답 없음: $($r.error)") }
    }
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    $port = ([uri]$Server).Port
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.InterfaceAlias -notmatch 'vEthernet|Loopback|VirtualBox|VMware' })
    if (-not $ips.Count) { return (Res 'fail' '공유기에 붙은 IPv4 주소가 없음') }
    $ok = @(); $bad = @()
    foreach ($ip in $ips) {
        $r = Http 'GET' "http://$($ip.IPAddress):$port/api/health" -timeout 4 -NoAuth
        $prof = ''
        try { $prof = (Get-NetConnectionProfile -InterfaceIndex $ip.InterfaceIndex -ErrorAction Stop).NetworkCategory } catch { }
        $s = "$($ip.IPAddress)($($ip.InterfaceAlias), $prof)"
        if ($r.ok) { $ok += $s } else { $bad += $s }
    }
    $d = "응답: " + ($(if ($ok.Count) { $ok -join ', ' } else { '없음' }))
    if ($bad.Count) { $d += " / 응답 안 함: " + ($bad -join ', ') }
    $d += " — TV에 넣을 주소: " + (($ok | ForEach-Object { ($_ -split '\(')[0] + ":$port" }) -join ', ')
    if ($ok.Count) { return (Res 'pass' $d) } else { return (Res 'fail' $d) }
}

$script:Checks['server.task'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    $t = Get-ScheduledTask -TaskName 'MenuBoardServer' -ErrorAction SilentlyContinue
    if (-not $t) { return (Res 'fail' "작업 스케줄러에 'MenuBoardServer' 작업이 없음(install-server.bat 실행 전이거나 실패)") }
    $info = Get-ScheduledTaskInfo -TaskName 'MenuBoardServer' -ErrorAction SilentlyContinue
    $user = [string]$t.Principal.UserId
    $trig = ($t.Triggers | ForEach-Object { $_.CimClass.CimClassName -replace 'MSFT_Task', '' -replace 'Trigger', '' }) -join ','
    $procs = @(Pb-Processes)
    $owners = @()
    foreach ($p in $procs) {
        $o = Invoke-CimMethod -InputObject $p -MethodName GetOwner -ErrorAction SilentlyContinue
        $owners += "PID $($p.ProcessId) $($o.User) $($p.ExecutablePath)"
    }
    $d = "상태 $($t.State), 계정 $user, 시작 조건 $trig, 마지막 실행 $($info.LastRunTime) 결과 0x{0:X}" -f [int64]$info.LastTaskResult
    $d += "; pocketbase.exe: " + ($(if ($owners.Count) { $owners -join ' / ' } else { '없음' }))
    $fails = @()
    if ([string]$t.State -ne 'Running') { $fails += '작업이 실행 중이 아님' }
    if ($user -notmatch 'SYSTEM|S-1-5-18') { $fails += 'SYSTEM 계정이 아님' }
    if ($trig -notmatch 'Boot') { $fails += '컴퓨터 시작 때 실행 조건 없음' }
    if (-not $procs.Count) { $fails += 'pocketbase.exe 가 돌지 않음' }
    elseif (-not ($owners -match ' SYSTEM ')) { $fails += 'pocketbase.exe 가 SYSTEM으로 돌지 않음' }
    if ($procs.Count -gt 1) { $fails += "pocketbase.exe 가 $($procs.Count)개" }
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', '))) }
    return (Res 'pass' $d)
}

$script:Checks['server.killRecover'] = {
    param($a)
    if (-not $script:IsWindows -or -not (Server-IsLocal)) { return (Res 'skip' 'POS기에서만 할 수 있음') }
    $max = if ($a -and $a.max) { [int]$a.max } else { 15 }
    $procs = @(Pb-Processes)
    if (-not $procs.Count) { return (Res 'fail' 'pocketbase.exe 가 돌고 있지 않음') }
    $ans = Ask '   지금 서버를 강제로 끕니다. 영업 중이 아니죠? [y/N]' 'n'
    if ($script:Interactive -and $ans -notmatch '^[yY]') { return (Res 'skip' '사람이 취소함') }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
    $back = $false
    while ($sw.Elapsed.TotalSeconds -lt ($max + 60)) {
        if (Server-Up) { $back = $true; break }
        Start-Sleep -Milliseconds 500
    }
    $sec = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    if (-not $back) { return (Res 'fail' "$($max + 60)초가 지나도 다시 뜨지 않음" $sec) }
    $new = @(Pb-Processes | ForEach-Object { $_.ProcessId }) -join ','
    if ($sec -gt $max) { return (Res 'fail' "$sec 초 만에 다시 응답(기준 $max 초), 새 PID $new" $sec) }
    return (Res 'pass' "$sec 초 만에 다시 응답, 새 PID $new" $sec)
}

$script:Checks['server.waitUp'] = {
    param($a)
    $max = if ($a -and $a.max) { [int]$a.max } else { 240 }
    $t0 = $script:StepStart
    if (-not $t0) { $t0 = [Diagnostics.Stopwatch]::StartNew() }
    $sawDown = -not (Server-Up)
    Say "   서버가 꺼졌다 다시 뜨기를 기다립니다(최대 $($max + 300)초, Ctrl+C로 멈춤)…"
    while ($t0.Elapsed.TotalSeconds -lt ($max + 300)) {
        $up = Server-Up
        if (-not $up) { $sawDown = $true }
        elseif ($sawDown) {
            $sec = [math]::Round($t0.Elapsed.TotalSeconds)
            if ($sec -le $max) { return (Res 'pass' "$sec 초 만에 서버 응답" $sec) }
            return (Res 'fail' "$sec 초 만에 서버 응답(기준 $max 초)" $sec)
        }
        if (-not $sawDown -and $t0.Elapsed.TotalSeconds -gt 90) { return (Res 'fail' '90초 동안 서버가 꺼지지 않았음(전원이 실제로 끊겼는지 확인)') }
        Start-Sleep -Seconds 2
    }
    return (Res 'fail' "$($max + 300)초 안에 서버가 다시 뜨지 않음")
}

$script:Checks['win.bootToServer'] = {
    param($a)
    if (-not $script:IsWindows -or -not (Server-IsLocal)) { return (Res 'skip' 'POS기에서만 할 수 있음') }
    $max = if ($a -and $a.max) { [int]$a.max } else { 120 }
    $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
    $start = $null; $how = ''
    $log = Join-Path $ServerDir ("logs\server-" + $boot.ToString('yyyyMMdd') + '.log')
    if (Test-Path -LiteralPath $log) {
        foreach ($line in [IO.File]::ReadAllLines($log, $Utf8)) {
            if ($line -match '^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+서버를 켭니다') {
                $t = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
                if ($t -ge $boot.AddSeconds(-5)) { $start = $t; $how = '서버 로그'; break }
            }
        }
    }
    if (-not $start) {
        $p = Pb-Processes | Sort-Object CreationDate | Select-Object -First 1
        if ($p) { $start = $p.CreationDate; $how = 'pocketbase.exe 시작 시각(로그 없음)' }
    }
    $up = Server-Up
    if (-not $start) { return (Res 'fail' "켠 시각 $($boot.ToString('HH:mm:ss')), 서버가 아직 시작되지 않음") }
    $sec = [math]::Round(($start - $boot).TotalSeconds)
    $d = "Windows 켜짐 $($boot.ToString('HH:mm:ss')) → 서버 시작 $($start.ToString('HH:mm:ss')) = $sec 초($how), 지금 응답 $up"
    $copy = ''
    if (Test-Path -LiteralPath $log) { $copy = Ev ('server-log-' + $boot.ToString('yyyyMMdd') + '.log'); Copy-Item -LiteralPath $log -Destination $copy -Force }
    if ($sec -gt $max -or -not $up) { return (Res 'fail' "$d (기준 $max 초)" $sec @($copy)) }
    return (Res 'pass' $d $sec @($copy))
}

$script:Checks['win.firewall'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    $rules = @(Get-NetFirewallRule -Group 'MenuBoard' -ErrorAction SilentlyContinue)
    if (-not $rules.Count) { return (Res 'fail' "방화벽에 'MenuBoard' 규칙이 없음(설치 묶음 실행 전, 또는 start-server.bat 때 Windows가 묻는 창으로만 열림)") }
    $desc = @(); $fails = @()
    foreach ($r in $rules) {
        $pf = $r | Get-NetFirewallPortFilter; $af = $r | Get-NetFirewallAddressFilter
        $desc += "$($r.DisplayName): $($r.Direction)/$($r.Action)/사용 $($r.Enabled)/포트 $($pf.LocalPort)/원격 $($af.RemoteAddress -join ',')/프로필 $($r.Profile)"
        if ([string]$r.Enabled -ne 'True') { $fails += "$($r.DisplayName) 꺼짐" }
        if (($af.RemoteAddress -join ',') -notmatch 'LocalSubnet') { $fails += "$($r.DisplayName) 원격 주소가 같은 망(LocalSubnet)으로 제한되지 않음" }
        $prof = [string]$r.Profile
        if ($prof -ne 'Any' -and -not ($prof -match 'Domain' -and $prof -match 'Private' -and $prof -match 'Public')) { $fails += "$($r.DisplayName) 프로필이 $prof (공용 망에서 막힘, B-5)" }
    }
    $exe = Join-Path $ServerDir 'pocketbase.exe'
    $blocks = @(Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | Where-Object { $_.Program -and $_.Program -ieq $exe } |
        Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.Action -eq 'Block' -and [string]$_.Enabled -eq 'True' })
    if ($blocks.Count) { $fails += "pocketbase.exe 차단 규칙 $($blocks.Count)개(처음 실행 때 '취소'를 눌러 생김)" }
    $d = $desc -join ' | '
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', '))) }
    return (Res 'pass' $d)
}

function PowerIndex([string]$sub, [string]$setting) {
    $r = Native "$env:SystemRoot\System32\powercfg.exe" @('/query', 'SCHEME_CURRENT', $sub, $setting)
    $m = [regex]::Matches([string]$r.out, '0x[0-9a-fA-F]{8}')
    if ($m.Count -lt 2) { return $null }
    return [Convert]::ToInt64($m[$m.Count - 2].Value, 16)    # 끝에서 두 번째 = AC(전원 연결), 마지막 = DC(배터리)
}

$script:Checks['win.power'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    $s = PowerIndex 'SUB_SLEEP' 'STANDBYIDLE'; $h = PowerIndex 'SUB_SLEEP' 'HIBERNATEIDLE'; $k = PowerIndex 'SUB_DISK' 'DISKIDLE'
    $fast = $null
    try { $fast = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -ErrorAction Stop).HiberbootEnabled } catch { }
    $d = "절전 $s 초, 최대 절전 $h 초, 디스크 끄기 $k 초(전원 연결, 0 = 안 함), 빠른 시작 $fast"
    $fails = @()
    if ($s -ne 0) { $fails += '절전이 켜져 있음' }
    if ($null -ne $h -and $h -ne 0) { $fails += '최대 절전이 켜져 있음' }
    if ($k -ne 0) { $fails += '하드디스크 끄기가 켜져 있음' }
    if ($fast -ne 0) { $fails += '빠른 시작이 켜져 있음' }
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', '))) }
    return (Res 'pass' $d)
}

$script:Checks['win.updateHours'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    function RegVal($p, $n) { try { return (Get-ItemProperty -Path $p -Name $n -ErrorAction Stop).$n } catch { return $null } }
    $ux = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
    $pol = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
    $s = RegVal $ux 'ActiveHoursStart'; $e = RegVal $ux 'ActiveHoursEnd'
    $ps = RegVal $pol 'ActiveHoursStart'; $pe = RegVal $pol 'ActiveHoursEnd'; $set = RegVal $pol 'SetActiveHours'
    $nar = RegVal (Join-Path $pol 'AU') 'NoAutoRebootWithLoggedOnUsers'
    $d = "사용 시간 $s~$e 시, 정책 $ps~$pe 시(SetActiveHours=$set), 로그인 중 자동 재시작 안 함=$nar"
    $fails = @()
    if ($set -ne 1 -or $ps -ne 7 -or $pe -ne 0) { $fails += '정책 사용 시간이 7~24시가 아님' }
    if ($nar -ne 1) { $fails += '로그인 중 자동 재시작 막기가 없음' }
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', '))) }
    return (Res 'pass' $d)
}

$script:Checks['win.defender'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    try { $m = Get-MpPreference -ErrorAction Stop } catch { return (Res 'info' "Defender 설정을 읽지 못함(다른 백신이 켜져 있으면 정상): $($_.Exception.Message)") }
    $ex = @($m.ExclusionPath)
    $hit = @($ex | Where-Object { $_ -and $ServerDir.TrimEnd('\') -ieq ([string]$_).TrimEnd('\') })
    if ($hit.Count) { return (Res 'pass' "검사 예외에 $ServerDir 있음") }
    if ($ex.Count -eq 1 -and [string]$ex[0] -match 'N/A|관리자') { return (Res 'skip' '관리자 권한이 없어 예외 목록을 못 읽음') }
    return (Res 'fail' "검사 예외에 $ServerDir 이 없음")
}

$script:Checks['win.antivirus'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    $av = @(Get-CimInstance -Namespace 'root/SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction SilentlyContinue)
    if (-not $av.Count) { return (Res 'info' '보안 센터에 등록된 백신 없음(서버 Windows이거나 읽기 실패)') }
    $list = $av | ForEach-Object { "$($_.displayName)(상태 0x{0:X})" -f [int64]$_.productState }
    return (Res 'info' ('백신: ' + ($list -join ', ')) ($av | ForEach-Object { $_.displayName }))
}

$script:Checks['win.folderAcl'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    if (-not (Test-Path -LiteralPath $ServerDir)) { return (Res 'fail' "서버 폴더가 없음: $ServerDir") }
    $broad = @('S-1-5-32-545', 'S-1-5-11', 'S-1-1-0', 'S-1-5-4')   # Users, Authenticated Users, Everyone, Interactive
    $write = [Security.AccessControl.FileSystemRights]'WriteData, AppendData, Delete, ChangePermissions, TakeOwnership, WriteAttributes'
    $bad = @(); $seen = @()
    foreach ($p in @($ServerDir, (Join-Path $ServerDir 'run-server.ps1'), (Join-Path $ServerDir 'pocketbase.exe'), (Join-Path $ServerDir 'pb_data\data.db'))) {
        if (-not (Test-Path -LiteralPath $p)) { continue }
        foreach ($ace in (Get-Acl -LiteralPath $p).Access) {
            $sid = ''
            try { $sid = $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { $sid = [string]$ace.IdentityReference }
            if ($broad -contains $sid -and $ace.AccessControlType -eq 'Allow' -and (($ace.FileSystemRights -band $write) -ne 0)) {
                $bad += "$(Split-Path $p -Leaf): $($ace.IdentityReference) $($ace.FileSystemRights)"
            }
            if ($p -eq $ServerDir) { $seen += "$($ace.IdentityReference)=$($ace.FileSystemRights)" }
        }
    }
    $copy = Ev 'icacls-server.txt'
    [IO.File]::WriteAllText($copy, (Native "$env:SystemRoot\System32\icacls.exe" @($ServerDir)).out, $Utf8)
    if ($bad.Count) { return (Res 'fail' ('일반 사용자가 쓸 수 있음: ' + ($bad -join '; ')) $null @($copy)) }
    return (Res 'pass' ('폴더 권한: ' + ($seen -join ', ')) $null @($copy))
}

$script:Checks['win.clock'] = {
    param($a)
    $parts = @(); $fails = @()
    $parts += "이 PC $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ($([TimeZoneInfo]::Local.Id))"
    $h = Http 'GET' '/api/health' -timeout 4 -NoAuth
    if ($h.date) {
        $diff = $h.date.ToUnixTimeSeconds() - (UnixNow)
        $parts += "서버와 차이 $diff 초"
        if ([math]::Abs($diff) -gt 60) { $fails += '서버와 60초 넘게 차이' }
    }
    if ($script:IsWindows) {
        $w = Native "$env:SystemRoot\System32\w32tm.exe" @('/query', '/status')
        $copy = Ev 'w32tm-status.txt'; [IO.File]::WriteAllText($copy, $w.out, $Utf8)
    }
    if (Ensure-Adb -Quiet) {
        $tv = Sh 'date +%s'
        $n = 0L
        if ([int64]::TryParse($tv, [ref]$n)) {
            $diff = $n - (UnixNow)
            $parts += "TV와 차이 $diff 초"
            if ([math]::Abs($diff) -gt 60) { $fails += 'TV와 60초 넘게 차이' }
        }
    } else { $parts += 'TV 시계는 adb가 없어 못 봄' }
    $d = $parts -join ', '
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', '))) }
    return (Res 'pass' $d)
}

$script:Checks['server.backups'] = {
    param($a)
    if (-not $script:IsWindows -or -not (Server-IsLocal)) { return (Res 'skip' 'POS기에서만 할 수 있음') }
    $dir = Join-Path $ServerDir 'pb_data\backups'
    $zips = @(Get-ChildItem -LiteralPath $dir -Filter '*.zip' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    $data = Join-Path $ServerDir 'pb_data'
    $dataMB = 0
    if (Test-Path -LiteralPath $data) { $dataMB = [math]::Round(((Get-ChildItem -LiteralPath $data -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notlike "$dir*" } | Measure-Object Length -Sum).Sum) / 1MB, 1) }
    $free = [math]::Round((Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'").FreeSpace / 1GB, 1)
    $newest = if ($zips.Count) { $zips[0] } else { $null }
    $newMB = if ($newest) { [math]::Round($newest.Length / 1MB, 1) } else { $dataMB }
    $needGB = [math]::Round($newMB * 10 / 1024, 1)
    $d = "데이터 $dataMB MB, 백업 $($zips.Count)개(총 $([math]::Round((($zips | Measure-Object Length -Sum).Sum) / 1MB, 1)) MB"
    if ($newest) { $d += ", 최신 $($newest.Name) $newMB MB $($newest.LastWriteTime.ToString('MM-dd HH:mm'))" }
    $d += "), C 빈 공간 $free GB, 백업 10개에 약 $needGB GB 필요"
    $v = @{ dataMB = $dataMB; backups = $zips.Count; newestMB = $newMB; freeGB = $free }
    if ($free -lt 10 -or $free -lt $needGB * 1.2) { return (Res 'fail' "$d — 공간 부족" $v) }
    return (Res 'pass' $d $v)
}

$script:Checks['pos.resources'] = {
    param($a)
    if (-not $script:IsWindows) { return (Res 'skip' 'Windows가 아님') }
    $secs = if ($a -and $a.seconds) { [int]$a.seconds } else { 300 }
    $csv = Ev 'pos-resources.csv'
    [IO.File]::WriteAllText($csv, "time,cpu_total,free_mem_mb,pocketbase_mb`r`n", $Utf8)
    $cpu = @(); $freeMb = @(); $pbMb = @()
    Say "   $secs 초 동안 5초마다 잽니다…"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $secs) {
        $c = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'" -ErrorAction SilentlyContinue).PercentProcessorTime
        $f = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB)
        $pb = [math]::Round(((Pb-Processes | Measure-Object WorkingSetSize -Sum).Sum) / 1MB)
        $cpu += [double]$c; $freeMb += $f; $pbMb += $pb
        [IO.File]::AppendAllText($csv, "$(Get-Date -Format 'HH:mm:ss'),$c,$f,$pb`r`n", $Utf8)
        Write-Host ("`r   CPU {0,3}%  남은 메모리 {1,5}MB  pocketbase {2,4}MB  ({3}/{4}초)" -f $c, $f, $pb, [int]$sw.Elapsed.TotalSeconds, $secs) -NoNewline
        Start-Sleep -Seconds 5
    }
    Write-Host ''
    $avg = [math]::Round((($cpu | Measure-Object -Average).Average), 1)
    $minFree = ($freeMb | Measure-Object -Minimum).Minimum
    $maxPb = ($pbMb | Measure-Object -Maximum).Maximum
    $top = (Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 | ForEach-Object { $_.ProcessName }) -join ', '
    $d = "CPU 평균 $avg%, 남은 메모리 최저 $minFree MB, pocketbase 최대 $maxPb MB, CPU 많이 쓴 프로그램: $top"
    $v = @{ cpuAvg = $avg; freeMinMB = $minFree; pbMaxMB = $maxPb }
    $fails = @()
    if ($avg -ge 70) { $fails += 'CPU 평균 70% 이상' }
    if ($minFree -lt 1024) { $fails += '남은 메모리 1GB 미만' }
    if ($maxPb -ge 300) { $fails += 'pocketbase 300MB 이상' }
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', ')) $v @($csv)) }
    return (Res 'pass' $d $v @($csv))
}

$script:Checks['tv.list'] = {
    param($a)
    if (-not (Ensure-Login)) { return (Res 'skip' '로그인하지 않아 TV 목록을 못 봄') }
    $tvs = @(Get-Tvs)
    $copy = Ev 'devices.json'
    [IO.File]::WriteAllText($copy, ($tvs | ConvertTo-Json -Depth 6), $Utf8)
    $script:Run.tvs = @($tvs | ForEach-Object { [pscustomobject]@{ id = $_.id; name = $_.name; model = $_.model; version = $_.version; ip = $_.ip } })
    if (-not $tvs.Count) { return (Res 'fail' 'TV 관리 화면에 TV가 하나도 없음(앱이 서버를 못 찾았거나 등록 실패)' $null @($copy)) }
    $lines = $tvs | ForEach-Object { Tv-Line $_ }
    $off = @($tvs | Where-Object { -not $_.online })
    $d = ($lines -join ' | ')
    if ($off.Count) { return (Res 'fail' "$d — 안 보이는 TV $($off.Count)대" $null @($copy)) }
    return (Res 'pass' $d $null @($copy))
}

$script:Checks['tv.shot'] = {
    param($a)
    if (-not (Ensure-Login)) {
        if (Ensure-Adb -Quiet) { return (& $script:Checks['adb.shot'] $a) }
        return (Res 'skip' '로그인하지 않았고 adb도 없어 TV 화면을 못 가져옴')
    }
    $tvs = @(Get-Tvs | Where-Object { $_.online })
    if (-not $tvs.Count) { return (Res 'fail' '켜져 있는 TV가 없음') }
    $files = @(); $bad = @()
    foreach ($tv in $tvs) {
        $before = [int64]$tv.shot_at
        $r = Api 'POST' "/api/menuboard/devices/$($tv.id)/shot"
        if (-not $r.ok) { $bad += "$($tv.name): 요청 실패 HTTP $($r.code)"; continue }
        $got = $null
        $sw = [Diagnostics.Stopwatch]::StartNew()
        while ($sw.Elapsed.TotalSeconds -lt 45) {
            Start-Sleep -Seconds 3
            $g = Api 'GET' "/api/collections/devices/records/$($tv.id)"
            if ($g.ok -and [int64]$g.json.shot_at -gt $before -and $g.json.shot) { $got = $g.json; break }
        }
        if (-not $got) { $bad += "$($tv.name): 45초 안에 사진이 안 옴"; continue }
        $file = Ev ("$($script:CurStep)-tv-$($tv.name).jpg")
        $dl = Http 'GET' "/api/files/$($got.collectionId)/$($got.id)/$($got.shot)" -OutFile $file -timeout 30
        if ($dl.ok -and (Test-Path -LiteralPath $file)) { $files += $file } else { $bad += "$($tv.name): 사진 내려받기 실패 $($dl.code)" }
    }
    $d = "TV 화면 $($files.Count)장 저장"
    if ($bad.Count) { return (Res 'fail' ("$d — " + ($bad -join '; ')) $null $files) }
    return (Res 'pass' "$d(사진이 실제 TV와 같은지 사람이 봅니다)" $null $files)
}

$script:Checks['tv.waitOnline'] = {
    param($a)
    if (-not (Ensure-Login)) { return (Res 'skip' '로그인하지 않아 TV 보고를 못 봄') }
    $max = if ($a -and $a.max) { [int]$a.max } else { 180 }
    $tv = Pick-Tv '기다릴 TV를 고르세요.'
    if (-not $tv) { return (Res 'fail' 'TV가 없음') }
    $t0 = $script:StepStart
    if (-not $t0) { $t0 = [Diagnostics.Stopwatch]::StartNew() }
    $limit = $max + 300
    $sawDown = $false
    Say "   '$($tv.name)' 이 꺼졌다 다시 보고하기를 기다립니다(최대 $limit 초, Ctrl+C로 멈춤)…"
    while ($t0.Elapsed.TotalSeconds -lt $limit) {
        $r = Api 'GET' "/api/collections/devices/records/$($tv.id)" -timeout 5
        if (-not $r.ok) { $sawDown = $true }
        else {
            $age = (ServerNow) - [int64]$r.json.last_seen
            if ($age -gt 20) { $sawDown = $true }
            elseif ($sawDown) {
                $sec = [math]::Round($t0.Elapsed.TotalSeconds)
                $d = "$sec 초 만에 다시 보고: " + (Tv-Line ($r.json | Add-Member -NotePropertyName age -NotePropertyValue $age -PassThru -Force | Add-Member -NotePropertyName online -NotePropertyValue $true -PassThru -Force))
                if ($sec -le $max) { return (Res 'pass' $d $sec) }
                return (Res 'fail' "$d (기준 $max 초)" $sec)
            }
        }
        if (-not $sawDown -and $t0.Elapsed.TotalSeconds -gt 75) { return (Res 'fail' '75초 동안 TV가 계속 보고함(전원이 실제로 끊겼는지 확인)') }
        Start-Sleep -Seconds 3
    }
    return (Res 'fail' "$limit 초 안에 TV가 다시 보고하지 않음")
}

$script:Checks['tv.reported'] = {
    param($a)
    if (-not (Ensure-Login)) { return (Res 'skip' '로그인하지 않아 TV 보고를 못 봄') }
    $tv = Pick-Tv '값을 볼 TV를 고르세요.'
    if (-not $tv) { return (Res 'fail' 'TV가 없음') }
    Say '   TV의 다음 보고를 기다립니다(최대 40초)…'
    $rec = Wait-Report $tv.id ((ServerNow) - 1) 40
    if (-not $rec) { return (Res 'fail' "40초 안에 '$($tv.name)' 이 보고하지 않음(앱이 꺼졌거나 서버를 못 찾음)") }
    $rp = $rec.reported
    $bad = @(); $seen = @()
    foreach ($p in $a.PSObject.Properties) {
        $got = $rp.($p.Name)
        $seen += "$($p.Name)=$got"
        if ([string]$got -ne [string]$p.Value) { $bad += "$($p.Name) 기대 $($p.Value), 실제 $got" }
    }
    $d = "$($tv.name): " + ($seen -join ', ')
    if ($rp.note) { $d += ", 알림: $($rp.note)" }
    if ($rp.usb) { $d += ", USB: $($rp.usb)" }
    if ($bad.Count) { return (Res 'fail' ("$d — " + ($bad -join '; ')) $rp) }
    return (Res 'pass' $d $rp)
}

$script:Checks['tv.openAdb'] = {
    param($a)
    if (-not $script:AdbExe) { return (Res 'skip' 'adb.exe 가 없음(README 준비물)') }
    if (-not (Ensure-Login)) { return (Res 'skip' '로그인하지 않아 A/S 연결을 못 엶') }
    $min = if ($a -and $a.minutes) { [int]$a.minutes } else { 30 }
    $tv = Pick-Tv 'A/S 연결을 열 TV를 고르세요.'
    if (-not $tv) { return (Res 'fail' 'TV가 없음') }
    $r = Api 'POST' "/api/menuboard/devices/$($tv.id)/adb" @{ minutes = $min }
    if ($r.code -eq 403 -or $r.code -eq 400) {
        Say "   매장 계정으로는 열 수 없습니다: $($r.json.message)" 'Yellow'
        if (Ensure-Login -Superuser) { $r = Api 'POST' "/api/menuboard/devices/$($tv.id)/adb" @{ minutes = $min } }
    }
    if (-not $r.ok) { return (Res 'fail' "A/S 연결 열기 실패 HTTP $($r.code): $($r.body)") }
    $script:AdbOpened += $tv.id
    $script:Run | Add-Member -NotePropertyName adbOpened -NotePropertyValue @(@($script:Run.adbOpened) + $tv.id | Where-Object { $_ } | Select-Object -Unique) -Force
    Save-Run
    Say '   TV가 A/S 연결을 켜기를 기다립니다(최대 40초)…'
    $rec = $null
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt 40) {
        $g = Api 'GET' "/api/collections/devices/records/$($tv.id)"
        if ($g.ok -and $g.json.reported -and $g.json.reported.adb -eq $true) { $rec = $g.json; break }
        Start-Sleep -Seconds 3
    }
    if (-not $rec) { return (Res 'fail' "40초 안에 TV가 adb를 켜지 않음(canAdb=$($tv.reported.canAdb): false면 설치 bat의 WRITE_SECURE_SETTINGS 허용이 빠짐)") }
    $serial = "$($rec.ip):$AdbPort"
    $c = Adb-Run @('connect', $serial)
    Start-Sleep -Seconds 2
    $state = ''
    for ($i = 0; $i -lt 20; $i++) {
        $state = ([string](Adb-Run @('-s', $serial, 'get-state')).out).Trim()
        if ($state -eq 'device') { break }
        if ($i -eq 0 -and $state -match 'unauthorized') { Say '   TV 화면에 "USB 디버깅을 허용할까요?" 창이 뜨면 "항상 허용"을 리모컨으로 누르세요.' 'Yellow' }
        Start-Sleep -Seconds 3
    }
    if ($state -ne 'device') { return (Res 'fail' "A/S 연결은 열렸지만 adb connect $serial 실패: $($c.out) / 상태 $state") }
    $script:AdbSerial = $serial
    return (Res 'pass' "$($tv.name) A/S 연결 $min 분 열림, adb $serial 연결됨")
}

function Need-Adb { if (-not (Ensure-Adb)) { return $false }; return $true }

$script:Checks['adb.info'] = {
    param($a)
    if (-not (Need-Adb)) { return (Res 'skip' 'adb로 붙은 TV가 없음') }
    $props = [ordered]@{}
    foreach ($k in @('ro.product.manufacturer', 'ro.product.model', 'ro.board.platform', 'ro.hardware', 'ro.build.version.release', 'ro.build.version.sdk', 'ro.build.fingerprint', 'ro.adb.secure', 'ro.debuggable', 'persist.adb.tcp.port', 'service.adb.tcp.port')) {
        $props[$k] = Sh "getprop $k"
    }
    $props['wm.size'] = Sh 'wm size'
    $props['wm.density'] = Sh 'wm density'
    $props['uptime'] = Sh 'uptime'
    $df = Sh 'df -k /data'
    $freeMB = $null
    foreach ($line in ($df -split "`n")) { if ($line -match '\s(\d+)\s+(\d+)\s+(\d+)\s+\d+%') { $freeMB = [math]::Round([int64]$Matches[3] / 1024) } }
    $props['data.freeMB'] = $freeMB
    $temps = @()
    foreach ($t in ((Sh 'cat /sys/class/thermal/thermal_zone*/temp') -split "`n")) { $n = 0; if ([int]::TryParse($t.Trim(), [ref]$n)) { $temps += [math]::Round($n / 1000, 1) } }
    $props['temps'] = ($temps -join ',')
    $file = Ev 'tv-getprop.txt'
    [IO.File]::WriteAllText($file, (Sh 'getprop'), $Utf8)
    $d = "$($props['ro.product.manufacturer']) $($props['ro.product.model']) / $($props['ro.board.platform']) / 안드로이드 $($props['ro.build.version.release']) (SDK $($props['ro.build.version.sdk'])) / $($props['wm.size']) / /data 빈 공간 $freeMB MB / 온도 $($props['temps'])도 / ro.adb.secure=$($props['ro.adb.secure'])"
    $fails = @(); $notes = @()
    $sdk = 0; [void][int]::TryParse($props['ro.build.version.sdk'], [ref]$sdk)
    if ($sdk -lt 30) { $fails += '안드로이드 11(SDK 30) 미만' }
    if ($null -ne $freeMB -and $freeMB -lt 1024) { $fails += '/data 빈 공간 1GB 미만' }
    if ($props['ro.adb.secure'] -ne '1') { $notes += '펌웨어 ADB 인증이 꺼져 있음(R-1, 보드 업체 요청 항목)' }
    if ($props['ro.board.platform'] -notmatch 'rk3568|rk356x') { $notes += "보드 칩이 rk3568이 아님($($props['ro.board.platform']))" }
    if ($notes.Count) { $d += ' — 참고: ' + ($notes -join ', ') }
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', ')) $props @($file)) }
    return (Res 'pass' $d $props @($file))
}

$script:Checks['adb.app'] = {
    param($a)
    if (-not (Need-Adb)) { return (Res 'skip' 'adb로 붙은 TV가 없음') }
    $pkg = Sh 'dumpsys package com.menuboard.player'
    $file = Ev 'tv-dumpsys-package.txt'
    [IO.File]::WriteAllText($file, $pkg, $Utf8)
    if ($pkg -notmatch 'versionCode=(\d+)') { return (Res 'fail' 'com.menuboard.player 가 설치되어 있지 않음' $null @($file)) }
    $vc = $Matches[1]
    $vn = if ($pkg -match 'versionName=(\S+)') { $Matches[1] } else { '' }
    $wss = $pkg -match 'android\.permission\.WRITE_SECURE_SETTINGS: granted=true'
    $ops = @{}
    foreach ($op in @('SYSTEM_ALERT_WINDOW', 'REQUEST_INSTALL_PACKAGES', 'MANAGE_EXTERNAL_STORAGE')) {
        $ops[$op] = (Sh "appops get com.menuboard.player $op") -replace '\s+', ' '
    }
    $d = "버전 $vn(코드 $vc), WRITE_SECURE_SETTINGS=$wss, " + (($ops.Keys | ForEach-Object { "$_ → $($ops[$_])" }) -join ', ')
    $fails = @()
    if (-not $wss) { $fails += 'WRITE_SECURE_SETTINGS 가 없음(A/S 연결 잠금이 안 됨)' }
    if ($ops['SYSTEM_ALERT_WINDOW'] -notmatch 'allow') { $fails += '다른 앱 위에 표시가 허용되지 않음(부팅 때 안 뜰 수 있음)' }
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', ')) $null @($file)) }
    return (Res 'pass' $d $null @($file))
}

$script:Checks['adb.home'] = {
    param($a)
    if (-not (Need-Adb)) { return (Res 'skip' 'adb로 붙은 TV가 없음') }
    $homeApp = ((Sh 'cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME') -split "`n" | Select-Object -Last 1).Trim()
    $acts = Sh 'dumpsys activity activities'
    $top = ''
    foreach ($line in ($acts -split "`n")) { if ($line -match '(topResumedActivity|mResumedActivity|ResumedActivity)[:=].*?(\S+/\S+)') { $top = $Matches[2]; break } }
    $d = "홈 앱 $homeApp, 맨 앞 화면 $top"
    $notes = @()
    if ($homeApp -notmatch 'com\.menuboard\.player') { $notes += '홈 앱으로 지정되지 않음(부팅 수신기로 떠야 함, H-3 확인)' }
    if ($notes.Count) { $d += ' — ' + ($notes -join ', ') }
    if ($top -notmatch 'com\.menuboard\.player') { return (Res 'fail' "$d — 맨 앞이 메뉴판이 아님") }
    return (Res 'pass' $d)
}

$script:Checks['adb.crash'] = {
    param($a)
    if (-not (Ensure-Adb -Quiet)) { return (Res 'skip' 'adb로 붙은 TV가 없음(꺼짐 여부는 사람이 본 것으로)') }
    $crash = (Adb-Run @('-s', $script:AdbSerial, 'logcat', '-b', 'crash', '-d')).out
    $all = (Adb-Run @('-s', $script:AdbSerial, 'logcat', '-d', '-t', '3000') 60).out
    $f1 = Ev ("$($script:CurStep)-logcat.txt"); [IO.File]::WriteAllText($f1, $all, $Utf8)
    $mine = @(([string]$crash -split "`n") | Where-Object { $_ -match 'com\.menuboard\.player' })
    if ($mine.Count) {
        $f2 = Ev ("$($script:CurStep)-crash.txt"); [IO.File]::WriteAllText($f2, $crash, $Utf8)
        $first = ([string]$crash -split "`n" | Where-Object { $_ -match 'Exception|Error' } | Select-Object -First 2) -join ' / '
        return (Res 'fail' "메뉴판 앱 꺼짐 기록 있음: $first" $null @($f2, $f1))
    }
    return (Res 'pass' '이번 부팅 뒤 메뉴판 앱 꺼짐(FATAL) 기록 없음' $null @($f1))
}

$script:Checks['adb.shot'] = {
    param($a)
    if (-not (Need-Adb)) { return (Res 'skip' 'adb로 붙은 TV가 없음') }
    $file = Ev ("$($script:CurStep)-tv-adb.png")
    $null = Adb-Run @('-s', $script:AdbSerial, 'shell', 'screencap -p /sdcard/mb-hwtest.png')
    $null = Adb-Run @('-s', $script:AdbSerial, 'pull', '/sdcard/mb-hwtest.png', $file)
    $null = Adb-Run @('-s', $script:AdbSerial, 'shell', 'rm /sdcard/mb-hwtest.png')
    if (Test-Path -LiteralPath $file) { return (Res 'pass' 'adb로 TV 화면 저장' $null @($file)) }
    return (Res 'fail' 'adb 화면 캡처 실패')
}

$script:Checks['adb.mem'] = {
    param($a)
    if (-not (Need-Adb)) { return (Res 'skip' 'adb로 붙은 TV가 없음') }
    $m = Sh 'dumpsys meminfo com.menuboard.player'
    $file = Ev ("$($script:CurStep)-meminfo.txt"); [IO.File]::WriteAllText($file, $m, $Utf8)
    $pss = $null
    if ($m -match 'TOTAL PSS:\s+(\d+)') { $pss = [math]::Round([int64]$Matches[1] / 1024) }
    elseif ($m -match '(?m)^\s*TOTAL\s+(\d+)') { $pss = [math]::Round([int64]$Matches[1] / 1024) }
    $avail = $null
    $mi = Sh 'cat /proc/meminfo'
    if ($mi -match 'MemAvailable:\s+(\d+)') { $avail = [math]::Round([int64]$Matches[1] / 1024) }
    $d = "메뉴판 앱 메모리 $pss MB, TV 남은 메모리 $avail MB (last.mht 크기는 앱 전용 폴더라 adb로 못 읽음)"
    if ($null -eq $pss) { return (Res 'fail' '메뉴판 앱이 돌고 있지 않음' $null @($file)) }
    if ($pss -gt 400) { return (Res 'fail' "$d — 400MB 넘음" $pss @($file)) }
    return (Res 'pass' $d $pss @($file))
}

$script:Checks['adb.wifi'] = {
    param($a)
    if (-not (Need-Adb)) { return (Res 'skip' 'adb로 붙은 TV가 없음(사람이 TV 설정의 신호 세기를 적음)') }
    $w = Sh 'dumpsys wifi'
    $rssi = $null
    if ($w -match 'RSSI:\s*(-\d+)') { $rssi = [int]$Matches[1] }
    $ssid = if ($w -match 'SSID:\s*"?([^",]+)') { $Matches[1] } else { '' }
    $eth = Sh 'cat /sys/class/net/eth0/operstate'
    if ($null -eq $rssi) { return (Res 'info' "와이파이 연결 정보 없음(유선 eth0=$eth)") }
    $d = "와이파이 $ssid 신호 $rssi dBm (유선 eth0=$eth)"
    if ($rssi -lt -70) { return (Res 'fail' "$d — -70보다 약함" $rssi) }
    return (Res 'pass' $d $rssi)
}

function Tcp-Open([string]$h, [int]$port, [int]$ms = 3000) {
    $c = New-Object Net.Sockets.TcpClient
    try { $ar = $c.BeginConnect($h, $port, $null, $null); if ($ar.AsyncWaitHandle.WaitOne($ms) -and $c.Connected) { return $true }; return $false }
    catch { return $false } finally { $c.Close() }
}

function Host-Of([string]$what) {
    if ($what -eq 'pos') {
        $h = ([uri]$Server).Host
        if ($h -ne '127.0.0.1' -and $h -ne 'localhost') { return $h }
        return (Ask '   POS기 주소(예 192.168.0.10)')
    }
    if ($what -eq 'tv') {
        if ($script:Run.tvs -and @($script:Run.tvs).Count) { $d = (Ask "   TV 주소 [$(@($script:Run.tvs)[0].ip)]" (@($script:Run.tvs)[0].ip)); return $d }
        return (Ask '   TV 주소(예 192.168.0.21, TV 관리 화면에 보임)')
    }
    return $what
}

$script:Checks['net.blocked'] = {
    param($a)
    $open = @(); $closed = @()
    foreach ($p in @($a.ports)) {
        $parts = ([string]$p).Split(':')
        $h = Host-Of $parts[0]
        if (-not $h) { continue }
        $port = [int]$parts[1]
        if ($parts[0] -eq 'tv') { $port = $AdbPort }
        if (Tcp-Open $h $port) { $open += "${h}:$port" } else { $closed += "${h}:$port" }
    }
    $ip = ''
    if ($script:IsWindows) { $ip = (@(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | ForEach-Object { $_.IPAddress }) -join ',') }
    $d = "이 PC($ip)에서 — 막힘: $($closed -join ', '), 열림: $($open -join ', ')"
    if ($open.Count) { return (Res 'fail' $d) }
    if (-not $closed.Count) { return (Res 'skip' '검사할 주소가 없음') }
    return (Res 'pass' $d)
}

$script:Checks['adb.foreign'] = {
    param($a)
    if (-not $script:AdbExe) { return (Res 'skip' 'adb.exe 가 없음') }
    $h = Host-Of 'tv'
    if (-not $h) { return (Res 'skip' 'TV 주소 없음') }
    $serial = "${h}:$AdbPort"
    # 한 번도 허용받은 적 없는 새 adb 키로 붙어 본다(이 PC의 원래 키는 건드리지 않음).
    $tmp = Join-Path $env:TEMP ('mb-adbkey-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    $oldHome = $env:ANDROID_USER_HOME; $oldSdkHome = $env:ANDROID_SDK_HOME
    try {
        $null = Adb-Run @('kill-server')
        $env:ANDROID_USER_HOME = $tmp; $env:ANDROID_SDK_HOME = $tmp
        $c = Adb-Run @('connect', $serial)
        Start-Sleep -Seconds 4
        $state = ([string](Adb-Run @('-s', $serial, 'get-state')).out).Trim()
        $null = Adb-Run @('disconnect', $serial)
        $null = Adb-Run @('kill-server')
    } finally {
        $env:ANDROID_USER_HOME = $oldHome; $env:ANDROID_SDK_HOME = $oldSdkHome
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        $script:AdbSerial = ''
    }
    $d = "새 키로 adb connect $serial → '$($c.out)', 상태 '$state'"
    if ($state -eq 'device') { return (Res 'fail' "$d — 허용 없이 바로 붙음(ro.adb.secure 꺼짐)") }
    return (Res 'pass' "$d — 허용 없이는 못 붙음(TV에 허용 창이 떴는지 사람이 봅니다)")
}

$script:Checks['load.calls'] = {
    param($a)
    if (-not (Ensure-Login)) { return (Res 'skip' '로그인하지 않아 번호를 못 부름') }
    $count = if ($a -and $a.count) { [int]$a.count } else { 1 }
    $every = if ($a -and $a.everyMs) { [int]$a.everyMs } else { 500 }
    $maxMs = if ($a -and $a.maxMs) { [int]$a.maxMs } else { 2000 }
    $store = Get-StoreId
    if (-not $store) { return (Res 'fail' '매장 번호를 모름(서버에 매장이 여럿이면 매장 계정으로 로그인)') }
    if (-not (Confirm-Calls)) { return (Res 'skip' '사람이 번호 부르기를 취소함') }
    $base = 900 + ((UnixNow) % 90) * 10
    $ms = @(); $bad = @(); $nums = @()
    for ($i = 0; $i -lt $count; $i++) {
        $n = (($base + $i) % 9998) + 1
        $r = Api 'POST' '/api/collections/calls/records' @{ store = $store; number = $n }
        if ($r.ok) { $ms += $r.ms; $nums += $n } else { $bad += "$n → HTTP $($r.code) $($r.json.message)" }
        if ($i -lt $count - 1) { Start-Sleep -Milliseconds $every }
    }
    $mx = if ($ms.Count) { ($ms | Measure-Object -Maximum).Maximum } else { 0 }
    $avg = if ($ms.Count) { [math]::Round(($ms | Measure-Object -Average).Average) } else { 0 }
    $d = "번호 $($nums.Count)/$count 개 부름(시험 번호 $($nums | Select-Object -First 1)~), 평균 $avg ms, 최대 $mx ms"
    $v = @{ ok = $nums.Count; avgMs = $avg; maxMs = $mx }
    if ($bad.Count) { return (Res 'fail' ("$d — 실패: " + (($bad | Select-Object -First 3) -join '; ')) $v) }
    if ($mx -gt $maxMs) { return (Res 'fail' "$d — 최대 $maxMs ms 넘음" $v) }
    return (Res 'pass' $d $v)
}

# 시험 번호(900·9000번대)를 실제 TV에 띄우기 전에 한 번 묻는다(영업 중 매장 보호).
$script:CallsOk = $false
function Confirm-Calls {
    if ($script:CallsOk -or -not $script:Interactive -or $script:Answers.Count -gt 0) { return $true }
    $a = Ask '   시험 번호(900·9000번대)를 실제로 불러 TV에 띄웁니다. 영업 중이 아니죠? [y/N]' 'n'
    $script:CallsOk = ($a -match '^[yY]')
    return $script:CallsOk
}

# 연속 운영 기록(H-5). 끊겨도 다시 돌리면 monitor.csv 에 이어서 적는다.
$script:Checks['monitor'] = {
    param($a)
    $hours = if ($a -and $a.hours) { [double]$a.hours } else { 72 }
    $every = if ($a -and $a.everyMinutes) { [double]$a.everyMinutes } else { 10 }
    $cph = if ($a -and $null -ne $a.callsPerHour) { [double]$a.callsPerHour } else { 0 }
    if ($env:HWTEST_MONITOR_SECONDS) { $hours = [double]$env:HWTEST_MONITOR_SECONDS / 3600; $every = 0.05 }
    $loggedIn = Ensure-Login
    $csv = Ev 'monitor.csv'
    if (-not (Test-Path -LiteralPath $csv)) {
        [IO.File]::WriteAllText($csv, "time,server_ok,server_ms,pb_mb,pb_handles,c_free_gb,pb_data_mb,tv_online,tv_total,tv_max_age_s,tv_app_mb,tv_temp_c,calls_ok,calls_fail,pb_pid`r`n", $Utf8)
    }
    $untilFile = Ev 'monitor-until.txt'
    if (Test-Path -LiteralPath $untilFile) { $until = [datetime]::Parse([IO.File]::ReadAllText($untilFile)) }
    else { $until = (Get-Date).AddHours($hours); [IO.File]::WriteAllText($untilFile, $until.ToString('o')) }
    Say "   $($until.ToString('MM-dd HH:mm'))까지 $every 분마다 적습니다. 이 창을 닫지 마세요(닫혀도 -Resume 으로 이어짐)." 'Yellow'
    $carry = 0.0
    $store = if ($loggedIn) { Get-StoreId } else { '' }
    if ($store -and $cph -gt 0 -and -not (Confirm-Calls)) { $cph = 0 }
    $lastPid = ''
    $num = 9000
    while ((Get-Date) -lt $until) {
        $h = Http 'GET' '/api/health' -timeout 5 -NoAuth
        $pb = @(Pb-Processes)
        $pbMb = [math]::Round((($pb | Measure-Object WorkingSetSize -Sum).Sum) / 1MB)
        $hand = ($pb | Measure-Object HandleCount -Sum).Sum
        $free = ''; $dataMb = ''
        if ($script:IsWindows) {
            $free = [math]::Round((Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'").FreeSpace / 1GB, 2)
            $pd = Join-Path $ServerDir 'pb_data'
            if (Test-Path -LiteralPath $pd) { $dataMb = [math]::Round(((Get-ChildItem -LiteralPath $pd -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum) / 1MB, 1) }
        }
        $on = ''; $tot = ''; $maxAge = ''
        if ($loggedIn -and $h.ok) {
            try { $tvs = @(Get-Tvs); $tot = $tvs.Count; $on = @($tvs | Where-Object { $_.online }).Count; $maxAge = ($tvs | Measure-Object age -Maximum).Maximum } catch { }
        }
        $tvMb = ''; $temp = ''
        if (Ensure-Adb -Quiet) {
            $m = Sh 'dumpsys meminfo com.menuboard.player'
            if ($m -match 'TOTAL PSS:\s+(\d+)') { $tvMb = [math]::Round([int64]$Matches[1] / 1024) } elseif ($m -match '(?m)^\s*TOTAL\s+(\d+)') { $tvMb = [math]::Round([int64]$Matches[1] / 1024) }
            $t = 0; if ([int]::TryParse((Sh 'cat /sys/class/thermal/thermal_zone0/temp'), [ref]$t)) { $temp = [math]::Round($t / 1000, 1) }
        }
        $cOk = 0; $cFail = 0
        if ($store -and $cph -gt 0) {
            $carry += $cph * $every / 60
            while ($carry -ge 1) {
                $carry -= 1; $num = if ($num -ge 9998) { 9000 } else { $num + 1 }
                $r = Api 'POST' '/api/collections/calls/records' @{ store = $store; number = $num }
                if ($r.ok) { $cOk++ } else { $cFail++ }
            }
        }
        $pids = (@($pb | ForEach-Object { $_.ProcessId }) -join ' ')
        $row = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$([int]$h.ok),$($h.ms),$pbMb,$hand,$free,$dataMb,$on,$tot,$maxAge,$tvMb,$temp,$cOk,$cFail,$pids"
        [IO.File]::AppendAllText($csv, "$row`r`n", $Utf8)
        Write-Host ("   {0}  서버 {1} {2}ms  pb {3}MB  C {4}GB  TV {5}/{6}  TV앱 {7}MB {8}도  번호 +{9}" -f (Get-Date -Format 'MM-dd HH:mm'), $(if ($h.ok) { '정상' } else { '응답없음' }), $h.ms, $pbMb, $free, $on, $tot, $tvMb, $temp, $cOk)
        $sleep = [int]($every * 60)
        $wake = (Get-Date).AddSeconds($sleep)
        while ((Get-Date) -lt $wake -and (Get-Date) -lt $until) { Start-Sleep -Seconds ([math]::Min(10, [math]::Max(1, $sleep))) }
    }
    return (Summarize-Monitor $csv $every)
}

function Summarize-Monitor([string]$csv, [double]$every) {
    $rows = @(Import-Csv -LiteralPath $csv -Encoding UTF8)
    if (-not $rows.Count) { return (Res 'fail' '기록이 없음' $null @($csv)) }
    $srvFail = @($rows | Where-Object { $_.server_ok -ne '1' }).Count
    $pbs = @($rows | Where-Object { $_.pb_mb -ne '' } | ForEach-Object { [double]$_.pb_mb })
    $pbFirst = if ($pbs.Count) { $pbs[0] } else { 0 }
    $pbMax = if ($pbs.Count) { ($pbs | Measure-Object -Maximum).Maximum } else { 0 }
    $frees = @($rows | Where-Object { $_.c_free_gb -ne '' } | ForEach-Object { [double]$_.c_free_gb })
    $freeMin = if ($frees.Count) { ($frees | Measure-Object -Minimum).Minimum } else { $null }
    $ages = @($rows | Where-Object { $_.tv_max_age_s -ne '' } | ForEach-Object { [double]$_.tv_max_age_s })
    $ageMax = if ($ages.Count) { ($ages | Measure-Object -Maximum).Maximum } else { $null }
    $calls = ($rows | Measure-Object calls_ok -Sum).Sum
    $callFail = ($rows | Measure-Object calls_fail -Sum).Sum
    $tvm = @($rows | Where-Object { $_.tv_app_mb -ne '' } | ForEach-Object { [double]$_.tv_app_mb })
    # 빈 시간(기록 간격이 기준의 2배 넘음), 예상 줄 수, 서버가 다시 시작된 횟수(PID 바뀜)
    $times = @($rows | ForEach-Object { [datetime]::ParseExact($_.time, 'yyyy-MM-dd HH:mm:ss', $null) })
    $maxGapMin = 0
    for ($i = 1; $i -lt $times.Count; $i++) { $g = ($times[$i] - $times[$i - 1]).TotalMinutes; if ($g -gt $maxGapMin) { $maxGapMin = $g } }
    $maxGapMin = [math]::Round($maxGapMin, 1)
    $spanMin = ($times[-1] - $times[0]).TotalMinutes
    $untilFile = Join-Path (Split-Path $csv) 'monitor-until.txt'
    $expected = 0
    if (Test-Path -LiteralPath $untilFile) {
        $until = [datetime]::Parse([IO.File]::ReadAllText($untilFile))
        $expected = [math]::Floor((($until - $times[0]).TotalMinutes) / $every)
    }
    $restarts = 0; $prev = ''
    foreach ($r in $rows) { if ($r.pb_pid -and $prev -and $r.pb_pid -ne $prev) { $restarts++ }; if ($r.pb_pid) { $prev = $r.pb_pid } }
    $d = "기록 $($rows.Count)줄(예상 약 $expected 줄, $($rows[0].time) ~ $($rows[-1].time)), 가장 긴 빈 시간 $maxGapMin 분, 서버 다시 시작 $restarts 번, 서버 응답 실패 $srvFail 번, pocketbase $pbFirst→최대 $pbMax MB, C 최저 $freeMin GB, TV 최장 안 보임 $ageMax 초, 번호 $calls 번(실패 $callFail)"
    if ($tvm.Count) { $d += ", TV 앱 메모리 $($tvm[0])→최대 $(($tvm | Measure-Object -Maximum).Maximum) MB" }
    $fails = @()
    if ($srvFail -gt 0) { $fails += '서버 응답 실패 있음' }
    if ($pbFirst -gt 0 -and $pbMax -gt $pbFirst * 2) { $fails += 'pocketbase 메모리가 2배 넘게 늘어남' }
    if ($null -ne $freeMin -and $freeMin -lt 5) { $fails += 'C 빈 공간 5GB 미만' }
    if ($null -ne $ageMax -and $ageMax -gt 300) { $fails += 'TV가 5분 넘게 안 보인 적 있음' }
    if ($callFail -gt 0) { $fails += '번호 부르기 실패 있음' }
    if ($maxGapMin -gt [math]::Max(20, $every * 2)) { $fails += "기록이 $maxGapMin 분 비었음(POS기가 꺼졌거나 창이 닫힘)" }
    if ($expected -ge 30 -and $rows.Count -lt $expected * 0.9) { $fails += '기록 줄 수가 예상의 90% 미만' }
    if ($restarts -gt 0) { $fails += "서버가 $restarts 번 다시 시작됨(메모리 비교가 그만큼 짧음)" }
    $v = @{ rows = $rows.Count; expected = $expected; maxGapMin = $maxGapMin; restarts = $restarts; serverFail = $srvFail; pbFirstMB = $pbFirst; pbMaxMB = $pbMax; freeMinGB = $freeMin; tvMaxAgeS = $ageMax; calls = $calls }
    if ($fails.Count) { return (Res 'fail' ("$d — " + ($fails -join ', ')) $v @($csv)) }
    return (Res 'pass' $d $v @($csv))
}

# ───────────────────────── 시험 진행 ─────────────────────────

$script:CurStep = ''
$script:StepStart = $null
# 사람이 아무것도 하지 않아도 되는 검사(-AutoOnly 때 이것만 돈다)
$script:Passive = @('build.apk', 'server.health', 'server.lan', 'server.task', 'win.bootToServer', 'win.firewall', 'win.power', 'win.updateHours',
    'win.defender', 'win.antivirus', 'win.folderAcl', 'win.clock', 'server.backups', 'tv.list', 'tv.shot',
    'adb.info', 'adb.app', 'adb.home', 'adb.crash', 'adb.mem', 'adb.wifi')

function Status-Ko([string]$s) {
    switch ($s) { 'pass' { '통과' } 'fail' { '실패' } 'skip' { '건너뜀' } 'info' { '기록' } 'pending' { '다시 켠 뒤 확인' } 'error' { '스크립트 오류' } default { $s } }
}
function Status-Color([string]$s) {
    switch ($s) { 'pass' { 'Green' } 'fail' { 'Red' } 'error' { 'Magenta' } 'skip' { 'DarkYellow' } default { 'Gray' } }
}

function Ask-Verdict([string]$suggest = '') {
    $hint = if ($suggest) { " (Enter = $(Status-Ko $suggest))" } else { '' }
    while ($true) {
        $a = Ask "   결과: [P]통과 [F]실패 [S]건너뜀 [I]기록만 [Q]그만(나중에 이어 하기)$hint" $(if ($suggest) { $suggest.Substring(0, 1) } else { '' })
        switch -regex ($a) {
            '^[pP]' { return 'pass' }
            '^[fF]' { return 'fail' }
            '^[sS]' { return 'skip' }
            '^[iI]' { return 'info' }
            '^[qQ]' { return 'quit' }
        }
        if (-not $script:Interactive) { return 'skip' }
    }
}

function Read-Value($v) {
    $a = Ask "   $($v.label) 을(를) 넣으세요. (Enter만 누르면 초시계 시작)" ''
    if ($a -eq '' -and $script:Interactive) {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $null = Read-Host '   초시계가 돌고 있습니다. 끝나면 Enter'
        return [math]::Round($sw.Elapsed.TotalSeconds)
    }
    $n = 0.0
    if ([double]::TryParse($a, [ref]$n)) { return $n }
    return $null
}

function Run-Step($item, $step) {
    $script:CurStep = "$($item.id)-$($step.n)"
    $script:StepStart = $null
    $prev = Find-Result $item.id $step.n
    $doText = [string]$step.do
    $auto = [string]$step.auto
    $hasDo = ($doText.Trim() -ne '')
    Write-Host ''
    Write-Host ("  [{0} {1}] " -f $item.id, $step.n) -ForegroundColor White -NoNewline
    if ($hasDo) { Write-Host $doText -ForegroundColor White } else { Write-Host '(자동)' -ForegroundColor DarkGray }
    if ($step.expect) { Say "      합격: $($step.expect)" 'DarkCyan' }

    # 다시 켠 뒤 이어서 온 경우
    if ($prev -and $prev.status -eq 'pending') {
        if (-not $step.expect) { $null = Add-Result $item $step (Res 'info' '다시 켜짐'); return 'ok' }
        $v = Ask-Verdict
        if ($v -eq 'quit') { return 'quit' }
        $memo = if ($v -eq 'fail') { Ask '   무엇이 잘못됐나요(한 줄)' } else { '' }
        $null = Add-Result $item $step (Res $v '다시 켠 뒤 사람이 확인') $memo
        return 'ok'
    }

    if ($AutoOnly -and -not ($auto -and $script:Passive -contains $auto) ) {
        $null = Add-Result $item $step (Res 'skip' '자동 검사만 하는 실행')
        return 'ok'
    }

    if ($step.reboot) {
        if (-not $script:Interactive) { $null = Add-Result $item $step (Res 'skip' '자동 점검에서는 다시 시작하지 않음'); return 'ok' }
        $null = Add-Result $item $step (Res 'pending' '다시 켜기를 기다림')
        $script:Run.state = 'reboot'; Save-Run
        try {
            $cmd = '"' + (Join-Path $Here 'run-hw-test.bat') + '" -Resume'
            Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'MenuBoardHwTest' -Value $cmd
            Say '   다시 켜고 로그인하면 이 시험이 저절로 이어집니다.' 'Yellow'
        } catch { Say "   자동 이어 하기를 등록하지 못했습니다. 다시 켠 뒤 run-hw-test.bat -Resume 을 실행하세요." 'Yellow' }
        $a = Ask '   [R] 지금 다시 시작  [Enter] 제가 직접 끄고 켭니다(이 창은 닫혀도 됨)' ''
        if ($a -match '^[rR]') { Restart-Computer -Force }
        return 'quit'
    }

    if ($hasDo -and $script:Interactive -and -not $AutoOnly) {
        $a = Ask '   하고 나면 Enter  ([S] 건너뜀, [Q] 그만)' ''
        if ($a -match '^[sS]') { $null = Add-Result $item $step (Res 'skip' '사람이 건너뜀'); return 'ok' }
        if ($a -match '^[qQ]') { return 'quit' }
    }
    $script:StepStart = [Diagnostics.Stopwatch]::StartNew()

    $files = @()
    if ($step.shot -eq 'pos') { $f = Shot-Pos $script:CurStep; if ($f) { $files += $f } }

    $res = $null
    if ($auto) {
        Say "   자동 검사: $auto …" 'DarkGray'
        if (-not $script:Checks.ContainsKey($auto)) { $res = Res 'error' "검사 '$auto' 가 hw-test.ps1 에 없음" }
        else {
            try { $res = & $script:Checks[$auto] $step.args }
            catch { $res = Res 'error' ("검사 중 오류: " + $_.Exception.Message + ' @ ' + $_.InvocationInfo.ScriptLineNumber) }
            if ($null -eq $res -or -not ($res -is [hashtable])) { $res = Res 'error' "검사 '$auto' 가 결과를 돌려주지 않음" }
        }
        $res.files = @($res.files) + $files
        Write-Host ("   → {0}: {1}" -f (Status-Ko $res.status), $res.detail) -ForegroundColor (Status-Color $res.status)
        $memo = ''
        if ($script:Interactive -and -not $AutoOnly) {
            $a = Ask '   [Enter] 다음  [M] 메모  [F] 실패로 바꾸기  [R] 다시 검사' ''
            if ($a -match '^[rR]') { return (Run-Step $item $step) }
            if ($a -match '^[fF]') { $res.status = 'fail'; $memo = Ask '   무엇이 잘못됐나요(한 줄)' }
            elseif ($a -match '^[mM]') { $memo = Ask '   메모' }
        }
        $null = Add-Result $item $step $res $memo
        return 'ok'
    }

    if ($step.shot -eq 'tv') {
        try { $t = & $script:Checks['tv.shot'] $null; $files += @($t.files) } catch { }
    }
    $value = $null; $suggest = ''
    if ($step.value) {
        $value = Read-Value $step.value
        if ($null -ne $value) {
            $suggest = 'pass'
            if ($null -ne $step.value.max -and $value -gt [double]$step.value.max) { $suggest = 'fail' }
            if ($null -ne $step.value.min -and $value -lt [double]$step.value.min) { $suggest = 'fail' }
            Say ("   {0} = {1} → {2}" -f $step.value.label, $value, (Status-Ko $suggest)) (Status-Color $suggest)
        }
    }
    $v = Ask-Verdict $suggest
    if ($v -eq 'quit') { return 'quit' }
    $memo = ''
    if ($v -eq 'fail') { $memo = Ask '   무엇이 잘못됐나요(한 줄, 숫자·화면 문구 그대로)' }
    elseif ($script:Interactive) { $memo = Ask '   메모(없으면 Enter)' }
    $detail = if ($null -ne $value) { "$($step.value.label) = $value" } else { '사람이 확인' }
    $null = Add-Result $item $step (Res $v $detail $value $files) $memo
    return 'ok'
}

function Run-Queue($tests) {
    foreach ($id in @($script:Run.queue)) {
        $item = $tests.items | Where-Object { $_.id -eq $id } | Select-Object -First 1
        if (-not $item) { continue }
        $todo = @($item.steps | Where-Object { $r = Find-Result $item.id $_.n; -not $r -or $r.status -eq 'pending' })
        if (-not $todo.Count) { continue }
        Title "$($item.id) $($item.title)  (관련 위험: $(@($item.risks) -join ', '), 약 $($item.minutes)분)"
        if ($item.where -eq 'laptop' -and (Server-IsLocal) -and $script:Interactive) {
            Say '   이 항목은 POS기가 꺼지거나 다른 망에서 보는 시험이라 다른 노트북에서 돌리는 것이 맞습니다(README 참고).' 'Yellow'
            $a = Ask '   그래도 여기서 할까요? [y/N/s=건너뜀]' 'n'
            if ($a -notmatch '^[yY]') { foreach ($s in $todo) { $null = Add-Result $item $s (Res 'skip' '노트북에서 할 항목') }; continue }
        }
        if (@($item.needs) -contains 'admin' -and -not (Is-Admin)) { Say '   관리자 권한이 없어 일부 자동 검사가 건너뛰어질 수 있습니다.' 'Yellow' }
        foreach ($s in $todo) {
            $r = Run-Step $item $s
            if ($r -eq 'quit') { return 'quit' }
        }
    }
    return 'done'
}

# ───────────────────────── 보고서 ─────────────────────────

function MdCell([string]$s) { return ([string]$s -replace '\|', '/' -replace "`r?`n", ' ') }

function Write-Report($tests) {
    $run = $script:Run
    $res = @($run.results)
    $sb = New-Object Text.StringBuilder
    function L([string]$s = '') { [void]$sb.AppendLine($s) }
    $day = ''
    try { $day = ([datetime]::ParseExact($run.started, 'yyyy-MM-dd HH:mm:ss', $null)).ToString('M/d') } catch { $day = (Get-Date).ToString('M/d') }
    $nP = @($res | Where-Object { $_.status -eq 'pass' }).Count
    $nF = @($res | Where-Object { $_.status -eq 'fail' -or $_.status -eq 'error' }).Count
    $nS = @($res | Where-Object { $_.status -eq 'skip' -or $_.status -eq 'pending' }).Count
    L "# 하드웨어 시험 결과 $($run.id)"
    L ''
    L "- 시작 $($run.started), 끝 $($run.finished), 시험한 사람: $($run.tester)"
    L "- PC: $($run.computer). $(if ($run.pc) { $run.pc.detail })"
    L "- 서버: $($run.server) (서버 폴더 $($run.serverDir))"
    if (@($run.tvs).Count) { L ("- TV: " + ((@($run.tvs) | ForEach-Object { "$($_.name) $($_.model) 앱 $($_.version) [$($_.ip)]" }) -join ' / ')) }
    L "- 결과: 통과 $nP, 실패 $nF, 건너뜀 $nS (단계 수 기준)"
    L ''
    L '## 항목별'
    L ''
    L '| 항목 | 시험 | 관련 위험 | 통과 | 실패 | 건너뜀 | 판정 |'
    L '|---|---|---|---|---|---|---|'
    $byItem = [ordered]@{}
    foreach ($id in @($run.queue)) {
        $item = $tests.items | Where-Object { $_.id -eq $id } | Select-Object -First 1
        if (-not $item) { continue }
        $rs = @($res | Where-Object { $_.item -eq $id })
        $p = @($rs | Where-Object { $_.status -eq 'pass' -or $_.status -eq 'info' }).Count
        $f = @($rs | Where-Object { $_.status -eq 'fail' -or $_.status -eq 'error' }).Count
        $s = @($rs | Where-Object { $_.status -eq 'skip' -or $_.status -eq 'pending' }).Count
        $left = @($item.steps).Count - $rs.Count
        $verdict = if ($f) { '실패' } elseif (-not $rs.Count) { '안 함' } elseif ($s -or $left -gt 0) { '일부' } else { '통과' }
        $byItem[$id] = @{ item = $item; rs = $rs; verdict = $verdict; p = $p; f = $f; s = $s + [math]::Max(0, $left) }
        L "| $id | $(MdCell $item.title) | $(@($item.risks) -join ', ') | $p | $f | $($s + [math]::Max(0, $left)) | **$verdict** |"
    }
    L ''
    $fails = @($res | Where-Object { $_.status -eq 'fail' -or $_.status -eq 'error' })
    L "## 실패 ($($fails.Count))"
    L ''
    if (-not $fails.Count) { L '없음.'; L '' }
    foreach ($r in $fails) {
        $item = $tests.items | Where-Object { $_.id -eq $r.item } | Select-Object -First 1
        L "### $($r.item) $($r.step) — $(MdCell $r.title)"
        if ($r.status -eq 'error') { L '- **검사 스크립트 오류** (기기 문제가 아닐 수 있음, hw-test.ps1 확인 필요)' }
        if ($r.do) { L "- 한 일: $(MdCell $r.do)" }
        L "- 합격 기준: $(MdCell $r.expect)"
        L "- 결과: $(MdCell $r.detail)"
        if ($r.memo) { L "- 메모: $(MdCell $r.memo)" }
        if (@($r.files).Count) { L ("- 증거: " + ((@($r.files) | ForEach-Object { $p = Rel $_; "[$p]($p)" }) -join ', ')) }
        if ($item -and @($item.risks).Count) { L "- 관련 위험: $(@($item.risks) -join ', ')" }
        L "- 시각: $($r.at)"
        L ''
    }
    L '## 위험 점검표(docs/risk-register.md) 상태 칸에 넣을 값'
    L ''
    L 'H 표의 "상태" 칸을 아래 값으로 바꿉니다. P·K·S 번호는 점검표에 없는 시험표 전용 번호라, 실패면 새 위험 항목으로 넣을지 정합니다.'
    L ''
    L '| 번호 | 상태 |'
    L '|---|---|'
    foreach ($id in $byItem.Keys) {
        $b = $byItem[$id]
        $short = @($b.rs | Where-Object { $_.status -eq 'fail' -or $_.status -eq 'error' } | ForEach-Object {
            $t = if ($_.memo) { $_.memo } else { $_.detail }
            if ($t.Length -gt 80) { $t = $t.Substring(0, 80) + '…' }
            "$($_.step) $t"
        }) -join '; '
        $state = switch ($b.verdict) {
            '실패' { "실패 $day($short) — docs/hw-test/results/$($run.id)" }
            '통과' { "통과 $day — docs/hw-test/results/$($run.id)" }
            '일부' { "일부 확인 $day(통과 $($b.p), 남음 $($b.s)) — docs/hw-test/results/$($run.id)" }
            default { '시험 전' }
        }
        L "| $id | $(MdCell $state) |"
    }
    L ''
    L '## 개발 스레드에 보낼 글'
    L ''
    L '```text'
    if (-not $fails.Count) { L "[하드웨어 시험 $day] 실패 없음. 통과 $nP, 건너뜀 $nS. 결과 폴더 docs/hw-test/results/$($run.id)" }
    else {
        L "[하드웨어 시험 $day] 실패 $nF 건. 결과 폴더 docs/hw-test/results/$($run.id) (압축 파일 첨부)"
        foreach ($r in $fails) {
            $item = $tests.items | Where-Object { $_.id -eq $r.item } | Select-Object -First 1
            $t = if ($r.memo) { "$($r.detail) / 메모: $($r.memo)" } else { $r.detail }
            L "- $($r.item) $($r.step) $($r.title) (위험 $(@($item.risks) -join ',')): 기준 '$($r.expect)' → $t"
        }
        L ('기기: ' + $(if ($run.pc) { $run.pc.detail } else { $run.computer }))
        if (@($run.tvs).Count) { L ('TV: ' + ((@($run.tvs) | ForEach-Object { "$($_.model) 앱 $($_.version)" }) -join ' / ')) }
    }
    L '```'
    L ''
    L '## 전체 기록'
    L ''
    L '| 항목 | 단계 | 결과 | 내용 | 메모 | 증거 | 시각 |'
    L '|---|---|---|---|---|---|---|'
    foreach ($r in $res) {
        $ev = (@($r.files) | ForEach-Object { $p = Rel $_; "[$(Split-Path $p -Leaf)]($p)" }) -join ' '
        L "| $($r.item) | $($r.step) | $(Status-Ko $r.status) | $(MdCell $r.detail) | $(MdCell $r.memo) | $ev | $($r.at.Substring(5)) |"
    }
    $file = Join-Path $script:RunDir 'report.md'
    [IO.File]::WriteAllText($file, $sb.ToString(), (New-Object Text.UTF8Encoding($true)))
    return $file
}

function Zip-Run {
    $zip = Join-Path $OutRoot ($script:Run.id + '.zip')
    try {
        if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
        Compress-Archive -Path (Join-Path $script:RunDir '*') -DestinationPath $zip -Force
        return $zip
    } catch { Say "   압축하지 못했습니다: $($_.Exception.Message)" 'Yellow'; return '' }
}

function Close-AdbWindows {
    $script:AdbOpened = @(@($script:AdbOpened) + @($script:Run.adbOpened) | Where-Object { $_ } | Select-Object -Unique)
    if (-not @($script:AdbOpened).Count) { return }
    if (-not (Ensure-Login)) { Say '   로그인하지 않아 A/S 연결을 잠그지 못했습니다. 30분 안에 TV가 스스로 잠급니다.' 'Yellow'; return }
    $a = Ask "   이 시험이 연 A/S 연결(adb)을 지금 잠글까요? [Y/n]" 'y'
    if ($a -match '^[nN]') { return }
    foreach ($id in @($script:AdbOpened | Select-Object -Unique)) { $null = Api 'POST' "/api/menuboard/devices/$id/adb" @{ minutes = 0 } }
    $script:Run | Add-Member -NotePropertyName adbOpened -NotePropertyValue @() -Force; Save-Run
    Say '   A/S 연결을 잠갔습니다(TV가 15초 안에 adb를 끕니다).' 'Green'
}

# ───────────────────────── 시험표 읽기·스스로 점검 ─────────────────────────

function Load-Tests {
    $file = Join-Path $Here 'hw-tests.json'
    $t = [IO.File]::ReadAllText($file, $Utf8) | ConvertFrom-Json
    return $t
}

function Validate-Tests($tests) {
    $errs = @(); $ids = @{}
    foreach ($it in $tests.items) {
        if ($ids.ContainsKey($it.id)) { $errs += "항목 번호 겹침: $($it.id)" }
        $ids[$it.id] = 1
        $ns = @{}
        foreach ($s in $it.steps) {
            if ($ns.ContainsKey($s.n)) { $errs += "$($it.id) 단계 번호 겹침: $($s.n)" }
            $ns[$s.n] = 1
            if ($s.auto -and -not $script:Checks.ContainsKey([string]$s.auto)) { $errs += "$($it.id) $($s.n): 검사 '$($s.auto)' 없음" }
            if (-not $s.auto -and -not ([string]$s.do).Trim() -and -not $s.reboot) { $errs += "$($it.id) $($s.n): 할 일도 자동 검사도 없음" }
        }
    }
    foreach ($p in $tests.plans) { foreach ($i in $p.items) { if (-not $ids.ContainsKey($i)) { $errs += "묶음 $($p.id)에 없는 항목 $i" } } }
    return $errs
}

function Self-Test($tests) {
    $errs = @(Validate-Tests $tests)
    foreach ($e in $errs) { Say "시험표 오류: $e" 'Red' }
    New-Run
    $script:Run.tester = 'selftest'
    # 사람이 필요 없는 검사를 모두 돌려 스크립트 오류(error)가 없는지 본다. 기기 판정(pass/fail)은 상관없다.
    $safe = @('pc.info', 'win.power', 'win.updateHours', 'win.defender', 'win.antivirus', 'win.clock', 'server.health', 'server.lan', 'server.task', 'win.firewall', 'tv.list', 'tv.reported', 'tv.shot', 'load.calls', 'monitor', 'adb.info', 'net.blocked')
    $fake = [pscustomobject]@{ id = 'SELF'; title = '스스로 점검'; risks = @() }
    foreach ($c in $safe) {
        $args2 = switch ($c) {
            'tv.reported' { [pscustomobject]@{ screen = 1 } }
            'load.calls' { [pscustomobject]@{ count = 3; everyMs = 100 } }
            'monitor' { [pscustomobject]@{ hours = 0.01; everyMinutes = 0.05; callsPerHour = 600 } }
            'net.blocked' { [pscustomobject]@{ ports = @('127.0.0.1:1') } }
            default { $null }
        }
        $script:CurStep = "SELF-$c"
        try { $r = & $script:Checks[$c] $args2 } catch { $r = Res 'error' ($_.Exception.Message + ' @ ' + $_.InvocationInfo.ScriptLineNumber) }
        if ($null -eq $r -or -not ($r -is [hashtable])) { $r = Res 'error' '결과 없음' }
        Write-Host ("  {0,-18} {1,-6} {2}" -f $c, (Status-Ko $r.status), $r.detail) -ForegroundColor (Status-Color $r.status)
        $null = Add-Result $fake ([pscustomobject]@{ n = $c; do = ''; expect = ''; auto = $c }) $r
        if ($r.status -eq 'error') { $errs += "$c : $($r.detail)" }
    }
    # 사람에게 묻는 흐름을 정해 둔 답으로 한 번 돈다.
    $script:Run.queue = @('H-27', 'H-19')
    foreach ($ans in @('', 'p', '', 'f', '리모컨이 안 닿음', '', 'p', '', '42', '', 's', '', 'q')) { $script:Answers.Enqueue($ans) }
    $script:Interactive = $true
    try { $null = Run-Queue $tests } catch { $errs += "진행 흐름 오류: $($_.Exception.Message) @ $($_.InvocationInfo.ScriptLineNumber)" }
    $script:Interactive = $false
    $script:Answers.Clear()
    $script:Run.queue = @('SELF') + @($script:Run.queue)
    $script:Run.finished = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $script:Run.state = 'done'
    Save-Run
    try {
        $rep = Write-Report $tests
        $txt = [IO.File]::ReadAllText($rep, $Utf8)
        foreach ($need in @('## 항목별', '## 실패', '## 위험 점검표', '## 개발 스레드에 보낼 글', '| H-19 |')) { if ($txt.IndexOf($need) -lt 0) { $errs += "보고서에 '$need' 없음" } }
        $zip = Zip-Run
        if (-not $zip -or -not (Test-Path -LiteralPath $zip)) { $errs += '압축 파일이 없음' }
        Say "보고서: $rep"
    } catch { $errs += "보고서 오류: $($_.Exception.Message) @ $($_.InvocationInfo.ScriptLineNumber)" }
    if ($errs.Count) { foreach ($e in $errs) { Say "오류: $e" 'Red' }; exit 1 }
    Say '스스로 점검 통과' 'Green'
    exit 0
}

# ───────────────────────── 시작 ─────────────────────────

$tests = Load-Tests
$script:AdbExe = Find-Adb
if ($SelfTest) { Self-Test $tests }

if ($Report) {
    Load-Run (Resolve-Path -LiteralPath $Report).Path
    $f = Write-Report $tests
    Say "보고서를 다시 만들었습니다: $f" 'Green'
    exit 0
}

Write-Host ''
Write-Host '  디지털 메뉴판 하드웨어 시험 도우미' -ForegroundColor Cyan
Say "  서버 $Server · adb $(if ($script:AdbExe) { $script:AdbExe } else { '없음' }) · 관리자 권한 $(Is-Admin)"
$errs = @(Validate-Tests $tests)
if ($errs.Count) { foreach ($e in $errs) { Say "  시험표 오류: $e" 'Red' } }

# 이어 할 시험 찾기
$pendingDir = ''
if (Test-Path -LiteralPath $OutRoot) {
    $last = Get-ChildItem -LiteralPath $OutRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'run.json') } | Select-Object -First 1
    if ($last) {
        $st = ([IO.File]::ReadAllText((Join-Path $last.FullName 'run.json'), $Utf8) | ConvertFrom-Json).state
        if ($st -ne 'done') { $pendingDir = $last.FullName }
    }
}
if ($pendingDir -and -not $Resume) {
    $a = Ask "  끝나지 않은 시험이 있습니다($(Split-Path $pendingDir -Leaf)). 이어 할까요? [Y/n]" 'y'
    if ($a -notmatch '^[nN]') { $Resume = $true }
}

if ($Resume -and $pendingDir) {
    Load-Run $pendingDir
    $script:Run.state = 'running'
    Say "  이어 합니다: $($script:Run.id)" 'Green'
} else {
    New-Run
    if ($Only.Count) { $queue = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }) }
    elseif ($Plan) { $queue = @(($tests.plans | Where-Object { $_.id -eq $Plan }).items) }
    else {
        Title '무엇을 할까요?'
        foreach ($p in $tests.plans) { Say ("   [{0}] {1}  ({2}) — {3}" -f $p.id, $p.title, $p.day, (@($p.items) -join ' ')) }
        Say '   [A] 자동 검사만 빠르게(POS기 설정·서버·TV 상태, 5분)'
        Say '   [H] 항목 번호로 고르기 (예: H-13,H-3)'
        Say '   [M] 연속 운영 기록 시작(H-5, 72시간)'
        $c = Ask '   고르세요' 'A'
        if ($c -match '^[aA]') { $AutoOnly = $true; $queue = @('P-3', 'P-4', 'H-25', 'H-27', 'H-12', 'H-11', 'H-29') }
        elseif ($c -match '^[hH]') { $queue = @((Ask '   항목 번호(쉼표로)') -split ',' | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }) }
        elseif ($c -match '^[mM]') { $queue = @('H-5') }
        else { $queue = @(($tests.plans | Where-Object { $_.id -eq $c }).items) }
    }
    $unknown = @($queue | Where-Object { $id = $_; -not ($tests.items | Where-Object { $_.id -eq $id }) })
    if ($unknown.Count) { Say "  모르는 항목 번호: $($unknown -join ', ')" 'Yellow' }
    $script:Run.queue = @($queue | Where-Object { $id = $_; $tests.items | Where-Object { $_.id -eq $id } })
    if (-not @($script:Run.queue).Count) { Say '  할 항목이 없습니다.' 'Red'; exit 1 }
    $script:Run.tester = Ask '  시험하는 사람 이름(보고서에 적음)' ''
    try { $pc = & $script:Checks['pc.info'] $null; $script:Run.pc = [pscustomobject]@{ detail = $pc.detail; value = $pc.value } } catch { }
    Save-Run
}

Say "  결과 폴더: $script:RunDir" 'DarkGray'
if (-not (Server-Up)) { Say "  서버 $Server 가 지금 응답하지 않습니다(서버를 끄는 시험이면 괜찮음)." 'Yellow' }

$outcome = 'quit'
try { $outcome = Run-Queue $tests }
finally {
    if ($outcome -eq 'done') { $script:Run.state = 'done'; $script:Run.finished = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }
    if ($script:Run.state -ne 'reboot' -and $script:IsWindows) {
        # 다시 켜기 단계에서 남긴 '로그인 때 이어 하기' 등록을 지운다(시험한 POS기를 그대로 출고해도 창이 뜨지 않게)
        Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'MenuBoardHwTest' -ErrorAction SilentlyContinue
    }
    elseif ($script:Run.state -ne 'reboot') { $script:Run.state = 'paused' }
    Save-Run
    try { Close-AdbWindows } catch { }
    $rep = Write-Report $tests
    $zip = if ($outcome -eq 'done') { Zip-Run } else { '' }
    Title '끝'
    Say "  보고서: $rep" 'Green'
    if ($zip) { Say "  압축 파일: $zip  ← 이 파일을 Claude 스레드에 올리면 점검표와 개발 스레드에 반영합니다." 'Green' }
    else { Say '  아직 끝나지 않았습니다. run-hw-test.bat 을 다시 실행하면 이어 합니다.' 'Yellow' }
    $nF = @($script:Run.results | Where-Object { $_.status -eq 'fail' -or $_.status -eq 'error' }).Count
    if ($nF) { Say "  실패 $nF 건 — 보고서의 '실패'와 '개발 스레드에 보낼 글'을 보세요." 'Red' }
    if ($script:Interactive -and $script:IsWindows) { try { Start-Process notepad.exe -ArgumentList "`"$rep`"" } catch { } }
}
