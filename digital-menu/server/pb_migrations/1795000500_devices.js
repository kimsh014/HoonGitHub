/// <reference path="../pb_data/types.d.ts" />
// TV(보드) 원격 관리: 매장 서버에 붙은 TV 목록, TV가 알려 온 지금 설정(reported), 관리 화면에서 바꾼 설정(desired),
// 재시작·화면 캡처 요청 번호, A/S용 네트워크 ADB를 열어 둘 시각, 마지막 캡처 사진.
// TV는 기기 토큰(원문은 TV에만, 서버에는 sha256)으로 pb_hooks/devices.pb.js 의 라우트만 부른다.
// 매장 계정은 자기 매장 TV를 읽고 지울 수만 있고, 바꾸는 것은 모두 같은 파일의 라우트로 한다.
migrate((app) => {
  const stores = app.findCollectionByNameOrId("stores")
  const own = "@request.auth.store = store"
  app.save(new Collection({
    type: "base", name: "devices",
    listRule: own, viewRule: own, createRule: null, updateRule: null, deleteRule: own,
    fields: [
      { name: "store", type: "relation", collectionId: stores.id, maxSelect: 1, required: true, cascadeDelete: true },
      { name: "name", type: "text", max: 50 },
      { name: "token_hash", type: "text", hidden: true, max: 64 },
      { name: "model", type: "text", max: 100 },
      { name: "version", type: "text", max: 30 },
      { name: "ip", type: "text", max: 45 },
      { name: "reported", type: "json", maxSize: 4000 },
      { name: "desired", type: "json", maxSize: 4000 },
      { name: "rev", type: "number", onlyInt: true, min: 0 },         // desired 를 바꿀 때마다 1씩
      { name: "restart_rev", type: "number", onlyInt: true, min: 0 }, // 재시작 요청 때마다 1씩
      { name: "shot_rev", type: "number", onlyInt: true, min: 0 },    // 캡처 요청 때마다 1씩
      { name: "adb_until", type: "number", onlyInt: true, min: 0 },   // 이 시각(유닉스 초)까지 A/S 연결을 연다. 0 = 잠금
      { name: "last_seen", type: "number", onlyInt: true, min: 0 },   // 마지막 보고 시각(유닉스 초)
      { name: "shot", type: "file", maxSelect: 1, maxSize: 3 * 1024 * 1024, mimeTypes: ["image/jpeg"] },
      { name: "shot_at", type: "number", onlyInt: true, min: 0 },
      { name: "created", type: "autodate", onCreate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_devices_token ON devices (token_hash) WHERE token_hash != ''"],
  }))
}, (app) => {
  app.delete(app.findCollectionByNameOrId("devices"))
})
