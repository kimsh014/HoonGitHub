// pos.pb.js가 쓰는 함수들. PocketBase는 라우트마다 따로 실행하므로 공용 함수는 require로 불러 쓴다.
// 이 파일은 이름이 .pb.js로 끝나지 않아서 훅으로 직접 실행되지는 않는다.

const MAX_UPDATES = 200 // 한 번에 바꿀 수 있는 메뉴 수
const MAX_AMOUNT = 10000000

// 요청 머리글의 연동 키로 매장을 찾는다. "Authorization: Bearer <키>" 또는 "X-POS-Key: <키>"
function storeByKey(app, request) {
  let key = request.header.get("X-POS-Key")
  const auth = request.header.get("Authorization")
  if (!key && auth.toLowerCase().indexOf("bearer ") === 0) key = auth.slice(7)
  key = (key || "").trim()
  if (!key) throw new UnauthorizedError("연동 키가 없습니다. X-POS-Key 머리글에 키를 넣어 주세요.")
  try {
    return app.findFirstRecordByData("stores", "pos_key_hash", $security.sha256(key))
  } catch (err) {
    throw new UnauthorizedError("연동 키가 올바르지 않습니다.")
  }
}

// 가맹점은 본사의 메뉴를 쓴다. 메뉴가 들어 있는 매장을 돌려준다.
function menuOwner(app, store) {
  const parent = store.getString("parent")
  return parent ? app.findRecordById("stores", parent) : store
}

function pricesOf(item) {
  const raw = item.getString("prices")
  return raw ? JSON.parse(raw) || [] : []
}

function soldOutIds(app, store, owner) {
  const rows = app.findRecordsByFilter("sold_out", "store = {:a} || store = {:b}", "", 0, 0, { a: store.id, b: owner.id })
  const sold = {}
  rows.forEach((r) => { sold[r.getString("item")] = true })
  return sold
}

// POS에 돌려주는 메뉴 한 줄의 모양
function view(item, sold) {
  return {
    id: item.id,
    posCode: item.getString("pos_code") || null,
    name: item.getString("name"),
    prices: pricesOf(item),
    soldOut: !!sold[item.id],
  }
}

function listItems(app, store) {
  const owner = menuOwner(app, store)
  const sold = soldOutIds(app, store, owner)
  return app.findRecordsByFilter("items", "store = {:s}", "sort_order", 0, 0, { s: owner.id }).map((i) => view(i, sold))
}

// 바꿀 메뉴 찾기: id → posCode → name 순으로 본다.
function findItem(app, owner, u, where) {
  if (u.id) {
    const rows = app.findRecordsByFilter("items", "store = {:s} && id = {:v}", "", 1, 0, { s: owner.id, v: String(u.id) })
    if (rows.length) return rows[0]
    throw new NotFoundError(where + "id가 " + u.id + "인 메뉴가 없습니다.")
  }
  if (u.posCode) {
    const rows = app.findRecordsByFilter("items", "store = {:s} && pos_code = {:v}", "", 1, 0, { s: owner.id, v: String(u.posCode) })
    if (rows.length) return rows[0]
    throw new NotFoundError(where + "POS 코드가 " + u.posCode + "인 메뉴가 없습니다.")
  }
  if (u.name) {
    const rows = app.findRecordsByFilter("items", "store = {:s} && name = {:v}", "", 2, 0, { s: owner.id, v: String(u.name) })
    if (rows.length === 1) return rows[0]
    throw rows.length
      ? new BadRequestError(where + "이름이 " + u.name + "인 메뉴가 여러 개입니다. posCode나 id로 지정해 주세요.")
      : new NotFoundError(where + "이름이 " + u.name + "인 메뉴가 없습니다.")
  }
  throw new BadRequestError(where + "id, posCode, name 중 하나로 메뉴를 지정해 주세요.")
}

function checkAmount(amount, where) {
  if (typeof amount !== "number" || amount % 1 !== 0 || amount < 0 || amount > MAX_AMOUNT) {
    throw new BadRequestError(where + "가격은 0~" + MAX_AMOUNT + " 사이의 정수여야 합니다.")
  }
}

// 새 가격 목록을 돌려준다. 바꾸지 않으면 null.
function newPrices(item, u, where) {
  if (u.prices !== undefined) {
    if (!Array.isArray(u.prices) || u.prices.length < 1 || u.prices.length > 2) {
      throw new BadRequestError(where + "prices는 가격 한 개 또는 두 개의 목록이어야 합니다.")
    }
    return u.prices.map((p) => {
      checkAmount(p && p.amount, where)
      const label = p.label == null || p.label === "" ? null : String(p.label).slice(0, 20)
      return { label: u.prices.length === 1 ? null : label, amount: p.amount }
    })
  }
  if (u.price !== undefined) {
    checkAmount(u.price, where)
    const old = pricesOf(item)
    if (old.length > 1) {
      throw new BadRequestError(where + "가격이 두 개인 메뉴(" + item.getString("name") + ")는 price 대신 prices로 바꿔 주세요.")
    }
    return [{ label: null, amount: u.price }]
  }
  return null
}

function setSoldOut(app, store, item, soldOut) {
  const rows = app.findRecordsByFilter("sold_out", "store = {:s} && item = {:i}", "", 1, 0, { s: store.id, i: item.id })
  if (soldOut && !rows.length) {
    const row = new Record(app.findCollectionByNameOrId("sold_out"))
    row.set("store", store.id)
    row.set("item", item.id)
    app.save(row)
  } else if (!soldOut && rows.length) {
    app.delete(rows[0])
  }
}

// 여러 메뉴의 품절·가격을 한 번에 바꾼다. 하나라도 틀리면 아무것도 바꾸지 않는다.
function applyUpdates(app, store, updates) {
  if (!Array.isArray(updates) || !updates.length) throw new BadRequestError("items에 바꿀 메뉴를 하나 이상 넣어 주세요.")
  if (updates.length > MAX_UPDATES) throw new BadRequestError("한 번에 " + MAX_UPDATES + "개까지 바꿀 수 있습니다.")
  const franchise = store.getString("kind") === "franchise"
  const changedIds = []
  app.runInTransaction((tx) => {
    const owner = menuOwner(tx, store)
    updates.forEach((u, n) => {
      const where = (n + 1) + "번째 메뉴: "
      if (!u || typeof u !== "object") throw new BadRequestError(where + "메뉴 한 줄은 객체여야 합니다.")
      const item = findItem(tx, owner, u, where)
      const prices = newPrices(item, u, where)
      if (u.soldOut === undefined && !prices) throw new BadRequestError(where + "soldOut, price, prices 중 하나는 넣어 주세요.")
      if (u.soldOut !== undefined && typeof u.soldOut !== "boolean") throw new BadRequestError(where + "soldOut은 true나 false여야 합니다.")
      if (prices) {
        if (franchise) throw new ForbiddenError(where + "가맹점 연동 키로는 가격을 바꿀 수 없습니다. 본사에서 바꿔 주세요.")
        item.set("prices", prices)
        tx.save(item)
      }
      if (u.soldOut !== undefined) setSoldOut(tx, store, item, u.soldOut)
      changedIds.push(item.id)
    })
  })
  const byId = {}
  listItems(app, store).forEach((i) => { byId[i.id] = i })
  return changedIds.map((id) => byId[id])
}

// ── 번호 호출 (키패드 앱) ──
// 번호표는 판매 프로그램·키오스크가 이미 찍는 주문번호를 그대로 쓴다. 직원이 키패드로 번호+Enter를 치면 TV에 띄운다.
// 부른 번호는 calls 컬렉션(매장마다 최근 30개, 10분 뒤 자동으로 빠짐)에 들어가고 TV는 실시간 구독으로 바로 그린다.
// 가맹점도 자기 매장 번호를 부른다(메뉴처럼 본사 것을 쓰지 않는다).
const CALL_MIN = 1
const CALL_MAX = 9999
const SAME_CALL_SECONDS = 3 // 같은 번호를 이 안에 또 부르면 한 번으로 친다(M-15, 키 두 번 눌림·재전송)

function callAt(row) {
  return new Date(String(row.getString("created")).replace(" ", "T")).getTime()
}

// 이 매장이 부른 번호들. 최근 것부터. at은 부른 시각(ms).
function listCalls(app, store) {
  return app.findRecordsByFilter("calls", "store = {:s}", "-created", 30, 0, { s: store.id })
    .map((r) => ({ number: r.getInt("number"), at: callAt(r) }))
}

function checkNumber(n) {
  if (typeof n === "string" && /^\d{1,4}$/.test(n.trim())) n = Number(n.trim())
  if (typeof n !== "number" || n % 1 !== 0 || n < CALL_MIN || n > CALL_MAX) {
    throw new BadRequestError("번호는 " + CALL_MIN + "~" + CALL_MAX + " 사이의 정수여야 합니다.")
  }
  return n
}

// action: "call"(기본) 번호 부르기 · "recall" 다시 부르기(이미 있어도 맨 앞으로, TV가 다시 깜빡임) · "cancel" 화면에서 빼기
// 돌려주는 것: { number, action, result: "called" | "ignored" | "removed" | "absent", calls: [...] }
function applyCall(app, store, body) {
  body = body || {}
  const action = body.action == null || body.action === "" ? "call" : String(body.action)
  if (["call", "recall", "cancel"].indexOf(action) < 0) throw new BadRequestError("action은 call, recall, cancel 중 하나여야 합니다.")
  const number = checkNumber(body.number)
  let result = ""
  app.runInTransaction((tx) => {
    const rows = tx.findRecordsByFilter("calls", "store = {:s} && number = {:n}", "", 10, 0, { s: store.id, n: number })
    if (action === "cancel") {
      rows.forEach((r) => tx.delete(r))
      result = rows.length ? "removed" : "absent"
      return
    }
    if (action === "call" && rows.length && Date.now() - callAt(rows[0]) < SAME_CALL_SECONDS * 1000) {
      result = "ignored"
      return
    }
    rows.forEach((r) => tx.delete(r)) // (store, number)는 하나만 있을 수 있다. 지우고 새로 넣어 맨 앞으로.
    const row = new Record(tx.findCollectionByNameOrId("calls"))
    row.set("store", store.id)
    row.set("number", number)
    tx.save(row)
    result = "called"
  })
  return { number: number, action: action, result: result, calls: listCalls(app, store) }
}

module.exports = { storeByKey, listItems, applyUpdates, listCalls, applyCall, SAME_CALL_SECONDS }
