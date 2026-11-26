/// <reference path="../pb_data/types.d.ts" />
// TV(보드) 원격 관리. 천장에 붙은 TV를 사다리 없이 POS기의 관리 화면(devices.html)에서 손보기 위한 것.
// TV 쪽: 등록 → 15초마다 보고(지금 설정을 알리고 할 일을 받음) → 캡처 요청이 있으면 JPEG를 올림.
// 관리 화면 쪽: 설정 바꾸기, 재시작, 캡처 요청, A/S 연결(네트워크 ADB) 열기·닫기. 목록·삭제는 PocketBase 기본 API.
// 사용법은 ../README.md의 "TV 원격 관리".

// ── TV가 부르는 곳 ──

// 처음 한 번: 기기 토큰을 받는다. 토큰 원문은 이 응답에서만 나간다.
// 본문: { "name": "카운터 위", "model": "...", "version": "1.2", "store": "매장번호(서버에 매장이 여럿일 때만)" }
// ponytail: 같은 망에 있으면 누구나 등록할 수 있다(매장당 50대까지). 등록만으로는 메뉴를 바꿀 수 없고, 모르는 TV는 관리 화면에서 지운다.
routerAdd("POST", "/api/menuboard/devices/register", (e) => {
  const lib = require(`${__hooks}/devices_lib.js`)
  const body = e.requestInfo().body || {}
  const store = lib.storeForRegister(e.app, body.store)
  const count = e.app.countRecords("devices", $dbx.hashExp({ store: store.id }))
  if (count >= lib.MAX_DEVICES) throw new BadRequestError("이 매장에 등록된 TV가 너무 많습니다. 관리 화면에서 안 쓰는 TV를 지워 주세요.")
  const token = "mbdev_" + $security.randomString(40)
  const device = new Record(e.app.findCollectionByNameOrId("devices"))
  device.set("store", store.id)
  device.set("name", lib.str(body.name, 50) || "TV " + (count + 1))
  device.set("model", lib.str(body.model, 100))
  device.set("version", lib.str(body.version, 30))
  device.set("token_hash", $security.sha256(token))
  device.set("ip", e.realIP())
  device.set("last_seen", lib.now())
  e.app.save(device)
  return e.json(200, { id: device.id, token: token, store: store.id })
})

// 15초마다: 지금 설정을 알리고, 바뀐 설정·재시작·캡처·ADB 지시를 받는다.
// 본문: { "version": "1.2", "model": "...", "reported": { server, screen, zoom, rotation, brightness, adb, canAdb, rev, usb, width, height } }
routerAdd("POST", "/api/menuboard/devices/report", (e) => {
  const lib = require(`${__hooks}/devices_lib.js`)
  const device = lib.deviceByToken(e.app, e.request)
  const body = e.requestInfo().body || {}
  device.set("version", lib.str(body.version, 30))
  device.set("model", lib.str(body.model, 100))
  device.set("reported", lib.cleanReported(body.reported))
  device.set("ip", e.realIP())
  device.set("last_seen", lib.now())
  e.app.save(device)
  return e.json(200, lib.orders(device))
})

// 캡처 요청을 받은 TV가 지금 화면을 JPEG 본문 그대로 올린다.
routerAdd("POST", "/api/menuboard/devices/shot", (e) => {
  const lib = require(`${__hooks}/devices_lib.js`)
  const device = lib.deviceByToken(e.app, e.request)
  const bytes = toBytes(e.request.body, lib.MAX_SHOT + 1)
  if (bytes.length > lib.MAX_SHOT) throw new BadRequestError("사진이 너무 큽니다.")
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) throw new BadRequestError("JPEG만 받습니다.")
  device.set("shot", $filesystem.fileFromBytes(bytes, "shot.jpg"))
  device.set("shot_at", lib.now())
  e.app.save(device)
  return e.json(200, { ok: true })
})

// ── 관리 화면이 부르는 곳 (매장 계정 로그인, 자기 매장 TV만) ──

// 설정 바꾸기. 본문에 바꿀 칸만: { name, screen, zoom, rotation, brightness, server }
// TV는 다음 보고 때 받아 적용한다. 서버 주소는 TV가 새 주소에 실제로 붙어 본 뒤에만 바꾼다.
routerAdd("POST", "/api/menuboard/devices/{id}/config", (e) => {
  const lib = require(`${__hooks}/devices_lib.js`)
  const device = lib.ownDevice(e.app, e)
  const body = e.requestInfo().body || {}
  if (body.name !== undefined) {
    const name = lib.str(body.name, 50).trim()
    if (!name) throw new BadRequestError("TV 이름을 적어 주세요.")
    device.set("name", name)
  }
  const desired = lib.cleanDesired(body, JSON.parse(device.getString("desired") || "null"))
  device.set("desired", desired)
  device.set("rev", device.getInt("rev") + 1)
  e.app.save(device)
  return e.json(200, { rev: device.getInt("rev"), desired: desired })
}, $apis.requireAuth("users"))

// 메뉴판 앱 다시 켜기
routerAdd("POST", "/api/menuboard/devices/{id}/restart", (e) => {
  const lib = require(`${__hooks}/devices_lib.js`)
  const device = lib.ownDevice(e.app, e)
  device.set("restart_rev", device.getInt("restart_rev") + 1)
  e.app.save(device)
  return e.json(200, { restartRev: device.getInt("restart_rev") })
}, $apis.requireAuth("users"))

// 지금 TV 화면 캡처 요청. 15초 안팎 뒤 devices.shot 에 사진이 올라온다(shot_at 이 바뀜).
routerAdd("POST", "/api/menuboard/devices/{id}/shot", (e) => {
  const lib = require(`${__hooks}/devices_lib.js`)
  const device = lib.ownDevice(e.app, e)
  device.set("shot_rev", device.getInt("shot_rev") + 1)
  e.app.save(device)
  return e.json(200, { shotRev: device.getInt("shot_rev"), shotAt: device.getInt("shot_at") })
}, $apis.requireAuth("users"))

// A/S 연결(네트워크 ADB) 열기·닫기. 본문: { "minutes": 60 } (0이면 바로 잠금). 시간이 지나면 TV가 스스로 잠근다.
routerAdd("POST", "/api/menuboard/devices/{id}/adb", (e) => {
  const lib = require(`${__hooks}/devices_lib.js`)
  const device = lib.ownDevice(e.app, e)
  const minutes = (e.requestInfo().body || {}).minutes
  if (typeof minutes !== "number" || minutes % 1 !== 0 || minutes < 0 || minutes > lib.MAX_ADB_MINUTES) {
    throw new BadRequestError("A/S 연결은 0~" + lib.MAX_ADB_MINUTES + "분까지 열 수 있습니다.")
  }
  device.set("adb_until", minutes ? lib.now() + minutes * 60 : 0)
  e.app.save(device)
  return e.json(200, { adbSeconds: lib.orders(device).adbSeconds })
}, $apis.requireAuth("users"))
