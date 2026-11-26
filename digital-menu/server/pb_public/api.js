// 화면이 서버를 부르는 유일한 곳. 계약(설계도 문서의 "역할 분담과 계약")에 적힌 함수만 내보낸다.
// 사용: <script src="api.js"></script> 뒤에 api.getBoard(storeId).then(function (board) { ... })
// 안드로이드 7의 오래된 브라우저에서도 돌도록 async/await, 전개 연산자, 화살표 함수, 모듈을 쓰지 않는다.
(function () {
  var BASE = window.MENU_API_BASE || '' // 화면을 서버와 다른 주소에서 띄워 시험할 때만 지정한다
  var AUTH_KEY = 'menuboard_auth'

  function loadAuth() {
    try { return JSON.parse(localStorage.getItem(AUTH_KEY)) } catch (e) { return null }
  }

  // body가 FormData면 파일과 함께 multipart로, 아니면 JSON으로 보낸다. guest면 로그인 정보를 싣지 않는다.
  function request(method, path, body, guest) {
    var headers = {}
    var auth = guest ? null : loadAuth()
    var isForm = typeof FormData !== 'undefined' && body instanceof FormData
    if (auth) headers.Authorization = auth.token
    if (body && !isForm) headers['Content-Type'] = 'application/json'
    return fetch(BASE + path, { method: method, headers: headers, body: body ? (isForm ? body : JSON.stringify(body)) : undefined })
      .then(function (res) {
        return res.text().then(function (text) {
          var data = text ? JSON.parse(text) : {}
          if (!res.ok) {
            // 입력 검사 실패면 어느 칸이 왜 틀렸는지 덧붙인다. 예: (password: Must be at least 8 character(s).)
            var fields = data.data ? Object.keys(data.data) : []
            var detail = fields.map(function (k) { return k + ': ' + (data.data[k].message || data.data[k]) }).join(', ')
            var err = new Error((data.message || 'HTTP ' + res.status) + (detail ? ' (' + detail + ')' : ''))
            err.status = res.status
            throw err
          }
          return data
        })
      })
  }

  function records(collection) { return '/api/collections/' + collection + '/records' }

  function list(collection, filter, sort) {
    // ponytail: 한 번에 500줄까지만 읽는다. 한 매장의 메뉴가 500개를 넘으면 페이지를 나눠 읽게 고칠 것.
    return request('GET', records(collection) + '?perPage=500&skipTotal=1' +
      '&filter=' + encodeURIComponent(filter) + (sort ? '&sort=' + sort : ''))
      .then(function (res) { return res.items })
  }

  // 추가(id 없음) 또는 수정(id 있음). 수정할 때는 store를 보내지 않는다(접근 규칙이 막는다).
  function save(collection, id, storeId, fields) {
    if (!id) fields.store = storeId
    var form = new FormData()
    for (var k in fields) {
      var v = fields[k]
      if (v === undefined) continue // 넘기지 않은 칸은 그대로 둔다
      if (v === null) v = '' // 파일·선택 칸을 비운다
      else if (typeof v === 'object' && !(v instanceof Blob)) v = JSON.stringify(v) // prices, sections 같은 칸
      form.append(k, v)
    }
    return id ? request('PATCH', records(collection) + '/' + id, form) : request('POST', records(collection), form)
  }

  function remove(collection, id) {
    return request('DELETE', records(collection) + '/' + encodeURIComponent(id)).then(function () {})
  }

  // 새 파일이 있으면 그 파일, 주소(…Url)가 null이면 지우기, 둘 다 없으면 손대지 않기(undefined)
  function fileField(file, url) {
    return file || (url === null ? null : undefined)
  }

  function fileUrl(record, name) {
    return name ? BASE + '/api/files/' + record.collectionId + '/' + record.id + '/' + name : null
  }

  function getStore(id) {
    return request('GET', records('stores') + '/' + encodeURIComponent(id))
  }

  // ── 바로 반영 (실시간) ──
  var live = null // { es, clientId, callback, heard: 이미 귀 기울이는 주제 }
  var watchedStores = [] // getBoard가 마지막으로 읽은 매장(가맹점이면 본사도)

  // 매장(stores)은 목록 규칙이 로그인을 요구해서 로그인 없이는 "stores/*"를 구독할 수 없다.
  // 그래서 getBoard가 읽은 매장 번호마다 "stores/번호"(한 줄 규칙 = 누구나)를 구독한다.
  // ponytail: 메뉴 쪽은 서버의 모든 매장 변경을 받는다. 매장 하나인 POS 서버에선 문제없고,
  // 매장이 많은 서버로 가면 주제에 ?options={"query":{"filter":"store='…'"}} 를 붙여 거를 것.
  function subscribe() {
    if (!live || !live.clientId) return
    var topics = ['sections/*', 'items/*', 'screens/*', 'sold_out/*', 'calls/*'].concat(watchedStores.map(function (id) { return 'stores/' + id }))
    topics.forEach(function (t) {
      if (!live.heard[t]) { live.heard[t] = true; live.es.addEventListener(t, function () { live.callback() }) }
    })
    // 구독은 늘 로그인 없이 한다. 메뉴판 내용은 공개이고, 연결 도중 로그인이 바뀌면 서버가 403으로 막기 때문이다.
    request('POST', '/api/realtime', { clientId: live.clientId, subscriptions: topics }, true)
      .catch(function (err) { if (window.console) console.error(err) })
  }

  // stores·sections·items·screens·sold_out·calls 중 하나라도 바뀌면 callback()을 부른다. 로그인 없이 된다.
  // 끊겼다 다시 이어지면 다시 구독하고, 끊긴 사이의 변경을 놓쳤을 수 있으니 callback()도 한 번 부른다.
  function onBoardChange(callback) {
    var connectedOnce = false
    function connect() {
      var es = new EventSource(BASE + '/api/realtime')
      live = { es: es, clientId: null, callback: callback, heard: {} }
      es.addEventListener('PB_CONNECT', function (e) {
        live.clientId = JSON.parse(e.data).clientId
        subscribe()
        if (connectedOnce) callback()
        connectedOnce = true
      })
      // 브라우저는 끊기면 스스로 다시 잇는다. 서버가 이상한 응답을 주어 아주 닫힌 경우만 직접 다시 연다.
      es.onerror = function () {
        if (es.readyState === 2) setTimeout(connect, 5000)
      }
    }
    connect()
  }

  // 메뉴판 전체를 계약의 데이터 모양으로 돌려준다. 로그인 없이 부를 수 있다.
  // storeId가 비어 있으면 서버의 하나뿐인 매장을 쓴다(GET /api/menuboard/store).
  function getBoard(storeId) {
    var id = storeId ? Promise.resolve(storeId)
      : request('GET', '/api/menuboard/store').then(function (res) { return res.id })
    return id.then(getStore).then(function (store) {
      // 가맹점은 본사의 메뉴·화면 구성·브랜드를 받아 쓰고, 품절은 본사 것과 자기 것을 합친다
      return (store.parent ? getStore(store.parent) : Promise.resolve(store)).then(function (owner) {
        var ids = owner.id === store.id ? [store.id] : [store.id, owner.id]
        if (ids.join() !== watchedStores.join()) { watchedStores = ids; subscribe() }
        var ofOwner = "store='" + owner.id + "'"
        return Promise.all([
          list('sections', ofOwner, 'sort_order'),
          list('items', ofOwner, 'sort_order'),
          list('screens', ofOwner, 'no'),
          list('sold_out', ofOwner + "||store='" + store.id + "'"),
          list('calls', "store='" + store.id + "'", '-created'), // 호출 번호는 가맹점도 자기 것
        ]).then(function (r) {
          var sold = {}
          r[3].forEach(function (s) { sold[s.item] = true })
          return {
            store: { name: store.name, brandColor: owner.brand_color, backgroundUrl: fileUrl(owner, owner.background) },
            sections: r[0].map(function (s) { return { id: s.id, name: s.name, order: s.sort_order } }),
            items: r[1].map(function (m) {
              return {
                id: m.id, sectionId: m.section, name: m.name, prices: m.prices || [],
                photoUrl: fileUrl(m, m.photo), order: m.sort_order, soldOut: !!sold[m.id], badge: m.badge || null,
                posCode: m.pos_code || null,
              }
            }),
            screens: r[2].map(function (s) {
              if (s.type === 'calls') return { no: s.no, type: s.type }
              return s.type === 'promo'
                ? { no: s.no, type: s.type, imageUrl: fileUrl(s, s.promo_image), lines: s.promo_lines || [], callBand: s.call_band }
                : { no: s.no, type: s.type, sectionIds: s.sections, callBand: s.call_band }
            }),
            calls: r[4].map(function (c) { return c.number }), // 최근에 부른 번호부터, 최대 30개
          }
        })
      })
    })
  }

  // ── 로그인 ──
  // 로그인하고 { kind: 'hq' | 'franchise' | 'independent', storeId } 를 돌려준다.
  // 로그인 정보는 이 기기에 저장되어 다음 저장 함수들이 쓴다.
  function login(email, password) {
    localStorage.removeItem(AUTH_KEY)
    return request('POST', '/api/collections/users/auth-with-password', { identity: email, password: password })
      .then(function (res) {
        if (!res.record.store) throw new Error('매장이 연결되지 않은 계정입니다.')
        var token = res.token
        localStorage.setItem(AUTH_KEY, JSON.stringify({ token: token })) // 매장 종류를 읽는 동안만
        return getStore(res.record.store).then(function (store) {
          var me = { kind: store.kind, storeId: store.id }
          localStorage.setItem(AUTH_KEY, JSON.stringify({ token: token, kind: me.kind, storeId: me.storeId }))
          return me
        })
      })
  }

  // 개인 매장의 첫 계정과 매장을 만들고 바로 로그인한다. 계정이 하나라도 있으면 403.
  function signUp(email, password, storeName) {
    return request('POST', '/api/menuboard/setup', { email: email, password: password, storeName: storeName })
      .then(function () { return login(email, password) })
  }

  // 이 기기에 저장된 로그인 { kind, storeId } 또는 null.
  // ponytail: 토큰이 만료됐는지는 보지 않는다. 만료되면 저장 함수가 401로 실패하니 그때 다시 로그인한다.
  function session() {
    var auth = loadAuth()
    return Promise.resolve(auth && auth.storeId ? { kind: auth.kind, storeId: auth.storeId } : null)
  }

  function logout() {
    localStorage.removeItem(AUTH_KEY)
    return Promise.resolve()
  }

  // ── 저장 (인자는 getBoard가 돌려주는 모양 그대로) ──
  // 저장한 줄의 id를 돌려준다.
  function saveItem(storeId, item) {
    return save('items', item.id, storeId, {
      section: item.sectionId, name: item.name, prices: item.prices, sort_order: item.order,
      badge: item.badge === undefined ? undefined : item.badge || null,
      photo: fileField(item.photoFile, item.photoUrl),
      pos_code: item.posCode === undefined ? undefined : item.posCode || '', // POS 상품 코드. 넘기지 않으면 그대로 둔다
    }).then(function (r) { return r.id })
  }

  function deleteItem(storeId, itemId) { return remove('items', itemId) }

  function saveSection(storeId, section) {
    return save('sections', section.id, storeId, { name: section.name, sort_order: section.order })
      .then(function (r) { return r.id })
  }

  // 구역에 메뉴가 있으면 서버가 400으로 거절한다(메뉴까지 같이 지워지는 사고 막기)
  function deleteSection(storeId, sectionId) { return remove('sections', sectionId) }

  function setSoldOut(storeId, itemId, soldOut) {
    return list('sold_out', "store='" + storeId + "'&&item='" + itemId + "'").then(function (rows) {
      if (soldOut && !rows.length) return save('sold_out', null, storeId, { item: itemId }).then(function () {})
      if (!soldOut && rows.length) return remove('sold_out', rows[0].id)
    })
  }

  // 화면 구성 전체를 바꾼다. 화면 번호(no)로 맞춰 있던 것은 고치고, 없던 것은 더하고, 빠진 것은 지운다.
  function saveScreens(storeId, screens) {
    return list('screens', "store='" + storeId + "'").then(function (old) {
      var byNo = {}
      old.forEach(function (s) { byNo[s.no] = s })
      var keep = {}
      screens.forEach(function (s) { keep[s.no] = true })
      return Promise.all(old.filter(function (s) { return !keep[s.no] }).map(function (s) { return remove('screens', s.id) }))
        .then(function () {
          return Promise.all(screens.map(function (s) {
            var promo = s.type === 'promo'
            return save('screens', byNo[s.no] && byNo[s.no].id, storeId, {
              no: s.no, type: s.type, call_band: s.type !== 'calls' && !!s.callBand,
              sections: promo ? [] : s.sectionIds || [],
              promo_lines: promo ? (s.lines || []).slice(0, 2) : [],
              promo_image: promo ? fileField(s.imageFile, s.imageUrl) : null,
            })
          }))
        })
        .then(function () {})
    })
  }

  // 가게 이름, 브랜드 색, 배경 이미지(store.backgroundFile, 지우려면 backgroundUrl: null)
  function saveStore(storeId, store) {
    return save('stores', storeId, storeId, {
      name: store.name, brand_color: store.brandColor,
      background: fileField(store.backgroundFile, store.backgroundUrl),
    }).then(function () {})
  }

  // ── 번호 호출 (가맹점 계정도 자기 매장 번호를 부른다) ──
  // 번호(1~9999)를 부른다. 이미 부른 번호면 맨 앞(최근)으로 옮긴다.
  function callNumber(storeId, number) {
    return clearCalls(storeId, number).then(function () {
      return save('calls', null, storeId, { number: number })
    }).then(function () {})
  }

  // 부른 번호 하나를 지운다. number를 빼면 이 매장의 번호를 모두 지운다.
  function clearCalls(storeId, number) {
    var filter = "store='" + storeId + "'" + (number == null ? '' : '&&number=' + Number(number))
    return list('calls', filter).then(function (rows) {
      return Promise.all(rows.map(function (c) { return remove('calls', c.id) }))
    }).then(function () {})
  }

  // ── POS·키오스크 연동 ──
  // 이 매장의 연동 키를 새로 만들어 돌려준다(문자열). 예전 키는 바로 못 쓰게 된다. 키는 이때 한 번만 볼 수 있다.
  function issuePosKey(storeId) {
    return request('POST', '/api/menuboard/pos/key').then(function (res) { return res.key })
  }

  // ── TV 목록 ──
  // 이 매장에 붙은 TV [{ id, name, screen }]. screen은 TV가 알려 온 지금 화면 번호,
  // 아직 알려 오지 않았으면 관리 화면에서 정한 번호, 둘 다 없으면 null. 로그인한 매장 계정만 읽을 수 있다.
  function listDevices(storeId) {
    return list('devices', "store='" + storeId + "'", 'name').then(function (rows) {
      return rows.map(function (d) {
        var screen = (d.reported && d.reported.screen) || (d.desired && d.desired.screen) || null
        return { id: d.id, name: d.name || '', screen: screen }
      })
    })
  }

  window.api = {
    getBoard: getBoard, onBoardChange: onBoardChange,
    signUp: signUp, login: login, session: session, logout: logout,
    saveItem: saveItem, deleteItem: deleteItem, saveSection: saveSection, deleteSection: deleteSection,
    setSoldOut: setSoldOut, saveScreens: saveScreens, saveStore: saveStore,
    callNumber: callNumber, clearCalls: clearCalls, issuePosKey: issuePosKey,
    listDevices: listDevices,
  }
})()
