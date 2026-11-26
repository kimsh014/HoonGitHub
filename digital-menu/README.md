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
  - `pb_public/api.js`: 화면이 서버를 부르는 유일한 곳(로그인, 메뉴·구역·화면 저장, 품절, 번호 호출, `getBoard`, `onBoardChange` 실시간 구독).
  - `pb_public/board.js`: 메뉴판 화면 갱신 흐름. 주소 `/?screen=화면번호` (선택 `&zoom=글자배율%`, `&refresh=초`(기본 300), `&store=매장번호`(서버에 매장이 여럿일 때)). 데이터를 받으면 `index.html`의 `renderBoard(board, screenNo)`를 부릅니다.
  - `pb_public/index.html`: 메뉴판 화면(사진 격자 · 목록 + 큰 사진 · 홍보 · 번호 전용, 번호 띠). 요구사항은 `../ui-prompt.md`, 화면 모습은 `docs/screens/`에 있습니다.
  - `pb_public/admin.html`: 동작 확인용 시안입니다. UI 담당이 바꿀 수정 화면입니다.
- **보드 앱 (`board-app/`)**: 메뉴판 주소를 전체 화면 WebView로 띄우는 안드로이드 앱(`com.menuboard.player`, minSdk 30). 홈 앱으로 지정하면 부팅 때 바로 뜹니다. 설정 화면에서 서버 주소, 화면 번호, 글자 크기 배율을 넣습니다. `/api/health`가 응답하지 않으면 마지막으로 저장한 화면을 띄우고 15초마다 다시 확인합니다.
- **`ui-prompt.md`**: 화면(UI) 작업 요구사항과 화면이 받는 데이터 계약.
- **`index.html`** (이 폴더 맨 위): 서버 없이 메뉴를 코드에 적어 띄우는 초기 한 장짜리 메뉴판 시안.

> 키오스크 연동 코드는 아직 이 폴더에 없습니다. 현재 POS와 연결되는 부분은 POS PC에서 이 서버를 돌리는 것까지입니다.

## 서버 실행 (POS PC, Windows)

1. [PocketBase](https://github.com/pocketbase/pocketbase/releases) Windows 실행 파일(작업 당시 v0.40.6)을 받아 `server/pocketbase.exe`로 둡니다. 실행 파일은 저장소에 넣지 않습니다.
2. `server/start-server.bat`을 더블클릭합니다. 다음 명령으로 `0.0.0.0:8090`에서 켜지고, 창에 보드에 넣을 매장 네트워크 주소가 나옵니다. 창을 닫으면 서버가 꺼집니다.
   ```
   pocketbase.exe serve --http 0.0.0.0:8090 --dir pb_data --migrationsDir pb_migrations --hooksDir pb_hooks --publicDir pb_public
   ```
   처음 켤 때 Windows 방화벽이 물으면 '허용'을 누릅니다.
3. 수정 화면: `http://127.0.0.1:8090/admin.html`. 빈 서버에서는 여기서 첫 매장과 계정을 만듭니다.
4. 메뉴판 화면: `http://127.0.0.1:8090/?screen=1&zoom=100`

### 검사 스크립트 (서버가 127.0.0.1:8090에서 돌고 있어야 함)

- `python seed_and_check.py`: 샘플 매장 '우리카페'와 메뉴를 넣고 접근 규칙을 검사합니다. 개발용 계정을 `server/.dev-owner`에 만들어 쓰고, `server/.dev-superuser`(PocketBase 관리자 이메일과 비밀번호, 한 줄씩)가 필요합니다. 두 파일은 커밋하지 않습니다.
- `node check_api.js`: `api.js`의 계약 함수 전부를 실제 서버에 대고 검사합니다 (`seed_and_check.py`를 먼저 실행).
- `node check_board.js`: `board.js` 갱신 흐름을 서버 없이 검사합니다.
- `node check_screens.js [shots]`: 메뉴판 화면을 서버 없이 가짜 데이터로 띄워 1920×1080, 3840×2160, 세로 1080×1920과 글자 배율 100·150%에서 잘리는 글이 없는지 검사합니다. `shots`를 붙이면 `server/shots/`에 스크린샷을 남깁니다(Playwright와 Chromium 필요, 서버는 필요 없음).

## 보드 앱 빌드와 설치

1. **빌드** (Git Bash, Gradle 없이 Android SDK 도구만 사용): `board-app/build.sh`
   - 필요: Android SDK build-tools 36.0.0, platforms/android-37.0, JDK(기본값 Android Studio의 `jbr`). 경로는 `ANDROID_SDK`, `JDK_HOME`으로 바꿀 수 있습니다.
   - 결과: `board-app/build/menuboard-player.apk`. 서명 키 `.debug.keystore`가 없으면 디버그 키를 새로 만듭니다(출시용 키는 별도).
2. **설치**: `menuboard-player.apk`를 `install-board-app.bat`과 같은 폴더에 두고, 보드를 USB(또는 adb 네트워크)로 연결한 PC에서 더블클릭합니다. adb가 없으면 APK를 USB 메모리로 옮겨 보드에서 설치해도 됩니다.
3. 보드 설정 화면에 서버 주소(예: `192.168.0.10:8090`), 화면 번호, 글자 크기 배율(%)을 넣고 저장합니다. adb로는 `--es server`, `--ei screen`, `--ei zoom` 인텐트 값으로도 넣을 수 있습니다.

`board-app/testpage/`는 서버 없이 보드 앱 동작을 보는 시험 페이지입니다.

## 저장소에 넣지 않은 것

`dist/`(배포 묶음), `pocketbase.exe`와 PocketBase의 `LICENSE.md`·`CHANGELOG.md`, `pb_data/`(계정과 메뉴 DB), `.dev-owner`·`.dev-superuser`(개발 계정 비밀번호), `.debug.keystore`, `board-app/build/`, `board-app/shots/`. 자세한 목록은 `.gitignore`에 있습니다.
