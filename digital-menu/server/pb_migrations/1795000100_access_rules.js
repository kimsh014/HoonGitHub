/// <reference path="../pb_data/types.d.ts" />
// 접근 규칙. null = 관리자만, "" = 누구나, 그 외 = 조건을 만족하는 요청만.
// 읽기: 메뉴판에 나오는 내용은 로그인 없이 읽는다 (TV에 공개되는 내용).
// 쓰기: 로그인한 계정의 매장 것만. 가맹점 계정은 품절(sold_out)만.
migrate((app) => {
  const own = '@request.auth.store = store'
  const editor = own + ' && @request.auth.store.kind != "franchise"'
  const keepStore = ' && @request.body.store:isset = false' // 줄을 다른 매장으로 옮기지 못하게

  const rules = {
    stores: {
      // 목록은 자기 매장과 자기 가맹점만. 매장 번호를 아는 TV는 한 줄씩 읽을 수 있다.
      listRule: '@request.auth.store != "" && (@request.auth.store = id || @request.auth.store = parent)',
      viewRule: '',
      createRule: '@request.auth.store.kind = "hq" && kind = "franchise" && parent = @request.auth.store',
      updateRule: '@request.auth.store = id && kind != "franchise" && @request.body.kind:isset = false && @request.body.parent:isset = false',
      deleteRule: null,
    },
    users: {
      listRule: 'id = @request.auth.id',
      viewRule: 'id = @request.auth.id',
      // 공개 가입은 막는다. 본사만 자기 가맹점의 계정을 만든다. 개인 매장의 첫 계정은 pb_hooks/setup.pb.js
      createRule: '@request.auth.store.kind = "hq" && store.parent = @request.auth.store',
      updateRule: 'id = @request.auth.id && @request.body.store:isset = false', // 자기 매장을 바꿔 남의 매장에 들어가지 못하게
      deleteRule: null,
    },
    sections: { listRule: '', viewRule: '', createRule: editor, updateRule: editor + keepStore, deleteRule: editor },
    // ponytail: 수정할 때 새 section이 같은 매장 것인지는 검사하지 않는다. 남의 구역을 가리키면
    // 자기 메뉴판에서 그 메뉴가 안 보일 뿐이라 둔다. 필요해지면 onRecordUpdateRequest 훅에서 검사.
    items: {
      listRule: '', viewRule: '',
      createRule: editor + ' && section.store = store',
      updateRule: editor + keepStore,
      deleteRule: editor,
    },
    screens: { listRule: '', viewRule: '', createRule: editor, updateRule: editor + keepStore, deleteRule: editor },
    sold_out: {
      listRule: '', viewRule: '',
      // 자기 매장 메뉴이거나, 가맹점이면 본사 메뉴
      createRule: own + ' && (item.store = store || item.store = store.parent)',
      updateRule: null,
      deleteRule: own,
    },
  }
  for (const name in rules) {
    const collection = app.findCollectionByNameOrId(name)
    unmarshal(rules[name], collection)
    app.save(collection)
  }
}, (app) => {
  const locked = { listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null }
  for (const name of ["stores", "users", "sections", "items", "screens", "sold_out"]) {
    const collection = app.findCollectionByNameOrId(name)
    unmarshal(locked, collection)
    app.save(collection)
  }
})
