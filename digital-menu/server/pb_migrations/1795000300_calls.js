/// <reference path="../pb_data/types.d.ts" />
// 번호 호출: 매장이 부른 번호(calls), 번호 전용 화면(screens.type "calls"), 메뉴 화면 아래 번호 띠(screens.call_band).
// 가맹점도 자기 매장 번호를 부르므로 stores 칸이 아니라 따로 둔다(가맹점 계정은 stores를 고치지 못한다).
migrate((app) => {
  const stores = app.findCollectionByNameOrId("stores")
  const own = '@request.auth.store = store'
  app.save(new Collection({
    type: "base", name: "calls",
    listRule: "", viewRule: "", createRule: own, updateRule: null, deleteRule: own,
    fields: [
      { name: "store", type: "relation", collectionId: stores.id, maxSelect: 1, required: true, cascadeDelete: true },
      { name: "number", type: "number", required: true, min: 1, max: 9999, onlyInt: true },
      { name: "created", type: "autodate", onCreate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_calls_store_number ON calls (store, number)"],
  }))

  const screens = app.findCollectionByNameOrId("screens")
  screens.fields.getByName("type").values = ["grid", "list", "promo", "calls"]
  screens.fields.add(new BoolField({ name: "call_band" }))
  app.save(screens)
}, (app) => {
  app.delete(app.findCollectionByNameOrId("calls"))
  const screens = app.findCollectionByNameOrId("screens")
  screens.fields.removeByName("call_band")
  screens.fields.getByName("type").values = ["grid", "list", "promo"]
  app.save(screens)
})
