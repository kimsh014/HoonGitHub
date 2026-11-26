// pb_public/board.js의 갱신 흐름을 서버·브라우저 없이 검사한다. 사용: node check_board.js
// 확인하는 것: 매장 번호 없는 주소, zoom 배율, 처음 실패하면 15초 뒤 재시도, 받으면 그리고 MenuBoardHost.rendered(),
// 화면의 사진이 다 뜬 뒤(최대 10초)에 rendered(), 같은 데이터면 다시 안 그리기, 변경 알림이 몰려와도 0.3초 뒤 한 번만 다시 받기, 받는 중에 온 알림도 놓치지 않기,
// 끊기면 마지막 화면 유지.
const assert = require('assert')

let answer // 다음 getBoard가 돌려줄 것 (Error면 실패, 함수면 그 함수가 끝낼 때까지 대기)
let onChange // board.js가 api.onBoardChange에 넘긴 함수
const timers = new Map() // 걸려 있는 타이머 id → { fn, ms }
let nextTimer = 0
const rendered = []
const status = []
const zoom = []
let hostCalls = 0
const images = [] // board.js가 보는 document.images
const fakeImg = (complete = false) => ({
  complete, on: {},
  addEventListener(type, fn) { (this.on[type] ||= []).push(fn) },
  emit(type) { (this.on[type] || []).forEach((fn) => fn()) },
})

global.window = global
global.location = { search: '?screen=2&refresh=60&zoom=120' }
global.console = { ...console, error() {} }
global.document = {
  documentElement: { style: { setProperty: (k, v) => zoom.push([k, v]) } },
  createElement: () => ({ style: {}, set textContent(t) { status.push(t) }, remove() { status.push('(지움)') } }),
  body: { appendChild() {} },
  images,
}
global.setTimeout = (fn, ms) => { timers.set(++nextTimer, { fn, ms }); return nextTimer }
global.clearTimeout = (id) => { timers.delete(id) }
global.api = {
  getBoard(id) {
    assert.strictEqual(id, null) // 주소에 매장 번호가 없으면 api.getBoard가 찾는다
    if (typeof answer === 'function') return new Promise(answer)
    return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer)
  },
  onBoardChange(fn) { onChange = fn },
}
global.renderBoard = (board, screenNo) => rendered.push([board.v, screenNo])
global.MenuBoardHost = { rendered: () => hostCalls++ }

const settle = () => new Promise(setImmediate)
const waits = () => [...timers.values()].map((t) => t.ms)
async function fire(next, ms) { // 걸려 있는 타이머 하나(ms를 주면 그 시간의 것)를 지금 울린다
  if (!ms) assert.strictEqual(timers.size, 1, `타이머는 하나여야 함: ${waits()}`)
  const [id, t] = [...timers].find(([, x]) => !ms || x.ms === ms)
  timers.delete(id)
  answer = next
  t.fn()
  await settle()
}

async function main() {
  const notFound = Object.assign(new Error('아직 매장이 없습니다.'), { status: 404 })
  answer = notFound
  require('./pb_public/board.js')
  await settle()
  assert.deepStrictEqual(zoom, [['--zoom', 1.2]])
  assert.strictEqual(typeof onChange, 'function')
  assert.deepStrictEqual([rendered, waits(), status], [[], [15000], ['아직 매장이 없습니다.']])

  await fire(new Error('연결 안 됨'))
  assert.deepStrictEqual([waits(), status.at(-1)], [[15000], '서버에 연결하는 중입니다…'])

  await fire({ v: 1 })
  assert.deepStrictEqual([rendered, waits(), status.at(-1), hostCalls], [[[1, 2]], [60000], '(지움)', 1])

  await fire({ v: 1 }) // 같은 데이터: 다시 안 그리고 보드 앱에도 안 알린다
  assert.deepStrictEqual([rendered, hostCalls], [[[1, 2]], 1])

  onChange(); onChange(); onChange() // 저장 한 번에 알림 여러 개
  assert.deepStrictEqual(waits(), [300])
  await fire({ v: 2 })
  assert.deepStrictEqual([rendered, waits(), hostCalls], [[[1, 2], [2, 2]], [60000], 2])

  // 받는 중에 변경 알림이 오면, 끝난 뒤에도 0.3초 예약이 남아 새 데이터를 다시 받는다
  let finish
  await fire((resolve) => { finish = resolve })
  onChange()
  finish({ v: 2 })
  await settle()
  assert.deepStrictEqual(waits(), [300])
  await fire({ v: 3 })
  assert.deepStrictEqual([rendered.at(-1), hostCalls], [[3, 2], 3])

  await fire(new Error('연결 끊김')) // 마지막 화면 유지, 안내 글도 다시 안 띄움
  assert.deepStrictEqual([rendered.length, waits(), status.length], [3, [60000], 3])

  await fire({ v: 4 })
  assert.deepStrictEqual(rendered.at(-1), [4, 2])

  // 사진이 있으면 다 뜨거나 실패한 뒤에 rendered(). 이미 뜬 사진은 기다리지 않는다
  const before = hostCalls
  const photo1 = fakeImg(), photo2 = fakeImg()
  images.push(photo1, photo2, fakeImg(true))
  onChange()
  await fire({ v: 5 })
  assert.deepStrictEqual([rendered.at(-1), hostCalls, waits().sort()], [[5, 2], before, [10000, 60000]])
  photo1.emit('load')
  assert.strictEqual(hostCalls, before)
  photo2.emit('error')
  assert.deepStrictEqual([hostCalls, waits()], [before + 1, [60000]]) // 10초 제한 타이머도 풀림

  // 사진이 10초 넘게 안 뜨면 그냥 부른다. 늦게 떠도 두 번 부르지 않는다
  const slow = fakeImg()
  images.splice(0, images.length, slow)
  onChange()
  await fire({ v: 6 })
  assert.strictEqual(hostCalls, before + 1)
  await fire(undefined, 10000)
  slow.emit('load')
  assert.deepStrictEqual([rendered.at(-1), hostCalls], [[6, 2], before + 2])
  console.log('OK: 매장 번호 없는 주소, zoom, 변경 알림으로 바로 다시 받기, 사진이 뜬 뒤(최대 10초) MenuBoardHost.rendered, 끊겼을 때 마지막 화면 유지가 맞습니다.')
}

main().catch((e) => { console.error(e); process.exit(1) })
