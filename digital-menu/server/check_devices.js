// TV 원격 관리(pb_hooks/devices.pb.js)를 검사한다. 사용: node check_devices.js
// 임시 폴더로 빈 서버(127.0.0.1:8093)를 잠깐 띄워 검사하므로 켜 둔 서버(8090)는 건드리지 않는다.
// 확인하는 것: TV 등록·보고, 토큰 없이/틀린 토큰으로 막힘, 설정 바꾸기와 검사, 재시작·캡처·A/S 연결 요청,
// 캡처 사진 올리기, 남의 매장 TV는 못 봄, TV를 지우면 그 토큰은 못 씀, A/S 연결은 A/S 관리자만 엶.
const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')

const BASE = 'http://127.0.0.1:8093'
const PB = process.env.POCKETBASE || path.join(__dirname, 'pocketbase.exe')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function call(method, url, body, headers = {}) {
  const raw = body instanceof Uint8Array
  const res = await fetch(BASE + url, {
    method,
    headers: { ...headers, ...(body && { 'Content-Type': raw ? 'image/jpeg' : 'application/json' }) },
    body: body && (raw ? body : JSON.stringify(body)),
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
const dev = (token) => ({ 'X-Device-Token': token })

async function main() {
  await fails('매장이 없을 때 등록', 400, 'POST', '/api/menuboard/devices/register', {})
  await ok('첫 설치', 'POST', '/api/menuboard/setup', { email: 'owner@menu.test', password: 'password-1234', storeName: '천장가게' })
  const login = await ok('로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'owner@menu.test', password: 'password-1234' })
  const owner = auth(login.token)
  const sid = login.record.store

  // ── TV 등록과 보고 ──
  const reg = await ok('등록', 'POST', '/api/menuboard/devices/register', { model: 'RK3568', version: '1.2' })
  assert.strictEqual(reg.store, sid)
  assert.match(reg.token, /^mbdev_/)
  const tv = dev(reg.token)
  await fails('토큰 없이 보고', 401, 'POST', '/api/menuboard/devices/report', {})
  await fails('틀린 토큰으로 보고', 401, 'POST', '/api/menuboard/devices/report', {}, dev('mbdev_wrong'))
  let o = await ok('보고', 'POST', '/api/menuboard/devices/report',
    { version: '1.2', model: 'RK3568', reported: { server: '192.168.0.10:8090', screen: 1, zoom: 100, rotation: 0, brightness: -1, rev: 0, junk: 'x'.repeat(9000) } }, tv)
  assert.deepStrictEqual(o, { id: reg.id, rev: 0, desired: {}, restartRev: 0, shotRev: 0, adbSeconds: 0 })

  const list = await ok('관리 화면 목록', 'GET', '/api/collections/devices/records', null, owner)
  assert.strictEqual(list.items.length, 1)
  const row = list.items[0]
  assert.strictEqual(row.name, 'TV 1')
  assert.ok(!('token_hash' in row), '토큰 해시가 응답에 보임')
  assert.ok(!('junk' in row.reported), '모르는 보고 칸이 저장됨')
  assert.strictEqual(row.reported.server, '192.168.0.10:8090')
  await fails('로그인 없이 목록은 비어 있음', 200, 'GET', '/api/collections/devices/records').then((d) => assert.strictEqual(d.items.length, 0))
  await fails('관리 화면에서 직접 고치기 막힘', 403, 'PATCH', `/api/collections/devices/records/${reg.id}`, { adb_until: 9999999999 }, owner)

  // ── 설정 바꾸기 ──
  await fails('로그인 없이 설정', 401, 'POST', `/api/menuboard/devices/${reg.id}/config`, { screen: 2 })
  await fails('틀린 화면 번호', 400, 'POST', `/api/menuboard/devices/${reg.id}/config`, { screen: 9 }, owner)
  await fails('틀린 방향', 400, 'POST', `/api/menuboard/devices/${reg.id}/config`, { rotation: 45 }, owner)
  await fails('너무 어두운 밝기', 400, 'POST', `/api/menuboard/devices/${reg.id}/config`, { brightness: 3 }, owner)
  await fails('틀린 서버 주소', 400, 'POST', `/api/menuboard/devices/${reg.id}/config`, { server: 'http://x/y' }, owner)
  await ok('설정', 'POST', `/api/menuboard/devices/${reg.id}/config`, { name: '카운터 위', screen: 2, rotation: 90, brightness: 70 }, owner)
  await ok('설정 한 칸 더', 'POST', `/api/menuboard/devices/${reg.id}/config`, { zoom: 150 }, owner)
  o = await ok('보고', 'POST', '/api/menuboard/devices/report', { reported: { rev: 0 } }, tv)
  assert.strictEqual(o.rev, 2)
  assert.deepStrictEqual(o.desired, { screen: 2, rotation: 90, brightness: 70, zoom: 150 })

  // ── 재시작·캡처·A/S 연결 ──
  await ok('재시작', 'POST', `/api/menuboard/devices/${reg.id}/restart`, null, owner)
  const shotReq = await ok('캡처 요청', 'POST', `/api/menuboard/devices/${reg.id}/shot`, null, owner)
  // A/S 연결은 A/S 관리자(superuser)만 열고(최대 60분), 사장님 계정은 잠그기만 한다(점검표 R-1)
  const asAdmin = auth((await ok('A/S 관리자 로그인', 'POST', '/api/collections/_superusers/auth-with-password', { identity: 'admin@menu.test', password: 'password-1234' })).token)
  await fails('사장님 계정으로 A/S 열기', 403, 'POST', `/api/menuboard/devices/${reg.id}/adb`, { minutes: 30 }, owner)
  await fails('A/S 너무 길게', 400, 'POST', `/api/menuboard/devices/${reg.id}/adb`, { minutes: 61 }, asAdmin)
  await ok('A/S 열기', 'POST', `/api/menuboard/devices/${reg.id}/adb`, { minutes: 60 }, asAdmin)
  o = await ok('보고', 'POST', '/api/menuboard/devices/report', {}, tv)
  assert.strictEqual(o.restartRev, 1)
  assert.strictEqual(o.shotRev, 1)
  assert.ok(o.adbSeconds > 3500 && o.adbSeconds <= 3600, `adbSeconds ${o.adbSeconds}`)
  await ok('A/S 닫기', 'POST', `/api/menuboard/devices/${reg.id}/adb`, { minutes: 0 }, owner)
  o = await ok('보고', 'POST', '/api/menuboard/devices/report', {}, tv)
  assert.strictEqual(o.adbSeconds, 0)

  // ── 캡처 사진 ──
  await fails('JPEG가 아닌 사진', 400, 'POST', '/api/menuboard/devices/shot', new Uint8Array([1, 2, 3, 4, 5]), tv)
  await fails('토큰 없이 사진', 401, 'POST', '/api/menuboard/devices/shot', new Uint8Array([0xff, 0xd8, 0xff, 0xd9]))
  const jpeg = new Uint8Array(fs.readFileSync(path.join(__dirname, '..', 'board-app', 'testpage', 'test-shot.jpg')))
  await ok('사진 올리기', 'POST', '/api/menuboard/devices/shot', jpeg, tv)
  const got = await ok('사진 확인', 'GET', `/api/collections/devices/records/${reg.id}`, null, owner)
  assert.ok(got.shot && got.shot_at >= shotReq.shotAt, '사진이 저장되지 않음')
  const file = await fetch(`${BASE}/api/files/devices/${reg.id}/${got.shot}`)
  assert.strictEqual(file.status, 200)
  assert.strictEqual(Buffer.from(await file.arrayBuffer()).length, jpeg.length)

  // ── 다른 매장 계정은 못 봄 ──
  const su = await ok('관리자 로그인', 'POST', '/api/collections/_superusers/auth-with-password', { identity: 'admin@menu.test', password: 'password-1234' })
  const other = await ok('다른 매장', 'POST', '/api/collections/stores/records', { kind: 'independent', name: '남의가게' }, auth(su.token))
  await ok('다른 매장 계정', 'POST', '/api/collections/users/records',
    { email: 'other@menu.test', password: 'password-1234', passwordConfirm: 'password-1234', store: other.id }, auth(su.token))
  const otherLogin = await ok('다른 매장 로그인', 'POST', '/api/collections/users/auth-with-password', { identity: 'other@menu.test', password: 'password-1234' })
  const stranger = auth(otherLogin.token)
  assert.strictEqual((await ok('남의 목록', 'GET', '/api/collections/devices/records', null, stranger)).items.length, 0)
  await fails('남의 TV 설정', 404, 'POST', `/api/menuboard/devices/${reg.id}/config`, { screen: 1 }, stranger)
  await fails('남의 TV A/S 잠그기', 404, 'POST', `/api/menuboard/devices/${reg.id}/adb`, { minutes: 0 }, stranger)
  await fails('매장이 둘일 때 번호 없이 등록', 400, 'POST', '/api/menuboard/devices/register', {})
  const reg2 = await ok('매장 번호로 등록', 'POST', '/api/menuboard/devices/register', { store: other.id, name: '입구' })
  assert.strictEqual(reg2.store, other.id)

  // ── TV를 지우면 그 토큰은 못 씀 ──
  await ok('TV 지우기', 'DELETE', `/api/collections/devices/records/${reg.id}`, null, owner)
  await fails('지운 TV 보고', 401, 'POST', '/api/menuboard/devices/report', {}, tv)
}

async function run() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'menuboard-dev-'))
  const dirs = ['migrations', 'hooks', 'public'].flatMap((d) => [`--${d}Dir`, path.join(__dirname, `pb_${d}`)])
  const su = spawnSync(PB, ['superuser', 'upsert', 'admin@menu.test', 'password-1234', '--dir', dir, ...dirs], { encoding: 'utf8' })
  assert.strictEqual(su.status, 0, `관리자 계정 만들기 실패 (${PB}): ${su.stderr || su.error}`)
  const pb = spawn(PB, ['serve', '--http', '127.0.0.1:8093', '--dir', dir, ...dirs], { stdio: 'ignore' })
  let failed = false
  try {
    for (let i = 0; ; i++) {
      if (await fetch(`${BASE}/api/health`).then((x) => x.ok, () => false)) break
      assert.ok(i < 100, '임시 서버가 10초 안에 뜨지 않음')
      await sleep(100)
    }
    await main()
    console.log('OK: TV 등록·보고, 설정 바꾸기, 재시작·캡처·A/S 연결 요청, 캡처 사진, 매장 구분, TV 지우기 모두 설계대로입니다.')
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
