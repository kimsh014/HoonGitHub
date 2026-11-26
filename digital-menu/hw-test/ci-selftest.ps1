# hw-test.ps1 을 실제 기기 없이 점검한다(GitHub Actions의 Windows, Windows PowerShell 5.1).
# 1) digital-menu 아래 모든 .ps1 이 문법 오류 없이 읽히는지, 한글이 있으면 UTF-8 BOM이 있는지
# 2) 임시 PocketBase 서버에 매장·가짜 TV를 만들고 hw-test.ps1 -SelfTest 로 자동 검사·보고서 흐름을 돌린다
#    가짜 TV는 15초 보고 대신 2초마다 보고하고, 화면 캡처 요청이 오면 작은 JPEG를 올린다.
# 사용: powershell -NoProfile -ExecutionPolicy Bypass -File ci-selftest.ps1 -Pb C:\pb\pocketbase.exe
param([Parameter(Mandatory = $true)][string]$Pb, [int]$Port = 8097)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Root = (Resolve-Path (Join-Path $Here '..')).Path
$Srv = Join-Path $Root 'server'
$fail = 0

Write-Host '== 1. PowerShell 문법·BOM'
foreach ($f in Get-ChildItem -LiteralPath $Root -Recurse -Filter '*.ps1') {
    $tokens = $null; $errs = $null
    [void][Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errs)
    $bytes = [IO.File]::ReadAllBytes($f.FullName)
    $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $nonAscii = @($bytes | Where-Object { $_ -ge 0x80 }).Count -gt 0
    if ($errs) { foreach ($e in $errs) { Write-Host "  오류 $($f.Name):$($e.Extent.StartLineNumber) $($e.Message)" -ForegroundColor Red }; $fail++ }
    elseif ($nonAscii -and -not $bom) { Write-Host "  오류 $($f.Name): 한글이 있는데 UTF-8 BOM이 없음(PowerShell 5.1이 깨뜨림)" -ForegroundColor Red; $fail++ }
    else { Write-Host "  통과 $($f.FullName.Substring($Root.Length + 1))" }
}

Write-Host '== 2. 임시 서버'
$data = Join-Path $env:TEMP ('pb-hwtest-' + [guid]::NewGuid().ToString('N'))
$dirs = @('--migrationsDir', (Join-Path $Srv 'pb_migrations'), '--hooksDir', (Join-Path $Srv 'pb_hooks'), '--publicDir', (Join-Path $Srv 'pb_public'))
& $Pb superuser upsert 'as@poswing.local' 'ci-password-12345' --dir $data @dirs | Out-Host
$pbLog = Join-Path $env:TEMP 'pb-hwtest.log'
$proc = Start-Process -FilePath $Pb -ArgumentList (@('serve', '--dev', '--http', "127.0.0.1:$Port", '--dir', $data) + $dirs) -PassThru -WindowStyle Hidden -RedirectStandardOutput $pbLog -RedirectStandardError "$pbLog.err"
function Show-PbLog { foreach ($f in @($pbLog, "$pbLog.err")) { if (Test-Path $f) { Get-Content $f -Encoding UTF8 | Select-Object -Last 40 | Out-Host } } }
$base = "http://127.0.0.1:$Port"
$up = $false
for ($i = 0; $i -lt 40; $i++) { try { $null = Invoke-WebRequest "$base/api/health" -UseBasicParsing -TimeoutSec 2; $up = $true; break } catch { Start-Sleep -Milliseconds 500 } }
if (-not $up) { Write-Host '서버가 뜨지 않음' -ForegroundColor Red; exit 1 }

function J($o) { return [Text.Encoding]::UTF8.GetBytes(($o | ConvertTo-Json -Depth 5 -Compress)) }
try {
    $null = Invoke-RestMethod "$base/api/menuboard/setup" -Method Post -ContentType 'application/json; charset=utf-8' -Body (J @{ storeName = '시험매장'; email = 'owner@menu.test'; password = 'password-1234' })
    $reg = Invoke-RestMethod "$base/api/menuboard/devices/register" -Method Post -ContentType 'application/json; charset=utf-8' -Body (J @{ name = 'CI TV'; model = 'ci-rk3568'; version = '1.1' })
} catch {
    Write-Host "준비 요청 실패: $($_.Exception.Message) $($_.ErrorDetails.Message)" -ForegroundColor Red
    Show-PbLog
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "  매장·가짜 TV 만듦 ($($reg.id))"

$tv = Start-Job -ArgumentList $base, $reg.token -ScriptBlock {
    param($base, $token)
    $jpg = [Convert]::FromBase64String('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=')
    $h = @{ 'X-Device-Token' = $token }
    $lastShot = $null
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalMinutes -lt 10) {
        try {
            $body = @{ version = '1.1'; model = 'ci-rk3568'; reported = @{ server = '127.0.0.1'; screen = 1; zoom = 100; rotation = 0; brightness = -1; adb = $false; canAdb = $true; rev = 0; usb = ''; note = ''; width = 1920; height = 1080 } }
            $o = Invoke-RestMethod "$base/api/menuboard/devices/report" -Method Post -Headers $h -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 5 -Compress)))
            if ($null -eq $lastShot) { $lastShot = $o.shotRev }
            elseif ($o.shotRev -gt $lastShot) {
                $lastShot = $o.shotRev
                $null = Invoke-RestMethod "$base/api/menuboard/devices/shot" -Method Post -Headers $h -ContentType 'image/jpeg' -Body $jpg
            }
        } catch { }
        Start-Sleep -Seconds 2
    }
}

Write-Host '== 3. hw-test.ps1 -SelfTest'
$env:HWTEST_EMAIL = 'owner@menu.test'
$env:HWTEST_PASSWORD = 'password-1234'
$out = Join-Path $env:TEMP ('hwtest-out-' + [guid]::NewGuid().ToString('N'))
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here 'hw-test.ps1') -SelfTest -Server $base -ServerDir $Srv -OutRoot $out
$code = $LASTEXITCODE
if ($code -ne 0) { $fail++; Show-PbLog }

# 가짜 TV가 있으니 TV 검사는 통과해야 한다(검사 코드가 API와 맞는지).
$run = Get-ChildItem -LiteralPath $out -Directory | Select-Object -First 1
if ($run) {
    $json = [IO.File]::ReadAllText((Join-Path $run.FullName 'run.json'), [Text.Encoding]::UTF8) | ConvertFrom-Json
    foreach ($need in @('server.health', 'tv.list', 'tv.reported', 'tv.shot', 'load.calls', 'monitor')) {
        $r = $json.results | Where-Object { $_.step -eq $need } | Select-Object -First 1
        if (-not $r -or $r.status -ne 'pass') { Write-Host "  실패: $need → $($r.status) $($r.detail)" -ForegroundColor Red; $fail++ }
        else { Write-Host "  통과: $need" }
    }
    $shots = @(Get-ChildItem -LiteralPath (Join-Path $run.FullName 'evidence') -Filter '*.jpg')
    if (-not $shots.Count) { Write-Host '  실패: TV 캡처 사진이 저장되지 않음' -ForegroundColor Red; $fail++ }
    Write-Host '---- report.md ----'
    Get-Content -LiteralPath (Join-Path $run.FullName 'report.md') -Encoding UTF8 | Select-Object -First 60 | Out-Host
    if ($env:GITHUB_WORKSPACE) { Copy-Item -LiteralPath $out -Destination (Join-Path $env:GITHUB_WORKSPACE 'hwtest-selftest') -Recurse -Force }
} else { Write-Host '  실패: 결과 폴더가 없음' -ForegroundColor Red; $fail++ }

Stop-Job $tv -ErrorAction SilentlyContinue; Remove-Job $tv -Force -ErrorAction SilentlyContinue
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
if ($fail) { Write-Host "실패 $fail 건" -ForegroundColor Red; exit 1 }
Write-Host '모두 통과' -ForegroundColor Green
exit 0
