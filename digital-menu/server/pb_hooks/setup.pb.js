/// <reference path="../pb_data/types.d.ts" />
// 개인 매장 첫 설치: 계정이 하나도 없을 때만 매장과 첫 계정을 만든다. api.js의 signUp이 부른다.
// "아직 아무도 없을 때만"은 접근 규칙으로 표현할 수 없어서 이 경로만 서버 코드로 둔다.
// ponytail: 인터넷에 여는 서버(프랜차이즈)는 열기 전에 본사 계정을 먼저 만들어 이 경로를 닫아 둘 것.
routerAdd("POST", "/api/menuboard/setup", (e) => {
  const body = e.requestInfo().body
  if ($app.countRecords("users") > 0) {
    throw new ForbiddenError("이미 설치가 끝났습니다.")
  }
  $app.runInTransaction((txApp) => {
    // 동시에 두 요청이 들어와도 한 계정만 만들어지게 트랜잭션 안에서 다시 센다
    if (txApp.countRecords("users") > 0) {
      throw new ForbiddenError("이미 설치가 끝났습니다.")
    }
    const store = new Record(txApp.findCollectionByNameOrId("stores"))
    store.set("kind", "independent")
    store.set("name", body.storeName)
    txApp.save(store)

    const user = new Record(txApp.findCollectionByNameOrId("users"))
    user.set("email", body.email)
    user.set("password", body.password)
    user.set("store", store.id)
    txApp.save(user)
  })
  return e.json(200, { ok: true })
})

// 화면 파일(pb_public)은 매번 바뀌었는지 서버에 묻게 한다. 안 그러면 화면 파일을 바꿔도 보드 WebView가 한동안 옛 화면을 띄운다.
routerUse((e) => {
  if (!e.request.url.path.startsWith("/api/")) e.response.header().set("Cache-Control", "no-cache")
  return e.next()
})

// 보드 주소에는 매장 번호가 없다. 이 서버에 가맹점이 아닌 매장이 하나뿐이면 그 매장 번호를 알려 준다.
// ponytail: 한 서버에 매장이 여럿이면(프랜차이즈 서버) 보드 주소에 ?store=매장번호 를 붙여야 한다.
routerAdd("GET", "/api/menuboard/store", (e) => {
  const stores = e.app.findRecordsByFilter("stores", "kind != 'franchise'", "", 2, 0)
  if (stores.length !== 1) {
    throw new NotFoundError(stores.length
      ? "이 서버에 매장이 여러 개입니다. 보드 주소에 ?store=매장번호 를 붙여 주세요."
      : "아직 매장이 없습니다. 수정 화면에서 첫 설치를 해 주세요.")
  }
  return e.json(200, { id: stores[0].id })
})
