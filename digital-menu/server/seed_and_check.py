"""샘플 매장·메뉴를 넣고, 접근 규칙이 설계대로 막고 여는지 검사한다.
사용: python seed_and_check.py   (서버가 127.0.0.1:8090 에서 돌고 있어야 함)
여러 번 돌려도 된다. 샘플 매장은 한 번만 만들고, 검사용 매장은 끝나면 지운다."""
import json
import pathlib
import secrets
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8090"
HERE = pathlib.Path(__file__).parent
REC = "/api/collections/%s/records"


def call(method, path, body=None, token=None):
    """(상태 코드, 응답 JSON)을 돌려준다. 4xx도 예외 없이 돌려준다."""
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", token)
    try:
        with urllib.request.urlopen(req) as res:
            text = res.read()
            return res.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def ok(result, what):
    assert 200 <= result[0] < 300, f"되어야 하는데 막힘: {what} -> {result}"
    return result[1]


def denied(result, what):
    assert result[0] in (400, 403, 404), f"막혀야 하는데 됨: {what} -> {result}"


def login(collection, email, password):
    return ok(call("POST", f"/api/collections/{collection}/auth-with-password", {"identity": email, "password": password}), f"{email} 로그인")


def make_account(admin, store_fields, email):
    """관리자 권한으로 검사용 매장과 계정을 만들고 (매장, 로그인 결과)를 돌려준다."""
    password = secrets.token_urlsafe(12)
    store = ok(call("POST", REC % "stores", store_fields, admin), "검사용 매장")
    ok(call("POST", REC % "users", {"email": email, "password": password, "passwordConfirm": password, "store": store["id"]}, admin), "검사용 계정")
    return store, login("users", email, password)


# ── 1. 첫 설치: 샘플 매장과 계정 ─────────────────────────────
owner_file = HERE / ".dev-owner"
if not owner_file.exists():
    owner_file.write_text("owner@menu.test\n" + secrets.token_urlsafe(12) + "\n")
email, password = owner_file.read_text().split()
setup = {"email": email, "password": password, "storeName": "우리카페"}
first = call("POST", "/api/menuboard/setup", setup)
assert first[0] in (200, 403), first
denied(call("POST", "/api/menuboard/setup", setup), "두 번째 설치")

auth = login("users", email, password)
owner, store_id = auth["token"], auth["record"]["store"]

# ── 2. 샘플 메뉴 (없을 때만) ──────────────────────────────────
if not ok(call("GET", REC % "sections" + f"?filter=(store='{store_id}')"), "구역 읽기")["items"]:
    ok(call("PATCH", REC % "stores" + "/" + store_id, {"brand_color": "#c8102e", "tv_count": 3}, owner), "브랜드 색 저장")
    menu = {
        "커피": [("아메리카노", [["HOT", 4500], ["ICE", 5000]], "best"), ("카페라떼", [["HOT", 5000], ["ICE", 5500]], ""),
               ("바닐라라떼", [["HOT", 5500], ["ICE", 6000]], "new"), ("에스프레소", [[None, 4000]], "")],
        "디저트": [("치즈케이크", [[None, 6500]], "best"), ("티라미수", [[None, 7000]], ""), ("크루아상", [[None, 4200]], "new")],
    }
    section_ids = []
    for s_no, (section_name, rows) in enumerate(menu.items(), 1):
        section = ok(call("POST", REC % "sections", {"store": store_id, "name": section_name, "sort_order": s_no}, owner), "구역 추가")
        section_ids.append(section["id"])
        for i_no, (name, prices, badge) in enumerate(rows, 1):
            ok(call("POST", REC % "items", {
                "store": store_id, "section": section["id"], "name": name, "sort_order": i_no, "badge": badge,
                "prices": [{"label": label, "amount": amount} for label, amount in prices],
            }, owner), "메뉴 추가")
    for no, body in enumerate([
        {"type": "grid", "sections": section_ids[:1]},
        {"type": "list", "sections": section_ids[1:]},
        {"type": "promo", "promo_lines": ["겨울 한정 바닐라라떼", "지금 만나 보세요"]},
    ], 1):
        ok(call("POST", REC % "screens", dict(body, store=store_id, no=no), owner), "화면 구성 추가")
    print("샘플 매장 '우리카페'에 구역 2개, 메뉴 7개, 화면 3개를 넣었습니다.")

items = ok(call("GET", REC % "items" + f"?filter=(store='{store_id}')"), "로그인 없이 메뉴 읽기")["items"]
assert len(items) == 7, len(items)
item_id = items[0]["id"]

# ── 3. 규칙 검사: 개인 매장 ───────────────────────────────────
ok(call("GET", REC % "stores" + "/" + store_id), "로그인 없이 매장 한 줄 읽기")
assert ok(call("GET", REC % "stores"), "로그인 없이 매장 목록")["items"] == [], "로그인 없이 매장 목록이 보임"
assert ok(call("GET", REC % "users"), "로그인 없이 계정 목록")["items"] == [], "로그인 없이 계정이 보임"
denied(call("POST", REC % "items", {"store": store_id, "section": items[0]["section"], "name": "침입"}), "로그인 없이 메뉴 추가")
denied(call("PATCH", REC % "items" + "/" + item_id, {"name": "침입"}), "로그인 없이 메뉴 수정")
denied(call("POST", REC % "users", {"email": "x@menu.test", "password": "12345678", "passwordConfirm": "12345678"}), "공개 가입")
denied(call("PATCH", REC % "stores" + "/" + store_id, {"kind": "hq"}, owner), "자기 매장 종류 바꾸기")
ok(call("PATCH", REC % "items" + "/" + item_id, {"sort_order": 1}, owner), "자기 메뉴 수정")
sold = ok(call("POST", REC % "sold_out", {"store": store_id, "item": item_id}, owner), "자기 메뉴 품절 켜기")
ok(call("DELETE", REC % "sold_out" + "/" + sold["id"], token=owner), "자기 메뉴 품절 끄기")

# ── 4. 규칙 검사: 다른 매장, 프랜차이즈 (검사용 매장은 끝나면 지운다) ──
admin_email, admin_password = (HERE / ".dev-superuser").read_text().split()
admin = login("_superusers", admin_email, admin_password)["token"]
tag = secrets.token_hex(3)
made = []
try:
    other_store, other = make_account(admin, {"kind": "independent", "name": "남의가게"}, f"other-{tag}@menu.test")
    made.append(other_store["id"])
    denied(call("POST", REC % "items", {"store": store_id, "section": items[0]["section"], "name": "침입"}, other["token"]), "남의 매장에 메뉴 추가")
    denied(call("PATCH", REC % "items" + "/" + item_id, {"name": "침입"}, other["token"]), "남의 메뉴 수정")
    denied(call("DELETE", REC % "items" + "/" + item_id, token=other["token"]), "남의 메뉴 삭제")
    denied(call("POST", REC % "sold_out", {"store": other_store["id"], "item": item_id}, other["token"]), "남의 메뉴를 품절로")
    denied(call("PATCH", REC % "users" + "/" + other["record"]["id"], {"store": store_id}, other["token"]), "자기 계정을 남의 매장으로 옮기기")
    denied(call("PATCH", REC % "stores" + "/" + store_id, {"name": "침입"}, other["token"]), "남의 매장 이름 바꾸기")

    hq_store, hq = make_account(admin, {"kind": "hq", "name": "본사"}, f"hq-{tag}@menu.test")
    made.append(hq_store["id"])
    hq_token = hq["token"]
    hq_section = ok(call("POST", REC % "sections", {"store": hq_store["id"], "name": "공통"}, hq_token), "본사 구역 추가")
    hq_item = ok(call("POST", REC % "items", {"store": hq_store["id"], "section": hq_section["id"], "name": "공통메뉴"}, hq_token), "본사 메뉴 추가")
    branch = ok(call("POST", REC % "stores", {"kind": "franchise", "name": "1호점", "parent": hq_store["id"], "tv_count": 3}, hq_token), "본사가 가맹점 등록")
    made.append(branch["id"])
    denied(call("POST", REC % "stores", {"kind": "hq", "name": "가짜본사"}, hq_token), "본사가 다른 본사 만들기")
    branch_password = secrets.token_urlsafe(12)
    branch_email = f"branch-{tag}@menu.test"
    ok(call("POST", REC % "users", {"email": branch_email, "password": branch_password, "passwordConfirm": branch_password, "store": branch["id"]}, hq_token), "본사가 가맹점 계정 만들기")
    denied(call("POST", REC % "users", {"email": f"x-{tag}@menu.test", "password": branch_password, "passwordConfirm": branch_password, "store": store_id}, hq_token), "본사가 남의 매장 계정 만들기")
    listed = {s["id"] for s in ok(call("GET", REC % "stores", token=hq_token), "본사의 매장 목록")["items"]}
    assert listed == {hq_store["id"], branch["id"]}, listed  # 자기 매장과 자기 가맹점만

    branch_token = login("users", branch_email, branch_password)["token"]
    denied(call("POST", REC % "items", {"store": branch["id"], "section": hq_section["id"], "name": "침입"}, branch_token), "가맹점이 메뉴 추가")
    denied(call("PATCH", REC % "items" + "/" + hq_item["id"], {"name": "침입"}, branch_token), "가맹점이 본사 메뉴 수정")
    denied(call("PATCH", REC % "stores" + "/" + branch["id"], {"name": "침입"}, branch_token), "가맹점이 매장 이름 바꾸기")
    ok(call("POST", REC % "sold_out", {"store": branch["id"], "item": hq_item["id"]}, branch_token), "가맹점이 본사 메뉴 품절 켜기")
    denied(call("POST", REC % "sold_out", {"store": branch["id"], "item": item_id}, branch_token), "가맹점이 남의 메뉴를 품절로")
finally:
    for sid in reversed(made):  # 매장을 지우면 구역·메뉴·품절·화면이 같이 지워진다
        call("DELETE", REC % "stores" + "/" + sid, token=admin)
    for user in ok(call("GET", REC % "users" + f"?filter=(email~'-{tag}@')", token=admin), "검사용 계정 찾기")["items"]:
        call("DELETE", REC % "users" + "/" + user["id"], token=admin)

print("OK: 샘플 매장이 있고, 접근 규칙이 개인 매장·남의 매장·본사·가맹점 경우 모두 설계대로 막고 엽니다.")
