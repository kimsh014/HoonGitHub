/// <reference path="../pb_data/types.d.ts" />
// POS·키오스크 연동: 메뉴의 POS 상품 코드(items.pos_code)와 매장의 연동 키(stores.pos_key_hash).
// 연동 키는 원문을 저장하지 않고 sha256만 둔다. 숨김 칸이라 API 응답에 나오지 않는다. 키를 만들고 쓰는 곳은 pb_hooks/pos.pb.js
migrate((app) => {
  const items = app.findCollectionByNameOrId("items")
  items.fields.add(new TextField({ name: "pos_code", max: 50 }))
  // 한 매장 안에서 같은 POS 코드는 하나만. 비어 있는 메뉴는 여럿이어도 된다.
  items.indexes.push("CREATE UNIQUE INDEX idx_items_store_pos_code ON items (store, pos_code) WHERE pos_code != ''")
  app.save(items)

  const stores = app.findCollectionByNameOrId("stores")
  stores.fields.add(new TextField({ name: "pos_key_hash", hidden: true, max: 64 }))
  // 연동 키는 POST /api/menuboard/pos/key 로만 바꾼다. 매장 수정 요청으로 직접 넣지 못하게 막는다.
  stores.updateRule = stores.updateRule + " && @request.body.pos_key_hash:isset = false"
  app.save(stores)
}, (app) => {
  const items = app.findCollectionByNameOrId("items")
  items.indexes = items.indexes.filter((i) => i.indexOf("idx_items_store_pos_code") < 0)
  items.fields.removeByName("pos_code")
  app.save(items)

  const stores = app.findCollectionByNameOrId("stores")
  stores.fields.removeByName("pos_key_hash")
  stores.updateRule = stores.updateRule.replace(" && @request.body.pos_key_hash:isset = false", "")
  app.save(stores)
})
