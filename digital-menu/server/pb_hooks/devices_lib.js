// devices.pb.js 가 쓰는 함수들. 이름이 .pb.js로 끝나지 않아 훅으로 직접 실행되지는 않는다.

const MAX_DEVICES = 50 // 매장 하나에 붙일 수 있는 TV 수(아무나 등록해 목록을 채우지 못하게)
const MAX_SHOT = 3 * 1024 * 1024
const MAX_ADB_MINUTES = 240

function now() {
  return Math.floor(Date.now() / 1000)
}

// TV 요청 머리글 "X-Device-Token: <토큰>" 으로 TV를 찾는다.
function deviceByToken(app, request) {
  const token = (request.header.get("X-Device-Token") || "").trim()
  if (!token) throw new UnauthorizedError("기기 토큰이 없습니다.")
  try {
    return app.findFirstRecordByData("devices", "token_hash", $security.sha256(token))
  } catch (err) {
    // TV는 이 응답을 받으면 토큰을 버리고 다시 등록한다(관리 화면에서 TV를 지운 경우)
    throw new UnauthorizedError("등록되지 않은 기기입니다.")
  }
}

// 매장 계정이 자기 매장 TV만 다루게 한다.
function ownDevice(app, e) {
  const storeId = e.auth && e.auth.getString("store")
  if (!storeId) throw new ForbiddenError("매장 계정으로 로그인해 주세요.")
  let device
  try {
    device = app.findRecordById("devices", e.request.pathValue("id"))
  } catch (err) {
    throw new NotFoundError("TV가 없습니다.")
  }
  if (device.getString("store") !== storeId) throw new NotFoundError("TV가 없습니다.")
  return device
}

// 등록할 매장: 요청에 매장 번호가 있으면 그 매장, 없으면 이 서버의 하나뿐인 (가맹점 아닌) 매장.
function storeForRegister(app, storeId) {
  if (storeId) {
    try {
      return app.findRecordById("stores", String(storeId))
    } catch (err) {
      throw new NotFoundError("매장 번호가 올바르지 않습니다.")
    }
  }
  const stores = app.findRecordsByFilter("stores", "kind != 'franchise'", "", 2, 0)
  if (stores.length !== 1) {
    throw new BadRequestError(stores.length ? "이 서버에 매장이 여럿입니다. 매장 번호를 함께 보내 주세요." : "아직 매장이 없습니다.")
  }
  return stores[0]
}

function str(v, max) {
  return typeof v === "string" ? v.slice(0, max) : ""
}

function int(v, min, max) {
  return typeof v === "number" && v % 1 === 0 && v >= min && v <= max ? v : null
}

const SERVER_RE = /^[A-Za-z0-9.-]+(:[0-9]{1,5})?$/
const ROTATIONS = [0, 90, 180, 270]

// TV가 알려 온 설정 중 아는 칸만 남긴다.
function cleanReported(r) {
  r = r || {}
  return {
    server: str(r.server, 100),
    screen: int(r.screen, 1, 4),
    zoom: int(r.zoom, 25, 400),
    rotation: ROTATIONS.indexOf(r.rotation) >= 0 ? r.rotation : null,
    brightness: int(r.brightness, -1, 100),
    adb: typeof r.adb === "boolean" ? r.adb : null,       // 지금 ADB가 켜져 있는지(권한이 없으면 null)
    canAdb: r.canAdb === true,                             // ADB를 켜고 끌 권한이 있는지
    rev: int(r.rev, 0, 1e9),                               // 마지막으로 적용한 desired 번호
    usb: str(r.usb, 200),                                  // 마지막 USB 설정 파일 적용 결과
    note: str(r.note, 200),                                // 그 밖의 알림(예: 바꾸라는 서버 주소에 붙지 못함)
    width: int(r.width, 0, 10000),
    height: int(r.height, 0, 10000),
  }
}

// 관리 화면이 보낸 설정을 검사한다. 보낸 칸만 바꾼다. 틀리면 400.
function cleanDesired(body, old) {
  const d = Object.assign({}, old || {})
  const bad = (m) => { throw new BadRequestError(m) }
  if (body.screen !== undefined) d.screen = int(body.screen, 1, 4) || bad("화면 번호는 1~4 입니다.")
  if (body.zoom !== undefined) d.zoom = int(body.zoom, 25, 400) || bad("글자 배율은 25~400% 입니다.")
  if (body.rotation !== undefined) {
    if (ROTATIONS.indexOf(body.rotation) < 0) bad("화면 방향은 0, 90, 180, 270 중 하나입니다.")
    d.rotation = body.rotation
  }
  if (body.brightness !== undefined) {
    // -1 = TV 기본 밝기에 맡김
    const b = int(body.brightness, -1, 100)
    if (b === null || (b >= 0 && b < 10)) bad("밝기는 10~100% 이거나 -1(기본)입니다.")
    d.brightness = b
  }
  if (body.server !== undefined) {
    if (typeof body.server !== "string" || !SERVER_RE.test(body.server.trim())) bad("서버 주소는 192.168.0.10:8090 형식입니다.")
    d.server = body.server.trim()
  }
  return d
}

// TV에 돌려줄 명령: 바뀐 설정, 재시작·캡처 요청 번호, ADB 열림 여부.
function orders(device) {
  const until = device.getInt("adb_until")
  return {
    id: device.id,
    rev: device.getInt("rev"),
    desired: JSON.parse(device.getString("desired") || "null") || {},
    restartRev: device.getInt("restart_rev"),
    shotRev: device.getInt("shot_rev"),
    adbSeconds: Math.max(0, until - now()),
  }
}

module.exports = {
  MAX_DEVICES, MAX_SHOT, MAX_ADB_MINUTES, now, deviceByToken, ownDevice, storeForRegister, str, cleanReported, cleanDesired, orders,
}
