/// <reference path="../pb_data/types.d.ts" />
// POS·키오스크 연동. POS가 품절·가격을 보내면 sold_out·items가 바뀌고, 보드 화면은 이미 하고 있는
// 실시간 구독(api.js의 onBoardChange)으로 새로고침 없이 바로 다시 그린다.
// 사용법은 ../README.md의 "POS·키오스크 연동".

// 연동 키 만들기. 로그인한 매장 계정만 부를 수 있고, 새로 만들면 예전 키는 바로 못 쓰게 된다.
// 키 원문은 이 응답에서 한 번만 보여 준다.
routerAdd("POST", "/api/menuboard/pos/key", (e) => {
  const storeId = e.auth && e.auth.getString("store")
  if (!storeId) throw new ForbiddenError("매장 계정으로 로그인해 주세요.")
  const key = "mbpos_" + $security.randomString(40)
  const store = e.app.findRecordById("stores", storeId)
  store.set("pos_key_hash", $security.sha256(key))
  e.app.save(store)
  return e.json(200, { key: key })
}, $apis.requireAuth("users"))

// 이 매장의 메뉴 목록 (POS 상품과 짝을 맞출 때 본다)
routerAdd("GET", "/api/menuboard/pos/items", (e) => {
  const pos = require(`${__hooks}/pos_lib.js`)
  const store = pos.storeByKey(e.app, e.request)
  return e.json(200, { store: { id: store.id, name: store.getString("name") }, items: pos.listItems(e.app, store) })
})

// 품절·가격 바꾸기. 본문: { "items": [ { "posCode": "A01", "soldOut": true }, { "name": "라떼", "price": 5000 } ] }
routerAdd("POST", "/api/menuboard/pos/items", (e) => {
  const pos = require(`${__hooks}/pos_lib.js`)
  const store = pos.storeByKey(e.app, e.request)
  const body = e.requestInfo().body
  return e.json(200, { items: pos.applyUpdates(e.app, store, body.items) })
})
