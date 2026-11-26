// 실행 중인 서버에 pb_public/api.js를 그대로 물려 계약의 함수 전부를 검사한다.
// 사용: node check_api.js   (먼저 python seed_and_check.py 로 샘플 매장이 들어가 있어야 함)
// 검사가 만든 것은 지우고 샘플 매장('우리카페')은 처음 모양 그대로 돌려놓는다.
// signUp의 첫 설치는 빈 서버가 필요해서, 임시 폴더로 두 번째 서버(127.0.0.1:8091)를 잠깐 띄워 검사한다.
const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')

// Node 24는 EventSource(실시간 구독)를 플래그 뒤에 두었다. 없으면 플래그를 붙여 자기 자신을 다시 실행한다.
if (typeof EventSource === 'undefined') {
  const r = spawnSync(process.execPath, ['--experimental-eventsource', '--no-warnings', __filename], { stdio: 'inherit' })
  process.exit(r.status)
}

const BASE = 'http://127.0.0.1:8090'
const REC = (c) => `${BASE}/api/collections/${c}/records`
const API_JS = path.join(__dirname, 'pb_public', 'api.js')
const kept = {}
global.window = global
Object.defineProperty(global, 'localStorage', {
  configurable: true,
  value: { getItem: (k) => kept[k] ?? null, setItem: (k, v) => { kept[k] = v }, removeItem: (k) => { delete kept[k] } },
})

// base 주소의 서버를 부르는 api 객체를 하나 만든다
function loadApi(base) {
  global.MENU_API_BASE = base
  delete require.cache[API_JS]
  require(API_JS)
  return window.api
}
const api = loadApi(BASE)

const creds = (file) => fs.readFileSync(path.join(__dirname, file), 'utf8').trim().split(/\s+/)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const pngBytes = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64')
const png = (size = pngBytes.length) => {
  const buf = Buffer.alloc(size) // 앞은 진짜 PNG, 뒤는 0으로 채워 크기만 키운다
  pngBytes.copy(buf)
  return new Blob([buf], { type: 'image/png' })
}

async function raw(method, url, body, token) {
  const res = await fetch(url, {
    method,
    headers: { ...(token && { Authorization: token }), ...(body && { 'Content-Type': 'application/json' }) },
    body: body && JSON.stringify(body),
  })
  assert.ok(res.ok, `${method} ${url} -> ${res.status} ${await res.clone().text()}`)
  return res.status === 204 ? null : res.json()
}

// 실시간 알림 세기. 저장한 뒤 5초 안에 알림이 와야 한다.
let changes = 0
async function changed(what, save) {
  await sleep(300) // 앞 저장의 늦은 알림이 섞이지 않게
  const before = changes
  const result = await save()
  for (let i = 0; i < 50 && changes === before; i++) await sleep(100)
  assert.ok(changes > before, `${what}: 저장했는데 onBoardChange 알림이 오지 않음`)
  return result
}

async function checkSignUp() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'menuboard-check-'))
  const pb = spawn(path.join(__dirname, 'pocketbase.exe'), ['serve', '--http', '127.0.0.1:8091', '--dir', dir,
    ...['migrations', 'hooks', 'public'].flatMap((d) => [`--${d}Dir`, path.join(__dirname, `pb_${d}`)])], { stdio: 'ignore' })
  try {
    for (let i = 0; ; i++) {
      if (await fetch('http://127.0.0.1:8091/api/health').then((r) => r.ok, () => false)) break
      assert.ok(i < 100, '임시 서버가 10초 안에 뜨지 않음')
      await sleep(100)
    }
    const fresh = loadApi('http://127.0.0.1:8091')
    await assert.rejects(fresh.getBoard(), (e) => e.status === 404 && /매장이 없습니다/.test(e.message), '빈 서버는 404')
    const me = await fresh.signUp('first@menu.test', 'password-1234', '새가게')
    assert.strictEqual(me.kind, 'independent')
    assert.deepStrictEqual(await fresh.session(), me)
    assert.strictEqual((await fresh.getBoard()).store.name, '새가게')
    await assert.rejects(fresh.signUp('second@menu.test', 'password-1234', '또가게'), (e) => e.status === 403, '두 번째 설치는 403')
    await fresh.logout()
  } finally {
    window.api = api
    pb.kill()
    await new Promise((r) => pb.once('exit', r))
    fs.rmSync(dir, { recursive: true, force: true })
  }
}

async function main() {
  // ── session, logout, login ──
  const [email, password] = creds('.dev-owner')
  await api.logout()
  assert.strictEqual(await api.session(), null)
  await assert.rejects(api.login(email, 'wrong-password'), (e) => e.status === 400, '틀린 비밀번호는 400이어야 함')
  const me = await api.login(email, password)
  assert.strictEqual(me.kind, 'independent')
  assert.deepStrictEqual(await api.session(), me)
  await api.logout()
  assert.strictEqual(await api.session(), null)
  await api.login(email, password)
  const sid = me.storeId

  // ── getBoard: 개인 매장, 매장 번호 없이도 같은 것 ──
  const original = await api.getBoard(sid)
  assert.deepStrictEqual(await api.getBoard(), original)
  assert.deepStrictEqual(await api.getBoard(''), original)
  let board = original
  assert.deepStrictEqual(board.store, { name: '우리카페', brandColor: '#c8102e', backgroundUrl: null })
  assert.deepStrictEqual(board.sections.map((s) => [s.name, s.order]), [['커피', 1], ['디저트', 2]])
  assert.strictEqual(board.items.length, 7)
  const americano = board.items.find((m) => m.name === '아메리카노')
  assert.deepStrictEqual(americano.prices, [{ label: 'HOT', amount: 4500 }, { label: 'ICE', amount: 5000 }])
  assert.strictEqual(americano.badge, 'best')
  assert.strictEqual(americano.sectionId, board.sections[0].id)
  const espresso = board.items.find((m) => m.name === '에스프레소')
  assert.deepStrictEqual([espresso.prices, espresso.badge, espresso.photoUrl, espresso.soldOut], [[{ label: null, amount: 4000 }], null, null, false])
  assert.deepStrictEqual(board.screens, [
    { no: 1, type: 'grid', sectionIds: [board.sections[0].id], callBand: false },
    { no: 2, type: 'list', sectionIds: [board.sections[1].id], callBand: false },
    { no: 3, type: 'promo', imageUrl: null, lines: ['겨울 한정 바닐라라떼', '지금 만나 보세요'], callBand: false },
  ])
  assert.deepStrictEqual(board.calls, [])

  // ── 저장 함수 + onBoardChange (api.js는 구독을 늘 로그인 없이 하므로, 알림이 오면 로그인 없는 보드도 받는다) ──
  api.onBoardChange(() => changes++)
  await sleep(1000) // 구독이 자리 잡을 때까지
  try {
    const sectionId = await changed('saveSection 추가', () => api.saveSection(sid, { name: '검사구역', order: 9 }))
    await changed('saveSection 수정', () => api.saveSection(sid, { id: sectionId, name: '검사구역2', order: 8 }))
    const itemId = await changed('saveItem 추가', () => api.saveItem(sid, {
      sectionId, name: '검사메뉴', prices: [{ label: null, amount: 1000 }], order: 99, badge: null, photoFile: png(),
    }))
    board = await api.getBoard()
    assert.deepStrictEqual(board.sections.find((s) => s.id === sectionId), { id: sectionId, name: '검사구역2', order: 8 })
    let item = board.items.find((m) => m.id === itemId)
    assert.deepStrictEqual({ ...item, photoUrl: !!item.photoUrl },
      { id: itemId, sectionId, name: '검사메뉴', prices: [{ label: null, amount: 1000 }], photoUrl: true, order: 99, soldOut: false, badge: null, posCode: null })
    // 응답 본문은 끝까지 읽는다. 윈도우에서는 읽다 만 파일이 열린 채로 남아 다음 저장의 파일 지우기가 실패한다
    const photo = await fetch(item.photoUrl)
    assert.deepStrictEqual([photo.headers.get('content-type'), (await photo.arrayBuffer()).byteLength], ['image/png', pngBytes.length])

    // 수정: getBoard 모양 그대로 받아 고친다. photoUrl: null 이면 사진을 지운다
    await changed('saveItem 수정', () => api.saveItem(sid, { ...item, name: '검사메뉴2', badge: 'new', photoUrl: null, posCode: 'T99',
      prices: [{ label: 'HOT', amount: 1500 }, { label: 'ICE', amount: 2000 }] }))
    item = (await api.getBoard()).items.find((m) => m.id === itemId)
    assert.deepStrictEqual([item.name, item.badge, item.photoUrl, item.prices, item.posCode], ['검사메뉴2', 'new', null, [{ label: 'HOT', amount: 1500 }, { label: 'ICE', amount: 2000 }], 'T99'])
    await api.saveItem(sid, { id: itemId, posCode: null }) // POS 코드 지우기
    assert.strictEqual((await api.getBoard()).items.find((m) => m.id === itemId).posCode, null)

    // POS 연동 키 (자세한 검사는 check_pos.js)
    const posKey = await api.issuePosKey(sid)
    assert.match(posKey, /^mbpos_\w{40}$/)
    assert.strictEqual((await fetch(`${BASE}/api/menuboard/pos/items`, { headers: { 'X-POS-Key': posKey } })).status, 200)

    await changed('setSoldOut 켜기', () => api.setSoldOut(sid, itemId, true))
    await api.setSoldOut(sid, itemId, true) // 두 번 켜도 오류 없이
    assert.strictEqual((await api.getBoard()).items.find((m) => m.id === itemId).soldOut, true)
    await changed('setSoldOut 끄기', () => api.setSoldOut(sid, itemId, false))
    assert.strictEqual((await api.getBoard()).items.find((m) => m.id === itemId).soldOut, false)

    await changed('deleteItem', () => api.deleteItem(sid, itemId))
    assert.ok(!(await api.getBoard()).items.some((m) => m.id === itemId))

    // 4K 사진 크기(20MB)가 올라가는지 (가게 배경으로). 매장 변경도 알림이 와야 한다
    await changed('saveStore', () => api.saveStore(sid, { name: '검사카페', brandColor: '#000000', backgroundFile: png(20 * 1024 * 1024) }))
    board = await api.getBoard()
    assert.deepStrictEqual([board.store.name, board.store.brandColor], ['검사카페', '#000000'])
    assert.strictEqual((await (await fetch(board.store.backgroundUrl)).arrayBuffer()).byteLength, 20 * 1024 * 1024)

    // 화면 구성 전체 교체: 1·2는 고치고, 3은 홍보 이미지와 함께 고치고, 4·5는 더한다
    await changed('saveScreens', () => api.saveScreens(sid, [
      { no: 1, type: 'list', sectionIds: [sectionId], callBand: true },
      { no: 2, type: 'grid', sectionIds: [original.sections[0].id, original.sections[1].id] },
      { no: 3, type: 'promo', lines: ['한 줄'], imageFile: png(), callBand: true },
      { no: 4, type: 'promo', lines: ['a', 'b', 'c'] },
      { no: 5, type: 'calls', callBand: true }, // 번호 전용 화면에는 띠가 없다
    ]))
    const screens = (await api.getBoard()).screens
    assert.deepStrictEqual(screens.map((s) => (s.type === 'promo' ? { ...s, imageUrl: !!s.imageUrl } : s)), [
      { no: 1, type: 'list', sectionIds: [sectionId], callBand: true },
      { no: 2, type: 'grid', sectionIds: [original.sections[0].id, original.sections[1].id], callBand: false },
      { no: 3, type: 'promo', imageUrl: true, lines: ['한 줄'], callBand: true },
      { no: 4, type: 'promo', imageUrl: false, lines: ['a', 'b'], callBand: false }, // 문구는 두 줄까지
      { no: 5, type: 'calls' },
    ])

    // 번호 호출: 최근 것이 앞, 다시 부르면 앞으로, 하나·전체 지우기, 매장마다 최근 30개까지만
    await changed('callNumber', () => api.callNumber(sid, 101))
    await api.callNumber(sid, 102)
    await api.callNumber(sid, 101)
    assert.deepStrictEqual((await api.getBoard()).calls, [101, 102])
    await changed('clearCalls 하나', () => api.clearCalls(sid, 102))
    assert.deepStrictEqual((await api.getBoard()).calls, [101])
    for (let n = 1; n <= 32; n++) await api.callNumber(sid, n)
    assert.deepStrictEqual((await api.getBoard()).calls, Array.from({ length: 30 }, (_, i) => 32 - i))
    await assert.rejects(api.callNumber(sid, 10000), (e) => e.status === 400, '번호는 9999까지')
    await changed('clearCalls 전체', () => api.clearCalls(sid))
    assert.deepStrictEqual((await api.getBoard()).calls, [])

    // 메뉴가 있는 구역은 지우지 못한다(메뉴까지 같이 지워지는 사고 막기). 메뉴를 지우면 구역을 지울 수 있고, 화면 구성에서도 빠진다
    const doomed = await api.saveItem(sid, { sectionId, name: '남은메뉴', prices: [{ label: null, amount: 1 }], order: 100, badge: null })
    await assert.rejects(api.deleteSection(sid, sectionId), (e) => e.status === 400 && /메뉴 1개/.test(e.message), '메뉴가 있는 구역 지우기는 400')
    await api.deleteItem(sid, doomed)
    await changed('deleteSection', () => api.deleteSection(sid, sectionId))
    board = await api.getBoard()
    assert.ok(!board.sections.some((s) => s.id === sectionId) && !board.items.some((m) => m.name === '남은메뉴'))
    assert.deepStrictEqual(board.screens[0].sectionIds, [])
  } finally {
    // 샘플 매장을 처음 모양으로. 검사 중간에 실패했어도 검사가 더한 구역과 그 메뉴를 지운다.
    // 화면 4는 빠지며 지워지고, 3의 홍보 이미지는 imageUrl: null 이라 지워진다
    const now = await api.getBoard(sid)
    for (const s of now.sections) {
      if (original.sections.some((o) => o.id === s.id)) continue
      for (const m of now.items) if (m.sectionId === s.id) await api.deleteItem(sid, m.id)
      await api.deleteSection(sid, s.id)
    }
    await api.saveScreens(sid, original.screens)
    await api.saveStore(sid, { name: original.store.name, brandColor: original.store.brandColor, backgroundUrl: null })
    await api.clearCalls(sid)
  }
  assert.deepStrictEqual(await api.getBoard(), original)

  // ── 남의 매장에는 저장 안 됨 (로그아웃 상태) ──
  await api.logout()
  await assert.rejects(api.saveSection(sid, { name: '침입' }), (e) => e.status >= 400)
  await assert.rejects(api.callNumber(sid, 1), (e) => e.status >= 400)
  await api.login(email, password)

  // ── getBoard: 가맹점은 본사 메뉴·화면·브랜드 + 자기 품절 (검사용 매장은 끝나면 지운다) ──
  const [adminEmail, adminPassword] = creds('.dev-superuser')
  const admin = (await raw('POST', `${BASE}/api/collections/_superusers/auth-with-password`, { identity: adminEmail, password: adminPassword })).token
  const hq = await raw('POST', REC('stores'), { kind: 'hq', name: '검사본사', brand_color: '#123456' }, admin)
  try {
    await assert.rejects(api.getBoard(), (e) => e.status === 404 && /여러 개/.test(e.message), '매장이 둘이면 매장 번호 없이 못 연다')
    const section = await raw('POST', REC('sections'), { store: hq.id, name: '공통', sort_order: 1 }, admin)
    const a = await raw('POST', REC('items'), { store: hq.id, section: section.id, name: '공통A', sort_order: 1 }, admin)
    const b = await raw('POST', REC('items'), { store: hq.id, section: section.id, name: '공통B', sort_order: 2 }, admin)
    await raw('POST', REC('screens'), { store: hq.id, no: 1, type: 'grid', sections: [section.id] }, admin)
    const branch1 = await raw('POST', REC('stores'), { kind: 'franchise', name: '1호점', parent: hq.id }, admin)
    const branch2 = await raw('POST', REC('stores'), { kind: 'franchise', name: '2호점', parent: hq.id }, admin)
    await raw('POST', REC('sold_out'), { store: hq.id, item: a.id }, admin) // 본사 품절: 전 가맹점
    await raw('POST', REC('sold_out'), { store: branch1.id, item: b.id }, admin) // 가맹점 품절: 그 매장만

    const soldNames = (bd) => bd.items.filter((m) => m.soldOut).map((m) => m.name)
    const b1 = await api.getBoard(branch1.id)
    assert.deepStrictEqual([b1.store.name, b1.store.brandColor], ['1호점', '#123456'])
    assert.deepStrictEqual(b1.items.map((m) => m.name), ['공통A', '공통B'])
    assert.deepStrictEqual(b1.screens, [{ no: 1, type: 'grid', sectionIds: [section.id], callBand: false }])
    assert.deepStrictEqual(soldNames(b1), ['공통A', '공통B'])
    assert.deepStrictEqual(soldNames(await api.getBoard(branch2.id)), ['공통A'])
    assert.deepStrictEqual(soldNames(await api.getBoard(hq.id)), ['공통A'])

    // 가맹점 계정도 자기 매장 번호를 부른다. 번호는 그 매장에만 나온다
    await raw('POST', REC('users'), { email: 'branch1@menu.test', password: 'password-1234', passwordConfirm: 'password-1234', store: branch1.id }, admin)
    const ft = (await raw('POST', `${BASE}/api/collections/users/auth-with-password`, { identity: 'branch1@menu.test', password: 'password-1234' })).token
    await raw('POST', REC('calls'), { store: branch1.id, number: 7 }, ft)
    await assert.rejects(raw('POST', REC('calls'), { store: branch2.id, number: 8 }, ft), /400|403/, '다른 가맹점 번호는 못 부른다')
    assert.deepStrictEqual([(await api.getBoard(branch1.id)).calls, (await api.getBoard(branch2.id)).calls], [[7], []])
  } finally {
    const fu = await raw('GET', `${REC('users')}?filter=${encodeURIComponent("email='branch1@menu.test'")}`, null, admin)
    for (const u of fu.items) await raw('DELETE', `${REC('users')}/${u.id}`, null, admin)
    // 본사를 가리키는 가맹점부터 지운다. 매장을 지우면 구역·메뉴·품절·화면이 같이 지워진다.
    const all = await raw('GET', `${REC('stores')}?filter=${encodeURIComponent(`parent='${hq.id}'`)}`, null, admin)
    for (const s of all.items) await raw('DELETE', `${REC('stores')}/${s.id}`, null, admin)
    await raw('DELETE', `${REC('stores')}/${hq.id}`, null, admin)
  }

  // ── signUp: 빈 임시 서버에서 첫 설치 ──
  await checkSignUp()

  console.log('OK: session·logout·login·signUp, 매장 번호 없는 getBoard, 저장 함수 전부(20MB 사진 포함), ' +
    '번호 호출(30개 정리, 가맹점), onBoardChange 알림, 가맹점 합치기가 맞고, 샘플 매장은 처음 모양 그대로입니다.')
}

main().then(() => process.exit(0), (e) => { console.error(e); process.exit(1) })
