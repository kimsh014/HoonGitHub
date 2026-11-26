/// <reference path="../pb_data/types.d.ts" />
// 부른 번호는 매장마다 최근 30개만 남긴다. 직원이 지우지 않아도 쌓이지 않게.
// ponytail: 시간으로는 지우지 않는다. 전날 번호가 아침에 남아 있으면 수정 화면의 '전체 지우기'로 지운다.
onRecordAfterCreateSuccess((e) => {
  const old = e.app.findRecordsByFilter("calls", "store = {:store}", "-created", 1000, 30, { store: e.record.get("store") })
  old.forEach((r) => e.app.delete(r))
  e.next()
}, "calls")
