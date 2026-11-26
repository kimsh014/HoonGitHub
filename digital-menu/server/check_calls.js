// 키패드 앱이 쓰는 번호 호출 경로(/api/menuboard/pos/calls)를 검사한다. 사용: node check_calls.js
// 임시 폴더로 빈 서버(127.0.0.1:8096)를 잠깐 띄워 검사하므로 켜 둔 서버(8090)나 샘플 매장은 건드리지 않는다.
// 확인하는 것: 연동 키로만 됨(로그인 없이, B-12), 부르기·다시 부르기·취소, 3초 안 같은 번호는 한 번(M-15),
// 틀린 번호 막기, 가맹점은 자기 매장 번호만, 그리고 TV 화면(board.js)이 새로고침 없이 바로 번호를 그림.
const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')

// Node 22~24는 EventSource(실시간 구독)를 플래그 뒤에 두었다. 없으면 플래그를 붙여 자기 자신을 다시 실행한다.
if (typeof EventSource === 'undefined') {
  const r = spawnSync(process.execPath, ['--experimental-eventsource', '--no-warnings', __filename], { stdio: 'inherit' })
  process.exit(r.status)
}

const BASE = 'http://127.0.0.1:8096'
const PB = process.env.POCKETBASE || path.join(__dirname, 'pocketbase.exe')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function call(method, url, body, headers = {}) {
  const res = await fetch(BASE + url, {
    method,
    headers: { ...headers, ...(body && { 'Content-Type': 'application/json' }) },
    body: body && JSON.stringify(body),
  })
  const text = await res.text()
  return { status: res.status, data: text ? JSON.parse(text) : {} }
}
async function ok(what, ...args) {
  const r = await call(...args)
  assert.ok(r.status < 300, `${what}: ${r.status} ${JSON.stringify(r.data)}`)
  return r.data
}
async function fails(what, status, ...args) {
  const r = await call(...args)
  assert.strictEqual(r.status, status, `${what}: ${status}이어야 하는데 ${r.status} ${JSON.stringify(r.data)}`)
  return r.data
}
const auth = (token) => ({ Authorization: token })
const posKey = (key) => ({ 'X-POS-Key': key })

// 보드 화면: 브라우저 대신 board.js가 쓰는 것만 흉내 내고, 진짜 api.js가 진짜 서버를 부르게 한다.
const drawn = [] // renderBoard가 받은 메뉴판
function startBoard(storeId) {
  const kept = {}
  global.window = global
  global.MENU_API_BASE = BASE
  Object.defineProperty(global, 'localStorage', {
    configurable: true,
    value: { getItem: (k) => kept[k] ?? null, setItem: (k, v) => { kept[k] = v }, removeItem: (k) => { delete kept[k] } },
  })
  global.location = { search: '?screen=1&store=' + storeId }
  global.document = {
    documentElement: { style: { setProperty() {} } },
    createElement: () => ({ style: {}, remove() {} }),
    body: { appendChild() {} },
    images: [],
  }
  global.renderBoard = (board) => drawn.push(board)
  require('./pb_public/api.js')
  require('./pb_public/board.js')
}
// 보드가 마지막으로 그린 메뉴 하나
const onBoard = (name) => drawn[drawn.length - 1].items.find((m) => m.name === name)
// fn()을 한 뒤 보드가 5초 안에 다시 그려 check를 만족해야 한다
async function boardShows(what, fn, check) {
  const before = drawn.length
  const t0 = Date.now()
  await fn()
  while (!(drawn.length > before && check())) {
    assert.ok(Date.now() - t0 < 5000, `${what}: 보드가 5초 안에 다시 그리지 않음`)
    await sleep(50)
  }
  console.log(`  보드 반영 ${Date.now() - t0}ms: ${what}`)
}


const onBoardCalls = () => drawn[drawn.length - 1].calls

async function main() {
  await ok('첫 설치', 'POST', '/api/menuboard/setup', { email: 'owner@menu.test', password: 'password-1234', storeName: '번호가게' })
  const login = await ok('로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'owner@menu.test', password: 'password-1234' })
  const owner = auth(login.token)
  const sid = login.record.store
  await ok('번호 화면', 'POST', '/api/collections/screens/records', { store: sid, no: 1, type: 'calls' }, owner)
  const key = (await ok('키 만들기', 'POST', '/api/menuboard/pos/key', null, owner)).key

  // ── 키 없이는 못 부름 ──
  await fails('키 없이 목록', 401, 'GET', '/api/menuboard/pos/calls')
  await fails('키 없이 부르기', 401, 'POST', '/api/menuboard/pos/calls', { number: 1 })
  await fails('틀린 키로 부르기', 401, 'POST', '/api/menuboard/pos/calls', { number: 1 }, posKey('mbpos_wrong'))
  const k = posKey(key)
  const send = (number, action) => ok(`${action || 'call'} ${number}`, 'POST', '/api/menuboard/pos/calls', { number, action }, k)

  startBoard(sid)
  for (let i = 0; !drawn.length; i++) { assert.ok(i < 100, '보드가 처음 화면을 그리지 않음'); await sleep(50) }
  await sleep(500)
  assert.deepStrictEqual(onBoardCalls(), [])

  // ── 부르기 ──
  let r
  await boardShows('12번 부르기', async () => {
    r = await send(12)
    assert.strictEqual(r.result, 'called')
    assert.strictEqual(r.number, 12)
    assert.deepStrictEqual(r.calls.map((c) => c.number), [12])
    assert.ok(Math.abs(r.calls[0].at - Date.now()) < 5000, '부른 시각이 이상함: ' + r.calls[0].at)
  }, () => onBoardCalls()[0] === 12)
  r = await send('13') // 글자로 와도 숫자면 받음
  assert.strictEqual(r.result, 'called')
  assert.deepStrictEqual(r.calls.map((c) => c.number), [13, 12])

  // ── 3초 안에 같은 번호는 한 번 ──
  r = await send(13)
  assert.strictEqual(r.result, 'ignored')
  assert.deepStrictEqual(r.calls.map((c) => c.number), [13, 12])
  // 다시 부르기는 바로 해도 맨 앞으로
  r = await send(12, 'recall')
  assert.strictEqual(r.result, 'called')
  assert.deepStrictEqual(r.calls.map((c) => c.number), [12, 13])
  await sleep(3200)
  r = await send(13) // 3초 지나면 다시 부를 수 있음(맨 앞으로)
  assert.strictEqual(r.result, 'called')
  assert.deepStrictEqual(r.calls.map((c) => c.number), [13, 12])

  // 못 보낸 번호 다시 보내기(retry): 이미 TV에 있으면 다시 띄우지 않음, 없으면 부름
  r = await ok('retry 13', 'POST', '/api/menuboard/pos/calls', { number: 13, retry: true }, k)
  assert.strictEqual(r.result, 'ignored')
  r = await ok('retry 14', 'POST', '/api/menuboard/pos/calls', { number: 14, retry: true }, k)
  assert.strictEqual(r.result, 'called')
  r = await send(14, 'cancel')

  // ── 취소 ──
  await boardShows('13번 취소', async () => {
    r = await send(13, 'cancel')
    assert.strictEqual(r.result, 'removed')
    assert.deepStrictEqual(r.calls.map((c) => c.number), [12])
  }, () => onBoardCalls().join() === '12')
  r = await send(13, 'cancel')
  assert.strictEqual(r.result, 'absent')

  // ── 틀린 요청 ──
  for (const [what, body] of [['0번', { number: 0 }], ['10000번', { number: 10000 }], ['소수', { number: 1.5 }],
    ['번호 없음', {}], ['글자', { number: 'abc' }], ['모르는 action', { number: 5, action: 'delete' }]]) {
    await fails(what, 400, 'POST', '/api/menuboard/pos/calls', body, k)
  }
  const list = await ok('목록', 'GET', '/api/menuboard/pos/calls', null, k)
  assert.deepStrictEqual(list.store, { id: sid, name: '번호가게' })
  assert.deepStrictEqual(list.calls.map((c) => c.number), [12])

  // ── 가맹점: 자기 매장 번호만 ──
  const su = await ok('관리자 로그인', 'POST', '/api/collections/_superusers/auth-with-password', { identity: 'admin@menu.test', password: 'password-1234' })
  const admin = auth(su.token)
  const hq = await ok('본사', 'POST', '/api/collections/stores/records', { kind: 'hq', name: '본사' }, admin)
  const branch = await ok('가맹점', 'POST', '/api/collections/stores/records', { kind: 'franchise', name: '1호점', parent: hq.id }, admin)
  await ok('가맹점 계정', 'POST', '/api/collections/users/records',
    { email: 'branch@menu.test', password: 'password-1234', passwordConfirm: 'password-1234', store: branch.id }, admin)
  const bl = await ok('가맹점 로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'branch@menu.test', password: 'password-1234' })
  const bk = posKey((await ok('가맹점 키', 'POST', '/api/menuboard/pos/key', null, auth(bl.token))).key)
  r = await ok('가맹점 12번', 'POST', '/api/menuboard/pos/calls', { number: 12 }, bk)
  assert.strictEqual(r.result, 'called') // 다른 매장의 12번과 겹치지 않음
  assert.deepStrictEqual(r.calls.map((c) => c.number), [12])
  r = await ok('가맹점 77번', 'POST', '/api/menuboard/pos/calls', { number: 77 }, bk)
  assert.deepStrictEqual((await ok('본 매장 목록', 'GET', '/api/menuboard/pos/calls', null, k)).calls.map((c) => c.number), [12])
  await ok('가맹점이 남의 번호 취소 시도', 'POST', '/api/menuboard/pos/calls', { number: 12, action: 'cancel' }, bk)
  assert.deepStrictEqual((await ok('본 매장 목록', 'GET', '/api/menuboard/pos/calls', null, k)).calls.map((c) => c.number), [12])
  const seen = drawn.length
  await send(12, 'recall') // 보드가 다시 그리게 한 뒤 확인
  for (let i = 0; drawn.length === seen; i++) { assert.ok(i < 100, '보드가 다시 그리지 않음'); await sleep(50) }
  assert.deepStrictEqual(onBoardCalls(), [12], '다른 매장 번호가 TV에 뜸')
}

async function run() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'menuboard-calls-'))
  const dirs = ['migrations', 'hooks', 'public'].flatMap((d) => [`--${d}Dir`, path.join(__dirname, `pb_${d}`)])
  const su = spawnSync(PB, ['superuser', 'upsert', 'admin@menu.test', 'password-1234', '--dir', dir, ...dirs], { encoding: 'utf8' })
  assert.strictEqual(su.status, 0, `관리자 계정 만들기 실패 (${PB}): ${su.stderr || su.error}`)
  const pb = spawn(PB, ['serve', '--http', '127.0.0.1:8096', '--dir', dir, ...dirs], { stdio: 'ignore' })
  let failed = false
  try {
    for (let i = 0; ; i++) {
      if (await fetch(`${BASE}/api/health`).then((x) => x.ok, () => false)) break
      assert.ok(i < 100, '임시 서버가 10초 안에 뜨지 않음')
      await sleep(100)
    }
    await main()
    console.log('OK: 키패드 번호 호출(부르기·다시·취소·3초 중복·틀린 번호·가맹점 구분)과 TV 바로 반영 모두 설계대로입니다.')
  } catch (err) {
    failed = true
    console.error(err)
  } finally {
    pb.kill()
    await new Promise((x) => pb.once('exit', x))
    fs.rmSync(dir, { recursive: true, force: true })
  }
  process.exit(failed ? 1 : 0)
}
run()
