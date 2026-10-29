# -*- coding: utf-8 -*-
"""시험 계획표 엑셀 만들기 — testcases.py 의 145항목에서 생성 (프로그램과 계획표가 항상 같은 목록).

실행: python make_plan.py [출력파일]   (기본 TestPlan.xlsx)
"""
import sys

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT = sys.argv[1] if len(sys.argv) > 1 else "TestPlan.xlsx"
FONT = "맑은 고딕"
F = lambda **k: Font(name=FONT, size=k.pop("size", 10), **k)
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="1F2A44")
INPUT = PatternFill("solid", fgColor="FFF2CC")
WRAP = Alignment(wrap_text=True, vertical="center")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
RESULTS = ["Pass", "Fail", "보류", "N/A"]
POS = "PrinterTestPOS"
PT = "PrinterTester"

from testcases import TC  # noqa: E402

ITEMS = [(t["part"], t["cat"], t["id"], t["name"], t["method"], t["criterion"], t["why"],
          t["tool"] + ("" if t["action"] is None else "  [실행]"), t["prio"]) for t in TC]

PARTS = list(dict.fromkeys(it[0] for it in ITEMS))
wb = Workbook()
CL = "체크리스트"
n = len(ITEMS)
first, last = 4, 4 + n - 1
rng = lambda col: f"'{CL}'!${col}${first}:${col}${last}"

# ---------------- 요약 ----------------
ws = wb.active
ws.title = "요약"
ws["A1"] = "80mm 열전사 프린터 시험 리스트 — 기능 · 시리얼(RS232) · 블루투스"
ws["A1"].font = F(size=16, bold=True)
ws["A2"] = "노란 칸만 입력하면 이 시트의 숫자는 자동으로 계산됩니다."
ws["A2"].font = F(color="595959")
ws["A4"] = "사용 방법"
ws["A4"].font = F(size=12, bold=True)
for i, t in enumerate([
    "1. '체크리스트' 시트에서 시험한 항목의 [완료] 칸에 ✔, [결과] 칸에 Pass / Fail / 보류 / N/A 를 고릅니다.",
    "2. [파트] 열의 필터로 기능 / 시리얼 / 블루투스 를 나눠 볼 수 있습니다.",
    "3. Fail 이면 '결함 목록' 시트에 한 줄 추가하고 결함 ID 를 체크리스트 [결함ID] 칸에 적습니다.",
    "4. 블루투스 거리·세기는 '거리·세기 측정' 시트에 조건별로 기록합니다 (평균·판정 자동).",
], start=5):
    ws.cell(i, 1, t).font = F()

ws["A10"] = "전체 진행 현황"
ws["A10"].font = F(size=12, bold=True)
rows = [
    ("전체 항목", f'=COUNTIF({rng("D")},"?*")'),
    ("완료 (✔)", f'=COUNTIF({rng("L")},"✔")'),
    ("진행률", "=IF(B11=0,0,B12/B11)"),
    ("Pass", f'=COUNTIF({rng("M")},"Pass")'),
    ("Fail", f'=COUNTIF({rng("M")},"Fail")'),
    ("보류", f'=COUNTIF({rng("M")},"보류")'),
    ("N/A", f'=COUNTIF({rng("M")},"N/A")'),
    ("필수 항목 완료", f'=COUNTIFS({rng("J")},"필수",{rng("L")},"✔")&" / "&COUNTIF({rng("J")},"필수")'),
]
for i, (k, v) in enumerate(rows, start=11):
    ws.cell(i, 1, k).font = F(bold=True)
    c = ws.cell(i, 2, v)
    c.font = F()
    c.alignment = CENTER
    ws.cell(i, 1).border = ws.cell(i, 2).border = BOX
ws["B13"].number_format = "0%"

ws["D10"] = "파트별 진행 현황"
ws["D10"].font = F(size=12, bold=True)
hd = ["파트", "항목 수", "필수", "완료", "진행률", "Pass", "Fail"]
for j, h in enumerate(hd):
    c = ws.cell(11, 4 + j, h)
    c.font = F(bold=True, color="FFFFFF")
    c.fill = HEAD
    c.alignment = CENTER
for i, p in enumerate(PARTS, start=12):
    ws.cell(i, 4, p)
    ws.cell(i, 5, f"=COUNTIF({rng('B')},D{i})")
    ws.cell(i, 6, f'=COUNTIFS({rng("B")},D{i},{rng("J")},"필수")')
    ws.cell(i, 7, f'=COUNTIFS({rng("B")},D{i},{rng("L")},"✔")')
    ws.cell(i, 8, f"=IF(E{i}=0,0,G{i}/E{i})")
    ws.cell(i, 9, f'=COUNTIFS({rng("B")},D{i},{rng("M")},"Pass")')
    ws.cell(i, 10, f'=COUNTIFS({rng("B")},D{i},{rng("M")},"Fail")')
    ws.cell(i, 8).number_format = "0%"
    for col in range(4, 11):
        c = ws.cell(i, col)
        c.font = F()
        c.border = BOX
        c.alignment = CENTER if col > 4 else WRAP

PR = 12 + len(PARTS) + 1
ws.cell(PR, 4, "우선순위별").font = F(size=12, bold=True)
for j, h in enumerate(["우선", "항목 수", "완료", "진행률", "Fail"]):
    c = ws.cell(PR + 1, 4 + j, h)
    c.font = F(bold=True, color="FFFFFF")
    c.fill = HEAD
    c.alignment = CENTER
for i, (p, desc) in enumerate([("필수", "반드시"), ("권장", "가능하면"), ("선택", "장비·시간 있으면")], start=PR + 2):
    ws.cell(i, 4, p)
    ws.cell(i, 5, f"=COUNTIF({rng('J')},D{i})")
    ws.cell(i, 6, f'=COUNTIFS({rng("J")},D{i},{rng("L")},"✔")')
    ws.cell(i, 7, f"=IF(E{i}=0,0,F{i}/E{i})")
    ws.cell(i, 8, f'=COUNTIFS({rng("J")},D{i},{rng("M")},"Fail")')
    ws.cell(i, 9, desc)
    ws.cell(i, 7).number_format = "0%"
    for col in range(4, 10):
        c = ws.cell(i, col)
        c.font = F(color="595959") if col == 9 else F()
        c.border = BOX if col < 9 else Border()
        c.alignment = CENTER
AS = PR + 7
ws.cell(AS, 1, "시험 전제").font = F(size=12, bold=True)
for i, t in enumerate([
    "• RS232 기본 설정: 9600bps · 8N1 · 흐름제어 없음 (실제 POS 에서 확인된 설정). 케이블에 CTS 결선이 없어 RTS/CTS 는 해당 시에만 시험.",
    "• RS232 는 프린터 → PC 응답이 없는 단방향 결선일 수 있음 → 상태 조회 무응답은 결선으로 기록 (S11).",
    "• 블루투스 모듈: 사양 미확보, HC-05 유사(클래식 SPP, Class 2, 목표 거리 약 10m)로 가정.",
    "• 블루투스 PC 쪽은 검증 동글(Realtek 칩, 예: TP-Link UB500) 사용. A·B 동글은 부적합 확인됨.",
    "• 블루투스에서 '텍스트 서식' 인쇄 후 먹통 결함(DEF-BT-01) → 텍스트 서식 품질 시험(F34)은 RS232 로 진행.",
    "• 도구: PrinterTestPOS.exe (RS232/USB/BT 간편 출력), PrinterTester.exe (TC·에이징·진단·교차 시험).",
    "• 도구 표기: 'POS화면' = PrinterTestPOS.exe, 'Tester' = PrinterTester.exe ('[실행]' 표시 = Tester 의 2. 테스트 케이스 탭에서 같은 ID 를 골라 ▶ 실행 가능, 결과는 [계획표 엑셀에 결과 반영] 으로 이 파일에 채워짐), '명령 전송' = Tester 의 명령 탭.",
    "• 우선 = 필수/권장/선택. 권장·선택 항목을 건너뛰면 [측정값/메모] 에 이유를 남기고 결과를 N/A 로 고릅니다.",
], start=AS + 1):
    ws.cell(i, 1, t).font = F()
ws.column_dimensions["A"].width = 18
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 3
ws.column_dimensions["D"].width = 18
for col in "EFGHIJ":
    ws.column_dimensions[col].width = 9

# ---------------- 체크리스트 ----------------
cl = wb.create_sheet(CL)
cl["A1"] = "시험 체크리스트 (기능 · 시리얼 · 블루투스)"
cl["A1"].font = F(size=14, bold=True)
cl["A2"] = "노란색 칸만 입력 (완료 ✔ / 결과 / 측정값 / 시험자 / 일시 / 결함ID)  ·  [파트] 필터로 나눠 보기"
cl["A2"].font = F(color="595959")
heads = ["No", "파트", "분류", "ID", "시험 항목", "시험 방법", "합격 기준", "왜 필요한가\n(안 하면 생기는 문제)", "도구", "우선",
         "시험일", "완료", "결과", "측정값 / 메모", "시험자", "결함ID"]
widths = [5, 13, 10, 7, 20, 40, 32, 30, 18, 6, 10, 6, 8, 26, 8, 10]
for j, (h, w) in enumerate(zip(heads, widths), start=1):
    c = cl.cell(3, j, h)
    c.font = F(bold=True, color="FFFFFF")
    c.fill = HEAD
    c.alignment = CENTER
    c.border = BOX
    cl.column_dimensions[get_column_letter(j)].width = w
cl.row_dimensions[3].height = 32
PRI = {"필수": "C00000", "권장": "1F4E79", "선택": "7F7F7F"}
for i, it in enumerate(ITEMS, start=first):
    for j, v in enumerate([i - first + 1, *it], start=1):
        c = cl.cell(i, j, v)
        c.font = F(bold=(j in (4, 10)), color=PRI.get(v) if j == 10 else None) if j == 10 else F(bold=(j == 4), color=("7F6000" if j == 8 else None))
        c.border = BOX
        c.alignment = CENTER if j in (1, 3, 4, 10) else WRAP
    for j in range(11, 17):
        c = cl.cell(i, j)
        c.fill = INPUT
        c.border = BOX
        c.font = F()
        c.alignment = WRAP if j == 14 else CENTER
    cl.row_dimensions[i].height = 36
cl.freeze_panes = "F4"
cl.auto_filter.ref = f"A3:P{last}"
dv_done = DataValidation(type="list", formula1='"✔"', allow_blank=True)
dv_res = DataValidation(type="list", formula1='"' + ",".join(RESULTS) + '"', allow_blank=True)
cl.add_data_validation(dv_done)
cl.add_data_validation(dv_res)
dv_done.add(f"L{first}:L{last}")
dv_res.add(f"M{first}:M{last}")
area = f"A{first}:P{last}"
cl.conditional_formatting.add(area, FormulaRule(formula=[f'$M{first}="Fail"'], fill=PatternFill("solid", fgColor="F8CBAD")))
cl.conditional_formatting.add(area, FormulaRule(formula=[f'$L{first}="✔"'], fill=PatternFill("solid", fgColor="E2EFDA")))
cl.print_title_rows = "3:3"

# ---------------- 거리·세기 측정 (BT18~BT21) ----------------
ds = wb.create_sheet("거리·세기 측정")
ds["A1"] = "블루투스 거리·신호 세기 측정표 (BT28~BT36)"
ds["A1"].font = F(size=14, bold=True)
for i, t in enumerate([
    "측정 방법: 프린터와 PC(또는 폰)를 같은 높이(약 1m)에 두고 줄자로 직선 거리를 잽니다.",
    "RSSI(dBm): 프린터가 '연결되지 않은' 상태에서 안드로이드 블루투스 스캐너 앱으로 3회 읽습니다 (HC-05 계열은 연결 중엔 검색되지 않음).",
    "인쇄 확인: 조건마다 [연결 확인] 1회 → [영수증] 10장(누락 수) → [대용량 이미지] 1회. 노란 칸만 입력, 평균·판정은 자동.",
], start=2):
    ds.cell(i, 1, t).font = F(color="595959")
dh = ["조건", "환경", "거리(m)", "장애물", "검색됨\n(Y/N)", "연결·출력\n(Y/N)", "연결 시간\n(초)", "RSSI 1", "RSSI 2", "RSSI 3",
      "RSSI 평균\n(dBm)", "영수증 10장\n누락 수", "대용량 이미지\n정상(Y/N)", "끊김 횟수", "판정", "비고"]
dw = [7, 16, 8, 14, 9, 10, 10, 8, 8, 8, 11, 12, 13, 9, 8, 26]
HR = 6
for j, (h, w) in enumerate(zip(dh, dw), start=1):
    c = ds.cell(HR, j, h)
    c.font = F(bold=True, color="FFFFFF")
    c.fill = HEAD
    c.alignment = CENTER
    c.border = BOX
    ds.column_dimensions[get_column_letter(j)].width = w
ds.row_dimensions[HR].height = 34
conds = [("D01", "실내 직선", 0.5, "없음"), ("D02", "실내 직선", 1, "없음"), ("D03", "실내 직선", 3, "없음"),
         ("D04", "실내 직선", 5, "없음"), ("D05", "실내 직선", 7, "없음"), ("D06", "실내 직선", 10, "없음"),
         ("D07", "실내 직선", 12, "없음"), ("D08", "실내 직선", 15, "없음"), ("D09", "실내 직선", 20, "없음"),
         ("D10", "장애물", 5, "벽/파티션 1개"), ("D11", "장애물", 10, "벽/파티션 1개"),
         ("D12", "간섭", 3, "Wi-Fi 공유기 옆"), ("D13", "최대 거리", None, "없음")]
d0 = HR + 1
for i, (cid, env, dist, obs) in enumerate(conds, start=d0):
    for j, v in enumerate([cid, env, dist, obs], start=1):
        c = ds.cell(i, j, v)
        c.font = F(bold=(j == 1))
        c.border = BOX
        c.alignment = CENTER
    for j in list(range(5, 11)) + [12, 13, 14, 16]:
        c = ds.cell(i, j)
        c.fill = INPUT
        c.border = BOX
        c.font = F()
        c.alignment = WRAP if j == 16 else CENTER
    ds.cell(i, 11, f'=IFERROR(ROUND(AVERAGE(H{i}:J{i}),1),"")')
    ds.cell(i, 15, f'=IF(F{i}="","",IF(AND(F{i}="Y",N(L{i})=0,M{i}="Y",N(N{i})=0),"OK","NG"))')
    for j in (11, 15):
        c = ds.cell(i, j)
        c.font = F(bold=(j == 15))
        c.border = BOX
        c.alignment = CENTER
dl = d0 + len(conds) - 1
ds.cell(dl, 3).fill = INPUT
ds.cell(dl, 16, "끊기기 시작한 거리를 '거리' 칸에 입력")
dv_yn = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
ds.add_data_validation(dv_yn)
for col in ("E", "F", "M"):
    dv_yn.add(f"{col}{d0}:{col}{dl}")
ds.conditional_formatting.add(f"O{d0}:O{dl}", FormulaRule(formula=[f'$O{d0}="NG"'], fill=PatternFill("solid", fgColor="F8CBAD")))
ds.conditional_formatting.add(f"O{d0}:O{dl}", FormulaRule(formula=[f'$O{d0}="OK"'], fill=PatternFill("solid", fgColor="C6EFCE")))
ds.freeze_panes = f"E{d0}"

# ---------------- 결함 목록 ----------------
df = wb.create_sheet("결함 목록")
df["A1"] = "결함 목록"
df["A1"].font = F(size=14, bold=True)
df["A2"] = "이미 알려진 결함을 미리 적어 두었습니다. 같은 형식으로 아래에 추가하세요."
df["A2"].font = F(color="595959")
fh = ["결함ID", "발견일", "관련 ID", "현상", "재현 절차", "재현율", "심각도", "임시 조치(우회)", "상태", "담당", "비고"]
fw = [11, 11, 9, 34, 40, 9, 8, 26, 10, 9, 24]
for j, (h, w) in enumerate(zip(fh, fw), start=1):
    c = df.cell(4, j, h)
    c.font = F(bold=True, color="FFFFFF")
    c.fill = HEAD
    c.alignment = CENTER
    c.border = BOX
    df.column_dimensions[get_column_letter(j)].width = w
known = [
    ["DEF-BT-01", "2026-10-01", "BT26, BT27", "블루투스로 텍스트 서식 인쇄 후 블루투스 연결이 먹통이 됨",
     "BT 연결 → 텍스트 서식 패턴 인쇄 → 이후 인쇄 명령에 응답 없음", "확인 필요", "상",
     "POS 간편 화면에서 텍스트 서식 제외", "분석 중", "", "BT27 에서 원인 명령 특정 예정"],
    ["DEF-RS-01", "2026-09-29", "S11", "RS232 상태 조회(DLE EOT) 응답 없음 (인쇄는 정상)",
     "9600bps 연결 → 상태 조회 → 무응답", "확인 필요", "중",
     "도구에서 무응답 채널은 상태 확인 생략", "확인 필요", "", "케이블 RX 결선 확인 필요 (CTS 미결선, DSR 만 있음). S16 핀 배치 측정으로 확인"],
]
for i in range(5, 41):
    for j in range(1, 12):
        v = known[i - 5][j - 1] if i - 5 < len(known) else None
        c = df.cell(i, j, v)
        c.fill = INPUT
        c.border = BOX
        c.font = F()
        c.alignment = WRAP if j in (4, 5, 8, 11) else CENTER
    df.row_dimensions[i].height = 30
dv_sev = DataValidation(type="list", formula1='"상,중,하"', allow_blank=True)
dv_st = DataValidation(type="list", formula1='"신규,분석 중,확인 필요,수정 완료,재확인 완료,보류"', allow_blank=True)
df.add_data_validation(dv_sev)
df.add_data_validation(dv_st)
dv_sev.add("G5:G40")
dv_st.add("I5:I40")

# ---------------- 준비물 ----------------
pp = wb.create_sheet("준비물")
pp["A1"] = "시험 전 준비물"
pp["A1"].font = F(size=14, bold=True)
for j, (h, w) in enumerate(zip(["준비", "항목", "내용", "비고"], [7, 26, 52, 30]), start=1):
    c = pp.cell(3, j, h)
    c.font = F(bold=True, color="FFFFFF")
    c.fill = HEAD
    c.alignment = CENTER
    c.border = BOX
    pp.column_dimensions[get_column_letter(j)].width = w
prep = [
    ("시료 프린터", "3대 (같은 펌웨어), 펌웨어 버전·BT 이름·MAC 기록", "셀프 테스트 출력물 보관"),
    ("POS / PC", "Windows 10 64bit POS (RS232 포트 있음)", "PrinterTestPOS / PrinterTester 최신본"),
    ("RS232 케이블", "RJ45-DB9 케이블 (길이별 보유 시 1.5m / 3m / 10m)", "CTS·RX 결선 여부 기록"),
    ("검증 블루투스 동글", "Realtek 칩 (예: TP-Link UB500)", "A·B 동글 사용 금지"),
    ("안드로이드 폰 2대", "버전이 다른 폰 2대", "Serial Bluetooth Terminal, 블루투스 스캐너 앱"),
    ("아이폰 1대", "BT07 검색 확인용 (없으면 N/A)", ""),
    ("캐시 드로어", "F31~F33 (없으면 N/A)", ""),
    ("바코드 스캐너", "F39 판독용", "폰 카메라 앱으로 대체 가능"),
    ("자·줄자", "자 30cm (F21·F46), 줄자 20m (BT28~36)", ""),
    ("용지", "80mm 감열지 충분히 (에이징 포함 10롤 이상)", "작은 롤(F28)·끝부분 롤(F16)·다른 제조사 용지 2종(F15)"),
    ("가변 전원 (선택)", "F04 전압 변동", "없으면 N/A"),
    ("RJ45 케이블 테스터기", "S16 핀 배치 측정", "멀티미터로 대체 가능"),
    ("LAN 스위치 / PoE 스위치", "S20 / S21 오삽입 시험", "PoE 는 보드 소손 위험 — 개발팀과 협의 후 진행"),
    ("RJ11 전화선", "S22", "선택"),
    ("USB-RS232 변환기", "S28 (CH340 / FTDI / PL2303)", "선택"),
    ("전력계·온도계", "F54 소비 전력, E07 표면 온도", "선택"),
    ("실제 POS 판매 프로그램", "E14", "매장에서 쓰는 프로그램"),
]
dv_p = DataValidation(type="list", formula1='"✔"', allow_blank=True)
pp.add_data_validation(dv_p)
for i, (a, b, c_) in enumerate(prep, start=4):
    for j, v in enumerate([None, a, b, c_], start=1):
        c = pp.cell(i, j, v)
        c.border = BOX
        c.font = F(bold=(j == 2))
        c.alignment = CENTER if j == 1 else WRAP
    pp.cell(i, 1).fill = INPUT
    pp.row_dimensions[i].height = 28
dv_p.add(f"A4:A{3 + len(prep)}")

for sh in wb.worksheets:
    sh.sheet_view.showGridLines = False
    sh.page_setup.orientation = "landscape"
    sh.page_setup.fitToWidth = 1
    sh.page_setup.fitToHeight = 0
    sh.sheet_properties.pageSetUpPr.fitToPage = True
wb.active = 1
wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
from collections import Counter  # noqa: E402
print("saved", OUT, "items", n, dict(Counter(it[0] for it in ITEMS)), dict(Counter(it[8] for it in ITEMS)))
