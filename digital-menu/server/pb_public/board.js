// 메뉴판 화면을 서버에 잇는다. 주소의 화면 번호를 읽고, 서버에서 변경 알림이 오면 바로(0.3초 모아서),
// 알림이 없어도 주기적으로 다시 받아 renderBoard(board, screenNo)를 부른다. renderBoard는 index.html(UI 담당)이 정의한다.
// 주소: /?screen=화면번호   (선택: &zoom=글자배율%, 기본 100 / &refresh=초, 기본 300 / &store=매장번호, 서버에 매장이 여럿일 때만)
(function () {
  var params = new URLSearchParams(location.search)
  var storeId = params.get('store') // 없으면 api.getBoard가 서버의 하나뿐인 매장을 찾는다
  var screenNo = Number(params.get('screen')) || 1
  var zoom = Number(params.get('zoom'))
  var refreshMs = (Number(params.get('refresh')) || 300) * 1000 // 실시간 알림을 놓쳤을 때의 안전망
  var RETRY_MS = 15000 // 아직 한 번도 못 받았으면 5분을 기다리지 않고 다시 시도한다
  var CHANGE_DELAY_MS = 300 // 저장 한 번에 알림이 여러 개 오므로 잠깐 모았다가 한 번만 받는다
  var shown = null // 지금 화면에 떠 있는 데이터 (JSON 문자열)
  var status = null // 메뉴를 한 번도 못 받았을 때만 띄우는 안내 글
  var timer = null // 다음 다시 받기 예약
  var latest = 0 // 가장 최근에 보낸 요청 번호. 늦게 도착한 옛 응답은 버린다
  var lastBoard = null // 마지막으로 받은 메뉴판 데이터
  var failingSince = 0 // 서버에 연결이 안 되기 시작한 시각(0 = 잘 붙어 있음)
  var STALE_CALLS_MS = 60000 // 서버와 이만큼 끊기면 떠 있는 호출 번호를 숨긴다(점검표 B-4: 지난 번호를 보고 손님이 받으러 옴)

  // 화면 크기(35~66인치)마다 설치자가 조절하는 글자 배율. index.html이 글자 크기에 var(--zoom, 1)을 곱한다
  if (zoom > 0) document.documentElement.style.setProperty('--zoom', zoom / 100)

  function say(text) {
    if (!status) {
      status = document.createElement('div')
      status.style.cssText = 'position:fixed;left:0;right:0;bottom:0;padding:1em;text-align:center;font-size:2vw;color:#fff;background:#000'
      document.body.appendChild(status)
    }
    status.textContent = text
  }

  // 화면의 img가 모두 뜨거나 실패한 뒤 done()을 부른다. 사진이 없으면 바로, 오래 걸려도 10초 뒤에는 부른다.
  // ponytail: CSS 배경 이미지(background-image)는 기다리지 않는다. 배경이 늦게 떠 저장 화면에서 빠지면
  // index.html이 배경도 img로 그리게 하거나 여기서 new Image()로 배경 주소를 미리 받아 기다릴 것.
  function afterImages(done) {
    var waiting = [].filter.call(document.images, function (img) { return !img.complete })
    var left = waiting.length
    if (!left) return done()
    var limit = setTimeout(finish, 10000)
    function finish() { clearTimeout(limit); left = -1; done() }
    function one() { if (--left === 0) finish() }
    waiting.forEach(function (img) { img.addEventListener('load', one); img.addEventListener('error', one) })
  }

  function schedule(ms) {
    clearTimeout(timer)
    timer = setTimeout(refresh, ms)
  }

  function refresh() {
    clearTimeout(timer)
    timer = null
    var mine = ++latest
    api.getBoard(storeId).then(function (board) {
      if (mine !== latest) return
      failingSince = 0
      lastBoard = board
      var json = JSON.stringify(board)
      if (json === shown) return // 바뀐 것이 없으면 다시 그리지 않는다 (깜빡임 방지)
      renderBoard(board, screenNo)
      shown = json
      if (status) { status.remove(); status = null }
      if (window.MenuBoardHost) afterImages(function () { window.MenuBoardHost.rendered() }) // 보드 앱이 이때 마지막 화면을 저장한다
    }).catch(function (err) {
      // 서버가 꺼졌거나 연결이 끊기면 떠 있는 마지막 메뉴를 그대로 둔다.
      if (window.console) console.error(err)
      if (!shown) {
        say(err.status === 404 ? (storeId ? '매장 번호가 올바르지 않습니다: ' + storeId : err.message) : '서버에 연결하는 중입니다…')
        return
      }
      if (!failingSince) failingSince = Date.now()
      // 메뉴는 그대로 두되, 오래 끊기면 호출 번호는 지운다. 다시 붙으면 데이터가 달라 새로 그린다.
      if (Date.now() - failingSince >= STALE_CALLS_MS && lastBoard && lastBoard.calls && lastBoard.calls.length) {
        var noCalls = JSON.parse(JSON.stringify(lastBoard))
        noCalls.calls = []
        renderBoard(noCalls, screenNo)
        lastBoard = noCalls
        shown = JSON.stringify(noCalls)
      }
    }).then(function () {
      // 그사이 변경 알림으로 예약된 것이 있으면 그것을 둔다. 끊긴 동안에는 자주 다시 시도한다.
      if (!timer) schedule(shown && !failingSince ? refreshMs : RETRY_MS)
    })
  }

  api.onBoardChange(function () { schedule(CHANGE_DELAY_MS) })
  refresh()
})()
