// 안내서용 화면 캡처: 임시 PocketBase(127.0.0.1:8097)에 샘플 매장 '포스윙 카페'를 넣고 화면을 찍는다.
// 사용: node make-shots.js ../../../server <출력 폴더>  (POCKETBASE=pocketbase 실행 파일 경로)  → python3 prepare-images.py <출력 폴더>
const fs = require('fs'), os = require('os'), path = require('path')
const { spawn, spawnSync } = require('child_process')
const { chromium } = require('playwright')

const SRC = path.resolve(process.argv[2]), OUT = path.resolve(process.argv[3])
const PB = process.env.POCKETBASE || path.join(SRC, process.platform === 'win32' ? 'pocketbase.exe' : 'pocketbase')
const BASE = 'http://127.0.0.1:8097'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const EMAIL = 'owner@cafe.test', PW = 'password-1234'
fs.mkdirSync(OUT, { recursive: true })

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pbshots-'))
for (const d of ['pb_migrations', 'pb_hooks', 'pb_public']) fs.cpSync(path.join(SRC, d), path.join(dir, d), { recursive: true })
spawnSync(PB, ['migrate', 'up', '--dir', dir + '/pb_data', '--migrationsDir', dir + '/pb_migrations'], { stdio: 'inherit' })
spawnSync(PB, ['superuser', 'upsert', 'su@test.local', 'su-password-1234', '--dir', dir + '/pb_data'], { stdio: 'inherit' })
const server = spawn(PB, ['serve', '--http', '127.0.0.1:8097', '--dir', dir + '/pb_data', '--migrationsDir', dir + '/pb_migrations',
  '--hooksDir', dir + '/pb_hooks', '--publicDir', dir + '/pb_public'], { stdio: 'ignore' })

async function req(method, url, body, token, raw) {
  const headers = {}
  if (token) headers.Authorization = token
  let data = body
  if (body && !(body instanceof FormData) && !raw) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(body) }
  if (raw) headers['Content-Type'] = raw
  const res = await fetch(BASE + url, { method, headers, body: data })
  const text = await res.text()
  if (res.status >= 300) throw new Error(method + ' ' + url + ' ' + res.status + ' ' + text)
  return text ? JSON.parse(text) : {}
}

// 그림 사진: 이모지 음식을 큰 접시 위에 그려 JPEG로
async function makePhoto(page, emoji, bg) {
  const b64 = await page.evaluate(([emoji, bg]) => {
    const c = document.createElement('canvas'); c.width = 800; c.height = 600
    const x = c.getContext('2d')
    const g = x.createLinearGradient(0, 0, 800, 600); g.addColorStop(0, bg[0]); g.addColorStop(1, bg[1])
    x.fillStyle = g; x.fillRect(0, 0, 800, 600)
    x.fillStyle = 'rgba(255,255,255,.55)'; x.beginPath(); x.ellipse(400, 330, 260, 200, 0, 0, Math.PI * 2); x.fill()
    x.font = '300px "Noto Color Emoji"'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(emoji, 400, 320)
    return c.toDataURL('image/jpeg', 0.85).split(',')[1]
  }, [emoji, bg])
  return Buffer.from(b64, 'base64')
}

// 찍기 전에 표시할 곳에 빨간 테두리와 번호
async function mark(page, marks) {
  await page.evaluate((marks) => {
    document.querySelectorAll('.guide-mark').forEach((n) => n.remove())
    marks.forEach(([sel, label, nth]) => {
      const all = document.querySelectorAll(sel)
      const node = all[nth || 0]
      if (!node) { console.log('no ' + sel); return }
      const r = node.getBoundingClientRect()
      const box = document.createElement('div'); box.className = 'guide-mark'
      Object.assign(box.style, { position: 'absolute', left: (r.left + scrollX - 4) + 'px', top: (r.top + scrollY - 4) + 'px', width: (r.width + 8) + 'px',
        height: (r.height + 8) + 'px', border: '3px solid #e5322d', borderRadius: '8px', zIndex: 9999, pointerEvents: 'none', boxSizing: 'border-box' })
      const b = document.createElement('div'); b.className = 'guide-mark'; b.textContent = label
      Object.assign(b.style, { position: 'absolute', left: (r.left + scrollX - 16) + 'px', top: (r.top + scrollY - 16) + 'px', minWidth: '28px', height: '28px', padding: '0 6px',
        borderRadius: '14px', background: '#e5322d', color: '#fff', font: 'bold 16px/28px sans-serif', textAlign: 'center', zIndex: 10000, boxSizing: 'border-box' })
      document.body.appendChild(box); document.body.appendChild(b)
    })
  }, marks)
}
async function clipSection(page, title, file, marks, opts = {}) {
  const h2 = page.locator('h2', { hasText: title }).first()
  const sec = h2.locator('xpath=..')
  await page.evaluate(() => { const m = document.getElementById('msg'); if (m) m.style.display = 'none' })
  await sec.scrollIntoViewIfNeeded()
  if (marks) await mark(page, marks)
  await sec.screenshot({ path: path.join(OUT, file) })
  await mark(page, [])
}

async function main() {
  for (let i = 0; i < 60; i++) { try { await fetch(BASE + '/api/health'); break } catch (e) { await sleep(250) } }
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ locale: 'ko-KR', viewport: { width: 1366, height: 768 } })
  const page = await ctx.newPage()
  page.on('dialog', (d) => d.accept())
  page.on('console', (m) => { if (m.text().startsWith('no ')) console.log(m.text()) })

  // 로그인 화면(첫 설치)
  await page.goto(BASE + '/admin.html'); await sleep(800)
  await page.fill('#email', EMAIL); await page.fill('#password', PW); await page.fill('#storeName', '포스윙 카페')
  await mark(page, [['#email', '1'], ['#password', '2'], ['#storeName', '3'], ['#signUp', '4']])
  await page.screenshot({ path: path.join(OUT, 'admin-first-setup.png') })
  await mark(page, [])
  await page.click('#signUp'); await sleep(1500)

  const su = (await req('POST', '/api/collections/_superusers/auth-with-password', { identity: 'su@test.local', password: 'su-password-1234' })).token
  const store = (await req('GET', '/api/collections/stores/records', null, su)).items[0].id
  const mk = (c, f) => req('POST', '/api/collections/' + c + '/records', f, su)
  const coffee = await mk('sections', { store, name: '커피', sort_order: 1 })
  const drink = await mk('sections', { store, name: '음료·차', sort_order: 2 })
  const dessert = await mk('sections', { store, name: '디저트', sort_order: 3 })
  const menu = [
    [coffee, '아메리카노', [{ label: 'HOT', amount: 4500 }, { label: 'ICE', amount: 5000 }], '☕', ['#c8a27a', '#6b4226'], 'best'],
    [coffee, '카페라떼', [{ label: 'HOT', amount: 5000 }, { label: 'ICE', amount: 5500 }], '🥛', ['#f1dfc8', '#a67c52']],
    [coffee, '바닐라라떼', [{ label: null, amount: 5500 }], '🧋', ['#fff0c9', '#d9a441'], 'new'],
    [coffee, '콜드브루', [{ label: null, amount: 5300 }], '🧊', ['#9ec5e8', '#3b5f80']],
    [drink, '레몬에이드', [{ label: null, amount: 5800 }], '🍋', ['#fff59d', '#f6c700']],
    [drink, '딸기 스무디', [{ label: null, amount: 6300 }], '🍓', ['#ffc1cc', '#d63c5a'], 'new'],
    [drink, '캐모마일', [{ label: null, amount: 4800 }], '🍵', ['#e2f0cb', '#7fa650']],
    [dessert, '치즈케이크', [{ label: null, amount: 6800 }], '🍰', ['#fff3e0', '#e0a96d'], 'best'],
    [dessert, '크루아상', [{ label: null, amount: 3900 }], '🥐', ['#ffe0b2', '#c47f2c']],
    [dessert, '초코 쿠키', [{ label: null, amount: 2800 }], '🍪', ['#d7b899', '#6d4c33']],
  ]
  const ids = {}
  for (let i = 0; i < menu.length; i++) {
    const [sec, name, prices, emoji, bg, badge] = menu[i]
    const fd = new FormData()
    fd.append('store', store); fd.append('section', sec.id); fd.append('name', name); fd.append('prices', JSON.stringify(prices))
    fd.append('sort_order', String(i + 1)); if (badge) fd.append('badge', badge)
    fd.append('photo', new Blob([await makePhoto(page, emoji, bg)], { type: 'image/jpeg' }), 'p' + i + '.jpg')
    ids[name] = (await req('POST', '/api/collections/items/records', fd, su)).id
  }
  await mk('screens', { store, no: 1, type: 'grid', sections: [coffee.id, drink.id], call_band: true })
  await mk('screens', { store, no: 2, type: 'list', sections: [dessert.id], call_band: true })
  await mk('screens', { store, no: 3, type: 'calls' })
  await mk('sold_out', { store, item: ids['콜드브루'] })
  for (const n of [101, 102, 104, 105]) { await mk('calls', { store, number: n }); await sleep(30) }

  // TV 두 대 등록·보고
  const tvs = [['카운터 왼쪽 TV', 1, 0], ['카운터 오른쪽 TV', 2, 0]]
  for (const [name, screen, rot] of tvs) {
    const r = await req('POST', '/api/menuboard/devices/register', { name, model: 'RK3568 보드', version: '1.2' })
    const hdr = { Authorization: 'Bearer ' + r.token, 'X-Device-Token': r.token, 'Content-Type': 'application/json' }
    await fetch(BASE + '/api/menuboard/devices/report', { method: 'POST', headers: hdr, body: JSON.stringify({ version: '1.2', model: 'RK3568 보드',
      reported: { server: '192.168.0.10:8090', screen, zoom: 100, rotation: rot, brightness: -1, adb: false, canAdb: true, rev: 0, width: 1920, height: 1080 } }) })
      .then((x) => x.text()).then((t) => { if (t.indexOf('error') >= 0 || t.indexOf('message') >= 0) console.log('report', t) })
  }

  // TV 화면들
  const tv = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
  for (const n of [1, 2, 3]) {
    await tv.goto(BASE + '/?screen=' + n + '&zoom=100'); await sleep(2500)
    await tv.screenshot({ path: path.join(OUT, 'tv-screen' + n + '.png') })
  }
  // 캡처 사진을 TV 1에 올리기
  // (devices 목록에 사진이 보이게 tv-screen1을 JPEG로)
  const shotJpg = await tv.screenshot({ type: 'jpeg', quality: 70, clip: { x: 0, y: 0, width: 1920, height: 1080 } })
  const devs = (await req('GET', '/api/collections/devices/records', null, su)).items
  await tv.close()

  // 수정 화면 (POS 1366)
  await page.goto(BASE + '/admin.html'); await sleep(800)
  if (await page.isVisible('#login')) { await page.fill('#email', EMAIL); await page.fill('#password', PW); await page.click('#login') }
  await page.waitForSelector('#items .row'); await sleep(1000)
  await page.screenshot({ path: path.join(OUT, 'admin-top.png') })
  await page.screenshot({ path: path.join(OUT, 'admin-full.png'), fullPage: true })
  await clipSection(page, '번호 호출', 'admin-calls.png', [['#calls input', '1'], ['#calls button', '2']])
  await clipSection(page, '지금 품절', 'admin-soldout.png', [['#soldout button', '1']])
  await clipSection(page, '구역', 'admin-sections.png', [['#sections .row:last-child input', '1', 0], ['#sections .row:last-child button', '2', 0]])
  {
    const r0 = page.locator('#items .row').first()
    await r0.scrollIntoViewIfNeeded()
    await mark(page, [['#items .row input', '1', 0], ['#items .row select', '2', 0], ['#items .row input.price', '3', 0], ['#items .row input[type=file]', '4', 0],
      ['#items .row input[type=checkbox]', '5', 1], ['#items .row button', '6', 0]])
    const bb = await r0.boundingBox()
    await page.screenshot({ path: path.join(OUT, 'admin-item-row.png'), clip: { x: 0, y: bb.y - 22, width: 1366, height: bb.height + 34 } })
    await mark(page, [])
    const last = page.locator('#items .row').last()
    await last.scrollIntoViewIfNeeded()
    const lb = await last.boundingBox()
    await page.screenshot({ path: path.join(OUT, 'admin-item-new.png'), clip: { x: 0, y: lb.y - 10, width: 1366, height: lb.height + 20 } })
  }
  await clipSection(page, '메뉴', 'admin-items.png')
  await clipSection(page, '화면 구성', 'admin-screens.png', [['#screens select', '1', 0], ['#screens input[type=checkbox]', '2', 0], ['#screens button', '3', 0]])
  await clipSection(page, 'POS·키오스크 연동', 'admin-pos.png')
  // 가격 실수 확인창 문구 캡처를 위해 아메리카노 가격을 45000으로
  const msgs = []
  page.removeAllListeners('dialog')
  page.on('dialog', (d) => { msgs.push(d.message()); d.dismiss() })
  const row = page.locator('#items .row').first()
  await row.locator('input.price').first().fill('45000')
  await row.getByRole('button', { name: '저장' }).click().catch(() => {})
  await sleep(800)
  fs.writeFileSync(path.join(OUT, 'dialogs.txt'), msgs.join('\n----\n'))
  page.removeAllListeners('dialog'); page.on('dialog', (d) => d.accept())
  await page.goto(BASE + '/admin.html'); await page.waitForSelector('#items .row'); await sleep(800)

  // 미리보기
  const pv = page.getByRole('button', { name: /미리보기/ }).first()
  if (await pv.count()) { await pv.click(); await sleep(2500); await page.screenshot({ path: path.join(OUT, 'admin-preview.png') }); await page.click('#pvClose') }

  // 폰
  const phone = await (await browser.newContext({ locale: 'ko-KR', viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage()
  await phone.goto(BASE + '/admin.html'); await sleep(600)
  if (await phone.isVisible('#login')) { await phone.fill('#email', EMAIL); await phone.fill('#password', PW); await phone.click('#login') }
  await phone.waitForSelector('#items .row'); await sleep(800)
  await phone.screenshot({ path: path.join(OUT, 'phone-top.png') })
  await phone.locator('h2', { hasText: '메뉴' }).first().scrollIntoViewIfNeeded()
  await phone.evaluate(() => window.scrollBy(0, -10))
  await phone.screenshot({ path: path.join(OUT, 'phone-items.png') })

  // TV 관리
  await page.goto(BASE + '/devices.html'); await sleep(800)
  if (await page.isVisible('#login')) { await page.fill('#email', EMAIL); await page.fill('#password', PW); await page.click('#login') }
  await sleep(2000)
  await page.screenshot({ path: path.join(OUT, 'devices-full.png'), fullPage: true })
  await page.locator('h2', { hasText: 'TV 목록' }).locator('xpath=..').screenshot({ path: path.join(OUT, 'devices-list.png') })
  await page.locator('h2', { hasText: 'USB 설정 파일' }).locator('xpath=..').screenshot({ path: path.join(OUT, 'devices-usb.png') })

  // 비밀번호 다시 정하기
  await page.goto(BASE + '/reset.html'); await sleep(1200)
  await page.screenshot({ path: path.join(OUT, 'reset.png') })

  await browser.close()
}
main().catch((e) => { console.error(e); process.exitCode = 1 }).finally(() => { server.kill(); fs.rmSync(dir, { recursive: true, force: true }) })
