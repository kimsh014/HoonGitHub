// 테마 파일(pb_public/themes/*.css) 검사. 서버·브라우저 없이 돈다. 사용: node check_themes.js
// UI팀이 테마를 더하거나 고친 뒤, PR을 올리기 전에 돌린다. 화면 잘림은 check_screens.js가 따로 본다.
// 확인하는 것:
//  1. themes/list.json의 테마마다 같은 이름의 .css 파일이 있고, 이름은 영어 소문자·숫자·- 만 (주소에 들어감)
//  2. 테마 파일은 :root { --이름: 값; } 한 덩어리만. 다른 선택자·@import·<script> 없음 (배치는 개발팀 몫)
//  3. 바꾸는 변수는 index.html의 "테마 값" 블록에 있는 것만 (--brand, --on-brand, --zoom, --fit, --pad는 못 바꿈)
//  4. url()은 themes/ 폴더 안의 파일만 (매장 인터넷이 끊겨도 보이게, 바깥 주소로 손님 화면이 새지 않게)
//  5. 글자색과 바탕색이 둘 다 고정 색(#rrggbb)인 짝은 명도 대비 4.5 이상 (천장 TV를 멀리서 읽음)
//  6. 파일 크기 20KB 이하
const fs = require('fs')
const path = require('path')

const PUBLIC = path.join(__dirname, 'pb_public')
const DIR = path.join(PUBLIC, 'themes')
const html = fs.readFileSync(path.join(PUBLIC, 'index.html'), 'utf8')
const block = html.split('테마 값: themes/*.css는')[1].split('테마 값 끝')[0]
const ALLOWED = new Set(block.match(/--[a-z0-9-]+(?=\s*:)/g))
const PAIRS = [ // [글자, 바탕]
  ['--ink', '--base'], ['--ink', '--panel'], ['--top-ink', '--top-bg'], ['--title-ink', '--title-bg'],
  ['--band-ink', '--band-bg'], ['--call-ink', '--call-bg'], ['--sold-ink', '--sold-bg'],
  ['--badge-new-ink', '--badge-new-bg'], ['--badge-best-ink', '--badge-best-bg'],
]

function lum(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return null
  const c = [0, 2, 4].map((i) => {
    const v = parseInt(m[1].substr(i, 2), 16) / 255
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}
const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)

let fails = 0
const bad = (theme, msg) => { fails++; console.log('실패', theme, msg) }

const list = JSON.parse(fs.readFileSync(path.join(DIR, 'list.json'), 'utf8'))
const ids = new Set()
for (const t of list) {
  const before = fails
  if (!/^[a-z0-9-]{1,32}$/.test(t.id || '')) { bad(t.id, '이름은 영어 소문자·숫자·- 1~32자'); continue }
  if (ids.has(t.id)) bad(t.id, 'list.json에 두 번 있음')
  ids.add(t.id)
  if (!t.name || !t.desc) bad(t.id, 'list.json에 name(보이는 이름)과 desc(설명)가 있어야 함')
  if (t.sampleBrand && lum(t.sampleBrand) === null) bad(t.id, 'sampleBrand는 #rrggbb')
  const file = path.join(DIR, t.id + '.css')
  if (!fs.existsSync(file)) { bad(t.id, 'themes/' + t.id + '.css 파일이 없음'); continue }
  const raw = fs.readFileSync(file, 'utf8')
  if (raw.length > 20000) bad(t.id, '파일이 20KB보다 큼')
  const css = raw.replace(/\/\*[\s\S]*?\*\//g, '').trim()
  const m = /^:root\s*\{([\s\S]*)\}$/.exec(css)
  if (!m || /[{}]/.test(m[1])) { bad(t.id, ':root { ... } 한 덩어리만 쓸 수 있음 (다른 선택자·@규칙 금지)'); continue }
  if (/@import|<|expression\(|javascript:/i.test(m[1])) bad(t.id, '@import·태그·스크립트는 쓸 수 없음')
  const vars = {}
  for (const decl of m[1].split(';').map((d) => d.trim()).filter(Boolean)) {
    const d = /^(--[a-z0-9-]+)\s*:\s*([\s\S]+)$/.exec(decl)
    if (!d) { bad(t.id, '변수가 아닌 줄: ' + decl.slice(0, 40)); continue }
    if (!ALLOWED.has(d[1])) bad(t.id, d[1] + '는 테마가 바꿀 수 없는 값 (index.html의 테마 값 목록 참고)')
    for (const u of d[2].match(/url\(([^)]*)\)/gi) || []) {
      const p = u.slice(4, -1).trim().replace(/^['"]|['"]$/g, '')
      if (/^[a-z]+:|^\/\/|^\/|\.\./i.test(p)) bad(t.id, 'url()은 themes/ 안의 파일만: ' + p)
      else if (!fs.existsSync(path.join(DIR, p))) bad(t.id, 'url() 파일이 없음: themes/' + p)
    }
    vars[d[1]] = d[2].trim()
  }
  for (const [fg, bg] of PAIRS) {
    const a = lum(vars[fg] || ''), b = lum(vars[bg] || '')
    if (a === null || b === null) continue // 브랜드 색·반투명·그라데이션은 화면에서 눈으로 (check_screens.js 스크린샷)
    const r = ratio(a, b)
    if (r < 4.5) bad(t.id, `${fg} ${vars[fg]} / ${bg} ${vars[bg]} 대비 ${r.toFixed(1)} (4.5 이상이어야 함)`)
  }
  if (fails === before) console.log('통과', t.id)
}
for (const f of fs.readdirSync(DIR)) {
  if (f.endsWith('.css') && !ids.has(f.slice(0, -4))) bad(f, 'list.json에 없는 테마 파일')
}
console.log(fails ? `실패 ${fails}건` : '모두 통과')
process.exit(fails ? 1 : 0)
