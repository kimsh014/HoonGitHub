// 매장 위험 점검표의 서버 쪽 1차 대응(pb_hooks/safety.pb.js, 로그인 횟수 제한 마이그레이션)을 검사한다. 사용: node check_safety.js
// 임시 폴더로 빈 서버(8095)를 잠깐 띄워 검사하므로 켜 둔 서버(8090)는 건드리지 않는다.
// 확인하는 것: 자동 백업(만들기, 7개만 남기기), 서버가 켜질 때 지난 번호 비우기, 메뉴가 있는 구역은 지우기 막기,
// POS기 앞(127.0.0.1)에서만 비밀번호 다시 정하기, 로그인 횟수 제한.
const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')

const PORT = 8095
const BASE = `http://127.0.0.1:${PORT}`
const PB = process.env.POCKETBASE || path.join(__dirname, 'pocketbase.exe')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const dirs = ['migrations', 'hooks', 'public'].flatMap((d) => [`--${d}Dir`, path.join(__dirname, `pb_${d}`)])

// 이 컴퓨터의 127.0.0.1이 아닌 주소(같은 와이파이의 폰처럼 들어오는 길). 없으면 그 검사는 건너뛴다.
const lanIP = Object.values(os.networkInterfaces()).flat().find((a) => a && a.family === 'IPv4' && !a.internal)?.address

async function call(method, url, body, headers = {}, base = BASE) {
  const res = await fetch(base + url, {
    method, headers: { ...headers, ...(body && { 'Content-Type': 'application/json' }) }, body: body && JSON.stringify(body),
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

let pb = null
async function startServer(dir, env = {}) {
  pb = spawn(PB, ['serve', '--http', `0.0.0.0:${PORT}`, '--dir', dir, ...dirs], { stdio: 'ignore', env: { ...process.env, ...env } })
  for (let i = 0; ; i++) {
    if (await fetch(`${BASE}/api/health`).then((x) => x.ok, () => false)) return
    assert.ok(i < 100, '임시 서버가 10초 안에 뜨지 않음')
    await sleep(100)
  }
}
async function stopServer() {
  if (!pb) return
  pb.kill()
  await new Promise((x) => pb.once('exit', x))
  pb = null
}

async function main(dir) {
  await ok('첫 설치', 'POST', '/api/menuboard/setup', { email: 'owner@menu.test', password: 'password-1234', storeName: '안전가게' })
  const login = await ok('로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'owner@menu.test', password: 'password-1234' })
  const owner = auth(login.token)
  const sid = login.record.store
  const su = auth((await ok('관리자 로그인', 'POST', '/api/collections/_superusers/auth-with-password', { identity: 'admin@menu.test', password: 'password-1234' })).token)

  // ── 자동 백업: 관리자만 지금 만들 수 있고, 7개만 남는다 ──
  await fails('사장님 계정으로 백업', 403, 'POST', '/api/menuboard/backup', null, owner)
  for (let i = 0; i < 9; i++) await ok('백업 ' + (i + 1), 'POST', '/api/menuboard/backup', null, su)
  const backups = (await ok('백업 목록', 'GET', '/api/backups', null, su)).map((b) => b.key).filter((k) => k.startsWith('@auto_pb_backup_menuboard_'))
  assert.strictEqual(backups.length, 7, `백업은 7개만 남아야 함: ${backups}`)

  // ── 메뉴가 있는 구역은 지우지 못한다 ──
  const section = await ok('구역', 'POST', '/api/collections/sections/records', { store: sid, name: '커피', sort_order: 1 }, owner)
  const item = await ok('메뉴', 'POST', '/api/collections/items/records', { store: sid, section: section.id, name: '라떼', prices: [{ label: null, amount: 4500 }] }, owner)
  const blocked = await fails('메뉴가 있는 구역 지우기', 400, 'DELETE', `/api/collections/sections/records/${section.id}`, null, owner)
  assert.match(blocked.message, /메뉴 1개/)
  await ok('메뉴 지우기', 'DELETE', `/api/collections/items/records/${item.id}`, null, owner)
  await ok('빈 구역 지우기', 'DELETE', `/api/collections/sections/records/${section.id}`, null, owner)

  // ── 비밀번호 다시 정하기: POS기 앞에서만 ──
  const accounts = await ok('계정 목록', 'GET', '/api/menuboard/local-reset')
  assert.deepStrictEqual(accounts.accounts, [{ email: 'owner@menu.test' }])
  await fails('짧은 비밀번호', 400, 'POST', '/api/menuboard/local-reset', { email: 'owner@menu.test', password: 'short' })
  await fails('없는 계정', 404, 'POST', '/api/menuboard/local-reset', { email: 'nobody@menu.test', password: 'new-password-1' })
  if (lanIP) {
    const lan = `http://${lanIP}:${PORT}`
    await fails('매장 와이파이에서 계정 목록', 403, 'GET', '/api/menuboard/local-reset', null, {}, lan)
    await fails('매장 와이파이에서 다시 정하기', 403, 'POST', '/api/menuboard/local-reset', { email: 'owner@menu.test', password: 'hacked-password' }, { 'X-Forwarded-For': '127.0.0.1' }, lan)
  } else console.log('  (127.0.0.1 말고 다른 주소가 없어 와이파이에서 막히는지는 건너뜀)')
  await ok('POS기에서 다시 정하기', 'POST', '/api/menuboard/local-reset', { email: 'owner@menu.test', password: 'new-password-1' })
  await fails('예전 로그인은 끊김', 401, 'POST', '/api/menuboard/pos/key', null, owner)
  await fails('예전 비밀번호', 400, 'POST', '/api/collections/users/auth-with-password', { identity: 'owner@menu.test', password: 'password-1234' })
  const relogin = await ok('새 비밀번호로 로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'owner@menu.test', password: 'new-password-1' })

  // ── 서버가 켜질 때 지난 번호를 비운다 (검사에서는 "지난"을 2초로) ──
  await ok('번호 부르기', 'POST', '/api/collections/calls/records', { store: sid, number: 12 }, auth(relogin.token))
  await sleep(2500)
  await stopServer()
  await startServer(dir, { MENUBOARD_CALL_KEEP_SECONDS: '2' })
  const calls = await ok('번호 목록', 'GET', `/api/collections/calls/records?filter=${encodeURIComponent(`store='${sid}'`)}`)
  assert.strictEqual(calls.items.length, 0, '켜질 때 지난 번호가 남아 있음')
  await ok('방금 부른 번호', 'POST', '/api/collections/calls/records', { store: sid, number: 13 }, auth(relogin.token))
  assert.strictEqual((await ok('번호 목록', 'GET', `/api/collections/calls/records?filter=${encodeURIComponent(`store='${sid}'`)}`)).items.length, 1)

  // ── 로그인 횟수 제한: 같은 주소에서 1분에 20번 넘게 로그인하면 막힌다 ──
  let limited = 0
  for (let i = 0; i < 24; i++) {
    const r = await call('POST', '/api/collections/users/auth-with-password', { identity: 'owner@menu.test', password: 'wrong-' + i })
    if (r.status === 429) limited++
  }
  assert.ok(limited >= 2, `틀린 로그인 24번 중 막힌 것이 ${limited}번`)
}

async function run() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'menuboard-safety-'))
  const su = spawnSync(PB, ['superuser', 'upsert', 'admin@menu.test', 'password-1234', '--dir', dir, ...dirs], { encoding: 'utf8' })
  assert.strictEqual(su.status, 0, `관리자 계정 만들기 실패 (${PB}): ${su.stderr || su.error}`)
  let failed = false
  try {
    await startServer(dir)
    await main(dir)
    console.log('OK: 자동 백업 7개, 켜질 때 지난 번호 비우기, 메뉴 있는 구역 지우기 막기, POS기 앞에서만 비밀번호 다시 정하기, 로그인 횟수 제한 모두 설계대로입니다.')
  } catch (err) {
    failed = true
    console.error(err)
  } finally {
    await stopServer()
    fs.rmSync(dir, { recursive: true, force: true })
  }
  process.exit(failed ? 1 : 0)
}
run()
