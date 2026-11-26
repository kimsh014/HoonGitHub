// 수정 화면(pb_public/admin.html)을 실제 브라우저로 눌러 본다. 사용: node check_admin.js
// 임시 폴더로 빈 서버(127.0.0.1:8094)를 잠깐 띄워 검사하므로 켜 둔 서버(8090)나 샘플 매장은 건드리지 않는다.
// 필요한 것: pocketbase 실행 파일(다른 위치면 POCKETBASE 환경 변수), Playwright(npm i playwright, npx playwright install chromium).
// 확인하는 것: 첫 계정 만들기, 가격 "4,500원" 읽기, 가격 10배 확인창, 100원 단위 경고, 저장 중 버튼 잠금,
// 어느 TV 화면에 나오는지 안내, 큰 사진을 1920px로 줄여 올림, 품절 목록과 품절 풀기, 메뉴가 있는 구역 지우기 막기,
// TV 미리보기, TV가 쓰는 화면 지우기 확인(TV 이름), 폰 크기에서 옆으로 넘치지 않음, 다시 로그인.
const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawn, spawnSync } = require('child_process')
const { chromium } = require('playwright')

const BASE = 'http://127.0.0.1:8094'
const PB = process.env.POCKETBASE || path.join(__dirname, 'pocketbase.exe')
const SHOTS = process.env.SHOTS // 화면 사진을 남길 폴더(선택)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const EMAIL = 'owner@menu.test', PASSWORD = 'password-1234'

async function call(method, url, body, headers = {}) {
  const res = await fetch(BASE + url, {
    method,
    headers: { ...headers, ...(body && { 'Content-Type': 'application/json' }) },
    body: body && JSON.stringify(body),
  })
  const text = await res.text()
  assert.ok(res.status < 300, `${method} ${url}: ${res.status} ${text}`)
  return text ? JSON.parse(text) : {}
}

async function main(browser) {
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  // 확인창: answers 앞에서부터 하나씩 꺼내 답한다(비면 확인)
  const dialogs = [], answers = []
  page.on('dialog', (d) => {
    dialogs.push(d.message())
    return answers.shift() === 'dismiss' ? d.dismiss() : d.accept()
  })
  const msg = (text) => page.waitForFunction((t) => document.getElementById('msg').textContent.indexOf(t) >= 0, text, { timeout: 10000 })
    .catch(async () => assert.fail(`안내 "${text}"가 안 나옴. 지금 안내: ${await page.textContent('#msg')}`))
  const idle = () => page.waitForFunction(() => !document.querySelector('#app button:disabled'), null, { timeout: 10000 })
  const shot = async (name) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, name + '.png'), fullPage: true }) }

  let token = null
  const api = async (url) => {
    if (!token) token = (await call('POST', '/api/collections/users/auth-with-password', { identity: EMAIL, password: PASSWORD })).token
    return call('GET', url, null, { Authorization: token })
  }
  const items = async () => (await api('/api/collections/items/records?sort=sort_order')).items

  // ── 첫 계정 ──
  await page.goto(BASE + '/admin.html')
  await shot('1-login')
  await page.fill('#email', EMAIL)
  await page.fill('#password', PASSWORD)
  await page.fill('#storeName', '검사카페')
  await page.click('#signUp')
  await msg('설치를 마쳤습니다')
  await page.waitForSelector('#sections .row')

  // ── 구역 ──
  await page.locator('#sections .row').last().locator('input').first().fill('커피')
  await page.locator('#sections .row').last().getByRole('button', { name: '추가' }).click()
  await msg('구역을 추가했습니다')
  await idle()
  assert.match(await page.locator('#sections .row').first().textContent(), /TV에 안 나옴/)

  // ── 메뉴 추가: "4,500원"으로 넣어도 4500 ──
  let row = page.locator('#items .row').last()
  await row.locator('input[placeholder="메뉴 이름"]').fill('아메리카노')
  await row.locator('input.price').first().fill('4,500원')
  assert.strictEqual(await row.locator('.won').first().textContent(), '4,500원')
  assert.strictEqual(await row.locator('input.price').first().getAttribute('inputmode'), 'numeric')
  await row.getByRole('button', { name: '추가' }).click()
  await msg('이 구역은 어느 화면에도 없어 TV에 나오지 않습니다')
  await idle()
  assert.deepStrictEqual((await items())[0].prices, [{ label: null, amount: 4500 }])

  // 100원 단위가 아니면 묻고, 아니오면 저장하지 않는다
  row = page.locator('#items .row').last()
  await row.locator('input[placeholder="메뉴 이름"]').fill('쿠키')
  await row.locator('input.price').first().fill('4550')
  answers.push('dismiss')
  await row.getByRole('button', { name: '추가' }).click()
  await msg('저장하지 않았습니다')
  assert.match(dialogs[dialogs.length - 1], /4,550원은 100원 단위가 아닙니다/)
  assert.strictEqual((await items()).length, 1)

  // ── 가격 10배: 확인창, 아니오면 그대로, 예면 저장 ──
  row = page.locator('#items .row').first()
  await row.locator('input.price').first().fill('45000')
  answers.push('dismiss')
  await row.getByRole('button', { name: '저장' }).click()
  await msg('저장하지 않았습니다')
  assert.strictEqual(dialogs[dialogs.length - 1], '4,500원 → 45,000원, 맞나요?')
  assert.strictEqual((await items())[0].prices[0].amount, 4500)
  answers.push('accept')
  await row.getByRole('button', { name: '저장' }).click()
  await msg('메뉴를 저장했습니다')
  await idle()
  assert.strictEqual((await items())[0].prices[0].amount, 45000)
  console.log('  가격: "4,500원" → 4500, 10배 확인창, 100원 단위 경고')

  // ── 화면 1(사진 격자)에 커피 구역 넣기 ──
  await page.getByRole('button', { name: '화면 더하기' }).click()
  await page.locator('#screens .row').last().getByLabel('커피').check()
  await page.getByRole('button', { name: '화면 구성 저장' }).click()
  await msg('화면 구성을 저장했습니다')
  await idle()
  assert.match(await page.locator('#sections .row').first().textContent(), /TV 화면 1번/)

  // 사진 없는 메뉴는 격자 화면에 안 나온다고 알린다. 이름이 길면 경고(저장은 된다)
  row = page.locator('#items .row').first()
  await row.locator('input[placeholder="메뉴 이름"]').fill('아메리카노 아주 진하게 내린 큰 컵 한정판')
  await row.getByRole('button', { name: '저장' }).click()
  await msg('사진이 없어 TV에 나오지 않습니다')
  await msg('이름이 20자를 넘어')
  await idle()
  row = page.locator('#items .row').first()
  await row.locator('input[placeholder="메뉴 이름"]').fill('아메리카노')

  // ── 큰 사진: 브라우저가 1920px JPEG로 줄여 올린다 ──
  const big = Buffer.from(await page.evaluate(() => {
    const c = document.createElement('canvas')
    c.width = 4032; c.height = 3024
    const g = c.getContext('2d')
    const d = g.createImageData(c.width, c.height) // 잘 안 눌리는 잡음 사진(실제 폰 사진처럼 몇 MB)
    for (let i = 0; i < d.data.length; i += 4) {
      d.data[i] = (i >> 6) % 256; d.data[i + 1] = Math.random() * 255; d.data[i + 2] = 128; d.data[i + 3] = 255
    }
    g.putImageData(d, 0, 0)
    return new Promise((r) => c.toBlob((b) => {
      const f = new FileReader()
      f.onload = () => r(f.result.split(',')[1])
      f.readAsDataURL(b)
    }, 'image/jpeg', 0.95))
  }), 'base64')
  await row.locator('input[type=file]').setInputFiles({ name: 'big.jpg', mimeType: 'image/jpeg', buffer: big })
  await row.locator('.note', { hasText: '줄임' }).waitFor({ timeout: 10000 })
  assert.ok(await row.locator('img').first().isVisible(), '고른 사진 미리보기가 안 보임')
  // 저장하는 동안: 누른 버튼은 "저장 중…", 화면의 버튼은 모두 잠김
  await page.evaluate(() => {
    window.__busy = []
    new MutationObserver(() => {
      const b = Array.prototype.some.call(document.querySelectorAll('#app button'), (x) => x.textContent === '저장 중…')
      if (b) window.__busy.push(document.querySelectorAll('#app button:not(:disabled)').length)
    }).observe(document.getElementById('app'), { subtree: true, childList: true, characterData: true, attributes: true })
  })
  await row.getByRole('button', { name: '저장' }).click()
  await msg('이 메뉴는 TV 1번 화면에 나옵니다')
  await idle()
  const busy = await page.evaluate(() => window.__busy)
  assert.ok(busy.length && busy.every((n) => n === 0), `저장 중 버튼 잠금이 안 됨: ${JSON.stringify(busy)}`)
  const saved = (await items())[0]
  assert.ok(saved.photo, '사진이 저장되지 않음')
  const photoUrl = `/api/files/${saved.collectionId}/${saved.id}/${saved.photo}`
  const stored = await page.evaluate(async (u) => {
    const blob = await (await fetch(u)).blob()
    const bmp = await createImageBitmap(blob)
    return { size: blob.size, width: bmp.width, height: bmp.height }
  }, photoUrl)
  assert.strictEqual(stored.width, 1920)
  assert.strictEqual(stored.height, 1440)
  assert.ok(stored.size < big.length / 2, `사진이 줄지 않음: ${big.length} → ${stored.size}`)
  console.log(`  사진: 4032×3024 ${(big.length / 1e6).toFixed(1)}MB → ${stored.width}×${stored.height} ${(stored.size / 1e6).toFixed(2)}MB`)
  await shot('2-pos-1366')

  // ── 품절 목록과 품절 풀기 ──
  assert.match(await page.textContent('#soldout'), /품절인 메뉴가 없습니다/)
  await page.locator('#items .row').first().getByLabel('품절').check()
  await page.locator('#soldout', { hasText: '지금 품절 1개: 아메리카노' }).waitFor({ timeout: 10000 })
  await idle()
  await page.locator('#soldout').getByRole('button', { name: '품절 풀기' }).click()
  await page.locator('#soldout', { hasText: '품절인 메뉴가 없습니다' }).waitFor({ timeout: 10000 })
  await idle()

  // ── 메뉴가 있는 구역은 지우지 않는다(확인창도 없이 안내만) ──
  const before = dialogs.length
  await page.locator('#sections .row').first().getByRole('button', { name: '삭제' }).click()
  await msg('메뉴 1개가 있습니다. 메뉴를 다른 구역으로 옮기거나 지운 뒤 구역을 지워 주세요.')
  assert.strictEqual(dialogs.length, before)
  assert.strictEqual((await api('/api/collections/sections/records')).items.length, 1)
  console.log('  구역 지우기 막힘, 품절 목록, 저장 중 잠금, 어느 화면에 나오는지 안내')

  // ── TV 미리보기 ──
  await page.locator('#screens .row').first().getByRole('button', { name: '미리보기' }).click()
  await page.locator('#preview').waitFor({ state: 'visible' })
  assert.match(await page.getAttribute('#pvFrame iframe', 'src'), /screen=1$/)
  await page.frameLocator('#pvFrame iframe').getByText('아메리카노').first().waitFor({ timeout: 10000 })
  await shot('3-preview')
  await page.click('#pvClose')
  await page.locator('#preview').waitFor({ state: 'hidden' })

  // ── TV가 띄운 화면을 지우려 하면 그 TV 이름으로 묻는다 ──
  const tv = await call('POST', '/api/menuboard/devices/register', { name: '카운터 TV', model: 'test', version: '1' })
  await call('POST', '/api/menuboard/devices/report', { version: '1', model: 'test', reported: { screen: 1 } }, { 'X-Device-Token': tv.token })
  await page.reload()
  await page.locator('#screens .row', { hasText: '띄운 TV: 카운터 TV' }).waitFor({ timeout: 10000 })
  await page.locator('#screens .row').first().getByRole('button', { name: '빼기' }).click()
  answers.push('dismiss')
  await page.getByRole('button', { name: '화면 구성 저장' }).click()
  await msg('화면 구성을 저장하지 않았습니다')
  assert.match(dialogs[dialogs.length - 1], /1번 화면을 지우면 이 화면을 띄운 TV\(카운터 TV\)에는 메뉴 대신 매장 이름만 나옵니다/)
  assert.strictEqual((await api('/api/collections/screens/records')).items.length, 1)
  console.log('  TV 미리보기, TV가 쓰는 화면 지우기 확인')

  // ── 폰 크기: 옆으로 넘치지 않음 ──
  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await page.waitForSelector('#items .row')
  const wide = await page.evaluate(() => document.documentElement.scrollWidth)
  assert.ok(wide <= 390, `폰 화면에서 옆으로 넘침: ${wide}px`)
  await shot('4-phone-390')

  // ── 로그아웃 후 다시 로그인 ──
  await page.click('#logout')
  await page.fill('#email', EMAIL)
  await page.fill('#password', PASSWORD)
  await page.click('#login')
  await page.waitForSelector('#items .row')
  assert.deepStrictEqual(errors, [], '화면 스크립트 오류')
}

async function run() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'menuboard-admin-'))
  const dirs = ['migrations', 'hooks', 'public'].flatMap((d) => [`--${d}Dir`, path.join(__dirname, `pb_${d}`)])
  const su = spawnSync(PB, ['superuser', 'upsert', 'admin@menu.test', 'password-1234', '--dir', dir, ...dirs], { encoding: 'utf8' })
  assert.strictEqual(su.status, 0, `관리자 계정 만들기 실패 (${PB}): ${su.stderr || su.error}`)
  const pb = spawn(PB, ['serve', '--http', '127.0.0.1:8094', '--dir', dir, ...dirs], { stdio: 'ignore' })
  let browser = null
  let failed = false
  try {
    for (let i = 0; ; i++) {
      if (await fetch(`${BASE}/api/health`).then((x) => x.ok, () => false)) break
      assert.ok(i < 100, '임시 서버가 10초 안에 뜨지 않음')
      await sleep(100)
    }
    browser = await chromium.launch()
    await main(browser)
    console.log('OK: 수정 화면의 가격·사진·저장 잠금·구역 지우기·품절·화면 안내·미리보기가 설계대로입니다.')
  } catch (err) {
    failed = true
    console.error(err)
  } finally {
    if (browser) await browser.close()
    pb.kill()
    await new Promise((x) => pb.once('exit', x))
    fs.rmSync(dir, { recursive: true, force: true })
  }
  process.exit(failed ? 1 : 0)
}
run()
