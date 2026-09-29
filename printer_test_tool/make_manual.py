"""사용 설명서(manual.html) 생성기.

테스트 케이스 표는 testcases.py 에서 자동으로 만든다 — 프로그램과 설명서가 어긋나지 않도록.
실행: python make_manual.py   (manual.html 을 다시 만든다)
"""
import html
import os

import patterns
from testcases import TC

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "manual.html")

HOW = {"RS232": "RS232", "USB": "USB", "BT": "BT", "ANY": "체크한 통신마다 각각", "ALL": "체크한 통신 함께"}


def e(s):
    return html.escape(str(s))


def tc_rows():
    rows, cat = [], None
    for t in TC:
        if t["cat"] != cat:
            cat = t["cat"]
            rows.append(f'<tr class="cat"><td colspan="5">{e(cat)}</td></tr>')
        run = "수동 확인" if t["action"] is None else HOW[t["channel"]]
        rows.append(
            f'<tr><td class="id">{e(t["id"])}</td><td><b>{e(t["name"])}</b><div class="sub">{e(t["method"])}</div></td>'
            f'<td>{e(run)}</td><td>{e(t["criterion"])}</td><td class="sub">{e(t["guide"])}</td></tr>')
    return "\n".join(rows)


def main():
    pats = ", ".join(e(p) for p in patterns.PATTERNS)
    doc = TEMPLATE.replace("{{TC_ROWS}}", tc_rows()).replace("{{N_TC}}", str(len(TC))).replace("{{PATTERNS}}", pats)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print("manual.html generated")  # ASCII: Windows CI 콘솔 인코딩 대비


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>열전사 프린터 검증 도구 사용 설명서</title>
<style>
:root{--bg:#fff;--fg:#1d2330;--muted:#5b6475;--line:#dfe3ea;--card:#f6f8fb;--acc:#1f4e78;--ok:#1e7b34;--bad:#b3261e;--warn:#8a5a00;--run:#e2efda}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e6e9ef;--muted:#9aa3b2;--line:#2c323c;--card:#1b1f26;--acc:#8cb8e6;--ok:#7fd49a;--bad:#ff8a80;--warn:#ffcc80;--run:#23392a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 "Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:20px;margin:40px 0 10px;padding-top:12px;border-top:2px solid var(--line);color:var(--acc)}
h3{font-size:16px;margin:22px 0 6px}
p,li{max-width:80ch}
.lead{color:var(--muted);margin:0 0 18px}
nav{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 18px;margin:18px 0}
nav ol{margin:0;padding-left:20px;columns:2;column-gap:32px}
a{color:var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin:12px 0}
.note{border-left:4px solid var(--warn);background:var(--card);padding:10px 14px;border-radius:6px;margin:12px 0}
.tip{border-left:4px solid var(--ok);background:var(--card);padding:10px 14px;border-radius:6px;margin:12px 0}
ol.steps{counter-reset:s;list-style:none;padding-left:0}
ol.steps>li{counter-increment:s;position:relative;padding:6px 0 6px 40px}
ol.steps>li::before{content:counter(s);position:absolute;left:0;top:6px;width:28px;height:28px;border-radius:50%;background:var(--acc);color:var(--bg);text-align:center;line-height:28px;font-weight:700;font-size:14px}
kbd,.btn{display:inline-block;border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:0 6px;background:var(--card);font-size:13px;white-space:nowrap}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
th{background:var(--card)}
tr.cat td{background:var(--acc);color:var(--bg);font-weight:700}
td.id{white-space:nowrap;font-weight:700}
.sub{color:var(--muted);font-size:13px}
.tbl-wrap{overflow-x:auto}
.receipt{font-family:Consolas,monospace;background:#fff;color:#111;border:1px dashed #999;width:300px;padding:10px 14px;margin:10px 0;line-height:1.4;font-size:13px}
.receipt .inv{background:#111;color:#fff;padding:0 6px;font-weight:700;font-size:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
@media print{nav{display:none}h2{break-before:page}body{font-size:12px}}
</style>
</head>
<body><div class="wrap">
<h1>열전사 프린터 검증 도구 사용 설명서</h1>
<p class="lead">80mm 열전사 프린터(RS232·USB·Bluetooth)를 여러 대 동시에 시험하는 방법. 처음 쓰는 사람도 순서대로 따라 하면 됩니다.</p>

<nav><b>목차</b><ol>
<li><a href="#s1">준비와 실행</a></li><li><a href="#s2">화면 구성</a></li><li><a href="#s3">프린터 등록·연결</a></li>
<li><a href="#s4">테스트 케이스 실행</a></li><li><a href="#s5">에이징 (여러 대 동시)</a></li><li><a href="#s6">작업 현황과 중지</a></li>
<li><a href="#s7">출력물 읽는 법</a></li><li><a href="#s8">결과 정리 (엑셀·CSV)</a></li><li><a href="#s9">테스트 케이스 전체 목록</a></li>
<li><a href="#s10">문제 해결</a></li></ol></nav>

<h2 id="s1">1. 준비와 실행</h2>
<div class="grid">
<div class="card"><b>준비물</b><ul><li>Windows 10/11 PC 1대</li><li>시험할 프린터 (여러 대 가능)</li><li>RJ45↔DB9 전용 케이블 또는 USB-시리얼 변환기, USB B 케이블</li><li>감열지 충분히, 바코드 스캐너, 스마트폰(QR), 자</li></ul></div>
<div class="card"><b>실행</b><ol><li><code>PrinterTester.exe</code> 를 바탕화면 등 <b>쓰기 가능한 폴더</b>에 복사</li><li>더블클릭. "Windows의 PC 보호"가 뜨면 <span class="btn">추가 정보</span> → <span class="btn">실행</span></li><li>같은 폴더에 <code>logs</code>, <code>results</code>, <code>settings.json</code> 이 생깁니다</li></ol></div>
</div>
<div class="tip"><b>설치 필요 없음:</b> exe 하나에 필요한 것이 모두 들어 있어 <b>파이썬이나 다른 프로그램을 설치하지 않습니다.</b> 레지스트리·시스템 설정도 바꾸지 않으므로 일반 POS 기기에서 그대로 쓸 수 있고, 다 쓰면 폴더째 지우면 끝입니다.</div>
<table><tr><th style="width:34%">POS / PC 의 Windows</th><th>사용할 파일</th></tr>
<tr><td>Windows 10 / 11 (64비트)</td><td><code>PrinterTester-windows</code> 의 PrinterTester.exe</td></tr>
<tr><td>Windows 7 / POSReady 7 / 32비트 Windows</td><td><code>PrinterTester-win7-32bit</code> 의 PrinterTester.exe (64비트 Windows 에서도 실행됨 — 모르면 이것)</td></tr>
</table>
<p class="sub">Windows 버전 확인: <kbd>Windows 키</kbd>+<kbd>R</kbd> → <code>winver</code> 입력 → 확인. 32/64비트는 파일 탐색기에서 '내 PC' 오른쪽 클릭 → 속성 → 시스템 종류.</p>
<ul>
<li>exe 가 있는 폴더에 쓸 수 없는 잠긴 POS 에서는 로그·결과가 자동으로 <code>문서\PrinterTester</code> 에 저장됩니다 (로그 창 첫 줄에 위치 표시).</li>
<li>보안 프로그램(백신·실행 제한 프로그램)이 서명 없는 exe 를 막으면 관리자에게 예외 등록을 요청하세요. USB 메모리에 넣고 거기서 바로 실행해도 됩니다.</li>
</ul>
<div class="note"><b>에이징 전 필수:</b> PC 절전 모드 끄기 (Windows 설정 → 전원 → 절전 "안 함"). 절전에 들어가면 USB·BT 연결이 끊겨 실패로 기록됩니다.</div>

<h2 id="s2">2. 화면 구성</h2>
<table><tr><th style="width:24%">영역</th><th>하는 일</th></tr>
<tr><td><b>1. 프린터 연결</b> 탭</td><td>프린터마다 이름을 붙이고 RS232 / USB / BT 연결을 각각 설정·연결. 빠른 점검.</td></tr>
<tr><td><b>2. 테스트 케이스</b> 탭</td><td>{{N_TC}}개 시험 항목. 프린터와 통신을 골라 <span class="btn">▶ 실행</span> → 출력물 확인 → 판정 저장.</td></tr>
<tr><td><b>3. 에이징</b> 탭</td><td>여러 프린터·통신을 체크해 동시에 연속 인쇄. 대상별 진행 현황 표.</td></tr>
<tr><td><b>4. 패턴 인쇄 / 명령</b> 탭</td><td>패턴 골라 인쇄, 상태·프린터 정보 조회, HEX 명령 직접 전송.</td></tr>
<tr><td><b>작업 현황</b> (화면 아래, 항상 보임)</td><td>지금 실행 중인 모든 작업 — <b>무엇을, 어느 프린터/통신에서, 몇 %까지</b> — 표시. 여기서 <span class="btn">■ 선택 작업 중지</span> · <span class="btn">■ 모두 중지</span>.</td></tr>
<tr><td>로그 (맨 아래)</td><td>전송량·상태 응답 등 자세한 기록. 같은 내용이 logs 폴더 CSV 에도 남습니다.</td></tr>
<tr><td><span class="btn">사용 설명서 (도움말)</span> (오른쪽 위)</td><td>이 문서를 엽니다.</td></tr>
</table>

<h2 id="s3">3. 프린터 등록·연결</h2>
<ol class="steps">
<li><b>공통 설정</b>에 시험자 이름을 넣고, <b>영수증 길이</b>(기본 120mm)를 확인합니다. 모든 출력물이 이 길이로 나옵니다 (속도 시험만 예외).</li>
<li>프린터 칸마다 <b>프린터 이름</b>을 적습니다 (예: <code>샘플A</code>, <code>SN-0001</code>). 이름이 영수증 머리와 결과 파일에 들어가므로 <b>대마다 다르게</b>. 더 필요하면 <span class="btn">+ 프린터 추가</span> (최대 9대).</li>
<li>통신 줄마다 <b>사용</b> 체크 → <b>포트</b> 선택 → 속도·형식·흐름제어를 프린터 설정과 똑같이 맞춥니다. 안 쓰는 통신은 사용 체크를 끕니다.</li>
<li>줄의 <span class="btn">연결</span> (또는 <span class="btn">이 프린터 연결</span> / <span class="btn">전체 연결</span>) → 상태가 <b>● 연결됨</b> 이 되면 성공.</li>
<li><span class="btn">▶ 빠른 점검</span> — 연결 → 프린터 정보(FW) → 상태 → 확인 영수증을 통신마다 차례로 수행. 응답한 FW 버전이 FW 칸에 자동 입력됩니다.</li>
</ol>
<h3>어느 포트가 어느 통신인가?</h3>
<table><tr><th>통신</th><th>포트 목록에 보이는 이름</th><th>연결 방식</th></tr>
<tr><td>RS232 (RJ45)</td><td><code>COMx — USB Serial Port</code> / <code>Prolific</code> / <code>CH340</code> 등 (변환기) 또는 <code>COM1 — 통신 포트</code></td><td>COM</td></tr>
<tr><td>USB B</td><td>가상 COM 이면 <code>COMx — USB 직렬 장치</code>. Windows 에 프린터로 설치되면 COM 목록에 없음</td><td>COM 또는 WinPrinter</td></tr>
<tr><td>Bluetooth</td><td>PC 와 페어링 후 <code>COMx — Bluetooth 링크를 통한 표준 직렬</code> (2개면 <b>발신</b> 쪽)</td><td>COM</td></tr>
</table>
<div class="tip"><b>찾는 요령:</b> 케이블을 뽑고 <span class="btn">포트 목록 새로고침</span> → 다시 꽂고 새로고침. 새로 생긴 COM 이 그 장치입니다. 장치 관리자 → 포트(COM &amp; LPT)에서도 확인할 수 있습니다.</div>
<div class="note">USB 를 <b>WinPrinter</b>(Windows 프린터)로 연결하면 상태 조회·재연결 자동 감지·프린터 정보가 안 됩니다. 해당 항목은 출력물로 판정하거나 N/A 처리하세요.</div>

<h2 id="s4">4. 테스트 케이스 실행</h2>
<ol class="steps">
<li><b>2. 테스트 케이스</b> 탭 왼쪽 목록에서 항목 선택 (결과 칸 색: <span style="color:var(--ok)">Pass 초록</span> / <span style="color:var(--bad)">Fail 빨강</span>).</li>
<li>오른쪽 <b>실행 대상</b>에서 <b>프린터</b>를 고르고, 시험할 <b>통신(RS232/USB/BT)</b>을 체크합니다. <b>●</b> 표시는 연결된 통신. 항목마다 알맞은 통신이 자동으로 체크됩니다.</li>
<li><span class="btn">▶ 실행</span>. 체크한 통신마다 <b>따로</b> 인쇄됩니다 (영수증 머리에 프린터 이름·통신 표시). 진행 상황은 화면 아래 <b>작업 현황</b>.</li>
<li>안내 문구대로 조작 (예: 케이블 분리, 커버 열기) 후 출력물을 확인합니다.</li>
<li>자동 판정이 가능한 항목은 결과가 미리 선택됩니다. 확인하고 필요하면 바꾼 뒤 <span class="btn">결과 저장</span> 또는 <span class="btn">저장 후 다음 ▶</span>. 실행 결과는 비고에 자동으로 쌓입니다.</li>
</ol>
<div class="tip"><b>여러 대 병행:</b> 프린터 A 에서 시험이 도는 동안 프린터를 B 로 바꿔 다른 시험을 실행할 수 있습니다. 같은 프린터라도 <b>다른 통신</b>이면 동시에 실행됩니다. 같은 통신이 이미 작업 중이면 안내창이 뜨고 작업 현황에서 해당 작업이 표시됩니다.</div>

<h2 id="s5">5. 에이징 (여러 대 동시)</h2>
<ol class="steps">
<li>1번 탭에서 프린터들을 등록·연결해 둡니다.</li>
<li><b>3. 에이징</b> 탭 표에 '사용' 체크된 모든 프린터·통신이 나옵니다. 돌릴 줄을 <b>클릭해 ☑</b> 로 만듭니다 (<span class="btn">전체 체크</span> 가능).</li>
<li>패턴(기본 <b>영수증</b>), 시간(예: 12), 간격(초)을 정합니다. 장수와 시간이 모두 0이면 중지할 때까지 계속.</li>
<li>먼저 <b>대상당 장수 5, 시간 0</b> 으로 짧게 돌려 모두 인쇄되는지 확인 → 이상 없으면 장수 0, 시간 12 로 다시 시작.</li>
<li><span class="btn">▶ 체크한 대상 시작</span>. 표의 상태·경과·전송·정상·실패·일시정지·재연결이 1초마다 갱신됩니다. 실패가 생기면 줄이 빨개집니다.</li>
</ol>
<ul>
<li>대상마다 <b>독립 실행</b> — 한 대가 실패·일시정지해도 나머지는 계속.</li>
<li>용지가 떨어지면 해당 대상만 <b>일시정지</b> → 용지를 넣으면 자동 재개 (실패로 세지 않음).</li>
<li>연결이 끊기면 자동 재연결을 시도합니다 (자동 재연결 옵션).</li>
<li>영수증마다 <b>순번</b>이 찍힙니다. 아침에 순번이 빠진 곳이 없는지 보세요.</li>
<li>로그 CSV: <code>logs\날짜_aging_기본_프린터명_통신.csv</code> — 결과 열이 FAIL / ERROR / NORESP 인 행이 문제 기록입니다. 에이징 중에 엑셀로 열어 봐도 됩니다.</li>
<li>끝나면 요약이 해당 프린터의 <b>X04</b> 비고에 자동 기록됩니다.</li>
</ul>

<h2 id="s6">6. 작업 현황과 중지</h2>
<p>실행한 모든 것(시험, 인쇄, 빠른 점검, 에이징)은 화면 아래 <b>작업 현황</b>에 한 줄씩 나타납니다. 초록 줄이 진행 중입니다.</p>
<table><tr><th>열</th><th>뜻</th></tr>
<tr><td>작업</td><td>무엇을 하고 있는지 (예: <code>B04 오토커터</code>, <code>에이징</code>)</td></tr>
<tr><td>대상</td><td>어느 프린터/통신에서 (예: <code>샘플A/RS232</code>)</td></tr>
<tr><td>진행</td><td>몇 장·몇 %까지 (에이징은 전송/정상/실패 수)</td></tr>
<tr><td>최근 내용</td><td>지금 하는 동작이나 해야 할 일 (예: "지금 연결됨: 분리하세요")</td></tr>
</table>
<ul>
<li><b>하나만 멈추기:</b> 작업 현황에서 그 줄 클릭 → <span class="btn">■ 선택 작업 중지</span></li>
<li><b>전부 멈추기:</b> <span class="btn">■ 모두 중지</span> (에이징 포함)</li>
<li>에이징 탭의 <span class="btn">■ 체크한 대상 중지</span> 로도 멈출 수 있습니다.</li>
<li>중지는 <b>지금 보내는 영수증 한 장을 마치고</b> 멈춥니다 (상태가 '중지 중…' → '중지됨').</li>
<li>"<i>○○ 는 지금 [작업] 작업 중입니다</i>" 가 뜨면: 그 통신에서 다른 작업이 돌고 있다는 뜻입니다. 작업 현황에 해당 줄이 선택돼 있으니 끝날 때까지 기다리거나 중지 후 다시 실행하세요.</li>
</ul>

<h2 id="s7">7. 출력물 읽는 법</h2>
<div class="grid">
<div><div class="receipt"><div style="text-align:center"><span class="inv">&nbsp;샘플A&nbsp;</span><br><b style="font-size:16px">[ RS232 ]</b><br><b>영수증 시험</b><br>#000012 2026-09-29 21:03:44</div>------------------------------------<br>아메리카노 &nbsp;&nbsp;&nbsp;&nbsp; 2 &nbsp; 9,000<br>…<br><div style="text-align:center">||||| ||| |||| (바코드)<br>▣ (QR)</div></div></div>
<div><ul>
<li><b>검은 바탕 이름</b> = 프린터 이름, <b>[ ]</b> = 통신 방식 → 여러 대·여러 통신 출력물을 섞여도 구분</li>
<li><b>#순번</b> = 에이징·연속 인쇄 순번 (빠진 번호 = 누락)</li>
<li>모든 출력물은 설정한 <b>영수증 길이</b>로 나옵니다 → 길이가 들쭉날쭉하면 급지 이상</li>
</ul></div></div>
<table><tr><th>패턴</th><th>보는 곳</th></tr>
<tr><td>헤드 도트 체크</td><td>검정 띠에 <b>흰 세로줄</b> = 해당 도트 불량</td></tr>
<tr><td>급지 눈금자</td><td>세로 긴 선 사이 = 10mm (자로 측정, ±0.5mm), 가로 눈금으로 인쇄 폭·좌우 여백</td></tr>
<tr><td>컷 위치</td><td>굵은 기준선~절단면 거리 = 헤드-커터 거리 사양과 비교</td></tr>
<tr><td>농도</td><td>0~100% 막대 단계 구분. 프린터 농도 설정을 바꿔 반복 비교</td></tr>
<tr><td>1D 바코드 / QR 코드</td><td>스캐너·스마트폰으로 모두 읽히면 Pass</td></tr>
<tr><td>대용량 이미지</td><td>맨 끝 <code>END #n</code> 줄이 보이면 데이터 누락 없음</td></tr>
<tr><td>동시 인쇄 (X02)</td><td>모든 줄에 <code>[프린터 통신]</code> 표시 — 한 영수증 안에 다른 이름이 섞이면 Fail</td></tr>
</table>
<p class="sub">사용 가능한 패턴: {{PATTERNS}}</p>

<h2 id="s8">8. 결과 정리</h2>
<ul>
<li><span class="btn">계획표 엑셀에 결과 반영</span> — 검증 계획표(.xlsx)를 고르면 <b>프린터마다 새 파일</b>(<code>계획표_결과_샘플A_…xlsx</code>)을 만들어 결과·시험자·시험일·FW·결함ID·비고를 채웁니다. 원본은 그대로.</li>
<li><span class="btn">CSV 내보내기</span> — 모든 프린터의 결과를 한 파일로 (<code>results</code> 폴더).</li>
<li>E로 시작하는 추가 시험은 계획표에 없으므로 CSV 에만 나옵니다.</li>
</ul>

<h2 id="s9">9. 테스트 케이스 전체 목록 ({{N_TC}}개)</h2>
<p class="sub">실행 = 프로그램이 어떤 통신으로 실행하는지. "수동 확인"은 안내만 보고 직접 확인 후 판정.</p>
<div class="tbl-wrap"><table>
<tr><th style="width:6%">ID</th><th style="width:26%">항목 / 방법</th><th style="width:13%">실행</th><th style="width:22%">합격 기준</th><th>안내</th></tr>
{{TC_ROWS}}
</table></div>

<h2 id="s10">10. 문제 해결</h2>
<table><tr><th style="width:32%">증상</th><th>조치</th></tr>
<tr><td>포트 목록에 COM 이 안 보임</td><td>케이블·전원 확인 → <span class="btn">포트 목록 새로고침</span>. USB-시리얼 변환기는 드라이버(FTDI/Prolific/CH340) 설치. BT 는 Windows 설정에서 먼저 페어링.</td></tr>
<tr><td>연결 실패 "Access is denied / 액세스 거부"</td><td>다른 프로그램(터미널, 드라이버 유틸)이 그 COM 을 쓰고 있음 → 닫고 다시 연결. 이 프로그램 안의 다른 프린터 줄이 같은 포트를 쓰는지도 확인.</td></tr>
<tr><td>글자가 깨져 나옴</td><td>속도·형식·흐름제어를 프린터 설정과 동일하게. 한글만 깨지면 공통 설정의 '한글 모드' 끄기 또는 인코딩 변경.</td></tr>
<tr><td>상태 응답 없음</td><td>단방향 연결이거나 흐름제어 불일치. RS232 는 RTS/CTS 케이블 결선 확인. WinPrinter 연결은 원래 조회 불가.</td></tr>
<tr><td>BT 연결이 오래 걸림</td><td>BT 가상 COM 은 열 때 무선 연결을 맺느라 수 초 걸립니다. 거리 1m 안에서 먼저 연결.</td></tr>
<tr><td>에이징이 '일시정지'</td><td>용지 없음·커버 열림. 조치하면 자동 재개. 로그에 RESUME 기록.</td></tr>
<tr><td>"작업 중입니다" 안내</td><td><a href="#s6">6. 작업 현황과 중지</a> 참고.</td></tr>
<tr><td>프린터 정보 응답 없음</td><td>GS I 명령을 지원하지 않는 모델. FW 칸에 직접 입력.</td></tr>
</table>
<p class="sub">문의 시 화면 아래 로그 내용과 logs 폴더의 CSV 를 함께 보내 주세요.</p>
</div></body></html>
"""

if __name__ == "__main__":
    main()
