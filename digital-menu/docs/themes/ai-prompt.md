# AI에 붙여 넣을 작업 지시: 메뉴판 테마 만들기

> UI 담당자용. 아래 줄부터 끝까지 통째로 Claude나 GPT에 붙여 넣고, 맨 아래 "이번에 만들 테마"만 채웁니다.
> 이 파일은 `digital-menu/docs/themes/` 안내의 일부입니다. 테마 값 목록이 바뀌면 개발팀이 이 파일도 함께 고칩니다.

---

나는 매장 천장 TV에 띄우는 전자메뉴판의 UI(디자인) 담당이다. 너는 나를 도와 **테마 파일(CSS) 하나**를 만든다.

## 배경
- 메뉴판 화면은 안드로이드 보드(RK3568, 안드로이드 11~14)의 WebView가 그린다. 35~66인치, 1920×1080부터 4K(3840×2160), 세로(1080×1920)로도 건다.
- 화면 종류: 사진 격자형, 목록 + 큰 사진형, 홍보 화면(이미지 + 문구 두 줄), 번호 전용 화면(가장 최근 번호를 아주 크게).
  메뉴·홍보 화면 아래에는 "번호 띠"(손님이 받으러 올 준비된 번호 한 줄, 가장 최근 번호를 강조)가 붙을 수 있다.
  이 매장들은 **번호 호출**이 핵심이다: 주문 → 번호표 → 준비되면 TV에 번호. 멀리서도 가장 최근 번호가 한눈에 보여야 한다.
- 배치(칸 수, 크기, 넘치면 줄이기, 4K·세로 대응, 품절 흐림)는 개발팀이 `index.html`에 이미 만들었다. 색과 모양은 모두 CSS 변수(테마 값)로 쓴다.
- 사장님이 고른 브랜드 색은 `var(--brand)`, 그 위 글자색은 `var(--on-brand)`(화면이 흰색·검은색 중 잘 보이는 쪽을 자동으로 고름)로 쓸 수 있다. 사장님은 아무 색이나 고를 수 있으니 브랜드 색이 빨강·노랑·남색 어느 것이어도 어울려야 한다.

## 규칙 (어기면 검사 스크립트가 실패한다)
1. 결과물은 `server/pb_public/themes/<이름>.css` 파일 하나와 `themes/list.json`에 더할 한 줄이다. 이름은 영어 소문자·숫자·`-`만.
2. 파일 안에는 주석과 `:root { --값: …; }` 한 덩어리만 쓴다. `.card {…}` 같은 다른 선택자, `@import`, `@font-face`, `@media`는 쓰지 않는다.
3. 아래 "테마 값" 목록에 있는 변수만 바꾼다. `--brand`, `--on-brand`, `--zoom`, `--fit`, `--pad`는 바꾸지 않는다. 바꾸지 않은 값은 기본값을 쓴다.
4. 크기는 `em`·`rem`만 쓴다(`px` 금지). 글자 크기·여백·위치는 테마 값에 없으므로 바꿀 수 없다.
5. `url()`은 `themes/` 폴더 안의 그림 파일만(예: `url(dots.png)`, 한 장 300KB 이하). 바깥 인터넷 주소의 그림·글꼴, `\` 이스케이프는 쓰지 않는다(매장 인터넷이 끊겨도 보여야 한다).
   함수는 var, rgb, rgba, hsl, hsla, linear-gradient, radial-gradient, repeating-linear-gradient, repeating-radial-gradient, url, calc만 쓴다.
6. 글꼴: 보드에는 Noto Sans CJK만 있고 확실한 굵기는 400과 700뿐이다. 다른 글꼴이 필요하면 만들지 말고 나에게 "개발팀 요청"으로 알려 준다.
7. 글자색과 바탕색이 둘 다 `#rrggbb` 고정 색인 짝(--ink/--base, --ink/--panel, --top-ink/--top-bg, --title-ink/--title-bg, --band-ink/--band-bg, --call-ink/--call-bg, --sold-ink/--sold-bg, NEW·BEST 딱지)은 명도 대비 4.5 이상.
8. 밝은 바탕 테마면 `--ink`, `--muted`, `--veil`(매장 배경 사진 위 막), `--band-*`, `--hot`·`--ice`도 어두운 글에 맞게 함께 바꾼다.
9. `index.html`, `api.js`, `board.js`, `admin.html`과 다른 폴더의 파일은 고치지 않는다. 배치를 바꾸고 싶으면 코드를 쓰지 말고 "개발팀 요청"으로 정리해 준다.

## 테마 값 (index.html에 있는 기본값 그대로)
```css
  /* ── 테마 값: themes/*.css는 이 블록의 변수만 바꾼다 (기본값 = 테마 없음) ── */
  --font:"Pretendard","Noto Sans KR","Noto Sans CJK KR","Malgun Gothic",sans-serif;
  --weight:700;              /* 보드(안드로이드)에 기본으로 있는 굵기는 400과 700뿐 */
  --ink:#fff;                /* 기본 글자 */
  --muted:rgba(255,255,255,.72); /* 보조 글자(안내, 이름표) */
  --base:#0b0b0d;            /* 바탕색 */
  --veil:linear-gradient(rgba(8,8,10,.5),rgba(8,8,10,.78)); /* 매장 배경 사진 위에 덮는 막 (글이 잘 보이게) */
  --glow:linear-gradient(160deg,var(--brand),transparent 50%); /* 막 위의 빛·무늬 (background 값) */
  --glow-opacity:.3;
  --panel:rgba(12,12,14,.74); /* 카드·목록 상자 바탕 */
  --line:rgba(255,255,255,.16);
  --radius:.8em;             /* 카드·상자 모서리 */
  --card-border:.06em solid var(--line);
  --card-shadow:none;
  --photo-bg:#000;           /* 사진 뒤 바탕 (사진 비율이 달라 남는 곳) */
  --top-bg:var(--brand);     /* 맨 위 매장 이름 띠 */
  --top-ink:var(--on-brand);
  --top-line:none;           /* 띠 아래 선 (border 값) */
  --top-shadow:0 .2rem .8rem rgba(0,0,0,.35);
  --top-align:flex-start;    /* 매장 이름 위치: flex-start(왼쪽) · center */
  --title-bg:var(--brand);   /* 구역 제목 띠 */
  --title-ink:var(--on-brand);
  --title-radius:0 2em 2em 0;
  --title-shadow:-.35em 0 0 rgba(255,255,255,.85);
  --badge-new-bg:#fff; --badge-new-ink:var(--brand);
  --badge-best-bg:#ffc928; --badge-best-ink:#2a1d00;
  --hot:#ff8a65; --ice:#7cc7ff; /* 가격 이름표 HOT·ICE 색 */
  --sold-bg:#000; --sold-ink:#fff; --sold-line:rgba(255,255,255,.8);
  --caption-bg:linear-gradient(transparent,rgba(0,0,0,.85)); --caption-ink:#fff; /* 목록형 큰 사진 위 이름 */
  --promo-shadow:0 .1em .6em rgba(0,0,0,.6); /* 홍보 문구 그림자 */
  --band-bg:rgba(0,0,0,.82); /* 번호 띠 */
  --band-ink:#fff; --band-muted:rgba(255,255,255,.72);
  --band-line:var(--brand);
  --call-bg:var(--brand);    /* 가장 최근 번호 강조 (번호 띠·번호 전용 화면) */
  --call-ink:var(--on-brand);
  /* ── 테마 값 끝 ── */
```

## 예시: 디저트 테마 (themes/dessert.css)
```css
/* 테마: 디저트 (파스텔) — 연분홍 크림 바탕, 흰 카드에 부드러운 그림자, 가운데 정렬 매장 이름.
   만든 곳: UI팀 시작 키트(2026-11). 이 파일은 :root의 테마 값만 바꾼다. 바꿀 수 있는 값은 docs/themes/README.md */
:root{
  --ink:#4a2a33;
  --muted:rgba(74,42,51,.66);
  --base:#fdf1f3;
  --veil:linear-gradient(rgba(253,241,243,.86),rgba(250,232,236,.93));
  --glow:radial-gradient(60% 50% at 88% 8%,var(--brand),transparent 70%);
  --glow-opacity:.18;
  --panel:rgba(255,255,255,.86);
  --line:rgba(74,42,51,.14);
  --radius:1.5em;
  --card-border:.06em solid rgba(74,42,51,.08);
  --card-shadow:0 .4em 1.2em rgba(150,80,100,.16);
  --photo-bg:#f7e3e7;
  --top-bg:rgba(255,255,255,.8);
  --top-ink:#4a2a33;
  --top-line:.2rem solid var(--brand);
  --top-shadow:0 .2rem .8rem rgba(150,80,100,.12);
  --top-align:center;
  --title-bg:var(--brand);
  --title-ink:var(--on-brand);
  --title-radius:2em;
  --title-shadow:none;
  --badge-new-bg:var(--brand); --badge-new-ink:var(--on-brand);
  --badge-best-bg:#ffd166; --badge-best-ink:#4a2a33;
  --hot:#d1495b; --ice:#2f80c2;
  --sold-bg:#4a2a33; --sold-ink:#fff; --sold-line:#4a2a33;
  --caption-bg:linear-gradient(transparent,rgba(74,42,51,.78)); --caption-ink:#fff;
  --promo-shadow:none;
  --band-bg:rgba(255,255,255,.94);
  --band-ink:#4a2a33; --band-muted:rgba(74,42,51,.66);
  --band-line:var(--brand);
  --call-bg:var(--brand); --call-ink:var(--on-brand);
}
```
list.json의 한 줄 예시:
```json
{ "id": "dessert", "name": "디저트 · 파스텔", "kind": "light", "sampleStore": "우리디저트", "sampleBrand": "#e05780",
  "desc": "연분홍 크림 바탕, 흰 카드와 부드러운 그림자, 가운데 매장 이름. 디저트·빙수·아이스크림" }
```

## 일하는 방식
1. 먼저 색 견본표(바탕, 상자, 글, 보조 글, 번호 띠, 최근 번호, 딱지, HOT/ICE)와 한 줄 설명을 보여 주고 내 확인을 받는다.
2. 확인되면 테마 파일 전체와 list.json 한 줄을 준다.
3. 내가 돌릴 검사와 볼 것을 알려 준다:
   - `node check_themes.js` (규칙·대비), `node check_screens.js shots <이름>` (잘림 검사와 스크린샷, server/shots/<이름>/)
   - 개발 서버에서 `http://127.0.0.1:8090/?screen=1&theme=<이름>` (screen 1~4, `&zoom=150`도)
4. 내가 스크린샷이나 검사 결과를 붙이면 그걸 보고 고친다. 대비가 모자라다는 실패가 나오면 바탕은 두고 글자색부터 바꾼다.

## 완료 기준
- `check_themes.js`와 `check_screens.js`가 모두 통과
- 번호 띠의 가장 최근 번호, 번호 전용 화면의 큰 번호가 멀리서 한눈에 보인다
- 번호가 없을 때의 번호 화면(매장 이름 + 안내), 품절 메뉴, 매장 배경 사진이 있을 때·없을 때 모두 글이 읽힌다
- 브랜드 색을 빨강·노랑·남색으로 바꿔도 어울린다

## 이번에 만들 테마
- 업종:
- 분위기·참고(사진이나 단어):
- 밝은 바탕 / 어두운 바탕:
- 이름(영어, 예: chicken):
