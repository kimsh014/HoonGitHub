/// <reference path="../pb_data/types.d.ts" />
// 로그인 횟수 제한(B-6). 관리자 화면(/_/)과 수정 화면이 매장 와이파이에 열려 있어, 비밀번호를 마구 넣어 보는 것을 늦춘다.
// 같은 주소에서 로그인(관리자 포함)은 1분에 20번, 비밀번호 다시 정하기는 1분에 5번까지.
// 메뉴 저장·번호 호출·TV 화면 읽기는 제한하지 않는다(키오스크가 번호를 몰아 부르거나 TV 여러 대가 사진을 받을 때 막히지 않게).
migrate((app) => {
  const settings = app.settings()
  settings.rateLimits.enabled = true
  settings.rateLimits.rules = [
    { label: "*:auth", maxRequests: 20, duration: 60, audience: "" },
    { label: "/api/menuboard/local-reset", maxRequests: 5, duration: 60, audience: "" },
  ]
  app.save(settings)
}, (app) => {
  const settings = app.settings()
  settings.rateLimits.enabled = false
  app.save(settings)
})
