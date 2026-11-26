/// <reference path="../pb_data/types.d.ts" />
// 매장 위험 점검표의 서버 쪽 1차 대응. 함수는 safety_lib.js.
// - 자동 백업: 30분마다 확인해 하루 한 번, 7개 보관 (B-3)
// - 부른 번호: 10분 지나면 빼고, 서버가 켜질 때도 지난 번호를 비움 (B-4)
// - 메뉴가 있는 구역은 지우지 못하게 (M-4, 구역을 지우면 메뉴까지 지워지는 사고 막기)
// - POS기 앞(127.0.0.1)에서만 되는 비밀번호 다시 정하기 (M-10), 화면은 pb_public/reset.html

cronAdd("menuboard_backup", "*/30 * * * *", () => {
  const lib = require(`${__hooks}/safety_lib.js`)
  try {
    const name = lib.backupIfDue($app, false)
    if (name) $app.logger().info("메뉴판 자동 백업", "name", name)
  } catch (err) {
    $app.logger().error("메뉴판 자동 백업 실패", "error", String(err))
  }
})

cronAdd("menuboard_old_calls", "* * * * *", () => {
  const lib = require(`${__hooks}/safety_lib.js`)
  lib.clearOldCalls($app)
})

// 서버가 켜질 때: 꺼져 있던 동안 지난 번호를 비운다(어제 번호가 아침에 뜨지 않게).
onBootstrap((e) => {
  e.next()
  const lib = require(`${__hooks}/safety_lib.js`)
  try { lib.clearOldCalls(e.app) } catch (err) { /* 첫 설치 직후 마이그레이션 전이면 calls가 아직 없을 수 있다 */ }
})

// 메뉴가 있는 구역은 지우지 못하게 한다. 관리자(superuser)는 그대로 지울 수 있다.
onRecordDeleteRequest((e) => {
  if (!e.hasSuperuserAuth()) {
    const count = e.app.countRecords("items", $dbx.hashExp({ section: e.record.id }))
    if (count > 0) {
      throw new BadRequestError("이 구역에 메뉴 " + count + "개가 있습니다. 메뉴를 다른 구역으로 옮기거나 지운 뒤 구역을 지워 주세요.")
    }
  }
  e.next()
}, "sections")

// 지금 백업을 하나 만든다(관리자만). A/S 기사가 POS기를 바꾸거나 업데이트하기 전에 쓴다.
routerAdd("POST", "/api/menuboard/backup", (e) => {
  const lib = require(`${__hooks}/safety_lib.js`)
  return e.json(200, { name: lib.backupIfDue(e.app, true) })
}, $apis.requireSuperuserAuth())

// 비밀번호 다시 정하기 화면이 계정 목록을 읽는다. POS기 앞에서만.
routerAdd("GET", "/api/menuboard/local-reset", (e) => {
  const lib = require(`${__hooks}/safety_lib.js`)
  lib.requireLocal(e)
  const users = e.app.findRecordsByFilter("users", "", "created", 50, 0)
  return e.json(200, { accounts: users.map((u) => ({ email: u.email() })) })
})

// 본문: { "email": "...", "password": "새 비밀번호" }. 바꾸면 그 계정으로 로그인해 있던 다른 기기는 모두 로그아웃된다.
routerAdd("POST", "/api/menuboard/local-reset", (e) => {
  const lib = require(`${__hooks}/safety_lib.js`)
  lib.requireLocal(e)
  const body = e.requestInfo().body || {}
  const password = typeof body.password === "string" ? body.password : ""
  if (password.length < 8) throw new BadRequestError("새 비밀번호는 8자 이상이어야 합니다.")
  let user
  try {
    user = e.app.findAuthRecordByEmail("users", String(body.email || ""))
  } catch (err) {
    throw new NotFoundError("그 이메일의 계정이 없습니다.")
  }
  user.setPassword(password) // 토큰 키도 바뀌어 예전 로그인은 모두 끊긴다
  e.app.save(user)
  e.app.logger().warn("POS기에서 비밀번호를 다시 정함", "email", user.email())
  return e.json(200, { email: user.email() })
})
