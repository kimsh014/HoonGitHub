// POS·키오스크 연동(pb_hooks/pos.pb.js)을 검사한다. 사용: node check_pos.js
// 임시 폴더로 빈 서버(127.0.0.1:8092)를 잠깐 띄워 검사하므로 켜 둔 서버(8090)나 샘플 매장은 건드리지 않는다.
// 확인하는 것: 연동 키 만들기·바꾸기, 키 없이/틀린 키로 막힘, posCode·이름·id로 품절·가격 바꾸기,
// 하나라도 틀리면 아무것도 안 바뀜, 가맹점 키는 품절만, 그리고 보드 화면(board.js)이 새로고침 없이 바로 다시 그림.
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

const BASE = 'http://127.0.0.1:8092'
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
function startBoard() {
  const kept = {}
  global.window = global
  global.MENU_API_BASE = BASE
  Object.defineProperty(global, 'localStorage', {
    configurable: true,
    value: { getItem: (k) => kept[k] ?? null, setItem: (k, v) => { kept[k] = v }, removeItem: (k) => { delete kept[k] } },
  })
  global.location = { search: '?screen=1' }
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

async function main() {
  // ── 첫 설치와 샘플 메뉴 ──
  await ok('첫 설치', 'POST', '/api/menuboard/setup', { email: 'owner@menu.test', password: 'password-1234', storeName: '포스가게' })
  const login = await ok('로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'owner@menu.test', password: 'password-1234' })
  const owner = auth(login.token)
  const sid = login.record.store
  const section = await ok('구역', 'POST', '/api/collections/sections/records', { store: sid, name: '커피', sort_order: 1 }, owner)
  const add = (name, prices, posCode) => ok('메뉴', 'POST', '/api/collections/items/records',
    { store: sid, section: section.id, name, prices, pos_code: posCode, sort_order: 1 }, owner)
  const americano = await add('아메리카노', [{ label: null, amount: 4500 }], 'A01')
  await add('카페라떼', [{ label: 'HOT', amount: 5000 }, { label: 'ICE', amount: 5500 }], 'A02')
  await add('쿠키', [{ label: null, amount: 3000 }], '')
  await add('쿠키 세트', [{ label: null, amount: 5000 }], '')
  await ok('화면 1', 'POST', '/api/collections/screens/records', { store: sid, no: 1, type: 'grid', sections: [section.id] }, owner)
  await fails('같은 매장에 같은 POS 코드', 400, 'POST', '/api/collections/items/records',
    { store: sid, section: section.id, name: '중복', pos_code: 'A01' }, owner)

  // ── 연동 키 ──
  await fails('키 없이 목록', 401, 'GET', '/api/menuboard/pos/items')
  await fails('틀린 키로 목록', 401, 'GET', '/api/menuboard/pos/items', null, posKey('mbpos_wrong'))
  await fails('로그인 없이 키 만들기', 401, 'POST', '/api/menuboard/pos/key')
  const oldKey = (await ok('키 만들기', 'POST', '/api/menuboard/pos/key', null, owner)).key
  const key = (await ok('키 다시 만들기', 'POST', '/api/menuboard/pos/key', null, owner)).key
  assert.notStrictEqual(oldKey, key)
  await fails('예전 키는 못 씀', 401, 'GET', '/api/menuboard/pos/items', null, posKey(oldKey))
  const store = await ok('매장 한 줄 읽기', 'GET', `/api/collections/stores/records/${sid}`)
  assert.ok(!('pos_key_hash' in store), '연동 키 해시가 공개 응답에 보임')
  await ok('매장 수정 요청에 키 해시 섞기', 'PATCH', `/api/collections/stores/records/${sid}`, { name: '포스가게', pos_key_hash: 'x' }, owner)
  await ok('키 해시는 그대로', 'GET', '/api/menuboard/pos/items', null, posKey(key))

  const listed = await ok('목록', 'GET', '/api/menuboard/pos/items', null, { Authorization: `Bearer ${key}` })
  assert.deepStrictEqual(listed.store, { id: sid, name: '포스가게' })
  assert.deepStrictEqual(listed.items.find((m) => m.posCode === 'A01'),
    { id: americano.id, posCode: 'A01', name: '아메리카노', prices: [{ label: null, amount: 4500 }], soldOut: false })

  // ── 보드 화면을 띄우고, POS가 보낸 변경이 새로고침 없이 바로 그려지는지 ──
  startBoard()
  for (let i = 0; !drawn.length; i++) { assert.ok(i < 100, '보드가 처음 화면을 그리지 않음'); await sleep(50) }
  await sleep(500) // 실시간 구독이 자리 잡을 때까지
  assert.strictEqual(onBoard('아메리카노').soldOut, false)

  const pos = (items, k = key) => call('POST', '/api/menuboard/pos/items', { items }, posKey(k))
  await boardShows('posCode로 품절', async () => {
    const r = await pos([{ posCode: 'A01', soldOut: true }])
    assert.strictEqual(r.status, 200, JSON.stringify(r.data))
    assert.strictEqual(r.data.items[0].soldOut, true)
  }, () => onBoard('아메리카노').soldOut === true)
  await boardShows('이름으로 가격, posCode로 두 가격', async () => {
    const r = await pos([{ name: '쿠키', price: 3200 }, { posCode: 'A02', prices: [{ label: 'HOT', amount: 5100 }, { label: 'ICE', amount: 5600 }] }])
    assert.strictEqual(r.status, 200, JSON.stringify(r.data))
  }, () => onBoard('쿠키').prices[0].amount === 3200 && onBoard('카페라떼').prices[1].amount === 5600)
  await boardShows('id로 품절 풀기와 가격을 함께', () => pos([{ id: americano.id, soldOut: false, price: 4700 }]),
    () => !onBoard('아메리카노').soldOut && onBoard('아메리카노').prices[0].amount === 4700)
  await ok('이미 풀린 품절을 또 풀기', 'POST', '/api/menuboard/pos/items', { items: [{ posCode: 'A01', soldOut: false }] }, posKey(key))

  // ── 틀린 요청: 하나라도 틀리면 아무것도 바꾸지 않는다 ──
  const before = (await ok('목록', 'GET', '/api/menuboard/pos/items', null, posKey(key))).items
  const bad = async (what, status, items, pattern) => {
    const r = await pos(items)
    assert.strictEqual(r.status, status, `${what}: ${r.status} ${JSON.stringify(r.data)}`)
    if (pattern) assert.match(r.data.message, pattern, what)
  }
  await bad('없는 POS 코드', 404, [{ posCode: 'A01', soldOut: true }, { posCode: 'ZZZ', soldOut: true }], /2번째 메뉴: POS 코드가 ZZZ/)
  await bad('두 가격 메뉴에 price', 400, [{ posCode: 'A01', soldOut: true }, { posCode: 'A02', price: 1 }], /prices로/)
  await bad('음수 가격', 400, [{ posCode: 'A01', price: -1 }])
  await bad('소수 가격', 400, [{ posCode: 'A01', price: 10.5 }])
  await bad('가격 세 개', 400, [{ posCode: 'A02', prices: [{ amount: 1 }, { amount: 2 }, { amount: 3 }] }])
  await bad('바꿀 것이 없음', 400, [{ posCode: 'A01' }])
  await bad('soldOut이 글자', 400, [{ posCode: 'A01', soldOut: 'yes' }])
  await bad('메뉴 지정 없음', 400, [{ soldOut: true }])
  await bad('빈 목록', 400, [])
  await bad('items 없음', 400, undefined)
  await bad('이름이 정확히 같아야 함', 404, [{ name: '쿠', soldOut: true }])
  const after = (await ok('목록', 'GET', '/api/menuboard/pos/items', null, posKey(key))).items
  assert.deepStrictEqual(after, before, '틀린 요청인데 일부가 바뀜')

  // ── 프랜차이즈: 가맹점 키는 본사 메뉴의 품절만, 남의 매장 메뉴는 못 봄 ──
  const su = await ok('관리자 로그인', 'POST', '/api/collections/_superusers/auth-with-password', { identity: 'admin@menu.test', password: 'password-1234' })
  const admin = auth(su.token)
  const hq = await ok('본사', 'POST', '/api/collections/stores/records', { kind: 'hq', name: '본사' }, admin)
  const hqSection = await ok('본사 구역', 'POST', '/api/collections/sections/records', { store: hq.id, name: '공통' }, admin)
  await ok('본사 메뉴', 'POST', '/api/collections/items/records',
    { store: hq.id, section: hqSection.id, name: '공통메뉴', prices: [{ label: null, amount: 9000 }], pos_code: 'A01' }, admin)
  const branch = await ok('가맹점', 'POST', '/api/collections/stores/records', { kind: 'franchise', name: '1호점', parent: hq.id }, admin)
  await ok('가맹점 계정', 'POST', '/api/collections/users/records',
    { email: 'branch@menu.test', password: 'password-1234', passwordConfirm: 'password-1234', store: branch.id }, admin)
  const branchLogin = await ok('가맹점 로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'branch@menu.test', password: 'password-1234' })
  const branchKey = (await ok('가맹점 키', 'POST', '/api/menuboard/pos/key', null, auth(branchLogin.token))).key
  const branchItems = (await ok('가맹점 목록', 'GET', '/api/menuboard/pos/items', null, posKey(branchKey))).items
  assert.deepStrictEqual(branchItems.map((m) => m.name), ['공통메뉴']) // 본사 메뉴만, 같은 A01이어도 포스가게 메뉴가 아님
  let r = await pos([{ posCode: 'A01', soldOut: true }], branchKey)
  assert.strictEqual(r.status, 200, JSON.stringify(r.data))
  assert.deepStrictEqual(r.data.items.map((m) => [m.name, m.soldOut]), [['공통메뉴', true]])
  r = await pos([{ posCode: 'A01', price: 1 }], branchKey)
  assert.strictEqual(r.status, 403, JSON.stringify(r.data))
  r = await pos([{ id: americano.id, soldOut: true }], branchKey)
  assert.strictEqual(r.status, 404, '가맹점 키로 남의 매장 메뉴를 찾음')
  assert.strictEqual(onBoard('아메리카노').soldOut, false)
}

async function run() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'menuboard-pos-'))
  const dirs = ['migrations', 'hooks', 'public'].flatMap((d) => [`--${d}Dir`, path.join(__dirname, `pb_${d}`)])
  const su = spawnSync(PB, ['superuser', 'upsert', 'admin@menu.test', 'password-1234', '--dir', dir, ...dirs], { encoding: 'utf8' })
  assert.strictEqual(su.status, 0, `관리자 계정 만들기 실패 (${PB}): ${su.stderr || su.error}`)
  const pb = spawn(PB, ['serve', '--http', '127.0.0.1:8092', '--dir', dir, ...dirs], { stdio: 'ignore' })
  let failed = false
  try {
    for (let i = 0; ; i++) {
      if (await fetch(`${BASE}/api/health`).then((x) => x.ok, () => false)) break
      assert.ok(i < 100, '임시 서버가 10초 안에 뜨지 않음')
      await sleep(100)
    }
    await main()
    console.log('OK: POS 연동 키, 품절·가격 바꾸기, 틀린 요청 막기, 가맹점 제한, 보드 화면 바로 반영 모두 설계대로입니다.')
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
