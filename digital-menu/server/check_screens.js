// pb_public/index.html(메뉴판 화면)을 서버 없이 가짜 데이터로 띄워, 화면 크기·방향·글자 배율마다 잘리는 글이 없는지 검사한다.
// 사용: node check_screens.js                 검사만 (기본 모습 + themes/list.json의 테마 전부)
//       node check_screens.js shots           검사하고 shots/ 폴더에 스크린샷도 저장 (shots/는 커밋하지 않는다)
//       node check_screens.js shots cafe      테마 하나만 (기본 모습만은 default)
// 필요: Playwright와 Chromium (npm i -g playwright 후 npx playwright install chromium)
// api.js만 같은 함수 이름의 가짜로 바꿔 끼우고, index.html과 board.js는 실제 파일을 그대로 쓴다.
const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')

const PUBLIC = path.join(__dirname, 'pb_public')
const OUT = path.join(__dirname, 'shots')
const SAVE = process.argv.includes('shots')
// 테마: '' = 테마 없음(기본 모습). 테마마다 견본 매장 이름·브랜드 색을 list.json에서 가져와 그 테마답게 찍는다.
const THEME_LIST = JSON.parse(fs.readFileSync(path.join(PUBLIC, 'themes', 'list.json'), 'utf8'))
const ONLY = process.argv.slice(2).filter((a) => a !== 'shots')[0]
const THEMES = [{ id: '' }].concat(THEME_LIST).filter((t) => !ONLY || (t.id || 'default') === ONLY)
if (!THEMES.length) { console.log('그런 테마가 없습니다: ' + ONLY); process.exit(1) }

const SIZES = [
  { name: 'fhd-landscape', width: 1920, height: 1080 },
  { name: '4k-landscape', width: 3840, height: 2160 },
  { name: 'fhd-portrait', width: 1080, height: 1920 },
]
const ZOOMS = [100, 150]

// 사진 대신 쓰는 그림 (색만 다른 컵·접시 그림, 4K에서도 깨지지 않게 SVG)
function photo(hue, kind) {
  const c1 = `hsl(${hue},55%,62%)`, c2 = `hsl(${hue},60%,28%)`, c3 = `hsl(${hue},45%,82%)`
  const body = kind === 'cake'
    ? `<path d="M210 520 L600 330 L990 520 L990 700 L210 700 Z" fill="${c3}"/><path d="M210 520 L990 520 L990 590 L210 590 Z" fill="${c1}"/><circle cx="600" cy="300" r="55" fill="#d7263d"/>`
    : `<path d="M380 300 L820 300 L770 800 L430 800 Z" fill="${c3}" opacity=".92"/><path d="M405 440 L795 440 L770 800 L430 800 Z" fill="${c1}"/><rect x="360" y="270" width="480" height="45" rx="20" fill="#fff" opacity=".9"/>`
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 900"><defs><radialGradient id="g" cx=".5" cy=".35" r=".8"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></radialGradient></defs><rect width="1200" height="900" fill="url(#g)"/><ellipse cx="600" cy="820" rx="380" ry="50" fill="#000" opacity=".25"/>${body}</svg>`
}
const BG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900"><defs><linearGradient id="w" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3b2a20"/><stop offset="1" stop-color="#1a120d"/></linearGradient></defs><rect width="1600" height="900" fill="url(#w)"/>${Array.from({ length: 18 }, (_, i) => `<rect x="0" y="${i * 50}" width="1600" height="2" fill="#000" opacity=".25"/>`).join('')}</svg>`
const PROMO = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3840 2160"><defs><linearGradient id="p" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd1dc"/><stop offset="1" stop-color="#c8102e"/></linearGradient></defs><rect width="3840" height="2160" fill="url(#p)"/><circle cx="1300" cy="1080" r="620" fill="#fff" opacity=".85"/><circle cx="1300" cy="1080" r="480" fill="#f48fb1"/><circle cx="2550" cy="1000" r="520" fill="#fff" opacity=".85"/><circle cx="2550" cy="1000" r="390" fill="#ad1457"/><text x="1920" y="1960" font-size="160" text-anchor="middle" fill="#fff" font-family="sans-serif" font-weight="700">SPRING STRAWBERRY</text></svg>`

const P = (n) => `/photos/${n}.svg`
const BOARD = {
  store: { name: '우리카페', brandColor: '#c8102e', backgroundUrl: '/photos/bg.svg' },
  sections: [
    { id: 's1', name: '커피', order: 1 },
    { id: 's2', name: '논커피', order: 2 },
    { id: 's3', name: '디저트', order: 3 },
  ],
  items: [
    { id: 'm1', sectionId: 's1', name: '아메리카노', prices: [{ label: 'HOT', amount: 4500 }, { label: 'ICE', amount: 5000 }], photoUrl: P('m1'), order: 1, soldOut: false, badge: 'best' },
    { id: 'm2', sectionId: 's1', name: '카페라떼', prices: [{ label: 'HOT', amount: 5000 }, { label: 'ICE', amount: 5500 }], photoUrl: P('m2'), order: 2, soldOut: false, badge: null },
    { id: 'm3', sectionId: 's1', name: '바닐라 크림 콜드브루', prices: [{ label: null, amount: 6300 }], photoUrl: P('m3'), order: 3, soldOut: false, badge: 'new' },
    { id: 'm4', sectionId: 's1', name: '카라멜 마키아토', prices: [{ label: 'HOT', amount: 5800 }, { label: 'ICE', amount: 6300 }], photoUrl: P('m4'), order: 4, soldOut: true, badge: null },
    { id: 'm5', sectionId: 's1', name: '에스프레소', prices: [{ label: null, amount: 4000 }], photoUrl: null, order: 5, soldOut: false, badge: null },
    { id: 'm6', sectionId: 's1', name: '돌체 라떼', prices: [{ label: 'HOT', amount: 5900 }, { label: 'ICE', amount: 6400 }], photoUrl: P('m6'), order: 6, soldOut: false, badge: null },
    { id: 'm7', sectionId: 's2', name: '딸기 라떼', prices: [{ label: null, amount: 6500 }], photoUrl: P('m7'), order: 7, soldOut: false, badge: 'new' },
    { id: 'm8', sectionId: 's2', name: '녹차 라떼', prices: [{ label: 'HOT', amount: 5500 }, { label: 'ICE', amount: 6000 }], photoUrl: P('m8'), order: 8, soldOut: false, badge: null },
    { id: 'm9', sectionId: 's2', name: '레몬 에이드', prices: [{ label: null, amount: 5800 }], photoUrl: null, order: 9, soldOut: false, badge: null },
    { id: 'm10', sectionId: 's2', name: '자몽 허니 블랙티', prices: [{ label: 'HOT', amount: 5700 }, { label: 'ICE', amount: 6200 }], photoUrl: P('m10'), order: 10, soldOut: false, badge: 'best' },
    { id: 'm11', sectionId: 's2', name: '초콜릿', prices: [{ label: 'HOT', amount: 5500 }, { label: 'ICE', amount: 6000 }], photoUrl: null, order: 11, soldOut: true, badge: null },
    { id: 'm12', sectionId: 's3', name: '딸기 생크림 케이크', prices: [{ label: null, amount: 7500 }], photoUrl: P('m12'), order: 12, soldOut: false, badge: 'new' },
    { id: 'm13', sectionId: 's3', name: '바스크 치즈케이크', prices: [{ label: null, amount: 6800 }], photoUrl: P('m13'), order: 13, soldOut: false, badge: null },
  ],
  screens: [
    { no: 1, type: 'grid', sectionIds: ['s1', 's3'], callBand: true },
    { no: 2, type: 'list', sectionIds: ['s1', 's2'], callBand: false },
    { no: 3, type: 'promo', imageUrl: '/photos/promo.svg', lines: ['봄 한정 딸기 시즌', '딸기 라떼 · 딸기 생크림 케이크 3월 31일까지'], callBand: true },
    { no: 4, type: 'calls' },
    { no: 5, type: 'list', sectionIds: ['s2'], callBand: true },
  ],
  calls: [1107, 1106, 1105, 1103, 1102, 1101, 1099, 1098, 1096],
}
const EMPTY_CALLS = { ...BOARD, calls: [] }
const HUES = { m1: 25, m2: 32, m3: 40, m4: 30, m6: 20, m7: 345, m8: 100, m10: 15, m12: 350, m13: 45 }

// 같은 함수 이름으로 가짜 데이터를 돌려주는 api.js (ui-prompt.md: 서버 없이 작업할 때)
function fakeApi(board) {
  return `window.api = { getBoard: function () { return Promise.resolve(${JSON.stringify(board)}) }, onBoardChange: function () {} }`
}

function themed(board, theme) {
  if (!theme.id) return board
  return { ...board, store: { ...board.store, name: theme.sampleStore || board.store.name, brandColor: theme.sampleBrand || board.store.brandColor } }
}

async function open(page, board, screen, zoom, theme = '') {
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    const p = url.pathname
    if (p === '/api.js') return route.fulfill({ contentType: 'text/javascript', body: fakeApi(board) })
    if (p === '/photos/bg.svg') return route.fulfill({ contentType: 'image/svg+xml', body: BG })
    if (p === '/photos/promo.svg') return route.fulfill({ contentType: 'image/svg+xml', body: PROMO })
    const m = p.match(/^\/photos\/(m\d+)\.svg$/)
    if (m) return route.fulfill({ contentType: 'image/svg+xml', body: photo(HUES[m[1]], /m1[23]/.test(m[1]) ? 'cake' : 'cup') })
    const file = path.join(PUBLIC, p === '/' ? 'index.html' : p)
    if (file.startsWith(PUBLIC) && fs.existsSync(file)) return route.fulfill({ path: file })
    return route.fulfill({ status: 404, body: '' })
  })
  await page.goto(`http://board.test/?screen=${screen}&zoom=${zoom}${theme ? '&theme=' + theme : ''}`)
  await page.waitForFunction(() => document.getElementById('main').childElementCount > 0)
  if (theme) await page.waitForFunction((t) => document.documentElement.getAttribute('data-theme') === t, theme, { timeout: 5000 })
  await page.evaluate(() => Promise.all([].map.call(document.images, (i) => i.complete || new Promise((r) => { i.onload = i.onerror = r }))))
  await page.unroute('**/*')
}

// 잘린 글: 글자(텍스트 노드)가 화면 밖에 있거나, 넘침을 자르는(overflow) 상자 밖으로 나간 것
function clipped() {
  const vw = innerWidth, vh = innerHeight, bad = []
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    const e = n.parentElement
    if (!n.textContent.trim() || e.closest('script,style,[hidden]')) continue
    const range = document.createRange()
    range.selectNodeContents(n)
    const boxes = []
    for (let p = e; p && p !== document.documentElement; p = p.parentElement) {
      if (getComputedStyle(p).overflow !== 'visible') boxes.push(p.getBoundingClientRect())
    }
    const cut = [].some.call(range.getClientRects(), (r) =>
      r.left < -2 || r.top < -2 || r.right > vw + 2 || r.bottom > vh + 2 ||
      boxes.some((q) => r.left < q.left - 2 || r.top < q.top - 2 || r.right > q.right + 2 || r.bottom > q.bottom + 2))
    if (cut) bad.push(`${e.tagName.toLowerCase()}.${e.className} "${n.textContent.trim().slice(0, 20)}"`)
  }
  return bad
}

;(async () => {
  if (SAVE) fs.mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch()
  let fails = 0
  for (const theme of THEMES) {
  const dir = path.join(OUT, theme.id || 'default')
  if (SAVE) fs.mkdirSync(dir, { recursive: true })
  for (const size of SIZES) {
    for (const zoom of ZOOMS) {
      const page = await browser.newPage({ viewport: { width: size.width, height: size.height }, deviceScaleFactor: 1 })
      const cases = [[BOARD, 1], [BOARD, 2], [BOARD, 3], [BOARD, 4], [BOARD, 5], [EMPTY_CALLS, 4]]
      for (const [board, screen] of cases) {
        await open(page, themed(board, theme), screen, zoom, theme.id)
        const name = `${size.name}-z${zoom}-screen${screen}${board === EMPTY_CALLS ? '-empty' : ''}`
        const bad = await page.evaluate(clipped)
        if (bad.length) { fails++; console.log('잘림', theme.id || 'default', name, bad.slice(0, 5)) } else console.log('통과', theme.id || 'default', name)
        if (SAVE) await page.screenshot({ path: path.join(dir, name + '.png') })
      }
      await page.close()
    }
  }
  }
  // 새 번호가 불리면 첫 번호만 깜빡이고, 같은 번호로 다시 그리면 깜빡이지 않는다
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
  await open(page, BOARD, 1, 100)
  const flash = await page.evaluate((b) => {
    const r = []
    r.push(!!document.querySelector('.flash')) // 처음 그릴 때는 깜빡이지 않음
    renderBoard(b, 1); r.push(!!document.querySelector('.flash')) // 같은 번호
    b.calls.unshift(1108); renderBoard(b, 1); r.push(!!document.querySelector('#band .now.flash')) // 새 번호
    return r
  }, BOARD)
  if (flash.join() !== 'false,false,true') { fails++; console.log('깜빡임 실패', flash) } else console.log('통과 새 번호 깜빡임')
  await browser.close()
  console.log(fails ? `실패 ${fails}건` : '모두 통과')
  process.exit(fails ? 1 : 0)
})()
