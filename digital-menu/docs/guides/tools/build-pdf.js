// 안내서 Markdown을 인쇄용 PDF(A4)로 만든다.
// 사용: (docs/guides/tools 에서) npm i marked@12 playwright 후  node build-pdf.js
//   → ../pdf/installer-guide.pdf, ../pdf/owner-guide.pdf
// 한글 글꼴이 있어야 한다(Windows는 맑은 고딕, 리눅스는 fonts-noto-cjk).
const fs = require('fs')
const path = require('path')
const { marked } = require('marked')
const { chromium } = require('playwright')

const ROOT = path.resolve(__dirname, '..')
const DOCS = [
  ['installer-guide.md', 'installer-guide.pdf', '설치 기사용 안내서'],
  ['owner-guide.md', 'owner-guide.pdf', '사장님용 사용 설명서'],
]

const CSS = `
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
body { font-family: 'Noto Sans KR','Noto Sans CJK KR','Malgun Gothic',sans-serif; font-size: 10.5pt; line-height: 1.6; color: #1f2328; }
h1 { font-size: 22pt; color: #c8102e; border-bottom: 3px solid #c8102e; padding-bottom: 4px; margin: 0 0 10px; }
h2 { font-size: 15pt; border-left: 6px solid #c8102e; padding-left: 8px; margin: 18px 0 8px; break-after: avoid; }
h2 { margin-top: 22px; }
h3 { font-size: 12pt; margin: 14px 0 6px; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
img { max-width: 100%; max-height: 120mm; display: block; margin: 6px auto; border: 1px solid #e5e7eb; border-radius: 4px; break-inside: avoid; }
table img { max-height: 60mm; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 1px solid #d0d7de; padding: 4px 6px; vertical-align: top; }
th { background: #f6f8fa; }
code { font-family: 'Noto Sans Mono CJK KR','D2Coding',Consolas,monospace; background: #f3f4f6; padding: 0 3px; border-radius: 3px; font-size: 9.5pt; }
pre { background: #f6f8fa; border: 1px solid #d0d7de; padding: 8px; border-radius: 4px; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { margin: 8px 0; padding: 6px 10px; background: #fffbe6; border-left: 4px solid #bf8700; }
blockquote p { margin: 2px 0; }
hr { display: none; }
a { color: #0969da; text-decoration: none; }
strong { color: #000; }
`

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  fs.mkdirSync(path.join(ROOT, 'pdf'), { recursive: true })
  for (const [src, out, title] of DOCS) {
    const md = fs.readFileSync(path.join(ROOT, src), 'utf8')
    const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>${title}</title>
      <style>${CSS}</style></head><body>${marked.parse(md)}</body></html>`
    // 이미지 상대 경로가 맞도록 안내서 폴더에 잠깐 써 두고 연다
    const tmp = path.join(ROOT, '.print-' + src + '.html')
    fs.writeFileSync(tmp, html)
    try {
      await page.goto('file://' + tmp, { waitUntil: 'load' })
      await page.evaluate(() => document.fonts.ready)
      await page.pdf({
        path: path.join(ROOT, 'pdf', out), format: 'A4', printBackground: true, displayHeaderFooter: true,
        headerTemplate: '<span></span>',
        footerTemplate: `<div style="width:100%;font-size:8pt;color:#6e7781;text-align:center;font-family:sans-serif">POSWING 번호 호출 메뉴판 · ${title} · <span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
        margin: { top: '16mm', bottom: '18mm', left: '14mm', right: '14mm' },
      })
    } finally {
      fs.rmSync(tmp, { force: true })
    }
    console.log('만듦:', path.join('pdf', out))
  }
  await browser.close()
}
main().catch((e) => { console.error(e); process.exit(1) })
