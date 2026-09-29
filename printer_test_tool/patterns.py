# -*- coding: utf-8 -*-
"""테스트용 인쇄 패턴.

모든 함수는 ESC/POS 바이트열을 돌려준다. opts 는 공통 설정:
  dots(인쇄 폭 도트, 80mm=576), encoding, korean_mode, cut("full"/"partial"/"none"),
  length_mm(영수증 길이 — 모든 출력물을 이 길이로 맞춘다. 0 이면 내용 길이 그대로)

channel 은 "프린터이름/인터페이스" (예: "프린터1/RS232") — 영수증 머리에 크게 찍어서
여러 프린터·여러 통신 방식의 출력물을 구분한다.
"""
import datetime
import math

from escpos import DOT_MM, Receipt

DEFAULT_OPTS = {"dots": 576, "encoding": "cp949", "korean_mode": True, "cut": "partial", "length_mm": 120}
MM_PER_DOT = DOT_MM


def _r(opts):
    o = {**DEFAULT_OPTS, **(opts or {})}
    return Receipt(o["encoding"], o["korean_mode"], o["dots"]).init(), o


def _finish(r, o, fixed_length=True):
    """영수증 길이를 opts["length_mm"] 로 맞춘 뒤 컷."""
    target = int((o.get("length_mm") or 0) / MM_PER_DOT)
    if fixed_length and target > r.height:
        r.feed_dots(target - r.height)
    if o["cut"] == "full":
        r.cut(partial=False)
    elif o["cut"] == "partial":
        r.cut(partial=True)
    else:
        r.feed(4)
    return r.bytes()


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cols(o):
    """기본 폰트(12x24) 기준 한 줄 글자 수."""
    return o["dots"] // 12


def _w(s):
    """인쇄 폭(반각 글자 수). 한글은 2칸."""
    return len(s.encode("cp949", "replace"))


def _ljust(s, n):
    return s + " " * max(1, n - _w(s))


def split_channel(channel):
    """'프린터1/RS232' -> ('프린터1', 'RS232')"""
    if "/" in (channel or ""):
        p, i = channel.rsplit("/", 1)
        return p, i
    return channel or "", ""


def _header(r, o, title, channel="", seq=None):
    """모든 영수증 공통 머리: 프린터 이름 / 통신 방식 / 시험명 / 순번 / 시각."""
    printer, iface = split_channel(channel)
    r.align("center")
    if printer:
        r.reverse(True).bold(True).size(2, 2).line(f" {printer} ").size(1, 1).bold(False).reverse(False)
    if iface:
        r.bold(True).size(2, 1).line(f"[ {iface} ]").size(1, 1).bold(False)
    r.bold(True).line(title).bold(False)
    info = [f"#{seq:06d}"] if seq is not None else []
    info.append(_now())
    r.line("  ".join(info)).align("left").line("-" * _cols(o))


# ---------------- 래스터 이미지 생성 ----------------

def _bayer(v, x, y):
    """0~1 명도 v 를 4x4 Bayer 디더링 -> 1(검정)/0."""
    m = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
    return 1 if v > (m[y & 3][x & 3] + 0.5) / 16 else 0


def img_gradient(w, h):
    return [[_bayer(x / (w - 1), x, y) for x in range(w)] for y in range(h)]


def img_logo(w, h):
    """원 + 체커 + 대각선: 왜곡/누락이 눈에 잘 띄는 패턴."""
    cx, cy, rad = w / 2, h / 2, min(w, h) * 0.45
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            d = math.hypot(x - cx, y - cy)
            ring = abs(d - rad) < 4
            checker = ((x // 16) + (y // 16)) % 2 == 0 and d < rad * 0.6
            diag = abs((x - y) % 64) < 2
            border = x < 3 or x >= w - 3 or y < 3 or y >= h - 3
            row.append(1 if (ring or checker or diag or border) else 0)
        rows.append(row)
    return rows


def img_dot_check(w):
    """헤드 도트 체크: 전면 검정 띠 + 1도트 계단(누락 도트가 흰 세로줄로 보임)."""
    rows = [[1] * w for _ in range(40)]
    rows += [[0] * w for _ in range(8)]
    for step in range(8):
        rows += [[1 if x % 8 == step else 0 for x in range(w)] for _ in range(6)]
    rows += [[0] * w for _ in range(8)]
    rows += [[1] * w for _ in range(40)]
    return rows


def img_hruler(w):
    """가로 눈금자: 1mm 짧은 눈금, 5mm 중간, 10mm 긴 눈금 (좌우 여백·인쇄 폭 확인)."""
    rows = []
    mm = 1 / MM_PER_DOT
    for y in range(48):
        row = [0] * w
        for k in range(int(w / mm) + 1):
            x = int(round(k * mm))
            if x >= w:
                break
            ln = 48 if k % 10 == 0 else (32 if k % 5 == 0 else 16)
            if y < ln:
                for dx in range(2):
                    if x + dx < w:
                        row[x + dx] = 1
        rows.append(row)
    rows += [[1] * w for _ in range(2)]
    return rows


def img_vruler(w, length_mm):
    """세로 눈금자: 왼쪽 가장자리에 1mm 눈금, 10mm 마다 긴 가로선 (급지 거리 확인)."""
    mm = 1 / MM_PER_DOT
    h = int(length_mm * mm)
    rows = []
    marks = {int(round(k * mm)): k for k in range(int(length_mm) + 1)}
    for y in range(h):
        row = [0] * w
        row[0] = row[1] = 1
        k = marks.get(y)
        if k is not None:
            ln = w if k % 10 == 0 else (48 if k % 5 == 0 else 24)
            for x in range(ln):
                row[x] = 1
        rows.append(row)
    return rows


# ---------------- 패턴 ----------------

def pattern_info(opts=None, channel="", note=""):
    """연결 확인용 영수증."""
    r, o = _r(opts)
    _header(r, o, "연결 확인", channel)
    for ln in (note or "").splitlines():
        r.line(ln)
    r.line("ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789")
    r.line("가나다라마바사 아자차카타파하 한글 출력")
    r.align("center").bold(True).line("이 영수증이 나오면 통신 정상").bold(False).align("left")
    return _finish(r, o)


def pattern_receipt(opts=None, channel="", seq=None, with_image=False):
    """일반 매장 영수증 형태(에이징 기본 패턴)."""
    r, o = _r(opts)
    _header(r, o, "영수증 시험", channel, seq)
    cols = _cols(o)
    items = [("아메리카노", 2, 4500), ("카페라떼", 1, 5000), ("치즈케이크", 1, 6500),
             ("생수 500ml", 3, 1000), ("샌드위치(햄치즈)", 1, 5800)]
    r.line(_ljust("상품명", cols - 18) + "  수량" + "        금액")
    total = 0
    for name, q, p in items:
        amt = q * p
        total += amt
        r.line(_ljust(name, cols - 18) + f"{q:>6}{amt:>12,}")
    r.line("-" * cols)
    r.bold(True).size(1, 2).line(_ljust("합계", cols - 12) + f"{total:>12,}").size(1, 1).bold(False)
    r.line(_ljust("부가세", cols - 12) + f"{total // 11:>12,}")
    r.line("-" * cols)
    r.align("center")
    r.barcode("CODE128", f"{seq or 0:012d}", height=50)
    if with_image:
        r.raster(o["dots"], img_logo(o["dots"], 96))
    else:
        r.qr(f"TEST|{channel}|{seq}|{_now()}", module=3)
    r.line("이용해 주셔서 감사합니다").align("left")
    return _finish(r, o)


def pattern_text_format(opts=None, channel=""):
    """P01 텍스트 서식."""
    r, o = _r(opts)
    _header(r, o, "텍스트 서식", channel)
    r.align("left").line("왼쪽 LEFT").align("center").line("가운데 CENTER").align("right").line("오른쪽 RIGHT")
    r.align("left")
    r.bold(True).line("굵게 BOLD 가나다").bold(False)
    r.underline(1).line("밑줄1 UNDERLINE").underline(2).line("밑줄2 UNDERLINE").underline(0)
    r.reverse(True).line(" 반전 REVERSE ").reverse(False)
    r.font(True).line("폰트B FONT B 0123456789 abcdefghijklmnopqrstuvwxyz").font(False)
    for w, h in ((2, 1), (1, 2), (2, 2), (3, 3)):
        r.size(w, h).line(f"{w}x{h} 가A").size(1, 1)
    return _finish(r, o)


def pattern_korean(opts=None, channel=""):
    """P02 한글/특수문자."""
    r, o = _r(opts)
    _header(r, o, "한글 출력", channel)
    for ln in ("다람쥐 헌 쳇바퀴에 타고파.",
               "[완성형] 가각간갇갈감갑갓강 똠똥뙤뛰뜀",
               "[완성형] 흙흠흡흥흩희힁 뷁뛟쐛",
               "[자음] ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ",
               "[모음] ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ",
               "[특수] ①②③ ㈜ ℃ ± × ÷ ※",
               "[도형] ☆★ ○● □■ △▲ → ←",
               "[통화] \\ ₩ $ ￦ 1,234,567원",
               "[영문] The quick brown fox jumps",
               "[숫자] 0123456789 !@#$%^&*()_+-="):
        r.line(ln)
    r.size(2, 2).line("큰 글씨 한글").size(1, 1)
    return _finish(r, o)


def pattern_barcode(opts=None, channel=""):
    """P03 1D 바코드."""
    r, o = _r(opts)
    _header(r, o, "1D 바코드", channel)
    r.align("center")
    r.line("CODE128 : TEST-12345").barcode("CODE128", "TEST-12345", height=60)
    r.line("EAN13 : 880123456789").barcode("EAN13", "880123456789", height=60)
    r.line("CODE39 : ABC123").barcode("CODE39", "ABC123", height=60)
    r.align("left")
    return _finish(r, o)


def pattern_qr(opts=None, channel=""):
    """P04 2D(QR) 바코드."""
    r, o = _r(opts)
    _header(r, o, "QR 코드", channel)
    r.align("center")
    r.line("QR 모듈 4").qr("https://example.com/qr-test/size4", module=4)
    r.line("QR 모듈 6 / 한글").qr("열전사 프린터 QR 한글 테스트", module=6)
    r.align("left")
    return _finish(r, o)


def pattern_image(opts=None, channel=""):
    """P05 이미지."""
    r, o = _r(opts)
    _header(r, o, "이미지 시험", channel)
    r.raster(o["dots"], img_logo(o["dots"], 200))
    r.raster(o["dots"], img_gradient(o["dots"], 64))
    return _finish(r, o)


def pattern_density(opts=None, channel=""):
    """P06 농도 — 단계별 회색 막대. 농도 설정을 바꿔 가며 반복 인쇄해 비교."""
    r, o = _r(opts)
    _header(r, o, "농도 시험", channel)
    w = o["dots"]
    for pct in (0, 25, 50, 75, 100):
        r.line(f"{pct:>3}%")
        r.raster(w, [[_bayer(pct / 100, x, y) for x in range(w)] for y in range(40)])
    return _finish(r, o)


def pattern_dot_check(opts=None, channel=""):
    """B02 보조 — 헤드 도트 누락 확인."""
    r, o = _r(opts)
    _header(r, o, "헤드 도트 체크", channel)
    r.line("흰 세로줄이 보이면 해당 도트 불량")
    r.raster(o["dots"], img_dot_check(o["dots"]))
    return _finish(r, o)


def pattern_ruler(opts=None, channel=""):
    """E02 급지 정확도/여백 — 가로·세로 눈금자. 자로 재서 10mm 간격이 맞는지 확인."""
    r, o = _r(opts)
    _header(r, o, "급지 정확도 눈금자", channel)
    r.line("가로 눈금: 1mm/5mm/10mm, 폭과 좌우 여백 확인")
    r.raster(o["dots"], img_hruler(o["dots"]))
    r.line("세로 눈금: 긴 선 사이 = 10mm (자로 확인)")
    r.raster(o["dots"], img_vruler(o["dots"], 50))
    r.line("50mm 끝")
    return _finish(r, o)


def pattern_cut_position(opts=None, channel=""):
    """E03 컷 위치 — 컷 직전에 기준선을 찍어, 기준선~절단면 거리를 잰다."""
    r, o = _r(opts)
    _header(r, o, "컷 위치 확인", channel)
    r.line("아래 굵은 선부터 절단면까지 거리를 재세요")
    r.line("(프린터 사양의 헤드-커터 거리와 비교)")
    target = int((o.get("length_mm") or 0) / MM_PER_DOT)
    if target > r.height + 16:
        r.feed_dots(target - r.height - 16)
    r.raster(o["dots"], [[1] * o["dots"] for _ in range(8)] + [[0] * o["dots"] for _ in range(8)])
    return _finish(r, o, fixed_length=False)


def pattern_charset(opts=None, channel=""):
    """E04 문자표 — ASCII 와 코드페이지(ESC t 0) 상위 문자 전체."""
    r, o = _r(opts)
    _header(r, o, "문자표 (코드페이지 0)", channel)
    r.raw(b"\x1c\x2e")                        # FS . : 한글(2바이트) 모드 해제
    r.codepage(0)
    for hi in range(2, 16):
        row = bytes(range(hi * 16, hi * 16 + 16))
        r.raw(f"{hi:X}x ".encode("ascii") + bytes(b for c in row for b in (c, 0x20)) + b"\n")
        r._advance()
    if o["korean_mode"]:
        r.raw(b"\x1c\x26")                    # FS & : 한글 모드 복귀
    r.line("한글 모드 복귀 확인: 가나다")
    return _finish(r, o)


def pattern_rotate(opts=None, channel=""):
    """E05 회전/뒤집기 인쇄."""
    r, o = _r(opts)
    _header(r, o, "회전 / 뒤집기", channel)
    r.line("[정상] ABC 가나다 123")
    r.upside_down(True).line("[180도] ABC 가나다 123").upside_down(False)
    r.rotate90(True).line("[90도] ABC 123").rotate90(False)
    r.height += 12 * 12                       # 90도 회전 줄은 세로로 길어짐(대략)
    r.line("[정상 복귀] ABC 가나다 123")
    return _finish(r, o)


def pattern_speed(opts=None, channel="", length_mm=500):
    """P07 인쇄 속도 — 정해진 길이를 인쇄 (속도 측정은 예외적으로 길게)."""
    r, o = _r(opts)
    line_dots = 24
    lines = int(length_mm / (line_dots * MM_PER_DOT))
    _header(r, o, f"속도 시험 {length_mm}mm", channel)
    r.line_spacing(line_dots)
    for i in range(1, lines + 1):
        r.line(f"{i:04d} SPEED TEST 속도 시험 {i * line_dots * MM_PER_DOT:8.1f}mm")
    r.line_spacing()
    return _finish(r, o, fixed_length=False)


def pattern_large_image(opts=None, channel="", height=640, seq=None):
    """R03/R04/U07/T07 — 대용량(약 46KB) 이미지. 흐름제어·버퍼 시험용."""
    r, o = _r(opts)
    _header(r, o, "대용량 이미지", channel, seq)
    w = o["dots"]
    rows = img_logo(w, height // 2) + img_gradient(w, height // 2)
    r.raster(w, rows)
    r.line(f"END #{seq if seq is not None else 0} — 이 줄이 보이면 누락 없음")
    return _finish(r, o)


def pattern_heat(opts=None, channel="", length_mm=60):
    """헤드 과열 보호 확인 — 전면 검정."""
    r, o = _r(opts)
    _header(r, o, f"전면 검정 {length_mm}mm", channel)
    h = int(length_mm / MM_PER_DOT)
    w = o["dots"]
    while h > 0:
        n = min(h, 400)
        r.raster(w, [[1] * w for _ in range(n)])
        h -= n
    return _finish(r, o)


def pattern_channel_mark(opts=None, channel="", seq=0, lines=16):
    """X02/X03 동시 인쇄 — 모든 줄에 채널 이름을 넣어 섞였는지 확인."""
    r, o = _r(opts)
    _header(r, o, f"동시 인쇄 #{seq}", channel)
    tag = channel.replace("/", " ")
    for i in range(1, lines + 1):
        r.line(f"[{tag}] {i:03d}/{lines}")
    r.align("center").bold(True).line(f"{tag} 끝").bold(False).align("left")
    return _finish(r, o)


def pattern_baud(opts=None, channel="", baud=0):
    """R01 — 설정한 Baud 로 인쇄. 모든 문자 범위 포함."""
    r, o = _r(opts)
    _header(r, o, f"BAUD {baud}", channel)
    asc = "".join(chr(c) for c in range(0x20, 0x7F))
    for i in range(0, len(asc), 40):
        r.line(asc[i:i + 40])
    r.line("가나다라마바사아자차카타파하 한글 확인")
    r.line(f"Baud {baud} 정상 인쇄되면 PASS")
    return _finish(r, o)


def pattern_cut(opts=None, channel="", seq=0, partial=True):
    r, o = _r({**(opts or {}), "cut": "partial" if partial else "full"})
    _header(r, o, f"{'부분' if partial else '전체'} 컷 #{seq:03d}", channel)
    return _finish(r, o)


PATTERNS = {
    "연결 확인": pattern_info,
    "영수증": pattern_receipt,
    "영수증+이미지": lambda opts=None, channel="", seq=None: pattern_receipt(opts, channel, seq, True),
    "텍스트 서식": pattern_text_format,
    "한글": pattern_korean,
    "1D 바코드": pattern_barcode,
    "QR 코드": pattern_qr,
    "이미지": pattern_image,
    "농도": pattern_density,
    "헤드 도트 체크": pattern_dot_check,
    "급지 눈금자": pattern_ruler,
    "컷 위치": pattern_cut_position,
    "문자표": pattern_charset,
    "회전/뒤집기": pattern_rotate,
    "대용량 이미지": pattern_large_image,
    "전면 검정": pattern_heat,
}

# 에이징에서 쓸 수 있는 패턴(순번 seq 를 받는 것)
AGING_PATTERNS = {
    "영수증": lambda o, ch, s: pattern_receipt(o, ch, s),
    "영수증+이미지": lambda o, ch, s: pattern_receipt(o, ch, s, True),
    "대용량 이미지": lambda o, ch, s: pattern_large_image(o, ch, 640, s),
    "채널 표시": lambda o, ch, s: pattern_channel_mark(o, ch, s, 10),
}
