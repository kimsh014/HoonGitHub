// safety.pb.js 가 쓰는 함수들. 이름이 .pb.js로 끝나지 않아 훅으로 직접 실행되지는 않는다.
// 매장 위험 점검표의 서버 쪽 1차 대응: 자동 백업(B-3), 지난 번호 정리(B-4), POS기 앞 비밀번호 다시 정하기(M-10).

// ── 자동 백업 (B-3) ──
// PocketBase 기본 자동 백업은 정해진 시각(cron)에만 돈다. 매장을 닫으며 POS기를 끄는 가게는 그 시각에 꺼져 있어
// 영영 백업이 안 되므로, 30분마다 "마지막 백업이 하루 넘었으면" 백업한다(켜고 30분 안에 하루 한 번).
// 이름이 @auto_pb_backup_ 로 시작해야 관리자 화면(/_/ Settings > Backups)에 자동 백업으로 보이고 거기서 되돌릴 수 있다.
const BACKUP_PREFIX = "@auto_pb_backup_menuboard_"
const BACKUP_KEEP = 7
const BACKUP_EVERY_SECONDS = 20 * 60 * 60 // 하루 영업 중 한 번은 잡히게 24시간보다 조금 짧게

function backupNames(app) {
  const fsys = app.newBackupsFilesystem()
  try {
    return fsys.list("").map((f) => ({ key: f.key, at: Math.floor(f.modTime.unix()) }))
      .filter((f) => f.key.indexOf(BACKUP_PREFIX) === 0 && f.key.slice(-4) === ".zip")
      .sort((a, b) => b.at - a.at)
  } finally {
    fsys.close()
  }
}

function stamp(d) {
  const p = (n, w) => ("000" + n).slice(-(w || 2))
  return "" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()) + p(d.getMilliseconds(), 3)
}

// A/S 기사가 누른 백업은 이름을 따로 두고 따로 센다. 여러 번 눌러도 매일 자동 백업이 밀려 지워지지 않게.
const MANUAL_PREFIX = BACKUP_PREFIX + "manual_"
const MANUAL_KEEP = 3

// 백업할 때가 되었으면 백업하고 7개(손으로 만든 것은 3개) 넘는 옛 백업을 지운다. 만든 백업 이름(안 만들었으면 "")을 돌려준다.
function backupIfDue(app, manual) {
  const isManual = (f) => f.key.indexOf(MANUAL_PREFIX) === 0
  const list = backupNames(app).filter((f) => !isManual(f))
  const nowSec = Math.floor(Date.now() / 1000)
  // 시계가 뒤로 간 경우(CMOS 배터리)도 "미래의 백업"을 믿지 않고 새로 만든다
  if (!manual && list.length && list[0].at <= nowSec && nowSec - list[0].at < BACKUP_EVERY_SECONDS) return ""
  const name = (manual ? MANUAL_PREFIX : BACKUP_PREFIX) + stamp(new Date()) + ".zip"
  app.createBackup(new Context(), name)
  const fsys = app.newBackupsFilesystem()
  try {
    const all = backupNames(app)
    const auto = all.filter((f) => !isManual(f)).slice(BACKUP_KEEP)
    const hand = all.filter(isManual).slice(MANUAL_KEEP)
    auto.concat(hand).forEach((f) => {
      fsys.delete(f.key)
      try { fsys.delete(f.key + ".attrs") } catch (err) {}
    })
  } finally {
    fsys.close()
  }
  return name
}

// ── 지난 번호 정리 (B-4) ──
// 부른 번호는 이 시간이 지나면 화면에서 빠진다. 손님이 받아 가기에 충분하고, 어제 번호가 아침에 남지 않게.
// 검사할 때만 환경 변수 MENUBOARD_CALL_KEEP_SECONDS 로 바꾼다.
const CALL_KEEP_MINUTES = 10

function callKeepSeconds() {
  const env = Number($os.getenv("MENUBOARD_CALL_KEEP_SECONDS"))
  return env > 0 ? env : CALL_KEEP_MINUTES * 60
}

function clearOldCalls(app) {
  const before = new Date(Date.now() - callKeepSeconds() * 1000).toISOString().replace("T", " ")
  const old = app.findRecordsByFilter("calls", "created < {:before}", "", 1000, 0, { before: before })
  old.forEach((r) => app.delete(r))
  return old.length
}

// ── POS기 앞에서만 되는 비밀번호 다시 정하기 (M-10) ──
// 매장 서버는 메일을 못 보내므로, POS기 자체(127.0.0.1)에서 연 화면만 비밀번호를 다시 정할 수 있게 한다.
// 같은 와이파이의 폰·TV·손님은 주소가 127.0.0.1이 아니라 막힌다. 프록시 머리글(X-Forwarded-For)은 보지 않는다.
function isLocal(e) {
  const ip = e.remoteIP()
  return ip === "127.0.0.1" || ip === "::1"
}

// 주소(Host·Origin)의 이름이 이 컴퓨터 자신인지. 포트는 보지 않는다.
function loopbackName(hostPort) {
  const m = String(hostPort || "").toLowerCase().match(/^(\[[^\]]*\]|[^:]*)/)
  const name = m ? m[1] : ""
  return name === "127.0.0.1" || name === "localhost" || name === "[::1]"
}

// POS기 브라우저에서 연 다른 사이트가 몰래 이 경로를 부르지 못하게(점검표 B-11) 주소 이름도 본다:
// - Host가 127.0.0.1·localhost가 아니면 거절(주소 이름 바꿔치기, DNS 리바인딩)
// - Origin이 있으면 그것도 127.0.0.1·localhost여야 함(다른 사이트의 fetch·양식 보내기)
function requireLocal(e) {
  const origin = e.request.header.get("Origin")
  if (!isLocal(e) || !loopbackName(e.request.host) || (origin && !loopbackName(origin.replace(/^[a-z]+:\/\//i, "")))) {
    throw new ForbiddenError("비밀번호 다시 정하기는 POS기에서 http://127.0.0.1:8090/reset.html 로 열어야 합니다.")
  }
}

module.exports = {
  BACKUP_PREFIX, BACKUP_KEEP, MANUAL_PREFIX, MANUAL_KEEP, CALL_KEEP_MINUTES,
  backupNames, backupIfDue, clearOldCalls, isLocal, requireLocal,
}
