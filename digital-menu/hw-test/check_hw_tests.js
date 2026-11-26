// 하드웨어 시험표(hw-tests.json)를 검사하고, 사람이 인쇄해 쓰는 시험표(docs/hw-test/시험표.md)를 만든다.
//   node check_hw_tests.js          검사만(시험표.md 가 json과 다르면 실패)
//   node check_hw_tests.js --write  시험표.md 를 다시 만든다
// P·N·S 는 이 시험표에만 있는 번호(키패드 앱의 K 번호는 docs/order-app.md).
// 검사: 번호 겹침, 묶음이 없는 항목을 가리키는지, 자동 검사 이름이 hw-test.ps1 에 있는지,
//       위험 점검표의 H 항목이 모두 시험표에 있는지, .ps1 BOM·.bat ASCII.
const fs = require('fs')
const path = require('path')

const here = __dirname
const tests = JSON.parse(fs.readFileSync(path.join(here, 'hw-tests.json'), 'utf8'))
const ps1 = fs.readFileSync(path.join(here, 'hw-test.ps1'), 'utf8')
const register = fs.readFileSync(path.join(here, '..', 'docs', 'risk-register.md'), 'utf8')
const outFile = path.join(here, '..', 'docs', 'hw-test', '시험표.md')
const errors = []

const checks = new Set([...ps1.matchAll(/\$script:Checks\['([^']+)'\]\s*=/g)].map((m) => m[1]))
const ids = new Set()
for (const it of tests.items) {
  if (ids.has(it.id)) errors.push(`항목 번호 겹침: ${it.id}`)
  ids.add(it.id)
  if (!/^[HPNS]-\d+$/.test(it.id)) errors.push(`항목 번호 형식: ${it.id}`)
  const ns = new Set()
  for (const s of it.steps) {
    if (ns.has(s.n)) errors.push(`${it.id} 단계 번호 겹침: ${s.n}`)
    ns.add(s.n)
    if (s.auto && !checks.has(s.auto)) errors.push(`${it.id} ${s.n}: 자동 검사 '${s.auto}' 가 hw-test.ps1 에 없음`)
    if (!s.auto && !(s.do || '').trim() && !s.reboot) errors.push(`${it.id} ${s.n}: 할 일도 자동 검사도 없음`)
    if (s.value && s.value.max === undefined && s.value.min === undefined) errors.push(`${it.id} ${s.n}: value 에 max/min 없음`)
  }
}
const planned = new Set()
for (const p of tests.plans) for (const i of p.items) {
  if (!ids.has(i)) errors.push(`묶음 ${p.id}: 없는 항목 ${i}`)
  planned.add(i)
}
for (const i of ids) if (!planned.has(i)) errors.push(`어느 묶음에도 없는 항목: ${i}`)

// 위험 점검표의 H 항목이 시험표에 모두 있어야 한다(점검표에 새 H가 생기면 여기서 알린다).
const regH = [...register.matchAll(/^\| (H-\d+) \|/gm)].map((m) => m[1])
for (const h of regH) if (!ids.has(h)) errors.push(`위험 점검표의 ${h} 가 hw-tests.json 에 없음`)
const notInRegister = [...ids].filter((i) => i.startsWith('H-') && !regH.includes(i))

for (const f of fs.readdirSync(here)) {
  const b = fs.readFileSync(path.join(here, f))
  if (f.endsWith('.ps1') && !(b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf)) errors.push(`${f}: UTF-8 BOM 없음`)
  if (f.endsWith('.bat') && b.some((x) => x >= 0x80)) errors.push(`${f}: bat 파일에 한글(ASCII 아닌 글자)이 있음`)
}

// ── 인쇄용 시험표 ──
const ko = { pos: 'POS기', laptop: '다른 노트북', dev: '개발 PC', any: '어디서나' }
const autoNote = (a) => `자동 \`${a}\``
let md = ''
md += '# 하드웨어 시험표 (11/30~12/10)\n\n'
md += '> 이 파일은 `digital-menu/hw-test/hw-tests.json` 에서 만든 것입니다(`node check_hw_tests.js --write`). 고칠 때는 json을 고칩니다.\n'
md += '> 시험은 POS기에서 `digital-menu/hw-test/run-hw-test.bat` 을 더블클릭해 진행하면 결과가 자동으로 저장됩니다. 이 표는 인쇄해 옆에 두거나 스크립트 없이 손으로 할 때 씁니다.\n\n'
md += '- **자동**: 스크립트가 직접 검사합니다. **사람**: 보고 통과/실패를 고릅니다. **값**: 숫자를 적습니다(Enter만 누르면 초시계).\n'
md += '- H 번호는 `docs/risk-register.md` 하드웨어 시험 표와 같습니다. P(준비)·N(번호 처리·키패드)·S(판매 프로그램과 함께)는 이 시험표에만 있습니다.\n\n'
md += '## 시험 순서\n\n| 묶음 | 날짜 | 내용 | 항목 |\n|---|---|---|---|\n'
for (const p of tests.plans) md += `| ${p.id} | ${p.day} | ${p.title} | ${p.items.join(', ')} |\n`
md += '\n'
for (const p of tests.plans) {
  md += `## 묶음 ${p.id}. ${p.title} (${p.day})\n\n`
  for (const id of p.items) {
    const it = tests.items.find((x) => x.id === id)
    md += `### ${it.id} ${it.title}\n\n`
    md += `- 관련 위험: ${it.risks.length ? it.risks.join(', ') : '없음'} · 하는 곳: ${ko[it.where] || it.where} · 약 ${it.minutes >= 120 ? Math.round(it.minutes / 60) + '시간' : it.minutes + '분'}`
    if (it.needs && it.needs.length) md += ` · 필요: ${it.needs.map((n) => ({ server: '서버 켜짐', login: '매장 계정', adb: 'adb', admin: '관리자 권한' }[n] || n)).join(', ')}`
    md += '\n\n| 단계 | 할 일 | 합격 기준 | 방식 | 결과 | 메모 |\n|---|---|---|---|---|---|\n'
    for (const s of it.steps) {
      const how = s.reboot ? '다시 켜기' : s.auto ? autoNote(s.auto) : s.value ? `값: ${s.value.label}` : '사람'
      const cell = (t) => String(t || '').replace(/\|/g, '/').replace(/\n/g, ' ')
      md += `| ${s.n} | ${cell(s.do) || '(자동)'} | ${cell(s.expect)} | ${how} | ☐통과 ☐실패 | |\n`
    }
    md += '\n'
  }
}
md += '## 자동 검사가 보는 것\n\n'
const what = {
  'build.apk': 'APK와 board-app.json 이 있고 sha256이 맞는지, 버전',
  'server.health': '/api/health, admin.html, devices.html, 메뉴판 주소가 응답하는지, start-server.bat 창이 같이 켜져 있지 않은지',
  'server.lan': 'POS기의 공유기 쪽 IPv4 주소마다 8090이 응답하는지, 네트워크 프로필(개인/공용), TV에 넣을 주소',
  'server.task': "작업 스케줄러 'MenuBoardServer' 가 SYSTEM·컴퓨터 시작 때 실행 중인지, pocketbase.exe 가 SYSTEM으로 하나만 도는지",
  'server.killRecover': 'pocketbase.exe 를 강제로 끄고 다시 응답할 때까지 초',
  'server.waitUp': '서버가 꺼졌다가(정전·작업 멈춤) 다시 응답할 때까지 초',
  'win.bootToServer': 'Windows가 켜진 시각과 서버 로그의 첫 "서버를 켭니다" 시각의 차이',
  'win.firewall': "'MenuBoard' 방화벽 규칙이 켜져 있고 같은 망(LocalSubnet)만, pocketbase.exe 차단 규칙이 없는지",
  'win.power': '전원 연결 시 절전·최대 절전·디스크 끄기 0, 빠른 시작 꺼짐',
  'win.updateHours': '업데이트 사용 시간 정책 7~24시, 로그인 중 자동 재시작 안 함',
  'win.defender': 'Defender 검사 예외에 서버 폴더',
  'win.antivirus': '보안 센터에 등록된 백신 목록(기록만)',
  'win.folderAcl': '일반 사용자(Users·Everyone 등)가 서버 폴더·run-server.ps1·pocketbase.exe·data.db에 쓸 권한이 없는지',
  'win.clock': 'POS기·서버·TV 시계 차이(60초 이하), w32tm 상태',
  'server.backups': 'pb_data 크기, 백업 개수·크기, C 빈 공간이 백업 10개를 감당하는지',
  'pos.resources': '정해진 시간 동안 CPU·남은 메모리·pocketbase 메모리(CSV 저장)',
  'tv.list': 'TV 관리 목록: 켜짐(45초 안 보고), 버전, 화면·배율·방향·밝기, 알림·USB 결과',
  'tv.shot': 'TV 원격 캡처를 요청해 사진을 저장(adb 필요 없음)',
  'tv.waitOnline': 'TV가 꺼졌다가 다시 보고할 때까지 초',
  'tv.reported': 'TV가 보고한 설정값이 기대값과 같은지',
  'tv.openAdb': 'A/S 연결(adb)을 정해진 분만큼 열고 네트워크 adb로 붙기(필요하면 A/S 관리자 로그인)',
  'adb.info': '보드 모델·칩·안드로이드·해상도·ro.adb.secure·/data 빈 공간·온도(getprop 전체 저장)',
  'adb.app': '앱 버전, WRITE_SECURE_SETTINGS·다른 앱 위에 표시 등 권한',
  'adb.home': '홈 앱 지정 여부와 맨 앞 화면',
  'adb.crash': '이번 부팅 뒤 메뉴판 앱 꺼짐(FATAL) 기록, logcat 저장',
  'adb.shot': 'adb로 TV 화면 캡처',
  'adb.mem': '메뉴판 앱 메모리(PSS)와 TV 남은 메모리',
  'adb.wifi': 'TV 와이파이 신호(dBm)',
  'adb.foreign': '한 번도 허용받지 않은 새 adb 키로 붙을 때 거부되는지',
  'net.blocked': '이 PC에서 POS기 8090·TV 5555로 TCP 연결이 막히는지',
  'load.calls': '시험 번호를 정해진 수만큼 부르고 응답 시간',
  monitor: '연속 기록: 정해진 분마다 서버 응답·pocketbase 메모리·C 빈 공간·pb_data 크기·TV 보고·TV 앱 메모리·온도, 번호 부르기(CSV)',
}
md += '| 검사 | 보는 것 |\n|---|---|\n'
for (const c of [...checks].filter((c) => c !== 'pc.info')) {
  if (!what[c]) errors.push(`시험표.md 설명이 없는 검사: ${c}`)
  md += `| \`${c}\` | ${what[c] || ''} |\n`
}
md += '\n'

const write = process.argv.includes('--write')
fs.mkdirSync(path.dirname(outFile), { recursive: true })
if (write) fs.writeFileSync(outFile, md)
else if (!fs.existsSync(outFile) || fs.readFileSync(outFile, 'utf8') !== md) errors.push('docs/hw-test/시험표.md 가 hw-tests.json 과 다름(node check_hw_tests.js --write)')

const steps = tests.items.reduce((n, it) => n + it.steps.length, 0)
const autos = tests.items.reduce((n, it) => n + it.steps.filter((s) => s.auto).length, 0)
console.log(`항목 ${tests.items.length}개, 단계 ${steps}개(자동 ${autos}), 자동 검사 ${checks.size}종, 점검표 H ${regH.length}개`)
if (notInRegister.length) console.log(`참고: 점검표(이 브랜치)에 아직 없는 H: ${notInRegister.join(', ')} (PR #11·#12 병합 뒤 들어옴)`)
if (errors.length) {
  for (const e of errors) console.log('실패: ' + e)
  process.exit(1)
}
console.log('통과')
