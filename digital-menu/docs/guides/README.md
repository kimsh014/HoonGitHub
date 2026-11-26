# 안내서

| 문서 | 누가 | 인쇄본 |
| --- | --- | --- |
| [설치 기사용 안내서](installer-guide.md) | 설치 기사·A/S 기사 | [installer-guide.pdf](pdf/installer-guide.pdf) |
| [사장님용 사용 설명서](owner-guide.md) | 사장님·직원 | [owner-guide.pdf](pdf/owner-guide.pdf) |
| [매장 POS기 설치 안내서(세부 절차)](../install-pos.md) | 설치 기사 | 설치 기사용 안내서에서 링크 |

**[준비 중]** 표시는 아직 시험 중이거나 다음 업데이트로 들어올 기능입니다(번호 키패드 앱, 밖에서 고치는 휴대폰 앱, 오늘만 품절, 휴지통, 직원 계정, "이 TV용 USB 파일 받기"). 기능이 들어오면 이 표시를 지우고 그림을 다시 만듭니다.

## 고치는 법

화면이나 기능이 바뀌면 Markdown을 고치고 아래 순서로 그림과 PDF를 다시 만듭니다(`tools/` 에서).

1. 그림(SVG): `python3 diagrams.py` → `images/*.svg`. SVG를 직접 고치지 말고 `diagrams.py` 를 고칩니다.
2. 화면 캡처: `node make-shots.js ../../../server <임시 폴더>` (PocketBase 실행 파일이 필요하면 `POCKETBASE=경로`, Playwright 필요) → `python3 prepare-images.py <임시 폴더>`. 샘플 매장 '포스윙 카페'를 임시 서버(127.0.0.1:8097)에 넣고 찍으므로 켜 둔 서버는 건드리지 않습니다.
3. PDF: `npm i marked@12 playwright` 후 `node build-pdf.js` → `pdf/*.pdf`. 한글 글꼴(맑은 고딕 또는 Noto Sans CJK)이 있어야 합니다.

`admin.html`, `devices.html`, `reset.html`, `index.html` 을 바꾼 PR은 이 안내서의 화면 캡처도 다시 찍어야 하는지 봅니다.
