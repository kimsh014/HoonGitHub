/// <reference path="../pb_data/types.d.ts" />
// 메뉴판 컬렉션: stores, sections, items, sold_out, screens + users.store
// 접근 규칙은 모두 기본값(null = 관리자만)으로 둔다. 규칙은 다음 마이그레이션에서 연다.
migrate((app) => {
  const img = ["image/jpeg", "image/png", "image/webp"]
  // 다른 컬렉션의 한 줄을 가리키는 필수 칸. 가리키는 줄이 지워지면 같이 지워진다.
  const owner = (name, collection) => ({
    name: name, type: "relation", collectionId: collection.id,
    maxSelect: 1, required: true, cascadeDelete: true,
  })

  const stores = new Collection({
    type: "base", name: "stores",
    fields: [
      { name: "kind", type: "select", required: true, maxSelect: 1, values: ["hq", "franchise", "independent"] },
      { name: "name", type: "text", required: true, max: 100 },
      { name: "brand_color", type: "text", max: 20 },
      { name: "background", type: "file", maxSelect: 1, mimeTypes: img },
      { name: "tv_count", type: "number", min: 0, onlyInt: true },
    ],
  })
  app.save(stores)
  // 가맹점 → 본사. 자기 자신을 가리키는 관계라 컬렉션을 먼저 저장한 뒤에 추가한다.
  stores.fields.add(new RelationField({ name: "parent", collectionId: stores.id, maxSelect: 1 }))
  app.save(stores)

  const users = app.findCollectionByNameOrId("users")
  users.fields.add(new RelationField({ name: "store", collectionId: stores.id, maxSelect: 1 }))
  app.save(users)

  const sections = new Collection({
    type: "base", name: "sections",
    fields: [
      owner("store", stores),
      { name: "name", type: "text", required: true, max: 100 },
      { name: "sort_order", type: "number", onlyInt: true },
    ],
  })
  app.save(sections)

  const items = new Collection({
    type: "base", name: "items",
    fields: [
      owner("store", stores),
      owner("section", sections),
      { name: "name", type: "text", required: true, max: 100 },
      { name: "prices", type: "json" }, // [{label, amount}] 한 개 또는 두 개
      { name: "photo", type: "file", maxSelect: 1, mimeTypes: img },
      { name: "sort_order", type: "number", onlyInt: true },
      { name: "badge", type: "select", maxSelect: 1, values: ["new", "best"] },
    ],
  })
  app.save(items)

  app.save(new Collection({
    type: "base", name: "sold_out", // 줄이 있으면 품절
    fields: [owner("store", stores), owner("item", items)],
    indexes: ["CREATE UNIQUE INDEX idx_sold_out_store_item ON sold_out (store, item)"],
  }))

  app.save(new Collection({
    type: "base", name: "screens",
    fields: [
      owner("store", stores),
      { name: "no", type: "number", required: true, min: 1, onlyInt: true },
      { name: "type", type: "select", required: true, maxSelect: 1, values: ["grid", "list", "promo"] },
      { name: "sections", type: "relation", collectionId: sections.id, maxSelect: 20 },
      { name: "promo_image", type: "file", maxSelect: 1, mimeTypes: img },
      { name: "promo_lines", type: "json" }, // 문구 최대 두 줄
    ],
    indexes: ["CREATE UNIQUE INDEX idx_screens_store_no ON screens (store, no)"],
  }))
}, (app) => {
  for (const name of ["screens", "sold_out", "items", "sections"]) {
    app.delete(app.findCollectionByNameOrId(name))
  }
  const users = app.findCollectionByNameOrId("users")
  users.fields.removeByName("store")
  app.save(users)
  app.delete(app.findCollectionByNameOrId("stores"))
})
