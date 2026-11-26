/// <reference path="../pb_data/types.d.ts" />
// 사진 칸의 최대 크기를 25MB로 늘린다. 기본값(maxSize 0)은 5MB라 4K 사진(최대 20MB 정도)이 막힌다.
// 요청 본문 전체 한도는 PocketBase 기본 32MB라 사진 한 장씩 올리는 데는 따로 늘리지 않는다.
const fields = [["stores", "background"], ["items", "photo"], ["screens", "promo_image"]]

function setMaxSize(app, bytes) {
  for (const [name, field] of fields) {
    const collection = app.findCollectionByNameOrId(name)
    collection.fields.getByName(field).maxSize = bytes
    app.save(collection)
  }
}

migrate((app) => setMaxSize(app, 25 * 1024 * 1024), (app) => setMaxSize(app, 0))
