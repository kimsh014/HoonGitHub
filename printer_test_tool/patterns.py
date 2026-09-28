"""테스트용 인쇄 패턴.

모든 함수는 ESC/POS 바이트열을 돌려준다. opts 는 공통 설정:
  dots(인쇄 폭 도트, 80mm=576), encoding, korean_mode, cut("full"/"partial"/"none")
"""
import datetime
import math

from escpos import Receipt

DEFAULT_OPTS = {"dots": 576, "encoding": "cp949", "korean_mode": True, "cut": "partial"}
MM_PER_DOT = 25.4 / 203  # 203dpi 기준 약 0.125mm


def _r(opts):
    o = {**DEFAULT_OPTS, **(opts or {})}
    return Receipt(o["encoding"], o["korean_mode"], o["dots"]).init(), o


def _finish(r, o):
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


def _header(r, o, title, channel="", seq=None):
    r.align("center").bold(True).size(2, 2).line(title).size(1, 1).bold(False)
    info = []
    if channel:
        info.append(f"CH:{channel}")
    if seq is not None:
        info.append(f"#{seq:06d}")
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
    rows = [[1] * w for _ in range(48)]
    rows += [[0] * w for _ in range(8)]
    for step in range(8):
        rows += [[1 if x % 8 == step else 0 for x in range(w)] for _ in range(6)]
    rows += [[0] * w for _ in range(8)]
    rows += [[1] * w for _ in range(48)]
    return rows


# ---------------- 패턴 ----------------

def pattern_info(opts=None, channel="", note=""):
    """연결 확인용 짧은 영수증."""
    r, o = _r(opts)
    _header(r, o, "연결 확인", channel)
    r.line(f"인터페이스 : {channel}")
    if note:
        r.line(note)
    r.line("ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789")
    r.line("가나다라마바사 아자차카타파하 한글 출력")
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
    code = f"{seq or 0:012d}"
    r.barcode("CODE128", code, height=60)
    r.qr(f"TEST|{channel}|{seq}|{_now()}", module=4)
    if with_image:
        r.raster(o["dots"], img_logo(o["dots"], 160))
    r.line("이용해 주셔서 감사합니다").align("left")
    return _finish(r, o)


def pattern_text_format(opts=None, channel=""):
    """P01 텍스트 서식."""
    r, o = _r(opts)
    _header(r, o, "텍스트 서식", channel)
    r.line("[정렬]").align("left").line("왼쪽 LEFT").align("center").line("가운데 CENTER") \
        .align("right").line("오른쪽 RIGHT").align("left")
    r.line("[굵게]").bold(True).line("굵게 BOLD 가나다").bold(False)
    r.line("[밑줄]").underline(1).line("밑줄1 UNDERLINE").underline(2).line("밑줄2 UNDERLINE").underline(0)
    r.line("[반전]").reverse(True).line(" 반전 REVERSE ").reverse(False)
    r.line("[크기 가로x세로]")
    for w, h in ((1, 1), (2, 1), (1, 2), (2, 2), (3, 3), (4, 4)):
        r.size(w, h).line(f"{w}x{h} 가A").size(1, 1)
    r.line("[줄 간격]")
    for d in (24, 40, 60):
        r.line_spacing(d).line(f"줄간격 {d}도트").line(f"줄간격 {d}도트")
    r.line_spacing()
    return _finish(r, o)


def pattern_korean(opts=None, channel=""):
    """P02 한글/특수문자."""
    r, o = _r(opts)
    _header(r, o, "한글 출력", channel)
    r.line("다람쥐 헌 쳇바퀴에 타고파.")
    r.line("키스의 고유조건은 입술끼리 만나야 하고")
    r.line("특별한 기술은 필요치 않다.")
    r.line("[완성형] 가각간갇갈감갑갓강 똠똥뙤뛰뜀")
    r.line("[완성형] 흙흠흡흥흩희힁 뷁뛟쐛")
    r.line("[자음] ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ")
    r.line("[모음] ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ")
    r.line("[특수] ①②③ ㈜ ℃ ± × ÷ ※")
    r.line("[도형] ☆★ ○● □■ △▲ → ←")
    r.line("[통화] \\ ₩ $ ￦ 1,234,567원")
    r.line("[영문] The quick brown fox jumps")
    r.line("       over the lazy dog")
    r.line("[숫자] 0123456789 !@#$%^&*()_+-=")
    r.line("[기호] []{};':\",./<>?")
    r.size(2, 2).line("큰 글씨 한글").size(1, 1)
    return _finish(r, o)


def pattern_barcode(opts=None, channel=""):
    """P03/P04 1D·2D 바코드."""
    r, o = _r(opts)
    _header(r, o, "바코드 시험", channel)
    r.align("center")
    r.line("CODE128 : TEST-12345").barcode("CODE128", "TEST-12345")
    r.line("EAN13 : 880123456789").barcode("EAN13", "880123456789")
    r.line("CODE39 : ABC123").barcode("CODE39", "ABC123")
    for m in (3, 5, 8):
        r.line(f"QR 모듈 {m}").qr(f"https://example.com/qr-test/size{m}", module=m)
    r.line("QR 한글: 테스트 데이터").qr("열전사 프린터 QR 한글 테스트", module=5)
    r.align("left")
    return _finish(r, o)


def pattern_image(opts=None, channel=""):
    """P05 이미지."""
    r, o = _r(opts)
    _header(r, o, "이미지 시험", channel)
    r.line("[로고 패턴]")
    r.raster(o["dots"], img_logo(o["dots"], 240))
    r.line("[그라데이션]")
    r.raster(o["dots"], img_gradient(o["dots"], 80))
    return _finish(r, o)


def pattern_density(opts=None, channel=""):
    """P06 농도 — 단계별 회색 막대. 농도 설정을 바꿔 가며 반복 인쇄해 비교."""
    r, o = _r(opts)
    _header(r, o, "농도 시험", channel)
    w = o["dots"]
    for pct in (0, 12, 25, 37, 50, 62, 75, 87, 100):
        r.line(f"{pct:>3}%")
        r.raster(w, [[_bayer(pct / 100, x, y) for x in range(w)] for y in range(32)])
    return _finish(r, o)


def pattern_dot_check(opts=None, channel=""):
    """B02 보조 — 헤드 도트 누락 확인."""
    r, o = _r(opts)
    _header(r, o, "헤드 도트 체크", channel)
    r.line("흰 세로줄이 보이면 해당 도트 불량")
    r.raster(o["dots"], img_dot_check(o["dots"]))
    return _finish(r, o)


def pattern_speed(opts=None, channel="", length_mm=1000):
    """P07 인쇄 속도 — 줄 간격을 고정해 정해진 길이를 인쇄."""
    r, o = _r(opts)
    line_dots = 24
    lines = int(length_mm / (line_dots * MM_PER_DOT))
    _header(r, o, f"속도 시험 {length_mm}mm", channel)
    r.line_spacing(line_dots)
    for i in range(1, lines + 1):
        r.line(f"{i:04d} SPEED TEST 속도 시험 {i * line_dots * MM_PER_DOT:8.1f}mm")
    r.line_spacing()
    return _finish(r, o)


def pattern_large_image(opts=None, channel="", height=800, seq=None):
    """R03/R04/U07/T07 — 대용량(약 57KB) 이미지. 흐름제어·버퍼 시험용."""
    r, o = _r(opts)
    _header(r, o, "대용량 이미지", channel, seq)
    w = o["dots"]
    rows = img_logo(w, height // 2) + img_gradient(w, height // 2)
    r.raster(w, rows)
    r.line(f"끝 표시 END #{seq if seq is not None else 0} — 이 줄이 보이면 데이터 누락 없음")
    return _finish(r, o)


def pattern_heat(opts=None, channel="", length_mm=100):
    """헤드 과열 보호 확인 — 전면 검정."""
    r, o = _r(opts)
    _header(r, o, f"전면 검정 {length_mm}mm", channel)
    h = int(length_mm / MM_PER_DOT)
    w = o["dots"]
    # 한 번에 너무 큰 래스터를 보내지 않도록 나눠 보냄
    while h > 0:
        n = min(h, 400)
        r.raster(w, [[1] * w for _ in range(n)])
        h -= n
    return _finish(r, o)


def pattern_channel_mark(opts=None, channel="", seq=0, lines=30):
    """X02/X03 동시 인쇄 — 모든 줄에 채널 이름을 넣어 섞였는지 확인."""
    r, o = _r(opts)
    r.align("center").reverse(True).size(3, 3).line(f" {channel} ").size(1, 1).reverse(False).align("left")
    r.line(f"동시 인쇄 시험 #{seq}  {_now()}")
    for i in range(1, lines + 1):
        r.line(f"[{channel}] {i:03d}/{lines} " + channel * 6)
    r.align("center").bold(True).line(f"{channel} 끝").bold(False).align("left")
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
    r.align("center").line(f"{'PARTIAL' if partial else 'FULL'} CUT #{seq:03d}").align("left")
    return _finish(r, o)


PATTERNS = {
    "연결 확인": pattern_info,
    "영수증": pattern_receipt,
    "영수증+이미지": lambda opts=None, channel="", seq=None: pattern_receipt(opts, channel, seq, True),
    "텍스트 서식": pattern_text_format,
    "한글": pattern_korean,
    "바코드/QR": pattern_barcode,
    "이미지": pattern_image,
    "농도": pattern_density,
    "헤드 도트 체크": pattern_dot_check,
    "대용량 이미지": pattern_large_image,
    "전면 검정 100mm": pattern_heat,
    "속도 1m": pattern_speed,
}

# 에이징에서 쓸 수 있는 패턴(순번 seq 를 받는 것)
AGING_PATTERNS = {
    "영수증": lambda o, ch, s: pattern_receipt(o, ch, s),
    "영수증+이미지": lambda o, ch, s: pattern_receipt(o, ch, s, True),
    "대용량 이미지": lambda o, ch, s: pattern_large_image(o, ch, 800, s),
    "채널 표시(짧게)": lambda o, ch, s: pattern_channel_mark(o, ch, s, 10),
}
