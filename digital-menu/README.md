# 디지털 메뉴판 (digital-menu)

매장 POS PC에서 메뉴판 서버를 돌리고, 천장 화면에 연결한 안드로이드 보드가 그 서버의 메뉴판 웹 화면을 띄우는 시스템입니다.

## 구조

```
POS PC (Windows)                               안드로이드 보드 → 35~66인치 화면
┌──────────────────────────────┐               ┌──────────────────────────────┐
│ PocketBase 서버 :8090        │  http (LAN)   │ board-app (WebView 플레이어) │
│  - pb_public/index.html 메뉴판│ ◀──────────── │  http://<서버>/?screen=N&zoom=Z│
│  - pb_public/admin.html 수정  │  실시간 구독   │                              │
│  - api.js / board.js         │ ──────────▶   │  끊기면 마지막 화면(last.mht) │
└──────────────────────────────┘               └──────────────────────────────┘
        ▲ 브라우저 (POS 화면·폰)에서 admin.html로 메뉴 수정
```

- **서버 (`server/`)**: [PocketBase](https://pocketbase.io) 위에 메뉴판 데이터와 화면 파일을 올린 것입니다.
  - `pb_migrations/`: 컬렉션 정의. `stores`(본사 `hq` / 가맹점 `franchise` / 개인 매장 `independent`), `users`(매장에 속한 계정), `sections`, `items`(가격 여러 개, 사진, `new`/`best` 배지), `sold_out`(줄이 있으면 품절), `screens`(화면 번호, `grid`/`list`/`promo` 형식, 번호 띠 `call_band`), `calls`(부른 번호). 접근 규칙은 `1795000100_access_rules.js`.
  - `pb_hooks/setup.pb.js`: 계정이 하나도 없을 때만 첫 매장과 계정을 만드는 `POST /api/menuboard/setup`, 서버에 매장이 하나뿐일 때 그 번호를 알려 주는 `GET /api/menuboard/store`, 화면 파일 `Cache-Control: no-cache`.
  - `pb_hooks/calls.pb.js`: 부른 번호는 매장마다 최근 30개만 남깁니다.
  - `pb_hooks/pos.pb.js`(+ `pos_lib.js`): POS·키오스크가 품절·가격을 보내는 `/api/menuboard/pos/*`. 아래 "POS·키오스크 연동" 참고.
  - `pb_public/api.js`: 화면이 서버를 부르는 유일한 곳(로그인, 메뉴·구역·화면 저장, 품절, 번호 호출, `getBoard`, `onBoardChange` 실시간 구독).
  - `pb_public/board.js`: 메뉴판 화면 갱신 흐름. 주소 `/?screen=화면번호` (선택 `&zoom=글자배율%`, `&refresh=초`(기본 300), `&store=매장번호`(서버에 매장이 여럿일 때)). 데이터를 받으면 `index.html`의 `renderBoard(board, screenNo)`를 부릅니다.
  - `pb_public/index.html`: 메뉴판 화면(사진 격자 · 목록 + 큰 사진 · 홍보 · 번호 전용, 번호 띠). 요구사항은 `../ui-prompt.md`, 화면 모습은 `docs/screens/`에 있습니다.
  - `pb_public/admin.html`: 동작 확인용 시안입니다. UI 담당이 바꿀 수정 화면입니다.
- **보드 앱 (`board-app/`)**: 메뉴판 주소를 전체 화면 WebView로 띄우는 안드로이드 앱(`com.menuboard.player`, minSdk 30). 안드로이드 TV와 일반 안드로이드 보드 둘 다 지원합니다.
  - 켜기: 홈 앱으로 지정할 수 있는 보드는 홈 앱으로, 구글 TV처럼 홈 앱을 못 바꾸는 TV는 부팅 완료 알림으로 스스로 뜹니다(‘다른 앱 위에 표시’ 허용 필요, 설치 bat이 허용). 화면 꺼짐·화면 보호기는 막습니다.
  - 리모컨: 메뉴판 화면에서 **확인 버튼 2초**(또는 MENU·설정 버튼)로 설정 화면. 설정 화면은 방향키와 확인만으로 움직이고, 2분 동안 손대지 않으면 메뉴판으로 돌아갑니다(업데이트를 받는 중에는 기다림).
  - 서버 찾기: 처음 켜면 같은 망(/24)에서 8090 포트의 메뉴판 서버(`/api/menuboard/store`가 매장 번호를 돌려줌)를 찾아 하나뿐이면 바로 씁니다. 설정 화면의 ‘서버 자동 찾기’로도 찾습니다. 붙은 서버의 매장 번호를 기억해 두고, 나중에 다시 찾을 때는 같은 매장 번호의 서버로만 옮깁니다(공유기를 같이 쓰는 옆 가게 서버로 옮겨 가지 않게).
  - 원격 관리: 아래 ‘TV 원격 관리’. 리모컨 설정 화면에서도 화면 방향과 밝기를 바꿀 수 있습니다.
  - 끊김: 마지막 화면은 10분에 한 번만 저장합니다(저장 장치 수명). `/api/health`가 응답하지 않으면 마지막으로 저장한 화면을 띄우고 15초마다 다시 확인합니다. 실제 화면을 띄운 동안에도 30초마다 확인하고, 끊겼다 다시 붙으면 화면을 새로 불러옵니다. 와이파이·랜이 다시 잡히면 바로 확인합니다. 2분 넘게 끊기면 서버 주소가 바뀌었는지 망을 다시 찾아봅니다(10분에 한 번, 하나만 찾았을 때만 바꿈).
  - 업데이트: 매장 서버의 `/updates/board-app.json`을 6시간마다 확인해 두고, 설정 화면의 ‘업데이트 확인·설치’로 설치합니다(아래 ‘보드 앱 업데이트’).
- **`ui-prompt.md`**: 화면(UI) 작업 요구사항과 화면이 받는 데이터 계약.
- **`index.html`** (이 폴더 맨 위): 서버 없이 메뉴를 코드에 적어 띄우는 초기 한 장짜리 메뉴판 시안.

> POS·키오스크는 아래 "POS·키오스크 연동"의 HTTP 요청으로 품절·가격을 보냅니다. 특정 POS 프로그램에 맞춘 연결 코드는 아직 없습니다.

## 서버 실행 (POS PC, Windows)

매장 설치는 **[설치 안내서 `docs/install-pos.md`](docs/install-pos.md)** 를 따릅니다(설치 기사용, 고정 IP·BIOS·백신·백업 포함).

1. [PocketBase](https://github.com/pocketbase/pocketbase/releases) Windows 실행 파일(작업 당시 v0.40.6)을 받아 `server/pocketbase.exe`로 둡니다. 실행 파일은 저장소에 넣지 않습니다.
2. **매장 설치**: `server/install-server.bat`을 더블클릭합니다(관리자 권한으로 스스로 다시 열림). 인터넷 없이 Windows 기본 기능만 씁니다.
   - 작업 스케줄러 작업 `MenuBoardServer`: 컴퓨터가 켜지면 로그온 없이 SYSTEM 계정으로 `run-server.ps1`을 창 없이 실행. 배터리 조건 없음, 실행 시간 제한 없음, 실패 시 1분마다 다시 시작(999번).
   - `run-server.ps1`: 아래 명령(경로는 이 폴더 기준 절대 경로)을 돌리고, 꺼지면 5초 뒤 다시 켭니다. 출력은 `server/logs/server-YYYYMMDD.log`(하루 단위, 5MB 넘으면 `.1.log`로 교체, 14일 보관).
     ```
     pocketbase.exe serve --http 0.0.0.0:8090 --dir pb_data --migrationsDir pb_migrations --hooksDir pb_hooks --publicDir pb_public
     ```
   - A/S 관리자(PocketBase superuser) `as@poswing.local`을 설치마다 무작위 24자 비밀번호로 `superuser create`. 이미 있으면 그대로 두고, `install-server.bat --reset`일 때만 `superuser upsert`로 새로 만듭니다. 비밀번호는 화면과 `server/AS-관리자-비밀번호.txt`(Administrators·SYSTEM만 읽기)에 나옵니다. A/S 기록에 옮기고 파일은 지웁니다.
   - 방화벽: 그룹 `MenuBoard`로 TCP 8090 들어오기 규칙과 `pocketbase.exe` 프로그램 규칙(모든 프로필, 원격 주소 `LocalSubnet`). Windows가 저절로 만든 `pocketbase.exe` 규칙(차단 포함)은 지우고 다시 만듭니다.
   - `powercfg`로 AC 절전·최대 절전·디스크 끄기 0, 빠른 시작 끄기(물음), Windows 업데이트 사용 시간 7~24시(레지스트리, Home 에디션은 안 먹을 수 있음), Defender 예외(실패해도 계속).
   - 제거: `server/uninstall-server.bat`(작업·방화벽·Defender 예외만 지우고 `pb_data`는 남김).
3. **개발·점검용**: `server/start-server.bat`은 같은 명령을 콘솔 창에서 돌립니다(창을 닫으면 꺼짐). `MenuBoardServer`가 설치돼 있거나 8090이 이미 쓰이면 경고합니다. 먼저 `schtasks /end /tn MenuBoardServer`.
4. 수정 화면: `http://127.0.0.1:8090/admin.html`. 빈 서버에서는 여기서 첫 매장과 계정을 만듭니다.
5. 메뉴판 화면: `http://127.0.0.1:8090/?screen=1&zoom=100`

`.bat`·`.ps1`은 CRLF로 꺼내지게 `.gitattributes`에 적어 두었고, `.ps1`은 UTF-8 BOM으로 저장합니다(Windows PowerShell 5.1이 BOM 없는 한글을 깨뜨림).

### 배포 묶음 `dist/` 만들기 (커밋하지 않음)

```
dist/
  server/   pocketbase.exe(v0.40.6, Windows) pb_migrations/ pb_hooks/ pb_public/
            install-server.bat install-server.ps1 run-server.ps1 uninstall-server.bat start-server.bat
  board-app/ menuboard-player.apk install-board-app.bat
  order-app/ src/ build.bat install-order-app.bat install-order-app.ps1
```

`server/`에서 위 파일만 복사합니다. `pb_data/`, `logs/`, `.dev-*`, `AS-관리자-비밀번호.txt`, `shots/`, 검사 스크립트(`check_*.js`, `seed_and_check.py`)는 넣지 않습니다. 묶음을 만든 뒤 `dist/server`에 `pb_data`와 `.dev-`로 시작하는 파일이 없는지 확인합니다.

### 검사 스크립트 (서버가 127.0.0.1:8090에서 돌고 있어야 함)

- `python seed_and_check.py`: 샘플 매장 '우리카페'와 메뉴를 넣고 접근 규칙을 검사합니다. 개발용 계정을 `server/.dev-owner`에 만들어 쓰고, `server/.dev-superuser`(PocketBase 관리자 이메일과 비밀번호, 한 줄씩)가 필요합니다. 두 파일은 커밋하지 않습니다.
- `node check_api.js`: `api.js`의 계약 함수 전부를 실제 서버에 대고 검사합니다 (`seed_and_check.py`를 먼저 실행).
- `node check_board.js`: `board.js` 갱신 흐름을 서버 없이 검사합니다.
- `node check_screens.js [shots]`: 메뉴판 화면을 서버 없이 가짜 데이터로 띄워 1920×1080, 3840×2160, 세로 1080×1920과 글자 배율 100·150%에서 잘리는 글이 없는지 검사합니다. `shots`를 붙이면 `server/shots/`에 스크린샷을 남깁니다(Playwright와 Chromium 필요, 서버는 필요 없음).
- `node check_devices.js`: TV 원격 관리(등록·보고, 설정 바꾸기, 재시작·캡처·A/S 연결 요청, 캡처 사진, 매장 구분)를 임시 서버(127.0.0.1:8093)로 검사합니다.
- `node check_pos.js`: POS·키오스크 연동을 검사합니다. 켜 둔 서버와 상관없이 임시 서버(127.0.0.1:8092)를 잠깐 띄워 쓰고, `pocketbase.exe`만 있으면 됩니다(다른 위치면 `POCKETBASE` 환경 변수). 보드 화면(`board.js`)이 POS 변경을 새로고침 없이 다시 그리는 데 걸린 시간도 찍습니다.
- `node check_calls.js`: 키패드 앱이 쓰는 번호 호출 경로(`/api/menuboard/pos/calls`)를 임시 서버(127.0.0.1:8096)로 검사합니다. 부르기·다시 부르기·빼기, 3초 안 같은 번호, 틀린 번호, 가맹점 구분, TV 화면 반영 시간을 봅니다.
- `node check_admin.js`: 수정 화면(`admin.html`)을 실제 브라우저(Playwright chromium)로 눌러 봅니다. 임시 서버(127.0.0.1:8094)를 잠깐 띄워 쓰고, 가격 읽기·확인창, 사진 줄이기, 저장 중 잠금, 구역 지우기 막기, 품절 목록, TV 미리보기, 폰 크기 넘침을 확인합니다. `SHOTS=폴더`를 주면 화면 사진을 남깁니다.

## POS·키오스크 연동

POS나 키오스크가 메뉴의 품절·가격을 서버에 보내면, 보드 화면은 이미 하고 있는 실시간 구독(`api.onBoardChange`)으로 새로고침 없이 바로(보통 1초 안) 다시 그립니다. 보드 앱이나 `index.html`은 바꿀 것이 없습니다.

```
POS / 키오스크 ──HTTP POST /api/menuboard/pos/items──▶ PocketBase (sold_out·items 저장)
                                                          │ 실시간 알림 (SSE /api/realtime)
                                                          ▼
                                                   보드 화면 board.js → renderBoard
```

### 준비

1. 수정 화면(`admin.html`) 맨 아래 **POS·키오스크 연동**에서 **새 연동 키 만들기**를 누르고, 나온 키(`mbpos_…`)를 POS·키오스크 설정에 넣습니다. 키는 이때 한 번만 보이고 서버에는 해시만 남습니다. 다시 만들면 예전 키는 바로 막힙니다(키가 새었을 때도 이렇게 바꿉니다).
2. 메뉴마다 **POS 코드** 칸에 POS의 상품 코드를 넣습니다(한 매장 안에서 겹치지 않아야 함). 넣지 않으면 메뉴 이름이나 id로도 지정할 수 있습니다.

모든 요청에 키를 `X-POS-Key: <키>` 또는 `Authorization: Bearer <키>` 머리글로 싣습니다. 키가 없거나 틀리면 401입니다.

### 메뉴 목록: `GET /api/menuboard/pos/items`

```
curl http://192.168.0.10:8090/api/menuboard/pos/items -H "X-POS-Key: mbpos_…"
```
```json
{ "store": { "id": "…", "name": "우리카페" },
  "items": [ { "id": "…", "posCode": "A01", "name": "아메리카노",
               "prices": [ { "label": "HOT", "amount": 4500 }, { "label": "ICE", "amount": 5000 } ], "soldOut": false } ] }
```

### 품절·가격 바꾸기: `POST /api/menuboard/pos/items`

```
curl -X POST http://192.168.0.10:8090/api/menuboard/pos/items -H "X-POS-Key: mbpos_…" -H "Content-Type: application/json" ^
  -d "{\"items\":[{\"posCode\":\"A01\",\"soldOut\":true},{\"name\":\"치즈케이크\",\"price\":6800}]}"
```

`items`의 한 줄(한 번에 200개까지):

| 칸 | 뜻 |
| --- | --- |
| `posCode` / `name` / `id` | 바꿀 메뉴. 하나만 넣습니다. 여럿이면 `id` → `posCode` → `name` 순으로 봅니다. `name`은 정확히 같아야 하고, 같은 이름이 둘이면 400 |
| `soldOut` | `true` 품절, `false` 품절 풀기 |
| `price` | 가격이 하나인 메뉴의 새 가격(0 이상 정수, 원). 가격이 둘(HOT/ICE 등)인 메뉴는 400 |
| `prices` | 가격 목록을 통째로 바꿈. `[{ "label": "HOT", "amount": 4500 }, { "label": "ICE", "amount": 5000 }]` (한 개 또는 두 개) |

`soldOut`, `price`, `prices` 중 하나 이상은 넣어야 합니다. 응답은 바뀐 메뉴들의 지금 상태(`{ "items": [ … ] }`, 모양은 목록과 같음)입니다.

한 요청 안에서 하나라도 틀리면(없는 메뉴, 잘못된 가격 등) **아무것도 바꾸지 않고** 오류를 돌려줍니다. 오류 문장에 몇 번째 줄인지가 붙습니다(예: `2번째 메뉴: POS 코드가 ZZZ인 메뉴가 없습니다.`). 같은 요청을 다시 보내도 결과가 같으니, 응답을 못 받았으면 그대로 다시 보내면 됩니다.

### 프랜차이즈

가맹점 계정으로 만든 키는 본사 메뉴를 보고, **품절만** 바꿀 수 있습니다(가맹점 자기 매장에만 품절이 걸림). 가격을 보내면 403입니다. 가격은 본사 키로 바꾸고, 본사에서 바꾼 품절·가격은 모든 가맹점 보드에 반영됩니다.

> ponytail: 연동 키는 매장마다 하나입니다. POS와 키오스크가 같은 키를 씁니다. 기기마다 따로 끊을 일이 생기면 키 컬렉션을 따로 두게 고칠 것. 서버는 매장 LAN의 http로 돌므로, 인터넷에 열 때는 https 뒤에 두어 키가 그대로 지나가지 않게 할 것.

## 번호 호출 키패드 앱 (`order-app/`)

1차 번호 호출 방식: 판매 프로그램·키오스크가 이미 찍는 주문번호를 번호표로 쓰고, 음식이 나오면 직원이 POS기의 USB 숫자 키패드로 **번호 + Enter**를 칩니다. 키패드 앱이 서버에 보내고 TV 메뉴판(번호 화면·번호 띠)에 바로(보통 0.5초 안) 뜹니다. 부른 번호는 10분 뒤 TV에서 저절로 빠집니다.

```
USB 숫자 키패드 ─▶ MenuBoardKeypad.exe (POS기, 항상 위 좁은 창)
                     └─HTTP POST /api/menuboard/pos/calls (X-POS-Key)─▶ 메뉴판 서버 ─실시간─▶ TV
```

- 키: 번호+Enter 부르기 · `+`[번호]Enter 다시 부르기 · `-`[번호]Enter TV에서 빼기(번호 없이 Enter면 맨 앞 번호, 방금 완료 취소) · `.` 한 자리 지움 · `*` `/` 모두 지움. 창의 화면 단추로도 똑같이 됩니다.
- 판매 프로그램에 포커스가 있어도 숫자패드를 받고, 그 키는 판매 프로그램에 넘기지 않습니다. Num Lock이 꺼져 있어도 숫자로 읽습니다.
- 실수 막기: 최근 번호와 30 넘게 떨어진 번호, 이미 TV에 있는 번호는 Enter를 한 번 더 받습니다. 3초 안에 같은 번호는 한 번만 띄웁니다(서버도 한 번 더 막음).
- 기술: Windows 10에 들어 있는 .NET Framework 4.8로 도는 exe 하나(약 40KB). 따로 깔 런타임이 없고, `build.bat`이 Windows 기본 `csc.exe`로 빌드합니다.
- 설치: `order-app/install-order-app.bat`을 판매 프로그램을 쓰는 Windows 계정에서 더블클릭. 로그인할 때 가장 높은 권한으로 켜지고(작업 스케줄러 `MenuBoardKeypad`), 앱이 꺼지면 2초 뒤 다시 켜집니다. 처음 켜면 설정 창에 수정 화면의 POS 연동 키를 붙여 넣습니다.
- 자세한 사용법·한계·현장 시험 항목: `docs/order-app.md`.

### 번호 호출 API (연동 키)

| 요청 | 본문 | 응답 |
| --- | --- | --- |
| `GET /api/menuboard/pos/calls` | | `{ "store": { "id", "name" }, "calls": [ { "number": 12, "at": 1795651200000 } ] }` (최근 것부터, 최대 30개) |
| `POST /api/menuboard/pos/calls` | `{ "number": 12, "action": "call" }` | `{ "number", "action", "result", "calls" }` |

`action`: `call`(기본, 3초 안에 같은 번호면 `result: "ignored"`) · `recall`(이미 있어도 맨 앞으로, TV가 다시 깜빡임) · `cancel`(TV에서 빼기, 없으면 `result: "absent"`). `result`는 `called`·`ignored`·`removed`·`absent`. 번호는 1~9999 정수(숫자 글자도 받음), 틀리면 400. 가맹점 키는 자기 매장 번호만 다룹니다. 로그인이 필요 없어서 매장 계정 로그인이 만료돼도(B-12) 번호를 부를 수 있습니다.

## 보드 앱 빌드와 설치

1. **빌드** (Git Bash, Gradle 없이 Android SDK 도구만 사용): `board-app/build.sh`
   - 필요: Android SDK build-tools 36.0.0, platforms/android-37.0, JDK(기본값 Android Studio의 `jbr`). 경로는 `ANDROID_SDK`, `JDK_HOME`으로 바꿀 수 있습니다.
   - 결과: `board-app/build/menuboard-player.apk`와 업데이트 묶음 `board-app/build/updates/`. 버전은 `build.sh` 맨 위 `VERSION_CODE`(새 버전마다 1씩 올림)와 `VERSION_NAME`.
   - 서명 키 `.debug.keystore`가 없으면 새로 만듭니다. **업데이트는 같은 키로 서명한 APK만 설치되므로 이 파일을 백업하세요.** 잃으면 설치된 보드는 앱을 지우고 다시 깔아야 합니다.
2. **설치**: `menuboard-player.apk`를 `install-board-app.bat`과 같은 폴더에 두고, 보드를 USB(또는 adb 네트워크)로 연결한 PC에서 더블클릭합니다. bat이 부팅 자동 실행과 업데이트 설치 권한도 허용합니다. adb가 없으면 APK를 USB 메모리로 옮겨 보드에서 설치하고, 설정 화면의 두 권한 버튼으로 허용합니다.
3. 보드가 같은 망의 서버를 스스로 찾습니다. 못 찾으면 설정 화면이 뜨니 서버 주소(예: `192.168.0.10:8090`), 화면 번호, 글자 크기 배율(%)을 넣고 저장합니다. adb로는 `--es server`, `--ei screen`, `--ei zoom` 인텐트 값으로도 넣을 수 있습니다(ADB가 켜져 있을 때만 받음). 설정 화면에서는 화면 방향과 밝기도 바꿉니다.

### 보드 앱 업데이트

보드는 인터넷이 아니라 매장 서버(POS기)에서만 새 버전을 받습니다. 그래서 인터넷이 끊긴 매장에서도 보드 쪽은 영향이 없습니다.

1. `build.sh`가 만든 `build/updates/`의 두 파일(`board-app.json`, `menuboard-player-<버전코드>.apk`)을 서버의 `pb_public/updates/`에 넣습니다. `board-app.json` 예: `{"versionCode":2,"versionName":"1.1","apk":"menuboard-player-2.apk","sha256":"…"}`
2. 보드는 6시간마다 확인만 해 두고(손님 앞에 설치 창이 뜨지 않게), 설정 화면에 ‘새 버전이 있습니다’를 보여 줍니다. ‘업데이트 확인·설치’를 누르면 받아서 sha256을 맞춰 본 뒤 설치 확인 창을 띄우고, 리모컨으로 ‘설치’를 누르면 바뀐 뒤 메뉴판이 다시 뜹니다.
3. 서명이 다르거나 버전이 낮거나 파일이 깨졌으면 설치하지 않고 지금 버전이 그대로 남습니다.

POS기가 POSWING 업데이트 서버에서 정품 인증 기기별 토큰으로 이 두 파일을 받아 `pb_public/updates/`에 넣는 부분은 서버 쪽 업데이트 작업입니다(아직 없음). 그 전까지는 위 1번을 손으로 합니다.

`board-app/testpage/`는 서버 없이 보드 앱 동작을 보는 시험 페이지입니다.

## TV 원격 관리 (천장에 붙은 TV를 POS기에서 손보기)

POS기에서 `http://127.0.0.1:8090/devices.html`을 엽니다(메뉴 수정 화면과 같은 계정). TV의 메뉴판 앱은 매장 서버에 스스로 등록하고 15초마다 지금 설정을 알려 오므로, 목록에 저절로 나타납니다. 인터넷 없이 매장 안에서만 동작합니다.

- **설정 바꾸기**: 이름, 화면 번호, 글자 배율, 화면 방향(가로·세로·뒤집기), 밝기, 서버 주소. 15초 안팎 뒤 TV에 반영됩니다. 서버 주소는 TV가 새 주소에 실제로 붙어 본 뒤에만 바꾸고, 못 붙으면 그대로 두고 목록에 알림을 띄웁니다.
  - 화면 방향은 안드로이드 화면 회전 대신 앱이 화면을 직접 돌립니다(센서 없는 HDMI 보드는 회전 요청을 무시하는 경우가 많아서).
  - 밝기는 화면 위에 검은 막을 덮는 방식입니다. HDMI로 연결된 TV의 백라이트는 앱이 바꿀 수 없습니다.
- **메뉴판 앱 다시 켜기**: 앱만 다시 켭니다. 보드 전체 재부팅은 보드 펌웨어 시스템 서명이 있어야 해서 1차에는 없습니다.
- **지금 화면 보기**: TV가 지금 화면을 찍어 올립니다(가로 1280 이하 JPEG, 마지막 한 장만 보관).
- **A/S 연결(네트워크 ADB)**: 평소에는 잠겨 있고, A/S 관리자 계정(설치 때 만든 관리자)으로만 열며 누른 때부터 30분(최대 60분)만 열립니다. 사장님 계정으로는 잠그기만 됩니다. 관리자 비밀번호가 매장 와이파이로 암호화 없이 가지 않게, 여는 것은 POS기에서(`http://127.0.0.1:8090/devices.html`) 합니다. 시간이 지나면 서버에 붙지 못해도 TV가 스스로 잠급니다.
  - 설치 bat이 `WRITE_SECURE_SETTINGS` 권한을 줘야 동작합니다. **설치가 끝나면 그 TV의 adb는 잠기니**, 다시 adb로 붙으려면 여기서 먼저 엽니다.
  - 포트(보통 5555)는 보드 펌웨어 설정을 따릅니다. **출고 펌웨어는 ADB 인증(`ro.adb.secure=1`)을 켜 두어야 합니다.** 인증이 꺼진 펌웨어는 열려 있는 동안 같은 망의 누구나 TV를 조작할 수 있습니다.
- **목록에서 지우기**: 그 TV는 다음 보고 때 새로 등록되어 다시 나타납니다. 모르는 TV를 치울 때 씁니다.

서버 쪽 코드는 `server/pb_hooks/devices.pb.js`(+ `devices_lib.js`), 저장 칸은 `pb_migrations/1795000500_devices.js`, 검사는 `node check_devices.js`(임시 서버 127.0.0.1:8093)입니다.

### USB 설정 파일 (현장 비상용)

TV가 서버에 붙지 못해 원격으로 손볼 수 없을 때 씁니다. USB 메모리 맨 위에 `menuboard.txt`를 두고 TV(보드)에 꽂으면 몇 초 안에 적용되고 화면 아래에 결과가 잠깐 뜹니다. 같은 내용은 한 번만 적용합니다. 파일은 `devices.html` 아래쪽에서 만들어 내려받을 수 있습니다.

```
server=192.168.0.10:8090
screen=1
zoom=100
rotation=0        # 0 가로, 90·270 세로, 180 뒤집기
brightness=-1     # 10~100, -1 = 기본
as=30             # A/S 연결을 30분 열기(최대 60), 0 = 잠금
restart=yes       # 적용 뒤 메뉴판 앱 다시 켜기
```

필요한 줄만 적으면 됩니다. 안드로이드 11 이상에서 USB 파일을 읽으려면 '모든 파일 접근' 권한이 필요하며, 설치 bat이 허용합니다.

## 저장소에 넣지 않은 것

`dist/`(배포 묶음), `pocketbase.exe`와 PocketBase의 `LICENSE.md`·`CHANGELOG.md`, `pb_data/`(계정과 메뉴 DB), `server/logs/`(서버 로그), `server/AS-관리자-비밀번호.txt`, `.dev-owner`·`.dev-superuser`(개발 계정 비밀번호), `.debug.keystore`, `board-app/build/`, `board-app/shots/`. 자세한 목록은 `.gitignore`에 있습니다.
