"""ESC/POS 명령 생성기.

프린터로 보낼 바이트열만 만들고, 통신은 transports.py 가 담당한다.
"""

ESC = b"\x1b"
GS = b"\x1d"
FS = b"\x1c"
DLE = b"\x10"
LF = b"\n"


DOT_MM = 25.4 / 203          # 203dpi 기준 1도트 ≈ 0.125mm
DEFAULT_LINE_DOTS = 34       # ESC 2 기본 줄간격(1/6인치)
QR_CAP_M = (14, 26, 42, 62, 84, 106, 122, 152, 180, 213)   # QR 버전별 바이트 용량(오류정정 M)


class Receipt:
    """ESC/POS 바이트열을 체이닝 방식으로 조립한다.

    height 에 인쇄 길이(도트)를 대략 누적해 두어, 영수증 길이를 일정하게 맞출 때 쓴다.
    """

    def __init__(self, encoding="cp949", korean_mode=True, dots=576):
        self.encoding = encoding
        self.korean_mode = korean_mode
        self.dots = dots
        self.buf = bytearray()
        self.height = 0
        self._spacing = DEFAULT_LINE_DOTS
        self._hmul = 1

    # ---- 기본 ----
    def raw(self, data: bytes):
        self.buf += data
        return self

    def init(self):
        self.buf += ESC + b"@"
        self._spacing, self._hmul = DEFAULT_LINE_DOTS, 1
        if self.korean_mode:
            # ESC R 13: 국제 문자셋 한국, FS &: 2바이트(한글) 모드 켜기
            self.buf += ESC + b"R" + bytes([13]) + FS + b"&"
        return self

    def text(self, s: str):
        self.buf += s.encode(self.encoding, errors="replace")
        return self

    def _advance(self):
        self.height += max(self._spacing, 24 * self._hmul)

    def line(self, s: str = ""):
        self.text(s).raw(LF)
        self._advance()
        return self

    def feed(self, n=1):
        n = max(0, min(255, n))
        self.buf += ESC + b"d" + bytes([n])
        self.height += n * self._spacing
        return self

    def feed_dots(self, n):
        """ESC J n: n 도트 급지 (255 넘으면 나눠 보냄)."""
        n = int(max(0, n))
        self.height += n
        while n > 0:
            k = min(255, n)
            self.buf += ESC + b"J" + bytes([k])
            n -= k
        return self

    # ---- 서식 ----
    def align(self, where="left"):
        self.buf += ESC + b"a" + bytes([{"left": 0, "center": 1, "right": 2}[where]])
        return self

    def bold(self, on=True):
        self.buf += ESC + b"E" + bytes([1 if on else 0])
        return self

    def underline(self, n=1):
        self.buf += ESC + b"-" + bytes([n])
        return self

    def reverse(self, on=True):
        self.buf += GS + b"B" + bytes([1 if on else 0])
        return self

    def size(self, w=1, h=1):
        self.buf += GS + b"!" + bytes([((w - 1) << 4) | (h - 1)])
        self._hmul = h
        return self

    def font(self, b=False):
        """ESC M: 폰트 A(12x24) / B(9x17)."""
        self.buf += ESC + b"M" + bytes([1 if b else 0])
        return self

    def upside_down(self, on=True):
        """ESC {: 180도 뒤집어 인쇄."""
        self.buf += ESC + b"{" + bytes([1 if on else 0])
        return self

    def rotate90(self, on=True):
        """ESC V: 90도 회전 인쇄."""
        self.buf += ESC + b"V" + bytes([1 if on else 0])
        return self

    def codepage(self, n):
        """ESC t n: 문자 코드 테이블 선택."""
        self.buf += ESC + b"t" + bytes([n])
        return self

    def line_spacing(self, dots=None):
        if dots is None:
            self.buf += ESC + b"2"
            self._spacing = DEFAULT_LINE_DOTS
        else:
            self.buf += ESC + b"3" + bytes([dots])
            self._spacing = dots
        return self

    def reset_style(self):
        return self.align("left").bold(False).underline(0).reverse(False).size(1, 1)

    # ---- 기구 ----
    def cut(self, partial=False, feed=True):
        if feed:
            # GS V 65/66 n: n 도트 급지 후 컷
            self.buf += GS + b"V" + bytes([66 if partial else 65, 0])
        else:
            self.buf += GS + b"V" + bytes([1 if partial else 0])
        return self

    def drawer(self, pin=0, on_ms=50, off_ms=500):
        self.buf += ESC + b"p" + bytes([pin, min(255, on_ms // 2), min(255, off_ms // 2)])
        return self

    # ---- 바코드 ----
    def barcode(self, kind: str, data: str, height=80, width=2, hri=2):
        self.buf += GS + b"h" + bytes([height]) + GS + b"w" + bytes([width]) + GS + b"H" + bytes([hri])
        d = data.encode("ascii")
        if kind == "CODE128":
            d = b"{B" + d
            self.buf += GS + b"k" + bytes([73, len(d)]) + d
        elif kind == "EAN13":
            self.buf += GS + b"k" + bytes([67, len(d)]) + d
        elif kind == "CODE39":
            self.buf += GS + b"k" + bytes([69, len(d)]) + d
        else:
            raise ValueError(kind)
        self.raw(LF)
        self.height += height + (30 if hri else 0) + 10
        return self

    def qr(self, data: str, module=6, ecc="M"):
        d = data.encode("utf-8")
        ecc_n = {"L": 48, "M": 49, "Q": 50, "H": 51}[ecc]

        def fn(cn, fn_, payload=b""):
            ln = len(payload) + 2  # pL pH = cn, fn 과 파라미터의 바이트 수
            return GS + b"(k" + bytes([ln & 0xFF, ln >> 8, cn, fn_]) + payload

        self.buf += fn(49, 65, bytes([50, 0]))          # 모델 2
        self.buf += fn(49, 67, bytes([module]))         # 모듈 크기
        self.buf += fn(49, 69, bytes([ecc_n]))          # 오류 정정
        self.buf += fn(49, 80, b"0" + d)                # 데이터 저장
        self.buf += fn(49, 81, b"0")                    # 인쇄
        self.raw(LF)
        ver = next((i + 1 for i, c in enumerate(QR_CAP_M) if len(d) <= c), 12)
        self.height += (17 + 4 * ver) * module + 10
        return self

    # ---- 이미지 ----
    def raster(self, width_dots: int, rows):
        """rows: 각 행이 0/1 리스트(길이 width_dots). GS v 0 래스터 인쇄."""
        wbytes = (width_dots + 7) // 8
        data = bytearray()
        for row in rows:
            for bx in range(wbytes):
                b = 0
                for bit in range(8):
                    x = bx * 8 + bit
                    if x < width_dots and row[x]:
                        b |= 0x80 >> bit
                data.append(b)
        h = len(rows)
        self.buf += GS + b"v0" + bytes([0, wbytes & 0xFF, wbytes >> 8, h & 0xFF, h >> 8]) + data
        self.height += h
        return self

    def height_mm(self):
        return self.height * DOT_MM

    def bytes(self) -> bytes:
        return bytes(self.buf)


# ---- 실시간 상태 조회 (DLE EOT n) ----

def dle_eot(n: int) -> bytes:
    return DLE + b"\x04" + bytes([n])


STATUS_NAMES = {1: "프린터", 2: "오프라인 원인", 3: "에러 원인", 4: "용지 센서"}


def parse_status(n: int, b: int) -> dict:
    """DLE EOT 응답 1바이트 해석. 고정 비트(bit1=1, bit4=1, bit0=0, bit7=0) 검사 포함."""
    valid = (b & 0x93) == 0x12
    flags = []
    error = False
    warn = False
    if n == 1:
        if b & 0x08:
            flags.append("오프라인")
            error = True
        if b & 0x04:
            flags.append("드로어 핀 High")
    elif n == 2:
        for bit, name in ((0x04, "커버 열림"), (0x08, "FEED 버튼 누름"), (0x20, "용지 없음으로 정지"), (0x40, "에러 발생")):
            if b & bit:
                flags.append(name)
                if bit != 0x08:
                    error = True
    elif n == 3:
        for bit, name in ((0x08, "커터 에러"), (0x20, "복구 불가 에러"), (0x40, "자동 복구 에러(헤드 온도 등)")):
            if b & bit:
                flags.append(name)
                error = True
    elif n == 4:
        if b & 0x0C:
            flags.append("용지 잔량 부족")
            warn = True
        if b & 0x60:
            flags.append("용지 없음")
            error = True
    return {
        "n": n,
        "name": STATUS_NAMES.get(n, str(n)),
        "byte": b,
        "hex": f"0x{b:02X}",
        "valid": valid,
        "flags": flags,
        "error": error,
        "warn": warn,
        "text": ", ".join(flags) if flags else "정상",
    }


# ---- 프린터 정보 (GS I n) ----
PRINTER_INFO = {65: "펌웨어 버전", 66: "제조사", 67: "모델명", 68: "시리얼 번호"}


def gs_i(n: int) -> bytes:
    return GS + b"I" + bytes([n])
