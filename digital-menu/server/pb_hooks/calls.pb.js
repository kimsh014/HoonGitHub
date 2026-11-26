/// <reference path="../pb_data/types.d.ts" />
// 부른 번호는 매장마다 최근 30개만 남긴다. 직원이 지우지 않아도 쌓이지 않게.
// 시간이 지난 번호(10분)와 서버가 켜질 때의 지난 번호는 safety.pb.js가 지운다.
onRecordAfterCreateSuccess((e) => {
  const old = e.app.findRecordsByFilter("calls", "store = {:store}", "-created", 1000, 30, { store: e.record.get("store") })
  old.forEach((r) => e.app.delete(r))
  e.next()
}, "calls")
